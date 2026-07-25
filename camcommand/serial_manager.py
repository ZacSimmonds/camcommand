from __future__ import annotations

import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import serial

from .exceptions import ConnectionError, ProtocolError


def _normalize_port_name(port: str) -> str:
    port = port.strip()
    if sys.platform == "win32":
        up = port.upper()
        if up.startswith("COM"):
            # COM10+ sometimes requires the Win32 device prefix.
            try:
                n = int(up[3:])
            except ValueError:
                return port
            if n >= 10 and not port.startswith("\\\\.\\"):
                return f"\\\\.\\{up}"
            return up
    return port


def _build_command_line(
    command: str,
    *,
    acs_port: Optional[int] = None,
    line_ending: str = "\n",
) -> str:
    cmd = command.strip()
    if not cmd:
        raise ProtocolError("Command cannot be empty.")
    if "\n" in cmd or "\r" in cmd:
        raise ProtocolError("Command must be a single line (no embedded newlines).")
    if line_ending not in {"", "\n", "\r", "\r\n"}:
        raise ProtocolError("line_ending must be one of: '', \\n, \\r, \\r\\n")
    if acs_port is not None:
        if acs_port < 1:
            raise ProtocolError("--port must be >= 1.")
        # Reserved format for multi-channel devices. Protocol may vary by device.
        cmd = f"{cmd} {acs_port}"
    return f"{cmd}{line_ending}"


@dataclass(frozen=True)
class SerialConfig:
    port: str
    read_timeout_s: float = 0.2
    write_timeout_s: float = 1.0
    baudrate: int = 115200
    line_ending: str = "\n"
    encoding: str = "utf-8"
    dtr: Optional[bool] = None
    rts: Optional[bool] = None
    open_delay_s: float = 0.0


class SerialManager:
    """
    Robust line-oriented serial manager.

    - Writes are always full-line (single write call, terminated with '\\n').
    - Reads use line-based decoding and support multi-line responses.
    - Optional background reader thread for interactive mode.
    """

    def __init__(self, config: SerialConfig):
        self._config = SerialConfig(
            port=_normalize_port_name(config.port),
            read_timeout_s=config.read_timeout_s,
            write_timeout_s=config.write_timeout_s,
            baudrate=int(config.baudrate),
            line_ending=config.line_ending,
            encoding=config.encoding,
            dtr=config.dtr,
            rts=config.rts,
            open_delay_s=float(config.open_delay_s or 0.0),
        )
        self._ser: Optional[serial.Serial] = None
        self._io_lock = threading.RLock()

        self._rx_queue: "queue.Queue[str]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_stop = threading.Event()
        self._reader_error: Optional[BaseException] = None
        self._on_disconnect: Optional[Callable[[BaseException], None]] = None

    @property
    def port(self) -> str:
        return self._config.port

    @property
    def baudrate(self) -> int:
        return self._config.baudrate

    @property
    def line_ending(self) -> str:
        return self._config.line_ending

    def is_open(self) -> bool:
        s = self._ser
        return bool(s and s.is_open)

    def open(self) -> None:
        with self._io_lock:
            if self.is_open():
                return
            try:
                ser = serial.Serial()  # configure before open (DTR/RTS can reset some devices)
                ser.port = self._config.port
                ser.baudrate = self._config.baudrate
                ser.timeout = self._config.read_timeout_s
                ser.write_timeout = self._config.write_timeout_s
                if self._config.dtr is not None:
                    try:
                        ser.dtr = bool(self._config.dtr)
                    except Exception:
                        pass
                if self._config.rts is not None:
                    try:
                        ser.rts = bool(self._config.rts)
                    except Exception:
                        pass
                ser.open()
                if self._config.dtr is not None:
                    try:
                        ser.dtr = bool(self._config.dtr)
                    except Exception:
                        pass
                if self._config.rts is not None:
                    try:
                        ser.rts = bool(self._config.rts)
                    except Exception:
                        pass
                self._ser = ser
            except (serial.SerialException, OSError) as exc:
                raise ConnectionError(f"Failed to open {self._config.port}: {exc}") from exc

            if self._config.open_delay_s > 0:
                time.sleep(self._config.open_delay_s)

    def close(self) -> None:
        self.stop_reader()
        with self._io_lock:
            if self._ser is None:
                return
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def reopen(self, *, delay_s: float = 0.25) -> None:
        self.close()
        if delay_s > 0:
            time.sleep(delay_s)
        self.open()

    def __enter__(self) -> "SerialManager":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    def start_reader(
        self,
        *,
        on_disconnect: Optional[Callable[[BaseException], None]] = None,
    ) -> "queue.Queue[str]":
        """
        Start a background reader thread that pushes received lines to a queue.
        """
        if self._reader_thread and self._reader_thread.is_alive():
            return self._rx_queue

        self._on_disconnect = on_disconnect
        self._reader_error = None
        self._reader_stop.clear()

        def run() -> None:
            while not self._reader_stop.is_set():
                try:
                    line = self._readline_once()
                except BaseException as exc:  # includes SerialException/OSError
                    self._reader_error = exc
                    if self._on_disconnect:
                        try:
                            self._on_disconnect(exc)
                        except Exception:
                            pass
                    return

                if line is None:
                    continue
                if line == "":
                    continue
                self._rx_queue.put(line)

        self._reader_thread = threading.Thread(
            target=run, name="camcommand-serial-reader", daemon=True
        )
        self._reader_thread.start()
        return self._rx_queue

    def stop_reader(self) -> None:
        t = self._reader_thread
        if not t:
            return
        self._reader_stop.set()
        t.join(timeout=1.0)
        self._reader_thread = None

    def get_reader_error(self) -> Optional[BaseException]:
        return self._reader_error

    def send_line(
        self,
        command: str,
        *,
        acs_port: Optional[int] = None,
        clear_input: bool = True,
    ) -> None:
        """
        Send exactly one full-line command (single write call, with configured line ending).
        """
        line = _build_command_line(command, acs_port=acs_port, line_ending=self._config.line_ending)
        data = line.encode(self._config.encoding)

        with self._io_lock:
            if not self.is_open():
                raise ConnectionError("Serial port is not open.")
            assert self._ser is not None
            try:
                if clear_input:
                    self._ser.reset_input_buffer()
                written = self._ser.write(data)
                self._ser.flush()
            except (serial.SerialException, OSError) as exc:
                raise ConnectionError(f"Failed to write to {self._config.port}: {exc}") from exc

        if written != len(data):
            raise ConnectionError(
                f"Partial write to {self._config.port}: {written}/{len(data)} bytes."
            )

    def send_and_read_response(
        self,
        command: str,
        *,
        acs_port: Optional[int] = None,
        total_timeout_s: float = 2.0,
        idle_timeout_s: float = 0.35,
        clear_input: bool = True,
    ) -> List[str]:
        """
        Send a command, then collect response lines.

        Collection stops when:
        - A blank line is received (common end-of-response marker), OR
        - No new line arrives for `idle_timeout_s` after at least one line, OR
        - `total_timeout_s` elapses.
        """
        self.send_line(command, acs_port=acs_port, clear_input=clear_input)
        return self.read_response_lines(
            total_timeout_s=total_timeout_s, idle_timeout_s=idle_timeout_s
        )

    def read_response_lines(
        self,
        *,
        total_timeout_s: float = 2.0,
        idle_timeout_s: float = 0.35,
    ) -> List[str]:
        if total_timeout_s <= 0:
            raise ValueError("total_timeout_s must be > 0")
        if idle_timeout_s <= 0:
            raise ValueError("idle_timeout_s must be > 0")

        deadline = time.monotonic() + total_timeout_s
        last_line_at: Optional[float] = None
        lines: List[str] = []

        while time.monotonic() < deadline:
            line = self._readline_once()
            if line is None:
                continue

            # Blank line terminator (common in PICO Hub tooling).
            if line == "":
                if lines:
                    break
                continue

            lines.append(line)
            now = time.monotonic()
            last_line_at = now

            # If we got at least one line and then go idle, stop.
            while time.monotonic() < deadline:
                if last_line_at is not None and (time.monotonic() - last_line_at) >= idle_timeout_s:
                    return lines
                nxt = self._readline_once()
                if nxt is None:
                    continue
                if nxt == "":
                    return lines
                lines.append(nxt)
                last_line_at = time.monotonic()

        return lines

    def _readline_once(self) -> Optional[str]:
        with self._io_lock:
            if not self.is_open():
                raise ConnectionError("Serial port is not open.")
            assert self._ser is not None
            try:
                raw = self._ser.readline()
            except (serial.SerialException, OSError) as exc:
                raise ConnectionError(f"Failed to read from {self._config.port}: {exc}") from exc

        if raw is None or raw == b"":
            return None  # timeout

        # Normalize CRLF/LF and decode.
        raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        text = raw.decode(self._config.encoding, errors="replace")
        text = text.rstrip("\n")
        return text

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

from .serial_manager import SerialManager


def run_interactive(
    manager: SerialManager,
    *,
    acs_port: Optional[int] = None,
) -> int:
    """
    Interactive REPL:
    - Reads user input line-by-line (only sends after ENTER).
    - Displays device responses in (near) real-time from a background reader.
    """
    stop = threading.Event()

    def on_disconnect(exc: BaseException) -> None:
        if stop.is_set():
            return
        print(f"\n[disconnected] {exc}")
        print("[reconnecting] attempting to reopen the port...")
        while not stop.is_set():
            try:
                manager.reopen(delay_s=0.5)
                manager.start_reader(on_disconnect=on_disconnect)
                print("[reconnected]")
                return
            except Exception as e:
                print(f"[reconnect failed] {e}")
                time.sleep(1.0)

    rx = manager.start_reader(on_disconnect=on_disconnect)

    def printer() -> None:
        while not stop.is_set():
            try:
                line = rx.get(timeout=0.2)
            except queue.Empty:
                continue
            print(line)

    t = threading.Thread(target=printer, name="camcommand-interactive-printer", daemon=True)
    t.start()

    print("Interactive mode. Type commands and press ENTER. Ctrl+C or 'exit' to quit.")
    try:
        while True:
            try:
                user = input("camcommand> ")
            except EOFError:
                break
            cmd = user.strip()
            if not cmd:
                continue
            if cmd.lower() in {"exit", "quit"}:
                break
            manager.send_line(cmd, acs_port=acs_port, clear_input=False)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        manager.stop_reader()

    return 0

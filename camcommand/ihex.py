from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


class IHexError(ValueError):
    pass


@dataclass(frozen=True)
class IHexImage:
    start_address: int
    data: List[int]


def _from_hex_byte(s: str) -> int:
    try:
        return int(s, 16)
    except Exception as exc:
        raise IHexError(f"Invalid hex byte: {s!r}") from exc


def load_ihex(filename: str) -> IHexImage:
    """
    Minimal Intel HEX loader.

    Supports record types:
    - 00: data
    - 01: EOF
    - 04: extended linear address
    Ignores:
    - 02, 03, 05 (not expected for these images)
    """
    memory: Dict[int, int] = {}
    ext_linear = 0
    saw_eof = False

    with open(filename, "r", encoding="utf-8", errors="replace") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise IHexError(f"{filename}:{lineno}: Line does not start with ':'")

            # :LLAAAATT[DD...]CC
            if len(line) < 11:
                raise IHexError(f"{filename}:{lineno}: Line too short")

            ll = _from_hex_byte(line[1:3])
            addr = int(line[3:7], 16)
            rectype = _from_hex_byte(line[7:9])
            data_hex = line[9 : 9 + ll * 2]
            checksum = _from_hex_byte(line[9 + ll * 2 : 9 + ll * 2 + 2])

            # Basic checksum validation (2's complement of sum of bytes)
            bytes_for_sum: List[int] = [ll, (addr >> 8) & 0xFF, addr & 0xFF, rectype]
            bytes_for_sum.extend(_from_hex_byte(data_hex[i : i + 2]) for i in range(0, len(data_hex), 2))
            calc = ((-sum(bytes_for_sum)) & 0xFF)
            if calc != checksum:
                raise IHexError(f"{filename}:{lineno}: Bad checksum (got 0x{checksum:02X}, expected 0x{calc:02X})")

            if rectype == 0x00:
                base = (ext_linear << 16) + addr
                for i in range(ll):
                    b = _from_hex_byte(data_hex[i * 2 : i * 2 + 2])
                    memory[base + i] = b
            elif rectype == 0x01:
                saw_eof = True
                break
            elif rectype == 0x04:
                if ll != 2:
                    raise IHexError(f"{filename}:{lineno}: Bad ELA record length: {ll}")
                ext_linear = int(data_hex, 16)
            else:
                # Ignore other records (start segment/linear, extended segment)
                continue

    if not memory:
        return IHexImage(start_address=0, data=[])
    if not saw_eof:
        # Not fatal in practice, but helps catch truncated files.
        raise IHexError(f"{filename}: Missing EOF record")

    min_addr = min(memory.keys())
    max_addr = max(memory.keys())
    data = [0xFF] * (max_addr - min_addr + 1)
    for a, b in memory.items():
        data[a - min_addr] = b
    return IHexImage(start_address=min_addr, data=data)


def _to_record(ll: int, addr: int, rectype: int, data: Iterable[int]) -> str:
    data_list = [int(b) & 0xFF for b in data]
    if ll != len(data_list):
        raise IHexError(f"Bad record length: ll={ll} data={len(data_list)}")
    if addr < 0 or addr > 0xFFFF:
        raise IHexError(f"Bad record address: 0x{addr:X}")
    if rectype < 0 or rectype > 0xFF:
        raise IHexError(f"Bad record type: 0x{rectype:X}")

    bytes_for_sum: List[int] = [ll, (addr >> 8) & 0xFF, addr & 0xFF, rectype]
    bytes_for_sum.extend(data_list)
    checksum = ((-sum(bytes_for_sum)) & 0xFF)

    data_hex = "".join(f"{b:02X}" for b in data_list)
    return f":{ll:02X}{addr:04X}{rectype:02X}{data_hex}{checksum:02X}"


def save_ihex(
    filename: str,
    *,
    start_address: int,
    data: Iterable[int],
    line_length: int = 16,
    trim_trailing_ff: bool = False,
) -> None:
    """
    Minimal Intel HEX writer.

    Writes record types:
    - 00: data
    - 01: EOF
    - 04: extended linear address
    """
    if line_length < 1 or line_length > 255:
        raise IHexError("line_length must be 1-255")

    start = int(start_address)
    if start < 0:
        raise IHexError("start_address must be >= 0")

    buf = [int(b) & 0xFF for b in data]
    if trim_trailing_ff:
        last_non_ff = -1
        for i in range(len(buf) - 1, -1, -1):
            if buf[i] != 0xFF:
                last_non_ff = i
                break
        buf = buf[: last_non_ff + 1] if last_non_ff >= 0 else []

    current_ela: Optional[int] = None
    out_lines: List[str] = []

    for offset in range(0, len(buf), line_length):
        abs_addr = start + offset
        ela = (abs_addr >> 16) & 0xFFFF
        if current_ela != ela:
            out_lines.append(_to_record(2, 0x0000, 0x04, [(ela >> 8) & 0xFF, ela & 0xFF]))
            current_ela = ela

        chunk = buf[offset : offset + line_length]
        out_lines.append(_to_record(len(chunk), abs_addr & 0xFFFF, 0x00, chunk))

    out_lines.append(_to_record(0, 0x0000, 0x01, []))
    text = "\n".join(out_lines) + "\n"
    with open(filename, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

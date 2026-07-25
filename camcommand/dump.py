from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .exceptions import CamcommandError
from .ihex import save_ihex

from ._pyupdi.device.device import Device
from ._pyupdi.updi.nvm import UpdiNvmProgrammer


class DumpError(CamcommandError):
    """Raised when reading flash (dump) fails."""


SUPPORTED_CHIP = "attiny1616"


@dataclass(frozen=True)
class DumpOptions:
    com: str
    out_file: str
    baud: int = 115200
    trim_trailing_ff: bool = False


def _clean_com_port(port: str) -> str:
    # Reference GUI sometimes shows: "COMx - CAMLOCK Device"
    return (port or "").split(" - ", 1)[0].strip()


def _close_updi(nvm: UpdiNvmProgrammer) -> None:
    try:
        nvm.application.datalink.updi_phy.close()  # type: ignore[attr-defined]
    except Exception:
        try:
            ser = nvm.application.datalink.updi_phy.ser  # type: ignore[attr-defined]
            if ser:
                ser.close()
        except Exception:
            pass


def dump_hex(opts: DumpOptions, *, dry_run: bool = False) -> None:
    com = _clean_com_port(opts.com)
    if not com:
        raise DumpError("--com is required (e.g. COM6).")

    out_path = os.path.abspath(opts.out_file)
    out_dir = os.path.dirname(out_path) or "."
    if not os.path.isdir(out_dir):
        raise DumpError(f"Output directory does not exist: {out_dir}")

    if dry_run:
        print(
            "UPDI dump (dry-run): "
            f"chip={SUPPORTED_CHIP} com={com} baud={int(opts.baud)} "
            f"trim={bool(opts.trim_trailing_ff)} out={out_path}"
        )
        return

    nvm: Optional[UpdiNvmProgrammer] = None
    try:
        nvm = UpdiNvmProgrammer(comport=com, baud=int(opts.baud), device=Device(SUPPORTED_CHIP))
        nvm.get_device_info()
        nvm.enter_progmode()

        start = int(nvm.device.flash_start)
        size = int(nvm.device.flash_size)
        data = [int(b) & 0xFF for b in nvm.read_flash(start, size)]

        save_ihex(
            out_path,
            start_address=start,
            data=data,
            trim_trailing_ff=bool(opts.trim_trailing_ff),
        )
        nvm.leave_progmode()

        wrote = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        print(
            "UPDI dump: OK "
            f"(chip={SUPPORTED_CHIP} com={com} baud={int(opts.baud)} "
            f"flash=0x{start:X}+{size}B out={out_path} bytes={wrote})"
        )
    except DumpError:
        raise
    except Exception as exc:
        raise DumpError(str(exc)) from exc
    finally:
        if nvm is not None:
            _close_updi(nvm)

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .exceptions import CamcommandError

from ._pyupdi.device.device import Device
from ._pyupdi.updi.nvm import UpdiNvmProgrammer


class ReflashError(CamcommandError):
    """Raised when reflashing fails."""


SUPPORTED_CHIP = "attiny1616"


@dataclass(frozen=True)
class ReflashOptions:
    com: str
    hex_file: str
    baud: int = 115200
    erase: bool = True
    verify: bool = True
    unlock_if_locked: bool = True


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


def reflash_hex(opts: ReflashOptions, *, dry_run: bool = False) -> None:
    com = _clean_com_port(opts.com)
    if not com:
        raise ReflashError("--com is required (e.g. COM6).")

    hex_path = os.path.abspath(opts.hex_file)
    if not os.path.exists(hex_path):
        raise ReflashError(f"Hex file not found: {hex_path}")

    if dry_run:
        print(
            "UPDI reflash (dry-run): "
            f"chip={SUPPORTED_CHIP} com={com} baud={int(opts.baud)} "
            f"erase={bool(opts.erase)} verify={bool(opts.verify)} unlock={bool(opts.unlock_if_locked)} "
            f"hex={hex_path}"
        )
        return

    nvm: Optional[UpdiNvmProgrammer] = None
    try:
        nvm = UpdiNvmProgrammer(comport=com, baud=int(opts.baud), device=Device(SUPPORTED_CHIP))

        # Retrieve info and enter programming mode; unlock if required.
        try:
            nvm.get_device_info()
            nvm.enter_progmode()
        except Exception:
            if not opts.unlock_if_locked:
                raise
            nvm.unlock_device()

        data, start_address = nvm.load_ihex_flash(hex_path)
        if opts.erase:
            nvm.chip_erase()
        nvm.write_flash(start_address, data)

        if opts.verify:
            readback = nvm.read_flash(start_address, len(data))
            for i, byte in enumerate(data):
                if int(byte) != int(readback[i]):
                    raise ReflashError(
                        "Verify error at location "
                        f"0x{i:04X}: expected 0x{int(byte):02X}, read 0x{int(readback[i]):02X}"
                    )

        nvm.leave_progmode()
        print(
            "UPDI reflash: OK "
            f"(chip={SUPPORTED_CHIP} com={com} baud={int(opts.baud)} "
            f"erase={bool(opts.erase)} verify={'pass' if opts.verify else 'skip'} "
            f"hex={hex_path} wrote={len(data)}B @ 0x{int(start_address):X})"
        )
    except ReflashError:
        raise
    except Exception as exc:
        raise ReflashError(str(exc)) from exc
    finally:
        if nvm is not None:
            _close_updi(nvm)

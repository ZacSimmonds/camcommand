from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DeviceInfo:
    device: str  # e.g. "COM3"
    description: str = ""
    hwid: str = ""
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    vid: Optional[int] = None
    pid: Optional[int] = None
    is_ch340_like: bool = False

    @property
    def vid_pid(self) -> str:
        if self.vid is None or self.pid is None:
            return ""
        return f"{self.vid:04X}:{self.pid:04X}"

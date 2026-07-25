from __future__ import annotations

from typing import List, Optional

from .device import DeviceInfo
from .exceptions import DiscoveryError

try:
    from serial.tools import list_ports
except Exception as exc:  # pragma: no cover
    list_ports = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


_CH340_VIDS = {0x1A86}
_CH340_PIDS = {
    0x7523,  # CH340/CH341
    0x5523,  # CH341 variant
}


def _is_ch340_like(
    *,
    description: str,
    hwid: str,
    manufacturer: str,
    vid: Optional[int],
    pid: Optional[int],
) -> bool:
    text = f"{description} {hwid} {manufacturer}".upper()
    if "CH340" in text or "CH341" in text:
        return True
    if vid is not None and vid in _CH340_VIDS:
        return True
    if vid is not None and pid is not None and vid in _CH340_VIDS and pid in _CH340_PIDS:
        return True
    if "VID:PID=1A86" in text:
        return True
    return False


def find_devices() -> List[DeviceInfo]:
    if list_ports is None:  # pragma: no cover
        raise DiscoveryError(
            f"pyserial is required for discovery but could not be imported: {_IMPORT_ERROR}"
        )

    devices: List[DeviceInfo] = []
    try:
        ports = list(list_ports.comports())
    except Exception as exc:
        raise DiscoveryError(f"Failed to enumerate serial ports: {exc}") from exc

    for p in ports:
        vid = getattr(p, "vid", None)
        pid = getattr(p, "pid", None)
        manufacturer = getattr(p, "manufacturer", "") or ""
        product = getattr(p, "product", "") or ""
        serial_number = getattr(p, "serial_number", "") or ""
        description = getattr(p, "description", "") or ""
        hwid = getattr(p, "hwid", "") or ""

        devices.append(
            DeviceInfo(
                device=getattr(p, "device", "") or "",
                description=description,
                hwid=hwid,
                manufacturer=manufacturer,
                product=product,
                serial_number=serial_number,
                vid=vid,
                pid=pid,
                is_ch340_like=_is_ch340_like(
                    description=description,
                    hwid=hwid,
                    manufacturer=manufacturer,
                    vid=vid,
                    pid=pid,
                ),
            )
        )

    return devices


def pick_default_device(devices: List[DeviceInfo]) -> Optional[DeviceInfo]:
    """
    Choose a sensible default:
    - Prefer CH340-like ports.
    - Otherwise, if only one port exists, return it.
    """
    ch340 = [d for d in devices if d.is_ch340_like]
    if len(ch340) == 1:
        return ch340[0]
    if len(ch340) > 1:
        def key(d: DeviceInfo) -> tuple:
            name = d.device.upper()
            if name.startswith("COM"):
                try:
                    return (0, int(name[3:]))
                except ValueError:
                    return (1, name)
            return (2, name)

        return sorted(ch340, key=key)[0]

    if len(devices) == 1:
        return devices[0]

    return None

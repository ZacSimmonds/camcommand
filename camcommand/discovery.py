from __future__ import annotations

import sys
from typing import List, Optional

from .device import DeviceInfo
from .exceptions import DiscoveryError


def find_devices() -> List[DeviceInfo]:
    """
    Platform dispatcher.

    Kept as a thin dispatcher so platform-specific logic doesn't leak into the
    rest of the package.
    """
    if sys.platform == "win32":
        from .discovery_windows import find_devices as impl
        return impl()

    if sys.platform.startswith("linux"):
        from .discovery_linux import find_devices as impl
        return impl()

    raise DiscoveryError(
        f"Device discovery is not implemented for platform '{sys.platform}'. "
        "Pass --com to specify the serial device path."
    )


def pick_default_device(devices: List[DeviceInfo]) -> Optional[DeviceInfo]:
    if sys.platform == "win32":
        from .discovery_windows import pick_default_device as impl
        return impl(devices)

    if sys.platform.startswith("linux"):
        from .discovery_linux import pick_default_device as impl
        return impl(devices)

    return None

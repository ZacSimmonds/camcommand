from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Optional

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from camcommand import SerialManager, find_devices  # noqa: E402
from camcommand.discovery_windows import pick_default_device  # noqa: E402
from camcommand.serial_manager import SerialConfig  # noqa: E402


def _resolve_com(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    devices = find_devices()
    if not devices:
        raise SystemExit("No serial devices found. Pass --com COMx.")
    chosen = pick_default_device(devices)
    if not chosen:
        raise SystemExit("Multiple devices found. Pass --com COMx.")
    return chosen.device


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Example camcommand app: send a few commands and print responses."
    )
    ap.add_argument("--com", help="Serial port (e.g. COM15). If omitted, auto-picks CH340.")
    args = ap.parse_args()

    com = _resolve_com(args.com)
    cfg = SerialConfig(port=com)

    print(f"Connecting to {com} (115200)...")
    with SerialManager(cfg) as mgr:
        while True:
            for cmd in ["STATE", "TEMP"]:
                print(f"\n> {cmd}")
                for line in mgr.send_and_read_response(cmd):
                    print(line)

            print("\n> UNLOCK")
            for line in mgr.send_and_read_response("UNLOCK"):
                print(line)

            print("\n> STATE")
            for line in mgr.send_and_read_response("STATE"):
                print(line)

            try:
                again = input("\nPress ENTER to run again, or type 'q' to quit: ").strip().lower()
            except EOFError:
                break
            if again in {"q", "quit", "exit"}:
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

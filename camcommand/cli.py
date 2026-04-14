from __future__ import annotations

import argparse
import os
import re
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import List, Optional

from .discovery import find_devices, pick_default_device
from .dump import DumpError, DumpOptions, dump_hex
from .exceptions import CamcommandError, ConnectionError, DiscoveryError, ProtocolError
from .interactive import run_interactive
from .reflash import ReflashError, ReflashOptions, reflash_hex
from .serial_manager import SerialConfig, SerialManager


def _print_devices(devices) -> None:
    if not devices:
        print("No serial ports found.")
        return

    print("PORT   CH340  VID:PID   DESCRIPTION")
    for d in devices:
        vp = d.vid_pid or "-"
        ch = "yes" if d.is_ch340_like else "no"
        desc = d.description or d.product or "-"
        print(f"{d.device:<6} {ch:<5} {vp:<8} {desc}")


def _resolve_com_port(explicit: Optional[str]) -> str:
    if explicit:
        return explicit

    devices = find_devices()
    if not devices:
        raise DiscoveryError("No serial ports found.")

    chosen = pick_default_device(devices)
    if chosen is None:
        print("Multiple candidate devices found; specify one with --com.")
        _print_devices(devices)
        raise DiscoveryError("No default device could be selected.")

    return chosen.device


def _build_manager(args) -> SerialManager:
    port = _resolve_com_port(args.com)
    cfg = SerialConfig(
        port=port,
        read_timeout_s=args.read_timeout,
        write_timeout_s=args.write_timeout,
    )
    return SerialManager(cfg)


def _build_acs200_manager(args) -> SerialManager:
    port = _resolve_com_port(args.com)

    line_ending = "\r"
    if getattr(args, "line_ending", None):
        le = str(args.line_ending).lower()
        if le == "cr":
            line_ending = "\r"
        elif le == "lf":
            line_ending = "\n"
        elif le == "crlf":
            line_ending = "\r\n"
        elif le == "none":
            line_ending = ""

    cfg = SerialConfig(
        port=port,
        baudrate=int(getattr(args, "baud", 9600) or 9600),
        line_ending=line_ending,
        read_timeout_s=args.read_timeout,
        write_timeout_s=args.write_timeout,
    )
    return SerialManager(cfg)


def cmd_list(_args) -> int:
    devices = find_devices()
    _print_devices(devices)
    return 0


def cmd_help(args) -> int:
    parser = build_parser(_program_name())
    if not args.topic:
        parser.print_help()
        return 0

    topic = args.topic[0]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            sub = action.choices.get(topic)
            if sub is None:
                print(f"Unknown help topic: {topic}", file=sys.stderr)
                return 2
            print(sub.format_help())
            return 0

    parser.print_help()
    return 0


def cmd_connect(args) -> int:
    manager = _build_manager(args)
    with manager:
        print(f"Connected to {manager.port} @ {manager.baudrate} baud.")
    return 0


def _normalize_command(command: str, *, raw: bool) -> str:
    cmd = command.strip()
    if not raw:
        cmd = cmd.upper()
    return cmd


def cmd_send(args) -> int:
    manager = _build_manager(args)
    command = _normalize_command(" ".join(args.command), raw=args.raw)
    with manager:
        lines = manager.send_and_read_response(
            command,
            acs_port=args.port,
            total_timeout_s=args.total_timeout,
            idle_timeout_s=args.idle_timeout,
            clear_input=True,
        )

    if not lines:
        print("(no response)")
        return 0

    for line in lines:
        print(line)
    return 0


def cmd_temp(args) -> int:
    args.command = ["TEMP"]
    return cmd_send(args)


def cmd_interactive(args) -> int:
    manager = _build_manager(args)
    with manager:
        return run_interactive(manager, acs_port=args.port)


def cmd_acs200_send(args) -> int:
    manager = _build_acs200_manager(args)
    command = " ".join(args.command).strip()
    with manager:
        lines = manager.send_and_read_response(
            command,
            total_timeout_s=args.total_timeout,
            idle_timeout_s=args.idle_timeout,
            clear_input=True,
        )

    if not lines:
        print("(no response)")
        return 0
    for line in lines:
        print(line)
    return 0


def _acs200_cmd(parts: list[str]) -> str:
    return ",".join(str(p).strip() for p in parts if str(p).strip() != "")


def _acs200_onoff(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"on", "1", "true", "yes"}:
        return "1"
    if v in {"off", "0", "false", "no"}:
        return "0"
    raise ProtocolError("Expected on/off (or 1/0).")


def _acs200_send_simple(args, command: str) -> int:
    manager = _build_acs200_manager(args)
    with manager:
        lines = manager.send_and_read_response(
            command,
            total_timeout_s=args.total_timeout,
            idle_timeout_s=args.idle_timeout,
            clear_input=True,
        )
    for line in lines:
        print(line)
    if not lines:
        print("(no response)")
    return 0


def cmd_acs200_unlock(args) -> int:
    target = str(args.target).strip().lower()
    if target == "all":
        cmd = "unlock,all"
    else:
        n = int(target)
        if n < 1 or n > 10:
            raise ProtocolError("ACS-200 port must be 1-10 (or 'all').")
        cmd = _acs200_cmd(["unlock", n])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_hold(args) -> int:
    cmd = _acs200_cmd(["hold", _acs200_onoff(args.value)])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_interlock(args) -> int:
    cmd = _acs200_cmd(["interlock", _acs200_onoff(args.value)])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_get_state(args) -> int:
    # GUI uses get_state; quickstart also mentions state.
    cmd = "get_state" if args.variant == "get_state" else "state"
    return _acs200_send_simple(args, cmd)


def cmd_acs200_get_locks(args) -> int:
    return _acs200_send_simple(args, "get_locks")


def cmd_acs200_get_info(args) -> int:
    return _acs200_send_simple(args, "get_info")


def cmd_acs200_reset(args) -> int:
    return _acs200_send_simple(args, "reset")


def cmd_acs200_relock_get(args) -> int:
    return _acs200_send_simple(args, "get_relock_duration")


def cmd_acs200_relock_set(args) -> int:
    seconds = int(args.seconds)
    cmd = _acs200_cmd(["set_relock_duration", seconds])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_output(args) -> int:
    n = int(args.number)
    if n < 1 or n > 10:
        raise ProtocolError("Output number must be 1-10.")
    level = str(args.level).strip().lower()
    if level in {"high", "on", "1"}:
        cmd = _acs200_cmd(["set_output_high", n])
    elif level in {"low", "off", "0"}:
        cmd = _acs200_cmd(["set_output_low", n])
    else:
        raise ProtocolError("Output level must be high/low (or on/off).")
    return _acs200_send_simple(args, cmd)


def cmd_acs200_outputs_all(args) -> int:
    level = str(args.level).strip().lower()
    if level in {"high", "on", "1"}:
        verb = "set_output_high"
    elif level in {"low", "off", "0"}:
        verb = "set_output_low"
    else:
        raise ProtocolError("Output level must be on/off.")

    manager = _build_acs200_manager(args)
    with manager:
        for n in range(10, 0, -1):
            manager.send_line(_acs200_cmd([verb, n]), clear_input=False)
    print("OK")
    return 0


def cmd_acs200_input_analog(args) -> int:
    n = int(args.number)
    if n < 1 or n > 10:
        raise ProtocolError("Input number must be 1-10.")
    cmd = _acs200_cmd(["get_input_analog", n])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_open_alarm(args) -> int:
    cmd = _acs200_cmd(["open_alarm", _acs200_onoff(args.value)])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_intrusion_alarm(args) -> int:
    cmd = _acs200_cmd(["intrusion_alarm", _acs200_onoff(args.value)])
    return _acs200_send_simple(args, cmd)


def cmd_acs200_interactive(args) -> int:
    manager = _build_acs200_manager(args)
    with manager:
        return run_interactive(manager)


def cmd_reflash(args) -> int:
    port = _resolve_com_port(args.com)
    opts = ReflashOptions(
        com=port,
        hex_file=args.hexfile,
        baud=args.baud,
        erase=not args.no_erase,
        verify=not args.no_verify,
        unlock_if_locked=not args.no_unlock,
    )
    reflash_hex(opts, dry_run=args.dry_run)
    return 0


def cmd_dump(args) -> int:
    port = _resolve_com_port(args.com)
    opts = DumpOptions(
        com=port,
        out_file=args.outfile,
        baud=args.baud,
        trim_trailing_ff=bool(args.trim),
    )
    dump_hex(opts, dry_run=args.dry_run)
    return 0


def _program_name() -> str:
    base = os.path.basename(sys.argv[0] or "camcommand")
    name, _ext = os.path.splitext(base)
    return name or "camcommand"


def _package_version() -> str:
    try:
        return str(pkg_version("camcommand"))
    except PackageNotFoundError:
        return "0.0.0+unknown"


def build_parser(prog: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description="Camcommand USB-serial CLI (fixed 115200 baud).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} list\n"
            f"  {prog} --com COM15 connect\n"
            f"  {prog} --com COM15 send STATE\n"
            f"  {prog} --com COM15 send HOLD ON\n"
            f"  {prog} --com COM15 temp\n"
            f"  {prog} --com COM15 interactive\n"
            f"  {prog} --com COM15 acs200 --help\n"
            "\n"
            "Shortcuts:\n"
            f"  {prog} COM15 TEMP        (same as: --com COM15 send TEMP)\n"
            f"  {prog} COM15 HOLD ON     (same as: --com COM15 send HOLD ON)\n"
            "\n"
            "Notes:\n"
            "  - Commands are sent as complete lines terminated with \\n.\n"
            "  - Interactive mode sends only after ENTER (never per-character).\n"
            "  - For ACS-200 controller commands, use: acs200 --help\n"
        ),
    )
    p.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {_package_version()}",
        help="Show version and exit.",
    )
    p.add_argument(
        "--com",
        help="Serial port (e.g. COM3). If omitted, auto-selects a likely CH340 port.",
    )
    p.add_argument(
        "--read-timeout",
        type=float,
        default=0.2,
        help="Per-read timeout in seconds (default: 0.2).",
    )
    p.add_argument(
        "--write-timeout",
        type=float,
        default=1.0,
        help="Write timeout in seconds (default: 1.0).",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("help", help="Show help for a command.")
    sp.add_argument("topic", nargs="*", help="Command to show help for (e.g. send).")
    sp.set_defaults(func=cmd_help)

    sp = sub.add_parser("list", help="List available serial ports.")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("connect", help="Open and close a serial connection (smoke test).")
    sp.set_defaults(func=cmd_connect)

    sp = sub.add_parser("send", help="Send a command and print the response.")
    sp.add_argument(
        "command",
        nargs="+",
        help="Command to send (e.g. STATE, UNLOCK, TEMP, HOLD ON).",
    )
    sp.add_argument(
        "--raw",
        action="store_true",
        help="Send exactly as provided (do not auto-uppercase).",
    )
    sp.add_argument(
        "--port",
        type=int,
        help="Reserved for multi-channel devices (e.g. ACS200).",
    )
    sp.add_argument(
        "--total-timeout",
        type=float,
        default=2.0,
        help="Max time to wait for the full response (default: 2.0).",
    )
    sp.add_argument(
        "--idle-timeout",
        type=float,
        default=0.35,
        help="Stop after this much response silence (default: 0.35).",
    )
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("temp", help="Shortcut for: send TEMP.")
    sp.add_argument(
        "--raw",
        action="store_true",
        help="Send exactly as provided (do not auto-uppercase).",
    )
    sp.add_argument(
        "--port",
        type=int,
        help="Reserved for multi-channel devices (e.g. ACS200).",
    )
    sp.add_argument(
        "--total-timeout",
        type=float,
        default=2.0,
        help="Max time to wait for the full response (default: 2.0).",
    )
    sp.add_argument(
        "--idle-timeout",
        type=float,
        default=0.35,
        help="Stop after this much response silence (default: 0.35).",
    )
    sp.set_defaults(func=cmd_temp)

    sp = sub.add_parser("interactive", help="Interactive mode (line-based; sends only after ENTER).")
    sp.add_argument(
        "--port",
        type=int,
        help="Reserved for multi-channel devices (e.g. ACS200).",
    )
    sp.set_defaults(func=cmd_interactive)

    sp = sub.add_parser(
        "acs200",
        help="ACS-200 / CAMCOMMAND multi-channel controller commands (serial: 9600 8N1, CR).",
    )
    sp.add_argument(
        "--baud",
        type=int,
        default=9600,
        help="ACS-200 serial baud rate (default: 9600).",
    )
    sp.add_argument(
        "--line-ending",
        choices=["cr", "lf", "crlf", "none"],
        default="cr",
        help="Line terminator to append to ACS-200 commands (default: cr).",
    )
    acs = sp.add_subparsers(dest="acs_cmd", required=True)

    asp = acs.add_parser("send", help="Send a raw ACS-200 command (e.g. unlock,3).")
    asp.add_argument("command", nargs="+", help="Command to send (e.g. state, unlock,3).")
    asp.add_argument(
        "--total-timeout",
        type=float,
        default=2.0,
        help="Max time to wait for the full response (default: 2.0).",
    )
    asp.add_argument(
        "--idle-timeout",
        type=float,
        default=0.35,
        help="Stop after this much response silence (default: 0.35).",
    )
    asp.set_defaults(func=cmd_acs200_send)

    asp = acs.add_parser("unlock", help="Unlock a lock port (1-10) or 'all'.")
    asp.add_argument("target", help="Port number 1-10, or 'all'.")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_unlock)

    asp = acs.add_parser("hold", help="Set hold-open on/off.")
    asp.add_argument("value", help="on/off (or 1/0).")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_hold)

    asp = acs.add_parser("interlock", help="Set interlock on/off.")
    asp.add_argument("value", help="on/off (or 1/0).")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_interlock)

    asp = acs.add_parser("state", help="Get system status.")
    asp.add_argument(
        "--variant",
        choices=["state", "get_state"],
        default="get_state",
        help="Firmware variant to query (default: get_state).",
    )
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_get_state)

    asp = acs.add_parser("locks", help="Search for connected locks.")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_get_locks)

    asp = acs.add_parser("info", help="Get controller info.")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_get_info)

    asp = acs.add_parser("reset", help="Reset the controller.")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_reset)

    asp = acs.add_parser("relock-get", help="Get relock duration.")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_relock_get)

    asp = acs.add_parser("relock-set", help="Set relock duration (seconds).")
    asp.add_argument("seconds", type=int)
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_relock_set)

    asp = acs.add_parser("output", help="Set output high/low (1-10).")
    asp.add_argument("number", type=int)
    asp.add_argument("level", help="high/low (or on/off).")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_output)

    asp = acs.add_parser("outputs", help="Set all outputs on/off.")
    asp.add_argument("level", help="on/off.")
    asp.set_defaults(func=cmd_acs200_outputs_all)

    asp = acs.add_parser("temp", help="Read an analog input and print raw response.")
    asp.add_argument("number", type=int, help="Input number 1-10.")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_input_analog)

    asp = acs.add_parser("open-alarm", help="Set open alarm relay on/off.")
    asp.add_argument("value", help="on/off (or 1/0).")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_open_alarm)

    asp = acs.add_parser("intrusion-alarm", help="Set intrusion alarm on/off.")
    asp.add_argument("value", help="on/off (or 1/0).")
    asp.add_argument("--total-timeout", type=float, default=2.0)
    asp.add_argument("--idle-timeout", type=float, default=0.35)
    asp.set_defaults(func=cmd_acs200_intrusion_alarm)

    asp = acs.add_parser("interactive", help="Interactive mode for ACS-200 (CR line endings).")
    asp.set_defaults(func=cmd_acs200_interactive)

    sp = sub.add_parser(
        "reflash",
        help="Flash an Intel HEX over UPDI using the Camlock flasher dongle.",
    )
    sp.add_argument(
        "hexfile",
        help="Path to Intel HEX file to write to the device.",
    )
    sp.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="UPDI serial baud rate (default: 115200).",
    )
    sp.add_argument(
        "--no-erase",
        action="store_true",
        help="Do not chip-erase before writing.",
    )
    sp.add_argument(
        "--no-verify",
        action="store_true",
        help="Do not verify after writing.",
    )
    sp.add_argument(
        "--no-unlock",
        action="store_true",
        help="Do not attempt unlock if the device is locked.",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done and exit.",
    )
    sp.set_defaults(func=cmd_reflash)

    sp = sub.add_parser(
        "dump",
        help="Read flash over UPDI and save as an Intel HEX file.",
    )
    sp.add_argument(
        "outfile",
        help="Output path for Intel HEX file.",
    )
    sp.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="UPDI serial baud rate (default: 115200).",
    )
    sp.add_argument(
        "--trim",
        action="store_true",
        help="Trim trailing 0xFF bytes to reduce file size.",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done and exit.",
    )
    sp.set_defaults(func=cmd_dump)

    return p


_SUBCOMMANDS = {"help", "list", "connect", "send", "temp", "interactive", "reflash", "dump", "acs200"}


def _preprocess_argv(argv: List[str]) -> List[str]:
    if not argv:
        return argv

    out = list(argv)

    # Allow: camcommand COM15 <...>
    if re.fullmatch(r"COM\d+", out[0], flags=re.IGNORECASE):
        out = ["--com", out[0], *out[1:]]

    # Allow: camcommand [--com COM15] TEMP|STATE|HOLD ON  (default to send)
    # Find first positional token after known options and their values.
    options_with_values = {"--com", "--read-timeout", "--write-timeout"}
    i = 0
    insert_at: Optional[int] = None
    while i < len(out):
        t = out[i]
        if t in options_with_values:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        insert_at = i
        break

    if insert_at is not None:
        token = out[insert_at]
        is_subcommand = token.lower() in _SUBCOMMANDS and token == token.lower()
        if not is_subcommand:
            out = out[:insert_at] + ["send"] + out[insert_at:]

    # Allow: camcommand help  (common muscle-memory)
    if out and out[0].lower() == "help":
        out = ["help", *out[1:]]

    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser(_program_name())
    args = parser.parse_args(
        _preprocess_argv(list(argv)) if argv is not None else _preprocess_argv(sys.argv[1:])
    )
    try:
        return int(args.func(args))
    except (DiscoveryError, ConnectionError, ProtocolError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ReflashError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except DumpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except CamcommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

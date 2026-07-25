from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


_INT_LINE_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class Acs200ParsedResponse:
    """
    Parsed ACS-200 response.

    Some firmwares return a leading numeric status/event code followed by one or
    more human-readable payload lines (e.g. `State,...`).
    """

    status_code: Optional[int]
    payload_lines: List[str]
    raw_lines: List[str]


# Known status/event codes (best-effort; firmware variants exist).
_STATUS_CODE_MEANINGS: dict[int, str] = {
    0: "ok",
    6: "intrusion alarm",
}


def parse_response_lines(lines: List[str]) -> Acs200ParsedResponse:
    """
    Split a multi-line response into an optional leading status code + payload.

    Important: numeric-only *single-line* responses can be legitimate payload
    (e.g. analog reads), so we only treat the first line as a status code when
    it is followed by at least one non-numeric line.
    """
    if len(lines) >= 2 and _INT_LINE_RE.match(lines[0]) and not _INT_LINE_RE.match(lines[1]):
        return Acs200ParsedResponse(
            status_code=int(lines[0]),
            payload_lines=list(lines[1:]),
            raw_lines=list(lines),
        )
    if len(lines) == 1 and _INT_LINE_RE.match(lines[0]):
        code = int(lines[0])
        if code in _STATUS_CODE_MEANINGS:
            return Acs200ParsedResponse(status_code=code, payload_lines=[], raw_lines=list(lines))
    return Acs200ParsedResponse(status_code=None, payload_lines=list(lines), raw_lines=list(lines))


def status_code_meaning(code: int) -> str:
    return _STATUS_CODE_MEANINGS.get(code, "unknown")

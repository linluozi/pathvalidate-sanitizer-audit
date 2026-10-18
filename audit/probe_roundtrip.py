"""Probe: does sanitize_* always produce output that validate_* accepts?

Contract under test: sanitize_filepath / sanitize_filename are documented to
"make a valid file path/name".  So for any input, the returned value should pass
is_valid_filepath / is_valid_filename with the same platform.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathvalidate import (  # noqa: E402
    is_valid_filename,
    is_valid_filepath,
    sanitize_filename,
    sanitize_filepath,
)

PLATFORMS = ["universal", "windows", "linux", "macos", "posix"]

PAYLOADS = [
    "CON",
    "con.txt",
    "aux",
    "NUL.log",
    "$Mft",
    "$mft",
    "a/$Mft",
    "a/$mft",
    "COM1",
    "LPT9.txt",
    "..",
    ".",
    "../../etc/passwd",
    "a/../../b",
    "/abs/path",
    "C:\\temp\\x",
    "C:\\a\\..\\..\\b",
    "\\\\srv\\share\\f",
    "a b",
    " a",
    "a ",
    "a.",
    "...",
    "a" * 300,
    "\u00e9" * 200,
    "a/b/c",
    "a//b",
    "./a",
    "a/./b",
    "a\\b",
    ":",
    "a:b",
    "x" * 259 + ".",
    " a ",
    "~$x",
    "a\x00b",
    "a\x1bb",
]


def probe_filepath() -> list[tuple[str, str, str, str]]:
    bad = []
    for platform in PLATFORMS:
        for payload in PAYLOADS:
            try:
                out = sanitize_filepath(payload, platform=platform)
            except Exception as e:  # noqa: BLE001
                bad.append((platform, payload, "RAISED", f"{type(e).__name__}: {e}"))
                continue
            try:
                ok = is_valid_filepath(out, platform=platform)
            except Exception as e:  # noqa: BLE001
                bad.append((platform, payload, repr(out), f"CHECK-RAISED {type(e).__name__}"))
                continue
            if not ok:
                bad.append((platform, payload, repr(out), "INVALID OUTPUT"))
    return bad


def probe_filename() -> list[tuple[str, str, str, str]]:
    bad = []
    for platform in PLATFORMS:
        for payload in PAYLOADS:
            try:
                out = sanitize_filename(payload, platform=platform)
            except Exception as e:  # noqa: BLE001
                bad.append((platform, payload, "RAISED", f"{type(e).__name__}: {e}"))
                continue
            try:
                ok = is_valid_filename(out, platform=platform)
            except Exception as e:  # noqa: BLE001
                bad.append((platform, payload, repr(out), f"CHECK-RAISED {type(e).__name__}"))
                continue
            if not ok:
                bad.append((platform, payload, repr(out), "INVALID OUTPUT"))
    return bad


print("=" * 78)
print("FILEPATH: sanitize -> is_valid round-trip failures")
print("=" * 78)
for row in probe_filepath():
    print(f"  platform={row[0]:<10} in={row[1]!r:<30} out={row[2]:<34} {row[3]}")

print()
print("=" * 78)
print("FILENAME: sanitize -> is_valid round-trip failures")
print("=" * 78)
for row in probe_filename():
    print(f"  platform={row[0]:<10} in={row[1]!r:<30} out={row[2]:<34} {row[3]}")

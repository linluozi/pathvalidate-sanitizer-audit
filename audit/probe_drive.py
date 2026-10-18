"""Probe: does sanitize_filepath silently turn a RELATIVE path into an ABSOLUTE one?

If yes, `os.path.join(upload_dir, sanitized)` discards upload_dir on Windows,
which is a base-directory escape reachable with default parameters and only
input-controlled data.
"""
import ntpath
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathvalidate import (  # noqa: E402
    is_valid_filepath,
    sanitize_filepath,
    validate_filepath,
)

CASES = [
    "C:x.txt",
    "C:file.txt",
    "C:.\\y.txt",
    "C:..\\..\\evil.txt",
    "D:payload.exe",
]

print("== is the input interpreted as relative by ntpath? ==")
print(f"{'input':<24} {'ntpath.isabs':<14} {'sanitized':<26} {'sanitized isabs':<16} {'join result'}")
print("-" * 104)

BASE = r"C:\srv\uploads"

for value in CASES:
    for platform in ["windows", "universal"]:
        in_abs = ntpath.isabs(value)
        try:
            out = sanitize_filepath(value, platform=platform)
        except Exception as e:  # noqa: BLE001
            print(f"{value!r:<24} {str(in_abs):<14} <{type(e).__name__}>")
            continue
        out_abs = ntpath.isabs(str(out))
        joined = os.path.join(BASE, str(out))
        escaped = not os.path.normpath(joined).startswith(BASE)
        flag = "  <== ESCAPES BASE" if escaped else ""
        print(
            f"{value!r:<24} {str(in_abs):<14} {out!r:<26} {str(out_abs):<16} "
            f"{os.path.normpath(joined)!r}{flag}   (platform={platform})"
        )

print()
print("== now the important question: was the input VALID as given? ==")
for value in CASES:
    try:
        validate_filepath(value, platform="windows")
        v = "valid as given"
    except Exception as e:  # noqa: BLE001
        v = f"rejected: {getattr(e, 'reason', type(e).__name__)}"
    out = sanitize_filepath(value, platform="windows")
    print(f"  {value!r:<22} {v:<26} -> {out!r}")

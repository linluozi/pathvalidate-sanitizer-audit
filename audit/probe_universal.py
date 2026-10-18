"""Probe: does the UNIVERSAL platform actually reject absolute paths?

Documented intent (FilePathValidator.validate_abspath):
    "platform-independent absolute file path is not supported"

So under platform="universal" every absolute path must be rejected.  Check
whether that holds for POSIX-style and NT-style inputs.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathvalidate import (  # noqa: E402
    is_valid_filepath,
    sanitize_filepath,
    validate_filepath,
)
from pathvalidate._common import is_nt_abspath  # noqa: E402

CASES = [
    "/abs/path",
    "/etc/passwd",
    "C:/temp/x",
    "C:\\temp\\x",
    "\\\\srv\\share\\f",
    "\\\\?\\C:\\long\\path",
    "\\\\.\\pipe\\x",
    "//srv/share/f",
    "rel/path",
]

print(f"{'input':<24} {'posix_abs':<10} {'nt_abs':<8} {'valid?':<8} {'sanitized'}")
print("-" * 88)
for value in CASES:
    try:
        is_valid_filepath(value, platform="universal")
        valid = "VALID"
    except Exception as e:  # noqa: BLE001
        valid = f"rejected({type(e).__name__.split('Error')[0]})"

    try:
        out = repr(sanitize_filepath(value, platform="universal"))
    except Exception as e:  # noqa: BLE001
        out = f"<raised {type(e).__name__}>"

    import posixpath

    print(
        f"{value!r:<24} {str(posixpath.isabs(value)):<10} {str(is_nt_abspath(value)):<8} "
        f"{valid:<8} {out}"
    )

print()
print("--- accepted absolute paths under 'universal' (should be none):")
leaks = []
for value in CASES:
    import posixpath

    if not (posixpath.isabs(value) or is_nt_abspath(value)):
        continue
    try:
        validate_filepath(value, platform="universal")
    except Exception:  # noqa: BLE001
        continue
    leaks.append(value)
for value in leaks:
    print("   ACCEPTED:", value)

print()
print("--- sanitized output must itself validate under the same platform:")
for value in CASES:
    try:
        out = sanitize_filepath(value, platform="universal")
        ok = is_valid_filepath(out, platform="universal")
    except Exception as e:  # noqa: BLE001
        print(f"   {value!r:<24} -> sanitize raised {type(e).__name__}")
        continue
    if not ok:
        print(f"   {value!r:<24} -> {out!r}  INVALID OUTPUT")

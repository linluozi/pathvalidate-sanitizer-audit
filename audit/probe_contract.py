"""Confirm the contract violation for drive-relative inputs.

Claim: sanitize_filepath takes a path that validate_filepath ACCEPTS and returns
a path that validate_filepath REJECTS, under the same platform.  That is not a
documented trade-off (unlike issue #49/#69, which are about length/strictness),
it is the sanitizer corrupting a valid input.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathvalidate import (  # noqa: E402
    is_valid_filepath,
    sanitize_filepath,
    validate_filepath,
)

CASES = ["C:x.txt", "C:..\\..\\evil.txt", "D:payload.exe", "C:.\\y.txt"]

print(f"{'platform':<11} {'input':<24} {'validate(in)':<14} {'sanitize(out)':<26} {'validate(out)'}")
print("-" * 96)
for platform in ["universal", "windows"]:
    for value in CASES:
        try:
            validate_filepath(value, platform=platform)
            vin = "ACCEPT"
        except Exception as e:  # noqa: BLE001
            vin = f"reject {getattr(e, 'reason', type(e).__name__)}"
        out = sanitize_filepath(value, platform=platform)
        try:
            validate_filepath(out, platform=platform)
            vout = "ACCEPT"
        except Exception as e:  # noqa: BLE001
            vout = f"REJECT {getattr(e, 'reason', type(e).__name__)}"
        flag = "  <== VALID IN, INVALID OUT" if vin == "ACCEPT" and vout.startswith("REJECT") else ""
        print(f"{platform:<11} {value!r:<24} {vin:<14} {out!r:<26} {vout}{flag}")

print()
print("== and the strict opt-in mode confirms it (it raises on its own output) ==")
for value in CASES:
    try:
        out = sanitize_filepath(value, platform="universal", validate_after_sanitize=True)
        print(f"  {value!r:<22} -> {out!r} (no error)")
    except Exception as e:  # noqa: BLE001
        print(f"  {value!r:<22} -> raised {type(e).__name__}: {getattr(e, 'reason', '')}")

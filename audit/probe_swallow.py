"""Which validation errors does sanitize_filepath swallow, and what leaks out?

sanitize_filepath validates its own output but only reacts to NULL_NAME:

    try:
        self._validator.validate(sanitized_path)
    except ValidationError as e:
        if e.reason == ErrorReason.NULL_NAME:
            sanitized_path = self._null_value_handler(e)

Every other reason is discarded.  Enumerate what that lets through.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathvalidate import is_valid_filepath, sanitize_filepath, validate_filepath  # noqa: E402

PAYLOADS = [
    "/abs/path",
    "/etc/passwd",
    "C:/temp/x",
    "C:\\temp\\x",
    "\\\\srv\\share\\f",
    "\\\\?\\C:\\long\\path",
    "//srv/share/f",
    "rel/path",
    "a/../../b",
]

print(f"{'platform':<11} {'input':<24} {'validate_filepath':<34} {'sanitize output':<26} {'valid?'}")
print("-" * 112)

leaks = []
for platform in ["universal", "windows", "linux", "macos", "posix"]:
    for value in PAYLOADS:
        try:
            validate_filepath(value, platform=platform)
            verdict = "ok"
        except Exception as e:  # noqa: BLE001
            reason = getattr(e, "reason", None)
            verdict = f"reject {reason.name if reason else type(e).__name__}"

        try:
            out = sanitize_filepath(value, platform=platform)
        except Exception as e:  # noqa: BLE001
            print(f"{platform:<11} {value!r:<24} {verdict:<34} <raised {type(e).__name__}>")
            continue

        ok = is_valid_filepath(out, platform=platform)
        flag = "" if ok else "  <== INVALID OUTPUT RETURNED"
        print(f"{platform:<11} {value!r:<24} {verdict:<34} {out!r:<26} {ok}{flag}")
        if not ok:
            leaks.append((platform, value, out))

print()
print(f"TOTAL invalid outputs returned silently: {len(leaks)}")
for platform, value, out in leaks:
    print(f"   {platform:<10} {value!r:<24} -> {out!r}")

print()
print("--- same inputs with validate_after_sanitize=True (opt-in guard):")
for platform, value, _out in leaks:
    try:
        o = sanitize_filepath(value, platform=platform, validate_after_sanitize=True)
        print(f"   {platform:<10} {value!r:<24} -> {o!r}  (still no error!)")
    except Exception as e:  # noqa: BLE001
        print(f"   {platform:<10} {value!r:<24} -> raised {type(e).__name__}")

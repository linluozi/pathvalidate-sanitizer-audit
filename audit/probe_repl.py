"""Pin down the replacement-template bug: what exactly can a caller inject?

Root cause hypothesis: replacement_text / reserved_name_handler output is passed
to re.sub() as a REPLACEMENT TEMPLATE, so backslash escapes are interpreted
instead of being treated as literal text.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathvalidate import (  # noqa: E402
    is_valid_filename,
    is_valid_filepath,
    sanitize_filename,
    sanitize_filepath,
)
from pathvalidate._symbol import replace_symbol  # noqa: E402

print("== replacement_text is documented as literal replacement text ==")
print("input 'a?b' with each replacement; inspect the byte values of output")
print()
print(f"{'replacement_text':<18} {'sanitize_filename(out)':<26} {'ord values'}")
print("-" * 84)

for repl in ["\\", "\\x00", "\\b", "\\g<0>", "\\t", "x\\1", "_", "\\\\"]:
    try:
        out = sanitize_filename("a?b", replacement_text=repl)
        ords = [ord(c) for c in out]
        detail = f"{out!r:<24} {ords}"
    except Exception as e:  # noqa: BLE001
        detail = f"<{type(e).__name__}: {e}>"
    print(f"{repl!r:<18} {detail}")

print()
print("== NUL byte injection ==")
try:
    out = sanitize_filename("a?b", replacement_text="\\x00")
    print(f"  sanitize_filename('a?b', replacement_text='\\\\x00') = {out!r}")
    print(f"  NUL present in output: {'\\x00' in out}")
    if "\x00" in out:
        print("  >>> sanitizer produced a filename containing a NUL byte")
except Exception as e:  # noqa: BLE001
    print("  raised", type(e).__name__, e)

print()
print("== sanitizer bypass: replacement that re-emits the invalid char ==")
for label, call in [
    ("sanitize_filename", lambda: sanitize_filename("a?b", replacement_text="\\g<0>")),
    ("sanitize_filepath", lambda: sanitize_filepath("a?b", replacement_text="\\g<0>")),
    ("replace_symbol", lambda: replace_symbol("a-b", replacement_text="\\g<0>")),
]:
    try:
        out = call()
        print(f"  {label:<20} -> {out!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label:<20} -> <{type(e).__name__}>")

out = sanitize_filename("a?b", replacement_text="\\g<0>")
print(f"  is output a valid filename? {is_valid_filename(out)}  <== False means the")
print("     sanitizer returned an invalid name and did not sanitize at all")

print()
print("== filepath + symbol modules affected too ==")
for label, call in [
    ("sanitize_filepath", lambda: sanitize_filepath("a/b?c", replacement_text="\\b")),
    ("replace_symbol", lambda: replace_symbol("a-b", replacement_text="\\b")),
]:
    try:
        out = call()
        print(f"  {label:<20} -> {out!r}  ords={[ord(c) for c in out]}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label:<20} -> <{type(e).__name__}: {e}>")

print()
print("== does the crash type belong to the documented error contract? ==")
print("  documented: raises ValueError for invalid filename (ValidationError subclasses ValueError)")
try:
    sanitize_filename("a?b", replacement_text="\\")
except ValueError as e:
    print("  caught as ValueError:", type(e).__name__)
except Exception as e:  # noqa: BLE001
    print(f"  NOT a ValueError -> {type(e).__name__}, mro={[c.__name__ for c in type(e).__mro__[:4]]}")

"""Cross-version smoke check: run key behaviour assertions on any interpreter.

Deliberately dependency-free so it can run on 3.12/3.13/3.14 without pytest.

The sibling package is put FIRST on sys.path and its resolved location is printed,
so an unrelated site-packages copy of pathvalidate can never be measured by
mistake.  Without ``--allow-external`` the run aborts if the import resolves
anywhere other than this distribution.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from pathvalidate import (  # noqa: E402
    is_valid_filepath,
    sanitize_filename,
    sanitize_filepath,
    validate_filepath,
)

_resolved = os.path.abspath(sys.modules["pathvalidate"].__file__)
_EXPECTED = os.environ.get("PATHVALIDATE_EXPECTED_ROOT", _ROOT)
if not _resolved.startswith(_EXPECTED) and "--allow-external" not in sys.argv:
    sys.exit(
        f"ABORT: imported pathvalidate from {_resolved}\n"
        f"       expected it under {_EXPECTED}\n"
        "       (pass --allow-external to test an installed copy instead)"
    )

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r} want {want!r}")


# --- A. replacement_text must be literal -------------------------------------
check("repl backslash", sanitize_filename("a?b", replacement_text="\\", platform="windows"), "a\\b")
check("repl \\\\b", sanitize_filename("a?b", replacement_text="\\b", platform="windows"), "a\\bb")
check(
    "repl \\\\g<0>",
    sanitize_filename("a?b", replacement_text="\\g<0>", platform="windows"),
    "a\\g<0>b",
)
check("repl normal", sanitize_filename("a?b", replacement_text="_", platform="windows"), "a_b")

# no raw re.error must escape
for repl in ["\\", "x\\1", "\\x00"]:
    try:
        sanitize_filename("a?b", replacement_text=repl, platform="windows")
        sanitize_filepath("a/b?c", replacement_text=repl, platform="windows")
    except Exception as e:  # noqa: BLE001
        failures.append(f"replacement {repl!r} raised {type(e).__name__}: {e}")

# --- B. drive-relative must stay relative ------------------------------------
# note: the separator normalises to the platform's ("/" for universal), which is
# pre-existing behaviour; what matters is that the result stays NON-absolute.
for value, want in [
    ("C:x.txt", "C:x.txt"),
    ("D:payload.exe", "D:payload.exe"),
    ("C:.\\y.txt", "C:y.txt"),
]:
    for platform in ("windows", "universal"):
        got = sanitize_filepath(value, platform=platform)
        check(f"drive {value!r} {platform}", got, want)

check(
    "drive traversal windows",
    sanitize_filepath("C:..\\..\\evil.txt", platform="windows"),
    "C:..\\..\\evil.txt",
)
check(
    "drive traversal universal",
    sanitize_filepath("C:..\\..\\evil.txt", platform="universal"),
    "C:../../evil.txt",
)
for value in ["C:x.txt", "C:..\\..\\evil.txt", "D:payload.exe"]:
    if is_valid_filepath(value, platform="universal"):
        out = sanitize_filepath(value, platform="universal")
        if out.startswith(("/", "\\")) or (len(out) > 2 and out[1] == ":" and out[2] in "/\\"):
            failures.append(f"drive-relative became absolute: {value!r} -> {out!r}")

# --- C. valid in => valid out (universal) ------------------------------------
for value in ["C:x.txt", "C:..\\..\\evil.txt", "D:payload.exe", "C:.\\y.txt"]:
    validate_filepath(value, platform="universal")
    out = sanitize_filepath(value, platform="universal")
    try:
        validate_filepath(out, platform="universal")
    except Exception as e:  # noqa: BLE001
        failures.append(f"valid-in-invalid-out {value!r} -> {out!r}: {e}")
    if not is_valid_filepath(out, platform="universal"):
        failures.append(f"is_valid_filepath False for {out!r}")

# --- D. absolute paths still behave as before --------------------------------
check("abs C:\\x.txt", sanitize_filepath("C:\\x.txt", platform="windows"), "C:\\x.txt")
check("abs C:/x.txt", sanitize_filepath("C:/x.txt", platform="windows"), "C:\\x.txt")
check("abs posix", sanitize_filepath("/a/b", platform="linux"), "/a/b")

# --- E. unrequested behaviour unchanged --------------------------------------
check("plain", sanitize_filename("report.txt"), "report.txt")
check("reserved", sanitize_filename("CON", platform="windows"), "CON_")
check("invalid chars", sanitize_filename("a?b*c", platform="windows"), "abc")

print(f"python {sys.version.split()[0]}  ({sys.platform})")
print(f"imported: {_resolved}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all cross-version checks passed")

"""Collect every number used in the figures and the report page.

Each arm runs in its own subprocess with its own sys.path so an unpatched copy
can never be silently measured instead of the patched one.  Results go to
data/results.json -- nothing in this project hardcodes a measured value.

Usage: python collect_data.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DATA = os.path.join(HERE, "data")

# ---------------------------------------------------------------------------
# per-arm worker: prints one JSON object
# ---------------------------------------------------------------------------
WORKER = r'''
import json, re, sys

sys.path.insert(0, sys.argv[1])          # this arm's tree
import pathvalidate
from pathvalidate import (
    is_valid_filepath, sanitize_filename, sanitize_filepath, validate_filepath,
)
from pathvalidate._symbol import replace_symbol

assert pathvalidate.__file__.startswith(sys.argv[1]), pathvalidate.__file__

out = {"resolved": pathvalidate.__file__, "version": pathvalidate.__version__}

def attempt(label, fn):
    try:
        out[label] = {"ok": True, "value": fn()}
    except Exception as e:
        out[label] = {"ok": False, "error": type(e).__name__,
                      "is_value_error": isinstance(e, ValueError), "msg": str(e)[:120]}

# --- defect A: replacement_text is used as a regex replacement template -----
attempt("A_backslash",  lambda: sanitize_filename("a?b", replacement_text="\\", platform="windows"))
attempt("A_groupref",   lambda: sanitize_filename("a?b", replacement_text="x\\1", platform="windows"))
attempt("A_reemit",     lambda: sanitize_filename("a?b", replacement_text="\\g<0>", platform="windows"))
attempt("A_backspace",  lambda: sanitize_filename("a?b", replacement_text="\\b", platform="windows"))
attempt("A_ord_reemit", lambda: [ord(c) for c in sanitize_filename("a?b", replacement_text="\\b", platform="windows")])
attempt("A_still_valid",lambda: is_valid_filepath(
    sanitize_filepath("a?b", replacement_text="\\g<0>", platform="windows"), platform="windows"))

# --- defect B: drive-relative path promoted to absolute --------------------
import ntpath
rows = []
for value in ["C:x.txt", "D:payload.exe", "C:.\\y.txt", "C:..\\..\\evil.txt"]:
    try:
        san = sanitize_filepath(value, platform="windows")
    except Exception as e:
        rows.append({"in": value, "out": None, "error": type(e).__name__}); continue
    rows.append({"in": value, "out": san,
                 "in_abs": ntpath.isabs(value), "out_abs": ntpath.isabs(san)})
out["B_rows"] = rows

uni = []
for value in ["C:x.txt", "D:payload.exe", "C:..\\..\\evil.txt", "C:.\\y.txt"]:
    try:
        validate_filepath(value, platform="universal"); vin = "accept"
    except Exception as e:
        vin = getattr(getattr(e, "reason", None), "name", type(e).__name__)
    try:
        san = sanitize_filepath(value, platform="universal")
        validate_filepath(san, platform="universal"); vout = "accept"
    except Exception as e:
        vout = getattr(getattr(e, "reason", None), "name", type(e).__name__)
    uni.append({"in": value, "vin": vin, "vout": vout})
out["B_universal"] = uni

# --- defect C: consecutive collapse of a multi-char replacement ------------
cc = []
for value, repl in [("!!!", "ab"), ("!!!", "aa"), ("!!!", "."), ("a---b", "-")]:
    try:
        cc.append({"in": value, "repl": repl,
                   "out": replace_symbol(value, repl, is_replace_consecutive_chars=True)})
    except Exception as e:
        cc.append({"in": value, "repl": repl, "error": type(e).__name__})
out["C_rows"] = cc

# --- guard: absolute paths must be untouched by the fix --------------------
guard = []
for value, platform in [("C:\\\\x.txt", "windows"), ("C:/x.txt", "windows"), ("/a/b", "linux")]:
    try:
        guard.append({"in": value, "platform": platform,
                      "out": sanitize_filepath(value, platform=platform)})
    except Exception as e:
        guard.append({"in": value, "platform": platform, "error": type(e).__name__})
out["guard_abs"] = guard

# --- sweep 1: how many (platform, input) pairs yield an output the validator rejects?
SWEEP_INPUTS = [
    "rel/path", "a/b", "file.txt", "a b",
    "C:x.txt", "C:file.txt", "D:payload.exe", "C:.\\\\y.txt", "C:..\\\\..\\\\evil.txt",
    "/abs/path", "C:/temp/x", "\\\\\\\\srv\\\\share\\\\f", "a/../../b",
    "CON", "..", "path.", "a?b",
]
DRIVE_RELATIVE = {"C:x.txt", "C:file.txt", "D:payload.exe", "C:.\\\\y.txt", "C:..\\\\..\\\\evil.txt"}
sweep = {}
for platform in ["universal", "windows", "linux", "macos", "posix"]:
    fixed = design = ok = 0
    for value in SWEEP_INPUTS:
        try:
            san = sanitize_filepath(value, platform=platform)
        except ValueError:
            ok += 1          # a rejected input is not an invalid output
            continue
        except Exception:
            ok += 1
            continue
        if is_valid_filepath(san, platform=platform):
            ok += 1
        elif value in DRIVE_RELATIVE:
            fixed += 1       # caused by the drive-relative promotion
        else:
            design += 1      # documented: sanitizers do not guarantee validity
    sweep[platform] = {"ok": ok, "drive_relative": fixed, "documented_design": design,
                       "total": len(SWEEP_INPUTS)}
out["sweep_invalid_output"] = sweep

# --- corpus 2: outcome class of each replacement_text ----------------------
# NB: the comparison must happen here, inside the arm, on the real string.
# Classifying in the reader after json() was wrong earlier: the repr's escaping
# made r"\b" and "\b" (backspace) indistinguishable, so real corruption was
# scored as "literal".
REPLS = ["", "_", "-", "\\", "\\\\", "\\b", "\\t", "\\g<0>", "x\\1", "\\x00"]
corpus = []
for repl in REPLS:
    entry = {"repl_show": repl.encode("unicode_escape").decode(),
             "repl_len": len(repl)}
    try:
        san = sanitize_filename("a?b", replacement_text=repl, platform="windows")
    except Exception as e:
        entry["class"] = "crash"
        entry["error"] = type(e).__name__
        corpus.append(entry)
        continue
    expected = "a" + repl + "b"
    if san == expected:
        entry["class"] = "literal"
    elif san == "a?b":
        entry["class"] = "noop"
    else:
        entry["class"] = "corrupt"
    entry["out_show"] = san.encode("unicode_escape").decode()
    entry["ords"] = [ord(c) for c in san]
    entry["ctrl_bytes"] = sum(1 for c in san if ord(c) < 0x20)
    corpus.append(entry)
out["replacement_corpus"] = corpus

print(json.dumps(out, ensure_ascii=False))
'''


def run_arm(tree):
    res = subprocess.run(
        [PY, "-c", WORKER, tree],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(f"arm {tree} failed:\n{res.stderr[-1500:]}")
    return json.loads(res.stdout)


def main():
    os.makedirs(DATA, exist_ok=True)
    arms = {
        "unpatched": run_arm(os.path.join(HERE, "unpatched")),
        "patched": run_arm(os.path.join(HERE, "patched")),
    }
    # sanity: the two arms really are different code
    if arms["unpatched"]["resolved"] == arms["patched"]["resolved"]:
        raise SystemExit("both arms resolved to the same file")

    with open(os.path.join(DATA, "results.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump(arms, fp, ensure_ascii=False, indent=2, sort_keys=True)

    for arm, d in arms.items():
        print(f"[{arm}] {d['resolved']}")
        for k in ("A_backslash", "A_reemit", "A_backspace"):
            v = d[k]
            print(f"   {k}: {'OK ' + repr(v['value'])[:40] if v['ok'] else v['error']}")
    print("\nwrote", os.path.join(DATA, "results.json"))


if __name__ == "__main__":
    main()

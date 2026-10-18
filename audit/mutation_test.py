"""Mutation test: do the new regression tests actually detect regressions?

Each mutation re-introduces a plausible bug into the patched source, runs the new
tests, and expects failure.  A mutation that survives means the test suite has a
blind spot.
"""
import io
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PATHVALIDATE_PY", sys.executable)

TESTS = [
    "-k",
    "escape_replacement or drive_relative or drive_root or absolute_drive or replacement or multichar or reserved_name_handler_literal",
]

MUTATIONS = [
    (
        "M1: helper becomes identity (no escaping)",
        "pathvalidate/_common.py",
        'return replacement_text.replace("\\\\", "\\\\\\\\")',
        "return replacement_text",
    ),
    (
        "M2: escape only the group-ref prefix",
        "pathvalidate/_common.py",
        'return replacement_text.replace("\\\\", "\\\\\\\\")',
        'return replacement_text.replace("\\\\g", "\\\\\\\\g")',
    ),
    (
        "M3: drive-relative detection disabled",
        "pathvalidate/_filepath.py",
        "is_drive_relative = bool(drive) and bool(unicode_filepath)",
        "is_drive_relative = False",
    ),
    (
        "M4: drive prefix dropped entirely",
        "pathvalidate/_filepath.py",
        "            sanitized_path = drive + sanitized_path",
        "            sanitized_path = sanitized_path",
    ),
    (
        "M5: drive always treated as absolute (original bug)",
        "pathvalidate/_filepath.py",
        "if drive and not is_drive_relative:",
        "if drive:",
    ),
    (
        "M6: consecutive quantifier left ungrouped (original bug)",
        "pathvalidate/_symbol.py",
        'f"(?:{re.escape(replacement_text)})+",',
        'f"{re.escape(replacement_text)}+",',
    ),
    (
        "M7: filename sanitizer stops escaping repl",
        "pathvalidate/_filename.py",
        "            escape_replacement_text(replacement_text), str(value)",
        "            replacement_text, str(value)",
    ),
    (
        "M8: ltsv sanitizer stops escaping repl",
        "pathvalidate/_ltsv.py",
        "escape_replacement_text(replacement_text), to_str(label)",
        "replacement_text, to_str(label)",
    ),
    (
        "M9: reserved-name rewrite stops escaping",
        "pathvalidate/_filename.py",
        "                        escape_replacement_text(replacement_word),",
        "                        replacement_word,",
    ),
]


def run_tests():
    r = subprocess.run(
        [PY, "-m", "pytest", "test", "-q", "-x", "--no-header", *TESTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return r.returncode, r.stdout + r.stderr


results = []
for label, rel, old, new in MUTATIONS:
    path = os.path.join(ROOT, rel)
    original = io.open(path, encoding="utf-8", newline="").read()

    if old not in original:
        results.append((label, "SETUP-FAILED (anchor not found)", ""))
        continue

    mutated = original.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(mutated)
    try:
        code, out = run_tests()
        tail = [ln for ln in out.splitlines() if ln.startswith("FAILED") or " passed" in ln]
        verdict = "KILLED (tests failed as expected)" if code != 0 else "SURVIVED  <== BLIND SPOT"
        results.append((label, verdict, " | ".join(tail[-3:])))
    finally:
        io.open(path, "w", encoding="utf-8", newline="").write(original)

print(f"{'mutation':<50} {'verdict'}")
print("=" * 100)
killed = 0
for label, verdict, tail in results:
    print(f"{label:<50} {verdict}")
    if tail:
        print(f"{'':<50} {tail[:150]}")
    if verdict.startswith("KILLED"):
        killed += 1

print()
print(f"score: {killed}/{len(MUTATIONS)} mutations killed")

# verify the tree is clean after mutation testing
r = subprocess.run(
    ["git", "diff", "--stat"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
)
print("\nsource restored, git diff --stat:")
print(r.stdout.strip() or "(no changes)")

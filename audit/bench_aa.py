"""A/A noise floor: compare two byte-identical baseline copies.

If the A/A ratios are not tight around 1.0, no A/B number from this machine is
reportable as a point value.
"""
import json
import os
import statistics
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PARENT = os.path.dirname(ROOT)

CASES = ["plain", "invalid_chars", "path", "reserved", "symbol"]
ROUNDS = 9

RUNNER = r'''
import json, statistics, sys, timeit
sys.path.insert(0, sys.argv[1])
from pathvalidate import sanitize_filename, sanitize_filepath
from pathvalidate._symbol import replace_symbol
CASES = {
    "plain": lambda: sanitize_filename("report-2026-final.txt"),
    "invalid_chars": lambda: sanitize_filename("a?b*c|d<e>f.txt"),
    "path": lambda: sanitize_filepath("a/b?c/d*e/f.txt"),
    "reserved": lambda: sanitize_filename("CON.txt", platform="windows"),
    "symbol": lambda: replace_symbol("a-b_c.d"),
}
out = {}
for name, fn in CASES.items():
    fn()
    out[name] = statistics.median(timeit.timeit(fn, number=400) / 400 * 1e6 for _ in range(3))
print(json.dumps(out))
'''


def run(d):
    r = subprocess.run(
        [PY, "-c", RUNNER, os.path.join(PARENT, d)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return json.loads(r.stdout)


acc = {"x": [], "y": []}
for i in range(ROUNDS):
    order = [("x", "_benchB"), ("y", "_benchC")]
    if i % 2:
        order.reverse()
    for k, d in order:
        acc[k].append(run(d))

print(f"{'case':<16} {'X us':>9} {'Y us':>9} {'ratio X/Y':>10}")
print("-" * 48)
ratios = []
for c in CASES:
    x = statistics.median(r[c] for r in acc["x"])
    y = statistics.median(r[c] for r in acc["y"])
    ratios.append(x / y)
    print(f"{c:<16} {x:>9.3f} {y:>9.3f} {x / y:>10.3f}x")
print()
print(f"A/A ratio range: {min(ratios):.3f} - {max(ratios):.3f}")
print("Any A/B ratio inside this band is indistinguishable from noise.")

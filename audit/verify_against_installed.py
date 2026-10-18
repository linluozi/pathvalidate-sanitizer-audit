"""Run the cross-version checks against a specific pathvalidate install.

Usage: python verify_against_installed.py <dir-containing-pathvalidate>
Used to prove the checks actually fail on unpatched code.
"""
import os
import runpy
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

target = sys.argv[1]
script = sys.argv[2]

sys.path.insert(0, target)
# force resolution away from the sibling package
import pathvalidate  # noqa: E402

resolved = os.path.abspath(pathvalidate.__file__)
if not resolved.startswith(os.path.abspath(target)):
    sys.exit(f"could not force import to {target}; got {resolved}")
print(f"target  : {target}")
print(f"resolved: {resolved}")

# strip the audit dir from sys.path so the sibling copy cannot win
sys.argv = [script] + sys.argv[3:]
runpy.run_path(script, run_name="__main__")

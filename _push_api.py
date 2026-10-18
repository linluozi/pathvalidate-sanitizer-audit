"""Push the local commit to GitHub via the Git Data API.

Used when github.com:443 is unreachable but api.github.com works.  Builds blobs,
then trees bottom-up (deepest directory first), then a commit, then updates the
ref.  Prints the remote root tree sha so it can be compared with the local
`git rev-parse HEAD^{tree}` -- equality proves byte-for-byte agreement.
"""
import base64
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = "linluozi/pathvalidate-sanitizer-audit"
ROOT = os.path.dirname(os.path.abspath(__file__))


def gh(args, payload=None):
    cmd = ["gh", "api"] + args
    if payload is not None:
        cmd += ["--input", "-"]
    res = subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args)} failed:\n{res.stderr[-1200:]}")
    return res.stdout


def git(*args):
    return subprocess.run(
        ["git"] + list(args), capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    ).stdout.strip()


def main():
    files = git("ls-files").splitlines()
    print(f"tracked files: {len(files)}")

    # --- 1. blobs ---------------------------------------------------------
    blob_sha = {}
    for i, path in enumerate(files, 1):
        with open(os.path.join(ROOT, path), "rb") as fp:
            raw = fp.read()
        out = gh(
            [f"repos/{REPO}/git/blobs", "-f", f"encoding=base64"],
            {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"},
        )
        blob_sha[path] = json.loads(out)["sha"]
        if i % 25 == 0 or i == len(files):
            print(f"  blobs {i}/{len(files)}")

    # --- 2. trees, deepest directory first --------------------------------
    dirs = {""}
    for path in files:
        parts = path.split("/")[:-1]
        for d in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:d]))
    depth = {d: (0 if d == "" else d.count("/") + 1) for d in dirs}
    ordered = sorted(dirs, key=lambda d: -depth[d])

    tree_sha = {}
    for d in ordered:
        prefix = "" if d == "" else d + "/"
        entries = []
        for path in files:
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix):]
            if "/" in rest:
                continue  # belongs to a subdirectory
            entries.append({"path": rest, "mode": "100644", "type": "blob",
                            "sha": blob_sha[path]})
        for sub in dirs:
            if sub == "" or sub == d:
                continue
            parent = sub.rsplit("/", 1)[0] if "/" in sub else ""
            if parent == d:
                entries.append({"path": sub.rsplit("/", 1)[-1], "mode": "040000",
                                "type": "tree", "sha": tree_sha[sub]})
        out = gh([f"repos/{REPO}/git/trees", "-f", f"base_tree="] if False else
                 [f"repos/{REPO}/git/trees"], {"tree": entries})
        tree_sha[d] = json.loads(out)["sha"]
        print(f"  tree {d or '<root>':<24} {tree_sha[d][:12]}  ({len(entries)} entries)")

    root = tree_sha[""]
    local = git("rev-parse", "HEAD^{tree}")
    print()
    print("remote root tree:", root)
    print("local  root tree:", local)
    print("IDENTICAL:", root == local)

    # --- 3. commit --------------------------------------------------------
    msg = git("log", "-1", "--pretty=%B")
    out = gh(
        [f"repos/{REPO}/git/commits"],
        {"message": msg, "tree": root, "parents": []},
    )
    commit = json.loads(out)["sha"]
    print("commit:", commit)

    # --- 4. ref -----------------------------------------------------------
    try:
        gh([f"repos/{REPO}/git/refs", "-f", "ref=refs/heads/main", "-f", f"sha={commit}"])
        print("created refs/heads/main")
    except RuntimeError:
        gh([f"repos/{REPO}/git/refs/heads/main", "-X", "PATCH", "-f", f"sha={commit}"])
        print("updated refs/heads/main")


if __name__ == "__main__":
    main()

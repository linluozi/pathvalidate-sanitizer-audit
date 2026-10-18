"""Render figures for the report page from data/results.json.

Design rule applied here: only chart something when the comparison has more than
one non-zero arm.  Before/after path pairs and per-platform zero rows are tables,
not charts -- charting them produced plots where 16 of 17 bars were zero and the
"after" series was invisible, which is worse than no figure at all.

Palette: warm editorial (espresso / amber / terracotta / olive) on a dark surface.
Every number is read from data/results.json; nothing is typed in by hand.

Usage: python make_figures.py
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)

INK = "#f2e9dd"
PAPER = "#1b1714"
PANEL = "#221d19"
MUTED = "#a3937f"
AMBER = "#d9a13b"
TERRA = "#c56a45"
OLIVE = "#9aa06a"
DEEP = "#8d3a3a"
GRID = "#3a322b"

plt.rcParams.update(
    {
        "figure.facecolor": PAPER,
        "axes.facecolor": PANEL,
        "savefig.facecolor": PAPER,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": GRID,
        "font.size": 11,
        "font.family": "DejaVu Sans",
    }
)

with open(os.path.join(HERE, "data", "results.json"), encoding="utf-8") as fp:
    D = json.load(fp)


def tidy(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)


# ===========================================================================
# Figure 1: replacement_text corpus -- outcome class, before vs after
# ===========================================================================
def fig_replacement():
    classes = ["literal", "corrupt", "noop", "crash"]
    colours = {"literal": OLIVE, "corrupt": TERRA, "noop": AMBER, "crash": DEEP}
    labels = {
        "literal": "literal (correct)",
        "corrupt": "silently corrupted",
        "noop": "sanitisation skipped",
        "crash": "crash (re.error)",
    }

    def count(arm, k):
        return sum(1 for c in D[arm]["replacement_corpus"] if c["class"] == k)

    present = [k for k in classes if count("unpatched", k) or count("patched", k)]
    n_total = len(D["unpatched"]["replacement_corpus"])

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), sharey=True)
    for ax, arm, title in zip(
        axes, ("unpatched", "patched"), ("Before  ·  v3.3.1", "After  ·  patched")
    ):
        bottom = 0
        for k in present:
            n = count(arm, k)
            if n == 0:
                continue
            ax.bar(0, n, bottom=bottom, width=0.46, color=colours[k],
                   edgecolor=PAPER, linewidth=1.4)
            ax.text(0, bottom + n / 2, str(n), ha="center", va="center",
                    color="#1b1714", fontweight="bold", fontsize=13)
            bottom += n
        ax.set_title(title, color=INK, fontsize=12.5, pad=12)
        ax.set_xlim(-0.55, 0.55)
        ax.set_ylim(0, n_total)
        ax.set_xticks([])
        tidy(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.7)

    axes[0].set_ylabel(f"distinct replacement_text values (n = {n_total})")
    axes[0].legend(
        handles=[Patch(facecolor=colours[k], label=labels[k]) for k in present],
        loc="upper center", bbox_to_anchor=(1.07, -0.03), ncol=len(present),
        frameon=False, labelcolor=INK, fontsize=9.8,
    )
    fig.suptitle("replacement_text is inserted verbatim: does it survive?",
                 color=INK, fontsize=13.5, y=0.985)
    fig.subplots_adjust(left=0.10, right=0.985, top=0.845, bottom=0.20, wspace=0.12)
    fig.savefig(os.path.join(ASSETS, "replacement-text.png"), dpi=170)
    plt.close(fig)


# ===========================================================================
# Figure 2: composition shift on the universal platform.  The 5 inputs broken by
#    the drive-relative promotion move into the "valid output" bucket; the 3 that
#    fail for the documented reason stay put -- which is exactly the point: the
#    fix is scoped, it did not "fix everything".
# ===========================================================================
def fig_composition():
    keys = ["ok", "drive_relative", "documented_design"]
    colours = {"ok": OLIVE, "drive_relative": TERRA, "documented_design": MUTED}
    labels = {
        "ok": "valid output",
        "drive_relative": "rejected — drive-relative promotion (this bug)",
        "documented_design": "rejected — documented: no validity guarantee",
    }

    fig, ax = plt.subplots(figsize=(9.6, 3.9))
    tidy(ax)

    arms = ["unpatched", "patched"]
    names = ["before", "after"]
    data = [D[a]["sweep_invalid_output"]["universal"] for a in arms]
    total = data[0]["total"]

    for i, (d, nm) in enumerate(zip(data, names)):
        left = 0
        for k in keys:
            v = d[k]
            if v == 0:
                left += v
                continue
            ax.barh(i, v, left=left, height=0.5, color=colours[k],
                    edgecolor=PAPER, linewidth=1.4)
            ax.text(left + v / 2, i, str(v), ha="center", va="center",
                    color="#1b1714", fontweight="bold", fontsize=12)
            left += v

    ax.set_yticks([0, 1])
    ax.set_yticklabels([f"{nm}\n(n = {total})" for nm in names])
    ax.invert_yaxis()
    ax.set_xlim(0, total)
    ax.set_xlabel("path names swept on platform='universal'")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.7)
    ax.legend(
        handles=[Patch(facecolor=colours[k], label=labels[k]) for k in keys],
        loc="upper center", bbox_to_anchor=(0.5, -0.30), ncol=3,
        frameon=False, labelcolor=INK, fontsize=9.5,
    )
    ax.set_title("What the drive-relative fix actually changed",
                 color=INK, fontsize=13, pad=12)
    fig.tight_layout(rect=(0.012, 0, 1, 0.94))
    fig.savefig(os.path.join(ASSETS, "composition-shift.png"), dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    fig_replacement()
    fig_composition()
    for name in sorted(os.listdir(ASSETS)):
        print(f"  {name:28s} {os.path.getsize(os.path.join(ASSETS, name)):>8d} bytes")

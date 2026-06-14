import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os

PLOTS_DIR = os.path.join(os.path.dirname(__file__), "plots")

fig, ax = plt.subplots(figsize=(7, 6))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

orange = "tomato"
blue   = "steelblue"

# (col, row, boja, kratko)
# row=1 gore, row=0 dolje
# col=0 lijevo, col=1 desno
cells = [
    # col=predviđeno, row=stvarno
    # row=1 gore (Legitimni stvarno), row=0 dolje (Zlonamjerni stvarno)
    # col=0 lijevo (Legitimni predviđeno), col=1 desno (Zlonamjerni predviđeno)
    (0, 1, orange, "True Negative"),   # gore lijevo:  stvarno=Leg, predv=Leg
    (1, 1, blue,   "False Positive"),  # gore desno:   stvarno=Leg, predv=SQLi
    (0, 0, blue,   "False Negative"),  # dolje lijevo: stvarno=SQLi, predv=Leg
    (1, 0, orange, "True Positive"),   # dolje desno:  stvarno=SQLi, predv=SQLi
]

for (col, row, color, short) in cells:
    rect = mpatches.FancyBboxPatch(
        (col, row), 1, 1,
        boxstyle="square,pad=0",
        facecolor=color, edgecolor="white", linewidth=3,
        alpha=0.85
    )
    ax.add_patch(rect)
    cx = col + 0.5
    cy = row + 0.5
    ax.text(cx, cy, short, ha="center", va="center",
            fontsize=13, fontweight="bold", color="white")

ax.set_xlim(-0.02, 2.02)
ax.set_ylim(-0.02, 2.02)

ax.set_xticks([0.5, 1.5])
ax.set_xticklabels(["Legitimni (0)", "Zlonamjerni (1)"], fontsize=11, fontweight="bold", color="#2C3E50")
ax.set_yticks([0.5, 1.5])
ax.set_yticklabels(["Zlonamjerni (1)", "Legitimni (0)"], fontsize=11, fontweight="bold", color="#2C3E50")

ax.xaxis.set_label_position("top")
ax.xaxis.tick_top()
ax.set_xlabel("Predviđena klasa", fontsize=12, fontweight="bold", color="#7F8C8D", labelpad=12)
ax.set_ylabel("Stvarna klasa", fontsize=12, fontweight="bold", color="#7F8C8D", labelpad=12)

for spine in ax.spines.values():
    spine.set_visible(False)
ax.tick_params(length=0)

fig.tight_layout()
fname = "confusion_matrix_general.png"
fig.savefig(os.path.join(PLOTS_DIR, fname), dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: plots/{fname}")

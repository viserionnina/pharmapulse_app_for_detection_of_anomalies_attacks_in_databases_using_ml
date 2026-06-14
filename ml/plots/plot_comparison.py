import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

PLOTS_DIR = os.path.join(os.path.dirname(__file__), "plots")

datasets = ["DS1", "DS2", "DS3", "DS4", "DS5", "DS6"]

rf = {
    "Accuracy":  [0.8950, 0.9590, 0.9848, 0.9906, 0.9929, 0.9942],
    "Precision": [1.0000, 0.9893, 0.9911, 0.9949, 0.9956, 0.9967],
    "Recall":    [0.7900, 0.9280, 0.9784, 0.9862, 0.9901, 0.9916],
    "F1":        [0.8827, 0.9577, 0.9847, 0.9906, 0.9929, 0.9942],
    "ROC-AUC":   [0.9734, 0.9860, 0.9977, 0.9993, 0.9996, 0.9997],
}

if_ = {
    "Accuracy":  [0.9160, 0.9418, 0.9575, 0.9525, 0.9525, 0.9528],
    "Precision": [0.8495, 0.9003, 0.9339, 0.9275, 0.9279, 0.9248],
    "Recall":    [0.8750, 0.9063, 0.9236, 0.9130, 0.9127, 0.9173],
    "F1":        [0.8621, 0.9033, 0.9287, 0.9202, 0.9202, 0.9210],
    "ROC-AUC":   [0.9043, 0.9317, 0.9478, 0.9412, 0.9412, 0.9427],
}

metrics = ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]
ylabels = ["Acc", "Precision", "Recall", "F1", "ROC-AUC"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

for metric, ylabel in zip(metrics, ylabels):
    fig, ax = plt.subplots(figsize=(7, 5))

    ax.plot(datasets, rf[metric], color="darkblue", linewidth=0.75,
            marker="s", markersize=7, label="RF")
    ax.plot(datasets, if_[metric], color="tomato", linewidth=0.75,
            marker="^", markersize=7, label="iForest")

    y_min = min(min(rf[metric]), min(if_[metric]))
    ax.set_ylim(max(0.75, y_min - 0.02), 1.005)

    ax.set_xlabel("Dataset", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.legend(fontsize=11, frameon=True, loc="lower right")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)

    fig.tight_layout()
    fname = f"comparison_{metric.lower().replace('-', '_')}.png"
    fig.savefig(os.path.join(PLOTS_DIR, fname), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: plots/{fname}")

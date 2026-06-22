import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pickle
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from ml.if_features import keyword_features

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "models", "DS6")
PLOTS_DIR  = os.path.dirname(__file__)

def _r(name):
    with open(os.path.join(MODELS_DIR, name), "rb") as f:
        return pickle.load(f)

iso       = _r("isolation_forest.pkl")
scaler    = _r("scaler.pkl")
threshold = _r("if_threshold.pkl")

import pandas as pd
df = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "Superviz25_SQL_dataset_cleaned.csv"), low_memory=False)

# subsample 2000 uzoraka (1400 normal, 600 sqli — 70/30)
normal = df[(df["label"] == 0) & (df["split"] == "test")].sample(n=469428, random_state=42)
sqli   = df[(df["label"] == 1) & (df["split"] == "test")].sample(n=201184, random_state=42)
sample = pd.concat([normal, sqli]).sample(frac=1, random_state=42).reset_index(drop=True)

kw     = keyword_features(sample["full_query"].tolist())
kw_sc  = scaler.transform(kw)
scores = iso.decision_function(kw_sc)
labels = sample["label"].values

fig, ax = plt.subplots(figsize=(22, 6))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

mask_normal = labels == 0
mask_sqli   = labels == 1

ax.scatter(np.where(mask_normal)[0], scores[mask_normal],
           color="steelblue", alpha=0.25, s=8, label="Normal (0)", zorder=2)
ax.scatter(np.where(mask_sqli)[0], scores[mask_sqli],
           color="tomato", alpha=0.4, s=8, label="SQLi (1)", zorder=3)

ax.axhline(y=threshold, color="black", linestyle="--", linewidth=1.5,
           label=f"Threshold ({threshold:.4f})", zorder=10)

ax.set_xlabel("Indeks uzorka", fontsize=12)
ax.set_ylabel("Anomaly Score", fontsize=12)
ax.set_title("Isolation Forest — Anomaly Score na uzorku iz testnog skupa DS6", fontsize=13)
ax.legend(fontsize=11, frameon=True)
ax.grid(axis="y", alpha=0.3, linestyle="--")
ax.set_axisbelow(True)

for spine in ["top", "right"]:
    ax.spines[spine].set_visible(False)

fig.tight_layout()
fname = "if_scatter_whole_DS6.png"
fig.savefig(os.path.join(PLOTS_DIR, fname), dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: plots/{fname}")

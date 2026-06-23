import pandas as pd
import numpy as np
import pickle
import os
import time
import scipy.sparse as sp

import matplotlib
matplotlib.use("Agg") #postavlja backend za renderiranje grafova bez potrebe za GUI (za server okruženje)
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D as _Axes3D 

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.tree import plot_tree
from sklearn.metrics import ConfusionMatrixDisplay, classification_report, accuracy_score,precision_score, recall_score, f1_score,  roc_auc_score,confusion_matrix, precision_recall_curve, average_precision_score, roc_curve, auc
from sklearn.model_selection import train_test_split
import seaborn as sns

from ml.if_features import SQL_KEYWORDS, keyword_features

# mijenjanje imena za svaki dataset
DS_NAME = "DS6_test_2"

#kreiranje direktorija
DATASET_DIR = os.path.join(os.path.dirname(__file__), "datasets")
os.makedirs(DATASET_DIR, exist_ok=True)
PLOTS_DIR = os.path.join(os.path.dirname(__file__), "plots", DS_NAME)
os.makedirs(PLOTS_DIR, exist_ok=True)
MODELS_DIR = os.path.join(os.path.dirname(__file__), "datasets", "models", DS_NAME)
os.makedirs(MODELS_DIR, exist_ok=True)

#pocetak racunaja vremena učenja modela i evaluacije
start = time.time()

print("Loading dataset...")
df_main = pd.read_csv(os.path.join(DATASET_DIR, "Superviz25_SQL_dataset_cleaned.csv"), low_memory=False) #low_memory=False da se izbjegnu warningi o miješanju tipova u stupcima, iako to može povećati memorijsku potrošnju ali pouzdanije za veliki dataset
print(f"Glavni dataset: {len(df_main):,} redova")

# pool_size = pd.read_csv('ml/datasets/Superviz25_SQL_dataset_cleaned.csv', low_memory=False)
# print(pool_size.groupby(['split', 'label']).size())
# # test   0        3017390
# #        1         336281
# # train  0         335306

# Supervised RF: svi legitimni (train split) + svi SQLi (test split)
sql_legit_pool = df_main[(df_main["split"] == "train") & (df_main["label"] == 0)].sample(n=335306) #mjenjanje vel. uzoraka za svaki dataset za RF model - normalni
sqli_pool  = df_main[(df_main["split"] == "test")  & (df_main["label"] == 1)].sample(n=336281) #mjenjanje vel. uzoraka za svaki dataset za RF model - maliciozni
df_rf_supervised = pd.concat([sql_legit_pool, sqli_pool]).sample(frac=1, random_state=42).reset_index(drop=True) #spajamo u jedan dataset i miješamo redoslijed (shuffle) da ne bi model naučio da su prvi redovi legit, a zadnji SQLi

X_rf_supervised, y_rf_supervised = df_rf_supervised["full_query"], df_rf_supervised["label"] #ulazni podaci i labele za nadzirano učenje RF modela
X_train, X_tmp, y_train, y_tmp = train_test_split(X_rf_supervised, y_rf_supervised, test_size=0.2, random_state=42, stratify=y_rf_supervised) #80% za trening, 20% za privremeni skup (koji ćemo onda podijeliti na val i test)
X_val, X_test, y_val, y_test = train_test_split(X_tmp, y_tmp, test_size=0.5, random_state=42, stratify=y_tmp)  #10% val, 10% test (od ukupnog skupa) — stratify da se održi ista distribucija klasa u svim splitovima

print(f"Supervised - Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")
print(f"Class distribution (train): {y_train.value_counts().to_dict()}")

# IF train: samo label=0 queriji iz train splita, BEZ labela — nenadzirano
X_if_train = X_train[y_train == 0]

# IF test: 70% normal, 30% maliciozni (realističniji scenarij)
test_normal_pool = df_main[(df_main["split"] == "test") & (df_main["label"] == 0)]
if_test_normal = test_normal_pool.sample(n=469428, random_state=42)  # DS1
if_test_attack = sqli_pool.sample(n=201184, random_state=42)          # DS1
df_if_test = pd.concat([if_test_normal, if_test_attack]).sample(frac=1, random_state=42).reset_index(drop=True)
X_if_test = df_if_test["full_query"]
y_if_test = df_if_test["label"]

# IF val: ista distribucija kao test, za Youden's J threshold tuning 
if_val_normal = test_normal_pool.sample(n=234714, random_state=99)  # DS1
if_val_attack = sqli_pool.sample(n=100592, random_state=99)         # DS1
df_if_val = pd.concat([if_val_normal, if_val_attack]).sample(frac=1, random_state=99).reset_index(drop=True)
X_if_val  = df_if_val["full_query"]
y_if_val  = df_if_val["label"]

print(f"IF train: {len(X_if_train)} upita bez labela (nenadzirano)")
print(f"IF test: {len(X_if_test)} ({(y_if_test==0).sum()} normal, {(y_if_test==1).sum()} napad)")
print(f"IF val: {len(X_if_val)} (threshold tuning)")

# ============================================================
# 1. RANDOM FOREST (nadzirano učenje)
# ============================================================
# --- TF-IDF ---
print("\nFitting TF-IDF vectorizer: ")
vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), max_features=5000, sublinear_tf=True) # duži n-grami mogu bolje uhvatiti union select, drop table itd.
X_train_vec = vectorizer.fit_transform(X_train)
X_val_vec = vectorizer.transform(X_val)
X_test_vec = vectorizer.transform(X_test)

print("\n--- Random Forest ---")
start_rf = time.time()
rf = RandomForestClassifier(
    n_estimators=100,
    max_depth=None,          # ili npr. 50 ako želiš ograničiti
    max_features="sqrt",     # default, ali eksplicitno
    min_samples_leaf=1,      # default
    class_weight="balanced", # uravnotežuje klase u slučaju neravnoteže (više normalnih nego napada)
    n_jobs=-1,
    random_state=42
)
rf.fit(X_train_vec, y_train)

val_pred = rf.predict(X_val_vec)
test_pred = rf.predict(X_test_vec)

print("\nValidation:")
print(classification_report(y_val, val_pred, target_names=["Normal", "SQLi"]))

print("Test:")
print(f" Accuracy        : {accuracy_score(y_test, test_pred):.4f}")
print(f" Precision       : {precision_score(y_test, test_pred):.4f}")
print(f" Recall          : {recall_score(y_test, test_pred):.4f}")
print(f" F1              : {f1_score(y_test, test_pred):.4f}")
print(f" ROC-AUC         : {roc_auc_score(y_test, rf.predict_proba(X_test_vec)[:,1]):.4f}")
print(f" Confusion matrix:\n{confusion_matrix(y_test, test_pred)}")

# ============================================================
# 2. ISOLATION FOREST (nenadzirano učenje) 
# ============================================================
elapsed_rf = time.time() - start_rf
print(f"Vrijeme treninga RF: {int(elapsed_rf // 60)}m {int(elapsed_rf % 60)}s")

print("\n--- Isolation Forest ---")
start_if = time.time()
print(f"Trening na {len(X_if_train)} legitimnih SQL upita")

print("Building keyword features...")
kw_if_train = keyword_features(X_if_train.tolist())
kw_if_val   = keyword_features(X_if_val.tolist())
kw_if_test  = keyword_features(X_if_test.tolist())

#Normalizira podatke kako bi IF  model pravilno usporedio razl. značajke
scaler = StandardScaler()
kw_train_scaled = scaler.fit_transform(kw_if_train)
kw_if_val_scaled = scaler.transform(kw_if_val)
kw_test_scaled  = scaler.transform(kw_if_test)

# Contamination = 0.15 (pretpostavka da ~15% upita u produkciji može biti napad)
# n_estimators - stabla u šumi (više stabala = stabilniji model, ali duže treniranje) - za manje datasetove max_samples=auto automatski se stavlja
iso = IsolationForest(n_estimators=1000, contamination=0.15, random_state=42, max_samples=10000)
iso.fit(kw_train_scaled)

# Tune threshold — Youden's J na IF val setu (70/30, ista distribucija kao test)
# Youden J - prag odrđuje granicu kojom klasificiramo anomaly scorove od isolation foresta
# score < prag  →  anomalija (napad)
# score >= prag →  normalno
# Taj prag nije proizvoljan —> pronađen je tako da se isproba 500 mogućih vrijednosti na validacijskom skupu
# i odabere onaj koji daje najbolji balans

# TPR (koliko stvarnih napada uhvatimo)
# TNR (koliko stvarno normalnih ostavimo na miru)
# Formula J = TPR + TNR - 1 nagrađuje prag koji je dobar u oba aspekta istovremeno, ne samo u jednom.
# Nakon što se taj optimalni prag jednom pronađe u treningu, sprema se u if_threshold.pkl i 
# koristi se zatim trajno u produkciji (u detector.py) za svaki novi upit koji stigne bez ponovnog računanja.
val_scores = iso.decision_function(kw_if_val_scaled)
best_thresh, best_j = 0.0, -1.0
for thresh in np.linspace(val_scores.min(), val_scores.max(), 500):
    preds = (val_scores < thresh).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_if_val, preds, labels=[0, 1]).ravel()
    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    tnr = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    j = tpr + tnr - 1 # Youden's J =  Sensitivity + Specificity - 1
    if j > best_j:
        best_j, best_thresh = j, thresh
print(f"Optimal threshold (IF val Youden J={best_j:.4f}): {best_thresh:.4f}")

# Koristi se za:
# Medicinske dijagnoze
# Otkrivanje prijevare
# Identifikaciju neispravnih proizvoda
# Predviđanje kvara opreme
# Procjenu kreditnog rizika

test_scores = iso.decision_function(kw_test_scaled)
iso_test_pred = (test_scores < best_thresh).astype(int)

print("Test:")
print(f" Accuracy        : {accuracy_score(y_if_test, iso_test_pred):.4f}")
print(f" Precision       : {precision_score(y_if_test, iso_test_pred):.4f}")
print(f" Recall          : {recall_score(y_if_test, iso_test_pred):.4f}")
print(f" F1              : {f1_score(y_if_test, iso_test_pred):.4f}")
print(f" ROC-AUC         : {roc_auc_score(y_if_test, iso_test_pred):.4f}")
print(f" Confusion matrix:\n{confusion_matrix(y_if_test, iso_test_pred)}")
elapsed_if = time.time() - start_if
print(f"Vrijeme treninga IF: {int(elapsed_if // 60)}m {int(elapsed_if % 60)}s")

# ============================================================
# Save models
# ============================================================
print("\nSaving models...")
with open(os.path.join(MODELS_DIR, "vectorizer.pkl"), "wb") as f:
    pickle.dump(vectorizer, f)
with open(os.path.join(MODELS_DIR, "random_forest.pkl"), "wb") as f:
    pickle.dump(rf, f)
with open(os.path.join(MODELS_DIR, "isolation_forest.pkl"), "wb") as f:
    pickle.dump(iso, f)
with open(os.path.join(MODELS_DIR, "scaler.pkl"), "wb") as f:
    pickle.dump(scaler, f)
with open(os.path.join(MODELS_DIR, "sql_keywords.pkl"), "wb") as f:
    pickle.dump(SQL_KEYWORDS, f)
with open(os.path.join(MODELS_DIR, "if_threshold.pkl"), "wb") as f:
    pickle.dump(best_thresh, f)







# ============================================================
# Visualizations
# ============================================================

# 0a. Confusion matrix — Random Forest
fig, ax = plt.subplots(figsize=(6, 5))
ConfusionMatrixDisplay.from_predictions(y_test, test_pred, display_labels=["Normal", "SQLi"], cmap="Blues", ax=ax)
ax.set_title("Random Forest — Confusion Matrix")
fig.savefig(os.path.join(PLOTS_DIR, "rf_confusion_matrix.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/rf_confusion_matrix.png")

# 0b. Confusion matrix — Isolation Forest
fig, ax = plt.subplots(figsize=(6, 5))
ConfusionMatrixDisplay.from_predictions(y_if_test, iso_test_pred,display_labels=["Normal", "SQLi"],cmap="Oranges", ax=ax)
ax.set_title("Isolation Forest — Confusion Matrix")
fig.savefig(os.path.join(PLOTS_DIR, "if_confusion_matrix.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/if_confusion_matrix.png")

# 0c. ROC krivulja — oba modela
fig, ax = plt.subplots(figsize=(8, 6))
# RF ROC
rf_proba_test = rf.predict_proba(X_test_vec)[:, 1]
fpr_rf, tpr_rf, _ = roc_curve(y_test, rf_proba_test)
auc_rf = auc(fpr_rf, tpr_rf)
ax.plot(fpr_rf, tpr_rf, color="steelblue", linewidth=2, label=f"Random Forest (AUC = {auc_rf:.4f})")
# IF ROC
if_scores_neg = -iso.decision_function(kw_test_scaled)
fpr_if, tpr_if, _ = roc_curve(y_if_test, if_scores_neg)
auc_if = auc(fpr_if, tpr_if)
ax.plot(fpr_if, tpr_if, color="tomato", linewidth=2, label=f"Isolation Forest (AUC = {auc_if:.4f})")

ax.set_xlabel("False Positive Rate")
ax.set_ylabel("True Positive Rate")
ax.set_title("ROC krivulja — Random Forest vs Isolation Forest")
ax.legend(loc="lower right")
ax.grid(alpha=0.3)
fig.savefig(os.path.join(PLOTS_DIR, "roc_curve.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/roc_curve.png")

# 0d. Feature importance — Random Forest (grupirano po SQL riječima)
importances = rf.feature_importances_
feature_names = vectorizer.get_feature_names_out()

# Mapiranje n-grama na čitljive SQL koncepte
SQL_GROUPS = [
    ("information_schema", ["information_schema", "nformation_sch", "nfo", "info", "ormation"]),
    ("union",              ["union", "unio", "nion", " uni", "on s"]),
    ("select",             ["select", "selec", "elect", " sel"]),
    ("--  (komentar)",     ["-- ", ")--", " --", "---", "' --"]),
    ("/*  (komentar)",     ["/*", " /*", "*/"]),
    ("or '1'='1",          ["or '", "r '1", "'1'=", "1'='", "'='1"]),
    ("sleep / waitfor",    ["sleep", "leep", "waitfor", "wait"]),
    ("drop",               ["drop ", "drop", "rop t"]),
    ("insert",             ["insert", "nsert", "inser"]),
    ("update",             ["update", "pdate", "updat"]),
    ("delete",             ["delete", "elete", "delet"]),
    ("exec / execute",     ["exec", "xec ", "execu", "ecutе"]),
    ("0x  (hex)",          ["0x", ",0x", " 0x", "0x3"]),
    ("char(",              ["char(", "har(", "char"]),
    ("concat(",            ["concat", "oncat", "conca"]),
    ("group_concat",       ["group_concat", "roup_", "_conc"]),
    ("version()",          ["version", "ersio", "ersion"]),
    ("database()",         ["database", "ataba", "datab"]),
    ("null",               ["null", "nul", " nul"]),
    ("mid / substr",       ["mid", " mid", "substr", "ubstr"]),
]

def best_group_importance(groups, feature_names, importances):
    name_to_imp = dict(zip(feature_names, importances))
    result = []
    for label, fragments in groups:
        total = sum(name_to_imp.get(f, 0.0) for f in fragments)
        result.append((label, total))
    result.sort(key=lambda x: x[1], reverse=True)
    return result

grouped = best_group_importance(SQL_GROUPS, feature_names, importances)
labels_rf = [g[0] for g in grouped]
values_rf = [g[1] for g in grouped]

fig, ax = plt.subplots(figsize=(10, 7))
bars = ax.barh(range(len(labels_rf)), values_rf[::-1], color="steelblue", alpha=0.8)
ax.set_yticks(range(len(labels_rf)))
ax.set_yticklabels(labels_rf[::-1], fontsize=10)
ax.set_xlabel("Grupirana važnost feature-a (suma n-grama)")
ax.set_title("Random Forest — Važnost SQL koncepata (TF-IDF char n-gram)")
ax.grid(axis="x", alpha=0.3)
fig.savefig(os.path.join(PLOTS_DIR, "rf_feature_importance.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/rf_feature_importance.png")

# 0e. Feature importance — Isolation Forest (keyword features)
IF_FEATURE_NAMES = (
    [kw if len(kw) <= 20 else kw[:18] + "…" for kw in SQL_KEYWORDS] +
    ["apostrofi (')", "jednako (=)", "točka-zarez (;)", "zagrada (", "zagrada )",
     "hash (#)", "backtick (`)", "gustoća znamenki", "gustoća spec. znakova",
     "duljina upita", "flag: dugi upit", "zarezi (,)", "neparni apostrofi",
     "crtice (--)", "komentar (/*)", "hex (0x)", "nebalansirane zagrade",
     "dvostruki navodnici", "hex/unicode escape", "tautologija (1=1)",
     "nejednakosti (!=,<=,>=)", "gustoća apostrofa/duljini",
     "SELECT/UNION + komentar", "OR/AND + apostrofi + uvjet"]
)

# Korelacija svake IF featura s labelom na test setu
kw_test_unscaled = keyword_features(X_if_test.tolist())
correlations = np.array([
    abs(np.corrcoef(kw_test_unscaled[:, j], np.array(y_if_test))[0, 1])
    for j in range(kw_test_unscaled.shape[1])
])
correlations = np.nan_to_num(correlations)

top_if_idx = np.argsort(correlations)[-20:][::-1]
fig, ax = plt.subplots(figsize=(10, 7))
ax.barh(range(20), correlations[top_if_idx][::-1], color="tomato", alpha=0.8)
ax.set_yticks(range(20))
ax.set_yticklabels([IF_FEATURE_NAMES[i] for i in top_if_idx[::-1]], fontsize=10)
ax.set_xlabel("Korelacija s labelom (|r|)")
ax.set_title("Isolation Forest — Važnost keyword feature-a")
ax.grid(axis="x", alpha=0.3)
fig.savefig(os.path.join(PLOTS_DIR, "if_feature_importance.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/if_feature_importance.png")

# 1. Decision tree from Random Forest (depth=3 for readability)
fig, ax = plt.subplots(figsize=(24, 8))
plot_tree(rf.estimators_[0],max_depth=3,feature_names=vectorizer.get_feature_names_out(),class_names=["Normal", "SQLi"],filled=True,fontsize=7,ax=ax)
ax.set_title("Random Forest — Decision Tree (depth=3)", fontsize=14)
fig.savefig(os.path.join(PLOTS_DIR, "decision_tree.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/decision_tree.png")

# 2. Isolation Forest anomaly score distribution
scores = iso.decision_function(kw_test_scaled)
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(scores[y_if_test == 0], bins=60, alpha=0.6, label="Normal", color="steelblue")
ax.hist(scores[y_if_test == 1], bins=60, alpha=0.6, label="SQLi", color="tomato")
ax.axvline(x=best_thresh, color="black", linestyle="--", label=f"Threshold ({best_thresh:.4f})")
ax.set_xlabel("Anomaly Score")
ax.set_ylabel("Count")
ax.set_title("Isolation Forest — Anomaly Score Distribution")
ax.legend()
fig.savefig(os.path.join(PLOTS_DIR, "isolation_forest_scores.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/isolation_forest_scores.png")

# 2b. 3D anomaly score distribution
bins = 40
score_min, score_max = scores.min(), scores.max()
edges = np.linspace(score_min, score_max, bins + 1)
centers = (edges[:-1] + edges[1:]) / 2
width = (score_max - score_min) / bins * 0.4

counts_normal = np.histogram(scores[np.array(y_if_test) == 0], bins=edges)[0]
counts_sqli   = np.histogram(scores[np.array(y_if_test) == 1], bins=edges)[0]

fig = plt.figure(figsize=(13, 8))
ax3 = fig.add_subplot(111, projection="3d")
ax3.bar(centers, counts_normal, zs=0, zdir="y", width=width,color="steelblue", alpha=0.7, label="Normal")
ax3.bar(centers, counts_sqli,   zs=1, zdir="y", width=width, color="tomato",    alpha=0.7, label="SQLi")
ax3.axvline(x=best_thresh, color="red", linestyle="--", linewidth=1.5)
ax3.set_xlabel("Anomaly score")
ax3.set_ylabel("Klasa")
ax3.set_zlabel("Broj uzoraka")
ax3.set_yticks([0, 1])
ax3.set_yticklabels(["Normal", "SQLi"])
ax3.set_title("Isolation Forest — 3D distribucija anomaly score-a")
ax3.legend()
fig.savefig(os.path.join(PLOTS_DIR, "isolation_forest_scores_3d.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/isolation_forest_scores_3d.png")

# 3. Precision-Recall krivulja — IF
fig, ax = plt.subplots(figsize=(8, 6))

rf_proba_test_pr = rf.predict_proba(X_test_vec)[:, 1]
prec_rf, rec_rf, _ = precision_recall_curve(y_test, rf_proba_test_pr)
ap_rf = average_precision_score(y_test, rf_proba_test_pr)
ax.plot(rec_rf, prec_rf, color="steelblue", linewidth=2, label=f"Random Forest (AP = {ap_rf:.4f})")

if_scores_pr = -iso.decision_function(kw_test_scaled)
prec_if, rec_if, _ = precision_recall_curve(y_if_test, if_scores_pr)
ap_if = average_precision_score(y_if_test, if_scores_pr)
ax.plot(rec_if, prec_if, color="tomato", linewidth=2, label=f"Isolation Forest (AP = {ap_if:.4f})")

ax.set_xlabel("Recall")
ax.set_ylabel("Precision")
ax.set_title("Precision-Recall krivulja — Random Forest vs Isolation Forest")
ax.legend(loc="lower left")
ax.grid(alpha=0.3)
fig.savefig(os.path.join(PLOTS_DIR, "precision_recall_curve.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/precision_recall_curve.png")

# 4a. Korelacijska matrica — top 20 keyword featura po korelaciji s labelom
kw_test_unscaled_corr = keyword_features(X_if_test.tolist())
correlations_all = np.array([
    abs(np.corrcoef(kw_test_unscaled_corr[:, j], np.array(y_if_test))[0, 1])
    for j in range(kw_test_unscaled_corr.shape[1])
])
correlations_all = np.nan_to_num(correlations_all)
top20_idx = np.argsort(correlations_all)[-20:][::-1]

top20_data = kw_test_unscaled_corr[:, top20_idx]
top20_names = [IF_FEATURE_NAMES[i] for i in top20_idx]

corr_matrix_20 = np.corrcoef(top20_data.T)
fig, ax = plt.subplots(figsize=(14, 12))
sns.heatmap(corr_matrix_20,xticklabels=top20_names,yticklabels=top20_names,annot=True, fmt=".2f", annot_kws={"size": 7},cmap="RdYlGn", center=0, vmin=-1, vmax=1,ax=ax, linewidths=0.3)
ax.set_title("Korelacijska matrica — top 20 keyword featura")
plt.xticks(rotation=45, ha="right", fontsize=8)
plt.yticks(rotation=0, fontsize=8)
fig.savefig(os.path.join(PLOTS_DIR, "corr_matrix_top20.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/corr_matrix_top20.png")

# 4b. Korelacijska matrica — samo numeričkih 24 featura
n_kw_plot = len(SQL_KEYWORDS)
numeric_data = kw_test_unscaled_corr[:, n_kw_plot:]
numeric_names = [
    "apostrofi (')", "jednako (=)", "točka-zarez (;)", "zagrada (", "zagrada )",
    "hash (#)", "backtick (`)", "gustoća znamenki", "gustoća spec. znakova",
    "duljina upita", "flag: dugi upit", "zarezi (,)", "neparni apostrofi",
    "crtice (--)", "komentar (/*)", "hex (0x)", "nebal. zagrade",
    "dvostruki nav.", "hex/unicode esc.", "tautologija (1=1)",
    "nejednakosti", "gustoća apost./dulj.",
    "SELECT/UNION+komen.", "OR/AND+apost.+uvjet"
]

corr_matrix_24 = np.corrcoef(numeric_data.T)
fig, ax = plt.subplots(figsize=(16, 14))
sns.heatmap(corr_matrix_24,xticklabels=numeric_names,yticklabels=numeric_names,annot=True, fmt=".2f", annot_kws={"size": 7},cmap="RdYlGn", center=0, vmin=-1, vmax=1,ax=ax, linewidths=0.3)
ax.set_title("Korelacijska matrica — 24 numerička featura")
plt.xticks(rotation=45, ha="right", fontsize=8)
plt.yticks(rotation=0, fontsize=8)
fig.savefig(os.path.join(PLOTS_DIR, "corr_matrix_numeric24.png"), dpi=120, bbox_inches="tight")
plt.close(fig)
print("Saved: plots/corr_matrix_numeric24.png")

#Izracun vremena trajanja treninga i evaluacije
elapsed = time.time() - start
print(f"\nUkupno vrijeme treninga: {int(elapsed // 60)}m {int(elapsed % 60)}s")

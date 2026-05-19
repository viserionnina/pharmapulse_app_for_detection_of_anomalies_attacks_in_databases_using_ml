import pandas as pd
import numpy as np
import pickle
import os
import time
import scipy.sparse as sp

import matplotlib
matplotlib.use("Agg") #postavlja backend za renderiranje grafova bez potrebe za GUI (za server okruženje)
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D as _Axes3D  # noqa: F401

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.tree import plot_tree
from sklearn.metrics import ConfusionMatrixDisplay, classification_report, accuracy_score,precision_score, recall_score, f1_score,  roc_auc_score,confusion_matrix, precision_recall_curve, average_precision_score, roc_curve, auc
from sklearn.model_selection import train_test_split
import seaborn as sns

SQL_KEYWORDS = [
    # Osnovne SQL naredbe
    "select", "union", "insert", "update", "delete", "drop", "truncate",
    "create", "alter", "exec", "execute", "cast", "convert", "declare",
    # Time-based
    "waitfor", "benchmark", "sleep", "pg_sleep", "delay",
    # Boolean-based
    "or 1=1", "or '1'='1", "and 1=1", "' or ", "\" or ",
    "case when", "if(", "ifnull(", "isnull(",
    # Union-based
    "union select", "union all select", "group_concat", "concat(",
    "table_name", "column_name", "database(", "version(",
    # Error-based
    "extractvalue", "updatexml", "floor(rand(", "exp(",
    "geometrycollection(", "multipoint(",
    # Informacijske tablice
    "information_schema", "sys.tables", "sys.columns", "pg_tables",
    "xp_", "@@version", "@@datadir",
    # Komentari i terminatori
    "--", "/*", "*/", "' #", "\" #",",",";","' ;","' --",
    # Ostalo
    "having", "group by", "order by", "limit ",
    "char(", "0x", "@@", "hex(", "unhex(", "ascii(", "substring(",
    "load_file", "outfile", "null", "regexp", "like 0x",
    "schema(", "user(", "current_user", "session_user",
    # Dodatne funkcije
    "exists", "rand(", "length(", "count(",
    "substr(", "mid(",
]

#double hyphen -> --
# As long as injected SQL code is syntactically correct, 
# tampering can't be detected programmatically. 

#Analiza dataseta:

#Feature                          Normal       SQLi  SQLi/Normal
#--------------------------------------------------------------
#komentar /*                      0.0000     0.9572      9572.0x
#crtice --                        0.0000     0.6152      5127.3x
#0x hex                           0.0006     0.6350       862.5x
#information_schema               0.0007     0.4479       574.0x
#sleep                            0.0000     0.0636       473.7x
#1=1                              0.0000     0.0050        49.5x
#neparni apostrofi                0.0063     0.1357        21.0x
#null                             0.0612     0.5088         8.3x
#union                            0.0922     0.4733         5.1x
#specijalni znakovi (avg)        22.4248    73.8283         3.3x
#duljina (avg chars)            170.9960   418.4098         2.4x
#apostrofi                        0.9853     1.5711         1.6x
#točka-zarez ;                    0.5831     0.5253         0.9x
#char(                            0.0000     0.0000         0.3x

# Feature Engineering — pomaganje modelu da "shvati" domenu u kojoj radi
def keyword_features(queries):  #prima listu SQL upita kao stringove
    q_lower = [q.lower() for q in queries] #pretvare sve upite u mala slova radi lakšeg pretraživanja ključnih riječi
    nb_keywords = len(SQL_KEYWORDS) #broj klj. rijeci u SQL_KEYWORDS listi = 84 za offsert
    n_extra = 24 #broj dodatnih numeričkih feature-a (broj apostrofa, duljina upita, gustoća specijalnih znakova itd.)
    
    mat = np.zeros((len(queries), nb_keywords + n_extra), dtype=np.float32) #kreira matricu nula, svaki red je jedan upit, ukupno 108 stupaca (84 + 24)
    
    for i, q in enumerate(q_lower): #prolazi kroz svaki upit i popunjava feature matricu
        length = max(len(q), 1) #velicina upita max(...,1) da se izbjegne dijeljenje s nulom kod gustoće znakova

        # Keyword count features (koliko puta se pojavljuje keyword npr. union, sleep,... , ne samo 0/1)
        for j, kw in enumerate(SQL_KEYWORDS):
            cnt = q.count(kw)
            if cnt > 0:
                mat[i, j] = min(cnt, 5) / 5.0 #broj pojavljivanja keyworda, ograničeno na 5 (više od 5 pojavljivanja ne daje dodatnu informaciju, a normalizira se na [0,1])

        # Numeričke feature
        n_quotes = q.count("'") #broj apostrofa (SQLi često koristi neparne apostrofe za zatvaranje stringova)
        n_dquotes = q.count('"') #broj dvostrukih navodnika (također se koristi u SQLi, ali rjeđe od apostrofa)
        n_equals = q.count("=") #broj znakova jednakosti (SQLi često koristi uvjete poput 1=1, 'a'='a', itd.)
        n_semi = q.count(";")  #broj točka-zarez (SQLi ponekad koristi ; za terminiranje jednog upita i pokretanje drugog)
        n_open = q.count("(") #broj otvorenih zagrada (SQLi često koristi funkcije i podupite s time povećava broj zagrada)
        n_close = q.count(")") #broj zatvorenih zagrada 
        n_hash = q.count("#") #broj hash znakova (SQLi koristi # za komentare, posebno u MySQL-u)
        n_dash = q.count("--") #broj dvostrukih crtice (SQLi koristi -- za komentare)
        n_special = sum(1 for c in q if not c.isalnum() and c != " ") #broj specijalnih znakova (ne alfanumeričkih i ne razmaka), SQLi upiti imaju znatno više specijalnih znakova od normalnih upita

        # Popunjavanje feature matrice dodatnim numeričkim feature-ima, normalizirano na [0,1] ili kao flag
        mat[i, nb_keywords] = min(n_quotes,  20) / 20.0                 # apostrofi
        mat[i, nb_keywords + 1] = min(n_equals,  20) / 20.0             # =
        mat[i, nb_keywords + 2] = min(n_semi,    10) / 10.0             # ;
        mat[i, nb_keywords + 3] = min(n_open,    10) / 10.0             # (
        mat[i, nb_keywords + 4] = min(n_close,   10) / 10.0             # )
        mat[i, nb_keywords + 5] = min(n_hash,    10) / 10.0             # #
        mat[i, nb_keywords + 6] = min(q.count("`"), 10) / 10.0          # backtick
        mat[i, nb_keywords + 7] = sum(c.isdigit() for c in q) / length  # gustoća znamenki
        mat[i, nb_keywords + 8] = min(n_special / length, 1.0)          # gustoća spec. znakova (3x viša u SQLi)
        mat[i, nb_keywords + 9] = min(length, 2000) / 2000.0            # duljina (SQLi 2.4x duži)
        mat[i, nb_keywords + 10] = float(length > 300)                  # flag: jako dugi upit (SQLi avg=418)
        mat[i, nb_keywords + 11] = min(q.count(","), 20) / 20.0         # zarezi
        mat[i, nb_keywords + 12] = n_quotes % 2                         # neparni apostrofi (21x u SQLi)
        mat[i, nb_keywords + 13] = min(n_dash, 10) / 10.0               # -- komentari (5127x u SQLi)
        mat[i, nb_keywords + 14] = min(q.count("/*"), 10) / 10.0        # /* komentari (9572x u SQLi)
        mat[i, nb_keywords + 15] = min(q.count("0x"), 10) / 10.0        # 0x hex (862x u SQLi)
        mat[i, nb_keywords + 16] = min(abs(n_open - n_close), 5) / 5.0  # nebalansirane zagrade
        mat[i, nb_keywords + 17] = min(n_dquotes, 10) / 10.0            # dvostruki navodnici
        mat[i, nb_keywords + 18] = min(q.count("\\x") + q.count("\\u"), 10) / 10.0  # hex/unicode escape
        mat[i, nb_keywords + 19] = float("1=1" in q or "a=a" in q or "'1'='1'" in q or "1 = 1" in q)  # identity (49x)
        mat[i, nb_keywords + 20] = min(q.count("!=") + q.count("<=") + q.count(">="), 10) / 10.0 # broji koliko puta relacijski operator poput >=, se pojavljuju
        mat[i, nb_keywords + 21] = min(n_quotes / length * 50, 1.0)      # gustoća apostrofa po duljini
        mat[i, nb_keywords + 22] = float(("select" in q or "union" in q) and ("--" in q or "#" in q or "/*" in q))        # SQL + komentar (UNION/comment injekcija)
        mat[i, nb_keywords + 23] = float(("or" in q or "and" in q) and n_quotes >= 2 and ("=" in q or "like" in q))       # OR/AND + navodnici + uvjet (tautologija)
    return mat

# mjanjamo ovdje za svaki dataset
DS_NAME = "DS6"

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
df_main = pd.read_csv(os.path.join(DATASET_DIR, "dataset_clean.csv"), low_memory=False) #low_memory=False da se izbjegnu warningi o miješanju tipova u stupcima, iako to može povećati memorijsku potrošnju ali pouzdanije za veliki dataset
print(f"Glavni dataset: {len(df_main):,} redova")

# Supervised RF: svi legitimni (train split) + svi SQLi (test split)
sql_legit_pool = df_main[(df_main["split"] == "train") & (df_main["label"] == 0)] # DS6
sqli_pool  = df_main[(df_main["split"] == "test")  & (df_main["label"] == 1)] # DS6
df_rf_supervised = pd.concat([sql_legit_pool, sqli_pool]).sample(frac=1, random_state=42).reset_index(drop=True) #spajamo u jedan dataset i miješamo redoslijed (shuffle) da ne bi model naučio da su prvi redovi legit, a zadnji SQLi

X_rf_supervised, y_rf_supervised = df_rf_supervised["full_query"], df_rf_supervised["label"] #ulazni podaci i labele za nadzirano učenje RF modela
X_train, X_tmp, y_train, y_tmp = train_test_split(X_rf_supervised, y_rf_supervised, test_size=0.2, random_state=42, stratify=y_rf_supervised) #80% za trening, 20% za privremeni skup (koji ćemo onda podijeliti na val i test)
X_val, X_test, y_val, y_test = train_test_split(X_tmp, y_tmp, test_size=0.5, random_state=42, stratify=y_tmp)  #10% val, 10% test (od ukupnog skupa) — stratify da se održi ista distribucija klasa u svim splitovima

print(f"Supervised - Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")
print(f"Class distribution (train): {y_train.value_counts().to_dict()}")

# IF: samo label=0 queriji iz train splita, BEZ labela — nenadzirano
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
print(f"IF val: {len(X_if_val)} (20/10 za threshold tuning)")

# ============================================================
# 1. RANDOM FOREST (nadzirano učenje)
# ============================================================
# --- TF-IDF ---
print("\nFitting TF-IDF vectorizer: ")
vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), max_features=50000, sublinear_tf=True) # duži n-grami mogu bolje uhvatiti union select, drop table itd.
X_train_vec = vectorizer.fit_transform(X_train)
X_val_vec = vectorizer.transform(X_val)
X_test_vec = vectorizer.transform(X_test)

print("\n--- Random Forest ---")
start_rf = time.time()
rf = RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=42)
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

scaler = StandardScaler()
kw_train_scaled = scaler.fit_transform(kw_if_train)
kw_if_val_scaled = scaler.transform(kw_if_val)
kw_test_scaled  = scaler.transform(kw_if_test)

# Contamination = 0.15 (pretpostavka da ~15% upita u produkciji može biti napad)
# n_estimators - stabla u šumi (više stabala = stabilniji model, ali duže treniranje) - za manje datasetove max_samples=auto
iso = IsolationForest(n_estimators=1000, contamination=0.15, random_state=42, max_samples=10000)
iso.fit(kw_train_scaled)

# Tune threshold — Youden's J na IF val setu (70/30, ista distribucija kao test)
val_scores = iso.decision_function(kw_if_val_scaled)
best_thresh, best_j = 0.0, -1.0
for thresh in np.linspace(val_scores.min(), val_scores.max(), 500):
    preds = (val_scores < thresh).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_if_val, preds, labels=[0, 1]).ravel()
    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    tnr = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    j = tpr + tnr - 1 # Youden's J = 2 *Sensitivity + Specificity - 1
    if j > best_j:
        best_j, best_thresh = j, thresh
print(f"Optimal threshold (IF val Youden J={best_j:.4f}): {best_thresh:.4f}")

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

# Korelacija svake IF featura s labelom na test setu (point-biserial ≈ pearson za binarni y)
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

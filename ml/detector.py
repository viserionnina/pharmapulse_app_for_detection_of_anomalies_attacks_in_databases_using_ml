import os
import pickle
import numpy as np

MODELS_DIR = os.path.join(os.path.dirname(__file__), "datasets", "models", "DS6")

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
    "--", "/*", "*/", "' #", "\" #", ",", ";", "' ;", "' --",
    # Ostalo
    "having", "group by", "order by", "limit ",
    "char(", "0x", "@@", "hex(", "unhex(", "ascii(", "substring(",
    "load_file", "outfile", "null", "regexp", "like 0x",
    "schema(", "user(", "current_user", "session_user",
    # Dodatne funkcije
    "exists", "rand(", "length(", "count(",
    "substr(", "mid(",
]


def keyword_features(queries):
    q_lower = [q.lower() for q in queries]
    n_kw = len(SQL_KEYWORDS)
    n_extra = 24
    mat = np.zeros((len(queries), n_kw + n_extra), dtype=np.float32)
    for i, q in enumerate(q_lower):
        length = max(len(q), 1)

        for j, kw in enumerate(SQL_KEYWORDS):
            cnt = q.count(kw)
            if cnt > 0:
                mat[i, j] = min(cnt, 5) / 5.0

        n_quotes  = q.count("'")
        n_dquotes = q.count('"')
        n_equals  = q.count("=")
        n_semi    = q.count(";")
        n_open    = q.count("(")
        n_close   = q.count(")")
        n_hash    = q.count("#")
        n_dash    = q.count("--")
        n_special = sum(1 for c in q if not c.isalnum() and c != " ")

        mat[i, n_kw]      = min(n_quotes,  20) / 20.0
        mat[i, n_kw + 1]  = min(n_equals,  20) / 20.0
        mat[i, n_kw + 2]  = min(n_semi,    10) / 10.0
        mat[i, n_kw + 3]  = min(n_open,    20) / 20.0
        mat[i, n_kw + 4]  = min(n_close,   20) / 20.0
        mat[i, n_kw + 5]  = min(n_hash,    10) / 10.0
        mat[i, n_kw + 6]  = min(q.count("`"), 10) / 10.0
        mat[i, n_kw + 7]  = sum(c.isdigit() for c in q) / length
        mat[i, n_kw + 8]  = min(n_special / length, 1.0)
        mat[i, n_kw + 9]  = min(length, 2000) / 2000.0
        mat[i, n_kw + 10] = float(length > 300)
        mat[i, n_kw + 11] = min(q.count(","), 20) / 20.0
        mat[i, n_kw + 12] = n_quotes % 2
        mat[i, n_kw + 13] = min(n_dash, 10) / 10.0
        mat[i, n_kw + 14] = min(q.count("/*"), 10) / 10.0
        mat[i, n_kw + 15] = min(q.count("0x"), 10) / 10.0
        mat[i, n_kw + 16] = min(abs(n_open - n_close), 5) / 5.0
        mat[i, n_kw + 17] = min(n_dquotes, 10) / 10.0
        mat[i, n_kw + 18] = min(q.count("\\x") + q.count("\\u"), 10) / 10.0
        mat[i, n_kw + 19] = float("1=1" in q or "a=a" in q or "'1'='1'" in q or "1 = 1" in q)
        mat[i, n_kw + 20] = min(q.count("!=") + q.count("<=") + q.count(">="), 10) / 10.0
        mat[i, n_kw + 21] = min(n_quotes / length * 50, 1.0)
        mat[i, n_kw + 22] = float(("select" in q or "union" in q) and
                                   ("--" in q or "#" in q or "/*" in q))
        mat[i, n_kw + 23] = float(("or" in q or "and" in q) and
                                   n_quotes >= 2 and
                                   ("=" in q or "like" in q))
    return mat


def _load():
    try:
        def _r(name):
            with open(os.path.join(MODELS_DIR, name), "rb") as f:
                return pickle.load(f)
        thresh = _r("if_threshold.pkl")
        return _r("vectorizer.pkl"), _r("random_forest.pkl"), _r("isolation_forest.pkl"), _r("scaler.pkl"), thresh
    except Exception as e:
        print(f"[ML] Modeli nisu učitani: {e}")
        return None, None, None, None, 0.0


_vectorizer, _rf, _iso, _scaler, _if_threshold = _load()


def detect(sql_query: str, mode: str = "both") -> dict:
    if _rf is None:
        return {"rf_pred": None, "if_pred": None, "detected": False, "mode": mode}

    rf_pred, rf_proba, if_pred, if_score, if_proba = None, None, None, None, None

    if mode in ("rf", "both"):
        vec = _vectorizer.transform([sql_query])
        rf_pred = int(_rf.predict(vec)[0])
        rf_proba = float(_rf.predict_proba(vec)[0][1])

    if mode in ("if", "both"):
        kw = keyword_features([sql_query])
        kw_scaled = _scaler.transform(kw)
        if_score = float(_iso.decision_function(kw_scaled)[0])
        if_pred = int(if_score < _if_threshold)
        if_proba = float(1.0 / (1.0 + np.exp(if_score * 20.0)))

    if mode == "none":
        detected = False
    elif mode == "rf":
        detected = bool(rf_proba is not None and rf_proba >= 0.88)
    elif mode == "if":
        detected = bool(if_pred == 1)
    else:  # both
        rf_very_confident = rf_proba is not None and rf_proba >= 0.97
        both_agree = rf_pred == 1 and if_pred == 1 and rf_proba >= 0.55
        detected = bool(rf_very_confident) or bool(both_agree)

    return {
        "rf_pred": rf_pred,
        "rf_proba": round(rf_proba, 4) if rf_proba is not None else None,
        "if_pred": if_pred,
        "if_score": round(if_score, 4) if if_score is not None else None,
        "if_proba": round(if_proba, 4) if if_score is not None else None,
        "detected": detected,
        "mode": mode,
    }

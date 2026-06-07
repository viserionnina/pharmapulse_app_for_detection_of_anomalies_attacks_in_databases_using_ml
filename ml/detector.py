import os
import pickle
import numpy as np
from ml.if_features import keyword_features


MODELS_DIR = os.path.join(os.path.dirname(__file__), "datasets", "models", "DS6")

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
        detected = bool(rf_proba is not None and rf_proba >= 0.55)
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

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
        rf_pred = int(_rf.predict(vec)[0])  #RF predviđa: 0 (legitimno) ili 1 (napad) — to je direktna odluka stabla-glasanja (majority vote svih 100 stabala u šumi).
        #rf_pred je već binarna odluka na pragu 0.5, dok rf_proba je kontinuirana vrijednost (npr. 0.63, 0.97, 0.12...) iz koje je rf_pred izveden.
        rf_proba = float(_rf.predict_proba(vec)[0][1])

    if mode in ("if", "both"):
        kw = keyword_features([sql_query])
        kw_scaled = _scaler.transform(kw)
        if_score = float(_iso.decision_function(kw_scaled)[0])
        if_pred = int(if_score < _if_threshold) #-0.25 < -0.04? → True → 1 anomalija
        if_proba = float(1.0 / (1.0 + np.exp(if_score * 20.0))) # sigmoid function za pretvorbu u postotak
        # Faktor 20 odabran je empirijski, na temelju opaženog raspona anomaly scoreova koje Isolation Forest model proizvodi 
        # (tipično između -0.3 i 0.15). Budući da je taj raspon uzakbez skaliranja vjerojatnosti su previše zgurane i zato množenjem
        # s 20.0 dobivamo širi raspon i bolje razdvajanje vjerojatnosti između legitimnih i anomalnih upita.
    
    if mode == "none":
        detected = False
    elif mode == "rf":
        detected = bool(rf_pred == 1 and rf_proba >= 0.70)
    elif mode == "if":
        detected = bool(if_pred == 1)
    else:  # both
        # Oba modela se slažu da je napad
        both_agree = rf_pred == 1 and if_pred == 1
        # RF kaže napad, IF se ne slaže — RF nadjačava samo ako je vrlo siguran
        rf_overrides = rf_pred == 1 and if_pred == 0 and rf_proba is not None and rf_proba >= 0.70
        # IF kaže anomalija, RF se ne slaže — IF nadjačava samo ako je vrlo siguran
        if_overrides = rf_pred == 0 and if_pred == 1 and if_proba is not None and if_proba >= 0.80
        detected = bool(both_agree) or bool(rf_overrides) or bool(if_overrides)

    return {
        "rf_pred": rf_pred,
        "rf_proba": round(rf_proba, 4) if rf_proba is not None else None,
        "if_pred": if_pred,
        "if_score": round(if_score, 4) if if_score is not None else None,
        "if_proba": round(if_proba, 4) if if_score is not None else None,
        "detected": detected,
        "mode": mode,
    }

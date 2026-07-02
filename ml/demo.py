from ml.detector import detect

# admin' -- u username polju (klasicni bypass), lozinka bilo sta
tests = {
  "samo input_u string":         "admin' OR '1'='1",
  "samo input_p string":         "lozinka",
  "cijeli upit:":                "SELECT * FROM users WHERE username='admin' OR '1'='1' AND password='lozinka'",
}

for label, q in tests.items():
    r = detect(q, mode='both')
    rf_p = r['rf_proba']; 
    if_p = r['if_proba']
    rf_pct = f'{rf_p*100:.1f}%' if rf_p is not None else '—'
    if_pct = f'{if_p*100:.1f}%' if if_p is not None else '—'
    print(f'{label}:')
    print(f'   upit: {q}')
    print(f'   RF: predikcija={r["rf_pred"]}, pouzdanost={rf_pct}')
    print(f'   IF: predikcija={r["if_pred"]}, pouzdanost={if_pct}')
    print()
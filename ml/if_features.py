import numpy as np

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
        mat[i, nb_keywords] = min(n_quotes,  20) / 20.0                 # apostrofi '
        mat[i, nb_keywords + 1] = min(n_equals,  20) / 20.0             # =
        mat[i, nb_keywords + 2] = min(n_semi,    10) / 10.0             # ;
        mat[i, nb_keywords + 3] = min(n_open,    10) / 10.0             # (
        mat[i, nb_keywords + 4] = min(n_close,   10) / 10.0             # )
        mat[i, nb_keywords + 5] = min(n_hash,    10) / 10.0             # #
        mat[i, nb_keywords + 6] = min(q.count("`"), 10) / 10.0          # backtick
        mat[i, nb_keywords + 7] = sum(c.isdigit() for c in q) / length  # gustoća znamenki
        mat[i, nb_keywords + 8] = min(n_special / length, 1.0)          # gustoća spec. znakova 
        mat[i, nb_keywords + 9] = min(length, 2000) / 2000.0            # duljina 
        mat[i, nb_keywords + 10] = float(length > 300)                  # flag: jako dugi upit 
        mat[i, nb_keywords + 11] = min(q.count(","), 20) / 20.0         # zarezi
        mat[i, nb_keywords + 12] = n_quotes % 2                         # neparni apostrofi 
        mat[i, nb_keywords + 13] = min(n_dash, 10) / 10.0               # -- komentari 
        mat[i, nb_keywords + 14] = min(q.count("/*"), 10) / 10.0        # /* komentari 
        mat[i, nb_keywords + 15] = min(q.count("0x"), 10) / 10.0        # 0x hex 
        mat[i, nb_keywords + 16] = min(abs(n_open - n_close), 5) / 5.0  # nebalansirane zagrade
        mat[i, nb_keywords + 17] = min(n_dquotes, 10) / 10.0            # dvostruki navodnici
        mat[i, nb_keywords + 18] = min(q.count("\\x") + q.count("\\u"), 10) / 10.0  # hex/unicode escape
        mat[i, nb_keywords + 19] = float("1=1" in q or "a=a" in q or "'1'='1'" in q or "1 = 1" in q)  # provjerava da li postoji true uvjet (tautologija) koji je čest u SQLi napadima
        mat[i, nb_keywords + 20] = min(q.count("!=") + q.count("<=") + q.count(">="), 10) / 10.0 # broji koliko puta relacijski operator poput >=, se pojavljuju
        mat[i, nb_keywords + 21] = min(n_quotes / length * 50, 1.0)      # gustoća apostrofa po duljini
        mat[i, nb_keywords + 22] = float(("select" in q or "union" in q) and ("--" in q or "#" in q or "/*" in q))        # SQL + komentar (UNION/comment injekcija)
        mat[i, nb_keywords + 23] = float(("or" in q or "and" in q) and n_quotes >= 2 and ("=" in q or "like" in q))       # OR/AND + navodnici + uvjet (tautologija)
    return mat

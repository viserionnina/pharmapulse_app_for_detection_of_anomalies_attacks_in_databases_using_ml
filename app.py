import os
import re
from dotenv import load_dotenv
load_dotenv()
from datetime import timedelta, datetime
from dataclasses import dataclass
from typing import List, Optional

from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_mysqldb import MySQL
import MySQLdb.cursors

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
    UserMixin,
)
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, IntegerField
from wtforms.validators import DataRequired, Length, NumberRange, Optional as Opt, InputRequired, Email
from wtforms.fields import DateField
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
from functools import wraps
#uploads
from werkzeug.utils import secure_filename
from flask_wtf.file import FileField, FileAllowed
import uuid
from ml.detector import detect as ml_detect

# --- App Setup ---
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=7)

# --- MySQL config ---
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "localhost")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER", "root")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "00000000")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB", "pharmapulse")
app.config["MYSQL_CURSORCLASS"] = "DictCursor"
# app.config["MYSQL_CLIENT_FLAG"] = "CLIENT.MULTI_STATEMENTS"

mysql = MySQL(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
app.config["WTF_CSRF_ENABLED"] = False  # SAMO ZA DEMO
csrf = CSRFProtect(app)

# Uploads (admin product images)
app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads")
#app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4MB
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "svg"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


#ya cart
@app.context_processor
def inject_cart_count():
    c = 0
    if getattr(current_user, "is_authenticated", False):
        try:
            c = cart_count(int(current_user.id))
        except Exception:
            c = 0
    return {"cart_count": c}


# --- models ---
@dataclass
class BrandView:
    id: int
    name: str
    logo_url: Optional[str] = None


@dataclass
class ProductView:
    id: int
    name: str
    price_cents: int
    description: str
    image_url: str
    prescription_required: bool
    created_at: Optional[datetime] = None
    is_recommended: bool = False
    is_on_sale: bool = False
    sale_price_cents: Optional[int] = None
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None
    stock_qty: int = 0
    is_active: bool = True


    def current_price_cents(self) -> int:
        # akcijska cijena vrijedi samo ako je ON i nije NULL/0
        if self.is_on_sale and self.sale_price_cents is not None and int(self.sale_price_cents) > 0:
            return int(self.sale_price_cents)
        return int(self.price_cents)


@dataclass
class CartItemView:
    product: ProductView
    quantity: int


@dataclass
class OrderItemView:
    product: ProductView
    quantity: int
    price_cents_snapshot: int


@dataclass
class OrderView:
    id: int
    created_at: datetime
    items: List[OrderItemView]
    status: Optional[str] = None

    shipping_full_name: Optional[str] = None
    shipping_phone: Optional[str] = None
    shipping_line1: Optional[str] = None
    shipping_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_postal_code: Optional[str] = None
    shipping_country: Optional[str] = None

    def total_cents(self) -> int:
        return sum(it.price_cents_snapshot * it.quantity for it in self.items)



# --- Auth user for Flask-Login ---
class User(UserMixin):
    def __init__(self, id: int, username: str, password_hash: str, is_admin: int = 0):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = int(is_admin or 0)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)

class ProfileForm(FlaskForm):
    full_name = StringField("Full name", validators=[Opt(), Length(max=120)])
    phone = StringField("Phone", validators=[Opt(), Length(max=40)])
    email = StringField("Email", validators=[Opt(), Length(max=255), Email()])
    country = StringField("Country", validators=[Opt(), Length(max=80)])
    postal_code = StringField("Postal code", validators=[Opt(), Length(max=20)])
    date_of_birth = DateField("Datum rođenja", format="%d-%m-%Y", validators=[Opt()])

class AddressForm(FlaskForm):
    full_name = StringField("Full name", validators=[Opt(), Length(max=120)])
    phone = StringField("Phone", validators=[Opt(), Length(max=40)])
    line1 = StringField("Address line 1", validators=[DataRequired(), Length(max=200)])
    line2 = StringField("Address line 2", validators=[Opt(), Length(max=200)])
    city = StringField("City", validators=[DataRequired(), Length(max=120)])
    postal_code = StringField("Postal code", validators=[DataRequired(), Length(max=20)])
    country = StringField("Country", validators=[DataRequired(), Length(max=80)])


class AdminProductForm(FlaskForm):
    name = StringField("Naziv", validators=[InputRequired(), Length(max=120)])
    description = StringField("Opis", validators=[InputRequired(), Length(max=500)])

    price_cents = IntegerField("Cijena (centi)",
        validators=[InputRequired(), NumberRange(min=0, max=10_000_000)]
    )
    sale_price_cents = IntegerField("Akcijska cijena (centi)",
        validators=[Opt(), NumberRange(min=0, max=10_000_000)]
    )

    image_url = StringField("Slika URL ili static path", validators=[Opt(), Length(max=400)])
    image_file = FileField("Upload slike", validators=[FileAllowed(list(ALLOWED_IMAGE_EXTS))])

    prescription_required = IntegerField("Recept (0/1)",
        validators=[InputRequired(), NumberRange(min=0, max=1)]
    )
    is_recommended = IntegerField("Preporuka (0/1)",
        validators=[InputRequired(), NumberRange(min=0, max=1)]
    )
    is_on_sale = IntegerField("Akcija (0/1)",
        validators=[InputRequired(), NumberRange(min=0, max=1)]
    )
    stock_qty = IntegerField("Zaliha",
        validators=[InputRequired(), NumberRange(min=0, max=1_000_000)]
    )
    is_active = IntegerField("Aktivan (0/1)",
        validators=[InputRequired(), NumberRange(min=0, max=1)]
    )

    brand_id = IntegerField("Brand ID", validators=[Opt(), NumberRange(min=1, max=1_000_000)])


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9čćđšž\s-]", "", s, flags=re.IGNORECASE)
    s = s.replace(" ", "-")
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def db_cursor():
    return mysql.connection.cursor(MySQLdb.cursors.DictCursor)


def fetch_user_by_id(user_id: int) -> Optional[dict]:
    cur = db_cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE id=%s", (user_id,))
    return cur.fetchone()

def fetch_user_by_username(username: str) -> Optional[dict]:
    cur = db_cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s", (username,))
    return cur.fetchone()


def fetch_categories_all() -> list:
    cur = db_cursor()
    cur.execute("""
        SELECT id, name, slug, parent_id
        FROM categories
        ORDER BY id ASC, name
    """)
    return cur.fetchall() or []

def fetch_category_by_slug(slug: str) -> Optional[dict]:
    cur = db_cursor()
    cur.execute("SELECT id, name, slug, parent_id FROM categories WHERE slug=%s", (slug,))
    return cur.fetchone()

def fetch_categories_for_product(product_id: int) -> list:
    cur = db_cursor()
    cur.execute("""
        SELECT c.id, c.name, c.slug
        FROM product_categories pc
        JOIN categories c ON c.id = pc.category_id
        WHERE pc.product_id = %s
        ORDER BY c.name
    """, (product_id,))
    return cur.fetchall() or []

def fetch_category_ids_for_product(product_id: int) -> set:
    cur = db_cursor()
    cur.execute("SELECT category_id FROM product_categories WHERE product_id=%s", (product_id,))
    return {int(r["category_id"]) for r in (cur.fetchall() or [])}

def fetch_related_products(product_id: int, limit: int = 6) -> List[ProductView]:
    """proizvodi iz istih kategorija kao trenutni, bez trenutnog proizvoda."""
    cur = db_cursor()
    cur.execute("""
        SELECT DISTINCT
               p.id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required,
               p.created_at, p.is_recommended, p.is_on_sale, p.sale_price_cents,
               p.brand_id, p.stock_qty, p.is_active,
               b.name AS brand_name
        FROM product_categories pc
        JOIN product_categories pc2 ON pc2.category_id = pc.category_id
        JOIN products p ON p.id = pc2.product_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE pc.product_id = %s
          AND p.id <> %s
          AND p.is_active = 1
        ORDER BY p.is_recommended DESC, p.created_at DESC, p.id DESC
        LIMIT %s
    """, (product_id, product_id, limit))

    rows = cur.fetchall() or []
    return [
        ProductView(
            id=r["id"],
            name=r["name"],
            price_cents=int(r["price_cents"]),
            description=r.get("description") or "",
            image_url=r.get("image_url") or "",
            prescription_required=bool(r.get("prescription_required", 0)),
            created_at=r.get("created_at"),
            is_recommended=bool(r.get("is_recommended", 0)),
            is_on_sale=bool(r.get("is_on_sale", 0)),
            sale_price_cents=(int(r["sale_price_cents"]) if r.get("sale_price_cents") is not None else None),
            brand_id=r.get("brand_id"),
            brand_name=r.get("brand_name"),
            stock_qty=int(r.get("stock_qty") or 0),
            is_active=bool(r.get("is_active", 1)),
        )
        for r in rows
    ]

def cart_count(user_id: int) -> int:
    cur = db_cursor()
    cur.execute("SELECT COALESCE(SUM(quantity), 0) AS c FROM cart_items WHERE user_id=%s", (user_id,))
    return int((cur.fetchone() or {}).get("c", 0))
    


@login_manager.user_loader
def load_user(user_id):
    row = fetch_user_by_id(int(user_id))
    if row:
        return User(row["id"], row["username"], row["password_hash"], row.get("is_admin", 0))
    return None


# --- Forms ---
class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=128)])


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class AddToCartForm(FlaskForm):
    quantity = IntegerField("Qty", default=1, validators=[DataRequired(), NumberRange(min=1, max=99)])


class ClearCartForm(FlaskForm):
    pass


class CheckoutForm(FlaskForm):
    pass


# --- Detektiranje SQLi taulogije ---
SQLI_TAUTOLOGY_PATTERNS = [
    r"""(?i)'\s*or\s*'1'\s*=\s*'1""",
    r"""(?i)'\s*or\s*1\s*=\s*1""",
    r"""(?i)'\s*or\s*'x'\s*=\s*'x""",
    r"""(?i)'\s*or\s*'a'\s*=\s*'a""",
    r"""(?i)'\s*or\s*exists\s*\(\s*select""",
    r"""(?i)\bor\b\s*1\s*=\s*1""",
    r"""(?i)\bor\b\s*'1'\s*=\s*'1'""",
    r"""(?i)'\s*--""",
    r"""(?i)'\s"""
]

# Trigger za ML: ' praćen SQL operatorom/terminatorom = pravi injection signal.
# Sama trailing ' (npr. "password'") nije napad i ne aktivira ML.
_SQLI_TRIGGER_RE = re.compile(
    r"'[^']*(?:--|/\*|;|\b(?:or|and|union|select|drop|insert|update|delete|exec|cast|convert|having|group|order)\b)"
    r"|--|/\*",
    re.IGNORECASE
)

def is_allowed_image(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTS

def save_uploaded_image(file_storage) -> str:
    """
    Sprema sliku u static/uploads i vraća putanju relativno na static,
    npr. 'uploads/abc123.webp'
    """
    original = secure_filename(file_storage.filename or "")
    if not is_allowed_image(original):
        raise ValueError("Nedozvoljen format slike.")

    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    abs_path = os.path.join(app.config["UPLOAD_FOLDER"], new_name)
    file_storage.save(abs_path)
    return f"uploads/{new_name}"

def image_src(image_url: str) -> str:
    """
    Ako je URL (http/https) -> vrati ga direktno,
    inače pretpostavi da je relative path u static/ i vrati url_for.
    """
    s = (image_url or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return url_for("static", filename=s)

def admin_set_product_categories(product_id: int, category_ids: list[int]) -> None:
    ids = []
    for x in category_ids:
        try:
            ids.append(int(x))
        except Exception:
            pass
    ids = sorted(set([i for i in ids if i > 0]))

    cur = db_cursor()
    cur.execute("DELETE FROM product_categories WHERE product_id=%s", (product_id,))
    if ids:
        cur.executemany(
            "INSERT IGNORE INTO product_categories (product_id, category_id) VALUES (%s, %s)",
            [(product_id, cid) for cid in ids],
        )
    mysql.connection.commit()



def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if int(getattr(current_user, "is_admin", 0)) != 1:
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def looks_like_sqli_tautology(s: str) -> bool:
    return any(re.search(p, s or "") for p in SQLI_TAUTOLOGY_PATTERNS)

def admin_stats():
    cur = db_cursor()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    users = (cur.fetchone() or {}).get("c", 0)

    cur.execute("SELECT COUNT(*) AS c FROM orders")
    orders_total = (cur.fetchone() or {}).get("c", 0)

    cur.execute("SELECT COUNT(*) AS c FROM orders WHERE status='pending'")
    orders_pending = (cur.fetchone() or {}).get("c", 0)

    cur.execute("""
        SELECT COUNT(*) AS c
        FROM products
        WHERE is_active=1 AND stock_qty <= 0
    """)
    products_oos = (cur.fetchone() or {}).get("c", 0)

    return {
        "users": users,
        "orders_total": orders_total,
        "orders_pending": orders_pending,
        "products_oos": products_oos,
    }


def admin_out_of_stock_products(limit=50):
    cur = db_cursor()
    cur.execute("""
        SELECT id, name, stock_qty
        FROM products
        WHERE is_active=1 AND stock_qty <= 0
        ORDER BY name
        LIMIT %s
    """, (limit,))
    return cur.fetchall() or []

def admin_create_product(data: dict) -> int:
    cur = db_cursor()
    cur.execute("""
        INSERT INTO products
        (name, price_cents, description, image_url, prescription_required,
         created_at, is_recommended, is_on_sale, sale_price_cents,
         brand_id, stock_qty, is_active)
        VALUES (%s,%s,%s,%s,%s, NOW(), %s,%s,%s, %s,%s,%s)
    """, (
        data["name"], data["price_cents"], data["description"], data["image_url"], data["prescription_required"],
        data["is_recommended"], data["is_on_sale"], data["sale_price_cents"],
        data["brand_id"], data["stock_qty"], data["is_active"]
    ))
    mysql.connection.commit()
    return int(cur.lastrowid)

def admin_update_product(product_id: int, data: dict) -> bool:
    cur = db_cursor()
    cur.execute("""
        UPDATE products SET
          name=%s,
          price_cents=%s,
          description=%s,
          image_url=%s,
          prescription_required=%s,
          is_recommended=%s,
          is_on_sale=%s,
          sale_price_cents=%s,
          brand_id=%s,
          stock_qty=%s,
          is_active=%s
        WHERE id=%s
    """, (
        data["name"], data["price_cents"], data["description"], data["image_url"], data["prescription_required"],
        data["is_recommended"], data["is_on_sale"], data["sale_price_cents"],
        data["brand_id"], data["stock_qty"], data["is_active"],
        product_id
    ))
    mysql.connection.commit()
    return cur.rowcount == 1

def admin_fetch_product_row(product_id: int) -> Optional[dict]:
    cur = db_cursor()
    cur.execute("""
        SELECT id, name, price_cents, description, image_url, prescription_required,
               is_recommended, is_on_sale, sale_price_cents, brand_id, stock_qty, is_active
        FROM products
        WHERE id=%s
    """, (product_id,))
    return cur.fetchone()

def admin_fetch_all_categories() -> list:
    cur = db_cursor()
    cur.execute("""
        SELECT id, name, slug, parent_id
        FROM categories
        ORDER BY COALESCE(parent_id, 0), name
    """)
    return cur.fetchall() or []


def set_product_categories(product_id: int, category_ids: list[int]) -> None:
    # očisti + upiši ponovno (najjednostavnije i pouzdano)
    cleaned = []
    for x in category_ids or []:
        try:
            cleaned.append(int(x))
        except Exception:
            pass
    cleaned = sorted(set([c for c in cleaned if c > 0]))

    cur = db_cursor()
    cur.execute("DELETE FROM product_categories WHERE product_id=%s", (product_id,))
    if cleaned:
        cur.executemany(
            "INSERT INTO product_categories (product_id, category_id) VALUES (%s, %s)",
            [(product_id, cid) for cid in cleaned],
        )
    mysql.connection.commit()


def admin_hard_delete_product(product_id: int) -> bool:
    cur = db_cursor()

    # prvo obriš iz cart_items i order_items ako postoje
    cur.execute("DELETE FROM cart_items WHERE product_id=%s", (product_id,))
    cur.execute("DELETE FROM order_items WHERE product_id=%s", (product_id,))

    # onda proizvod
    cur.execute("DELETE FROM products WHERE id=%s", (product_id,))
    mysql.connection.commit()
    return cur.rowcount == 1

def admin_fetch_users(limit: int = 500) -> list:
    cur = db_cursor()
    cur.execute("""
        SELECT
            u.id,
            u.username,
            up.full_name,
            up.phone,
            up.email,
            up.date_of_birth,
            a.line1, a.line2, a.city,
            a.postal_code AS a_postal_code,
            a.country AS a_country
        FROM users u
        LEFT JOIN user_profiles up ON up.user_id = u.id
        LEFT JOIN addresses a ON a.user_id = u.id AND a.is_default = 1
        WHERE u.id IS NOT NULL AND u.id > 0
        ORDER BY u.id ASC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall() or []

    from datetime import date, datetime

    for r in rows:
        dob = r.get("date_of_birth")
        age = None
        if dob:
            if isinstance(dob, datetime):
                dob = dob.date()
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        r["age"] = age

        addr_parts = []
        if r.get("line1"):
            addr_parts.append(r["line1"])
        if r.get("line2"):
            addr_parts.append(r["line2"])
        city_line = f"{r.get('a_postal_code') or ''} {r.get('city') or ''}".strip()
        if city_line:
            addr_parts.append(city_line)
        if r.get("a_country"):
            addr_parts.append(r["a_country"])

        r["default_address"] = ", ".join([p for p in addr_parts if p]) or "-"

    return rows



def fetch_profile(user_id: int) -> dict:
    cur = db_cursor()
    cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT IGNORE INTO user_profiles (user_id) VALUES (%s)", (user_id,))
        mysql.connection.commit()
        cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
    return row or {}

def upsert_profile(user_id: int, full_name, phone, email, country, postal_code, date_of_birth) -> None:
    cur = db_cursor()
    cur.execute("""
        INSERT INTO user_profiles (user_id, full_name, phone, email, country, postal_code, date_of_birth)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          full_name=VALUES(full_name),
          phone=VALUES(phone),
          email=VALUES(email),
          country=VALUES(country),
          postal_code=VALUES(postal_code),
          date_of_birth=VALUES(date_of_birth)
    """, (user_id, full_name, phone, email, country, postal_code, date_of_birth))
    mysql.connection.commit()


def fetch_addresses(user_id: int) -> list:
    cur = db_cursor()
    cur.execute("""
        SELECT * FROM addresses
        WHERE user_id=%s
        ORDER BY is_default DESC, id DESC
    """, (user_id,))
    return cur.fetchall() or []

def add_address(user_id: int, data: dict) -> None:
    cur = db_cursor()

    # ako je prva adresa -> default
    cur.execute("SELECT COUNT(*) AS c FROM addresses WHERE user_id=%s", (user_id,))
    first = (cur.fetchone() or {}).get("c", 0) == 0

    if first:
        cur.execute("UPDATE addresses SET is_default=0 WHERE user_id=%s", (user_id,))

    cur.execute("""
        INSERT INTO addresses
        (user_id, full_name, phone, line1, line2, city, postal_code, country, is_default)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        user_id,
        data.get("full_name"),
        data.get("phone"),
        data["line1"],
        data.get("line2"),
        data["city"],
        data["postal_code"],
        data["country"],
        1 if first else 0
    ))
    mysql.connection.commit()

def set_default_address(user_id: int, address_id: int) -> None:
    cur = db_cursor()
    cur.execute("UPDATE addresses SET is_default=0 WHERE user_id=%s", (user_id,))
    cur.execute("UPDATE addresses SET is_default=1 WHERE user_id=%s AND id=%s", (user_id, address_id))
    mysql.connection.commit()


def fetch_brands(limit: int = 50) -> List[BrandView]:
    cur = db_cursor()
    cur.execute("""
        SELECT id, name, logo_url
        FROM brands
        WHERE is_active = 1
        ORDER BY sort_order ASC, id ASC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall() or []
    return [BrandView(id=r["id"], name=r["name"], logo_url=r.get("logo_url")) for r in rows]


# --- DB fetch helpers ---
def fetch_product(product_id: int) -> Optional[ProductView]:
    cur = db_cursor()
    cur.execute("""
        SELECT p.id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required,
               p.created_at, p.is_recommended, p.is_on_sale, p.sale_price_cents,
               p.brand_id, p.stock_qty, p.is_active,
               b.name AS brand_name
        FROM products p
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id=%s AND p.is_active=1
    """, (product_id,))
    r = cur.fetchone()
    if not r:
        return None

    return ProductView(
        id=r["id"],
        name=r["name"],
        price_cents=int(r["price_cents"]),
        description=r["description"],
        image_url=r["image_url"],
        prescription_required=bool(r["prescription_required"]),
        created_at=r.get("created_at"),
        is_recommended=bool(r.get("is_recommended", 0)),
        is_on_sale=bool(r.get("is_on_sale", 0)),
        sale_price_cents=(int(r["sale_price_cents"]) if r.get("sale_price_cents") is not None else None),

        brand_id=r.get("brand_id"),
        brand_name=r.get("brand_name"),
        stock_qty=int(r.get("stock_qty") or 0),
        is_active=bool(r.get("is_active", 1)),
    )


def fetch_products() -> List[ProductView]:
    cur = db_cursor()
    cur.execute("""
        SELECT p.id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required,
               p.created_at, p.is_recommended, p.is_on_sale, p.sale_price_cents,
               p.brand_id, p.stock_qty, p.is_active,
               b.name AS brand_name
        FROM products p
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.is_active = 1
        ORDER BY p.name
    """)
    rows = cur.fetchall() or []
    return [
        ProductView(
            id=r["id"],
            name=r["name"],
            price_cents=int(r["price_cents"]),
            description=r["description"],
            image_url=r["image_url"],
            prescription_required=bool(r["prescription_required"]),
            created_at=r.get("created_at"),
            is_recommended=bool(r.get("is_recommended", 0)),
            is_on_sale=bool(r.get("is_on_sale", 0)),
            sale_price_cents=(int(r["sale_price_cents"]) if r.get("sale_price_cents") is not None else None),

            brand_id=r.get("brand_id"),
            brand_name=r.get("brand_name"),
            stock_qty=int(r.get("stock_qty") or 0),
            is_active=bool(r.get("is_active", 1)),
        )
        for r in rows
    ]



def fetch_home_tab_products(tab: str, limit: int, offset: int) -> List[ProductView]:
    tab = (tab or "").lower()
    cur = db_cursor()

    base_select = """
        SELECT p.id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required,
               p.created_at, p.is_recommended, p.is_on_sale, p.sale_price_cents,
               p.brand_id, p.stock_qty, p.is_active,
               b.name AS brand_name
        FROM products p
        LEFT JOIN brands b ON b.id = p.brand_id
    """

    if tab == "new":
        sql = base_select + """
            WHERE p.is_active = 1
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %s OFFSET %s
        """
        params = (limit, offset)

    elif tab == "recommended":
        sql = base_select + """
            WHERE p.is_recommended = 1
            AND p.is_active = 1 
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %s OFFSET %s
        """
        params = (limit, offset)

    elif tab == "sale":
        sql = base_select + """
            WHERE p.is_on_sale = 1
            AND p.is_active = 1 
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %s OFFSET %s
        """
        params = (limit, offset)

    else:
        return []

    cur.execute(sql, params)
    rows = cur.fetchall() or []

    out: List[ProductView] = []
    for r in rows:
        out.append(
            ProductView(
                id=r["id"],
                name=r["name"],
                price_cents=int(r["price_cents"]),
                description=r["description"],
                image_url=r["image_url"],
                prescription_required=bool(r["prescription_required"]),
                created_at=r.get("created_at"),
                is_recommended=bool(r.get("is_recommended", 0)),
                is_on_sale=bool(r.get("is_on_sale", 0)),
                sale_price_cents=(int(r["sale_price_cents"]) if r.get("sale_price_cents") is not None else None),

                brand_id=r.get("brand_id"),
                brand_name=r.get("brand_name"),
                stock_qty=int(r.get("stock_qty") or 0),
                is_active=bool(r.get("is_active", 1)),
            )
        )

    return out



def fetch_cart_items(user_id: int) -> List[CartItemView]:
    cur = db_cursor()
    cur.execute("""
        SELECT ci.quantity,
               p.id AS product_id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required,
               p.created_at, p.is_recommended, p.is_on_sale, p.sale_price_cents
        FROM cart_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.user_id = %s
        ORDER BY p.name
    """, (user_id,))
    rows = cur.fetchall() or []

    items: List[CartItemView] = []
    for r in rows:
        p = ProductView(
            id=r["product_id"],
            name=r["name"],
            price_cents=int(r["price_cents"]),
            description=r["description"],
            image_url=r["image_url"],
            prescription_required=bool(r["prescription_required"]),
            created_at=r.get("created_at"),
            is_recommended=bool(r.get("is_recommended", 0)),
            is_on_sale=bool(r.get("is_on_sale", 0)),
            sale_price_cents=(int(r["sale_price_cents"]) if r.get("sale_price_cents") is not None else None),
        )
        items.append(CartItemView(product=p, quantity=int(r["quantity"])))
    return items


def remove_cart_item(user_id: int, product_id: int) -> bool:
    cur = db_cursor()
    cur.execute(
        "DELETE FROM cart_items WHERE user_id=%s AND product_id=%s",
        (user_id, product_id),
    )
    mysql.connection.commit()
    return cur.rowcount == 1

def clear_cart(user_id: int) -> None:
    cur = db_cursor()
    cur.execute("DELETE FROM cart_items WHERE user_id=%s", (user_id,))
    mysql.connection.commit()


def add_cart_item(user_id: int, product_id: int, qty: int) -> None:
    cur = db_cursor()
    # unique (user_id, product_id) -> upsert ponašanje
    cur.execute("SELECT id, quantity FROM cart_items WHERE user_id=%s AND product_id=%s", (user_id, product_id))
    row = cur.fetchone()
    if row:
        new_qty = min(int(row["quantity"]) + qty, 99)
        cur.execute("UPDATE cart_items SET quantity=%s WHERE id=%s", (new_qty, row["id"]))
    else:
        cur.execute(
            "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)",
            (user_id, product_id, min(qty, 99)),
        )
    mysql.connection.commit()

def fetch_default_address(user_id: int) -> Optional[dict]:
    cur = db_cursor()
    cur.execute("""
        SELECT *
        FROM addresses
        WHERE user_id=%s AND is_default=1
        LIMIT 1
    """, (user_id,))
    return cur.fetchone()


def create_order_from_cart(user_id: int) -> Optional[int]:
    items = fetch_cart_items(user_id)
    if not items:
        return None

    addr = fetch_default_address(user_id)
    prof = fetch_profile(user_id)

    if not addr:
        return None  # nema default adrese -> blokiraj

    now = datetime.utcnow()
    shipping_cents = 0
    discount_cents = 0
    subtotal_cents = sum(it.product.current_price_cents() * it.quantity for it in items)
    total_cents = max(0, subtotal_cents + shipping_cents - discount_cents)

    cur = db_cursor()

    try:
        mysql.connection.begin()

        # 1) PROVJERI I SKINI STOCK
        for it in items:
            needed = int(it.quantity)
            cur.execute("""
                UPDATE products
                SET stock_qty = stock_qty - %s
                WHERE id=%s AND is_active=1 AND stock_qty >= %s
            """, (needed, it.product.id, needed))

            if cur.rowcount != 1:
                mysql.connection.rollback()
                return None  # nema dovoljno zalihe

        # 2) INSERT ORDER + snapshot shipping iz profila + adrese
        cur.execute("""
            INSERT INTO orders (
              created_at, user_id, status, total_cents, shipping_cents, discount_cents,
              shipping_full_name, shipping_phone,
              shipping_line1, shipping_line2, shipping_city, shipping_postal_code, shipping_country
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            now, user_id, "pending", total_cents, shipping_cents, discount_cents,
            (prof.get("full_name") or None),
            (prof.get("phone") or None),
            addr.get("line1"), addr.get("line2"), addr.get("city"),
            addr.get("postal_code"), addr.get("country"),
        ))
        order_id = cur.lastrowid

        # 3) INSERT ORDER ITEMS
        for it in items:
            unit_price = it.product.current_price_cents()
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price_cents_snapshot)
                VALUES (%s, %s, %s, %s)
            """, (order_id, it.product.id, int(it.quantity), int(unit_price)))

        # 4) CLEAR CART
        cur.execute("DELETE FROM cart_items WHERE user_id=%s", (user_id,))
        mysql.connection.commit()
        return int(order_id)

    except Exception:
        mysql.connection.rollback()
        raise

def admin_update_order_status(order_id: int, status: str) -> bool:
    allowed = {"pending", "approved", "shipped", "cancelled"}
    if status not in allowed:
        return False
    cur = db_cursor()
    cur.execute("UPDATE orders SET status=%s WHERE id=%s", (status, order_id))
    mysql.connection.commit()
    return cur.rowcount == 1

def admin_set_stock(product_id: int, new_qty: int) -> bool:
    new_qty = max(0, int(new_qty))
    cur = db_cursor()
    cur.execute("UPDATE products SET stock_qty=%s WHERE id=%s", (new_qty, product_id))
    mysql.connection.commit()
    return cur.rowcount == 1

def admin_fetch_carts(limit_users: int = 200) -> list:
    cur = db_cursor()
    cur.execute("""
        SELECT
            u.id AS user_id,
            u.username,
            COALESCE(up.full_name, '') AS full_name,
            COALESCE(up.email, '') AS email,
            COUNT(ci.id) AS line_count,
            COALESCE(SUM(ci.quantity), 0) AS total_qty
        FROM users u
        JOIN cart_items ci ON ci.user_id = u.id
        LEFT JOIN user_profiles up ON up.user_id = u.id
        WHERE u.id IS NOT NULL AND u.id > 0
        GROUP BY u.id, u.username, up.full_name, up.email
        ORDER BY total_qty DESC, u.id ASC
        LIMIT %s
    """, (limit_users,))
    return cur.fetchall() or []


def fetch_orders(user_id: int) -> List[OrderView]:
    cur = db_cursor()
    cur.execute("""
    SELECT id, created_at, status,
           shipping_full_name, shipping_phone, shipping_line1, shipping_line2,
           shipping_city, shipping_postal_code, shipping_country
    FROM orders
    WHERE user_id=%s
    ORDER BY created_at DESC
    """, (user_id,))


    order_rows = cur.fetchall() or []

    orders: List[OrderView] = []
    for o in order_rows:
        order_id = o["id"]
        cur2 = db_cursor()
        cur2.execute("""
            SELECT oi.quantity, oi.price_cents_snapshot,
                   p.id AS product_id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = %s
            ORDER BY p.name
        """, (order_id,))
        item_rows = cur2.fetchall() or []
        items: List[OrderItemView] = []
        for r in item_rows:
            p = ProductView(
                id=r["product_id"],
                name=r["name"],
                price_cents=int(r["price_cents"]),
                description=r["description"],
                image_url=r["image_url"],
                prescription_required=bool(r["prescription_required"]),
            )
            items.append(
                OrderItemView(
                    product=p,
                    quantity=int(r["quantity"]),
                    price_cents_snapshot=int(r["price_cents_snapshot"]),
                )
            )
        orders.append(OrderView(
            id=int(order_id),
            created_at=o["created_at"],
            items=items,
            status=o.get("status"),
            shipping_full_name=o.get("shipping_full_name"),
            shipping_phone=o.get("shipping_phone"),
            shipping_line1=o.get("shipping_line1"),
            shipping_line2=o.get("shipping_line2"),
            shipping_city=o.get("shipping_city"),
            shipping_postal_code=o.get("shipping_postal_code"),
            shipping_country=o.get("shipping_country"),
        ))

    return orders

def log_security_event(event_type, username, payload):
    cur = db_cursor()
    cur.execute("""
        INSERT INTO security_events
        (event_type, username_attempted, payload, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        event_type,
        username,
        payload,
        request.remote_addr,
        request.headers.get("User-Agent")
    ))
    mysql.connection.commit()

def delete_address(user_id: int, address_id: int) -> bool:
    cur = db_cursor()

    # ne daj brisanje default adrese
    cur.execute("SELECT is_default FROM addresses WHERE id=%s AND user_id=%s", (address_id, user_id))
    row = cur.fetchone()
    if not row:
        return False
    if int(row.get("is_default") or 0) == 1:
        return False

    cur.execute("DELETE FROM addresses WHERE id=%s AND user_id=%s", (address_id, user_id))
    mysql.connection.commit()
    return cur.rowcount == 1

def fetch_products_by_category_slug(slug: str) -> List[ProductView]:
    cur = db_cursor()
    cur.execute("""
        SELECT p.id, p.name, p.price_cents, p.description, p.image_url, p.prescription_required,
               p.created_at, p.is_recommended, p.is_on_sale, p.sale_price_cents,
               p.brand_id, p.stock_qty, p.is_active,
               b.name AS brand_name
        FROM products p
        JOIN product_categories pc ON pc.product_id = p.id
        JOIN categories c ON c.id = pc.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE c.slug=%s AND p.is_active=1
        ORDER BY p.name
    """, (slug,))
    rows = cur.fetchall() or []
    return [
        ProductView(
            id=r["id"],
            name=r["name"],
            price_cents=int(r["price_cents"]),
            description=r["description"],
            image_url=r["image_url"],
            prescription_required=bool(r["prescription_required"]),
            created_at=r.get("created_at"),
            is_recommended=bool(r.get("is_recommended", 0)),
            is_on_sale=bool(r.get("is_on_sale", 0)),
            sale_price_cents=(int(r["sale_price_cents"]) if r.get("sale_price_cents") is not None else None),
            brand_id=r.get("brand_id"),
            brand_name=r.get("brand_name"),
            stock_qty=int(r.get("stock_qty") or 0),
            is_active=bool(r.get("is_active", 1)),
        )
        for r in rows
    ]

def fetch_categories_for_product_ids(product_ids):
    """
    Vraća dict: { product_id: [ {id,name,slug}, ... ] }
    """
    if not product_ids:
        return {}

    placeholders = ",".join(["%s"] * len(product_ids))
    cur = db_cursor()
    cur.execute(f"""
        SELECT pc.product_id, c.id, c.name, c.slug
        FROM product_categories pc
        JOIN categories c ON c.id = pc.category_id
        WHERE pc.product_id IN ({placeholders})
        ORDER BY c.name
    """, tuple(product_ids))

    rows = cur.fetchall() or []
    out = {}
    for r in rows:
        pid = int(r["product_id"])
        out.setdefault(pid, []).append({
            "id": int(r["id"]),
            "name": r["name"],
            "slug": r["slug"],
        })
    return out




# --- Routes ---
@app.route("/")
def index():
    per_page = 8

    new_list = fetch_home_tab_products("new", per_page + 1, 0)
    has_more_new = len(new_list) > per_page
    new_list = new_list[:per_page]

    rec_list = fetch_home_tab_products("recommended", per_page + 1, 0)
    has_more_rec = len(rec_list) > per_page
    rec_list = rec_list[:per_page]

    sale_list = fetch_home_tab_products("sale", per_page + 1, 0)
    has_more_sale = len(sale_list) > per_page
    sale_list = sale_list[:per_page]

    brands = fetch_brands(limit=30)

    new_categories_by_product = fetch_categories_for_product_ids([p.id for p in new_list])
    rec_categories_by_product = fetch_categories_for_product_ids([p.id for p in rec_list])
    sale_categories_by_product = fetch_categories_for_product_ids([p.id for p in sale_list])

    return render_template(
        "index.html",
        new_products=new_list,
        rec_products=rec_list,
        sale_products=sale_list,
        has_more_new=has_more_new,
        has_more_rec=has_more_rec,
        has_more_sale=has_more_sale,
        brands=brands,
        new_categories_by_product=new_categories_by_product,
        rec_categories_by_product=rec_categories_by_product,
        sale_categories_by_product=sale_categories_by_product,
    )

@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = admin_fetch_users(limit=500)
    return render_template("admin/users.html", users=users)


@app.route("/admin/orders")
@login_required
@admin_required
def admin_orders():
    cur = db_cursor()
    cur.execute("""
        SELECT id, created_at, user_id, status, total_cents,
               shipping_full_name, shipping_phone, shipping_line1, shipping_line2,
               shipping_city, shipping_postal_code, shipping_country
        FROM orders
        ORDER BY created_at DESC
        LIMIT 200
    """)
    orders = cur.fetchall() or []
    return render_template("admin/orders.html", orders=orders)

@app.post("/admin/orders/<int:order_id>/status")
@login_required
@admin_required
def admin_orders_status(order_id: int):
    status = (request.form.get("status") or "").strip()
    ok = admin_update_order_status(order_id, status)
    flash("Status spremljen." if ok else "Neispravan status.")
    return redirect(url_for("admin_orders"), code=303)

@app.route("/admin/products")
@login_required
@admin_required
def admin_products():
    cur = db_cursor()
    cur.execute("""
        SELECT id, name, price_cents, stock_qty, is_active, is_on_sale, sale_price_cents
        FROM products
        ORDER BY id ASC
        LIMIT 300
    """)
    products = cur.fetchall() or []
    return render_template("admin/products.html", products=products)

@app.route("/admin/products/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_product_new():
    form = AdminProductForm()

    if form.validate_on_submit():
        # 1) slika: upload ima prednost nad URL-om
        img = (form.image_url.data or "").strip()
        if form.image_file.data and getattr(form.image_file.data, "filename", ""):
            try:
                img = save_uploaded_image(form.image_file.data)
            except Exception as e:
                flash(str(e))
                return render_template("admin/product_form.html", form=form, mode="new")

        if not img:
            flash("Moraš staviti sliku (upload ili URL).")
            return render_template("admin/product_form.html", form=form, mode="new")

        data = {
            "name": form.name.data.strip(),
            "description": form.description.data.strip(),
            "price_cents": int(form.price_cents.data or 0),
            "sale_price_cents": (int(form.sale_price_cents.data) if form.sale_price_cents.data is not None else None),
            "image_url": img,
            "prescription_required": int(form.prescription_required.data or 0),
            "is_recommended": int(form.is_recommended.data or 0),
            "is_on_sale": int(form.is_on_sale.data or 0),
            "brand_id": (int(form.brand_id.data) if form.brand_id.data else None),
            "stock_qty": int(form.stock_qty.data or 0),
            "is_active": int(form.is_active.data) if form.is_active.data is not None else 1,

        }

        # ako nije akcija, nuliraj akcijsku cijenu
        if data["is_on_sale"] != 1:
            data["sale_price_cents"] = None

        try:
            pid = admin_create_product(data)
            cat_ids = request.form.getlist("category_ids")
            admin_set_product_categories(pid, cat_ids)
            flash(f"Proizvod dodan (ID {pid}).")
            return redirect(url_for("admin_products"), code=303)
        except MySQLdb.IntegrityError:
            flash("Greška: naziv proizvoda mora biti UNIQUE (već postoji).")
    
    all_categories = fetch_categories_all()
    return render_template("admin/product_form.html", form=form, mode="new", all_categories=all_categories, selected_category_ids=set())


@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_product_edit(product_id: int):
    row = admin_fetch_product_row(product_id)

    all_categories = fetch_categories_all()
    selected_category_ids = fetch_category_ids_for_product(product_id)

    if not row:
        abort(404)

    form = AdminProductForm()

    if request.method == "GET":
        form.name.data = row["name"]
        form.description.data = row["description"]
        form.price_cents.data = int(row["price_cents"] or 0)
        form.sale_price_cents.data = (int(row["sale_price_cents"]) if row["sale_price_cents"] is not None else None)
        form.image_url.data = row["image_url"]
        form.prescription_required.data = int(row["prescription_required"] or 0)
        form.is_recommended.data = int(row["is_recommended"] or 0)
        form.is_on_sale.data = int(row["is_on_sale"] or 0)
        form.brand_id.data = (int(row["brand_id"]) if row["brand_id"] else None)
        form.stock_qty.data = int(row["stock_qty"] or 0)
        form.is_active.data = int(row["is_active"]) if row["is_active"] is not None else 1

    if form.validate_on_submit():
        img = (form.image_url.data or "").strip()

        if form.image_file.data and getattr(form.image_file.data, "filename", ""):
            try:
                img = save_uploaded_image(form.image_file.data)
            except Exception as e:
                flash(str(e))
                return render_template("admin/product_form.html", form=form, mode="edit", product_id=product_id)

        if not img:
            flash("Moraš imati sliku (upload ili URL).")
            return render_template("admin/product_form.html", form=form, mode="edit", product_id=product_id)

        data = {
            "name": form.name.data.strip(),
            "description": form.description.data.strip(),
            "price_cents": int(form.price_cents.data or 0),
            "sale_price_cents": (int(form.sale_price_cents.data) if form.sale_price_cents.data is not None else None),
            "image_url": img,
            "prescription_required": int(form.prescription_required.data or 0),
            "is_recommended": int(form.is_recommended.data or 0),
            "is_on_sale": int(form.is_on_sale.data or 0),
            "brand_id": (int(form.brand_id.data) if form.brand_id.data else None),
            "stock_qty": int(form.stock_qty.data or 0),
            "is_active": int(form.is_active.data) if form.is_active.data is not None else 1,
        }

        if data["is_on_sale"] != 1:
            data["sale_price_cents"] = None

        try:
            admin_update_product(product_id, data)
            cat_ids = request.form.getlist("category_ids")
            admin_set_product_categories(product_id, cat_ids)
            flash("Proizvod spremljen.")
            return redirect(url_for("admin_products"), code=303)
        except MySQLdb.IntegrityError:
            flash("Greška: naziv proizvoda mora biti UNIQUE (već postoji).")

    return render_template("admin/product_form.html", form=form, mode="edit", product_id=product_id, all_categories=all_categories, selected_category_ids=selected_category_ids)



@app.post("/admin/products/<int:product_id>/delete")
@login_required
@admin_required
def admin_product_delete(product_id):
    ok = admin_hard_delete_product(product_id)
    flash("Proizvod trajno obrisan." if ok else "Ne mogu obrisati proizvod.")
    return redirect(url_for("admin_products"), code=303)


@app.post("/admin/products/<int:product_id>/stock")
@login_required
@admin_required
def admin_products_stock(product_id: int):
    try:
        qty = int(request.form.get("stock_qty") or "0")
    except ValueError:
        qty = 0
    ok = admin_set_stock(product_id, qty)
    flash("Stock ažuriran." if ok else "Greška kod update-a.")
    return redirect(url_for("admin_products"), code=303)


@app.get("/api/home-products/<tab>")
def api_home_products(tab):
    tab = (tab or "").lower()
    if tab not in ("new", "recommended", "sale"):
        abort(404)

    per_page = 8
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    page = max(page, 1)

    offset = (page - 1) * per_page

    items = fetch_home_tab_products(tab, per_page + 1, offset)
    has_more = len(items) > per_page
    items = items[:per_page]

    categories_by_product = fetch_categories_for_product_ids([p.id for p in items])

    html = render_template(
        "partials/_home_product_cards.html",
        products=items,
        categories_by_product=categories_by_product
    )
    return {"html": html, "has_more": has_more}

@app.route("/admin")
@login_required
@admin_required
def admin_index():
    stats = admin_stats()
    oos = admin_out_of_stock_products()
    return render_template("admin/index.html", stats=stats, oos=oos)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data

        if fetch_user_by_username(username):
            flash("Username already taken.")
            return redirect(url_for("register"), code=303)

        #####################
        pw_hash = generate_password_hash(password, method="pbkdf2:sha256")
        cur = db_cursor()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, pw_hash))
        #####################

        mysql.connection.commit()

        # dohvat id-a
        user_id = cur.lastrowid

        # napravi profil red (prazan)
        cur2 = db_cursor()
        cur2.execute("INSERT IGNORE INTO user_profiles (user_id) VALUES (%s)", (user_id,))
        mysql.connection.commit()


        # auto-login
        row = fetch_user_by_username(username)
        login_user(User(row["id"], row["username"], row["password_hash"]))
        flash("Welcome! Account created.")
        return redirect(url_for("products"), code=303)

    return render_template("register.html", form=form)

# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if current_user.is_authenticated:
#         return redirect(url_for("index"))

#     form = LoginForm()
#     if form.validate_on_submit():
#         username = (form.username.data or "").strip()
#         password = form.password.data or ""

#         # SAMO ranjivi SQL - BEZ fallback-a
#         insecure_sql = f"SELECT * FROM users WHERE username='{username}' AND password_hash='{password}'"

#         cur = db_cursor()
#         try:
#             cur.execute(insecure_sql)
#             row = cur.fetchone()
#         except Exception as e:
#             flash(f"Database error: {str(e)}")
#             return redirect(url_for("login"), code=303)
#         finally:
#             try:
#                 cur.close()
#             except:
#                 pass

#         if row:
#             try:
#                 user_id = int(row.get("id", 0))
#                 if user_id <= 0:
#                     raise ValueError("Invalid ID")
                
#                 user = User(user_id, row["username"], row["password_hash"], row.get("is_admin", 0))
#                 login_user(user, remember=True)
                
#                 if looks_like_sqli_tautology(username) or looks_like_sqli_tautology(password):
#                     try:
#                         log_security_event("SQL_INJECTION_ATTEMPT", username, password)
#                     except:
#                         pass
                
#                 flash("Logged in successfully!")
#                 return redirect(url_for("products"), code=303)
                
#             except (ValueError, TypeError, KeyError):
#                 flash("Login error - invalid data")
#                 return redirect(url_for("login"), code=303)
        
#         # BEZ fallback mehanizma - direktan fail
#         flash("Invalid username or password.")
#         return redirect(url_for("login"), code=303)

#     return render_template("login.html", form=form)

#ORIGINAL:
# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if current_user.is_authenticated:
#         return redirect(url_for("index"))

#     form = LoginForm()
#     if form.validate_on_submit():
#         username = (form.username.data or "").strip()
#         password = form.password.data or ""

#         #insecure query
#         insecure_sql = (
#             f"SELECT * FROM users WHERE username='{username}' AND password_hash='{password}'"
#         )

#         #_ = insecure_sql  # možemo logirati ako želimo
#         #row = fetch_user_by_username(username)

#         #######################
#         cur = db_cursor()
#         try:
#             cur.execute(insecure_sql)   # ← OVDJE je SQL injection
#             row = cur.fetchone()
#         except Exception as e:
#             flash(f"Database error: {str(e)}")
#             return redirect(url_for("login"), code=303)
#         finally:
#             try:
#                 cur.close()  # ← uvijek očisti cursor
#             except:
#                 pass
#         ####################

#         if row:
#             user_id = int(row.get("id", 0))
#             if user_id <= 0:
#                 raise ValueError("Invalid ID")

#             user = User(row["id"], row["username"], row["password_hash"], row.get("is_admin", 0))
#             # simulacija bypassa: ako lozinka izgleda kao tautologija, pusti login
#             # if looks_like_sqli_tautology(password) or user.check_password(password):
#             login_user(user, remember=True)
#             if looks_like_sqli_tautology(username) or looks_like_sqli_tautology(password):
#                 try: 
#                     log_security_event(
#                         event_type="SQL_INJECTION_ATTEMPT",
#                         username=username,
#                         payload=password
#                     )
#                 except Exception as log:
#                     print(f"Warning log failed: {log}")

#             flash("Logged in.")
#             return redirect(url_for("products"), code=303)

#         #######################
#         row = fetch_user_by_username(username)
#         if row:
#             user = User(row["id"], row["username"], row["password_hash"], row.get("is_admin", 0))
#             if user.check_password(password):
#                 login_user(user, remember=True)
#                 flash("Logged in.")
#                 return redirect(url_for("products"), code=303)
#         #######################
        
#         flash("Invalid credentials.")
#         return redirect(url_for("login"), code=303)

#     return render_template("login.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = LoginForm()
    if form.validate_on_submit():
        username = (form.username.data or "").strip()
        password = form.password.data or ""

        insecure_sql = f"SELECT * FROM users WHERE username='{username}' AND password_hash='{password}'"

        # ML detekcija na svakom loginu — RF (nadzirano) + IF (nenadzirano)
        ml_result = ml_detect(insecure_sql)
        if ml_result["detected"]:
            try:
                log_security_event(
                    f"ML_SQLI_DETECTED (RF={ml_result['rf_pred']}, RF_proba={ml_result['rf_proba']}, IF={ml_result['if_pred']}, IF_score={ml_result['if_score']})",
                    username,
                    insecure_sql
                )
            except Exception:
                pass
            return render_template("blocked.html", details=ml_result), 403

        # Pokušaj ranjivog SQL-a; greška (npr. malformiran string zbog ' u lozinki)
        # NE smije ubiti login — pravimo fallback na siguran hash check ispod.
        row = None
        cur = db_cursor()
        try:
            cur.execute(insecure_sql)
            row = cur.fetchone()
        except Exception:
            row = None
        finally:
            try:
                cur.close()
            except Exception:
                pass

        if row:
            username_val = row.get("username") or ""
            password_hash_val = row.get("password_hash") or ""
            try:
                user_id = int(row.get("id") or 0)
            except (ValueError, TypeError):
                user_id = 0

            user = User(user_id, username_val, password_hash_val, row.get("is_admin", 0))
            login_user(user, remember=True)

            flash(f"Welcome, {username_val}!")
            return redirect(url_for("products"), code=303)

        # Fallback za normalne korisnike
        row = fetch_user_by_username(username)
        if row:
            user = User(row["id"], row["username"], row["password_hash"], row.get("is_admin", 0))
            if user.check_password(password):
                login_user(user, remember=True)
                flash("Logged in.")
                return redirect(url_for("products"), code=303)
        
        return render_template("login.html", form=form, login_error=f"Invalid credentials for {username}.")

    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.")
    return redirect(url_for("index"), code=303)


@app.route("/products", methods=["GET"])
def products():
    cat = (request.args.get("cat") or "").strip()   # slug kategorije
    categories = fetch_categories_all()

    if cat:
        prods = fetch_products_by_category_slug(cat)
    else:
        prods = fetch_products()

    categories_by_product = fetch_categories_for_product_ids([p.id for p in prods])

    form = AddToCartForm()
    return render_template(
        "products.html",
        products=prods,
        add_form=form,
        categories=categories,
        active_cat=cat,
        categories_by_product=categories_by_product
    )



@app.route("/admin/categories")
@login_required
@admin_required
def admin_categories():
    cats = fetch_categories_all()
    return render_template("admin/categories.html", categories=cats)

@app.route("/admin/categories/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_category_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        parent_id = request.form.get("parent_id") or None
        slug = slugify(request.form.get("slug") or name)

        if not name or not slug:
            flash("Name i slug su obavezni.")
            return redirect(url_for("admin_category_new"), code=303)

        try:
            pid = int(parent_id) if parent_id else None
        except ValueError:
            pid = None

        cur = db_cursor()
        try:
            cur.execute(
                "INSERT INTO categories (name, slug, parent_id) VALUES (%s,%s,%s)",
                (name, slug, pid),
            )
            mysql.connection.commit()
            flash("Kategorija dodana.")
            return redirect(url_for("admin_categories"), code=303)
        except MySQLdb.IntegrityError:
            flash("Slug mora biti UNIQUE (već postoji).")

    cats = fetch_categories_all()
    return render_template("admin/category_form.html", mode="new", categories=cats, cat=None)
 
@app.route("/admin/categories/<int:cat_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_category_edit(cat_id: int):
    cur = db_cursor()
    cur.execute("SELECT id, name, slug, parent_id FROM categories WHERE id=%s", (cat_id,))
    cat = cur.fetchone()
    if not cat:
        abort(404)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slug = slugify(request.form.get("slug") or name)
        parent_id = request.form.get("parent_id") or None

        try:
            pid = int(parent_id) if parent_id else None
        except ValueError:
            pid = None

        # ne dozvoli da si sam sebi parent
        if pid == cat_id:
            pid = None

        try:
            cur.execute(
                "UPDATE categories SET name=%s, slug=%s, parent_id=%s WHERE id=%s",
                (name, slug, pid, cat_id),
            )
            mysql.connection.commit()
            flash("Kategorija spremljena.")
            return redirect(url_for("admin_categories"), code=303)
        except MySQLdb.IntegrityError:
            flash("Slug mora biti UNIQUE (već postoji).")

    cats = fetch_categories_all()
    return render_template("admin/category_form.html", mode="edit", categories=cats, cat=cat)

@app.post("/admin/categories/<int:cat_id>/delete")
@login_required
@admin_required
def admin_category_delete(cat_id: int):
    cur = db_cursor()
    cur.execute("DELETE FROM categories WHERE id=%s", (cat_id,))
    mysql.connection.commit()
    flash("Kategorija obrisana.")
    return redirect(url_for("admin_categories"), code=303)

@app.route("/admin/carts")
@login_required
@admin_required
def admin_carts():
    carts = admin_fetch_carts()
    return render_template("admin/carts.html", carts=carts)

@app.route("/product/<int:product_id>")
def product_detail(product_id: int):
    product = fetch_product(product_id)
    if not product:
        abort(404)

    product_categories = fetch_categories_for_product(product_id)
    related_products = fetch_related_products(product_id, limit=6)
    form = AddToCartForm()

    return render_template(
        "product_detail.html",
        product=product,
        add_form=form,
        product_categories=product_categories,
        related_products=related_products
    )

@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id: int):
    form = AddToCartForm()
    if not form.validate_on_submit():
        flash(f"Invalid request: {form.errors}")
        return redirect(url_for("products"), code=303)

    product = fetch_product(product_id)
    if not product:
        flash("Product not found.")
        return redirect(url_for("products"), code=303)

    if int(product.stock_qty or 0) <= 0:
        flash("Proizvod je rasprodan (out of stock).")
        return redirect(url_for("products"), code=303)

    qty = int(form.quantity.data or 1)
    qty = max(1, qty)

    # ne daj više od stocka
    max_add = min(qty, int(product.stock_qty))
    add_cart_item(int(current_user.id), product.id, max_add)
    flash("Dodano u košaricu.")

    next_url = (request.form.get("next") or "").strip()
    # sigurnost: dopuštamo samo interne relative URL-ove
    if next_url.startswith("/"):
        return redirect(next_url, code=303)

    return redirect(request.referrer or url_for("products"), code=303)



@app.route("/cart", methods=["GET", "POST"])
@login_required
def cart():
    clear_form = ClearCartForm()
    checkout_form = CheckoutForm()

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "clear_cart" and clear_form.validate_on_submit():
            clear_cart(int(current_user.id))
            flash("Cart cleared.")
            return redirect(url_for("cart"), code=303)

        if action == "remove_item" and clear_form.validate_on_submit():
            try:
                pid = int(request.form.get("product_id") or "0")
            except ValueError:
                pid = 0

            if pid > 0:
                remove_cart_item(int(current_user.id), pid)
                flash("Stavka uklonjena iz košarice.")
            return redirect(url_for("cart"), code=303)

    items = fetch_cart_items(int(current_user.id))
    total_cents = sum(i.product.current_price_cents() * i.quantity for i in items)

    return render_template(
        "cart.html",
        items=items,
        total_cents=total_cents,
        clear_form=clear_form,
        checkout_form=checkout_form
    )

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    form = CheckoutForm()
    if not form.validate_on_submit():
        flash("Invalid checkout request.")
        return redirect(url_for("cart"), code=303)

    order_id = create_order_from_cart(int(current_user.id))
    if not order_id:
        flash("Neuspješno: nema default adrese ili nema dovoljno zalihe za neki proizvod.")
        return redirect(url_for("cart"), code=303)


    # izračun total za flash (ponovno dohvatimo zadnju narudžbu)
    my_orders = fetch_orders(int(current_user.id))
    newest = my_orders[0] if my_orders else None
    total = newest.total_cents() if newest and newest.id == order_id else 0

    VAT_NUM, VAT_DEN = 125, 100
    total_vat = (int(total) * VAT_NUM + (VAT_DEN // 2)) // VAT_DEN

    flash(f"Order #{order_id} placed. Total €{total_vat/100:.2f}")
    return redirect(url_for("orders"), code=303)


@app.route("/orders")
@login_required
def orders():
    my_orders = fetch_orders(int(current_user.id))
    default_address = fetch_default_address(int(current_user.id))
    return render_template("orders.html", orders=my_orders, default_address=default_address)


@app.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    email = (request.form.get("email") or "").strip().lower()
    back = request.referrer or url_for("index")

    # validacija maila
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        flash("Unesite ispravnu email adresu.")
        return redirect(back, code=303)

    cur = db_cursor()

    # upsert-. ako već postoji email ne ruši se, samo javi poruku
    cur.execute(
        """
        INSERT INTO newsletter_subscribers (email, source_url)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE source_url = VALUES(source_url)
        """,
        (email, back),
    )
    mysql.connection.commit()

    if cur.rowcount == 1:
        flash("Hvala! Uspješno ste se prijavili na newsletter.")
    else:
        flash("Već ste prijavljeni na newsletter 🙂")

    return redirect(back, code=303)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    profile_form = ProfileForm()
    address_form = AddressForm()

    # dohvat profila i adresa (treba i za POST, jer ćemo možda popuniti full_name/phone)
    prof = fetch_profile(int(current_user.id))

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "save_profile":
            if profile_form.validate_on_submit():
                upsert_profile(
                    int(current_user.id),
                    profile_form.full_name.data,
                    profile_form.phone.data,
                    profile_form.email.data,
                    profile_form.country.data,
                    profile_form.postal_code.data,
                    profile_form.date_of_birth.data
                )
                flash("Profil spremljen.")
                return redirect(url_for("profile"), code=303)
            else:
                flash(f"Greška u formi profila: {profile_form.errors}")

        elif action == "add_address":
            if address_form.validate_on_submit():
                # Ako ne unoim ime/telefon u adresi uzmi ga iz profila
                data = {
                    "full_name": address_form.full_name.data or prof.get("full_name"),
                    "phone": address_form.phone.data or prof.get("phone"),
                    "line1": address_form.line1.data,
                    "line2": address_form.line2.data,
                    "city": address_form.city.data,
                    "postal_code": address_form.postal_code.data,
                    "country": address_form.country.data,
                }
                add_address(int(current_user.id), data)
                flash("Adresa dodana.")
                return redirect(url_for("profile"), code=303)
            else:
                flash(f"Greška u formi adrese: {address_form.errors}")

        elif action == "set_default_address":
            # CSRF provjera - koristimo token koji šalješ kroz profile_form.hidden_tag())
            if not profile_form.validate_on_submit():
                flash("Neispravan zahtjev (CSRF).")
                return redirect(url_for("profile"), code=303)

            try:
                address_id = int(request.form.get("address_id") or "0")
            except ValueError:
                address_id = 0

            if address_id <= 0:
                flash("Neispravan ID adrese.")
                return redirect(url_for("profile"), code=303)

            set_default_address(int(current_user.id), address_id)
            flash("Default adresa postavljena.")
            return redirect(url_for("profile"), code=303)

        elif action == "delete_address":
            if not profile_form.validate_on_submit():
                flash("Neispravan zahtjev (CSRF).")
                return redirect(url_for("profile"), code=303)

            try:
                address_id = int(request.form.get("address_id") or "0")
            except ValueError:
                address_id = 0

            if address_id <= 0:
                flash("Neispravan ID adrese.")
                return redirect(url_for("profile"), code=303)

            ok = delete_address(int(current_user.id), address_id)
            if ok:
                flash("Adresa obrisana.")
            else:
                flash("Ne možeš obrisati default adresu (ili adresa ne postoji).")
            return redirect(url_for("profile"), code=303)


    # GET (ili nakon POST-a bez redirecta): dohvat adresa
    addrs = fetch_addresses(int(current_user.id))

    # PREFILL radi samo na GET da ne pregazi ono što je user upisao ako forma padne
    if request.method == "GET":
        profile_form.full_name.data = prof.get("full_name") or ""
        profile_form.phone.data = prof.get("phone") or ""
        profile_form.email.data = prof.get("email") or ""
        profile_form.country.data = prof.get("country") or ""
        profile_form.postal_code.data = prof.get("postal_code") or ""
        profile_form.date_of_birth.data = prof.get("date_of_birth")

        # opcionalno: prefill adrese s profila
        address_form.full_name.data = prof.get("full_name") or ""
        address_form.phone.data = prof.get("phone") or ""

    return render_template(
        "profile.html",
        profile_form=profile_form,
        address_form=address_form,
        addresses=addrs,
        profile=prof
    )


if __name__ == "__main__":
    # na Mac-u je 5000 zauzet (Control Center), pa koristim 5001
    app.run(debug=True, host="127.0.0.1", port=5001)

import io
import json
import os
import shutil
import smtplib
import sqlite3
import subprocess
import threading
import time as _time
import urllib.request
from datetime import date
from email.mime.text import MIMEText

from flask import (Flask, abort, redirect, render_template, request,
                   send_file, session, url_for)
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash
import qrcode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", os.path.join(BASE_DIR, "media_test"))
DB_PATH = os.path.join(BASE_DIR, "fang.db")
SECRET_PATH = os.path.join(BASE_DIR, "secret.txt")

# 功能模块注册表：showcase 为基础能力，不可关闭
FEATURES = [
    {"key": "showcase", "name": "房源展示", "locked": True,
     "desc": "租客扫码查看照片、视频、参数与联系方式（基础功能，不可关闭）"},
    {"key": "booking", "name": "预约看房", "locked": False,
     "desc": "租客在房源页提交看房预约，你在房源编辑页查看联系"},
    {"key": "repair", "name": "维修申报", "locked": False,
     "desc": "在租租客在线报修，你跟进处理后标记完成"},
    {"key": "message", "name": "租客留言", "locked": False,
     "desc": "租客在房源页留言咨询，你在房源编辑页查看"},
    {"key": "lease_alert", "name": "租约到期邮件提醒", "locked": False,
     "desc": "租约临近到期时自动发邮件，提醒你收租或谈续约"},
]

# 配套设施组件注册表：key / 名称 / 图标（线性 SVG，与全站图标风格一致）
_AM = lambda p: f'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{p}</svg>'
AMENITIES = [
    {"key": "fridge",    "name": "冰箱",   "icon": _AM('<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M5 10h14"/><path d="M15 6v.01"/><path d="M15 16v.01"/>')},
    {"key": "washer",    "name": "洗衣机", "icon": _AM('<rect x="4" y="2" width="16" height="20" rx="2"/><circle cx="12" cy="12" r="4"/><path d="M4 6h16"/><path d="M7 4h.01"/>')},
    {"key": "ac",        "name": "空调",   "icon": _AM('<rect x="3" y="4" width="18" height="7" rx="2"/><path d="M6 15v2"/><path d="M12 15v4"/><path d="M18 15v2"/><path d="M7 11h10"/>')},
    {"key": "heater",    "name": "热水器", "icon": _AM('<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>')},
    {"key": "wifi",      "name": "WiFi",  "icon": _AM('<path d="M5 13a10 10 0 0 1 14 0"/><path d="M8.5 16.5a5 5 0 0 1 7 0"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M12 20h.01"/>')},
    {"key": "tv",        "name": "电视",   "icon": _AM('<rect x="2" y="7" width="20" height="13" rx="2"/><path d="m17 2-5 5-5-5"/>')},
    {"key": "bed",       "name": "床",     "icon": _AM('<path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"/><path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"/><path d="M2 17h20"/>')},
    {"key": "wardrobe",  "name": "衣柜",   "icon": _AM('<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M12 2v20"/><path d="M9 11h.01"/><path d="M15 11h.01"/>')},
    {"key": "sofa",      "name": "沙发",   "icon": _AM('<path d="M20 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3"/><path d="M2 16a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v2H6v-2a2 2 0 0 0-4 0z"/><path d="M4 18v2"/><path d="M20 18v2"/>')},
    {"key": "microwave", "name": "微波炉", "icon": _AM('<rect x="2" y="5" width="20" height="14" rx="2"/><rect x="5" y="8" width="10" height="8" rx="1"/><path d="M19 8v.01"/><path d="M19 12v.01"/>')},
    {"key": "elevator",  "name": "电梯",   "icon": _AM('<rect x="5" y="2" width="14" height="20" rx="2"/><path d="m9.5 9 2.5-3 2.5 3"/><path d="m9.5 15 2.5 3 2.5-3"/>')},
    {"key": "parking",   "name": "车位",   "icon": _AM('<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.5 2.8C1.4 11.3 1 12.1 1 13v3c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>')},
]
AMENITY_MAP = {a["key"]: a for a in AMENITIES}

app = Flask(__name__)
# 不限制上传大小（nginx 侧 client_max_body_size 0 配合）
app.config["MAX_CONTENT_LENGTH"] = None

with open(SECRET_PATH) as f:
    lines = f.readlines()
    app.secret_key = lines[0].strip()
    _legacy_admin_password = lines[1].strip() if len(lines) > 1 else ""


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS landlords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT '',
                phone TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                wechat_id TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                landlord_id INTEGER NOT NULL REFERENCES landlords(id),
                name TEXT NOT NULL,
                price TEXT DEFAULT '',
                layout TEXT DEFAULT '',
                area TEXT DEFAULT '',
                floor TEXT DEFAULT '',
                orientation TEXT DEFAULT '',
                address TEXT DEFAULT '',
                descr TEXT DEFAULT '',
                status TEXT DEFAULT 'vacant',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                wechat_id TEXT DEFAULT '',
                lease_start TEXT DEFAULT '',
                lease_end TEXT DEFAULT '',
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                filename TEXT NOT NULL,
                sort INTEGER DEFAULT 0
            );
        """)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(properties)")]
        for col in ("address", "layout", "area", "floor", "orientation"):
            if col not in cols:
                conn.execute(f"ALTER TABLE properties ADD COLUMN {col} TEXT DEFAULT ''")
        if "status" not in cols:
            conn.execute("ALTER TABLE properties ADD COLUMN status TEXT DEFAULT 'vacant'")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feature_flags (
                landlord_id INTEGER NOT NULL REFERENCES landlords(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (landlord_id, key)
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                wish_time TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS repairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                contact TEXT DEFAULT '',
                content TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                contact TEXT DEFAULT '',
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                landlord_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                lease_end TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (landlord_id, tenant_id, lease_end)
            );
        """)
        lcols = [r["name"] for r in conn.execute("PRAGMA table_info(landlords)")]
        if "email" not in lcols:
            conn.execute("ALTER TABLE landlords ADD COLUMN email TEXT DEFAULT ''")
        if "alert_days" not in lcols:
            conn.execute("ALTER TABLE landlords ADD COLUMN alert_days INTEGER DEFAULT 30")
        if "amenities" not in [r["name"] for r in conn.execute("PRAGMA table_info(properties)")]:
            conn.execute("ALTER TABLE properties ADD COLUMN amenities TEXT DEFAULT ''")
        if "wechat_qr" not in [r["name"] for r in conn.execute("PRAGMA table_info(landlords)")]:
            conn.execute("ALTER TABLE landlords ADD COLUMN wechat_qr TEXT DEFAULT ''")
        for f in FEATURES:
            conn.execute("INSERT OR IGNORE INTO feature_flags (landlord_id, key, enabled) "
                         "SELECT id, ?, 1 FROM landlords", (f["key"],))
        _migrate_accounts(conn)


def get_flags(landlord_id):
    with db() as conn:
        rows = conn.execute("SELECT key, enabled FROM feature_flags WHERE landlord_id=?",
                            (landlord_id,)).fetchall()
    flags = {f["key"]: True for f in FEATURES}
    for r in rows:
        flags[r["key"]] = bool(r["enabled"])
    return flags


def smtp_configured():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_PORT"))


def send_mail(to_addr, subject, body):
    """Send via SMTP. Port 465 = SSL, 587 = STARTTLS, else plain (dev debugging)."""
    if not smtp_configured() or not to_addr:
        return False
    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", user or "fang-manager@localhost")
    msg["To"] = to_addr
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
        try:
            if port == 587:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        finally:
            server.quit()
        return True
    except Exception as e:
        print(f"[mail] send failed: {e}")
        return False


def check_lease_alerts():
    """Email landlords whose tenants' leases end within the lead window.
    Deduplicated per (landlord, tenant, lease_end) via alert_log."""
    if not smtp_configured():
        return 0
    with db() as conn:
        rows = conn.execute("""
            SELECT l.id AS lid, l.email, COALESCE(l.alert_days, 30) AS lead,
                   t.id AS tid, t.name, t.phone, t.lease_end,
                   p.id AS pid, p.name AS pname
            FROM landlords l
            JOIN feature_flags f ON f.landlord_id = l.id
                AND f.key = 'lease_alert' AND f.enabled = 1
            JOIN properties p ON p.landlord_id = l.id
            JOIN tenants t ON t.property_id = p.id
                AND t.active = 1 AND TRIM(t.lease_end) != ''
            WHERE TRIM(l.email) != ''
        """).fetchall()
    today = date.today()
    sent = 0
    for r in rows:
        try:
            end = date.fromisoformat(str(r["lease_end"]).strip())
        except ValueError:
            continue
        days_left = (end - today).days
        if days_left < 0 or days_left > r["lead"]:
            continue
        with db() as conn:
            dup = conn.execute(
                "SELECT 1 FROM alert_log WHERE landlord_id=? AND tenant_id=? AND lease_end=?",
                (r["lid"], r["tid"], r["lease_end"])).fetchone()
        if dup:
            continue
        tenant = r["name"] or "租客"
        when = f"{'今天' if days_left == 0 else str(days_left) + ' 天后'}（{r['lease_end']}）"
        body = (f"【fang-manager 租约到期提醒】\n\n"
                f"房源：{r['pname']}\n"
                f"租客：{tenant}" + (f"（电话 {r['phone']}）" if r["phone"] else "") + "\n"
                f"租期至：{r['lease_end']}，{when}到期。\n\n"
                f"请及时联系租客办理续约、收租或安排退租。\n"
                f"房源管理页：查看系统编辑页\n")
        if send_mail(r["email"], f"租约到期提醒：{r['pname']} {when}到期", body):
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO alert_log (landlord_id, tenant_id, lease_end) "
                             "VALUES (?,?,?)", (r["lid"], r["tid"], r["lease_end"]))
            sent += 1
    return sent


def _alert_loop():
    while True:
        try:
            check_lease_alerts()
        except Exception as e:
            print(f"[alert] loop error: {e}")
        _time.sleep(3600)


def _migrate_accounts(conn):
    """One-time upgrade: old per-property `landlords` rows become login
    accounts; every property is assigned to its landlord (default admin)."""
    lcols = [r["name"] for r in conn.execute("PRAGMA table_info(landlords)")]
    if "password_hash" in lcols:
        if "landlord_id" not in [r["name"] for r in conn.execute("PRAGMA table_info(properties)")]:
            conn.execute("ALTER TABLE properties ADD COLUMN landlord_id INTEGER")
        return
    has_rows = conn.execute("SELECT COUNT(*) c FROM landlords").fetchone()["c"] > 0
    if has_rows:
        conn.execute("ALTER TABLE landlords RENAME TO prop_landlords")
    conn.execute("""
        CREATE TABLE landlords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT '',
            phone TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            wechat_id TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    admin_id = conn.execute(
        "INSERT INTO landlords (name, phone, password_hash, wechat_id) VALUES (?,?,?,?)",
        ("管理员", "13800000000",
         generate_password_hash(_legacy_admin_password or "admin123"), "")).lastrowid
    prop_cols = [r["name"] for r in conn.execute("PRAGMA table_info(properties)")]
    if "landlord_id" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN landlord_id INTEGER")
    owner_of = {}
    if has_rows:
        for r in conn.execute("SELECT property_id, name, phone, wechat_id FROM prop_landlords"):
            acc = conn.execute("SELECT id FROM landlords WHERE phone=?", (r["phone"],)).fetchone()
            if acc:
                acc_id = acc["id"]
            else:
                acc_id = conn.execute(
                    "INSERT INTO landlords (name, phone, password_hash, wechat_id) VALUES (?,?,?,?)",
                    (r["name"] or "房东", r["phone"],
                     generate_password_hash(r["phone"][-6:] if r["phone"] else "123456"),
                     r["wechat_id"] or "")).lastrowid
            owner_of[r["property_id"]] = acc_id
    for (pid,) in conn.execute("SELECT id FROM properties").fetchall():
        conn.execute("UPDATE properties SET landlord_id=? WHERE id=?",
                     (owner_of.get(pid, admin_id), pid))


def logged_in():
    return session.get("landlord_id") is not None


def current_landlord():
    with db() as conn:
        row = conn.execute("SELECT * FROM landlords WHERE id=?",
                           (session["landlord_id"],)).fetchone()
    if not row:
        session.clear()
        abort(401)
    return dict(row)


def prop_dir(pid):
    path = os.path.join(MEDIA_ROOT, str(pid))
    os.makedirs(path, exist_ok=True)
    return path


def get_property(pid):
    prop = conn_execute_one(
        "SELECT p.*, l.name AS owner_name, l.phone AS owner_phone, "
        "l.wechat_id AS owner_wechat, l.wechat_qr AS owner_wechat_qr "
        "FROM properties p LEFT JOIN landlords l ON l.id = p.landlord_id "
        "WHERE p.id = ?", (pid,))
    if not prop:
        abort(404)
    return prop


def conn_execute_one(sql, args):
    with db() as conn:
        return conn.execute(sql, args).fetchone()


def get_my_property(pid):
    prop = dict(get_property(pid))
    if prop["landlord_id"] != session.get("landlord_id"):
        abort(404)
    return prop


def get_media(pid):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM media WHERE property_id = ? ORDER BY type, sort, id",
            (pid,)).fetchall()

    def with_ver(r):
        m = dict(r)
        try:
            m["v"] = int(os.path.getmtime(os.path.join(MEDIA_ROOT, str(pid), m["filename"])))
        except OSError:
            m["v"] = 0
        return m

    photos = [with_ver(r) for r in rows if r["type"] == "photo"]
    videos = [with_ver(r) for r in rows if r["type"] == "video"]
    return photos, videos


def get_active_tenant(pid):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM tenants WHERE property_id = ? AND active = 1 "
            "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    return dict(row) if row else None


def _file_ver(pid, filename):
    try:
        return int(os.path.getmtime(os.path.join(MEDIA_ROOT, str(pid), filename)))
    except OSError:
        return 0


@app.route("/")
def index():
    with db() as conn:
        props = conn.execute(
            "SELECT p.*, COUNT(m.id) AS media_count, "
            "(SELECT COUNT(*) FROM media mv WHERE mv.property_id = p.id AND mv.type = 'video') AS video_count "
            "FROM properties p LEFT JOIN media m ON m.property_id = p.id "
            "GROUP BY p.id ORDER BY p.id DESC").fetchall()
    props = [dict(p) for p in props]
    for p in props:
        p["thumb_v"] = _file_ver(p["id"], "photo_1.jpg")
        p["_price"] = float(p["price"]) if str(p.get("price", "")).strip() else None
        p["_area"] = float(p["area"]) if str(p.get("area", "")).strip() else None

    stats = {
        "total": len(props),
        "vacant": sum(1 for p in props if p["status"] != "rented"),
        "rented": sum(1 for p in props if p["status"] == "rented"),
    }
    vacant_prices = [p["_price"] for p in props
                     if p["status"] != "rented" and p["_price"]]
    stats["avg_price"] = (int(sum(vacant_prices) / len(vacant_prices))
                          if vacant_prices else 0)

    q = request.args.get("q", "").strip()
    if q:
        kw = q.lower()
        props = [p for p in props if any(
            kw in str(p.get(k, "")).lower()
            for k in ("name", "address", "layout", "descr", "orientation"))]

    status = request.args.get("status", "all")
    if status == "rented":
        props = [p for p in props if p["status"] == "rented"]
    elif status == "vacant":
        props = [p for p in props if p["status"] != "rented"]

    sort = request.args.get("sort", "default")
    if sort == "price_asc":
        props.sort(key=lambda p: (p["_price"] is None, p["_price"] or 0))
    elif sort == "price_desc":
        props.sort(key=lambda p: (p["_price"] is None, -(p["_price"] or 0)))
    elif sort == "area_asc":
        props.sort(key=lambda p: (p["_area"] is None, p["_area"] or 0))
    elif sort == "area_desc":
        props.sort(key=lambda p: (p["_area"] is None, -(p["_area"] or 0)))

    return render_template("index.html", props=props, stats=stats,
                           status=status, sort=sort, q=q)


@app.route("/h/<int:pid>")
def landing(pid):
    prop = dict(get_property(pid))
    photos, videos = get_media(pid)
    flags = get_flags(prop["landlord_id"])
    try:
        amenity_keys = json.loads(prop.get("amenities") or "[]")
    except (ValueError, TypeError):
        amenity_keys = []
    prop["amenity_items"] = [AMENITY_MAP[k] for k in amenity_keys if k in AMENITY_MAP]
    return render_template("landing.html", prop=prop,
                           media=list(photos) + list(videos),
                           flags=flags, sent=request.args.get("sent", ""))


def _service_target(pid):
    """Property dict + owner flags for a public service submission; 404 if module off."""
    prop = dict(get_property(pid))
    flags = get_flags(prop["landlord_id"])
    return prop, flags


@app.route("/h/<int:pid>/book", methods=["POST"])
def service_book(pid):
    prop, flags = _service_target(pid)
    if not flags.get("booking"):
        abort(404)
    name = request.form.get("name", "").strip()[:30]
    phone = request.form.get("phone", "").strip()[:30]
    wish = request.form.get("wish_time", "").strip()[:40]
    if phone:
        with db() as conn:
            conn.execute("INSERT INTO bookings (property_id, name, phone, wish_time) "
                         "VALUES (?,?,?,?)", (pid, name, phone, wish))
    return redirect(url_for("landing", pid=pid) + "?sent=booking")


@app.route("/h/<int:pid>/repair", methods=["POST"])
def service_repair(pid):
    prop, flags = _service_target(pid)
    if not flags.get("repair"):
        abort(404)
    contact = request.form.get("contact", "").strip()[:40]
    content = request.form.get("content", "").strip()[:500]
    if content:
        with db() as conn:
            conn.execute("INSERT INTO repairs (property_id, contact, content) "
                         "VALUES (?,?,?)", (pid, contact, content))
    return redirect(url_for("landing", pid=pid) + "?sent=repair")


@app.route("/h/<int:pid>/message", methods=["POST"])
def service_message(pid):
    prop, flags = _service_target(pid)
    if not flags.get("message"):
        abort(404)
    contact = request.form.get("contact", "").strip()[:40]
    content = request.form.get("content", "").strip()[:500]
    if content:
        with db() as conn:
            conn.execute("INSERT INTO messages (property_id, contact, content) "
                         "VALUES (?,?,?)", (pid, contact, content))
    return redirect(url_for("landing", pid=pid) + "?sent=message")


@app.route("/h/")
@app.route("/h")
def landing_redirect():
    return redirect(url_for("index"))


@app.route("/qr/<int:pid>.png")
def qr(pid):
    get_property(pid)
    url = f"{request.host_url.rstrip('/')}/h/{pid}"
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png",
                     download_name=f"qr_{pid}.png")


@app.route("/media/<int:pid>/<path:filename>")
def media(pid, filename):
    path = os.path.join(MEDIA_ROOT, str(pid), filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        with db() as conn:
            row = conn.execute("SELECT * FROM landlords WHERE phone=?",
                               (phone,)).fetchone()
        if row and check_password_hash(row["password_hash"],
                                       request.form.get("password", "")):
            session["landlord_id"] = row["id"]
            return redirect(url_for("dashboard"))
        error = "手机号或密码错误"
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        wechat = request.form.get("wechat_id", "").strip()
        password = request.form.get("password", "")
        if not name or not phone or len(password) < 6:
            error = "请填写姓名、手机号，密码至少 6 位"
        else:
            with db() as conn:
                exists = conn.execute("SELECT id FROM landlords WHERE phone=?",
                                      (phone,)).fetchone()
                if exists:
                    error = "该手机号已注册"
                else:
                    conn.execute(
                        "INSERT INTO landlords (name, phone, password_hash, wechat_id) "
                        "VALUES (?,?,?,?)",
                        (name, phone, generate_password_hash(password), wechat))
            if not error:
                with db() as conn:
                    row = conn.execute("SELECT id FROM landlords WHERE phone=?",
                                       (phone,)).fetchone()
                session["landlord_id"] = row["id"]
                return redirect(url_for("dashboard"))
    return render_template("register.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- 上传审核（前端做类型预检，这里做魔术字节级校验） ----------
_ALLOWED_IMG_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}


def _image_ok(stream):
    """校验真实图片格式（防改后缀伪装），通过则返回重开的 PIL 对象。"""
    try:
        stream.seek(0)
        img = Image.open(stream)
        if (img.format or "").upper() not in _ALLOWED_IMG_FORMATS:
            return None
        img.verify()
        stream.seek(0)
        img = Image.open(stream)
        if (img.format or "").upper() not in _ALLOWED_IMG_FORMATS:
            return None
        return img.convert("RGB")
    except Exception:
        return None


def _video_file_ok(path):
    """ffprobe 校验视频容器与视频流，防伪装文件。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=format_name",
             "-of", "csv=p=0", path], capture_output=True, timeout=30)
        fmt = r.stdout.decode(errors="replace").strip().lower()
        if not any(k in fmt for k in ("mp4", "mov", "matroska", "webm")):
            return False
        r2 = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, timeout=30)
        return "video" in r2.stdout.decode(errors="replace")
    except Exception:
        return False


def _external_moderation_ok(data):
    """可选的外部内容审核钩子：设置 UPLOAD_MODERATION_URL 后启用。
    审核接口收到原始字节，返回 JSON {"pass": true/false, "label": "..."}。
    接口不可用时不阻断业务。"""
    url = os.environ.get("UPLOAD_MODERATION_URL")
    if not url:
        return True, ""
    try:
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode())
        return bool(res.get("pass")), str(res.get("label") or "未通过审核")
    except Exception:
        return True, ""


# ---------- 房东微信二维码 ----------
def _qr_path(lid):
    return os.path.join(MEDIA_ROOT, "qr", f"qr_{lid}.jpg")


@app.route("/profile/qr", methods=["POST"])
def upload_wechat_qr():
    if not logged_in():
        return redirect(url_for("login"))
    f = request.files.get("qr")
    if not f or not f.filename:
        return redirect(url_for("profile"))
    img = _image_ok(f.stream)
    if img is None:
        return redirect(url_for("profile", err="qr_format"))
    img.thumbnail((800, 800), Image.LANCZOS)
    os.makedirs(os.path.dirname(_qr_path(session["landlord_id"])), exist_ok=True)
    img.save(_qr_path(session["landlord_id"]), quality=92)
    with db() as conn:
        conn.execute("UPDATE landlords SET wechat_qr=? WHERE id=?",
                     (f"qr_{session['landlord_id']}.jpg", session["landlord_id"]))
    return redirect(url_for("profile", saved=1))


@app.route("/profile/qr/remove", methods=["POST"])
def remove_wechat_qr():
    if not logged_in():
        return redirect(url_for("login"))
    path = _qr_path(session["landlord_id"])
    if os.path.exists(path):
        os.remove(path)
    with db() as conn:
        conn.execute("UPDATE landlords SET wechat_qr='' WHERE id=?",
                     (session["landlord_id"],))
    return redirect(url_for("profile"))


@app.route("/wxqr/<int:lid>")
def wechat_qr_image(lid):
    path = _qr_path(lid)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=300)


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not logged_in():
        return redirect(url_for("login"))
    me = current_landlord()
    saved = False
    if request.method == "POST":
        name = request.form.get("name", "").strip() or me["name"]
        wechat = request.form.get("wechat_id", "").strip()
        oldpw = request.form.get("old_password", "")
        newpw = request.form.get("new_password", "")
        with db() as conn:
            if newpw:
                if not check_password_hash(me["password_hash"], oldpw):
                    return render_template("profile.html", me=me,
                                           error="原密码不正确", saved=False)
                if len(newpw) < 6:
                    return render_template("profile.html", me=me,
                                           error="新密码至少 6 位", saved=False)
                conn.execute("UPDATE landlords SET name=?, wechat_id=?, password_hash=? WHERE id=?",
                             (name, wechat, generate_password_hash(newpw), me["id"]))
            else:
                conn.execute("UPDATE landlords SET name=?, wechat_id=? WHERE id=?",
                             (name, wechat, me["id"]))
        return redirect(url_for("profile", saved=1))
    if request.args.get("saved"):
        saved = True
    return render_template("profile.html", me=me, error="", saved=saved)


@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect(url_for("login"))
    me = current_landlord()
    with db() as conn:
        props = conn.execute(
            "SELECT p.*, COUNT(m.id) AS media_count, "
            "(SELECT COUNT(*) FROM media mv WHERE mv.property_id = p.id AND mv.type = 'video') AS video_count, "
            "(SELECT COUNT(*) FROM tenants t WHERE t.property_id = p.id AND t.active = 1) AS tenant_count "
            "FROM properties p LEFT JOIN media m ON m.property_id = p.id "
            "WHERE p.landlord_id = ? GROUP BY p.id ORDER BY p.id DESC",
            (me["id"],)).fetchall()
    props = [dict(p) for p in props]
    for p in props:
        p["thumb_v"] = _file_ver(p["id"], "photo_1.jpg")
    stats = {
        "total": len(props),
        "rented": sum(1 for p in props if p["status"] == "rented"),
        "vacant": sum(1 for p in props if p["status"] != "rented"),
        "media": sum(p["media_count"] or 0 for p in props),
    }
    return render_template("dashboard.html", me=me, props=props, stats=stats)


@app.route("/prop/new", methods=["POST"])
def create_prop():
    if not logged_in():
        return redirect(url_for("login"))
    name = request.form.get("name", "").strip()
    if not name:
        abort(400)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO properties (landlord_id, name, price, layout, area, floor, "
            "orientation, address, descr) VALUES (?,?,?,?,?,?,?,?,?)",
            (session["landlord_id"], name,
             request.form.get("price", "").strip(),
             request.form.get("layout", "").strip(),
             request.form.get("area", "").strip(),
             request.form.get("floor", "").strip(),
             request.form.get("orientation", "").strip(),
             request.form.get("address", "").strip(),
             request.form.get("descr", "").strip()))
        pid = cur.lastrowid
    prop_dir(pid)
    return redirect(url_for("edit_prop", pid=pid))


@app.route("/prop/<int:pid>")
def edit_prop(pid):
    if not logged_in():
        return redirect(url_for("login"))
    prop = get_my_property(pid)
    photos, videos = get_media(pid)
    tenant = get_active_tenant(pid)
    me = current_landlord()
    try:
        selected = set(json.loads(prop["amenities"] or "[]"))
    except (ValueError, TypeError):
        selected = set()
    amenity_items = [dict(a, on=a["key"] in selected) for a in AMENITIES]
    with db() as conn:
        bookings = conn.execute("SELECT * FROM bookings WHERE property_id=? "
                                "ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
        repairs = conn.execute("SELECT * FROM repairs WHERE property_id=? "
                               "ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
        messages = conn.execute("SELECT * FROM messages WHERE property_id=? "
                                "ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
    return render_template("edit.html", prop=prop, me=me,
                           photos=photos, videos=videos, tenant=tenant,
                           bookings=bookings, repairs=repairs, messages=messages,
                           flags=get_flags(me["id"]),
                           amenity_items=amenity_items)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if not logged_in():
        return redirect(url_for("login"))
    me = current_landlord()
    saved = request.args.get("saved")
    if request.method == "POST":
        email = request.form.get("email", "").strip()[:80]
        alert_days = request.form.get("alert_days", "30").strip()
        try:
            alert_days = max(1, min(180, int(alert_days)))
        except ValueError:
            alert_days = 30
        with db() as conn:
            conn.execute("UPDATE landlords SET email=?, alert_days=? WHERE id=?",
                         (email, alert_days, me["id"]))
            for f in FEATURES:
                if f["locked"]:
                    continue
                enabled = 1 if request.form.get("feat_" + f["key"]) else 0
                conn.execute("UPDATE feature_flags SET enabled=? WHERE landlord_id=? AND key=?",
                             (enabled, me["id"], f["key"]))
        if request.args.get("then") == "check":
            n = check_lease_alerts()
            return redirect(url_for("settings", saved=1, checked=n))
        return redirect(url_for("settings", saved=1))
    me = current_landlord()
    return render_template("settings.html", me=me, FEATURES=FEATURES,
                           flags=get_flags(me["id"]),
                           smtp_ok=smtp_configured(), saved=saved,
                           checked=request.args.get("checked"))


def _own_service(table, item_id):
    """Fetch a service row joined with owner check; returns row or None."""
    with db() as conn:
        return conn.execute(
            f"SELECT s.* FROM {table} s JOIN properties p ON p.id = s.property_id "
            f"WHERE s.id=? AND p.landlord_id=?",
            (item_id, session.get("landlord_id"))).fetchone()


@app.route("/repairs/<int:rid>/done", methods=["POST"])
def repair_done(rid):
    if not logged_in():
        return redirect(url_for("login"))
    if _own_service("repairs", rid):
        with db() as conn:
            conn.execute("UPDATE repairs SET status='done' WHERE id=?", (rid,))
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/repairs/<int:rid>/delete", methods=["POST"])
def repair_delete(rid):
    if not logged_in():
        return redirect(url_for("login"))
    if _own_service("repairs", rid):
        with db() as conn:
            conn.execute("DELETE FROM repairs WHERE id=?", (rid,))
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/bookings/<int:bid>/delete", methods=["POST"])
def booking_delete(bid):
    if not logged_in():
        return redirect(url_for("login"))
    if _own_service("bookings", bid):
        with db() as conn:
            conn.execute("DELETE FROM bookings WHERE id=?", (bid,))
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/bookings/<int:bid>/call", methods=["POST"])
def booking_convert(bid):
    """Placeholder: booking is handled offline; just removes it from the list."""
    return booking_delete(bid)


@app.route("/messages/<int:mid>/delete", methods=["POST"])
def message_delete(mid):
    if not logged_in():
        return redirect(url_for("login"))
    if _own_service("messages", mid):
        with db() as conn:
            conn.execute("DELETE FROM messages WHERE id=?", (mid,))
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/settings/test_email", methods=["POST"])
def test_email():
    if not logged_in():
        return redirect(url_for("login"))
    me = current_landlord()
    if not smtp_configured():
        return redirect(url_for("settings", tested="nosmtp"))
    if not (me["email"] or "").strip():
        return redirect(url_for("settings", tested="noemail"))
    ok = send_mail(me["email"].strip(),
                   "fang-manager 测试邮件",
                   "收到这封邮件说明告警邮箱配置成功。\n租约到期提醒将发送到这个邮箱。")
    return redirect(url_for("settings", tested="ok" if ok else "fail"))


@app.route("/prop/<int:pid>/update", methods=["POST"])
def update_prop(pid):
    get_my_property(pid)
    amenities = [k for k in request.form.getlist("amenities") if k in AMENITY_MAP]
    with db() as conn:
        conn.execute(
            "UPDATE properties SET name=?, price=?, layout=?, area=?, floor=?, "
            "orientation=?, address=?, descr=?, amenities=? WHERE id=?",
            (request.form.get("name", "").strip(),
             request.form.get("price", "").strip(),
             request.form.get("layout", "").strip(),
             request.form.get("area", "").strip(),
             request.form.get("floor", "").strip(),
             request.form.get("orientation", "").strip(),
             request.form.get("address", "").strip(),
             request.form.get("descr", "").strip(),
             json.dumps(amenities), pid))
    return redirect(url_for("edit_prop", pid=pid))


@app.route("/prop/<int:pid>/delete", methods=["POST"])
def delete_prop(pid):
    get_my_property(pid)
    with db() as conn:
        conn.execute("DELETE FROM properties WHERE id=?", (pid,))
    shutil.rmtree(prop_dir(pid), ignore_errors=True)
    return redirect(url_for("dashboard"))


@app.route("/prop/<int:pid>/status", methods=["POST"])
def toggle_status(pid):
    prop = get_my_property(pid)
    new_status = "rented" if prop["status"] == "vacant" else "vacant"
    with db() as conn:
        conn.execute("UPDATE properties SET status=? WHERE id=?", (new_status, pid))
    return redirect(url_for("edit_prop", pid=pid))


@app.route("/prop/<int:pid>/photos", methods=["POST"])
def upload_photos(pid):
    get_my_property(pid)
    for f in request.files.getlist("photos"):
        if not f.filename:
            continue
        img = _image_ok(f.stream)
        if img is None:
            flash("有文件不是有效图片（仅支持 JPG / PNG / WebP），已跳过")
            continue
        f.stream.seek(0)
        ok, label = _external_moderation_ok(f.stream.read())
        if not ok:
            flash(f"有图片未通过内容审核（{label}），已跳过")
            continue
        with db() as conn:
            n = conn.execute(
                "SELECT COUNT(*) c FROM media WHERE property_id=? AND type='photo'",
                (pid,)).fetchone()["c"]
            filename = f"photo_{n + 1}.jpg"
            conn.execute(
                "INSERT INTO media (property_id, type, filename, sort) VALUES (?,?,?,?)",
                (pid, "photo", filename, n + 1))
        img.thumbnail((1920, 1920), Image.LANCZOS)
        img.save(os.path.join(prop_dir(pid), filename), quality=85, optimize=True)
    return redirect(url_for("edit_prop", pid=pid))


@app.route("/prop/<int:pid>/video", methods=["POST"])
def upload_video(pid):
    get_my_property(pid)
    f = request.files.get("video")
    if not f or not f.filename:
        return redirect(url_for("edit_prop", pid=pid))
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("mp4", "mov", "webm"):
        ext = "mp4"
    filename = f"video.{ext}"
    final_path = os.path.join(prop_dir(pid), filename)
    f.save(final_path)
    if not _video_file_ok(final_path):
        os.remove(final_path)
        flash("视频校验未通过：仅支持包含视频流的 mp4 / mov / webm 文件")
        return redirect(url_for("edit_prop", pid=pid))
    _transcode_to_h264(final_path)
    with db() as conn:
        conn.execute("DELETE FROM media WHERE property_id=? AND type='video'", (pid,))
        conn.execute(
            "INSERT INTO media (property_id, type, filename, sort) VALUES (?,?,?,1)",
            (pid, "video", filename))
    return redirect(url_for("edit_prop", pid=pid))


def _transcode_to_h264(path):
    """Re-encode uploads to H.264 main profile so every mobile webview can
    decode them (iPhone HEVC recordings cannot). Keeps original on failure."""
    tmp = path + ".h264.mp4"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", path,
             "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
             "-preset", "fast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", tmp],
            capture_output=True, timeout=600)
        if result.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, path)
            return True
    except Exception:
        pass
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False


@app.route("/prop/<int:pid>/tenant", methods=["POST"])
def save_tenant(pid):
    get_my_property(pid)
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    wechat = request.form.get("wechat_id", "").strip()
    lease_start = request.form.get("lease_start", "").strip()
    lease_end = request.form.get("lease_end", "").strip()
    with db() as conn:
        if name or phone or wechat:
            conn.execute("UPDATE tenants SET active=0 WHERE property_id=?", (pid,))
            conn.execute(
                "INSERT INTO tenants (property_id, name, phone, wechat_id, lease_start, "
                "lease_end, active) VALUES (?,?,?,?,?,?,1)",
                (pid, name, phone, wechat, lease_start, lease_end))
            conn.execute("UPDATE properties SET status='rented' WHERE id=?", (pid,))
        else:
            conn.execute("UPDATE tenants SET active=0 WHERE property_id=?", (pid,))
            conn.execute("UPDATE properties SET status='vacant' WHERE id=?", (pid,))
    return redirect(url_for("edit_prop", pid=pid))


@app.route("/media/<int:mid>/delete", methods=["POST"])
def delete_media(mid):
    row = None
    with db() as conn:
        row = conn.execute(
            "SELECT m.* FROM media m JOIN properties p ON p.id = m.property_id "
            "WHERE m.id=? AND p.landlord_id=?", (mid, session.get("landlord_id"))).fetchone()
        if row:
            conn.execute("DELETE FROM media WHERE id=?", (mid,))
    if row:
        path = os.path.join(prop_dir(row["property_id"]), row["filename"])
        if os.path.exists(path):
            os.remove(path)
    return redirect(request.referrer or url_for("dashboard"))


@app.errorhandler(404)
def not_found(e):
    return "页面不存在", 404


@app.route("/favicon.ico")
def favicon():
    buf = io.BytesIO()
    img = Image.new("RGB", (32, 32), (20, 108, 67))
    img.save(buf, format="ICO")
    buf.seek(0)
    return send_file(buf, mimetype="image/x-icon")


init_db()

if __name__ == "__main__":
    threading.Thread(target=_alert_loop, daemon=True).start()
    app.run(host="127.0.0.1", port=5002)

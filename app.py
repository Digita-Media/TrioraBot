import os
import sqlite3
import threading
import time
from functools import wraps

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

from werkzeug.security import generate_password_hash, check_password_hash

# ------------------------------------------------
# FLASK APP SETUP
# ------------------------------------------------
app = Flask(__name__)

# Secret key for sessions (set in Replit "Secrets" ideally)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

# Facebook tokens (set these in Replit "Secrets")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")  # long-lived Page token
DEFAULT_GROUP_ID = "849838074302350"  # your TEST bot group

# Poll interval in seconds (used later if you want background polling)
POLL_INTERVAL = 30

DB_PATH = "triora_bot.db"


# ------------------------------------------------
# DB HELPERS
# ------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # Keywords table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patterns TEXT NOT NULL,  -- comma-separated patterns
            reply TEXT NOT NULL
        )
        """
    )

    # Settings table (key/value)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    # Dismissed posts (so they don't show again)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dismissed_posts (
            post_id TEXT PRIMARY KEY
        )
        """
    )

    # Replied posts (for tracking / analytics)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS replied_posts (
            post_id TEXT PRIMARY KEY,
            replied_at TEXT
        )
        """
    )

    conn.commit()

    # Ensure default settings exist
    def ensure_setting(key, value):
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()

    ensure_setting("group_id", DEFAULT_GROUP_ID)
    ensure_setting("page_name", "Triora Damp & Mould")

    # Ensure default admin user exists
    admin_email = "connor@triora.co.uk"
    default_password = "Triorabot25"  # you can change this later from UI

    cur.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            INSERT INTO users (email, password_hash, is_admin, is_active)
            VALUES (?, ?, 1, 1)
            """,
            (admin_email, generate_password_hash(default_password)),
        )
        conn.commit()

    conn.close()


@app.before_first_request
def setup():
    init_db()


# ------------------------------------------------
# AUTH DECORATORS
# ------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE id = ?", (session["user_id"],))
        row = cur.fetchone()
        conn.close()
        if not row or not row["is_admin"]:
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


# ------------------------------------------------
# SETTINGS HELPERS
# ------------------------------------------------
def get_setting(key, default=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row["value"]
    return default


def set_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------
# KEYWORD REPLY LOGIC
# ------------------------------------------------
def load_keywords():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, patterns, reply FROM keywords")
    rows = cur.fetchall()
    conn.close()

    keyword_rules = []
    for row in rows:
        patterns = [p.strip().lower() for p in row["patterns"].split(",") if p.strip()]
        keyword_rules.append((patterns, row["reply"]))
    return keyword_rules


GENERIC_FALLBACK = """Thanks for your post! Damp and mould issues can have a range of causes, and getting the right advice early can make a big difference.

If you’d like some guidance, feel free to contact our team at Triora Damp & Mould:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk"""


def choose_reply_for_message(message: str) -> str:
    if not message:
        return GENERIC_FALLBACK

    msg = message.lower()
    rules = load_keywords()

    for patterns, reply in rules:
        if any(p in msg for p in patterns):
            return reply

    # No match → fallback
    return GENERIC_FALLBACK


# ------------------------------------------------
# FACEBOOK HELPERS
# ------------------------------------------------
def fb_get_group_feed(limit=25):
    """Fetch latest posts from the configured Facebook Group."""
    group_id = get_setting("group_id", DEFAULT_GROUP_ID)

    if not PAGE_ACCESS_TOKEN:
        return {
            "error": {
                "message": "PAGE_ACCESS_TOKEN is not set. Add it in Replit Secrets."
            }
        }

    url = f"https://graph.facebook.com/v17.0/{group_id}/feed"
    params = {
        "access_token": PAGE_ACCESS_TOKEN,
        "limit": limit,
        "fields": "id,message,from,created_time",
    }
    resp = requests.get(url, params=params)
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": "Invalid JSON from Facebook."}}
    return data


def fb_send_comment(post_id: str, message: str):
    """Send a comment as the Page to a given post."""
    if not PAGE_ACCESS_TOKEN:
        return {"error": "PAGE_ACCESS_TOKEN not set"}

    url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
    resp = requests.post(url, data=payload)
    try:
        data = resp.json()
    except Exception:
        data = {"error": "Invalid JSON from Facebook."}
    return data


# Simple lead detection (can be improved later)
LEAD_KEYWORDS = [
    "quote",
    "survey",
    "price",
    "cost",
    "visit",
    "come out",
    "assessment",
    "inspection",
]


def classify_post(message: str) -> str:
    if not message:
        return "advice"

    msg = message.lower()
    if any(k in msg for k in LEAD_KEYWORDS):
        return "lead"
    return "advice"


# ------------------------------------------------
# ROUTES: AUTH
# ------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        conn.close()

        if not user:
            flash("Account not found.", "danger")
            return render_template("login.html")

        if not user["is_active"]:
            flash("Your account is awaiting admin approval.", "warning")
            return render_template("login.html")

        if not check_password_hash(user["password_hash"], password):
            flash("Incorrect password.", "danger")
            return render_template("login.html")

        # Success
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["is_admin"] = bool(user["is_admin"])

        next_url = request.args.get("next") or url_for("dashboard")
        return redirect(next_url)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------
# ROUTES: DASHBOARD (POST MODERATION)
# ------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    """Main moderation dashboard: shows new posts split into Advice / Leads."""
    # Fetch dismissed / replied post IDs to filter
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT post_id FROM dismissed_posts")
    dismissed = {row["post_id"] for row in cur.fetchall()}
    cur.execute("SELECT post_id FROM replied_posts")
    replied = {row["post_id"] for row in cur.fetchall()}
    conn.close()

    fb_data = fb_get_group_feed(limit=30)

    if "error" in fb_data:
        error_msg = fb_data["error"].get("message", "Unknown Facebook API error")
        return render_template(
            "dashboard.html",
            error=error_msg,
            advice_posts=[],
            lead_posts=[],
            group_id=get_setting("group_id", DEFAULT_GROUP_ID),
        )

    advice_posts = []
    lead_posts = []

    for post in fb_data.get("data", []):
        post_id = post.get("id")
        message = post.get("message", "")

        if not post_id:
            continue

        # Skip if dismissed or already replied
        if post_id in dismissed or post_id in replied:
            continue

        category = classify_post(message)
        post_info = {
            "id": post_id,
            "message": message,
            "from_name": (post.get("from") or {}).get("name", "Unknown"),
            "created_time": post.get("created_time", ""),
            "category": category,
            "suggested_reply": choose_reply_for_message(message),
        }

        if category == "lead":
            lead_posts.append(post_info)
        else:
            advice_posts.append(post_info)

    return render_template(
        "dashboard.html",
        error=None,
        advice_posts=advice_posts,
        lead_posts=lead_posts,
        group_id=get_setting("group_id", DEFAULT_GROUP_ID),
    )


@app.route("/posts/action", methods=["POST"])
@login_required
def post_action():
    """Handle Approve & Reply / Skip actions."""
    action = request.form.get("action")
    post_id = request.form.get("post_id")
    custom_reply = request.form.get("custom_reply", "").strip()
    original_msg = request.form.get("original_message", "")

    if not post_id:
        flash("No post selected.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    if action == "skip":
        cur.execute(
            "INSERT OR IGNORE INTO dismissed_posts (post_id) VALUES (?)",
            (post_id,),
        )
        conn.commit()
        conn.close()
        flash("Post dismissed.", "info")
        return redirect(url_for("dashboard"))

    if action == "reply":
        reply_text = custom_reply or choose_reply_for_message(original_msg)
        fb_resp = fb_send_comment(post_id, reply_text)

        if "error" in fb_resp:
            flash(f"Facebook error: {fb_resp['error']}", "danger")
        else:
            # Mark as replied
            cur.execute(
                """
                INSERT OR REPLACE INTO replied_posts (post_id, replied_at)
                VALUES (?, datetime('now'))
                """,
                (post_id,),
            )
            conn.commit()
            flash("Reply sent as Page (if token is correct).", "success")

        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()
    flash("Unknown action.", "danger")
    return redirect(url_for("dashboard"))


# ------------------------------------------------
# ROUTES: KEYWORDS MANAGEMENT (ADMIN)
# ------------------------------------------------
@app.route("/keywords", methods=["GET", "POST"])
@admin_required
def manage_keywords():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        patterns = request.form.get("patterns", "").strip()
        reply = request.form.get("reply", "").strip()
        if not patterns or not reply:
            flash("Both patterns and reply are required.", "danger")
        else:
            cur.execute(
                "INSERT INTO keywords (patterns, reply) VALUES (?, ?)",
                (patterns, reply),
            )
            conn.commit()
            flash("Keyword rule added.", "success")

    cur.execute("SELECT * FROM keywords ORDER BY id DESC")
    rules = cur.fetchall()
    conn.close()
    return render_template("keywords.html", rules=rules)


@app.route("/keywords/delete/<int:rule_id>", methods=["POST"])
@admin_required
def delete_keyword(rule_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM keywords WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    flash("Keyword rule deleted.", "info")
    return redirect(url_for("manage_keywords"))


# ------------------------------------------------
# ROUTES: ADMIN – USER MANAGEMENT
# ------------------------------------------------
@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        # Admin can create a new staff account
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        make_admin = bool(request.form.get("is_admin"))

        if not email or not password:
            flash("Email and password are required.", "danger")
        else:
            try:
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash, is_admin, is_active)
                    VALUES (?, ?, ?, 1)
                    """,
                    (
                        email,
                        generate_password_hash(password),
                        1 if make_admin else 0,
                    ),
                )
                conn.commit()
                flash("User created and activated.", "success")
            except sqlite3.IntegrityError:
                flash("A user with that email already exists.", "danger")

    cur.execute("SELECT * FROM users ORDER BY id ASC")
    users = cur.fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/toggle_active/<int:user_id>", methods=["POST"])
@admin_required
def toggle_user_active(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_active FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        new_val = 0 if row["is_active"] else 1
        cur.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (new_val, user_id),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/toggle_admin/<int:user_id>", methods=["POST"])
@admin_required
def toggle_user_admin(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        new_val = 0 if row["is_admin"] else 1
        cur.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (new_val, user_id),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("admin_users"))


# ------------------------------------------------
# ROUTES: SETTINGS (GROUP ID, ETC.)
# ------------------------------------------------
@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings_page():
    if request.method == "POST":
        group_id = request.form.get("group_id", "").strip()
        page_name = request.form.get("page_name", "").strip()

        if group_id:
            set_setting("group_id", group_id)
        if page_name:
            set_setting("page_name", page_name)

        flash("Settings updated.", "success")
        return redirect(url_for("settings_page"))

    return render_template(
        "admin_settings.html",
        group_id=get_setting("group_id", DEFAULT_GROUP_ID),
        page_name=get_setting("page_name", "Triora Damp & Mould"),
    )


# ------------------------------------------------
# SIMPLE HEALTH CHECK
# ------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ------------------------------------------------
# OPTIONAL: BACKGROUND POLLING (currently not used)
# ------------------------------------------------
def background_polling_loop():
    while True:
        try:
            # For now we just touch the group feed so the token gets used.
            fb_get_group_feed(limit=5)
        except Exception as e:
            print("Background polling error:", e)
        time.sleep(POLL_INTERVAL)


def start_background_polling():
    t = threading.Thread(target=background_polling_loop, daemon=True)
    t.start()


# ------------------------------------------------
# MAIN ENTRY
# ------------------------------------------------
if __name__ == "__main__":
    # If you want background polling, uncomment:
    # start_background_polling()

    # Replit usually runs on port 5000
    app.run(host="0.0.0.0", port=5000, debug=True)

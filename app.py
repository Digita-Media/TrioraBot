import os
from flask import Flask, request, jsonify, session, redirect, render_template, url_for
from flask_bcrypt import Bcrypt
from flask_session import Session
import requests
from uuid import uuid4

# --------------------------------------
# CONFIG
# --------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")
app.config["SESSION_TYPE"] = "filesystem"

Session(app)
bcrypt = Bcrypt(app)

# --------------------------------------
# DATA STORAGE (TEMP - WILL MOVE TO DB LATER)
# --------------------------------------

users = {
    "connor@triora.co.uk": {
        "password": bcrypt.generate_password_hash("Triorabot25").decode(),
        "role": "admin"
    }
}

keywords = {
    "mould": "Thanks for sharing. Mould can appear for many reasons. If you'd like guidance: https://trioradampandmould.co.uk",
    "condensation": "Condensation can have many causes. We're here to help.",
    "damp": "Thanks for sharing. Damp issues often need assessment."
}

pending_posts = []  # All detected posts
ai_suggestions = {}  # Post ID → AI generated reply

FACEBOOK_PAGE_ID = "TrioraDampandMould"
GROUP_ID = "2095729247274508"  # Real group
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --------------------------------------
# AUTH HELPERS
# --------------------------------------

def logged_in():
    return "user" in session

def admin_only():
    return logged_in() and session["role"] == "admin"

# --------------------------------------
# ROUTES
# --------------------------------------

@app.route("/")
def home():
    if not logged_in():
        return redirect("/login")
    return redirect("/dashboard")

# --------------------------------------
# LOGIN
# --------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if email in users:
            stored_pw = users[email]["password"]
            if bcrypt.check_password_hash(stored_pw, password):
                session["user"] = email
                session["role"] = users[email]["role"]
                return redirect("/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# --------------------------------------
# DASHBOARD
# --------------------------------------

@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect("/login")

    return render_template("dashboard.html", posts=pending_posts)

# --------------------------------------
# POST DETAIL
# --------------------------------------

@app.route("/post/<post_id>")
def post_detail(post_id):
    if not logged_in():
        return redirect("/login")

    post = next((p for p in pending_posts if p["id"] == post_id), None)

    if not post:
        return "Post not found", 404

    suggestion = ai_suggestions.get(post_id, "")

    return render_template("post_detail.html", post=post, suggestion=suggestion)

# --------------------------------------
# UPDATE KEYWORDS
# --------------------------------------

@app.route("/keywords", methods=["GET", "POST"])
def keyword_page():
    if not admin_only():
        return redirect("/dashboard")

    if request.method == "POST":
        word = request.form["keyword"]
        reply = request.form["reply"]
        keywords[word.lower()] = reply

    return render_template("keywords.html", keywords=keywords)

# --------------------------------------
# ADD STAFF USERS (ADMIN ONLY)
# --------------------------------------

@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if not admin_only():
        return redirect("/dashboard")

    if request.method == "POST":
        email = request.form["email"]
        pw = request.form["password"]
        role = request.form["role"]

        users[email] = {
            "password": bcrypt.generate_password_hash(pw).decode(),
            "role": role
        }

    return render_template("admin_users.html", users=users)

# --------------------------------------
# AI CONSOLE (ADMIN ONLY)
# --------------------------------------

@app.route("/admin/ai", methods=["GET", "POST"])
def ai_console():
    if not admin_only():
        return redirect("/dashboard")

    output = ""

    if request.method == "POST":
        prompt = request.form["prompt"]
        output = "AI replies will work once API key is added."

    return render_template("admin_ai_console.html", output=output)

# --------------------------------------
# FACEBOOK POLLING PLACEHOLDER
# --------------------------------------

@app.route("/poll_test")
def poll_test():
    """Simulated post detection until live Facebook integration"""
    fake_post = {
        "id": str(uuid4()),
        "text": "My house has mould issues, what should I do?",
        "type": "advice"
    }
    pending_posts.append(fake_post)

    return "Fake post added!"

# --------------------------------------
# START
# --------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

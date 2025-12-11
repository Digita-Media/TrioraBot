import os
import time
import requests
from flask import Flask, request

app = Flask(__name__)

# ------------------------------------------------
# CONFIG
# ------------------------------------------------
VERIFY_TOKEN = "triora_verify_2025"
PAGE_ACCESS_TOKEN = os.getenv("USER_ACCESS_TOKEN")   # long-lived token you will set in Replit
GROUP_ID = "849838074302350"  # group ID you provided

# ------------------------------------------------
# KEYWORD AUTO-REPLIES
# ------------------------------------------------
KEYWORD_REPLIES = {
    ("mould", "black mould", "black spots"): """Thanks for sharing your post. Mould can appear for a variety of reasons, and understanding the underlying moisture source is important.

If you’d like help identifying possible causes or next steps, our team can assist:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk""",

    ("condensation", "wet windows", "moisture"): """Thanks for your post. Condensation can happen in different situations and may be linked to a number of contributing factors.

If you'd like some advice on managing moisture or exploring potential causes, we're here to help:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk""",

    ("leak", "leaking", "water ingress"): """Thanks for sharing. Moisture from leaks or water ingress can come from various sources, so gathering a bit more information is usually helpful.

If you'd like support in working out what might be happening, please feel free to contact us:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk""",
}

GENERIC_FALLBACK = """Thanks for your post! Damp and mould issues can have a range of causes, and getting the right advice early can make a big difference.

If you’d like some guidance, feel free to contact our team at Triora Damp & Mould:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk"""

# ------------------------------------------------
# WEBHOOK ENDPOINTS
# ------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return "Triora Bot is running!", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification token mismatch", 403

@app.route("/webhook", methods=["POST"])
def receive_webhook():
    data = request.get_json()
    print("Webhook Received:", data)
    return "EVENT_RECEIVED", 200

# ------------------------------------------------
# REPLY FUNCTION
# ------------------------------------------------
def send_comment(post_id, message):
    url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    payload = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    r = requests.post(url, data=payload)
    print("Reply sent:", r.text)

# ------------------------------------------------
# KEYWORD MATCHING
# ------------------------------------------------
def get_reply_for_text(text):
    text_low = text.lower()
    for keywords, reply in KEYWORD_REPLIES.items():
        if any(k in text_low for k in keywords):
            return reply
    return GENERIC_FALLBACK

# ------------------------------------------------
# POLLING (ONE-SHOT VERSION FOR REPLIT)
# ------------------------------------------------
seen_posts = set()

def poll_group_once():
    print("📡 Polling Facebook group feed...")

    url = f"https://graph.facebook.com/v17.0/{GROUP_ID}/feed"
    params = {"access_token": PAGE_ACCESS_TOKEN}

    r = requests.get(url, params=params)
    data = r.json()
    print("FB Response:", data)

    if "data" not in data:
        print("⚠ No feed data returned:", data)
        return {"status": "error", "details": data}

    for post in data["data"]:
        post_id = post.get("id")
        message = post.get("message", "")

        if not post_id:
            continue

        if post_id in seen_posts:
            continue

        seen_posts.add(post_id)

        print(f"📝 New post detected: {post_id} — {message}")

        reply = get_reply_for_text(message)
        send_comment(post_id, reply)

    return {"status": "ok", "handled": len(seen_posts)}

# ------------------------------------------------
# PUBLIC ENDPOINT TRIGGERED BY UPTIMEROBOT
# ------------------------------------------------
@app.route("/poll", methods=["GET"])
def poll_route():
    result = poll_group_once()
    return result, 200

# ------------------------------------------------
# RUN FLASK (NO BACKGROUND THREADS!)
# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

from flask import Flask, request
import requests
import os

app = Flask(__name__)

# ------------------------------------------------
# CONFIG
# ------------------------------------------------
VERIFY_TOKEN = "triora_verify_2025"
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")  # ← PAGE TOKEN (correct)

# ------------------------------------------------
# KEYWORDS + REPLIES
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

    ("chimney", "chimney breast"): """Thanks for your post. Damp around chimney breasts can occur for several different reasons, and understanding the context often helps determine next steps.

If you'd like more guidance, our team can offer support:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk/chimney-damp""",

    ("landlord", "renting"): """Thanks for your post. Damp and mould in rented properties can have different causes, and responsibilities can vary depending on the situation.

If you need guidance relating to your circumstances, feel free to reach out:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk""",

    ("rising damp",): """Thanks for sharing. Issues described as rising damp can have a number of potential explanations, and further details usually help determine what’s going on.

If you'd like some guidance, our specialists can help point you in the right direction:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk""",

    ("damp smell", "musty odour"): """Thanks for your post. A damp or musty smell can sometimes indicate moisture in hidden areas, but there are several possible causes.

If you'd like support in exploring this further, feel free to get in touch:
📞 +44 (0)1782 898444
✉️ dminfo@triora.co.uk
🌐 https://trioradampandmould.co.uk""",

    ("ventilation", "airflow", "extractor"): """Thanks for sharing. Ventilation can play a role in managing moisture levels, but each situation is different and may benefit from personalised guidance.

If you'd like information tailored to your property, our team can help:
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
# ROUTES
# ------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return "Triora Bot is running!", 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Facebook webhook verification."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification token mismatch", 403


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    """Handle incoming Group Feed events."""
    data = request.get_json()
    print("Webhook Received:", data)

    if "entry" in data:
        for entry in data["entry"]:
            for change in entry.get("changes", []):
                if change.get("field") == "feed":   # <-- Group feed posts
                    value = change.get("value", {})
                    if value.get("item") == "post":
                        post_id = value.get("post_id")
                        message = value.get("message", "")

                        reply_to_post(post_id, message)

    return "EVENT_RECEIVED", 200


# ------------------------------------------------
# REPLY LOGIC
# ------------------------------------------------

def reply_to_post(post_id, message):
    """Detect keywords and post the appropriate reply."""
    msg = message.lower()

    reply_text = GENERIC_FALLBACK

    for keywords, response in KEYWORD_REPLIES.items():
        if any(k in msg for k in keywords):
            reply_text = response
            break

    url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    payload = {
        "message": reply_text,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    response = requests.post(url, data=payload)
    print("Reply sent:", response.text)


# ------------------------------------------------
# RUN APP
# ------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

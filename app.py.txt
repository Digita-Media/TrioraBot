from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

VERIFY_TOKEN = "triora_verify_2025"   # <-- you can change this
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")  # will add later


@app.route("/", methods=["GET"])
def home():
    return "Triora Bot is running!", 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Webhook verification (Meta calls this first)"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    else:
        return "Verification token mismatch", 403


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    """Receive events from Group feed"""
    data = request.get_json()

    print("Webhook Received:", data)

    # Ensure this is a group post event
    if "entry" in data:
        for entry in data["entry"]:
            changes = entry.get("changes", [])
            for change in changes:
                if change.get("field") == "feed":
                    value = change.get("value", {})

                    if value.get("item") == "post":
                        post_id = value.get("post_id")
                        message = value.get("message", "")

                        print(f"New post detected: {message}")

                        reply_to_post(post_id, message)

    return "EVENT_RECEIVED", 200


def reply_to_post(post_id, message):
    """Send automatic reply based on keywords"""
    default_reply = (
        "Thanks for your post! For expert damp & mould guidance visit: "
        "https://trioradampandmould.co.uk"
    )

    # Example keyword logic (you can expand this later)
    if "chimney" in message.lower():
        reply = (
            "It looks like you're asking about chimney damp issues. "
            "Here’s a guide to help: https://trioradampandmould.co.uk/chimney-damp"
        )
    elif "landlord" in message.lower():
        reply = (
            "Landlord damp responsibility info can be found here: "
            "https://trioradampandmould.co.uk/landlord-support"
        )
    else:
        reply = default_reply

    url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    payload = {"message": reply, "access_token": PAGE_ACCESS_TOKEN}

    response = requests.post(url, data=payload)

    print("Reply sent:", response.text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

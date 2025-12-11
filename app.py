import os
import time
import json
import requests
from flask import Flask

app = Flask(__name__)

GROUP_ID = "849838074302350"
PAGE_ACCESS_TOKEN = os.getenv("USER_ACCESS_TOKEN")
POLL_INTERVAL = 30  # seconds

STATE_FILE = "state.json"

# Load or create state file
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"replied_posts": []}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# Function to post a reply as the Page
def reply_to_post(post_id, message):
    url = f"https://graph.facebook.com/v18.0/{post_id}/comments"
    params = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN
    }
    r = requests.post(url, params=params)
    print("Reply Response:", r.text)
    return r.status_code == 200

# Polling function (checks new group posts)
def poll_group_posts():
    state = load_state()
    replied_posts = state.get("replied_posts", [])

    url = f"https://graph.facebook.com/v18.0/{GROUP_ID}/feed"
    params = {
        "fields": "id,message,from,created_time",
        "access_token": PAGE_ACCESS_TOKEN
    }

    response = requests.get(url, params=params).json()
    print("Poll Response:", response)

    if "data" not in response:
        print("No data found in group feed response.")
        return

    for post in response["data"]:
        post_id = post.get("id")
        message = post.get("message", "")
        author = post.get("from", {}).get("name", "")

        # Skip posts already replied to
        if post_id in replied_posts:
            continue

        # Skip posts from your own page to avoid loops
        if author.lower().startswith("triora damp"):
            continue

        # Check if post contains mould keywords
        keywords = ["mould", "damp", "condensation", "mold"]
        if any(keyword in message.lower() for keyword in keywords):
            reply_text = (
                "Hi! Thanks for sharing. It looks like you're having an issue with mould or damp. "
                "Please send us a message on our page so we can help you further!"
            )

            if reply_to_post(post_id, reply_text):
                replied_posts.append(post_id)

    # Save updated state
    state["replied_posts"] = replied_posts
    save_state(state)

# Background loop
def start_polling():
    while True:
        try:
            poll_group_posts()
        except Exception as e:
            print("Error during polling:", e)
        time.sleep(POLL_INTERVAL)

@app.route("/")
def home():
    return "Triora Group Bot is running."

if __name__ == "__main__":
    # Start polling loop
    start_polling()

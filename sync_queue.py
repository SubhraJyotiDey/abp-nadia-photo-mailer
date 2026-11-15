"""
Generates queue.json for GitHub Pages static dashboard.
Scans @pixell.poet, checks sent_history.json, and produces queue.json.
"""

import os
import json
import instaloader
from dotenv import load_dotenv

load_dotenv()

HISTORY_FILE = "sent_history.json"
SETTINGS_FILE = "settings.json"
QUEUE_FILE = "queue.json"
DEFAULT_USER = "pixell.poet"

def sync():
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception as e:
            print(f"Error loading {HISTORY_FILE}: {e}")

    sent_keys = set(history.get("posts", {}).keys())

    settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            pass

    custom_captions = settings.get("custom_captions", {})

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False
    )
    username = os.environ.get("INSTAGRAM_USERNAME", DEFAULT_USER)

    print(f"[INFO] Scanning posts for @{username} to update queue.json...")
    profile = instaloader.Profile.from_username(L.context, username)

    queue = []
    count = 0
    for post in profile.get_posts():
        count += 1
        if count > 100:
            break
        if post.shortcode in sent_keys:
            continue
        if post.is_video or post.typename != "GraphImage":
            continue

        caption = custom_captions.get(post.shortcode, "")

        queue.append({
            "shortcode": post.shortcode,
            "date_utc": post.date_utc.strftime("%d %b %Y, %I:%M %p"),
            "image_url": post.url,
            "instagram_url": f"https://www.instagram.com/p/{post.shortcode}/",
            "custom_caption": caption,
            "is_next": len(queue) == 0
        })

        if len(queue) >= 10:
            break

    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "last_synced": profile.get_posts_count() if hasattr(profile, 'get_posts_count') else None,
            "queue": queue
        }, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Wrote {len(queue)} items to {QUEUE_FILE}.")
    if queue:
        print(f"[NEXT CANDIDATE] {queue[0]['shortcode']} ({queue[0]['date_utc']})")

if __name__ == "__main__":
    sync()

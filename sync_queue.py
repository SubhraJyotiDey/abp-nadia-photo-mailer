"""
Generates queue.json for GitHub Pages static dashboard.
Scans @pixell.poet, checks sent_history.json, and produces queue.json.

Uses two strategies:
1. Full profile scrape via Instaloader (gets fresh CDN URLs, but may be blocked)
2. Lightweight edge-based scrape (uses profile edge data with display_url,
   avoids per-post metadata fetches that trigger rate limits)
"""

import os
import json
import requests
import instaloader
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

HISTORY_FILE = "sent_history.json"
SETTINGS_FILE = "settings.json"
QUEUE_FILE = "queue.json"
DEFAULT_USER = "pixell.poet"


def load_sent_keys():
    """Load set of already sent/skipped shortcodes."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            return set(history.get("posts", {}).keys())
        except Exception as e:
            print(f"Error loading {HISTORY_FILE}: {e}")
    return set()


def load_custom_captions():
    """Load custom captions from settings."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            return settings.get("custom_captions", {})
        except Exception:
            pass
    return {}


def strategy_full_scrape(L, username, sent_keys, custom_captions):
    """
    Strategy 1: Full Instaloader profile scrape.
    Gets the highest quality URLs but each post triggers a metadata fetch.
    """
    print(f"[INFO] Strategy 1: Full profile scrape for @{username}...")
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

        if len(queue) >= 15:
            break

    return queue


def strategy_graphql_edge(username, sent_keys, custom_captions):
    """
    Strategy 2: Use Instagram's public GraphQL endpoint to get the profile edge data.
    This returns display_url for each post without needing per-post metadata fetches.
    Less likely to be rate-limited.
    """
    print(f"[INFO] Strategy 2: GraphQL edge scrape for @{username}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "X-IG-App-ID": "936619743392459",
    }

    # Get user ID first
    resp = requests.get(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        headers=headers,
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()

    user = data.get("data", {}).get("user", {})
    edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])

    queue = []
    for edge in edges:
        node = edge.get("node", {})
        shortcode = node.get("shortcode", "")
        if shortcode in sent_keys:
            continue
        typename = node.get("__typename", "")
        is_video = node.get("is_video", False)
        if is_video or typename != "GraphImage":
            continue

        display_url = node.get("display_url", "")
        timestamp = node.get("taken_at_timestamp", 0)
        date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%d %b %Y, %I:%M %p") if timestamp else ""

        caption = custom_captions.get(shortcode, "")
        queue.append({
            "shortcode": shortcode,
            "date_utc": date_str,
            "image_url": display_url,
            "instagram_url": f"https://www.instagram.com/p/{shortcode}/",
            "custom_caption": caption,
            "is_next": len(queue) == 0
        })

        if len(queue) >= 15:
            break

    return queue


def sync():
    sent_keys = load_sent_keys()
    custom_captions = load_custom_captions()
    username = os.environ.get("INSTAGRAM_USERNAME", DEFAULT_USER)

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False
    )

    queue = None

    # Try Strategy 1: Full Instaloader scrape
    try:
        queue = strategy_full_scrape(L, username, sent_keys, custom_captions)
        if queue:
            print(f"[SUCCESS] Strategy 1 succeeded with {len(queue)} items.")
    except Exception as e:
        print(f"[WARN] Strategy 1 failed: {e}")

    # Try Strategy 2: GraphQL edge if Strategy 1 failed
    if not queue:
        try:
            queue = strategy_graphql_edge(username, sent_keys, custom_captions)
            if queue:
                print(f"[SUCCESS] Strategy 2 succeeded with {len(queue)} items.")
        except Exception as e:
            print(f"[WARN] Strategy 2 also failed: {e}")

    # Write results
    if queue:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_synced": datetime.now(timezone.utc).isoformat(), "queue": queue}, f, indent=2, ensure_ascii=False)
        print(f"[SUCCESS] Wrote {len(queue)} items to {QUEUE_FILE}.")
        if queue:
            print(f"[NEXT CANDIDATE] {queue[0]['shortcode']} ({queue[0]['date_utc']})")
    else:
        print(f"[WARN] sync_queue: All strategies failed. queue.json not updated.")


if __name__ == "__main__":
    sync()

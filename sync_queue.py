"""
Generates queue.json and pre-caches images in queue_images/ for GitHub Pages static dashboard.
Scans @pixell.poet using Instagram's Polaris web client timeline,
checks sent_history.json, downloads images locally to prevent CDN expiry, and produces queue.json.
"""

import os
import json
import re
import requests
from datetime import datetime, timezone
import instaloader
from dotenv import load_dotenv

load_dotenv()

HISTORY_FILE = "sent_history.json"
SETTINGS_FILE = "settings.json"
QUEUE_FILE = "queue.json"
QUEUE_IMAGES_DIR = "queue_images"
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


def format_date_from_caption(acc_caption: str) -> str:
    """Extract human-readable date from accessibility caption like 'Photo by Pixel Poet on December 07, 2025.'"""
    if not acc_caption:
        return ""
    m = re.search(r"on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", acc_caption)
    if m:
        return m.group(1)
    return acc_caption


def scrape_polaris_timeline(username: str, max_items: int = 35):
    """
    Extracts posts from Instagram's polaris_ordered_timeline_connection without
    per-post metadata queries, avoiding rate-limiting while getting fresh CDN URLs.
    """
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
    )

    page = L.context.get_page_data(f"{username}/")
    user = next((d["xig_user_by_username"] for d in page if "polaris_ordered_timeline_connection" in (d.get("xig_user_by_username") or {})), None)
    if not user:
        raise ValueError(f"Could not find polaris_ordered_timeline_connection for {username}")

    user_id = user.get("id")
    timeline = user.get("polaris_ordered_timeline_connection", {})
    edges = list(timeline.get("edges", []))
    page_info = timeline.get("page_info", {})

    # Paginate to collect enough candidate posts
    pages_fetched = 1
    while page_info.get("has_next_page") and len(edges) < 60 and pages_fetched < 5:
        end_cursor = page_info.get("end_cursor")
        if not end_cursor:
            break
        try:
            resp = L.context.doc_id_graphql_query(
                "28904005159232689",
                {
                    "id": user_id,
                    "after": end_cursor,
                    "first": 12,
                    "__relay_internal__pv__PolarisSEOIsCrawlerrelayprovider": False,
                },
                web_api=True,
            )
            conn = (resp.get("data") or {}).get("node", {}).get("polaris_ordered_timeline_connection")
            if not conn:
                break
            new_edges = conn.get("edges", [])
            if not new_edges:
                break
            edges.extend(new_edges)
            page_info = conn.get("page_info", {})
            pages_fetched += 1
        except Exception as p_err:
            print(f"[WARN] Pagination error on page {pages_fetched + 1}: {p_err}")
            break

    return edges


def sync():
    sent_keys = load_sent_keys()
    custom_captions = load_custom_captions()
    username = os.environ.get("INSTAGRAM_USERNAME", DEFAULT_USER)

    os.makedirs(QUEUE_IMAGES_DIR, exist_ok=True)

    print(f"[INFO] Scanning timeline for @{username}...")
    try:
        edges = scrape_polaris_timeline(username)
        print(f"[INFO] Retrieved {len(edges)} total timeline items.")
    except Exception as e:
        print(f"[ERROR] Failed to fetch timeline for @{username}: {e}")
        return

    queue = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for edge in edges:
        node = edge.get("node", {})
        code = node.get("code")
        if not code or code in sent_keys:
            continue

        media_type = node.get("media_type")
        typename = node.get("__typename")

        # STRICT FILTER: Single image only
        # media_type 1 is Photo; 2 is Video/Reel; 8 is Carousel
        if media_type != 1 or typename != "XIGPolarisImageMedia" or node.get("carousel_media_count"):
            continue

        display_uri = node.get("display_uri")
        if not display_uri:
            continue

        # Download and cache image locally in queue_images/ to guarantee zero CDN expiry
        img_rel_path = f"{QUEUE_IMAGES_DIR}/{code}.jpg"
        if not os.path.exists(img_rel_path) or os.path.getsize(img_rel_path) == 0:
            try:
                r = requests.get(display_uri, headers=headers, timeout=20)
                if r.status_code == 200:
                    with open(img_rel_path, "wb") as img_f:
                        img_f.write(r.content)
            except Exception as dl_err:
                print(f"[WARN] Could not cache image locally for {code}: {dl_err}")

        date_str = format_date_from_caption(node.get("accessibility_caption", ""))
        caption = custom_captions.get(code, "")

        queue.append({
            "shortcode": code,
            "date_utc": date_str or "Recent Post",
            "local_image": img_rel_path if os.path.exists(img_rel_path) else None,
            "image_url": display_uri,
            "instagram_url": f"https://www.instagram.com/p/{code}/",
            "custom_caption": caption,
            "is_next": len(queue) == 0,
        })

        if len(queue) >= 30:
            break

    if queue:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "queue": queue
            }, f, indent=2, ensure_ascii=False)

        print(f"[SUCCESS] Wrote {len(queue)} cached single-photo items to {QUEUE_FILE}.")
        print(f"[NEXT CANDIDATE] {queue[0]['shortcode']} ({queue[0]['date_utc']})")
    else:
        print("[WARN] No unsent single photos found to add to queue.")


if __name__ == "__main__":
    sync()

"""
Daily Instagram Photo Mailer for ABP Nadia
Author: Antigravity Assistant for Shuvro Jyoti Dey
Target Account: @pixell.poet
Destination: edit.nadia@abp.in
"""

import os
import sys
import json
import io
import re
import base64
import argparse
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header

import requests
from PIL import Image
from dotenv import load_dotenv
import instaloader

# Load .env file if present
load_dotenv()

HISTORY_FILE = "sent_history.json"
DEFAULT_INSTAGRAM_USER = "pixell.poet"
DEFAULT_RECIPIENT = "edit.nadia@abp.in"
SUBJECT = "আপনার লেন্সে (শুভ্র জ্যোতি দে)"

EMAIL_TEMPLATE = """ছবির নাম : {caption}
ক্যামেরা: রেডমি নোট ১০ প্রো 
নাম : শুভ্র জ্যোতি দে 
ঠিকানা : রানাঘাট, নদিয়া।"""


def load_history(filepath: str = HISTORY_FILE) -> dict:
    """Loads the history of previously sent posts."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Error reading {filepath}: {e}. Creating new history structure.")
    return {"last_updated": None, "sent_count": 0, "posts": {}}


def save_history(history: dict, filepath: str = HISTORY_FILE) -> None:
    """Saves updated history to JSON file."""
    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    history["sent_count"] = len(history.get("posts", {}))
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Updated {filepath} with {history['sent_count']} total sent posts.")


def init_instaloader() -> instaloader.Instaloader:
    """Initializes Instaloader with optional session support."""
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )

    # Optional: If session is provided via environment variable (useful on GitHub Actions)
    session_b64 = os.environ.get("INSTAGRAM_SESSION_BASE64")
    if session_b64:
        try:
            session_bytes = base64.b64decode(session_b64)
            temp_session_file = "temp_session"
            with open(temp_session_file, "wb") as f:
                f.write(session_bytes)
            username = os.environ.get("INSTAGRAM_SESSION_USER", DEFAULT_INSTAGRAM_USER)
            L.load_session_from_file(username, temp_session_file)
            print(f"[INFO] Loaded Instagram session for user {username}")
            if os.path.exists(temp_session_file):
                os.remove(temp_session_file)
        except Exception as e:
            print(f"[WARN] Failed to load INSTAGRAM_SESSION_BASE64: {e}. Proceeding anonymously.")

    return L


def clean_bengali_caption(text: str) -> str:
    """
    Cleans up LLM output to strictly extract 1 or 2 Bengali words.
    Removes prefixes like 'ছবির নাম :', quotation marks, brackets, English text, etc.
    """
    if not text:
        return "ছেলেবেলা"

    # Remove standard prefix labels
    cleaned = re.sub(
        r"^(ছবির\s*নাম|শিরোনাম|নাম|ক্যাপশন)\s*[:ঃ\-—]\s*", "", text, flags=re.IGNORECASE
    )

    # Remove anything inside parentheses or brackets
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)

    # Remove non-Bengali characters except whitespace (Bengali Unicode range: \u0980-\u09FF)
    cleaned = re.sub(r"[^\u0980-\u09FF\s]", "", cleaned).strip()

    words = cleaned.split()
    if not words:
        return "ছেলেবেলা"

    # Ensure strictly 1 or 2 words maximum
    return " ".join(words[:2])


def generate_bengali_caption(image_bytes: bytes, gemini_api_key: str) -> str:
    """
    Analyzes the image with Google Gemini API and generates
    a 1-2 word artistic Bengali caption.
    """
    prompt = (
        "You are an artistic Bengali poet and photography curator.\n"
        "Carefully analyze this photograph. Craft an evocative, poetic, and artistic title or caption "
        "in Bengali (বাংলা) that captures its mood, emotional depth, nostalgia, or atmosphere.\n"
        "Examples of desired tone: ছেলেবেলা, নিস্তব্ধতা, একাকীত্ব, জলছবি, আলোছায়া, স্মৃতিচারণ, জীবনযুদ্ধ, মেঠোপথ, মায়াবী ভোর, নদীমাতৃক।\n\n"
        "STRICT REQUIREMENTS:\n"
        "1. Output MUST be ONLY 1 or 2 words in Bengali script (বাংলা অক্ষর).\n"
        "2. Do NOT include quotation marks, punctuation, English translations, or explanations.\n"
        "3. Output strictly the 1-2 Bengali words and nothing else."
    )

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Try modern google-genai SDK first
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_api_key)

        # Attempt with gemini-2.5-flash or gemini-1.5-flash
        model_name = "gemini-2.5-flash"
        try:
            response = client.models.generate_content(
                model=model_name, contents=[image, prompt]
            )
            raw_text = response.text
        except Exception:
            model_name = "gemini-1.5-flash"
            response = client.models.generate_content(
                model=model_name, contents=[image, prompt]
            )
            raw_text = response.text

        caption = clean_bengali_caption(raw_text)
        print(f"[INFO] Generated caption using {model_name}: {caption} (raw: {raw_text.strip()})")
        return caption

    except ImportError:
        pass
    except Exception as e:
        print(f"[WARN] Error with google-genai client: {e}. Trying legacy google-generativeai SDK...")

    # Fallback to legacy google-generativeai SDK
    try:
        import google.generativeai as legacy_genai

        legacy_genai.configure(api_key=gemini_api_key)
        model = legacy_genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([prompt, image])
        raw_text = response.text
        caption = clean_bengali_caption(raw_text)
        print(f"[INFO] Generated caption using legacy SDK: {caption} (raw: {raw_text.strip()})")
        return caption
    except Exception as e:
        print(f"[ERROR] Failed to generate caption via Gemini: {e}")
        return "ছেলেবেলা"  # Poetic fallback default


def prepare_jpeg_attachment(image_bytes: bytes) -> bytes:
    """Converts any image (WebP, PNG) into a high-quality standard JPEG buffer."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def send_email(
    gmail_user: str,
    gmail_app_password: str,
    recipient_email: str,
    caption: str,
    jpeg_bytes: bytes,
    filename: str = "photo_submission.jpg",
) -> None:
    """Composes and dispatches the email via Gmail SMTP with attachment."""
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = recipient_email
    msg["Subject"] = Header(SUBJECT, "utf-8")

    body_text = EMAIL_TEMPLATE.format(caption=caption)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    # Image attachment
    attachment = MIMEImage(jpeg_bytes, _subtype="jpeg")
    attachment.add_header(
        "Content-Disposition", "attachment", filename=filename
    )
    msg.attach(attachment)

    print(f"[INFO] Connecting to Gmail SMTP to send email to {recipient_email}...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_app_password)
            server.send_message(msg)
        print("[SUCCESS] Email sent successfully!")
    except Exception as e:
        print(f"[WARN] SMTP_SSL (port 465) failed: {e}. Retrying with STARTTLS (port 587)...")
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_app_password)
            server.send_message(msg)
        print("[SUCCESS] Email sent successfully via STARTTLS!")


def main():
    parser = argparse.ArgumentParser(description="Daily Instagram Photo Mailer for ABP Nadia")
    parser.add_argument("--dry-run", action="store_true", help="Fetch photo and generate caption without sending email or saving history")
    parser.add_argument("--test-email", type=str, default=None, help="Send email to this test address instead of ABP Nadia")
    parser.add_argument("--force-shortcode", type=str, default=None, help="Process a specific post shortcode for testing")
    parser.add_argument("--max-scan", type=int, default=500, help="Maximum number of posts to examine (default: 500)")
    args = parser.parse_args()

    # Load credentials
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    target_username = os.environ.get("INSTAGRAM_USERNAME", DEFAULT_INSTAGRAM_USER)
    recipient_email = args.test_email or os.environ.get("RECIPIENT_EMAIL", DEFAULT_RECIPIENT)

    if not args.dry_run:
        if not gmail_user or not gmail_app_password:
            sys.exit("[FATAL] GMAIL_USER and GMAIL_APP_PASSWORD environment variables are required.")
        if not gemini_api_key:
            sys.exit("[FATAL] GEMINI_API_KEY environment variable is required.")

    print(f"==================================================")
    print(f" Daily Instagram Photo Mailer")
    print(f" Profile: @{target_username}")
    print(f" Recipient: {recipient_email}")
    print(f" Dry Run Mode: {args.dry_run}")
    print(f"==================================================")

    history = load_history()
    sent_posts = history.get("posts", {})
    sent_shortcodes = set(sent_posts.keys())
    print(f"[INFO] Previously sent posts count: {len(sent_shortcodes)}")

    L = init_instaloader()

    try:
        print(f"[INFO] Fetching profile information for @{target_username}...")
        profile = instaloader.Profile.from_username(L.context, target_username)
    except Exception as e:
        sys.exit(f"[FATAL] Failed to access Instagram profile @{target_username}: {e}")

    target_post = None

    if args.force_shortcode:
        print(f"[INFO] Using forced shortcode: {args.force_shortcode}")
        try:
            target_post = instaloader.Post.from_shortcode(L.context, args.force_shortcode)
        except Exception as e:
            sys.exit(f"[FATAL] Could not retrieve post with shortcode {args.force_shortcode}: {e}")
    else:
        print(f"[INFO] Scanning posts sequentially (latest to oldest)...")
        count = 0
        for post in profile.get_posts():
            count += 1
            if count > args.max_scan:
                print(f"[WARN] Reached max scan limit ({args.max_scan} posts). Stopping.")
                break

            shortcode = post.shortcode

            # Check if previously sent
            if shortcode in sent_shortcodes:
                continue

            # Filter out videos and reels
            if post.is_video:
                print(f"[SKIP] Post {shortcode} is a video/reel.")
                continue

            # Filter out multi-photo carousels (GraphSidecar)
            if post.typename != "GraphImage":
                print(f"[SKIP] Post {shortcode} is type '{post.typename}' (not a single photo).")
                continue

            # Found the target post!
            target_post = post
            print(f"[MATCH] Found next unsent single photo post: {shortcode} (Posted: {post.date_utc} UTC)")
            break

    if not target_post:
        print("[INFO] No new unsent single photo found on profile. Nothing to send today.")
        return

    # Download image bytes directly from post.url
    print(f"[INFO] Downloading image from CDN...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(target_post.url, headers=headers, timeout=30)
        resp.raise_for_status()
        raw_image_bytes = resp.content
    except Exception as e:
        sys.exit(f"[FATAL] Failed to download image for post {target_post.shortcode}: {e}")

    # Convert to standard JPEG format
    jpeg_bytes = prepare_jpeg_attachment(raw_image_bytes)

    # Generate Bengali caption via Gemini
    if gemini_api_key:
        print("[INFO] Analyzing photo with Gemini to craft Bengali caption...")
        caption = generate_bengali_caption(jpeg_bytes, gemini_api_key)
    else:
        print("[WARN] GEMINI_API_KEY not provided (dry-run). Using sample caption 'ছেলেবেলা'.")
        caption = "ছেলেবেলা"

    # Display preview
    body_text = EMAIL_TEMPLATE.format(caption=caption)
    print("\n------------------- EMAIL PREVIEW -------------------")
    print(f"To: {recipient_email}")
    print(f"Subject: {SUBJECT}")
    print("Body:")
    print(body_text)
    print(f"Attachment: photo_{target_post.shortcode}.jpg ({len(jpeg_bytes)} bytes)")
    print("-----------------------------------------------------\n")

    if args.dry_run:
        print("[INFO] Dry run complete! No email sent and history not modified.")
        return

    # Dispatch Email
    send_email(
        gmail_user=gmail_user,
        gmail_app_password=gmail_app_password,
        recipient_email=recipient_email,
        caption=caption,
        jpeg_bytes=jpeg_bytes,
        filename=f"shuvro_jyoti_dey_{target_post.shortcode}.jpg",
    )

    # Record in history
    history.setdefault("posts", {})[target_post.shortcode] = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "caption": caption,
        "post_date_utc": target_post.date_utc.isoformat(),
        "instagram_url": f"https://www.instagram.com/p/{target_post.shortcode}/",
    }
    save_history(history)
    print(f"[SUCCESS] Successfully completed daily mailing for post {target_post.shortcode}!")


if __name__ == "__main__":
    main()

"""
Web Dashboard for ABP Nadia Daily Photo Mailer
Responsive for both Mobile and PC
"""

import os
import sys
import json
import io
import time
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template_string, jsonify, request, Response
from PIL import Image
from dotenv import load_dotenv
import instaloader

load_dotenv()

app = Flask(__name__)

HISTORY_FILE = "sent_history.json"
SETTINGS_FILE = "settings.json"
LOG_FILE = "mailer_log.txt"
DEFAULT_INSTAGRAM_USER = "pixell.poet"
DEFAULT_RECIPIENT = "edit.nadia@abp.in"

# In-memory queue cache
queue_cache = {
    "last_fetched": 0,
    "items": []
}


def get_ist_now():
    """Returns current datetime in Indian Standard Time (UTC+5:30)."""
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def load_settings():
    default_settings = {
        "mode": "approval",   # "auto" or "approval"
        "paused": True,       # True = paused
        "scheduled_time": "09:00",
        "recipient_email": DEFAULT_RECIPIENT,
        "custom_captions": {}
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception as e:
            print(f"Error loading {SETTINGS_FILE}: {e}")
    return default_settings


def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {HISTORY_FILE}: {e}")
    return {"last_updated": None, "sent_count": 0, "posts": {}}


def get_cached_or_fresh_queue(max_items=8, force_refresh=False):
    """Fetches and caches the next queued single photo posts."""
    now = time.time()
    # Cache for 10 minutes unless force_refresh is requested
    if not force_refresh and (now - queue_cache["last_fetched"] < 600) and queue_cache["items"]:
        return queue_cache["items"]

    history = load_history()
    sent_keys = set(history.get("posts", {}).keys())

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False
    )
    username = os.environ.get("INSTAGRAM_USERNAME", DEFAULT_INSTAGRAM_USER)

    try:
        profile = instaloader.Profile.from_username(L.context, username)
        items = []
        count = 0
        for post in profile.get_posts():
            count += 1
            if count > 80:
                break
            if post.shortcode in sent_keys:
                continue
            if post.is_video or post.typename != "GraphImage":
                continue

            items.append({
                "shortcode": post.shortcode,
                "date_utc": post.date_utc.strftime("%d %b %Y, %I:%M %p"),
                "image_url": post.url,
                "instagram_url": f"https://www.instagram.com/p/{post.shortcode}/"
            })
            if len(items) >= max_items:
                break

        queue_cache["items"] = items
        queue_cache["last_fetched"] = now
        return items
    except Exception as e:
        print(f"Error fetching Instagram queue: {e}")
        return queue_cache.get("items", [])


@app.route("/api/proxy-image")
def proxy_image():
    """Proxies Instagram CDN images to bypass referrer/CORS restrictions on mobile & browsers."""
    url = request.args.get("url")
    if not url:
        return "Missing URL", 400
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        return Response(resp.content, mimetype=resp.headers.get("Content-Type", "image/jpeg"))
    except Exception as e:
        return str(e), 500


@app.route("/api/status")
def get_status():
    settings = load_settings()
    history = load_history()

    # Calculate next 9:00 AM IST
    ist_now = get_ist_now()
    scheduled_hour = 9
    scheduled_minute = 0
    next_run = ist_now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    if ist_now >= next_run:
        next_run += timedelta(days=1)

    diff_seconds = max(0, int((next_run - ist_now).total_seconds()))

    today_str = ist_now.strftime("%d-%m-%Y")
    expected_filename = f"SubhraJyotiDey_{today_str}.jpg"

    return jsonify({
        "mode": settings.get("mode", "approval"),
        "paused": settings.get("paused", True),
        "scheduled_time": "09:00 AM IST",
        "next_run_iso": next_run.isoformat(),
        "next_run_display": next_run.strftime("%d %b %Y, 09:00 AM IST"),
        "countdown_seconds": diff_seconds,
        "sent_count": len(history.get("posts", {})),
        "expected_filename": expected_filename,
        "recipient": settings.get("recipient_email", DEFAULT_RECIPIENT)
    })


@app.route("/api/queue")
def get_queue():
    force = request.args.get("refresh", "false").lower() == "true"
    items = get_cached_or_fresh_queue(max_items=8, force_refresh=force)
    settings = load_settings()
    custom_captions = settings.get("custom_captions", {})

    for idx, item in enumerate(items):
        item["custom_caption"] = custom_captions.get(item["shortcode"], "")
        item["is_next"] = (idx == 0)

    return jsonify({"queue": items})


@app.route("/api/history")
def get_history():
    history = load_history()
    posts = history.get("posts", {})
    records = []
    for sc, p in posts.items():
        records.append({
            "shortcode": sc,
            "caption": p.get("caption", ""),
            "sent_at": p.get("sent_at", ""),
            "post_date_utc": p.get("post_date_utc", ""),
            "instagram_url": p.get("instagram_url", f"https://www.instagram.com/p/{sc}/")
        })
    records.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
    return jsonify({"history": records})


@app.route("/api/caption/override", methods=["POST"])
def override_caption():
    data = request.json or {}
    shortcode = data.get("shortcode")
    caption = data.get("caption", "").strip()
    if not shortcode:
        return jsonify({"error": "Missing shortcode"}), 400

    settings = load_settings()
    settings.setdefault("custom_captions", {})[shortcode] = caption
    save_settings(settings)
    return jsonify({"success": True, "caption": caption})


@app.route("/api/caption/generate", methods=["POST"])
def generate_caption():
    """Generates a live Gemini caption for preview."""
    data = request.json or {}
    image_url = data.get("image_url")
    if not image_url:
        return jsonify({"error": "Missing image_url"}), 400

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        return jsonify({"caption": "ছেলেবেলা", "source": "default"})

    try:
        from main import generate_bengali_caption, prepare_jpeg_attachment
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(image_url, headers=headers, timeout=20)
        resp.raise_for_status()
        jpeg_bytes = prepare_jpeg_attachment(resp.content)
        caption = generate_bengali_caption(jpeg_bytes, gemini_api_key)
        return jsonify({"caption": caption, "source": "gemini"})
    except Exception as e:
        return jsonify({"error": str(e), "caption": "ছেলেবেলা"}), 500


@app.route("/api/settings/update", methods=["POST"])
def update_settings():
    data = request.json or {}
    settings = load_settings()

    if "mode" in data and data["mode"] in ["auto", "approval"]:
        settings["mode"] = data["mode"]
    if "paused" in data:
        settings["paused"] = bool(data["paused"])

    save_settings(settings)
    return jsonify({"success": True, "settings": settings})


@app.route("/api/send-now", methods=["POST"])
def send_now():
    """Triggers immediate dispatch of the next photo (requires user explicit confirmation)."""
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--force-send"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        # Invalidate queue cache so next photo updates
        queue_cache["last_fetched"] = 0

        if result.returncode == 0:
            return jsonify({"success": True, "output": result.stdout})
        else:
            return jsonify({"success": False, "error": result.stderr or result.stdout}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/logs")
def get_logs():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()[-40:]
                return jsonify({"logs": "".join(lines)})
        except Exception as e:
            return jsonify({"logs": f"Error reading logs: {e}"})
    return jsonify({"logs": "No logs recorded yet."})


# Dashboard HTML with Tailwind CSS, Lucide Icons, and responsive design
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="bn" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>আপনার লেন্সে | ABP Nadia Daily Photo Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@400;500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
            bengali: ['"Anek Bangla"', 'sans-serif'],
          },
          colors: {
            brand: {
              50: '#fff1f2',
              500: '#e11d48',
              600: '#be123c',
              700: '#9f1239',
            }
          }
        }
      }
    }
  </script>
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
    .bangla { font-family: 'Anek Bangla', sans-serif; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen pb-16 selection:bg-rose-500 selection:text-white">

  <!-- Header -->
  <header class="sticky top-0 z-40 bg-slate-900/80 backdrop-blur-md border-b border-slate-800">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/30">
          <i data-lucide="camera" class="w-5 h-5 text-white"></i>
        </div>
        <div>
          <h1 class="text-lg sm:text-xl font-bold tracking-tight bangla flex items-center gap-2">
            আপনার লেন্সে
            <span class="text-xs font-normal text-rose-400 bg-rose-950/60 border border-rose-800/60 px-2 py-0.5 rounded-full">ABP Nadia</span>
          </h1>
          <p class="text-xs text-slate-400">শুভ্র জ্যোতি দে • @pixell.poet</p>
        </div>
      </div>

      <!-- Controls & Status Badge -->
      <div class="flex items-center gap-2 sm:gap-3">
        <div id="statusBadge" class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-amber-950/50 text-amber-300 border border-amber-800/50">
          <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
          <span id="statusText">Paused</span>
        </div>

        <button onclick="togglePause()" id="pauseBtn" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
          <i data-lucide="play" class="w-3.5 h-3.5"></i>
          <span id="pauseBtnText">Resume</span>
        </button>

        <button onclick="loadAllData(true)" class="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition" title="Refresh Queue">
          <i data-lucide="refresh-cw" class="w-4 h-4"></i>
        </button>
      </div>
    </div>
  </header>

  <main class="max-w-6xl mx-auto px-4 sm:px-6 pt-6 space-y-8">

    <!-- Top Banner: Scheduled Mail Time & Countdown -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="bg-gradient-to-br from-slate-900 to-slate-800/80 p-5 rounded-2xl border border-slate-800 shadow-sm flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl bg-blue-950/80 text-blue-400 border border-blue-800/50 flex items-center justify-center shrink-0">
          <i data-lucide="clock" class="w-6 h-6"></i>
        </div>
        <div>
          <p class="text-xs text-slate-400 font-medium">Scheduled Daily Dispatch</p>
          <p class="text-base font-bold text-slate-100" id="scheduledTimeDisplay">09:00 AM IST</p>
          <p class="text-[11px] text-slate-400" id="nextRunDisplay">Tomorrow</p>
        </div>
      </div>

      <div class="bg-gradient-to-br from-slate-900 to-slate-800/80 p-5 rounded-2xl border border-slate-800 shadow-sm flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl bg-purple-950/80 text-purple-400 border border-purple-800/50 flex items-center justify-center shrink-0">
          <i data-lucide="hourglass" class="w-6 h-6"></i>
        </div>
        <div>
          <p class="text-xs text-slate-400 font-medium">Time Remaining</p>
          <p class="text-xl font-extrabold text-purple-300 tracking-wider font-mono" id="countdownTimer">-- : -- : --</p>
          <p class="text-[11px] text-slate-400">Until next automated dispatch</p>
        </div>
      </div>

      <div class="bg-gradient-to-br from-slate-900 to-slate-800/80 p-5 rounded-2xl border border-slate-800 shadow-sm flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl bg-emerald-950/80 text-emerald-400 border border-emerald-800/50 flex items-center justify-center shrink-0">
          <i data-lucide="shield-check" class="w-6 h-6"></i>
        </div>
        <div class="flex-1">
          <p class="text-xs text-slate-400 font-medium">Dispatch Mode</p>
          <div class="flex items-center justify-between mt-1">
            <span class="text-sm font-bold text-emerald-300" id="modeDisplayText">Manual Approval</span>
            <button onclick="toggleMode()" class="text-xs px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200">
              Switch
            </button>
          </div>
          <p class="text-[11px] text-slate-400 mt-0.5" id="modeSubText">Requires your approval before sending</p>
        </div>
      </div>
    </div>

    <!-- HERO SECTION: Next Photo to be Mailed -->
    <section class="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
      <div class="p-4 sm:p-6 border-b border-slate-800 flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
          <h2 class="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            📸 Next Photo to be Mailed
            <span class="text-xs font-medium px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700">Priority #1</span>
          </h2>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-slate-400">Recipient:</span>
          <code class="text-xs font-mono px-2 py-0.5 rounded bg-slate-950 text-rose-300 border border-slate-800" id="recipientDisplay">edit.nadia@abp.in</code>
        </div>
      </div>

      <div class="p-4 sm:p-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        <!-- Left: Image Preview -->
        <div class="lg:col-span-5 flex flex-col items-center">
          <div class="relative w-full aspect-square sm:aspect-[4/5] rounded-2xl overflow-hidden bg-slate-950 border border-slate-800 shadow-lg group">
            <img id="nextPhotoImage" src="" alt="Next Queued Photo" class="w-full h-full object-cover transition duration-300 group-hover:scale-105">
            <div id="imageLoading" class="absolute inset-0 bg-slate-950/80 flex flex-col items-center justify-center text-slate-400 text-sm gap-2">
              <i data-lucide="loader-2" class="w-6 h-6 animate-spin text-rose-500"></i>
              Loading next photo from Instagram...
            </div>
            <a id="igLink" href="#" target="_blank" class="absolute bottom-3 right-3 bg-slate-950/80 hover:bg-rose-600 text-white p-2.5 rounded-xl border border-slate-700 backdrop-blur-md transition shadow-md flex items-center gap-1.5 text-xs">
              <i data-lucide="external-link" class="w-4 h-4"></i>
              <span>View on Instagram</span>
            </a>
          </div>
          <p class="text-xs text-slate-400 mt-3 text-center flex items-center gap-1.5">
            <i data-lucide="calendar" class="w-3.5 h-3.5"></i>
            <span id="nextPhotoDate">--</span> • Post Shortcode: <span id="nextPhotoShortcode" class="font-mono text-slate-200">--</span>
          </p>
        </div>

        <!-- Right: Email Details, AI Caption & Actions -->
        <div class="lg:col-span-7 space-y-6">

          <!-- Artistic Bengali Caption Card -->
          <div class="p-6 rounded-2xl bg-gradient-to-br from-rose-950/40 via-slate-900 to-slate-900 border border-rose-900/40 shadow-inner space-y-4">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold tracking-wider uppercase text-rose-400 flex items-center gap-1.5">
                <i data-lucide="sparkles" class="w-4 h-4 text-rose-400"></i>
                AI Crafted Bengali Caption (ছবির নাম)
              </span>
              <button onclick="requestAiCaption()" id="regenBtn" class="text-xs text-slate-400 hover:text-rose-300 flex items-center gap-1">
                <i data-lucide="wand-2" class="w-3.5 h-3.5"></i>
                <span>Re-analyze</span>
              </button>
            </div>

            <div class="flex items-center justify-between gap-4">
              <div class="space-y-1">
                <h3 id="captionDisplay" class="text-3xl sm:text-4xl font-extrabold bangla text-rose-100 tracking-wide">
                  লোড হচ্ছে...
                </h3>
                <p class="text-xs text-slate-400">ছবির মেজাজ ও আবেগ অনুযায়ী জেমিনাই এআই দ্বারা তৈরি</p>
              </div>
            </div>

            <!-- Custom Override Input Field -->
            <div class="pt-3 border-t border-rose-900/30">
              <label class="block text-xs text-slate-400 mb-1.5">ক্যাপশন পরিবর্তন বা নিজের নাম দিন (Custom Override):</label>
              <div class="flex gap-2">
                <input type="text" id="customCaptionInput" placeholder="যেমন: ছেলেবেলা, জলছবি, নিস্তব্ধতা..." class="flex-1 bg-slate-950/80 border border-slate-700 rounded-xl px-3.5 py-2 text-sm text-slate-100 focus:outline-none focus:border-rose-500 bangla">
                <button onclick="saveCustomCaption()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition flex items-center gap-1.5 shrink-0">
                  <i data-lucide="save" class="w-3.5 h-3.5"></i>
                  <span>Save</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Email Preview Box -->
          <div class="p-5 rounded-2xl bg-slate-950/60 border border-slate-800 space-y-3 font-mono text-xs">
            <div class="flex items-center justify-between pb-2 border-b border-slate-800/80">
              <span class="text-slate-400 font-sans font-medium text-xs">Full Email Body Preview</span>
              <span class="text-slate-400 text-[11px] font-sans">বিষয়: আপনার লেন্সে (শুভ্র জ্যোতি দে)</span>
            </div>
            <div class="text-slate-300 space-y-1 bangla text-sm">
              <p>ছবির নাম : <span id="emailCaptionPreview" class="text-rose-400 font-bold">--</span></p>
              <p>ক্যামেরা: রেডমি নোট ১০ প্রো</p>
              <p>নাম : শুভ্র জ্যোতি দে</p>
              <p>ঠিকানা : রানাঘাট, নদিয়া।</p>
            </div>
            <div class="pt-2 border-t border-slate-800/80 flex items-center justify-between text-slate-400 text-[11px] font-sans">
              <span class="flex items-center gap-1">
                <i data-lucide="paperclip" class="w-3.5 h-3.5 text-rose-400"></i>
                Attachment:
              </span>
              <span id="attachmentNameDisplay" class="font-mono text-rose-300 font-semibold">SubhraJyotiDey_DD-MM-YYYY.jpg</span>
            </div>
          </div>

          <!-- Big Action Button: Send Now -->
          <div class="pt-2">
            <button onclick="openSendModal()" class="w-full py-4 rounded-2xl bg-gradient-to-r from-rose-600 via-rose-500 to-amber-500 hover:from-rose-500 hover:to-amber-400 text-white font-bold text-base shadow-xl shadow-rose-900/40 hover:shadow-rose-900/60 transition transform hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2">
              <i data-lucide="send" class="w-5 h-5"></i>
              <span>Send Today's Photo Now (Review & Dispatch)</span>
            </button>
            <p class="text-center text-xs text-slate-400 mt-2">
              🔒 Safety Protected: No email is ever sent without your explicit click on the confirmation modal.
            </p>
          </div>

        </div>
      </div>
    </section>

    <!-- SECTION 2: Upcoming Queue (Next Photos in Line) -->
    <section class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-base sm:text-lg font-bold text-white flex items-center gap-2">
          <i data-lucide="layers" class="w-5 h-5 text-purple-400"></i>
          Upcoming Queue (Next Photos in Sequence)
        </h2>
        <span class="text-xs text-slate-400" id="queueCount">-- photos queued</span>
      </div>

      <div id="queueGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4">
        <!-- Rendered via JS -->
      </div>
    </section>

    <!-- SECTION 3: Sent History Archive -->
    <section class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-base sm:text-lg font-bold text-white flex items-center gap-2">
          <i data-lucide="archive" class="w-5 h-5 text-emerald-400"></i>
          Sent History Gallery (ABP Nadia Submissions)
        </h2>
        <span class="text-xs text-slate-400" id="historyCount">-- sent</span>
      </div>

      <div id="historyGrid" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <!-- Rendered via JS -->
      </div>
    </section>

    <!-- SECTION 4: Live Execution Log -->
    <section class="bg-slate-900 p-5 rounded-2xl border border-slate-800 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <i data-lucide="terminal" class="w-4 h-4"></i>
          System Execution Logs (mailer_log.txt)
        </h3>
        <button onclick="fetchLogs()" class="text-xs text-slate-400 hover:text-slate-200">Refresh Logs</button>
      </div>
      <pre id="logContent" class="bg-slate-950 p-4 rounded-xl text-[11px] font-mono text-slate-300 max-h-48 overflow-y-auto whitespace-pre-wrap border border-slate-850">Loading logs...</pre>
    </section>

  </main>

  <!-- CONFIRMATION MODAL -->
  <div id="confirmModal" class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-3xl max-w-lg w-full p-6 space-y-6 shadow-2xl relative">
      <div class="flex items-center gap-3">
        <div class="w-12 h-12 rounded-2xl bg-rose-950/80 text-rose-400 border border-rose-800/60 flex items-center justify-center shrink-0">
          <i data-lucide="mail-check" class="w-6 h-6"></i>
        </div>
        <div>
          <h3 class="text-lg font-bold text-white">Confirm Email Dispatch</h3>
          <p class="text-xs text-slate-400">Are you sure you want to mail this photo to ABP Nadia now?</p>
        </div>
      </div>

      <div class="p-4 rounded-xl bg-slate-950 border border-slate-850 space-y-2 text-xs">
        <div class="flex justify-between text-slate-400">
          <span>Recipient:</span>
          <span class="text-slate-200 font-mono" id="modalRecipient">edit.nadia@abp.in</span>
        </div>
        <div class="flex justify-between text-slate-400">
          <span>Subject:</span>
          <span class="text-slate-200 font-mono">আপনার লেন্সে (শুভ্র জ্যোতি দে)</span>
        </div>
        <div class="flex justify-between text-slate-400">
          <span>ছবির নাম (Caption):</span>
          <span class="text-rose-400 font-bold bangla text-sm" id="modalCaption">--</span>
        </div>
        <div class="flex justify-between text-slate-400">
          <span>Attachment:</span>
          <span class="text-slate-200 font-mono" id="modalAttachment">--</span>
        </div>
      </div>

      <div id="sendProgress" class="hidden text-center py-2 text-xs text-rose-400 font-medium">
        <i data-lucide="loader-2" class="w-4 h-4 animate-spin inline mr-1.5"></i>
        Connecting to Gmail SMTP and sending email...
      </div>

      <div class="flex items-center justify-end gap-3 pt-2">
        <button onclick="closeSendModal()" id="cancelBtn" class="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition">
          Cancel
        </button>
        <button onclick="executeSendNow()" id="confirmSendBtn" class="px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow-lg shadow-rose-900/40 transition flex items-center gap-1.5">
          <i data-lucide="send" class="w-4 h-4"></i>
          <span>Yes, Send Email</span>
        </button>
      </div>
    </div>
  </div>

  <script>
    let currentNextItem = null;
    let countdownInterval = null;
    let currentCountdownSeconds = 0;

    async function loadAllData(forceRefresh = false) {
      await Promise.all([
        fetchStatus(),
        fetchQueue(forceRefresh),
        fetchHistory(),
        fetchLogs()
      ]);
      lucide.createIcons();
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Update mode & pause badges
        const isPaused = data.paused;
        const statusBadge = document.getElementById('statusBadge');
        const statusText = document.getElementById('statusText');
        const pauseBtn = document.getElementById('pauseBtn');
        const pauseBtnText = document.getElementById('pauseBtnText');

        if (isPaused) {
          statusBadge.className = "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-amber-950/60 text-amber-300 border border-amber-800/60";
          statusBadge.children[0].className = "w-2 h-2 rounded-full bg-amber-400";
          statusText.textContent = "Safety Paused";
          pauseBtnText.textContent = "Resume Auto";
        } else {
          statusBadge.className = "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/60";
          statusBadge.children[0].className = "w-2 h-2 rounded-full bg-emerald-400 animate-pulse";
          statusText.textContent = "Active Scheduler";
          pauseBtnText.textContent = "Pause Sending";
        }

        // Mode display
        const modeText = document.getElementById('modeDisplayText');
        const modeSub = document.getElementById('modeSubText');
        if (data.mode === 'auto') {
          modeText.textContent = "Full Auto-pilot";
          modeText.className = "text-sm font-bold text-amber-400";
          modeSub.textContent = "Sends automatically at 9:00 AM daily";
        } else {
          modeText.textContent = "Manual Approval";
          modeText.className = "text-sm font-bold text-emerald-300";
          modeSub.textContent = "Requires your approval before sending";
        }

        document.getElementById('scheduledTimeDisplay').textContent = data.scheduled_time;
        document.getElementById('nextRunDisplay').textContent = data.next_run_display;
        document.getElementById('recipientDisplay').textContent = data.recipient;
        document.getElementById('attachmentNameDisplay').textContent = data.expected_filename;

        // Countdown setup
        currentCountdownSeconds = data.countdown_seconds;
        startCountdown();

      } catch (err) {
        console.error("Status fetch failed:", err);
      }
    }

    function startCountdown() {
      if (countdownInterval) clearInterval(countdownInterval);
      updateCountdownDisplay();
      countdownInterval = setInterval(() => {
        if (currentCountdownSeconds > 0) {
          currentCountdownSeconds--;
          updateCountdownDisplay();
        }
      }, 1000);
    }

    function updateCountdownDisplay() {
      const h = Math.floor(currentCountdownSeconds / 3600);
      const m = Math.floor((currentCountdownSeconds % 3600) / 60);
      const s = currentCountdownSeconds % 60;
      const pad = (n) => String(n).padStart(2, '0');
      document.getElementById('countdownTimer').textContent = `${pad(h)} : ${pad(m)} : ${pad(s)}`;
    }

    async function fetchQueue(forceRefresh = false) {
      try {
        const url = forceRefresh ? '/api/queue?refresh=true' : '/api/queue';
        const res = await fetch(url);
        const data = await res.json();
        const queue = data.queue || [];

        document.getElementById('queueCount').textContent = `${queue.length} upcoming single photos`;

        if (queue.length > 0) {
          currentNextItem = queue[0];
          renderNextPhoto(currentNextItem);

          // Render upcoming queue (items 1 onwards)
          const grid = document.getElementById('queueGrid');
          grid.innerHTML = '';
          queue.slice(1).forEach((item, i) => {
            const card = document.createElement('div');
            card.className = "bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm flex flex-col group hover:border-slate-700 transition";
            card.innerHTML = `
              <div class="aspect-square bg-slate-950 relative overflow-hidden">
                <img src="/api/proxy-image?url=${encodeURIComponent(item.image_url)}" class="w-full h-full object-cover group-hover:scale-105 transition duration-300">
                <span class="absolute top-2 left-2 text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-950/80 text-purple-300 border border-slate-800 backdrop-blur-md">
                  #${i + 2} in line
                </span>
              </div>
              <div class="p-2.5 text-xs flex flex-col justify-between flex-1">
                <div>
                  <p class="font-mono text-slate-300 font-semibold truncate">${item.shortcode}</p>
                  <p class="text-[10px] text-slate-400 mt-0.5">${item.date_utc}</p>
                </div>
                <a href="${item.instagram_url}" target="_blank" class="mt-2 text-[10px] text-slate-400 hover:text-rose-400 flex items-center gap-1">
                  <i data-lucide="external-link" class="w-3 h-3"></i> IG Post
                </a>
              </div>
            `;
            grid.appendChild(card);
          });
        }
      } catch (err) {
        console.error("Queue fetch failed:", err);
      }
    }

    async function renderNextPhoto(item) {
      document.getElementById('nextPhotoShortcode').textContent = item.shortcode;
      document.getElementById('nextPhotoDate').textContent = item.date_utc;
      document.getElementById('igLink').href = item.instagram_url;

      const img = document.getElementById('nextPhotoImage');
      const loader = document.getElementById('imageLoading');
      loader.classList.remove('hidden');

      img.onload = () => loader.classList.add('hidden');
      img.src = `/api/proxy-image?url=${encodeURIComponent(item.image_url)}`;

      // Caption handling
      if (item.custom_caption) {
        document.getElementById('captionDisplay').textContent = item.custom_caption;
        document.getElementById('emailCaptionPreview').textContent = item.custom_caption;
        document.getElementById('customCaptionInput').value = item.custom_caption;
      } else {
        // Request Gemini generation if needed
        requestAiCaption();
      }
    }

    async function requestAiCaption() {
      if (!currentNextItem) return;
      const captionDisplay = document.getElementById('captionDisplay');
      const emailPreview = document.getElementById('emailCaptionPreview');
      captionDisplay.textContent = "এআই বিশ্লেষণ করছে...";

      try {
        const res = await fetch('/api/caption/generate', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ image_url: currentNextItem.image_url })
        });
        const data = await res.json();
        const caption = data.caption || "ছেলেবেলা";
        captionDisplay.textContent = caption;
        emailPreview.textContent = caption;
      } catch (e) {
        captionDisplay.textContent = "ছেলেবেলা";
        emailPreview.textContent = "ছেলেবেলা";
      }
    }

    async function saveCustomCaption() {
      if (!currentNextItem) return;
      const customVal = document.getElementById('customCaptionInput').value.trim();
      if (!customVal) return alert("Please enter a valid Bengali caption!");

      try {
        const res = await fetch('/api/caption/override', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ shortcode: currentNextItem.shortcode, caption: customVal })
        });
        const data = await res.json();
        if (data.success) {
          document.getElementById('captionDisplay').textContent = customVal;
          document.getElementById('emailCaptionPreview').textContent = customVal;
          alert("ক্যাপশন সংরক্ষিত হয়েছে (Caption saved successfully!)");
        }
      } catch (err) {
        alert("Failed to save caption: " + err);
      }
    }

    async function togglePause() {
      const res = await fetch('/api/status');
      const data = await res.json();
      const newPaused = !data.paused;

      await fetch('/api/settings/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ paused: newPaused })
      });
      fetchStatus();
    }

    async function toggleMode() {
      const res = await fetch('/api/status');
      const data = await res.json();
      const newMode = data.mode === 'auto' ? 'approval' : 'auto';

      await fetch('/api/settings/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ mode: newMode })
      });
      fetchStatus();
    }

    async function fetchHistory() {
      try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const records = data.history || [];
        document.getElementById('historyCount').textContent = `${records.length} sent`;

        const grid = document.getElementById('historyGrid');
        grid.innerHTML = '';
        if (records.length === 0) {
          grid.innerHTML = `<div class="col-span-full text-slate-500 text-xs p-4 text-center bg-slate-900 rounded-xl">No submissions sent yet.</div>`;
          return;
        }

        records.forEach(r => {
          const card = document.createElement('div');
          card.className = "p-4 rounded-2xl bg-slate-900 border border-slate-800 space-y-2 text-xs";
          card.innerHTML = `
            <div class="flex items-center justify-between">
              <span class="text-emerald-400 font-semibold flex items-center gap-1">
                <i data-lucide="check-circle-2" class="w-3.5 h-3.5"></i> Sent Successfully
              </span>
              <a href="${r.instagram_url}" target="_blank" class="text-slate-400 hover:text-rose-400">
                <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
              </a>
            </div>
            <p class="text-lg font-bold bangla text-rose-200">${r.caption}</p>
            <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
              <span>Date: ${r.sent_at ? new Date(r.sent_at).toLocaleDateString() : '--'}</span>
              <span class="font-mono text-slate-400">${r.shortcode}</span>
            </div>
          `;
          grid.appendChild(card);
        });
      } catch (err) {
        console.error("History fetch error:", err);
      }
    }

    async function fetchLogs() {
      try {
        const res = await fetch('/api/logs');
        const data = await res.json();
        document.getElementById('logContent').textContent = data.logs || "No logs available.";
      } catch (err) {
        document.getElementById('logContent').textContent = "Failed to load logs.";
      }
    }

    // Modal Handlers
    function openSendModal() {
      const caption = document.getElementById('captionDisplay').textContent;
      const attachment = document.getElementById('attachmentNameDisplay').textContent;
      const recipient = document.getElementById('recipientDisplay').textContent;

      document.getElementById('modalCaption').textContent = caption;
      document.getElementById('modalAttachment').textContent = attachment;
      document.getElementById('modalRecipient').textContent = recipient;

      document.getElementById('confirmModal').classList.remove('hidden');
    }

    function closeSendModal() {
      document.getElementById('confirmModal').classList.add('hidden');
    }

    async function executeSendNow() {
      const progress = document.getElementById('sendProgress');
      const confirmBtn = document.getElementById('confirmSendBtn');
      const cancelBtn = document.getElementById('cancelBtn');

      progress.classList.remove('hidden');
      confirmBtn.disabled = true;
      cancelBtn.disabled = true;

      try {
        const res = await fetch('/api/send-now', { method: 'POST' });
        const data = await res.json();
        progress.classList.add('hidden');

        if (data.success) {
          alert("🎉 Email sent successfully to ABP Nadia!");
          closeSendModal();
          loadAllData(true);
        } else {
          alert("❌ Failed to send email: " + (data.error || "Unknown error"));
          confirmBtn.disabled = false;
          cancelBtn.disabled = false;
        }
      } catch (err) {
        progress.classList.add('hidden');
        confirmBtn.disabled = false;
        cancelBtn.disabled = false;
        alert("Network error: " + err);
      }
    }

    // Initial load
    window.onload = () => loadAllData();
  </script>
</body>
</html>
"""

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


if __name__ == "__main__":
    # Listen on all network interfaces (0.0.0.0) so it's accessible from both PC and phone on same WiFi!
    port = int(os.environ.get("DASHBOARD_PORT", 5000))
    print(f"\n=======================================================")
    print(f"  📸 ABP Nadia Photo Mailer Dashboard")
    print(f"  PC Local Access:    http://localhost:{port}")
    print(f"  Mobile / LAN Access: http://0.0.0.0:{port}")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)

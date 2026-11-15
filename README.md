# 📸 Daily Instagram Photo Submission to ABP Nadia (আপনার লেন্সে)

An automated system that fetches single photography posts sequentially (from latest to oldest) from Instagram profile **[@pixell.poet](https://instagram.com/pixell.poet)**, uses **Google Gemini AI** to inspect the photo and generate an artistic 1–2 word Bengali caption, and emails it daily with the attachment to **`edit.nadia@abp.in`** using **GitHub Actions**.

---

## 🌟 How It Works

1. **Sequential & Deduplicated Selection**:
   - The script scans posts on `@pixell.poet` in reverse chronological order (latest to oldest).
   - Checks `sent_history.json` to guarantee **no photo is ever emailed twice**.
   - **Skips videos, reels, and multi-photo carousel posts** (`GraphSidecar` and `GraphVideo`), focusing strictly on individual photography submissions (`GraphImage`).
2. **AI Bengali Captioning (Gemini Vision)**:
   - Passes the image to Google Gemini (e.g., `gemini-2.5-flash`).
   - Generates an evocative, poetic 1–2 word title in Bengali script (e.g., *ছেলেবেলা*, *নিস্তব্ধতা*, *আলোছায়া*, *একাকীত্ব*, *জলছবি*).
3. **Email Formatting & Dispatch**:
   - **Recipient:** `edit.nadia@abp.in`
   - **Subject:** `আপনার লেন্সে (শুভ্র জ্যোতি দে)`
   - **Body:**
     ```text
     ছবির নাম : [Generated Bengali Caption]
     ক্যামেরা: রেডমি নোট ১০ প্রো 
     নাম : শুভ্র জ্যোতি দে 
     ঠিকানা : রানাঘাট, নদিয়া।
     ```
   - **Attachment:** High-quality JPEG conversion of the photo (`shuvro_jyoti_dey_<shortcode>.jpg`).
4. **Persistent History on GitHub**:
   - Once dispatched, the post's shortcode, timestamp, and caption are saved to `sent_history.json` and committed automatically back to your GitHub repository.

---

## 🚀 Setup Guide

### 1. Generate Google Gemini API Key (Free)
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with your Google account.
3. Click **Create API key** and copy the key.

---

### 2. Generate a Gmail App Password
Because Google requires modern security for SMTP, you need an **App Password** (not your normal Gmail password):
1. Go to your [Google Account Security Settings](https://myaccount.google.com/security).
2. Ensure **2-Step Verification** is turned ON.
3. Go to [App Passwords](https://myaccount.google.com/apppasswords).
4. Enter an App Name (e.g., `ABP Photo Mailer`) and click **Create**.
5. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`).

---

### 3. Push this Code to a Private GitHub Repository
Run these commands in PowerShell or Terminal inside this project folder:

```bash
git init
git add .
git commit -m "Initial commit for ABP Nadia daily photo mailer"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
git push -u origin main
```
*(Tip: Make the repository **Private** to keep your submission history private).*

---

### 4. Add Repository Secrets in GitHub
1. Open your repository on GitHub.
2. Go to **Settings** -> **Secrets and variables** -> **Actions**.
3. Under **Repository secrets**, click **New repository secret** and add:

| Secret Name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Google Gemini API Key |
| `GMAIL_USER` | Your full Gmail address (e.g., `yourname@gmail.com`) |
| `GMAIL_APP_PASSWORD` | The 16-character Google App Password (without spaces) |

*(Optional)*:
- If you ever want to test sending to yourself before emailing ABP, you can add repository variable `RECIPIENT_EMAIL`. By default, it sends to `edit.nadia@abp.in`.

---

## 🧪 Testing

### Test 1: In GitHub Actions (Recommended)
1. Go to the **Actions** tab in your GitHub repository.
2. Click **Daily Instagram Photo Mailer** on the left.
3. Click **Run workflow**:
   - Check the **Dry Run** box to preview without emailing or modifying history.
   - Or enter your personal email in **test_email** to send a live test email directly to yourself!

### Test 2: Locally on your PC
Create a `.env` file from `.env.example`:
```bash
cp .env.example .env
```
Fill in `GEMINI_API_KEY`, `GMAIL_USER`, and `GMAIL_APP_PASSWORD`.

Run dry-run:
```bash
python main.py --dry-run
```

Send a test email to yourself:
```bash
python main.py --test-email your_email@gmail.com
```

---

## ⏰ Automated Schedule
The workflow runs automatically every day at **09:00 AM IST** (03:30 UTC):
```yaml
schedule:
  - cron: '30 3 * * *'
```
You can edit `.github/workflows/daily_mailer.yml` if you want to change the daily delivery time.

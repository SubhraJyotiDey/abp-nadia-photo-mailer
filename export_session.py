"""
Helper utility to export an Instagram session for GitHub Actions.
Run this locally on your PC ONLY IF GitHub Actions encounters an Instagram login check.

Usage:
    python export_session.py [instagram_username]
"""

import sys
import os
import base64
import instaloader

def export_session():
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("Enter your Instagram username (e.g. pixell.poet): ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    L = instaloader.Instaloader()
    print(f"\n[INFO] Logging in for @{username} (password input will be hidden)...")
    try:
        L.interactive_login(username)
        session_filename = f"session_{username}"
        L.save_session_to_file(session_filename)

        with open(session_filename, "rb") as f:
            b64_str = base64.b64encode(f.read()).decode("utf-8")

        print("\n" + "="*60)
        print("  SESSION GENERATED SUCCESSFULLY!")
        print("="*60)
        print("In your GitHub repository:")
        print("1. Go to Settings -> Secrets and variables -> Actions")
        print("2. Click 'New repository secret'")
        print("3. Name:  INSTAGRAM_SESSION_BASE64")
        print("4. Value: Paste the text below:\n")
        print(b64_str)
        print("\n5. (Optional) Secret INSTAGRAM_SESSION_USER: " + username)
        print("="*60)

        if os.path.exists(session_filename):
            os.remove(session_filename)

    except Exception as e:
        print(f"\n[ERROR] Failed to login or export session: {e}")

if __name__ == "__main__":
    export_session()

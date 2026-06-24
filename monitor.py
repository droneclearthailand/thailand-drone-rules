#!/usr/bin/env python3
"""
Thailand Drone Rules - source monitor.
Runs daily via GitHub Actions:
1. Updates LAST_VERIFIED in data.js to today's date (always)
2. Fetches public regulation sources and compares against saved snapshots
3. Pings Telegram if a meaningful change is detected
You then review and manually update data.js before publishing any regulation changes.
"""
import os, re, hashlib, json, pathlib, datetime, requests
from bs4 import BeautifulSoup

SOURCES = {
    "caat_uas_portal": "https://uasportal.caat.or.th/",
    # Add more as you confirm they're scrapable:
    # "nbtc": "https://...",
    # "tat_newsroom": "https://...",
}

SNAP_DIR = pathlib.Path("snapshots")
SNAP_DIR.mkdir(exist_ok=True)

DATA_JS = pathlib.Path("data.js")

def clean_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text

def notify(msg):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[no telegram configured] " + msg)
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": msg, "disable_web_page_preview": True},
        timeout=20,
    )

def update_last_verified():
    """Update LAST_VERIFIED in data.js to today's date (Thailand time UTC+7)."""
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
    if not DATA_JS.exists():
        print("data.js not found, skipping date update")
        return False
    content = DATA_JS.read_text()
    # Replace the date value
    updated = re.sub(
        r'const LAST_VERIFIED = "[0-9]{4}-[0-9]{2}-[0-9]{2}";',
        f'const LAST_VERIFIED = "{today}";',
        content
    )
    if updated == content:
        print(f"LAST_VERIFIED already set to {today} or pattern not found")
        return False
    DATA_JS.write_text(updated)
    print(f"Updated LAST_VERIFIED to {today}")
    return True

# --- Update the date first (always runs) ---
date_updated = update_last_verified()

# --- Then check sources for regulation changes ---
changes = []
for name, url in SOURCES.items():
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 DroneMonitor"})
        text = clean_text(r.text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except Exception as e:
        notify(f"Warning: Could not fetch {name}: {e}")
        continue

    snap_file = SNAP_DIR / f"{name}.json"
    prev = json.loads(snap_file.read_text()) if snap_file.exists() else {}
    if prev.get("hash") != digest:
        if prev:  # not first run
            changes.append(name)
        snap_file.write_text(json.dumps({"hash": digest, "url": url, "len": len(text)}, indent=2))

if changes:
    notify(
        "Regulation source change detected:\n" +
        "\n".join(f"- {c}: {SOURCES[c]}" for c in changes) +
        "\n\nReview the source, then update data.js if a regulation actually changed."
    )
    print(f"Changes detected: {changes}")
else:
    print("No source changes detected.")

if date_updated:
    print("data.js date updated - GitHub Actions will commit this change.")

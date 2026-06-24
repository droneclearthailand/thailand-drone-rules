#!/usr/bin/env python3
"""
Thailand Drone Rules — source monitor.
Fetches public regulation sources, compares against saved snapshots,
and pings Telegram when a meaningful change is detected.
You then review and manually update data.js before publishing.
"""
import os, re, hashlib, json, pathlib, requests
from bs4 import BeautifulSoup

SOURCES = {
    "caat_uas_portal": "https://uasportal.caat.or.th/",
    # Add more as you confirm they're scrapable:
    # "nbtc": "https://...",
    # "tat_newsroom": "https://...",
}

SNAP_DIR = pathlib.Path("snapshots")
SNAP_DIR.mkdir(exist_ok=True)

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

changes = []
for name, url in SOURCES.items():
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 DroneMonitor"})
        text = clean_text(r.text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except Exception as e:
        notify(f"⚠ Could not fetch {name}: {e}")
        continue

    snap_file = SNAP_DIR / f"{name}.json"
    prev = json.loads(snap_file.read_text()) if snap_file.exists() else {}
    if prev.get("hash") != digest:
        if prev:  # not first run
            changes.append(name)
        snap_file.write_text(json.dumps({"hash": digest, "url": url, "len": len(text)}, indent=2))

if changes:
    notify("🔔 Thailand drone source change detected:\n" +
           "\n".join(f"• {c}: {SOURCES[c]}" for c in changes) +
           "\n\nReview, then update data.js if regulation actually changed.")
else:
    print("No changes detected.")

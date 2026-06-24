#!/usr/bin/env python3
"""
Thailand Drone Rules - source monitor.
Runs daily via GitHub Actions:
1. Updates LAST_VERIFIED in data.js to today's date (always)
2. Fetches public regulation sources and compares against saved snapshots
3. If hash changed: sends page content to Claude API for analysis
4. Pings Telegram with Claude's verdict + ready-to-paste data.js snippet

You review the Telegram message and manually paste any snippet into data.js
before pushing. Nothing auto-publishes.
"""
import os, re, hashlib, json, pathlib, datetime, requests
from bs4 import BeautifulSoup

SOURCES = {
    "caat_uas_portal": "https://uasportal.caat.or.th/",
}
SNAP_DIR = pathlib.Path("snapshots")
SNAP_DIR.mkdir(exist_ok=True)
DATA_JS = pathlib.Path("data.js")

# ---------------------------------------------------------------------------
# CURRENT DATA.JS STATE — keep this block in sync with data.js manually.
# Claude uses this as ground truth when drafting change snippets.
# ---------------------------------------------------------------------------
CURRENT_DATA_CONTEXT = """\
STATUS indicators (state values: "ok", "warn", "err"):
  - "Border province bans":     state="warn", value="ACTIVE"
  - "CAAT UAS Portal":          state="ok",   value="OPERATIONAL"
  - "NBTC Registration":        state="ok",   value="OPEN"
  - "Pre-arrival registration": state="warn", value="NOT POSSIBLE"

FIGURES (rule labels must match exactly):
  - Altitude limit:        90 m / 300 ft
  - Min. airport distance: 9 km
  - Insurance minimum:     THB 1,000,000
  - NBTC fee (approx.):    ~THB 200
  - CAAT exam questions:   40
  - Exam pass score:       75%
  - Exam retake wait:      24 hours
  - Camera = registration: ANY weight

BORDER_BANS active (CAAT Notice No. 15, Feb 2026, no end date):
  Sa Kaeo, Surin, Buriram, Sisaket, Ubon Ratchathani, Trat, Chanthaburi

Most recent CHANGELOG entries (newest first):
  - 2026-06-24: Border bans remain active in Sa Kaeo, Surin, Buriram, Sisaket,
    Ubon Ratchathani, Trat, and Chanthaburi. No end date announced.
  - 2025-01-15: Pre-arrival registration no longer possible. Thai SIM and
    passport arrival stamp now required to register on the CAAT UAS Portal.
  - 2025-01-15: CAAT portal updated — OTP verification now required via a
    Thai mobile number.
"""

DATA_JS_FORMAT = """\
data.js JavaScript structure — snippets must match this exactly:

const STATUS = [
  { state: "ok"|"warn"|"err", label: "...", value: "..." },
  ...
];

const FIGURES = [
  { rule: "...", value: "..." },
  ...
];

const BORDER_BANS = [
  { name: "...", lat: 0.000, lng: 0.000 },
  ...
];

// CHANGELOG: newest entry first
const CHANGELOG = [
  { date: "YYYY-MM-DD", text: "Plain English description." },
  ...
];

Only output the specific array entries that need to change — not entire
unchanged arrays. For example, if only a STATUS entry changed, output just
that modified STATUS object. If adding a CHANGELOG entry, output just the
new object to prepend. Keep snippets short and paste-ready.
"""

TELEGRAM_MAX_CHARS = 4000   # Telegram hard limit is 4096; leave headroom


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text


def notify(msg):
    """Send a Telegram message, splitting if it exceeds the character limit."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat  = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[no telegram configured]\n" + msg)
        return

    # Split on the TELEGRAM_MAX_CHARS boundary without cutting mid-word
    chunks = []
    while len(msg) > TELEGRAM_MAX_CHARS:
        split_at = msg.rfind("\n", 0, TELEGRAM_MAX_CHARS)
        if split_at == -1:
            split_at = TELEGRAM_MAX_CHARS
        chunks.append(msg[:split_at])
        msg = msg[split_at:].lstrip("\n")
    chunks.append(msg)

    for i, chunk in enumerate(chunks):
        label = f" [{i+1}/{len(chunks)}]" if len(chunks) > 1 else ""
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": chunk + label,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )


def update_last_verified():
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
    if not DATA_JS.exists():
        print("data.js not found, skipping date update")
        return False
    content = DATA_JS.read_text()
    updated = re.sub(
        r'const LAST_VERIFIED = "[0-9]{4}-[0-9]{2}-[0-9]{2}";',
        f'const LAST_VERIFIED = "{today}";',
        content,
    )
    if updated == content:
        print(f"LAST_VERIFIED already set to {today} or pattern not found")
        return False
    DATA_JS.write_text(updated)
    print(f"Updated LAST_VERIFIED to {today}")
    return True


# ---------------------------------------------------------------------------
# Claude analysis — only called when a hash change is detected
# ---------------------------------------------------------------------------

def analyse_change_with_claude(source_name, url, new_text, prev_text=None):
    """
    Send the changed page content to Claude for regulatory analysis.
    Returns (analysis_dict, error_string). One of the two will be None.
    This function is NEVER called on a clean daily run with no hash change.
    """
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed — add it to the workflow pip install step"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "ANTHROPIC_API_KEY secret not set in GitHub repository"

    client = anthropic.Anthropic(api_key=api_key)
    today  = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")

    # Cap page text to control token cost. 5 000 chars ≈ ~1 250 tokens — enough
    # for any Thai regulation page. Previous text capped lower; it's supplementary.
    new_text_excerpt  = new_text[:5000]
    prev_text_section = (
        f"PREVIOUS PAGE CONTENT (before today's change — for comparison):\n"
        f"---\n{prev_text[:2500]}\n---\n"
        if prev_text
        else "(No previous page text available — first snapshot or not stored previously.)\n"
    )

    system_prompt = """\
You are a regulatory analyst for DroneClear Thailand, a concierge service that
helps international tourists register camera drones legally in Thailand.

Your task: analyse a detected change on a Thai drone regulation website and
classify it as REGULATION_CHANGE, COSMETIC, or AMBIGUOUS.

Key facts about the current rules (cross-reference these when analysing):
- Any camera drone requires CAAT + NBTC registration regardless of weight.
- Pre-arrival registration ended early 2025; Thai SIM + arrival stamp required.
- Altitude limit: 90 m. Airport exclusion: 9 km. Insurance: THB 1,000,000 min.
- CAAT exam: 40 questions, 75% pass score (30/40), 24-hour retake lockout.
- Active border bans (CAAT Notice No. 15, Feb 2026, no end date):
  Sa Kaeo, Surin, Buriram, Sisaket, Ubon Ratchathani, Trat, Chanthaburi.
- NBTC registration fee: ~THB 200.

Classification guide:
  REGULATION_CHANGE — a rule, figure, ban, fee, or procedure actually changed.
  AMBIGUOUS         — you cannot determine from page text alone whether a rule
                      changed; the owner should verify manually.
  COSMETIC          — layout, menu, wording, or styling change with no rule impact.

Respond ONLY with a valid JSON object. No preamble, no markdown fences.

Required JSON schema:
{
  "verdict": "REGULATION_CHANGE" | "COSMETIC" | "AMBIGUOUS",
  "reasoning": "2-3 sentences explaining what changed and why you classified it this way.",
  "changelog_entry": { "date": "YYYY-MM-DD", "text": "Plain English for tourists. Factual, no jargon." } | null,
  "status_changes": [
    { "label": "<exact label string from STATUS array>", "new_state": "ok|warn|err", "new_value": "NEW VALUE" }
  ],
  "figures_changes": [
    { "rule": "<exact rule label from FIGURES array>", "new_value": "new value string" }
  ],
  "border_ban_changes": "Plain English description of any border ban changes." | null,
  "data_js_snippet": "Minimal ready-to-paste JS snippet — only the changed entries, not full arrays." | null
}

Rules for data_js_snippet:
- Include only entries that need to change, not entire unchanged arrays.
- For a new CHANGELOG entry: just the single new object to prepend.
- For a STATUS change: just the modified { state, label, value } object.
- For a FIGURES change: just the modified { rule, value } object.
- If COSMETIC and nothing needs changing: set to null.
- Match the exact JavaScript format specified in the format reference below.
"""

    user_prompt = (
        f"Source: {source_name}\n"
        f"URL: {url}\n"
        f"Today's date (Thailand time): {today}\n\n"
        f"CURRENT data.js STATE:\n{CURRENT_DATA_CONTEXT}\n"
        f"data.js FORMAT REFERENCE:\n{DATA_JS_FORMAT}\n"
        f"{prev_text_section}\n"
        f"NEW PAGE CONTENT (after today's detected change):\n"
        f"---\n{new_text_excerpt}\n---\n\n"
        f"Analyse the change and return your JSON verdict."
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip accidental markdown fences
        raw = re.sub(r"^```(?json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"Claude returned invalid JSON: {e}"
    except Exception as e:
        return None, f"Claude API error: {e}"


def format_telegram_message(source_name, url, analysis):
    """Build the Telegram alert from Claude's analysis dict."""
    verdict        = analysis.get("verdict", "UNKNOWN")
    reasoning      = analysis.get("reasoning", "No reasoning provided.")
    changelog      = analysis.get("changelog_entry")
    status_changes = analysis.get("status_changes") or []
    figures_changes= analysis.get("figures_changes") or []
    border_bans    = analysis.get("border_ban_changes")
    snippet        = analysis.get("data_js_snippet")

    emoji = {"REGULATION_CHANGE": "🚨", "AMBIGUOUS": "⚠️", "COSMETIC": "ℹ️"}.get(verdict, "❓")

    lines = [
        f"{amoji} {verdict}",
        f"Source: {source_name}",
        "",
        "REASONING",
        reasoning,
        "",
        f"SOURCE: {url}",
    ]

    if status_changes:
        lines += ["", "STATUS CHANGES SUGGESTED"]
        for sc in status_changes:
            lines.append(f'  • "{sc["label"]}": state={sc["new_state"]}, value="{sc["new_value"]}"')

    if figures_changes:
        lines += ["", "FIGURES CHANGES SUGGESTED"]
        for fc in figures_changes:
            lines.append(f'  • {fc["rule"]}: {fc["new_value"]}')

    if border_bans:
        lines += ["", "BORDER BAN CHANGES", f"  {border_bans}"]

    if changelog:
        lines += [
            "",
            "CHANGELOG ENTRY DRAFT",
            f'  date: "{mchangelog["date"]}"',
            f'  text: "{changelog["text"]}"',
        ]

    if snippet:
        lines += [
            "",
            "READY-TO-PASTE data.js SNIPPET",
            "---",
            snippet,
            "---",
        ]

    lines += [
        "",
        "ACTION: Review source → paste snippet into data.js → push to GitHub → Vercel deploys.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main — two-path structure preserved from original
# ---------------------------------------------------------------------------

# PATH 1: Always update the date stamp (no API calls, no LLM)
date_updated = update_last_verified()

# PATH 2: Check sources — LLM only fires if a hash change is detected
changes = []

for name, url in SOURCES.items():
    try:
        r    = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 DroneMonitor"})
        text = clean_text(r.text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except Exception as e:
        notify(f"Warning: Could not fetch {name}: {e}")
        continue

    snap_file = SNAP_DIR / f"{name}.json"
    prev      = json.loads(snap_file.read_text()) if snap_file.exists() else {}

    if prev.get("hash") != digest:
        if prev:
            # Genuine change (not just first-ever snapshot)
            changes.append((name, url, text, prev.get("text")))  # prev["text"] may be None on old snapshots

        # Save updated snapshot — now includes full text for future diffs
        snap_file.write_text(json.dumps({
            "hash":     digest,
            "url":      url,
            "len":      len(text),
            "text":     text,       # not stored in old snapshots; present from this run onwards
            "saved_at": datetime.datetime.utcnow().isoformat() + "Z",
        }, indent=2))

if changes:
    for name, url, new_text, prev_text in changes:
        print(f"Change detected: {name} — running Claude analysis…")

        # LLM call — only reached on this branch
        analysis, error = analyse_change_with_claude(name, url, new_text, prev_text)

        if error:
            # Claude failed — fall back to the original plain-text ping so you're
            # never silently left without a notification
            notify(
                f"⚠️ Change detected on {name}: {url}\n\n"
                f"Claude analysis failed: {error}\n\n"
                f"Review the source manually and update data.js if a regulation changed."
            )
        else:
            verdict = analysis.get("verdict", "UNKNOWN")
            if verdict == "COSMETIC":
                notify(
                    f"ℹ️ COSMETIC change on {name} — no data.js update needed.\n\n"
                    f"{analysis.get('reasoning', '')}\n\n"
                    f"SOURCE: {url}"
                )
            else:
                notify(format_telegram_message(name, url, analysis))

        print(f"Verdict: {analysis.get('verdict') if analysis else 'ERROR — see above'}")

else:
    print("No source changes detected.")

if date_updated:
    print("data.js date updated — GitHub Actions will commit this change.")

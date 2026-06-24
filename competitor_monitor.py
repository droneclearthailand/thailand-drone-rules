#!/usr/bin/env python3
"""
DroneClear Thailand — weekly competitor monitor.
Runs every Monday at 02:00 UTC (09:00 Thailand time) via GitHub Actions.

1. Scrapes pricing and service pages of key competitors
2. Compares against saved snapshots (hash-based, same pattern as monitor.py)
3. If changes detected: sends page content to Claude API for competitive analysis
4. Sends a weekly Telegram digest regardless — changes found or no changes

Claude API is only called when a change is detected — zero cost in quiet weeks.
Snapshots stored in competitor_snapshots/ folder.
"""
import os, re, hashlib, json, pathlib, datetime, requests
from bs4 import BeautifulSoup

SNAP_DIR = pathlib.Path("competitor_snapshots")
SNAP_DIR.mkdir(exist_ok=True)

TELEGRAM_MAX_CHARS = 4000

# ---------------------------------------------------------------------------
# Competitors and pages to monitor
# ---------------------------------------------------------------------------

COMPETITORS = {
    "feic_registration": {
        "name": "FEIC Thailand",
        "url": "https://www.feic.co.th/thailand-drone-registration-service/",
        "focus": (
            "Registration service page. Current known price: THB 1,498 for NBTC+CAAT assistance "
            "(insurance must be purchased separately — cannot use registration service without buying "
            "their insurance). Watch for: price changes, new service tiers, changes to what's included, "
            "or removal of the insurance-bundling requirement."
        ),
        "language": "English",
    },
    "feic_insurance": {
        "name": "FEIC Thailand",
        "url": "https://www.feic.co.th/thailand-drone-insurance-plans/",
        "focus": (
            "Insurance plans page. Watch for: premium changes to any plan tier, "
            "new plan types added, changes to coverage limits, or changes to terms."
        ),
        "language": "English",
    },
    "mydronethailand_home": {
        "name": "MyDroneThailand",
        "url": "https://mydronethailand.com/",
        "focus": (
            "Homepage — contains the full current pricing breakdown. "
            "Known prices: NBTC-only THB 1,300, second drone THB 1,300, "
            "insurance THB 699 (under 300g) / THB 899 (301-3000g). "
            "Watch for: any price changes, new or removed service tiers, "
            "changes to what's included, new language targeting (e.g. German content added)."
        ),
        "language": "English",
    },
    "tds_packages": {
        "name": "ThailandDroneInsurance (TDS)",
        "url": "https://www.thailanddroneinsurance.com/packages",
        "focus": (
            "Registration packages page. Two current tiers: Package 1 (full-service, "
            "everything handled by TDS team) and Package 2 (self-paced, customer sits CAAT "
            "exam independently, TDS handles rest). Watch for: price changes to either package, "
            "new packages added, removed tiers, or changes to what each package includes."
        ),
        "language": "English",
    },
    "tds_insurance": {
        "name": "ThailandDroneInsurance (TDS)",
        "url": "https://www.thailanddroneinsurance.com/tourist-drone-insurance",
        "focus": (
            "Tourist drone insurance page. Current known price: from THB 790/year. "
            "Watch for: price changes, new coverage tiers, "
            "changes to policy terms, eligibility rules, or claims process."
        ),
        "language": "English",
    },
    "thaifreude_de": {
        "name": "ThaiFreude (German service page)",
        "url": "https://thaifreu.de/drohnenservice/",
        "focus": (
            "PRIMARY page for German audience monitoring. Content is in German — analyse in German, "
            "summarise findings in English. "
            "Current known price: EUR 85 for full CAAT+NBTC service (NBTC fee included). "
            "CRITICAL CURRENCY NOTE: ThaiFreude prices in EUR, not THB. Always note the EUR price "
            "and include approximate THB equivalent (use ~38-40 THB per EUR). "
            "If they add THB pricing alongside EUR, or switch from EUR to THB, flag this as HIGH "
            "significance — it signals a deliberate shift toward Thai-based or non-German-speaking "
            "audiences and directly threatens DroneClear's positioning. "
            "Also watch for: new service tiers at different price points, changes to what EUR 85 "
            "includes, expansion of content targeting non-German tourists."
        ),
        "language": "GerMan",
    },
    "thaifreude_en": {
        "name": "ThaiFreude (English service page)",
        "url": "https://thaifreu.de/drone-registration-service-thailand/",
        "focus": (
            "English-language version of ThaiFreude's service page. "
            "Note: German page prices in EUR 85 — check if this English page uses EUR or THB pricing. "
            "Watch for: any price listed (note currency), new English content targeting non-German "
            "tourists, or divergence from the German page in pricing, scope, or audience framing."
        ),
        "language": "English",
    },
}

# ---------------------------------------------------------------------------
# DroneClear context — fed to Claude for all competitor analyses
# ---------------------------------------------------------------------------

DRONECLEAR_CONTEXT = """\
You are analysing competitor changes for DroneClear Thailand, a solo drone compliance \
concierge based in Hua Hin, Thailand (run by Rainer).

DroneClear's current pricing:
  - NBTC-only registration: THB 970
  - Full Compliance Package (CAAT + NBTC): THB 1,950
  - Insurance: from THB 960 (tiered by drone weight, via insurance partner)

DroneClear's positioning:
  - WhatsApp-first, human concierge — no self-service portal
  - Authority-on-the-pitfalls tone, not a DIY guide
  - Based in Thailand (Hua Hin) — local physical presence is a differentiator
  - Highest-priority audience: German-speaking tourists and expats

Competitors being monitored:
  - FEIC Thailand: Established Bangkok insurance broker. Registration THB 1,498 \
but requires insurance purchase first — bundled model.
  - MyDroneThailand: Chiang Rai-based service. NBTC-only THB 1,300, insurance THB 699/899. \
Operates in English and German.
  - ThailandDroneInsurance (TDS): Insurance-first positioning. Packages for full-service \
and self-paced registration. Insurance from THB 790/year.
  - ThaiFreude: German-language concierge, EUR 85 (approx. THB 3,230-3,400) for full service. \
DroneClear's primary German-audience competitor.

IMPORTANT — ThaiFreude currency note: ThaiFreude prices in EUR, not THB. \
When analysing ThaiFreude pages, always state the EUR price and its approximate \
THB equivalent (1 EUR ≈ 38-40 THB). If ThaiFreude adds THB pricing or switches \
from EUR to THB, treat this as HIGH significance — it signals audience expansion \
toward non-German or in-country customers.
"""


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
    """Send a Telegram message, splitting at newlines if over the character limit."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat  = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[no telegram configured]\n" + msg)
        return

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


# ---------------------------------------------------------------------------
# Claude analysis — only called when a hash change is detected
# ---------------------------------------------------------------------------

def analyse_competitor_change(key, competitor, new_text, prev_text=None):
    """
    Send changed page content to Claude for competitive intelligence analysis.
    Returns (analysis_dict, error_string). One of the two will be None.
    This function is NEVER called on quiet weeks with no changes.
    """
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "ANTHROPIC_API_KEY secret not set"

    client = anthropic.Anthropic(api_key=api_key)
    today  = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")

    new_text_excerpt = new_text[:5000]
    prev_section = (
        f"PREVIOUS PAGE CONTENT (before this week's change — for comparison):\n"
        f"---\n{prev_text[:2500]}\n---\n"
        if prev_text
        else "(No previous page text stored — first snapshot or not available.)\n"
    )

    system_prompt = """\
You are a competitive intelligence analyst for DroneClear Thailand.

Your job: analyse a change detected on a competitor's website. Identify what \
specifically changed, how significant it is commercially, and what it means for \
DroneClear Thailand.

Focus only on commercially meaningful changes:
  - Price changes (any currency — always note EUR/THB where relevant)
  - New or Removed service tiers or products
  - Changes to what's included in existing packages
  - Changes in target audience or language
  - Changes in key positioning claims or guarantees

Ignore and classify as NOISE: blog posts, minor wording tweaks, nav/footer \
changes, seasonal banners, cookie notices, SEO filler text.

For German-language pages: the content will be in German. Analyse it normally \
and write all findings in English. Pay close attention to pricing in EUR and \
always include approximate THB equivalent.

Respond ONLY with a valid JSON object. No preamble, no markdown fences.

JSON schema:
{
  "significance": "HIGH" | "MEDIUM" | "LOW" | "NOISE",
  "what_changed": "1-3 plain English sentences describing exactly what changed.",
  "why_it_matters": "1-2 sentences on relevance to DroneClear Thailand specifically.",
  "recommended_action": "1 sentence on what Rainer might consider, or null.",
  "confidence": "HIGH" | "MEDIUM" | "LOW"
}

Significance guide:
  HIGH   — price change, new/removed service tier, new product, new audience targeting
  MEDIUM — wording shift in key claims, new feature within existing tier, notable policy change
  LOW    — minor content update with marginal commercial relevance
  NOISE  — cosmetic, structural, or irrelevant change
"""

    user_prompt = (
        f"Competitor: {competitor['name']}\n"
        f"Page URL: {competitor['url']}\n"
        f"Page language: {competitor['language']}\n"
        f"What to watch on this page: {competitor['focus']}\n"
        f"Analysis date (Thailand time): {today}\n\n"
        f"--- DRONECLEAR CONTEXT ---\n{DRONECLEAR_CONTEXT}\n"
        f"--- END CONTEXT ---\n\n"
        f"{prev_section}\n"
        f"NEW PAGE CONTENT (after this week's detected change):\n"
        f"---\n{new_text_excerpt}\n---\n\n"
        f"Analyse the change and return your JSON verdict."
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"Claude returned invalid JSON: {e}"
    except Exception as e:
        return None, f"Claude API error: {e}"


# ---------------------------------------------------------------------------
# Weekly digest formatter
# ---------------------------------------------------------------------------

def format_digest(changes):
    """
    Build the weekly Telegram digest.
    changes: list of (key, competitor, analysis_or_none, error_or_none)
    Always sent — either a clean all-clear or a list of flagged changes.
    """
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
    sig_emoji = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️", "NOISE": "·"}

    if not changes:
        checked = "\n".join(
            f"  • {c['name']}: {c['url']}" for c in COMPETITORS.values()
        )
        return (
            f"🗓 Competitor Monitor — {today}\n\n"
            f"✅ No changes detected across all {len(COMPETITORS)} monitored pages.\n\n"
            f"Pages checked:\n{checked}"
        )

    lines = [
        f"🗓 Competitor Monitor — {today}",
        f"",
        f"{len(changes)} page(s) changed this week:",
    ]

    for key, competitor, analysis, error in changes:
        lines += ["", "─" * 28]
        lines.append(f"📍 {competitor['name']}")
        lines.append(f"🔗 {competitor['url']}")

        if error:
            lines.append(f"⚠️ Analysis failed: {error}")
            lines.append("Review manually.")
        elif analysis:
            sig    = analysis.get("significance", "?")
            emoji  = sig_emoji.get(sig, "❓")
            conf   = analysis.get("confidence", "?")
            lines += [
                f"",
                f"{emoji} {sig}  (confidence: {conf})",
                f"",
                f"WHAT CHANGED",
                analysis.get("what_changed", "—"),
                f"",
                f"WHY IT MATTERS",
                analysis.get("why_it_matters", "—"),
            ]
            action = analysis.get("recommended_action")
            if action:
                lines += ["", f"ACTION", action]

    lines += [
        "",
        "─" * 28,
        "Unmentioned pages: no changes detected.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

changes_detected = []   # list of (key, competitor, analysis, error)

for key, competitor in COMPETITORS.items():
    url = competitor["url"]
    try:
        r    = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 DroneClearMonitor"})
        text = clean_text(r.text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"Fetch error — {key}: {e}")
        # Include fetch failures in digest so nothing goes silently missing
        changes_detected.append((key, competitor, None, f"Fetch error: {e}"))
        continue

    snap_file = SNAP_DIR / f"{key}.json"
    prev      = json.loads(snap_file.read_text()) if snap_file.exists() else {}

    if prev.get("hash") != digest:
        if prev:
            # Genuine change — run Claude analysis (LLM cost only incurred here)
            print(f"Change detected: {key} — running Claude analysis...")
            analysis, error = analyse_competitor_change(
                key, competitor, text, prev.get("text")
            )
            changes_detected.append((key, competitor, analysis, error))
            sig = analysis.get("significance") if analysis else "ERROR"
            print(f"  → {sig}")

        # Save updated snapshot — includes full text for future diffs
        snap_file.write_text(json.dumps({
            "hash":     digest,
            "url":      url,
            "len":      len(text),
            "text":     text,
            "saved_at": datetime.datetime.utcnow().isoformat() + "Z",
        }, indent=2))
    else:
        print(f"No change: {key}")

# Send weekly digest — always fires, regardless of whether changes were found
digest_msg = format_digest(changes_detected)
notify(digest_msg)
print("Weekly digest sent.")

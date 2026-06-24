# Thailand Drone Rules

Live status, fees, and no-fly zone map for tourists flying drones in Thailand.
Independent reference. CTA to DroneClear Thailand.

## Stack
- Static `index.html` + `data.js` (no build step)
- Leaflet.js map (no API key)
- Hosted on Vercel (free)
- GitHub Actions monitors sources daily → Telegram alert → you update `data.js`

## How to update the dashboard
1. Edit `data.js` (status, figures, border bans, changelog, LAST_VERIFIED)
2. Commit + push → Vercel auto-deploys in ~60s

## Deploy to Vercel
1. Push this repo to GitHub
2. vercel.com → New Project → import repo
3. Framework preset: **Other** · Output dir: **/** (root) · no build command
4. Deploy. Add custom domain in Vercel settings.

## Monitoring setup (optional, do after deploy)
1. Create a Telegram bot via @BotFather → get TOKEN
2. Get your chat ID (message @userinfobot)
3. GitHub repo → Settings → Secrets → add `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
4. Actions tab → enable workflows. Runs daily; ping = review + update data.js.

## Disclaimer
Guidance only, not legal advice. Verify with CAAT/NBTC before flying.

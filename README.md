# Polymarket Spike Telegram Bot

Small Python bot that polls active Polymarket markets and sends Telegram notifications when a market price spikes.

## What counts as a spike?

A spike alert is sent when all conditions pass:
- percentage move threshold is dynamic by previous price:
  - `0 - 0.02` => `400%`
  - `0.02 - 0.05` => `300%`
  - `0.05 - 0.10` => `200%`
  - `0.10 - 0.20` => `100%`
  - `0.20 - 0.40` => `50%`
  - `0.40 - 0.60` => `25%`
  - `>= 0.60` => `DEFAULT_SPIKE_THRESHOLD` (default `10%`)
- market absolute price move since last poll >= `MIN_ABSOLUTE_MOVE` (default `0.05` = 5 cents)
- market 24h volume >= `MIN_NOTIONAL_24H` (default `$10,000`)
- market is not in excluded categories (`EXCLUDED_CATEGORIES`, default `crypto,sports,esports`)
- sports/esports keyword matching also checks terms like `win`, `vs`, and `post`

## 1) Local setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather), copy token.
2. Get your Telegram chat ID (DM your bot, then inspect `getUpdates` response).
3. Create and activate a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Export environment variables:

```bash
export TELEGRAM_BOT_TOKEN="<your_token>"
export TELEGRAM_CHAT_ID="<your_chat_id>"
# optional tuning:
export DEFAULT_SPIKE_THRESHOLD="0.10"
export MIN_NOTIONAL_24H="10000"
export MIN_ABSOLUTE_MOVE="0.05"
export POLL_SECONDS="45"
export MARKET_LIMIT="200"
export EXCLUDED_CATEGORIES="crypto,sports,esports"
export STARTUP_TEST_MESSAGE="true"
```

5. Run:

```bash
python bot.py
```

## 2) Deploy so it works on your phone

Your phone does **not** run this script directly. Instead:
- deploy the bot to a cloud host that runs 24/7
- receive alerts in the Telegram app on your phone

### Option A (recommended): Render background worker

1. Push this repo to GitHub.
2. In Render, create a **Background Worker** from your repo.
3. Build command:

```bash
pip install -r requirements.txt
```

4. Start command:

```bash
python bot.py
```

5. Set environment variables in Render dashboard:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- optional: `DEFAULT_SPIKE_THRESHOLD`, `MIN_ABSOLUTE_MOVE`, `MIN_NOTIONAL_24H`, `POLL_SECONDS`, `MARKET_LIMIT`, `EXCLUDED_CATEGORIES`, `STARTUP_TEST_MESSAGE`

6. Deploy. You should receive the startup message in Telegram.

### Option B: VPS (DigitalOcean/Lightsail/Hetzner) + systemd

On your server:

```bash
git clone <your-repo-url>
cd poly_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `/etc/systemd/system/poly-bot.service`:

```ini
[Unit]
Description=Polymarket Spike Bot
After=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/poly_bot
Environment=TELEGRAM_BOT_TOKEN=YOUR_TOKEN
Environment=TELEGRAM_CHAT_ID=YOUR_CHAT_ID
Environment=DEFAULT_SPIKE_THRESHOLD=0.10
Environment=MIN_NOTIONAL_24H=10000
Environment=MIN_ABSOLUTE_MOVE=0.05
Environment=POLL_SECONDS=45
Environment=MARKET_LIMIT=200
Environment=EXCLUDED_CATEGORIES=crypto,sports,esports
Environment=STARTUP_TEST_MESSAGE=true
ExecStart=/home/ubuntu/poly_bot/.venv/bin/python /home/ubuntu/poly_bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now poly-bot
sudo systemctl status poly-bot
```

## 3) Using it from your phone

1. Install Telegram on your iPhone/Android.
2. Open chat with your bot (the one created via BotFather).
3. Press **Start** and send any message (for some privacy settings this helps establish chat).
4. Keep your cloud worker/server running.
5. Alerts arrive as Telegram push notifications.

## Notes

- Market discovery uses Polymarket Gamma API (`https://gamma-api.polymarket.com/markets`).
- The bot keeps a local in-memory baseline. Restarting the process resets previous prices.
- For production reliability, use a process manager (Render worker, systemd, Docker, or supervisord).


## Troubleshooting (Render deployed but no messages)

1. Check Render logs for these lines:
   - `Telegram token valid for bot @...`
   - `Fetched N included markets`
   - `Detected N spike alerts this cycle`
2. If startup message is missing, verify:
   - `TELEGRAM_BOT_TOKEN` is correct
   - `TELEGRAM_CHAT_ID` is correct
   - you opened your bot chat and pressed **Start**
3. For easier testing, temporarily reduce thresholds:

```bash
DEFAULT_SPIKE_THRESHOLD=0.03
MIN_NOTIONAL_24H=1000
MIN_ABSOLUTE_MOVE=0.02
POLL_SECONDS=30
```

4. Keep `STARTUP_TEST_MESSAGE=true` so each deploy confirms Telegram delivery.

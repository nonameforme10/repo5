# Telegram Console Bot

Telegram bot plus browser control console for sending text, links, emoji, GIFs, files, videos, photos, audio, voice messages, and stickers to chats where the bot has permission.

## Local Run

```powershell
python -m pip install -r .\bot\requirements.txt
Copy-Item .env.template .env
python -m bot.main
```

Open:

```text
http://127.0.0.1:8080/
```

If the console HTML is hosted separately, set the API server field in the page
or open it with an `api` query string:

```text
https://nonameforme10.github.io/repo5/?api=https://your-vps-domain.com
```

## Telegram Setup

1. Create a bot with BotFather and put the token in `.env` as `TELEGRAM_BOT_TOKEN`.
2. Add your Telegram numeric ID to `ADMIN_IDS`.
3. Add the bot to your group or channel.
4. For channels, make the bot an admin so it can post.
5. Send `/chatid` in the target chat and paste that ID into the web console.
6. Put that same ID in `.env` as `TARGET_CHAT_ID` if this should be the default chat every time.

Private invite links such as `https://t.me/+...` are not valid Bot API chat IDs.
Use the numeric channel ID that starts with `-100...`, or a public `@channelname`
if the channel has one.

## VPS Setup

Example path used below:

```bash
/opt/telegram-console-bot
```

Install packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

Create a service user:

```bash
sudo useradd --system --home /opt/telegram-console-bot --shell /usr/sbin/nologin telegrambot
```

Copy this project to the VPS, then:

```bash
cd /opt/telegram-console-bot
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r bot/requirements.txt
cp .env.template .env
nano .env
mkdir -p data
sudo chown -R telegrambot:telegrambot /opt/telegram-console-bot
```

Recommended `.env` for VPS:

```env
TELEGRAM_BOT_TOKEN=123456:replace_with_botfather_token
ADMIN_IDS=123456789
TARGET_CHAT_ID=-1001234567890
CONSOLE_HOST=127.0.0.1
CONSOLE_PORT=8080
CONSOLE_PUBLIC_URL=https://your-domain.com/
CONSOLE_API_KEY=replace_with_a_long_random_password
CONSOLE_ALLOWED_ORIGINS=https://nonameforme10.github.io
CONSOLE_ENABLED=true
MAX_UPLOAD_MB=60
```

If you want GitHub Pages to be the console frontend, use this style instead:

```env
CONSOLE_HOST=127.0.0.1
CONSOLE_PORT=8080
TARGET_CHAT_ID=-1001234567890
CONSOLE_PUBLIC_URL=https://nonameforme10.github.io/repo5/?api=https://your-vps-domain.com
CONSOLE_API_KEY=replace_with_a_long_random_password
CONSOLE_ALLOWED_ORIGINS=https://nonameforme10.github.io
```

GitHub Pages can only host the static `index.html`. The Python bot and `/api/*`
routes must still run on the VPS.

Install systemd service:

```bash
sudo cp deploy/telegram-console-bot.service /etc/systemd/system/telegram-console-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-console-bot
sudo systemctl status telegram-console-bot
```

Install Nginx proxy:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/telegram-console-bot
sudo ln -s /etc/nginx/sites-available/telegram-console-bot /etc/nginx/sites-enabled/telegram-console-bot
sudo nginx -t
sudo systemctl reload nginx
```

Add HTTPS with Certbot after pointing your domain to the VPS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Useful Commands

```bash
sudo journalctl -u telegram-console-bot -f
sudo systemctl restart telegram-console-bot
sudo systemctl stop telegram-console-bot
```

## Safety Notes

Keep `TELEGRAM_BOT_TOKEN` private. If you bind `CONSOLE_HOST=0.0.0.0`, always set `CONSOLE_API_KEY`; the bot refuses to start without it unless `ALLOW_UNSAFE_CONSOLE=true`.

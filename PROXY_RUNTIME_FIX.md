# Proxy Runtime Fix - Root Cause + Evidence

Date: 2026-11-17
Repo: https://github.com/AbubakarGSF/evilmarkhorsX_Bot

## Symptom (Railway logs)

```
WARNING PROXY_FILE nahi mila: /app/kro_proxies.txt
INFO    Proxy: OFF (direct)
INFO    Bot chalu | db=True | proxy=off | live=on | state=/data
GET https://api.x.com/1.1/account/verify_credentials.json -> 403 Forbidden (x N)
WARNING db_upsert 400 {"code":"23502", ...}
ERROR   reverify_loop TypeError: unsupported operand type(s) for +: 'NoneType' and 'NoneType'
```

## Root cause 1 - file image ke andar hi nahi thi (FIXED)

`Dockerfile` sirf do cheezein copy karta tha:

```dockerfile
COPY requirements.txt .
COPY evilmarkhorsx_bot.py bot.py
```

`kro_proxies.txt` GitHub par committed tha, lekin image ke andar copy nahi hota
tha. Container ka working dir `/app` hai aur `load_proxies()` `PROXY_FILE` ko
`HERE` (= `/app`) ke relative resolve karta hai - is liye `/app/kro_proxies.txt`
kabhi exist nahi karta tha. Environment variable kitne bhi sahi hon, file
image mein na ho to proxy kabhi load nahi hoti.

Fix:

```dockerfile
COPY kro_proxies.txt /app/kro_proxies.txt
```

Plus defence-in-depth: `load_proxies()` ab `PROXY_FILE` ke baad
`kro_proxies.txt` aur `proxies.txt` khud bhi dhoondta hai (script ke folder
mein), phir `STATE_DIR/proxies.txt`. Matlam `PROXY_FILE` galat/missing ho to
bhi proxy load hogi.

Startup line ab `Proxy: ON (42 configured, mode=rotate)` aani chahiye.

## Root cause 2 - `None + None` crash (FIXED)

`db_upsert()` ke andar:

```python
async def push(chunk, depth=0):
    ...
    if len(chunk) > 1 and depth < 4:
        mid = len(chunk) // 2
        return await push(chunk[:mid], depth + 1) + await push(chunk[mid:], depth + 1)
    # <- yahan se None return hota tha
```

Jab ek single bad row (ya depth >= 4) ka POST fail hota tha to `push()` `None`
return karta tha, aur `None + None` / `ok += None` par TypeError aata tha.
`reverify_loop` isi exception se mar jata tha.

Fix: har path par `int` return hota hai (`return 0`), aur recursion
`asyncio.gather` + `(a or 0) + (b or 0)` use karta hai.

## Root cause 3 - Supabase 23502 on partial upsert (FIXED)

`db_upsert` PostgREST upsert karta hai = `INSERT ... ON CONFLICT DO UPDATE`.
Postgres NOT NULL constraint **conflict resolution se pehle** check karta hai.
Reverify sirf `status/last_check/fails` bhejta hai, `cookies` (NOT NULL) nahi,
is liye har partial row par:

```
{"code":"23502","details":"Failing row contains (19, null, BGamuh51117, ...)"}
```

Fix (dono taraf):

1. Code: jin rows mein `cookies` nahi hota unhe `PATCH ?username=eq.<name>`
   se update kiya jata hai (concurrency 8); full rows pehle jaise upsert.
2. `schema.sql`: `cookies jsonb not null default '{}'::jsonb` +
   `alter table ... set default` migration lines (script idempotent hai).

## Root cause 4 - proxy credentials khud reject ho rahi hain (USER ACTION)

Yeh code se fix nahi hota. `gw.proxi.st:9999` khud credentials reject kar raha
hai. Local evidence (bot ke bahar, raw socket se test kiya):

```
SOCKS5 greeting      -> server offers username/password (0x02)
SOCKS5 auth reply    -> 0x01 0x01   = invalid username/password
HTTP CONNECT         -> 407 Proxy Authentication Required
```

Sabhi 42 entries, "KR/US/JP/..." har country code ke liye same result. DNS theek
hai (`gw.proxi.st -> 130.78.217.74`), port 9999 open hai, sirf `user:pass`
reject hota hai. Aapki di hui line thi:

```
gw.proxi.st:9999:nrta23q1-cc-KR:mo1KpFnV
```

Yani `user=nrta23q1-cc-KR`, `pass=mo1KpFnV`. Yeh combo gateway reject kar raha
hai - credentials expire/rotate ho gaye hain ya panel ka username pattern
alag hai.

Verify khud karein (repo root se):

```bash
python tools/check_proxies.py kro_proxies.txt
```

Sample output jab credentials theek na hon:

```
AUTH  socks5://nrta23q1-cc-KR@gw.proxi.st:9999 -> AUTH REJECTED (SOCKS5 0101)
summary: ok=0 auth_rejected=20 unreachable=22
=> Credentials gateway ne reject kar diye. Panel se naye user:pass lo.
```

### Kya karna hai

1. KRO panel se proxy credentials **dobara copy** karein (username + password,
   country format ke saath).
2. `kro_proxies.txt` mein same format mein paste karein:
   `socks5|gw.proxi.st:9999:<user>:<pass>`
3. Commit + push (Railway auto-deploy).
4. Telegram mein `/proxy reload` phir `/netcheck`.

Jab `/netcheck` mein `proxy ... HTTP 200/400 ...ms` aaye (404/407/ProxyError
nahi), matlab route zinda hai.

## Bonus fixes isi commit mein

- `live_check()`: `NameError: name 'r' is not defined` hataya (200 response
  par undefined `r` ko reference karne wali dead branch).
- `startup_netcheck`: report 4096 chars par truncate + asli exception log
  (`netcheck alert fail <id>: <error>`), pehle sirf id log hoti thi.
- `/netcheck` verdict: auth-reject case ka alag, clear message.
- `tools/check_proxies.py`: standalone checker (no deps).
- `tools/container_sim.py`: Docker image jaisa layout bana kar prove karta hai
  ke `kro_proxies.txt` load ho rahi hai.
- `tools/smoke_test.py`: proxy parsing + db_upsert regression test.

## Local verification (isi machine par)

```
$ python tools/container_sim.py
HERE = ...\app_sim_xxx\app
PROXY_FILE env = kro_proxies.txt
LOADED 42 proxies; first = socks5://***@gw.proxi.st:9999
STARTUP_LINE Proxy: ON (42 configured)
exit: 0

$ python tools/smoke_test.py
proxy parse OK
load_proxies (no PROXY_FILE env) OK -> 42 proxies
load_proxies (bad PROXY_FILE) OK -> 42 proxies
db_upsert partial rows -> PATCH OK (ok=5)
db_upsert full rows -> POST OK (ok=3)
db_upsert single bad row -> 0, no TypeError OK
ALL LOCAL TESTS PASSED
```

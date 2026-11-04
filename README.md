# Evil Markhors Bot

Single-file Telegram bot that reworks X/Twitter cookie files, logs in with
ULP (`user:pass:2fa`), verifies cookies, splits/filters cookie zips, runs
posting campaigns and keeps a Supabase account pool fresh.

Everything ships in `evilmarkhorsx_bot.py`; on first start the bot also
writes `requirements.txt`, `.env.example`, `schema.sql` and a few deployment
files if they are missing.

## Quick start

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # fill BOT_TOKEN, ADMIN_IDS, Supabase keys
python evilmarkhorsx_bot.py
```

Linux/macOS: `source venv/bin/activate`, `cp .env.example .env`.

The bot loads a `.env` file next to the script automatically (existing
environment variables win), and also reads the host's environment
variables, so Railway/Docker dashboards work unchanged.
`python evilmarkhorsx_bot.py --init` writes the helper files and exits.

## Supabase

1. Create a project.
2. Run `schema.sql` in the SQL editor.
3. Set `SUPABASE_URL` and `SUPABASE_KEY`. The key **must** be the
   `service_role` key: row level security is enabled and no policies exist,
   so the anon key cannot read/write `accounts`.
4. `/db stats` should answer. If it says the env is missing, the variables
   are not visible to the process.

Without Supabase the bot still works in file-only mode; DB buttons are
hidden and `/db` reports that it is off.

## Modes

| Mode | How | What it does |
| --- | --- | --- |
| cookies | send a `.txt`/`.zip` (auto-detected) | rewrites cookie files, verifies when `live` is on, optionally stores live accounts |
| ulp | send a `.txt`/`.zip` of `user:pass` lines | logs in, handles 2FA/e-mail codes, optional takeover (password/e-mail change) |
| verify | `/verify` then send a cookie zip | live/dead split with `working/`, `dead/`, `unknown/` + `summary.txt` (`unknown` = network/server error, not dead) |
| split | `/split field country` + zip | buckets a cookie zip by a metadata field |
| extract | `/extract country PK,IN year 2015-2020` + zip | keeps only matching accounts |

Verification first runs a dummy read-only request through the configured route.
If X is unreachable (proxy down, Cloudflare block page, DNS), the job stops
immediately with the real reason instead of grinding through every account and
returning `unknown`. `dead` with a reason is what suspension/lock looks like;
`unknown` only means the check could not be completed.

Commands: `/start /help /commands /status /diag /store /mode /verify /live
/takeover /newpass /newemail /finalize /cancel /split /splitoff /extract
/camp /stopcamp /report /db /broadcast /countrytest /tweet /tweetgo
/tweetcancel /delbatches /delbatch`

`/commands` pages through the full list.

## Campaigns

```
/camp new launch
/camp text            # then send variants for the current role
/camp role PK         # PK | IN | OTHER
/camp auto IN         # toggle auto variants per role
/camp media           # send photo/video
/camp filter country PK,IN
/camp filter year 2015-2020
/camp filter followers 500
/camp filter protected on
/camp filter clear
/camp limit 50
/camp delay 45-110
/camp parts 3
/camp preview
/camp source db       # or zip
/camp start
/stopcamp             # stops after the current account
```

Campaign runs post a live feed, then a report zip plus `links.txt` and a
delete batch (`/delbatch camp<id>`). Retryable failures are packed into
`retry/` inside the report zip. With `/camp cleanup off`, a thread that fails
mid-way keeps its posted parts; they land in `partial.txt` and in the same
delete batch, so nothing is orphaned.

`/stopcamp` stops after the current account (report still arrives). `/cancel`
hard-stops the job; posted/partial ids are still saved for `/delbatch`.

## Background jobs

Long operations run as background tasks with one job per user
(`JOBS` / `start_job` / `stop_job`), so the bot answers other commands
while a zip is processing. `/cancel` cancels the running job, clears its
batch and resets every per-user stage (store prompt, tweet media, split,
extract, country test, campaign stage). A janitor task expires stale store
prompts every `JOB_REAP_MIN` minutes, closes ULP clients whose code never
arrived after `PEND_TTL_MIN` minutes, and drops stale country-test state.

## Limits

- `ZIP_UPLOAD_MAX` (default 45 MB) - larger reports are rejected with a
  message instead of a failed upload.
- `MAX_FILES` (default 5000) - accounts read from one zip.
- `ZIP_MAX_FILE` (default 16 MB) - max uncompressed size of one entry.
- `ZIP_MAX_TOTAL` (default 256 MB) - max total uncompressed size per zip,
  so a zip bomb cannot exhaust memory.
- `PEND_TTL_MIN` (default 180) - how long a login/e-mail code prompt stays
  valid before the client is closed.
- `CAMP_STAGE_SEC` (default 21600 = 6 h) - how long `/camp start` waits for
  its cookie zip; after that a later zip is treated as a normal upload.
- `CONCURRENCY` (default 8) - parallel HTTP workers for cookie/verify splits.
- `DEAD_AFTER` (default 2) - failed checks before an account is marked dead.
- `MEDIA_WAIT_MAX` (default 300 s) - how long the bot polls X while it
  processes an uploaded video/GIF before giving up on that post.

## Proxies

X traffic can go through one or more proxies; Telegram and Supabase always
stay direct.

| Var | Meaning |
| --- | --- |
| `PROXIES` | comma/space separated list, e.g. `http://u:p@1.2.3.4:8080,socks5://5.6.7.8:1080` |
| `PROXY_FILE` | path to a file with one proxy per line (`#` comments ok); can live on the volume |
| `PROXY_TYPE` | scheme for lines without one: `http` (default), `https`, `socks5`, `socks5h` |
| `PROXY_MODE` | `rotate` (round robin, default) or `random` |
| `PROXY_TEST_URL` | health-check URL, default `https://api.x.com/1.1/account/verify_credentials.json` |
| `NETCHECK_ON_START` | send a one-time reachability summary to admins after deploy (default `1`) |

Supported schemes are `http`, `https`, `socks5` and `socks5h` (SOCKS needs
`httpx[socks]`, already in `requirements.txt`). `socks5h` asks the proxy to
resolve DNS remotely. Hiddify/xray share links (`vless://`, `vmess://`,
`ss://`, `trojan://`) are **not** HTTP proxies and cannot be used directly -
export the subscription into a local SOCKS5 listener (xray or sing-box) and
point `PROXIES` at it.

Accepted proxy line formats:

```
http://user:pass@1.2.3.4:8080
socks5://user:pass@1.2.3.4:1080
socks5h://user:pass@proxy.example.com:1080
45.144.31.82:5000:LzaUSER:CWNPASS      # provider panel, needs PROXY_TYPE=socks5
socks5|45.144.31.82:5000:LzaUSER:CWNPASS
socks5:45.144.31.82:5000:LzaUSER:CWNPASS
[2001:db8::1]:5000:LzaUSER:CWNPASS     # IPv6 (brackets optional)
45.144.31.82:5000                       # host:port, no auth
```

If a provider entry has no scheme, `PROXY_TYPE` decides what it is. An inline
`socks5|` / `socks5:` / `socks5h|` marker always wins, so mixed lists work.

Rotation is per request, and only connection errors fail over to the next
proxy; a request that was already sent is never retried, so a tweet cannot be
posted twice.

If a proxy password contains `,` or spaces, percent-encode it (`%2C`, `%20`)
or put the proxy in `PROXY_FILE` (one per line).

Provider links that look like `https://1.1.1.1:2001/name` are accepted, but the
path part is ignored (httpx only uses scheme/host/port/auth). If the proxy
needs a login, pass it as `http://user:pass@host:port` and run `/proxy test`:
`407` means auth is missing, an SSL error means the port is plain HTTP (use
`http://`).

Path-auth links are converted automatically: `https://host:port/user/pass`
(or `/user:pass`) becomes `https://user:pass@host:port`, so a provider that
prints credentials in the path works as-is.

Admin commands: `/proxy` (status, credentials masked), `/proxy test`
(ok/fail + latency per proxy), `/proxy list`, `/proxy detect entry`
(tries SOCKS5 and HTTP, tells you which protocol that host:port speaks),
`/proxy add [auto|type] entry` (validate, optionally auto-detect, and save to
`STATE_DIR/proxies.txt` on the volume), `/proxy clear` (remove saved runtime
proxies), `/proxy reload` (re-read `PROXY_FILE` and the runtime file),
`/proxy off|on` (disable/enable proxies for the current run without
redeploying). `/diag` shows the proxy count and the last network
error; `/netcheck` tests X direct, every proxy and Supabase in one go and
prints a verdict. After each deploy the bot runs the same check once and
sends the summary to `ADMIN_IDS`.

A SOCKS5 probe that ends with `ProtocolError: Malformed reply` means the
port is not speaking SOCKS5 (usually it is the HTTP endpoint). The provider
format is the same for both, so run `/proxy detect host:port:user:pass` and
add the type that returns JSON, or `/proxy add auto ...`. Timeouts are
hard-capped at 20s so one bad proxy cannot stall the whole test.

If every cookie comes back `unknown` with no `dead`, the cookies were never
checked - X was not reachable through the configured route. `/netcheck`
tells you whether direct or the proxies are the problem; suspension/lock
always shows up as `dead` with a reason.

With no `PROXIES` set the bot behaves exactly as before (direct).

## Deployment

Docker:

```bash
docker build -t evilmarkhors .
docker run --env-file .env evilmarkhors
```

Railway: connect the repo (or `railway up`); `railway.toml` uses the
Dockerfile and restarts on failure. Set the env vars in the dashboard.

## Files created at runtime

| Path | Purpose |
| --- | --- |
| `users.json` | per-user settings (`STORE_PATH`) |
| `batch_<uid>.json` | resumable ULP batch state |
| `camp_<uid>.json` | campaign configuration |
| `del_data/` | tweet-delete batches (JSON) |
| `camp_media/` | campaign photos/videos |

All of these live in the directory of `STORE_PATH` (default: next to the
script), so point `STORE_PATH` at your Railway volume, e.g.
`STORE_PATH=/data/users.json`, and settings, campaigns and media survive
redeploys.

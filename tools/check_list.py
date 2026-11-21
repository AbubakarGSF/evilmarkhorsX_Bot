"""Bulk proxy-list checker - raw asyncio tunnel + real TLS to api.x.com.

Kyun raw: httpx/anyio ke connect timeouts Windows par kabhi 21s tak atak jaate
hain, aur humein TLS certificate bhi check karna hai (free proxies aksar TLS
MITM karte hain - unke saath bot ka verify=True fail hota hai, is liye wo proxy
bot ke liye bekaar hai).

Per entry (host:port):
  1. TCP connect
  2. proxy tunnel to api.x.com:443  (HTTP CONNECT ya SOCKS5)
  3. TLS handshake with normal verification
  4. GET /1.1/account/verify_credentials.json -> HTTP status

Classes:
  OK      TLS verified + HTTP jawab mila (400/401/403/429 = route zinda)
  MITM    TLS verify fail (self-signed / MITM) -> bot ke liye unusable + khatra
  BLOCKED tunnel/TCP fail

Usage:
    python tools/check_list.py live_proxies.txt --concurrency 500 \
        --out live_working.txt --json live_working.json
"""
import argparse
import asyncio
import ipaddress
import json
import re
import ssl
import sys
import time

HOST = "api.x.com"
PATH = "/1.1/account/verify_credentials.json"

HOST = "api.x.com"
PATH = "/1.1/account/verify_credentials.json"
CTX = ssl.create_default_context()
GOOD_CODES = {200, 400, 401, 403, 404, 429}


def parse_entry(line):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    hint = None
    m = re.match(r"^(socks5h|socks5|https|http)://(.+)$", s, re.I)
    if m:
        hint = m.group(1).lower()
        if hint == "socks5h":
            hint = "socks5"
        s = m.group(2)
    host, _, port = s.rpartition(":")
    host = host.strip("[]")
    if not host or not port.isdigit():
        return None
    port = int(port)
    if not 0 < port < 65536:
        return None
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            return None
    except ValueError:
        pass
    return {"host": host, "port": port, "hint": hint}


async def _http_tunnel(r, w, tmo):
    w.write(("CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n" % (HOST, HOST)).encode())
    await w.drain()
    head = await asyncio.wait_for(r.readuntil(b"\r\n\r\n"), tmo)
    status = head.split(b"\r\n", 1)[0]
    if b" 200" not in status:
        return False, status.decode("latin-1", "ignore")[:50]
    return True, ""


async def _socks_tunnel(r, w, tmo):
    w.write(b"\x05\x01\x00")
    await w.drain()
    g = await asyncio.wait_for(r.readexactly(2), tmo)
    if g[0] != 5:
        return False, "not socks5"
    if g[1] != 0:
        return False, "needs auth (method %d)" % g[1]
    t = HOST.encode()
    w.write(b"\x05\x01\x00\x03" + bytes([len(t)]) + t + (443).to_bytes(2, "big"))
    await w.drain()
    rep = await asyncio.wait_for(r.readexactly(10), tmo)
    if rep[1] != 0:
        return False, "socks rep=%d" % rep[1]
    return True, ""


async def probe(entry, scheme, tmo):
    t0 = time.time()
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection(entry["host"], entry["port"]), tmo)
    except Exception as e:
        return {"cls": "BLOCKED", "why": "tcp " + type(e).__name__,
                "ms": int((time.time() - t0) * 1000)}
    try:
        fn = _http_tunnel if scheme == "http" else _socks_tunnel
        ok, why = await fn(r, w, tmo)
        if not ok:
            return {"cls": "BLOCKED", "why": why,
                    "ms": int((time.time() - t0) * 1000)}
        loop = asyncio.get_running_loop()
        tr = w.transport
        try:
            await loop.start_tls(tr, tr.get_protocol(), CTX, server_hostname=HOST)
        except ssl.SSLError as e:
            return {"cls": "MITM", "why": str(e)[:90],
                    "ms": int((time.time() - t0) * 1000)}
        except Exception as e:
            return {"cls": "BLOCKED", "why": "tls " + type(e).__name__,
                    "ms": int((time.time() - t0) * 1000)}
        w.write(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: curl/8\r\n"
                 "Accept: */*\r\nConnection: close\r\n\r\n" % (PATH, HOST)).encode())
        await w.drain()
        line = await asyncio.wait_for(r.readline(), tmo)
        m = re.match(rb"HTTP/\d(?:\.\d)?\s+(\d{3})", line)
        code = int(m.group(1)) if m else None
        return {"cls": "OK" if code else "BLOCKED",
                "code": code, "why": "" if code else "no status line",
                "ms": int((time.time() - t0) * 1000)}
    except asyncio.TimeoutError:
        return {"cls": "BLOCKED", "why": "timeout",
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"cls": "BLOCKED", "why": type(e).__name__,
                "ms": int((time.time() - t0) * 1000)}
    finally:
        try:
            w.close()
        except Exception:
            pass


async def check_one(entry, sem, tmo, order):
    async with sem:
        order = ([entry["hint"]] + [o for o in order if o != entry["hint"]]
                 if entry["hint"] else order)
        last = None
        for scheme in order:
            r = await probe(entry, scheme, tmo)
            r.update({"scheme": scheme, "host": entry["host"],
                      "port": entry["port"]})
            last = r
            if r["cls"] in ("OK", "MITM"):
                return r
        return last


async def run(entries, sem_size, tmo, order, quiet):
    sem = asyncio.Semaphore(sem_size)
    done = 0
    counts = {"OK": 0, "MITM": 0, "BLOCKED": 0}
    keep = []

    async def wrapped(e):
        nonlocal done
        r = await check_one(e, sem, tmo, order)
        done += 1
        counts[r["cls"]] = counts.get(r["cls"], 0) + 1
        if r["cls"] in ("OK", "MITM"):
            keep.append(r)
        if not quiet and (done % 250 == 0 or r["cls"] == "OK"):
            print("  %d/%d ok=%d mitm=%d blocked=%d"
                  % (done, len(entries), counts["OK"], counts["MITM"],
                     counts["BLOCKED"]), flush=True)
            if r["cls"] == "OK":
                print("      + %s|%s:%d -> %s %dms"
                      % (r["scheme"], r["host"], r["port"], r.get("code"),
                         r.get("ms", 0)), flush=True)

    await asyncio.gather(*(wrapped(e) for e in entries))
    return keep, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="live_working.txt")
    ap.add_argument("--json", default="live_working.json")
    ap.add_argument("--concurrency", type=int, default=500)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--order", default="http,socks5")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--path", default=PATH)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()


    order = [p.strip() for p in args.order.split(",")
             if p.strip() in ("http", "socks5")] or ["http", "socks5"]

    with open(args.input, encoding="utf-8", errors="ignore") as fh:
        raw = fh.read().splitlines()
    entries, seen = [], set()
    for line in raw:
        e = parse_entry(line)
        if not e:
            continue
        key = (e["host"], e["port"])
        if key in seen:
            continue
        seen.add(key)
        entries.append(e)
    if args.limit:
        entries = entries[:args.limit]

    print("entries: %d | target %s:443 | concurrency=%d timeout=%.1fs"
          % (len(entries), HOST, args.concurrency, args.timeout), flush=True)
    t0 = time.time()
    keep, counts = asyncio.run(run(entries, args.concurrency, args.timeout,
                                   order, args.quiet))
    print("tested %d in %.0fs | OK=%d MITM=%d BLOCKED=%d"
          % (len(entries), time.time() - t0, counts["OK"], counts["MITM"],
             counts["BLOCKED"]), flush=True)

    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=1)

    ok = [r for r in keep if r["cls"] == "OK" and r.get("code") in GOOD_CODES]
    ok.sort(key=lambda r: ({400: 0, 401: 1, 429: 2, 403: 3}.get(r["code"], 9),
                           r.get("ms", 0)))
    lines = ["# verified proxies %s | target https://%s%s"
             % (time.strftime("%Y-%m-%d %H:%M"), HOST, PATH),
             "# format: scheme|host:port  (TLS verified, X reachable)"]
    for r in ok:
        lines.append("%s|%s:%d" % (r["scheme"], r["host"], r["port"]))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\n%-8s %-22s %5s %7s" % ("SCHEME", "PROXY", "CODE", "MS"))
    for r in ok[:80]:
        print("%-8s %-22s %5s %7d"
              % (r["scheme"], "%s:%d" % (r["host"], r["port"]),
                 r.get("code"), r.get("ms", 0)))
    if len(ok) > 80:
        print("... %d more" % (len(ok) - 80))
    if counts["MITM"]:
        print("\n!! %d proxies TLS MITM kar rahe the (cert verify fail) - "
              "inhe use NA karein; bot ka verify=True unhe reject karta hai."
              % counts["MITM"])
    print("\nverified -> %s (%d) | details -> %s"
          % (args.out, len(ok), args.json))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

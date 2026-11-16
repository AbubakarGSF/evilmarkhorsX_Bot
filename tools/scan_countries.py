"""Country-coverage scanner for a SOCKS5 gateway.

Har ISO 3166-1 alpha-2 country ke liye `<prefix><CC>` username se SOCKS5 auth
check karta hai. Sirf auth pass hone wale entries ka exit IP bhi nikalta hai, aur
wo lines `--out` par repo ke proxy format mein likhta hai.

Usage:
    python tools/scan_countries.py --host gw.proxi.st --port 9999 \\
        --user-prefix nrta23q1-cc- --password mo1KpFnV \\
        --workers 8 --out kro_proxies.working.txt

Kuch bhi auth pass na kare to exit code 2 aur out file khaali/na-bane.
"""
import argparse
import json
import socket
import ssl
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

try:
    import pycountry
    ISO = sorted({c.alpha_2 for c in pycountry.countries})
except Exception:  # pragma: no cover - pycountry optional
    ISO = ("AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG "
           "BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI "
           "CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH "
           "ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ "
           "GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT "
           "JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS "
           "LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU "
           "MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG "
           "PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG "
           "SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK "
           "TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU "
           "WF WS YE YT ZA ZM ZW").split()

TARGET_HOST = "api.ipify.org"
TARGET_PORT = 443


def socks5_auth(host, port, user, pwd, timeout):
    """Return (status, detail, ms). status: OK | REJECT | UNREACHABLE."""
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except Exception as e:
        return "UNREACHABLE", type(e).__name__, int((time.time() - t0) * 1000)
    try:
        s.settimeout(timeout)
        s.sendall(b"\x05\x02\x00\x02")
        r = s.recv(2)
        if len(r) < 2 or r[0] != 5:
            return "UNREACHABLE", "bad greeting %s" % r.hex(), int((time.time() - t0) * 1000)
        if r[1] != 0x02:
            return "REJECT", "server auth method %s" % hex(r[1]), int((time.time() - t0) * 1000)
        u, p = user.encode(), pwd.encode()
        s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        rep = s.recv(2)
        ms = int((time.time() - t0) * 1000)
        if rep == b"\x01\x00":
            return "OK", "", ms
        return "REJECT", rep.hex(), ms
    except Exception as e:
        return "UNREACHABLE", type(e).__name__, int((time.time() - t0) * 1000)
    finally:
        try:
            s.close()
        except Exception:
            pass


def exit_ip(host, port, user, pwd, timeout):
    """Full SOCKS5 CONNECT + TLS GET -> exit IP (proof the route works)."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except Exception as e:
        return None, type(e).__name__
    try:
        s.settimeout(timeout)
        s.sendall(b"\x05\x02\x00\x02")
        _, method = s.recv(2)
        if method == 0x02:
            u, p = user.encode(), pwd.encode()
            s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
            if s.recv(2) != b"\x01\x00":
                return None, "auth"
        t = TARGET_HOST.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(t)]) + t + struct.pack(">H", TARGET_PORT))
        rep = s.recv(10)
        if not rep or rep[1] != 0:
            return None, "connect %s" % (rep.hex() if rep else "empty")
        ss = ssl.create_default_context().wrap_socket(s, server_hostname=TARGET_HOST)
        ss.sendall(("GET /?format=json HTTP/1.1\r\nHost: %s\r\n"
                    "User-Agent: curl/8\r\nConnection: close\r\n\r\n" % TARGET_HOST).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += ss.recv(4096)
        body = buf.split(b"\r\n\r\n", 1)[1]
        return body.strip().decode("utf-8", "ignore")[:120], None
    except Exception as e:
        return None, type(e).__name__
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="gw.proxi.st")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--user-prefix", default="nrta23q1-cc-")
    ap.add_argument("--password", default="mo1KpFnV")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--delay", type=float, default=0.25,
                    help="har attempt se pehle sleep (gateway throttling se bachne ke liye)")
    ap.add_argument("--out", default="kro_proxies.working.txt")
    ap.add_argument("--json", default="scan_countries.json")
    args = ap.parse_args()

    codes = ISO
    lock = threading.Lock()
    rows = []

    print("scanning %d countries on %s:%d (workers=%d)" %
          (len(codes), args.host, args.port, args.workers), flush=True)

    def work(cc):
        user = args.user_prefix + cc
        status, detail, ms = "UNREACHABLE", "no attempt", 0
        for attempt in range(args.retries + 1):
            time.sleep(args.delay)
            status, detail, ms = socks5_auth(args.host, args.port, user,
                                             args.password, args.timeout)
            if status != "UNREACHABLE":
                break
            time.sleep(1.0 * (attempt + 1))
        ip = None
        if status == "OK":
            ip, err = exit_ip(args.host, args.port, user, args.password, args.timeout)
            detail = ip or ("connect: " + str(err))
        row = {"cc": cc, "user": user, "status": status,
               "detail": detail, "ms": ms}
        with lock:
            rows.append(row)
            mark = {"OK": "OK  ", "REJECT": "AUTH", "UNREACHABLE": "FAIL"}[status]
            print("%s %s %-22s %6dms %s" % (mark, cc, user, ms, detail), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(work, codes))

    ok = sorted([r for r in rows if r["status"] == "OK"], key=lambda r: r["cc"])
    rej = [r for r in rows if r["status"] == "REJECT"]
    bad = [r for r in rows if r["status"] == "UNREACHABLE"]
    print("\nsummary: ok=%d auth_rejected=%d unreachable=%d total=%d"
          % (len(ok), len(rej), len(bad), len(rows)))

    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)

    if ok:
        lines = ["# Working gateway entries scanned %s" % time.strftime("%Y-%m-%d %H:%M"),
                 "# format: socks5|host:port:user:pass"]
        for r in ok:
            lines.append("socks5|%s:%d:%s:%s" % (args.host, args.port,
                                                 r["user"], args.password))
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print("working entries ->", args.out)
        return 0
    print("koi bhi country auth pass nahi hui - credentials/IP panel se verify karein")
    return 2


if __name__ == "__main__":
    sys.exit(main())

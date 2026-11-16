"""KRO proxy file checker - no third-party deps.

Usage:
    python tools/check_proxies.py [path-to-proxy-file]

Har line ke liye:
  1. TCP connect
  2. SOCKS5 / HTTP proxy handshake + auth
  3. agar auth pass ho to api.ipify.org se exit IP

Exit codes: 0 = koi auth-OK proxy mila, 2 = sab reject/unreachable.
"""
import base64
import json
import re
import socket
import ssl
import struct
import sys
from concurrent.futures import ThreadPoolExecutor

DEFAULT_FILE = "kro_proxies.txt"
TARGET_HOST = "api.ipify.org"
TARGET_PORT = 443
TIMEOUT = 8
WORKERS = 12


def parse_line(line):
    """socks5|host:port:user:pass | http://user:pass@host:port | host:port:user:pass"""
    s = line.strip().strip('"').strip("'")
    if not s or s.startswith("#"):
        return None
    scheme = None
    m = re.match(r"^(socks5h|socks5|https|http)\s*(?::\/\/|\||:)\s*(.*)$", s, re.I)
    if m and m.group(2):
        scheme, s = m.group(1).lower(), m.group(2)
    if scheme == "socks5h":
        scheme = "socks5"
    scheme = scheme or "socks5"
    if "@" in s:
        auth, hostport = s.rsplit("@", 1)
        user, _, pwd = auth.partition(":")
        host, _, port = hostport.rpartition(":")
    else:
        bits = s.split(":")
        if len(bits) < 2:
            return None
        host, port = bits[0], bits[1]
        user = bits[2] if len(bits) > 2 else ""
        pwd = bits[3] if len(bits) > 3 else ""
    if not host or not port.isdigit():
        return None
    return {"scheme": scheme, "host": host, "port": int(port),
            "user": user, "pwd": pwd, "raw": line.strip()}


def socks5_connect(host, port, user, pwd, thost=TARGET_HOST, tport=TARGET_PORT):
    try:
        s = socket.create_connection((host, port), timeout=TIMEOUT)
    except Exception as e:
        return None, "TCP connect: %s" % type(e).__name__
    try:
        methods = b"\x05\x02\x00\x02" if user else b"\x05\x01\x00"
        s.sendall(methods)
        ver, method = s.recv(2)
        if ver != 5:
            return None, "not a SOCKS5 server"
        if method == 0x02:
            u, p = user.encode(), pwd.encode()
            s.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
            r = s.recv(2)
            if r != b"\x01\x00":
                return None, "AUTH REJECTED (SOCKS5 %s)" % r.hex()
        elif method != 0x00:
            return None, "no acceptable auth method (%s)" % hex(method)
        t = thost.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(t)]) + t + struct.pack(">H", tport))
        rep = s.recv(10)
        if not rep or rep[0] != 5 or rep[1] != 0:
            return None, "CONNECT failed (%s)" % (rep.hex() if rep else "empty")
        return s, None
    except Exception as e:
        s.close()
        return None, "%s: %s" % (type(e).__name__, str(e)[:60])


def http_proxy_connect(host, port, user, pwd, thost=TARGET_HOST, tport=TARGET_PORT):
    try:
        s = socket.create_connection((host, port), timeout=TIMEOUT)
    except Exception as e:
        return None, "TCP connect: %s" % type(e).__name__
    try:
        auth = ""
        if user:
            tok = base64.b64encode(("%s:%s" % (user, pwd)).encode()).decode()
            auth = "Proxy-Authorization: Basic %s\r\n" % tok
        req = ("CONNECT %s:%s HTTP/1.1\r\nHost: %s:%s\r\n%s\r\n"
               % (thost, tport, thost, tport, auth))
        s.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = s.recv(1024)
            if not chunk:
                break
            head += chunk
            if len(head) > 8192:
                break
        status = head.split(b"\r\n", 1)[0].decode("latin-1", "ignore")
        if " 200 " not in status:
            return None, "HTTP proxy: %s" % status
        return s, None
    except Exception as e:
        s.close()
        return None, "%s: %s" % (type(e).__name__, str(e)[:60])


def exit_ip(cfg):
    fn = socks5_connect if cfg["scheme"] == "socks5" else http_proxy_connect
    s, err = fn(cfg["host"], cfg["port"], cfg["user"], cfg["pwd"])
    if not s:
        return None, err
    try:
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname=TARGET_HOST)
        req = ("GET /?format=json HTTP/1.1\r\nHost: %s\r\n"
               "User-Agent: curl/8\r\nConnection: close\r\n\r\n" % TARGET_HOST)
        ss.sendall(req.encode())
        buf = b""
        while True:
            chunk = ss.recv(4096)
            if not chunk:
                break
            buf += chunk
        body = buf.split(b"\r\n\r\n", 1)[1]
        return body.strip().decode("utf-8", "ignore")[:200], None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:60])
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        print("file nahi mili:", path)
        return 1
    cfgs = [c for c in (parse_line(l) for l in lines) if c]
    print("file:", path, "| entries:", len(cfgs), "| workers:", WORKERS)
    ok = bad_auth = unreachable = 0
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(exit_ip, c) for c in cfgs]
        for cfg, fut in zip(cfgs, futures):
            ip, err = fut.result()
            label = "%s://%s@%s:%s" % (cfg["scheme"], cfg["user"] or "-",
                                       cfg["host"], cfg["port"])
            if ip:
                ok += 1
                results.append("OK    %s -> %s" % (label, ip))
            elif err and ("AUTH" in err.upper() or "407" in err):
                bad_auth += 1
                results.append("AUTH  %s -> %s" % (label, err))
            else:
                unreachable += 1
                results.append("FAIL  %s -> %s" % (label, err))
    for line in results:
        print(line)
    print("\nsummary: ok=%d auth_rejected=%d unreachable=%d" % (ok, bad_auth, unreachable))
    if not ok and bad_auth:
        print("=> Credentials gateway ne reject kar diye. Panel se naye user:pass lo.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

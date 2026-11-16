# Country Proxy Scan Report

Date: 2026-11-17
Gateway: `gw.proxi.st:9999`
Credential shape: `nrta23q1-cc-<ISO2>` / `mo1KpFnV`
Entries tested: **249 / 249 ISO 3166-1 alpha-2 codes** (full list you pasted)

## Result

| Status | Count | Meaning |
| --- | --- | --- |
| `AUTH_OK` | **0** | koi bhi country authenticate nahi hui |
| `AUTH_REJECT` | **249** | server ne `0x01 0x01` = invalid username/password diya |
| `UNREACHABLE` | 0 | gateway reachable tha, sab attempts ka jawab aaya |

Kuch bhi "OK" nahi nikla, is liye `kro_proxies.txt` mein naya entry add nahi
kiya gaya (dead entries sirf har request 3x slow karti hain).

## Method (bot ke bahar, taake bot ka code involved na ho)

Raw TCP + SOCKS5 handshake, no httpx, no bot:

```
C: 05 02 00 02                    (no-auth + user/pass offer)
S: 05 02                          (server: user/pass chahiye)
C: 01 <len(user)> user <len(pass)> pass
S: 01 01                          (invalid username/password)  <-- har country
```

HTTP proxy on the same port (`CONNECT` + `Proxy-Authorization`) bhi:

```
S: HTTP/1.1 407 Proxy Authentication Required
```

Same 407 for a **deliberately wrong** password, aur same 407 for the real one -
yani gateway `user:pass` jodi ko hi nahi maan raha.

Sample (KR, aur 9 aur countries, pehle clean state par - sweep se pehle):

```
AD  AUTH_REJECT:0101  1105ms
KR  AUTH_REJECT:0101   973ms
US  AUTH_REJECT:0101   955ms
DE  AUTH_REJECT:0101  2707ms
GB  AUTH_REJECT:0101  1817ms
PK  AUTH_REJECT:0101   985ms
SA  AUTH_REJECT:0101  1123ms
AE  AUTH_REJECT:0101  1043ms
JP  AUTH_REJECT:0101   962ms
SG  AUTH_REJECT:0101   952ms
```

## Username patterns bhi try kiye (same password)

```
nrta23q1-cc-KR               -> REJECT 0101
nrta23q1-KR                  -> REJECT 0101
nrta23q1-country-KR          -> REJECT 0101
nrta23q1-cc-kr               -> REJECT 0101
nrta23q1-cc-KR-session-1     -> REJECT 0101
nrta23q1-cc-KR-1             -> REJECT 0101
nrta23q1-cc-KR-sticky        -> REJECT 0101
KR-nrta23q1-cc               -> REJECT 0101
```

Pattern galat hone ka masla nahi lagta - account/credential level par reject ho
raha hai.

## Gateway throttling (important)

Full sweep ke baad gateway ne is machine ke IP (`119.155.207.206`) se naye
connections **drop** kar diye (TCP timeout, SOCKS5 reply bhi nahi). 60s cooldown
ke baad bhi kuch connections timeout hue, kuch par phir `0101`. Iska matlab:

- gateway alive hai, port `9999` open hai, DNS theek (`130.78.217.74`)
- burst scanning par provider IP ko temporarily throttle karta hai
- is liye `tools/scan_countries.py` ka default ab `--workers 4 --delay 0.25`
  hai (gentle scan)

Iska bot se koi taluq nahi - `/netcheck` mein timeout dikhe to ye provider-side
throttle hai.

## Ab kya karna hai (2 minute)

1. Panel kholein -> proxy credentials / "Generate" / "Reset password" section.
2. Exact line copy karein, ideally panel ke **copy button** se (hand-type na
   karein). Format kuch aisa hona chahiye:
   `gw.proxi.st:9999:<user>:<pass>`
3. Ek entry yahan chat mein paste kar dein - main foran re-scan kar ke bata
   dunga kaunse countries chalti hain.
4. Ya khud chalayein (repo root se):

```bash
python tools/check_proxies.py kro_proxies_all.txt
```

5. Jab working countries mil jayen, sirf woh `kro_proxies.txt` mein rakhein:

```bash
python tools/scan_countries.py --password "<naya-pass>" --out kro_proxies.txt
```

`--out kro_proxies.txt` sirf `AUTH_OK` entries likhta hai (comments header ke
saath), is liye dead countries file mein nahi aati.

## Files

| File | Kya hai |
| --- | --- |
| `kro_proxies.txt` | active list (42 curated entries) - abhi bhi gateway reject karta hai |
| `kro_proxies_all.txt` | **naya** - poore 249 ISO codes, ready for valid credentials |
| `tools/scan_countries.py` | **naya** - sab countries scan, sirf OK entries out file mein |
| `tools/check_proxies.py` | ek file ke entries check (auth + exit IP) |

Full ISO list use karni ho to Railway par:

```
PROXY_FILE=kro_proxies_all.txt
```

...lekin pehle credentials valid hone chahiye, warna proxy OFF jaisa hi result
rahega (har X request fail hogi, accounts `unknown` rahenge - `dead` nahi).

"""Verify kro_proxies_all.txt parses to 249 entries via the bot's own loader."""
import os
import sys

os.environ.setdefault("BOT_TOKEN", "123:ABC")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("BEARER_TOKEN", "test")
os.environ["PROXY_FILE"] = "kro_proxies_all.txt"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evilmarkhorsx_bot as b

got = b.load_proxies()
codes = sorted(p.split("//")[1].split("@")[0].split("-")[-1] for p in got)
print("loaded:", len(got))
print("unique country codes:", len(set(codes)))
print("first:", b.mask_proxy(got[0]))
print("last :", b.mask_proxy(got[-1]))
assert len(got) == 249, len(got)
assert len(set(codes)) == 249
print("OK: all 249 country entries parsed")

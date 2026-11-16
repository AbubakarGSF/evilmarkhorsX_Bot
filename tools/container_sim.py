"""Simulate the exact /app container layout: only bot.py + kro_proxies.txt."""
import os
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(tempfile.mkdtemp(prefix="app_sim_"), "app")
os.makedirs(APP)

# Samething Dockerfile does
shutil.copy2(os.path.join(SRC, "evilmarkhorsx_bot.py"), os.path.join(APP, "bot.py"))
shutil.copy2(os.path.join(SRC, "kro_proxies.txt"), os.path.join(APP, "kro_proxies.txt"))

probe = r'''
import logging, os, sys
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
sys.path.insert(0, os.getcwd())
import bot
print("HERE =", bot.HERE)
print("PROXY_FILE env =", os.getenv("PROXY_FILE"))
print("STATE_DIR =", bot.STATE_DIR)
got = bot.load_proxies()
print("LOADED", len(got), "proxies; first =", bot.mask_proxy(got[0]) if got else None)
print("STARTUP_LINE Proxy:", ("ON (%d configured)" % len(got)) if got else "OFF (direct)")
'''
env = dict(os.environ)
env.update({"PROXY_FILE": "kro_proxies.txt", "PROXY_TYPE": "socks5",
            "BOT_TOKEN": "123:ABC", "ADMIN_IDS": "1",
            "BEARER_TOKEN": "test", "STORE_PATH": os.path.join(APP, "users.json")})
r = subprocess.run([sys.executable, "-c", probe], cwd=APP, env=env,
                   capture_output=True, text=True, timeout=120)
print(r.stdout)
if r.returncode:
    print("STDERR:", r.stderr[-2000:])
print("exit:", r.returncode)
shutil.rmtree(os.path.dirname(APP), ignore_errors=True)
sys.exit(0 if r.returncode == 0 and "LOADED 42" in r.stdout else 1)

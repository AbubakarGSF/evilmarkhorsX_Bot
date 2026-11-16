"""Local smoke test for the proxy loader + db_upsert (no network, no Telegram)."""
import asyncio
import os
import sys

os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("BOT_TOKEN", "123:ABC")
os.environ.setdefault("BEARER_TOKEN", "test-bearer-token")
os.environ.pop("PROXIES", None)
os.environ.pop("PROXY_FILE", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evilmarkhorsx_bot as b  # noqa: E402


def t_proxy_parse():
    cases = {
        "socks5|gw.proxi.st:9999:nrta23q1-cc-KR:mo1KpFnV ": "socks5://nrta23q1-cc-KR:mo1KpFnV@gw.proxi.st:9999",
        "gw.proxi.st:9999:u:p": "http://u:p@gw.proxi.st:9999",
        "# comment": None,
        "": None,
        "http://u:p@1.2.3.4:8080": "http://u:p@1.2.3.4:8080",
    }
    for raw, want in cases.items():
        got = b.norm_proxy(raw)
        assert got == want, (raw, got, want)
    print("proxy parse OK")


def t_load_without_env_file():
    os.environ.pop("PROXY_FILE", None)
    got = b.load_proxies()
    assert len(got) >= 10, len(got)
    assert all(p.startswith("socks5://") for p in got), got[:3]
    print("load_proxies (no PROXY_FILE env) OK ->", len(got), "proxies")


def t_load_bad_env_file():
    os.environ["PROXY_FILE"] = "does_not_exist.txt"
    got = b.load_proxies()
    assert len(got) >= 10, len(got)
    print("load_proxies (bad PROXY_FILE) OK ->", len(got), "proxies")
    os.environ.pop("PROXY_FILE", None)


class FakeResp:
    def __init__(self, code, text=""):
        self.status_code = code
        self.text = text


class FakeClient:
    """Fails every POST (like 23502) and records PATCH calls."""

    def __init__(self, post_code=400):
        self.post_code = post_code
        self.posts = []
        self.patches = []

    async def post(self, url, params=None, headers=None, json=None, timeout=None):
        self.posts.append(json)
        return FakeResp(self.post_code, '{"code":"23502"}')

    async def patch(self, url, params=None, headers=None, json=None, timeout=None):
        self.patches.append((params, json))
        return FakeResp(204, "")


async def t_db_upsert_no_none_crash():
    b.SUPABASE_URL = "https://x.supabase.co"
    b.SUPABASE_KEY = "k" * 50
    c = FakeClient()
    partial = [{"username": "a%d" % i, "status": "live", "last_check": "now"}
               for i in range(5)]
    ok, err = await b.db_upsert(c, partial)
    assert ok == 5, (ok, err)
    assert len(c.patches) == 5, len(c.patches)
    print("db_upsert partial rows -> PATCH OK (ok=%s)" % ok)

    c = FakeClient(post_code=201)
    full = [{"username": "b%d" % i, "cookies": {"auth_token": "t"}} for i in range(3)]
    ok, err = await b.db_upsert(c, full)
    assert ok == 3, (ok, err)
    print("db_upsert full rows -> POST OK (ok=%s)" % ok)

    # single failing row: push() must return 0, not None (old None+None crash)
    c = FakeClient(post_code=400)
    ok, err = await b.db_upsert(c, [{"username": "z", "cookies": {"a": 1}}])
    assert ok == 0 and isinstance(ok, int), (ok, err)
    print("db_upsert single bad row -> 0, no TypeError OK")


if __name__ == "__main__":
    t_proxy_parse()
    t_load_without_env_file()
    t_load_bad_env_file()
    asyncio.run(t_db_upsert_no_none_crash())
    print("ALL LOCAL TESTS PASSED")

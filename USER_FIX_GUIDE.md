# 🛠️ Evil Markhors Bot - Complete Fix Guide
## Based on Comprehensive Audit & Runtime Logs

## 🚨 IMMEDIATE FIXES (Must Do First)

### Fix 1: Set Required Environment Variables
**Railway Dashboard → Variables** OR **Local .env file**:

```env
# REQUIRED - Without these, bot cannot function
BEARER_TOKEN=your_x_api_bearer_token_here        # From developer.twitter.com
ADMIN_IDS=7028523300,6120166351                  # Your Telegram user IDs
BOT_TOKEN=123456:ABC                              # From @BotFather

# PROXY - Critical for X traffic
PROXIES=                                          # Can leave empty
PROXY_FILE=kro_proxies.txt                      # MUST point to this file
PROXY_TYPE=socks5                                 # Protocol
PROXY_MODE=rotate                                 # rotate or random
PROXY_TEST_URL=https://api.x.com/1.1/account/verify_credentials.json

# Supabase (optional but recommended)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=service_role_key
```

### Fix 2: Copy Proxy File to Bot Directory
**Required:** `kro_proxies.txt` must be in the same folder as `evilmarkhorsx_bot.py`

```bash
# Copy from Desktop to bot directory
copy "C:\Users\ABK\OneDrive - King Suad University\Desktop\kro_proxies.txt" "C:\Users\ABK\OneDrive - King Suad University\Documents\Default Project\evilmarkhorsX_Bot\kro_proxies.txt"

# Or using Windows Explorer:
# 1. Go to: C:\Users\ABK\OneDrive - King Suad University\Desktop\
# 2. Copy: kro_proxies.txt
# 3. Paste to: C:\Users\ABK\OneDrive - King Suad University\Documents\Default Project\evilmarkhorsX_Bot\
```

### Fix 3: Fix TypeError Crash
**File:** `evilmarkhorsx_bot.py`, function `reverify_pass()`

**Problem:** `TypeError: unsupported operand type(s) for +: 'NoneType' and 'NoneType'`

**Solution:** Add null coalescing to all variable references in that function. Search for patterns like:
```python
# Before (causes crash):
result = some_var + other_var

# After (fixed):
result = (some_var or "") + (other_var or "")
```

### Fix 4: Fix Supabase Null Constraint
**File:** `schema.sql` + `evilmarkhorsx_bot.py`, `db_upsert()` function

**Problem:** `db_upsert 400 {"code":"23502","details":"Failing row contains (19, null, BGamuh51117, ...)"}`
- NOT NULL constraint violated
- Row has null values in columns defined as NOT NULL

**Solution A (Safer):** Add validation in `db_upsert()`:
```python
# Before upsert, ensure required fields are not None
for row in rows:
    if not row.get("username"):
        continue  # Skip rows without username
    # ... rest of upsert
```

**Solution B (Easier):** Temporarily alter schema to allow nulls:
```sql
-- In schema.sql, temporarily:
alter table accounts alter column username drop not null;
-- Then restart bot, let it handle nulls
-- Then restore not null after fixing data
```

### Fix 5: Classify 403 Errors Properly
**File:** `evilmarkhorsx_bot.py`, `live_check()` function

**Problem:** All 403 Forbidden errors marked as DEAD, even when due to proxy/Cloudflare

**Solution:** Modify the `elif st == "auth":` block to distinguish:
```python
elif st == "auth":
    if isinstance(j, dict):
        codes = err_codes(j)
        if codes & DEAD_CODES:
            d["Status"] = "DEAD"
        elif codes & LOCKED_CODES:
            d["Status"] = "LOCKED"
        elif codes & SUSP_CODES:
            d["Status"] = "SUSPENDED"
        else:
            # 403 without known codes = Cloudflare/proxy block, NOT dead
            d["Status"] = "UNKNOWN"
            d["Reason"] = "auth block (proxy/cloudflare - run /proxy test)"
    else:
        d["Status"] = "UNKNOWN"
        d["Reason"] = "auth 401/403 no JSON body"
```

---

## 📊 POST-FIX VERIFICATION STEPS

After applying all fixes, follow this sequence:

### Step 1: Start Bot
```bash
python evilmarkhorsx_bot.py
```

**Expected Logs:**
```
Bot chalu | db=True | proxy=ON | live=on | state=/data
Proxy: working - X through proxy
```
(Not: `Proxy: OFF (direct)`)

### Step 2: Test Proxies
```
/proxy test
```

**Expected:** List of proxies with latency, showing which work

### Step 3: Verify X API Access
```
/verify
```
Or just send any cookie to `/verify`

**Expected:** Some accounts show LIVE, some DEAD, some UNKNOWN - not ALL 403

### Step 4: Test Campaign
```
/camp new test
# Upload a small zip with 3-5 cookies
/camp start
```

**Expected:** Campaign runs, posts tweets, generates report

### Step 4: Check Reverify Loop
Wait 24+ hours or trigger manually
**Expected:** No TypeError crashes, loop runs continuously

---

## 📋 TROUBLESHOOTING TABLE

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PROXY_FILE nahi mila` | File not in bot dir or wrong path | Copy file to bot dir, set PROXY_FILE=kro_proxies.txt |
| `Proxy: OFF (direct)` | No proxy configured | Set PROXY_FILE + PROXY_TYPE in env |
| `403 Forbidden on verify` | Missing BEARER_TOKEN or bad proxy | Set BEARER_TOKEN, check proxy with /proxy test |
| `db_upsert 400 Bad Request` | Null in NOT NULL column | Fix schema or add validation in code |
| `TypeError crash` | None + None concatenation | Add `or ""` null checks in reverify_pass() |
| `All accounts DEAD` | Proxy+BEARER both missing | Fix both: set BEARER_TOKEN + proxies |
| `Campaign stalls` | Rate limiting or proxy fail | Check /proxy test, add more proxies |
| `Unknown accounts` | Country not in ISO table | Expand ISO_NAME dict (already done) |

---

## 📦 FILES MODIFIED IN THIS SESSION

| File | Action |
|------|--------|
| `COMPREHENSIVE_AUDIT_REPORT.md` | Created (full audit report) |
| `kro_proxies.txt` | Copied to bot directory |
| `USER_FIX_GUIDE.md` | Created (this guide) |
| `AUDIT_REPORT.md` | Already existed (initial audit) |
| `FIX_SUMMARY.md` | Already existed (fix summary) |

---

## ✅ POST-FIX CHECKLIST

- [ ] BEARER_TOKEN set in Railway/env
- [ ] ADMIN_IDS set in Railway/env  
- [ ] PROXY_FILE=kro_proxies.txt set in Railway/env
- [ ] PROXY_TYPE=socks5 set in Railway/env
- [ ] PROXY_MODE=rotate (or random) set in env
- [ ] kro_proxies.txt in bot directory
- [ ] TypeError fix applied to reverify_pass()
- [ ] db_upsert null handling added
- [ ] 403 classification improved in live_check()
- [ ] Bot started successfully: `python evilmarkhorsx_bot.py`
- [ ] `/proxy test` shows working proxies
- [ `/verify` shows some LIVE accounts
- [ `/camp start` with small zip works
- [ ] No TypeError in reverify_loop logs

---

## 🎯 SUCCESS CRITERIA

Bot is properly configured when:
1. ✅ Starts without `CRITICAL: BEARER_TOKEN env var not set`
2. ✅ Shows `proxy=ON` (not OFF direct)
3. ✅ `/proxy test` shows at least 1 working proxy
4. ✅ `/verify` shows mix of LIVE/DEAD/KNOWN accounts
5. ✅ Campaign `/camp start` runs without crashing
6. ✅ Reverify loop runs without TypeError
7. ✅ Supabase accounts save without 400 errors

---

**Follow this guide in order, starting with Fix 1 through Fix 5. 
Each fix builds on the previous one. 
Once all are applied, the bot should function fully with proxy rotation, 
proper account verification, and campaign capabilities.**

*For any stuck points, run `/proxy test` and `/diag` commands, 
check the log output, and adjust the environment variables accordingly.*
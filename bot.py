#!/usr/bin/env python3
"""Diaz Shop — Telegram Bot + Web Server + Mini App API (all-in-one)"""

import threading
import asyncio
import os, json, time, logging, threading, secrets as _secrets
from pathlib import Path
import httpx
from aiohttp import web

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ─── Config ───────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@diazplaylist")
OWNER_ID = int(os.environ.get("OWNER_ID", "6326889425"))
SUPPORT_USERNAME = "MrArat"
CARD_NUMBER = "6219861825198608"
CARD_NAME = "امیرمحمد زارعی"

PENDING_FILE = "pending_state.json"
WALLET_FILE = "wallet.json"
CONFIGS_FILE = "user_configs.json"
REFERRALS_FILE = "referrals.json"
ACCOUNTS_FILE = "express_accounts.json"

SPIDER_URL = os.environ.get("SPIDER_URL", "https://spiderpanel-production-2268.up.railway.app")
SPIDER_PASSWORD = os.environ.get("SPIDER_PASSWORD", "admin")

# ─── BPB Panel — آنی‌سازی کانفیگ ──────────────────────────
BPB_ORIGIN = os.environ.get("BPB_ORIGIN", "").rstrip("/")
BPB_SECURE_PATH = os.environ.get("BPB_SECURE_PATH", "").strip("/")
BPB_EMAIL = os.environ.get("BPB_EMAIL", "")
BPB_PASSWORD = os.environ.get("BPB_PASSWORD", "")

def bpb_ready():
    return bool(BPB_ORIGIN and BPB_SECURE_PATH and BPB_EMAIL and BPB_PASSWORD)

async def bpb_create_user(name: str, limit_gb: int, days: int) -> dict:
    """ساخت کاربر روی پنل BPB + برگرداندن لینک ساب و صفحه وضعیت"""
    if not bpb_ready():
        raise RuntimeError("BPB env not set")
    import base64 as _b64
    base = f"{BPB_ORIGIN}/{BPB_SECURE_PATH}"
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(f"{base}/login/authenticate",
                         json={"username": BPB_EMAIL.lower(), "password": BPB_PASSWORD})
        try:
            if not r.json().get("success"):
                raise RuntimeError(f"panel login failed: {r.text[:120]}")
        except ValueError:
            raise RuntimeError(f"panel login non-json: {r.status_code}")
        r = await c.post(f"{base}/panel/user/save",
                         json={"name": name, "totalGB": int(limit_gb), "days": int(days), "enabled": True})
        if not r.json().get("success"):
            raise RuntimeError(f"panel save failed: {r.text[:120]}")
        r = await c.get(f"{base}/panel/users")
        users = r.json()["body"]["users"]
        u = next(x for x in reversed(users) if x.get("name") == name)
        sub_link = f"{base}/sub/u/{u['subToken']}"
        page_link = f"{base}/user/{u['uuid']}"
        try:
            raw = _b64.b64decode((await c.get(sub_link)).text).decode()
        except Exception:
            raw = ""
        return {"sub": sub_link, "page": page_link, "configs": raw.strip()}

CONFIG_PLANS = {
    "10gb": {"name": "۱۰ گیگ", "price": "۱۲,۰۰۰", "data": "10GB", "duration": "۱ ماه", "price_int": 12000, "limit_gb": 10, "days": 30},
    "20gb": {"name": "۲۰ گیگ", "price": "۳۰,۰۰۰", "data": "20GB", "duration": "۱ ماه", "price_int": 30000, "limit_gb": 20, "days": 30},
    "50gb": {"name": "۵۰ گیگ", "price": "۷۰,۰۰۰", "data": "50GB", "duration": "۱ ماه", "price_int": 70000, "limit_gb": 50, "days": 30},
    "80gb": {"name": "۸۰ گیگ", "price": "۱۱۰,۰۰۰", "data": "80GB", "duration": "۱ ماه", "price_int": 110000, "limit_gb": 80, "days": 30},
}

EXPRESS_PLANS = {
    "1m": {"name": "۱ ماهه", "price": "۲۲۰,۰۰۰", "price_int": 220000, "days": 30},
    "3m": {"name": "۳ ماهه", "price": "۳۳۰,۰۰۰", "price_int": 330000, "days": 90},
    "6m": {"name": "۶ ماهه", "price": "۴۹۰,۰۰۰", "price_int": 490000, "days": 180},
    "1y": {"name": "۱ ساله", "price": "۹۵۰,۰۰۰", "price_int": 950000, "days": 365},
}

DEEZER_PLANS = {
    "family": {"name": "فمیلی یک‌ماهه", "price": "۱۵۰,۰۰۰", "price_int": 150000},
    "personal": {"name": "شخصی یک‌ماهه", "price": "۲۲۰,۰۰۰", "price_int": 220000},
}

AI_PLANS = {
    "gemini18": {"name": "جمنای یک‌ماهه", "price": "۵۰۰,۰۰۰", "price_int": 500000, "days": 30},
    "claudepro": {"name": "Claude Pro یک‌ماهه", "price": "۶,۵۰۰,۰۰۰", "price_int": 6500000, "days": 30},
    "gpt_go": {"name": "ChatGPT Go یک‌ماهه", "price": "۲,۵۵۰,۰۰۰", "price_int": 2550000, "days": 30},
    "gpt_plus": {"name": "ChatGPT پلاس آماده یک‌ماهه", "price": "۴,۷۰۰,۰۰۰", "price_int": 4700000, "days": 30},
}

SPOTIFY_PLANS = {
    "spotify1m": {"name": "Spotify اختصاصی یک‌ماهه (نامحدود)", "price": "۱,۵۰۰,۰۰۰", "price_int": 1500000, "days": 30},
}

REFERRAL_TARGET = 1

async def context_broad_config(uid, info, plan, name):
    """ارسال پیام کانفیگ به کاربر از مسیر مینی‌اپ (بدون دسترسی به bot object)"""
    import urllib.request, urllib.parse
    token = BOT_TOKEN
    text = (f"✅ **کانفیگ شما آماده شد!** 🎉\n\n"
            f"📦 پلن: **{plan.get('name', '')}**\n📝 اسم: `{name}`\n\n"
            f"🔗 **لینک ساب:**\n`{info['sub']}`\n\n"
            f"وضعیت سرویس رو از مینی‌اپ می‌تونی ببینی 👤")
    payload = json.dumps({"chat_id": int(uid), "text": text, "parse_mode": "Markdown"}, ensure_ascii=False)
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=payload.encode(), headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        logger.error(f"broad config msg failed: {e}")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── File Helpers ─────────────────────────────────────────
# ─── Durable storage: Cloudflare KV (state survives Railway deploys) ─────
# Local files stay the fast sync store; every change is mirrored into KV via the
# panel worker (GET/POST /<securePath>/bot/<bot_key>, password in x-bot-key).
# KV wins on boot, so a fresh deploy restores wallets/orders/configs/etc.
BPB_ORIGIN = os.environ.get("BPB_ORIGIN", "").rstrip("/")
BPB_SECURE_PATH = os.environ.get("BPB_SECURE_PATH", "").strip("/")
BPB_PASSWORD = os.environ.get("BPB_PASSWORD", "")
_KV_PREFIX = "bot_"
_KV_STATE = {}        # kv key -> {"ts": float, "data": obj}
_KV_DIRTY = set()     # kv keys waiting to be pushed
_KV_UNKNOWN = set()   # keys whose boot read failed — empty pushes blocked
_KV_ENABLED = bool(BPB_ORIGIN and BPB_SECURE_PATH and BPB_PASSWORD)
_KV_UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36"

def _kv_files():
    return [PENDING_FILE, WALLET_FILE, CONFIGS_FILE, REFERRALS_FILE,
            ACCOUNTS_FILE, ORDERS_FILE, DISCOUNTS_FILE,
            PLAN_OVERRIDES_FILE, RECEIPTS_FILE]

def _kv_key(fn):
    return _KV_PREFIX + Path(str(fn)).name.replace(".json", "").replace("-", "_").lower()

def _kv_url(key):
    return f"{BPB_ORIGIN}/{BPB_SECURE_PATH}/bot/{key}"

def _kv_headers():
    return {"x-bot-key": BPB_PASSWORD, "User-Agent": _KV_UA,
            "Content-Type": "application/json"}

def _write_file(fn, d):
    try:
        with open(fn, "w") as f: json.dump(d, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.warning(f"local state write failed ({fn}): {e}")
        return False

def _load(fn):
    key = _kv_key(fn)
    env = _KV_STATE.get(key)
    if env is not None:
        try:
            return json.loads(json.dumps(env["data"], ensure_ascii=False))
        except Exception:
            pass
    try:
        if os.path.exists(fn):
            with open(fn) as f: return json.load(f)
    except: pass
    return {}

def _save(fn, d):
    _write_file(fn, d)
    if not _KV_ENABLED:
        return
    try:
        snap = json.loads(json.dumps(d, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"KV snapshot skipped ({fn}): {e}")
        return
    key = _kv_key(fn)
    _KV_STATE[key] = {"ts": time.time(), "data": snap}
    _KV_DIRTY.add(key)

def kv_boot():
    """Pull every state key from KV — KV wins over the (wiped) local files."""
    if not _KV_ENABLED:
        logger.warning("KV sync OFF: BPB_ORIGIN / BPB_SECURE_PATH / BPB_PASSWORD missing")
        return
    for fn in _kv_files():
        key = _kv_key(fn)
        try:
            r = httpx.get(_kv_url(key), headers=_kv_headers(), timeout=25)
        except Exception as e:
            _KV_UNKNOWN.add(key)
            logger.warning(f"KV boot read {key} failed: {e}")
            continue
        if r.status_code != 200:
            _KV_UNKNOWN.discard(key)      # 404 = key confirmed empty
            # nothing in KV yet (first run) — push whatever the local file has
            if os.path.exists(fn):
                try:
                    with open(fn) as f: local = json.load(f)
                except Exception:
                    local = None
                if isinstance(local, (dict, list)):
                    _KV_STATE[key] = {"ts": time.time(), "data": local}
                    _KV_DIRTY.add(key)
            continue
        try:
            body = r.json()
        except Exception:
            body = None
        # worker responds as {success,status,message,body}; body holds the envelope
        env = body.get("body") if isinstance(body, dict) and isinstance(body.get("body"), (dict, list)) else body
        data = env.get("data") if isinstance(env, dict) else None
        ts = env.get("ts") if isinstance(env, dict) else None
        if not isinstance(data, (dict, list)):
            _KV_UNKNOWN.add(key)          # unreadable — never let an empty push clobber it
            logger.warning(f"KV boot {key}: unexpected payload shape")
            continue
        _KV_UNKNOWN.discard(key)
        _KV_STATE[key] = {"ts": ts or time.time(), "data": data}
        _write_file(fn, data)
    logger.info(f"KV boot done (enabled={_KV_ENABLED}, keys={len(_KV_STATE)}, pending={len(_KV_DIRTY)})")

async def _kv_push_loop():
    """Flush dirty state keys to KV every few seconds (the bot is the only writer)."""
    async with httpx.AsyncClient() as cli:
        while True:
            try:
                while _KV_DIRTY:
                    key = next(iter(_KV_DIRTY))
                    envd = _KV_STATE.get(key)
                    if envd is None:
                        _KV_DIRTY.discard(key)
                        continue
                    try:
                        payload = json.loads(json.dumps(envd, ensure_ascii=False))
                    except Exception:
                        _KV_DIRTY.discard(key)
                        continue
                    if key in _KV_UNKNOWN and not payload.get("data"):
                        logger.warning(f"KV push {key} blocked: boot read failed, refusing to overwrite with empty state")
                        _KV_DIRTY.discard(key)
                        continue
                    try:
                        r = await cli.post(_kv_url(key), headers=_kv_headers(),
                                           json=payload, timeout=25)
                    except Exception as e:
                        logger.warning(f"KV push {key} failed: {e}")
                        break
                    if r.status_code == 200:
                        _KV_DIRTY.discard(key)
                    else:
                        logger.warning(f"KV push {key} -> HTTP {r.status_code}")
                        break
            except Exception as e:
                logger.warning(f"KV push loop: {e}")
            await asyncio.sleep(5)

def load_pending(): return _load(PENDING_FILE)
def save_pending(d): _save(PENDING_FILE, d)
def load_configs(): return _load(CONFIGS_FILE)
def save_configs(d): _save(CONFIGS_FILE, d)
ORDERS_FILE = Path(__file__).parent / "orders.json"
def load_orders(): return _load(ORDERS_FILE)
def save_orders(d): _save(ORDERS_FILE, d)
def _plan_days(kind, key):
    if kind == "express": return EXPRESS_PLANS.get(key, {}).get("days", 30)
    if kind == "ai": return AI_PLANS.get(key, {}).get("days", 30)
    if kind == "music": return SPOTIFY_PLANS.get(key, {}).get("days", 30)
    return 30
def add_order(uid, kind, plan_key, plan_name, price):
    o = load_orders(); lst = o.setdefault(str(uid), [])
    lst.append({"id": int(time.time()), "kind": kind, "plan": plan_key, "name": plan_name, "price": price, "status": "pending", "ts": int(time.time())})
    save_orders(o)
def mark_order_sent(uid, link=""):
    o = load_orders(); lst = o.get(str(uid), [])
    for it in reversed(lst):
        if it.get("status") == "pending":
            it["status"] = "sent"; it["delivered_ts"] = int(time.time())
            it["days"] = _plan_days(it.get("kind", ""), it.get("plan", ""))
            if link: it["link"] = link[:300]
            break
    save_orders(o)
def load_wallet(): return _load(WALLET_FILE)
def save_wallet(d): _save(WALLET_FILE, d)
def load_referrals(): return _load(REFERRALS_FILE)
def save_referrals(d): _save(REFERRALS_FILE, d)
def load_accounts():
    d = _load(ACCOUNTS_FILE)
    return d if isinstance(d, list) else []
def save_accounts(d): _save(ACCOUNTS_FILE, d)

# ─── Business Logic ──────────────────────────────────────
def get_balance(uid):
    return load_wallet().get(str(uid), {}).get("balance", 0)

def add_balance(uid, amount):
    w = load_wallet(); k = str(uid)
    if k not in w: w[k] = {"balance": 0, "history": []}
    w[k]["balance"] += amount
    w[k]["history"].append({"amount": amount, "type": "charge", "ts": time.time()})
    save_wallet(w)

def spend_balance(uid, amount):
    w = load_wallet(); k = str(uid)
    if k not in w or w[k]["balance"] < amount: return False
    w[k]["balance"] -= amount
    w[k]["history"].append({"amount": -amount, "type": "spend", "ts": time.time()})
    save_wallet(w)
    return True

def get_referral_count(inv):
    return len(load_referrals().get(str(inv), {}).get("invited", []))

def add_referral(inv, uid):
    refs = load_referrals(); k = str(inv)
    if k not in refs: refs[k] = {"invited": [], "free_given": False}
    if uid not in refs[k]["invited"]:
        refs[k]["invited"].append(uid); save_referrals(refs); return True
    return False

def has_free_sub(uid): return load_referrals().get(str(uid), {}).get("free_given", False)
def mark_free_given(uid):
    refs = load_referrals(); k = str(uid)
    if k in refs: refs[k]["free_given"] = True; save_referrals(refs)

def get_next_account():
    accs = load_accounts()
    for a in accs:
        if a.get("used_count", 0) < a.get("max_uses", 3):
            a["used_count"] = a.get("used_count", 0) + 1; save_accounts(accs); return a
    return None

# ─── SpiderPanel API Client ──────────────────────────────
class SpiderPanel:
    def __init__(self, base_url, password):
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.session_token = None
        self.client = httpx.AsyncClient(timeout=30, verify=False)

    async def _ensure_auth(self):
        if not self.session_token: await self.login()

    async def login(self):
        for pw in [self.password, "admin"]:
            try:
                r = await self.client.post(f"{self.base_url}/api/login", json={"password": pw})
                if r.status_code == 200:
                    for cookie in r.cookies.jar:
                        if cookie.name == "spider_session":
                            self.session_token = cookie.value; return True
                    cookies = dict(r.cookies)
                    if cookies:
                        self.session_token = list(cookies.values())[0]; return True
            except Exception as e:
                logger.error(f"SpiderPanel login error ({pw}): {e}")
        return False

    def _cookies(self):
        return {"spider_session": self.session_token} if self.session_token else {}

    async def _req(self, method, url, **kw):
        await self._ensure_auth()
        func = getattr(self.client, method)
        r = await func(url, cookies=self._cookies(), **kw)
        if r.status_code == 401:
            self.session_token = None; await self.login()
            r = await func(url, cookies=self._cookies(), **kw)
        return r

    async def create_user(self, username, limit_gb=0, days=30):
        body = {"username": username, "traffic_limit_gb": limit_gb, "expire_days": days,
                "protocol": "vless", "concurrent_connections": 1,
                "inbound_ids": ["default-reverse", "default"]}
        r = await self._req("post", f"{self.base_url}/api/users", json=body)
        if r.status_code == 409:
            body["username"] = f"{username}-{_secrets.token_hex(2)}"
            r = await self._req("post", f"{self.base_url}/api/users", json=body)
        if r.status_code == 200:
            data = r.json()
            uid = data.get("user_id", "")
            config = data.get("config", "")
            if not config and uid:
                try:
                    cr = await self._req("get", f"{self.base_url}/api/users/{uid}/config")
                    if cr.status_code == 200: config = cr.json().get("config", "")
                except: pass
            return {"user_id": uid, "username": data.get("username"), "config": config,
                    "expire_at": data.get("expire_at", "")}
        return None

    async def close(self): await self.client.aclose()

spider = SpiderPanel(SPIDER_URL, SPIDER_PASSWORD)

# ─── Telegram Bot Handlers ───────────────────────────────
WELCOME_TEXT = (
    "🎮 به ربات اختصاصی Diaz Shop خوش آمدید 🚀!\n\n"
    " محصولات ما زیر قیمت و تضمینی هستند! ✅\n\n"
    "━━━━━━━━━━━━━━━━━\n"
    f" پشتیبانی: @{SUPPORT_USERNAME}"
)

def main_menu_kb(uid=0):
    import time as _ts; _t = int(_ts.time()); shop_url = f"https://worker-production-e8dd.up.railway.app/?uid={uid}&t={_t}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕷️ فروشگاه", web_app=WebAppInfo(url=shop_url))],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet_menu")],
        [InlineKeyboardButton("🎁 اشتراک رایگان", callback_data="free_sub")],
        [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

async def _process_referral(context, inviter_id, invited_id):
    added = add_referral(inviter_id, invited_id)
    count = get_referral_count(inviter_id)
    if added and count >= REFERRAL_TARGET and not has_free_sub(inviter_id):
        mark_free_given(inviter_id)
        try:
            await context.bot.send_message(chat_id=inviter_id,
                text="🎉 <b>تبریک!</b>\n\nشما یک نفر رو دعوت کردید!\n\nروی دکمه زیر کلیک کنید 👇",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 دریافت", callback_data="claim_free_sub")]]),
                parse_mode="HTML")
        except: pass

async def start(update, context):
    user = update.effective_user
    if context.args:
        payload = context.args[0]
        if payload.startswith("ref"):
            try:
                inviter_id = int(payload[3:])
                if inviter_id != user.id:
                    context.user_data["pending_ref"] = inviter_id
                    await _process_referral(context, inviter_id, user.id)
            except: pass
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user.id)
        is_m = member.status in ["member", "administrator", "creator"]
        logger.info(f"Channel check for {user.id}: status={member.status}, is_m={is_m}")
    except Exception as e:
        is_m = False
        logger.error(f"Channel check failed for {user.id}: {e}")
    if not is_m:
        kb = [
            [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_member")]
        ]
        if update.message:
            await update.message.reply_text("⚠️ برای استفاده از ربات ابتدا باید در کانال عضو شوید!", reply_markup=InlineKeyboardMarkup(kb))
        return
    if update.message:
        await update.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_kb(uid=user.id))

async def check_member(update, context):
    q = update.callback_query; await q.answer()
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, q.from_user.id)
        is_m = member.status in ["member", "administrator", "creator"]
    except: is_m = False
    if not is_m:
        await q.edit_message_text("❌ هنوز عضو کانال نشدید!"); return
    pr = context.user_data.pop("pending_ref", None)
    if pr: await _process_referral(context, pr, q.from_user.id)
    await q.message.delete()
    await q.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_kb(uid=q.from_user.id))

async def sub_status(update, context):
    """نمایش زنده حجم/انقضای اشتراک مشتری داخل ربات (بدون لینک صفحه)"""
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    cfgs = load_configs().get(uid, []) or load_configs().get(int(uid), [])
    links = []
    for c in cfgs:
        lk = c.get("link") or ""
        if "/sub/u/" in lk:
            links.append((c.get("data") or "اشتراک", lk.split("?")[0].rstrip("/").split("/")[-1]))
    if not links:
        await q.edit_message_text(
            "📭 هنوز اشتراکی ثبت نکردی.\n\nاز فروشگاه کانفیگ بگیر، بعد همین‌جا حجم و انقضاش رو ببین.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]))
        return
    base = f"{BPB_ORIGIN}/{BPB_SECURE_PATH}"
    out = ["📊 **وضعیت اشتراک شما**"]
    async with httpx.AsyncClient(timeout=20) as hc:
        for title, token in links[-3:]:
            try:
                r = await hc.get(f"{base}/user/{token}")
                if r.status_code != 200:
                    out.append(f"\n🔹 {title}\n⚠️ خطا در دریافت وضعیت ({r.status_code})")
                    continue
                import re as _re
                html = r.text
                bm = _re.search(r'class="badge">(.*?)</span>', html)
                badge = bm.group(1) if bm else "—"
                rows = _re.findall(r'<div class="row"><span>(.*?)</span><b>(.*?)</b></div>', html)
                out.append(f"\n🔹 **{title}** — {badge}")
                for k, v in rows:
                    out.append(f"• {k}: {v}")
            except Exception as e:
                out.append(f"\n🔹 {title}\n⚠️ {e}")
    kb = [[InlineKeyboardButton("🔄 بروزرسانی", callback_data="sub_status")],
          [InlineKeyboardButton("🏠 بازگشت", callback_data="back_main")]]
    try:
        await q.edit_message_text("\n".join(out), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except Exception:
        await q.edit_message_text("⚠️ خطا، دوباره بزن.", reply_markup=InlineKeyboardMarkup(kb))

async def back_main(update, context):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu_kb(uid=q.from_user.id))

async def free_sub_menu(update, context):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; count = get_referral_count(uid); done = has_free_sub(uid)
    if done: text = "🎁 <b>اشتراک رایگان</b>\n\nشما قبلاً دریافت کرده‌اید! ✅"
    elif count >= REFERRAL_TARGET: text = f"🎉 <b>تبریک!</b>\n\nشما {count} نفر را دعوت کرده‌اید!"
    else:
        un = context.bot.username
        text = (f"🎁 <b>اشتراک رایگان</b>\n\nبا دعوت یک نفر، اشتراک رایگان بگیرید!\n\n"
                f"📊 تعداد دعوت‌شده: <b>{count}/{REFERRAL_TARGET}</b>\n"
                f"🔗 لینک دعوت:\n<code>https://t.me/{un}?start=ref{uid}</code>")
    kb = []
    if count >= REFERRAL_TARGET and not done: kb.append([InlineKeyboardButton("🎁 دریافت", callback_data="claim_free_sub")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def claim_free_sub(update, context):
    q = update.callback_query; await q.answer(); uid = q.from_user.id
    if get_referral_count(uid) < REFERRAL_TARGET:
        await q.edit_message_text(f"❌ هنوز {REFERRAL_TARGET - get_referral_count(uid)} نفر لازم دارید."); return
    account = get_next_account()
    if not account:
        await q.edit_message_text("❌ اشتراک رایگان تمام شده!"); return
    await q.edit_message_text(
        f"🎉 <b>اشتراک رایگان فعال شد!</b>\n\n📧 <code>{account['email']}</code>\n🔑 <code>{account['password']}</code>\n\n⏰ {account['days_left']} روز",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 بازگشت", callback_data="back_main")]]), parse_mode="HTML")
    mark_free_given(uid)

async def wallet_menu(update, context):
    q = update.callback_query; await q.answer(); bal = get_balance(q.from_user.id)
    kb = [[InlineKeyboardButton("💳 افزایش موجودی", callback_data="charge_wallet")],
          [InlineKeyboardButton("📊 تاریخچه", callback_data="wallet_history")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"💰 **کیف پول:** {bal:,} تومان", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def charge_wallet(update, context):
    q = update.callback_query; await q.answer()
    kb = [[InlineKeyboardButton(f"{n:,} تومان", callback_data=f"charge_{n}")] for n in [50000,100000,200000,500000]]
    kb.append([InlineKeyboardButton("📝 مبلغ دلخواه", callback_data="charge_custom")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")])
    await q.edit_message_text("💳 **افزایش موجودی**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def charge_amount(update, context):
    q = update.callback_query; await q.answer()
    amount = int(q.data.replace("charge_", ""))
    kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"charge_receipt_{amount}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text(f"💳 **{amount:,} تومان**\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def charge_custom(update, context):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "type": "charge_custom"}; save_pending(p)
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text("📝 **مبلغ دلخواه (فقط عدد):**", reply_markup=InlineKeyboardMarkup(kb))

async def charge_receipt_step(update, context):
    q = update.callback_query; await q.answer()
    amount = int(q.data.replace("charge_receipt_", ""))
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "type": "charge", "amount": amount}; save_pending(p)
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text(f"📸 **رسید ({amount:,} تومان) رو بفرستید:**", reply_markup=InlineKeyboardMarkup(kb))

async def wallet_history(update, context):
    q = update.callback_query; await q.answer()
    w = load_wallet().get(str(q.from_user.id), {}); hist = w.get("history", []); bal = w.get("balance", 0)
    text = "📊 **تاریخچه:**\n\n"
    if not hist: text += "خالی"
    else:
        for h in hist[-10:]:
            sign = "+" if h["amount"] > 0 else ""
            text += f"{'💳' if h['type'] == 'charge' else '📦'} {sign}{h['amount']:,}\n"
    text += f"\n💰 موجودی: {bal:,}"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]), parse_mode="Markdown")

async def buy_config(update, context):
    q = update.callback_query; await q.answer()
    kb = [[InlineKeyboardButton(f"📦 {v['name']} — {v['price']}", callback_data=f"config_{k}")] for k,v in CONFIG_PLANS.items()]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await q.edit_message_text("📦 **انتخاب پلن:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def select_config(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("config_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    uid = q.from_user.id; bal = get_balance(uid)
    kb = []
    if bal >= plan["price_int"]: kb.append([InlineKeyboardButton(f"💰 کیف پول ({plan['price']})", callback_data=f"pay_wallet_config_{pid}")])
    kb.append([InlineKeyboardButton("💳 کارت", callback_data=f"pay_config_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="buy_config")])
    await q.edit_message_text(f"📦 **{plan['name']}** — {plan['price']} تومان\n💰 موجودی: {bal:,}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def pay_config(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_config_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_{pid}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"💳 **{plan['price']} تومان**\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def receipt_received(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("receipt_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "plan": pid, "type": "config"}; save_pending(p)
    await q.edit_message_text("📸 **رسید رو بفرستید:**")

async def pay_wallet_config(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_wallet_config_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    uid = q.from_user.id
    if not spend_balance(uid, plan["price_int"]):
        await q.edit_message_text("❌ موجودی کافی نیست!"); return
    p = load_pending(); p[str(uid)] = {"waiting": True, "type": "config_wallet_name", "plan": pid, "plan_data": plan}; save_pending(p)
    await q.edit_message_text(f"✅ **{plan['price']} تومان کسر شد!**\n\n📝 **اسمتون رو بفرستید:**")

async def buy_express(update, context):
    q = update.callback_query; await q.answer()
    kb = [[InlineKeyboardButton(f"⏰ {v['name']} — {v['price']}", callback_data=f"express_{k}")] for k,v in EXPRESS_PLANS.items()]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await q.edit_message_text("🔐 **ExpressVPN**\n\n• Killswitch\n• ۳۰۰ سرور از ۱۰۰ کشور\n• مناسب گیمینگ\n\n**انتخاب پلن:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def select_express(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("express_", ""); plan = EXPRESS_PLANS.get(pid)
    if not plan: return
    uid = q.from_user.id; bal = get_balance(uid)
    kb = []
    if bal >= plan["price_int"]: kb.append([InlineKeyboardButton(f"💰 کیف پول ({plan['price']})", callback_data=f"pay_wallet_express_{pid}")])
    kb.append([InlineKeyboardButton("💳 کارت", callback_data=f"pay_express_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="buy_express")])
    await q.edit_message_text(f"🔐 **{plan['name']}** — {plan['price']} تومان\n💰 موجودی: {bal:,}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def pay_express(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_express_", ""); plan = EXPRESS_PLANS.get(pid)
    if not plan: return
    kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_express_{pid}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"💳 **{plan['price']} تومان**\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def receipt_express_received(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("receipt_express_", ""); plan = EXPRESS_PLANS.get(pid)
    if not plan: return
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "plan": pid, "type": "express"}; save_pending(p)
    await q.edit_message_text("📸 **رسید رو بفرستید:**")

async def pay_wallet_express(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_wallet_express_", ""); plan = EXPRESS_PLANS.get(pid)
    if not plan: return
    uid = q.from_user.id
    if not spend_balance(uid, plan["price_int"]):
        await q.edit_message_text("❌ موجودی کافی نیست!"); return
    # Notify admin
    kb = [[InlineKeyboardButton("✅ تایید و ارسال", callback_data=f"approve_express_{uid}_{pid}")],
          [InlineKeyboardButton("❌ رد", callback_data=f"reject_{uid}")]]
    try:
        await context.bot.send_message(chat_id=OWNER_ID,
            text=f"💰 **خرید ExpressVPN از کیف پول!**\n\n👤 {q.from_user.first_name} (@{q.from_user.username or ''})\n🆔 {uid}\n📦 {plan['name']}\n💰 {plan['price']} تومان\n\nلطفاً اشتراک رو بفرستید.",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except: pass
    kb2 = [[InlineKeyboardButton("🏠 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"✅ **پرداخت موفق!** {plan['price']} تومان کسر شد.\n\n⏳ سفارش شما ثبت شد. به زودی اشتراک به پنل کاربری شما اضافه می‌شود!", reply_markup=InlineKeyboardMarkup(kb2), parse_mode="Markdown")

async def user_panel(update, context):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id); bal = get_balance(int(uid)); configs = load_configs().get(uid, [])
    text = f"👤 **پنل کاربری**\n\n💰 کیف پول: {bal:,} تومان\n\n"
    if not configs: text += "📦 هیچ اشتراکی ندارید."
    else:
        for i, c in enumerate(configs, 1):
            text += f"**{i}.** {c.get('type','')} - {c.get('data','')}\n"
            if c.get("link"): text += f"   🔗 `{c['link']}`\n"
    kb = [[InlineKeyboardButton("🔄 بروزرسانی", callback_data="user_panel")],
          [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ─── Receipt & Text Handlers ─────────────────────────────
async def handle_photo(update, context):
    uid = str(update.effective_user.id); p = load_pending(); state = p.get(uid)
    if not state or not state.get("waiting"): return
    user = update.effective_user; ptype = state["type"]
    if ptype == "charge":
        amount = state.get("amount", 0); del p[uid]; save_pending(p)
        caption = f"💰 **رسید شارژ**\n\n👤 {user.first_name} (@{user.username or 'ندارد'})\n🆔 {uid}\n💰 {amount:,} تومان"
        try:
            _rs = load_receipts()
            _rs[f"{int(time.time())}_{uid}"] = {"uid": uid, "ptype": ptype, "amount": amount,
                                                "plan": "", "price": 0, "ts": int(time.time()), "status": "waiting"}
            save_receipts(_rs)
        except Exception as e:
            logger.warning(f"receipt save failed: {e}")
        kb = [[InlineKeyboardButton("✅ تایید", callback_data=f"approve_charge_{user.id}_{amount}"),
               InlineKeyboardButton("❌ رد", callback_data=f"reject_{user.id}")]]
        try: await context.bot.send_photo(chat_id=OWNER_ID, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        except: pass
        await update.message.reply_text("✅ رسید دریافت شد!"); return
    if ptype == "charge_custom": del p[uid]; save_pending(p); await update.message.reply_text("❌ ابتدا مبلغ رو عددی تایپ کنید."); return
    plan_id = state.get("plan")
    plan = CONFIG_PLANS.get(plan_id) if "config" in ptype else EXPRESS_PLANS.get(plan_id)
    if not plan: return
    del p[uid]; save_pending(p)
    caption = f"📸 **رسید**\n\n👤 {user.first_name} (@{user.username or 'ندارد'})\n🆔 {uid}\n📦 {plan['name']}\n💰 {plan['price']} تومان"
    try:
        _rs = load_receipts()
        _rs[f"{int(time.time())}_{uid}"] = {"uid": uid, "ptype": ptype, "amount": 0, "plan": plan_id,
                                            "price": plan.get("price_int", 0), "ts": int(time.time()), "status": "waiting"}
        save_receipts(_rs)
    except Exception as e:
        logger.warning(f"receipt save failed: {e}")
    kb = [[InlineKeyboardButton("✅ تایید", callback_data=f"approve_{ptype}_{user.id}_{plan_id}"),
           InlineKeyboardButton("❌ رد", callback_data=f"reject_{user.id}")]]
    try: await context.bot.send_photo(chat_id=OWNER_ID, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except: pass
    await update.message.reply_text("✅ رسید دریافت شد!")

async def handle_text(update, context):
    uid = str(update.effective_user.id); p = load_pending(); state = p.get(uid)
    # Admin sending subscription/config link — check FIRST
    if state and state.get("waiting_admin"):
        admin_type = state["type"]; target_user = state["user_id"]
        link = update.message.text.strip()
        del p[uid]; save_pending(p)
        configs = load_configs(); k = str(target_user)
        if k not in configs: configs[k] = []
        configs[k].append({"type": admin_type, "data": state.get("plan", ""), "link": link[:300]})
        save_configs(configs)
        try: mark_order_sent(str(target_user), link)
        except Exception: pass
        await update.message.reply_text(f"✅ اشتراک/ظرفیت برای کاربر {target_user} ارسال شد!")
        try:
            label = admin_type.replace("send_gta", "🎮 GTA VI — Ultimate Edition").replace("send_express", "⚡ ExpressVPN").replace("send_config", "📦 کانفیگ VPN").replace("send_deezer", "🎵 Deezer").replace("send_spotify", "🎧 Spotify").replace("send_ai", "🤖 هوش مصنوعی")
            await context.bot.send_message(chat_id=target_user,
                text=f"✅ **سفارش شما تأیید شد!**\n\n📦 **نوع:** {label}\n\n🔑 **اطلاعات:**\n`{link[:500]}`\n\nاز پنل کاربری قابل مشاهده است.",
                parse_mode="Markdown")
        except: pass
        return
    if not state or not state.get("waiting"): return
    if state["type"] == "charge_custom":
        try: amount = int(update.message.text.strip())
        except: await update.message.reply_text("❌ فقط عدد."); return
        del p[uid]; save_pending(p)
        kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"charge_receipt_{amount}")]]
        await update.message.reply_text(f"💳 واریز {amount:,} تومان\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return
    if state["type"] in ("config_wallet_name", "config_receipt_name"):
        name = update.message.text.strip()[:60]; plan = state.get("plan_data", {})
        del p[uid]; save_pending(p)
        try: add_order(uid, "config", state.get("plan", ""), plan.get("name", ""), plan.get("price_int", 0))
        except Exception: pass
        info = None
        try:
            info = await bpb_create_user(name, int(plan.get("limit_gb", 1)), int(plan.get("days", 30)))
        except Exception as e:
            logger.error(f"auto config failed: {e}")
        if not info:
            # fallback: ادمین دستی لینک رو میفرسته (روی قبلی)
            try:
                await context.bot.send_message(chat_id=OWNER_ID,
                    text=f"📝 **کانفیگ دستی!** (اتوماسیون در دسترس نیست)\n\n👤 {update.effective_user.first_name}\n🆔 {uid}\n📝 اسم: {name}\n📦 پلن: {plan.get('name', '')}\n\nلطفاً لینک کانفیگ رو بفرستید.",
                    parse_mode="Markdown")
            except: pass
            pending2 = load_pending()
            pending2[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_config", "user_id": uid, "plan": plan.get("name", "")}
            save_pending(pending2)
            await update.message.reply_text("✅ **سفارش شما ثبت شد!**\n\n⏳ به زودی اشتراک به پنل کاربری شما اضافه می‌شود.", parse_mode="Markdown")
            return
        configs = load_configs()
        if uid not in configs: configs[uid] = []
        configs[uid].append({"type": "کانفیگ", "data": f"{plan.get('name', '')} — {name}", "link": info["sub"][:300]})
        save_configs(configs)
        try: mark_order_sent(uid, info["sub"])
        except Exception: pass
        text = (f"✅ **کانفیگ شما آماده شد!** 🎉\n\n"
                f"📦 پلن: **{plan.get('name', '')}** — {plan.get('duration', '')}\n"
                f"📝 اسم: `{name}`\n\n"
                f"🔗 **لینک ساب:**\n`{info['sub']}`\n\n"
                f"کانفیگ‌ها با اسم **Diaz-{name}-۱/۲/۳** توی اپ میفتن — کافیه لینک ساب رو توی v2rayNG یا Hiddify کپی کنی.\n"
                f"وضعیت سرویس رو از مینی‌اپ می‌تونی ببینی 👤")
        kb = [[InlineKeyboardButton("👤 پنل کاربری", callback_data="user_panel")],
              [InlineKeyboardButton("🏠 بازگشت", callback_data="back_main")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        if info.get("configs"):
            try:
                import io as _io
                await context.bot.send_document(chat_id=int(uid),
                    document=_io.BytesIO(info["configs"].encode()),
                    filename=f"Diaz-{name}.txt",
                    caption="📄 کانفیگ‌ها برای ایمپورت دستی")
            except Exception as e:
                logger.error(f"send config file failed: {e}")
        try:
            await context.bot.send_message(chat_id=OWNER_ID,
                text=f"📦 **کانفیگ خودکار صادر شد ✅**\n\n👤 {update.effective_user.first_name}\n🆔 {uid}\n📝 اسم: {name}\n📦 پلن: {plan.get('name', '')}\n💰 {plan.get('price', '')} تومان",
                parse_mode="Markdown")
        except: pass
        return

# ─── Admin Approve/Reject ────────────────────────────────

async def approve_express(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); user_id = int(parts[2]); plan_id = parts[3]
    plan = EXPRESS_PLANS.get(plan_id)
    # Ask admin for the subscription link
    pending = load_pending()
    pending[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_express", "user_id": user_id, "plan": plan_id}
    try: add_order(str(user_id), "express", plan_id, plan["name"] if plan else plan_id, plan["price_int"] if plan else 0)
    except Exception: pass
    save_pending(pending)
    await q.edit_message_caption(caption=q.message.caption + "\n\n📝 **لینک اشتراک رو بفرستید:**", parse_mode="Markdown")


async def approve_config(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); user_id = int(parts[2]); plan_id = parts[3]
    plan = CONFIG_PLANS.get(plan_id)
    # پرداخت تایید شد → اسم رو از مشتری میگیریم → تحویل خودکار توی handle_text
    p = load_pending()
    p[str(user_id)] = {"waiting": True, "type": "config_receipt_name", "plan": plan_id, "plan_data": plan or {}}
    save_pending(p)
    try:
        await context.bot.send_message(chat_id=user_id,
            text="✅ **پرداخت تایید شد!**\n\n📝 **اسمی که میخوای روی کانفیگ بیاد رو بفرست:**",
            parse_mode="Markdown")
    except: pass
    await q.edit_message_caption(caption=q.message.caption + "\n\n✅ تایید شد — کانفیگ خودکار صادر می‌شود.", parse_mode="Markdown")

async def approve_receipt(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); ptype = parts[1]; user_id = int(parts[2])
    try: _receipts_resolve(user_id, ptype)
    except Exception: pass
    if ptype == "charge":
        amount = int(parts[3]); add_balance(user_id, amount)
        kb = [[InlineKeyboardButton("🏠 صفحه اصلی", callback_data="back_main")]]
        await context.bot.send_message(chat_id=user_id, text=f"✅ کیف پول {amount:,} تومان شارژ شد!", reply_markup=InlineKeyboardMarkup(kb))
        await q.edit_message_caption(caption=q.message.caption + "\n\n✅ تایید شد!", parse_mode="Markdown")
        return
    plan_id = parts[3]
    if "config" in ptype:
        p = load_pending(); p[str(user_id)] = {"waiting": True, "type": "config_receipt_name", "plan": plan_id, "plan_data": CONFIG_PLANS.get(plan_id, {})}; save_pending(p)
        await context.bot.send_message(chat_id=user_id, text="✅ **پرداخت تایید شد!**\n\n📝 **اسمتون رو بفرستید:**", parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"📝 **لینک ExpressVPN رو بفرست:**\n\n👤 {user_id}", parse_mode="Markdown")
    await q.edit_message_caption(caption=q.message.caption + "\n\n✅ تایید شد!", parse_mode="Markdown")

async def reject_receipt(update, context):
    q = update.callback_query; await q.answer()
    user_id = int(q.data.split("_")[1])
    try: _receipts_resolve(user_id)
    except Exception: pass
    await context.bot.send_message(chat_id=user_id, text="❌ رسید تایید نشد.\nبا پشتیبانی تماس بگیرید.")
    await q.edit_message_caption(caption=q.message.caption + "\n\n❌ رد شد!", parse_mode="Markdown")


def _notify_admin(text):
    """Send notification to admin via Telegram HTTP API (thread-safe)"""
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass

# ─── Web Server (serves mini app + API) ──────────────────
STATIC_DIR = Path(__file__).parent.resolve()

async def serve_index(request):
    from datetime import datetime, timezone, timedelta
    release = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone(timedelta(hours=3, minutes=30)))
    now = datetime.now(timezone.utc)
    diff = max(0, (release - now).total_seconds())
    vals = [int(diff // 86400), int((diff % 86400) // 3600), int((diff % 3600) // 60), int(diff % 60)]
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for i, label in enumerate(["روز", "ساعت", "دقیقه", "ثانیه"]):
        pos = html.find(label)
        if pos > 0:
            before = html.rfind(">00</div>", 0, pos)
            if before > 0:
                html = html[:before + 1] + str(vals[i]).zfill(2) + html[before + 3:]
    resp = web.Response(text=html, content_type="text/html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

async def serve_static(request):
    fname = request.match_info["name"]
    if not fname or ".." in fname:
        return web.Response(status=404)
    fpath = (STATIC_DIR / fname).resolve()
    if str(fpath).startswith(str(STATIC_DIR)) and fpath.is_file():
        return web.FileResponse(str(fpath))
    return web.Response(status=404)

# API handlers
def _orders_with_heal(uid):
    """سفارش‌های کانفیگ قدیمی که اتوماسیون نداشت رو تحویل‌شده حساب کن"""
    try:
        o = load_orders(); lst = o.get(str(uid), [])
        cl = load_configs().get(uid) or load_configs().get(str(uid)) or []
        healed = False
        for it in reversed(lst):
            if it.get("kind") == "config" and it.get("status") == "pending" and cl:
                it["status"] = "sent"
                it["delivered_ts"] = it.get("ts", int(time.time()))
                it["days"] = _plan_days("config", it.get("plan", ""))
                it["link"] = (cl[-1].get("link", "") or "")[:300]
                healed = True
        if healed: save_orders(o)
        return lst[-15:]
    except Exception:
        return load_orders().get(str(uid), [])[-15:]

async def api_user(request):
    uid = request.match_info["uid"]
    is_member = False
    try:
        import httpx
        async with httpx.AsyncClient() as _hc:
            _r = await _hc.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember", params={"chat_id": CHANNEL_ID, "user_id": int(uid)}, timeout=10)
            _d = _r.json()
            if _d.get("ok"):
                is_member = _d["result"]["status"] in ["member", "administrator", "creator"]
    except: pass
    return web.json_response({
        "balance": get_balance(uid),
        "referral_count": get_referral_count(int(uid)),
        "free_done": has_free_sub(int(uid)),
        "configs": load_configs().get(uid, []),
        "history": load_wallet().get(uid, {}).get("history", [])[-10:],
        "card_number": CARD_NUMBER, "card_name": CARD_NAME,
        "referral_target": REFERRAL_TARGET, "bot_username": "Diazpshopbot",
        "is_member": is_member,
        "orders": _orders_with_heal(uid),
    })

async def api_sub_status(request):
    """وضعیت زنده اشتراک‌ها (صفحه پنل) برای کارت انیمیشنی مینی‌اپ"""
    import re as _re
    data = await request.json()
    uid = str(data.get("uid", ""))
    cfgs = load_configs().get(uid, [])
    links = []
    for c in cfgs:
        lk = c.get("link") or ""
        if "/sub/u/" in lk:
            links.append((c.get("data") or "اشتراک", lk.split("?")[0].rstrip("/").split("/")[-1]))
    items = []
    if links and bpb_ready():
        base = f"{BPB_ORIGIN}/{BPB_SECURE_PATH}"
        async with httpx.AsyncClient(timeout=20) as hc:
            for title, token in links[-3:]:
                try:
                    r = await hc.get(f"{base}/user/{token}")
                    if r.status_code != 200:
                        items.append({"title": title, "badge": f"⚠️ خطا ({r.status_code})", "rows": [], "pct": None})
                        continue
                    html = r.text
                    bm = _re.search(r'class="badge">(.*?)</span>', html)
                    rows = _re.findall(r'<div class="row"><span>(.*?)</span><b>(.*?)</b></div>', html)
                    pm = _re.search(r'class="bar"><i style="width:([\d.]+)%"', html)
                    items.append({"title": title,
                                  "badge": bm.group(1) if bm else "—",
                                  "rows": [list(x) for x in rows],
                                  "pct": float(pm.group(1)) if pm else None})
                except Exception:
                    items.append({"title": title, "badge": "⚠️ خطا", "rows": [], "pct": None})
    return web.json_response({"items": items})

async def api_buy_config(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = CONFIG_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if plan.get("active") is False:
        return web.json_response({"error": "این پلن موقتاً غیرفعال است"}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method)
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        p = load_pending(); p[uid] = {"waiting": True, "type": "config_wallet_name", "plan": plan_id, "plan_data": plan}; save_pending(p)
        _notify_admin(f"📦 **سفارش کانفیگ (مینی\u200cاپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n📝 منتظر اسم کاربر...")
        return web.json_response({"ok": True, "action": "need_name"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

async def api_buy_config_name(request):
    data = await request.json()
    uid = data.get("uid"); name = data.get("name", "").strip()
    if not name: return web.json_response({"error": "name required"}, status=400)
    p = load_pending(); state = p.get(uid)
    if not state: return web.json_response({"error": "no pending order"})
    plan = state.get("plan_data", {})
    del p[uid]; save_pending(p)
    try: add_order(uid, "config", state.get("plan", ""), plan.get("name", ""), plan.get("price_int", 0))
    except Exception: pass
    info = None
    try:
        info = await bpb_create_user(name[:60], int(plan.get("limit_gb", 1)), int(plan.get("days", 30)))
    except Exception as e:
        logger.error(f"miniapp auto config failed: {e}")
    if info:
        configs = load_configs()
        if uid not in configs: configs[uid] = []
        configs[uid].append({"type": "کانفیگ", "data": f"{plan.get('name', '')} — {name}", "link": info["sub"][:300]})
        save_configs(configs)
        try: mark_order_sent(uid, info["sub"])
        except Exception: pass
        try:
            await context_broad_config(uid, info, plan, name)
        except Exception:
            pass
        _notify_admin(f"📦 **کانفیگ خودکار صادر شد (مینی\u200cاپ) ✅**\n\n👤 کاربر: {uid}\n📝 اسم: {name}\n📦 پلن: {plan.get('name', '')}")
        return web.json_response({"ok": True, "config": info["sub"], "page": info["page"],
                                  "expire_at": "", "plan": plan.get("name", "")})
    # fallback: ادمین دستی
    p2 = load_pending()
    p2[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_config", "user_id": uid, "plan": plan.get("name", "")}
    save_pending(p2)
    _notify_admin(f"📦 **کانفیگ دستی (اتوماسیون در دسترس نیست)**\n\n👤 کاربر: {uid}\n📝 اسم: {name}\n📦 پلن: {plan.get('name', '')}\n\n🔗 لینک کانفیگ رو بفرستید:")
    return web.json_response({"error": "creation failed"}, status=500)

async def api_buy_express(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = EXPRESS_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if plan.get("active") is False:
        return web.json_response({"error": "این پلن موقتاً غیرفعال است"}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method)
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_express", "user_id": uid, "plan": plan_id}
        save_pending(p)
        _notify_admin(f"⚡ **سفارش ExpressVPN (مینی\u200cاپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "express", plan_id, plan["name"], plan["price_int"])
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid"})


    # ─── API: Buy GTA VI ─────────────────
    @routes.post("/api/buy_gta")
    async def api_buy_gta(request):
        data = await request.json()
        uid = data.get("uid")
        if not uid: return web.json_response({"error": "uid required"})
        uid = str(uid)
        balance = get_balance(int(uid))
        if balance < 12000000:
            return web.json_response({"error": "موجودی کافی نیست"})
        if not spend_balance(int(uid), 12000000):
            return web.json_response({"error": "خطا در کسر موجودی"})
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_gta", "user_id": uid, "plan": "GTA VI Ultimate Edition Xbox Home"}
        save_pending(p)
        _notify_admin("🎮 **سفارش GTA VI (مینی\u200cاپ)**\n\n👤 کاربر: {}\n📦 پلن: Ultimate Edition — Xbox Home\n💰 12,000,000 تومان\n\n🔑 ظرفیت هوم رو بفرستید:".format(uid))
        return web.json_response({"ok": True, "action": "wallet_paid"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

async def api_buy_deezer(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = DEEZER_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if plan.get("active") is False:
        return web.json_response({"error": "این پلن موقتاً غیرفعال است"}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method)
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_deezer", "user_id": uid, "plan": plan["name"]}
        save_pending(p)
        _notify_admin(f"🎵 **سفارش Deezer (مینی‌اپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "deezer", plan_id, plan["name"], plan["price_int"])
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

async def api_buy_spotify(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = SPOTIFY_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if plan.get("active") is False:
        return web.json_response({"error": "این پلن موقتاً غیرفعال است"}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method)
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_spotify", "user_id": uid, "plan": plan["name"]}
        save_pending(p)
        _notify_admin(f"🎧 **سفارش Spotify (مینی‌اپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "music", plan_id, plan["name"], plan["price_int"])
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

async def api_buy_ai(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = AI_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if plan.get("active") is False:
        return web.json_response({"error": "این پلن موقتاً غیرفعال است"}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method)
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_ai", "user_id": uid, "plan": plan["name"]}
        save_pending(p)
        _notify_admin(f"🤖 **سفارش هوش مصنوعی (مینی‌اپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "ai", plan_id, plan["name"], plan["price_int"])
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

async def api_wallet_charge(request):
    data = await request.json()
    uid = data.get("uid"); amount = data.get("amount", 0)
    if amount <= 0: return web.json_response({"error": "invalid amount"}, status=400)
    p = load_pending(); p[uid] = {"waiting": True, "type": "charge", "amount": amount}; save_pending(p)
    return web.json_response({"ok": True, "card": CARD_NUMBER, "card_name": CARD_NAME, "amount": amount})

# Debug: test channel check
_bot_ref = None

async def api_debug_channel(request):
    uid = request.query.get("uid", "6326889425")
    result = {"uid": uid, "channel": CHANNEL_ID, "bot_token_prefix": BOT_TOKEN[:10]}
    try:
        import httpx
        async with httpx.AsyncClient() as hc:
            r = await hc.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
                           params={"chat_id": CHANNEL_ID, "user_id": int(uid)}, timeout=10)
            result["api_response"] = r.json()
    except Exception as e:
        result["error"] = str(e)
    return web.json_response(result)

_status_cache = {"ts": 0, "ok": False, "ms": 0}

async def api_status(request):
    if time.time() - _status_cache["ts"] > 60:
        t0 = time.time()
        try:
            async with httpx.AsyncClient() as hc:
                r = await hc.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=8)
                _status_cache["ok"] = bool(r.json().get("ok"))
        except Exception:
            _status_cache["ok"] = False
        _status_cache["ms"] = int((time.time() - t0) * 1000)
        _status_cache["ts"] = time.time()
    return web.json_response({"ok": _status_cache["ok"], "ms": _status_cache["ms"], "ts": int(time.time())})

# ─── ADMIN PANEL API (پنل مدیریت — فقط مالک) ──────────────
import hmac as _hmac, hashlib as _hashlib, asyncio as _asyncio

ADMIN_UID = int(os.environ.get("ADMIN_UID", str(OWNER_ID)))
DISCOUNTS_FILE = "discounts.json"
def load_discounts(): return _load(DISCOUNTS_FILE)
def save_discounts(d): _save(DISCOUNTS_FILE, d)

def _fa(n):
    return f"{int(n):,}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def _admin_pw():
    return os.environ.get("ADMIN_PASSWORD") or os.environ.get("BPB_PASSWORD") or ""

def _make_admin_token():
    pw = _admin_pw()
    if not pw: return ""
    per = int(time.time() // 43200)
    sig = _hmac.new(BOT_TOKEN.encode(), f"{pw}|{per}".encode(), _hashlib.sha256).hexdigest()
    return f"{per}.{sig}"

def _admin_token_ok(tok):
    pw = _admin_pw()
    if not pw or not tok or "." not in tok: return False
    try:
        per_s, sig = tok.split(".", 1); per = int(per_s)
    except Exception:
        return False
    if abs(int(time.time() // 43200) - per) > 1: return False
    exp = _hmac.new(BOT_TOKEN.encode(), f"{pw}|{per}".encode(), _hashlib.sha256).hexdigest()
    return _hmac.compare_digest(exp, sig)

def _denied(request):
    if _admin_token_ok(request.headers.get("X-Admin-Token", "")): return None
    return web.json_response({"error": "unauthorized"}, status=401)

def _apply_code(plan, code, uid=None, method="wallet"):
    """نسخه‌ تخفیف‌خوردهٔ پلن. کد نامعتبر → ValueError. مصرف کد فقط بعد از اطمینان از موجودی ثبت می‌شود."""
    code = (code or "").strip().lower()
    if not code: return plan
    ds = load_discounts(); d = ds.get(code)
    if not d or not d.get("active", True): raise ValueError("کد تخفیف معتبر نیست")
    if d.get("expires") and time.time() > float(d["expires"]): raise ValueError("کد تخفیف منقضی شده")
    if d.get("max_uses") and int(d.get("used", 0)) >= int(d["max_uses"]): raise ValueError("سقف استفاده از کد تخفیف تمام شده")
    price = int(plan["price_int"])
    off = price * int(d["value"]) // 100 if d.get("type") == "percent" else int(d["value"])
    final = max(0, price - off)
    if method == "wallet" and uid is not None and get_balance(int(uid)) < final:
        raise ValueError("موجودی کافی نیست")
    d["used"] = int(d.get("used", 0)) + 1
    ds[code] = d; save_discounts(ds)
    out = dict(plan); out["price_int"] = final; out["price"] = _fa(final); out["discount"] = code
    return out

def _all_uids():
    u = set()
    for d in (load_wallet(), load_configs(), load_orders()):
        try: u |= set(str(k) for k in d)
        except Exception: pass
    return sorted([x for x in u if str(x).isdigit()], key=int)

def _flat_orders():
    out = []
    for uid, lst in load_orders().items():
        for o in (lst or []):
            rec = dict(o); rec["uid"] = str(uid); out.append(rec)
    out.sort(key=lambda o: o.get("ts", 0), reverse=True)
    return out

def _day_start():
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))

async def admin_entry(request):
    """آیا این uid مالک است؟ (بدون لو دادن شناسهٔ مالک)"""
    uid = str(request.query.get("uid", ""))
    return web.json_response({"ok": uid != "" and uid == str(ADMIN_UID)})

async def admin_login(request):
    data = await request.json()
    pw = str(data.get("password", ""))
    real = _admin_pw()
    if not real: return web.json_response({"error": "پنل ادمین پیکربندی نشده"}, status=503)
    if not _hmac.compare_digest(pw, real): return web.json_response({"error": "رمز اشتباه"}, status=401)
    return web.json_response({"ok": True, "token": _make_admin_token()})

async def admin_stats(request):
    err = _denied(request)
    if err: return err
    orders = _flat_orders(); now = time.time(); ds = _day_start()
    today = [o for o in orders if o.get("ts", 0) >= ds]
    w = load_wallet()
    return web.json_response({
        "users": len(_all_uids()),
        "wallet_total": sum(int(v.get("balance", 0)) for v in w.values() if isinstance(v, dict)),
        "orders_total": len(orders),
        "orders_today": len(today),
        "revenue_total": sum(int(o.get("price", 0)) for o in orders if o.get("status") != "rejected"),
        "revenue_today": sum(int(o.get("price", 0)) for o in today if o.get("status") != "rejected"),
        "pending": len([o for o in orders if o.get("status") == "pending"]),
        "subs": sum(len(v) for v in load_configs().values() if isinstance(v, list)),
        "pending_admin": len([1 for v in load_pending().values() if isinstance(v, dict) and v.get("waiting_admin")]),
    })

async def admin_users(request):
    err = _denied(request)
    if err: return err
    w = load_wallet(); c = load_configs(); o = load_orders()
    users = []
    for uid in _all_uids():
        users.append({
            "uid": uid,
            "balance": int(w.get(uid, {}).get("balance", 0)) if isinstance(w.get(uid), dict) else 0,
            "subs": len(c.get(uid, []) or []),
            "orders": len(o.get(uid, []) or []),
        })
    users.sort(key=lambda x: -x["orders"])
    return web.json_response({"users": users})

async def admin_user_detail(request):
    err = _denied(request)
    if err: return err
    uid = str(request.match_info["uid"])
    w = load_wallet(); c = load_configs(); o = load_orders(); r = load_referrals()
    return web.json_response({
        "uid": uid,
        "balance": int(w.get(uid, {}).get("balance", 0)) if isinstance(w.get(uid), dict) else 0,
        "history": (w.get(uid, {}).get("history", []) if isinstance(w.get(uid), dict) else [])[-15:],
        "configs": c.get(uid, []) or [],
        "orders": o.get(uid, []) or [],
        "referrals": len(r.get(uid, {}).get("invited", []) or []),
    })

async def admin_wallet(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    uid = str(data.get("uid", "")).strip(); delta = int(data.get("delta", 0))
    if not uid.isdigit() or not delta: return web.json_response({"error": "uid/delta نامعتبر"}, status=400)
    w = load_wallet()
    if uid not in w or not isinstance(w[uid], dict): w[uid] = {"balance": 0, "history": []}
    w[uid]["balance"] = max(0, int(w[uid].get("balance", 0)) + delta)
    w[uid].setdefault("history", []).append({"amount": delta, "type": "admin", "ts": time.time()})
    save_wallet(w)
    return web.json_response({"ok": True, "balance": w[uid]["balance"]})

async def admin_orders(request):
    err = _denied(request)
    if err: return err
    return web.json_response({"orders": _flat_orders()[:200]})

async def admin_discount_delete(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    code = str(data.get("code", "")).strip().lower()
    ds = load_discounts()
    if code not in ds:
        return web.json_response({"error": "کد پیدا نشد"}, status=404)
    del ds[code]
    save_discounts(ds)
    return web.json_response({"ok": True})


async def admin_broadcast(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    text = str(data.get("text", "")).strip()
    scope = str(data.get("scope", "all"))
    if not text: return web.json_response({"error": "متن خالی است"}, status=400)
    uids = _all_uids()
    if scope == "buyers":
        o = load_orders(); uids = [u for u in uids if o.get(u)]
    sent = failed = 0
    async with httpx.AsyncClient(timeout=15) as hc:
        for u in uids[:3000]:
            try:
                r = await hc.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                  json={"chat_id": int(u), "text": text})
                if r.json().get("ok"): sent += 1
                else: failed += 1
            except Exception:
                failed += 1
            await _asyncio.sleep(0.05)
    return web.json_response({"ok": True, "sent": sent, "failed": failed, "targets": len(uids)})

async def admin_discounts(request):
    err = _denied(request)
    if err: return err
    now = time.time()
    out = []
    for code, d in load_discounts().items():
        out.append({"code": code, "type": d.get("type"), "value": d.get("value"),
                    "used": d.get("used", 0), "max_uses": d.get("max_uses", 0),
                    "expires": d.get("expires", 0), "active": d.get("active", True),
                    "expired": bool(d.get("expires")) and now > float(d.get("expires"))})
    out.sort(key=lambda x: -x["used"])
    return web.json_response({"discounts": out})

async def admin_discount_save(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    code = str(data.get("code", "")).strip().lower()
    typ = "percent" if data.get("type") == "percent" else "amount"
    try: value = int(data.get("value", 0))
    except Exception: value = 0
    if not code or value <= 0 or (typ == "percent" and value > 100):
        return web.json_response({"error": "کد یا مقدار نامعتبر"}, status=400)
    try: max_uses = int(data.get("max_uses", 0))
    except Exception: max_uses = 0
    try: days = float(data.get("expires_days", 0) or 0)
    except Exception: days = 0
    ds = load_discounts()
    ds[code] = {"type": typ, "value": value, "max_uses": max_uses,
                "used": ds.get(code, {}).get("used", 0),
                "expires": (time.time() + days * 86400) if days else 0,
                "active": bool(data.get("active", True)), "created": time.time()}
    save_discounts(ds)
    return web.json_response({"ok": True, "code": code})

async def admin_discount_toggle(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    code = str(data.get("code", "")).strip().lower()
    ds = load_discounts()
    if code not in ds: return web.json_response({"error": "کد پیدا نشد"}, status=404)
    ds[code]["active"] = not ds[code].get("active", True)
    save_discounts(ds)
    return web.json_response({"ok": True, "active": ds[code]["active"]})

def create_web_app():
    app = web.Application()
    app.router.add_get("/", serve_index)
    app.router.add_get("/index.html", serve_index)
    app.router.add_get("/api/user/{uid}", api_user)
    app.router.add_get("/api/debug_channel", api_debug_channel)
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/sub_status", api_sub_status)
    app.router.add_post("/api/buy_config", api_buy_config)
    app.router.add_post("/api/buy_config_name", api_buy_config_name)
    app.router.add_post("/api/buy_express", api_buy_express)
    app.router.add_post("/api/buy_deezer", api_buy_deezer)
    app.router.add_post("/api/buy_ai", api_buy_ai)
    app.router.add_post("/api/buy_spotify", api_buy_spotify)
    app.router.add_post("/api/wallet_charge", api_wallet_charge)
    app.router.add_get("/api/admin/entry", admin_entry)
    app.router.add_post("/api/admin/login", admin_login)
    app.router.add_get("/api/admin/stats", admin_stats)
    app.router.add_get("/api/admin/users", admin_users)
    app.router.add_get("/api/admin/user/{uid}", admin_user_detail)
    app.router.add_post("/api/admin/wallet", admin_wallet)
    app.router.add_get("/api/admin/orders", admin_orders)
    app.router.add_post("/api/admin/broadcast", admin_broadcast)
    app.router.add_get("/api/admin/discounts", admin_discounts)
    app.router.add_post("/api/admin/discount", admin_discount_save)
    app.router.add_post("/api/admin/discount_toggle", admin_discount_toggle)
    app.router.add_post("/api/admin/discount_delete", admin_discount_delete)
    app.router.add_get("/api/plans", api_plans)
    app.router.add_get("/api/admin/plans", admin_plans)
    app.router.add_post("/api/admin/plan", admin_plan_save)
    app.router.add_get("/api/admin/subs", admin_subs)
    app.router.add_post("/api/admin/sub", admin_sub_action)
    app.router.add_get("/api/admin/requests", admin_requests)
    app.router.add_post("/api/admin/request", admin_request_action)
    app.router.add_post("/api/admin/order", admin_order_action)
    # Static files — must come AFTER specific routes
    app.router.add_get("/{name:.*}", serve_static)
    return app

# ─── Admin panel: plan overrides / subscriptions / requests ────────────
PLAN_OVERRIDES_FILE = "plan_overrides.json"
RECEIPTS_FILE = "receipts.json"

def load_plan_overrides(): return _load(PLAN_OVERRIDES_FILE)
def save_plan_overrides(d): _save(PLAN_OVERRIDES_FILE, d)
def load_receipts(): return _load(RECEIPTS_FILE)
def save_receipts(d): _save(RECEIPTS_FILE, d)

PLAN_KINDS = {"config": CONFIG_PLANS, "express": EXPRESS_PLANS, "deezer": DEEZER_PLANS,
              "ai": AI_PLANS, "spotify": SPOTIFY_PLANS}

TYPE_LABELS = {
    "send_config": "📦 کانفیگ VPN", "send_express": "⚡ ExpressVPN",
    "send_deezer": "🎵 Deezer", "send_spotify": "🎧 Spotify",
    "send_ai": "🤖 هوش مصنوعی", "send_gta": "🎮 GTA VI",
    "charge": "💰 رسید شارژ کیف پول", "charge_custom": "💳 درخواست شارژ",
    "charge_receipt": "💳 رسید شارژ", "config_wallet_name": "📝 اسم کانفیگ",
    "config_receipt_name": "📝 اسم کانفیگ (پس از پرداخت)",
    "config": "📦 رسید کانفیگ", "express": "📸 رسید ExpressVPN",
}

def apply_plan_overrides():
    ov = load_plan_overrides()
    n = 0
    for kind, table in PLAN_KINDS.items():
        for key, o in (ov.get(kind) or {}).items():
            t = table.get(key)
            if not isinstance(t, dict):
                continue
            pi = o.get("price_int")
            if isinstance(pi, int) and pi > 0:
                t["price_int"] = pi
                t["price"] = _fa(pi)
            t["active"] = bool(o.get("active", True))
            n += 1
    logger.info(f"plan overrides applied: {n}")

def _plan_state(kind, key):
    t = PLAN_KINDS.get(kind, {}).get(key)
    if not isinstance(t, dict):
        return None
    return {"key": key, "name": t.get("name", key), "price": t.get("price", ""),
            "price_int": t.get("price_int", 0), "active": t.get("active", True)}

async def api_plans(request):
    """عمومی — مینی‌اپ قیمت/فعال بودن پلن‌ها رو از همین‌جا می‌گیره"""
    out = {}
    for kind, table in PLAN_KINDS.items():
        out[kind] = {k: {"price": v.get("price", ""), "price_int": v.get("price_int", 0),
                         "active": v.get("active", True)}
                     for k, v in table.items()}
    return web.json_response(out)

async def admin_plans(request):
    err = _denied(request)
    if err: return err
    out = {kind: [_plan_state(kind, k) for k in table] for kind, table in PLAN_KINDS.items()}
    return web.json_response({"plans": out})

async def admin_plan_save(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    kind = str(data.get("kind", "")); key = str(data.get("key", ""))
    if kind not in PLAN_KINDS or key not in PLAN_KINDS[kind]:
        return web.json_response({"error": "پلن پیدا نشد"}, status=404)
    ov = load_plan_overrides()
    slot = ov.setdefault(kind, {})
    cur = dict(slot.get(key) or {})
    if "active" in data:
        cur["active"] = bool(data.get("active"))
    if data.get("price_int") is not None:
        try:
            p = int(data.get("price_int"))
        except Exception:
            return web.json_response({"error": "قیمت نامعتبر"}, status=400)
        if p < 0:
            return web.json_response({"error": "قیمت نامعتبر"}, status=400)
        cur["price_int"] = p
    slot[key] = cur
    save_plan_overrides(ov)
    apply_plan_overrides()
    return web.json_response({"ok": True, "plan": _plan_state(kind, key)})

# ─── Subscriptions control (via BPB panel) ─────────────────────────────
def _panel_ready():
    return bool(BPB_ORIGIN and BPB_SECURE_PATH and BPB_EMAIL and BPB_PASSWORD)

async def _panel_login(c, base):
    r = await c.post(f"{base}/login/authenticate",
                     json={"username": BPB_EMAIL.lower(), "password": BPB_PASSWORD})
    try:
        ok = r.json().get("success")
    except ValueError:
        ok = False
    if not ok:
        raise RuntimeError(f"panel login failed ({r.status_code})")

def _sub_field(link):
    lk = link or ""
    if "/sub/u/" in lk:
        return "subToken", lk.split("?")[0].rstrip("/").split("/")[-1]
    if "/user/" in lk:
        return "uuid", lk.split("?")[0].rstrip("/").split("/")[-1]
    return None, None

def _panel_status(u):
    now = time.time()
    if not u.get("enabled", True): return "disabled"
    if u.get("expireAt", 0) > 0 and now > u["expireAt"]: return "expired"
    gb = u.get("totalGB", 0)
    if gb > 0 and u.get("usedBytes", 0) >= gb * 1024**3: return "quota"
    return "active"

def _remaining_days(u):
    ea = u.get("expireAt", 0)
    if ea <= 0: return 0
    # ceiling: وگرنه هر عملیات پنل یک روز از اشتراک کم می‌کرد
    return max(0, int((ea - time.time() + 86400 - 1) // 86400))

async def admin_subs(request):
    err = _denied(request)
    if err: return err
    uid = str(request.query.get("uid", ""))
    if not uid:
        return web.json_response({"error": "uid لازم"}, status=400)
    if not _panel_ready():
        return web.json_response({"error": "پنل تنظیم نشده"}, status=503)
    cfgs = load_configs().get(uid, [])
    base = f"{BPB_ORIGIN}/{BPB_SECURE_PATH}"
    out = []
    async with httpx.AsyncClient(timeout=40) as c:
        await _panel_login(c, base)
        r = await c.get(f"{base}/panel/users")
        try:
            users = (r.json().get("body") or {}).get("users") or []
        except ValueError:
            users = []
        for i, cf in enumerate(cfgs):
            field, val = _sub_field(cf.get("link", ""))
            u = next((x for x in users if field and x.get(field) == val), None)
            out.append({
                "idx": i, "label": cf.get("data") or cf.get("type") or "اشتراک",
                "type": cf.get("type") or "", "link": (cf.get("link") or "")[:300],
                "found": bool(u),
                "status": _panel_status(u) if u else "notfound",
                "enabled": bool(u.get("enabled", True)) if u else None,
                "expireAt": u.get("expireAt", 0) if u else 0,
                "days_left": _remaining_days(u) if u else 0,
                "totalGB": u.get("totalGB", 0) if u else 0,
                "usedBytes": u.get("usedBytes", 0) if u else 0,
                "name": u.get("name", "") if u else "",
                "token": val or "",
            })
    return web.json_response({"items": out})

async def admin_sub_action(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    token = str(data.get("token", ""))
    action = str(data.get("action", ""))
    days = int(data.get("days") or 0)
    gb = data.get("gb")
    if not token:
        return web.json_response({"error": "token لازم"}, status=400)
    if not _panel_ready():
        return web.json_response({"error": "پنل تنظیم نشده"}, status=503)
    base = f"{BPB_ORIGIN}/{BPB_SECURE_PATH}"
    async with httpx.AsyncClient(timeout=40) as c:
        await _panel_login(c, base)
        r = await c.get(f"{base}/panel/users")
        try:
            users = (r.json().get("body") or {}).get("users") or []
        except ValueError:
            users = []
        u = next((x for x in users if x.get("subToken") == token or x.get("uuid") == token), None)
        if not u:
            return web.json_response({"error": "کاربر پنل پیدا نشد"}, status=404)
        rem = _remaining_days(u)
        never = u.get("expireAt", 0) <= 0   # بدون انقضا: days=0 یعنی منقضی‌شدن!
        keep = 3650 if never else rem
        payload = {"id": u["id"], "name": u.get("name", "user"),
                   "totalGB": int(u.get("totalGB", 0) or 0), "days": keep,
                   "enabled": bool(u.get("enabled", True))}
        note = ""
        if action == "disable":
            payload["enabled"] = False; note = "اشتراک غیرفعال شد"
        elif action == "enable":
            payload["enabled"] = True
            if not never and rem <= 0:
                payload["days"] = days if days > 0 else 30
            note = "اشتراک فعال شد"
        elif action == "extend":
            add = days if days > 0 else 30
            payload["enabled"] = True
            payload["days"] = (keep + add) if (never or rem > 0) else add
            note = f"{add} روز تمدید شد"
        elif action == "quota":
            try:
                payload["totalGB"] = max(0, int(gb))
            except Exception:
                return web.json_response({"error": "حجم نامعتبر"}, status=400)
            note = f"حجم = {payload['totalGB']} گیگ"
        elif action == "reset":
            payload["resetUsage"] = True
            payload["totalGB"] = payload["totalGB"]
            note = "مصرف صفر شد"
        else:
            return web.json_response({"error": "عملیات نامعتبر"}, status=400)
        r = await c.post(f"{base}/panel/user/save", json=payload)
        try:
            ok = r.json().get("success")
        except ValueError:
            ok = False
        if not ok:
            return web.json_response({"error": f"پنل خطا داد ({r.status_code})"}, status=502)
        u2 = next((x for x in users if x.get("id") == u["id"]), None)
        return web.json_response({"ok": True, "note": note,
                                  "status": _panel_status(dict(u, **{"enabled": payload["enabled"],
                                                                     "expireAt": (int(time.time()) + payload["days"] * 86400) if payload["days"] > 0 else 0,
                                                                     "totalGB": payload["totalGB"]}))})

# ─── Requests queue (pending + receipts) + orders actions ──────────────
def _pending_items():
    items = []
    p = load_pending()
    for key, st in p.items():
        if not isinstance(st, dict):
            continue
        typ = str(st.get("type") or "")
        kind = "deliver" if st.get("waiting_admin") else ("user" if st.get("waiting") else "other")
        items.append({"key": str(key), "kind": kind, "type": typ,
                      "label": TYPE_LABELS.get(typ, typ),
                      "user_id": str(st.get("user_id") or key),
                      "plan": st.get("plan") or "", "ts": st.get("ts") or 0})
    for rid, rc in load_receipts().items():
        if not isinstance(rc, dict) or rc.get("status") != "waiting":
            continue
        typ = str(rc.get("ptype") or "")
        items.append({"key": f"receipt:{rid}", "kind": "receipt", "type": typ,
                      "label": TYPE_LABELS.get(typ, "📸 رسید"), "user_id": str(rc.get("uid", "")),
                      "plan": rc.get("plan") or "", "amount": rc.get("amount", 0),
                      "price": rc.get("price", 0), "ts": rc.get("ts", 0)})
    items.sort(key=lambda x: -x.get("ts", 0))
    return items

def _tg_send(uid, text):
    def _fire():
        try:
            httpx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                       json={"chat_id": int(uid), "text": text, "parse_mode": "Markdown"}, timeout=15)
        except Exception:
            try:
                httpx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                           json={"chat_id": int(uid), "text": text}, timeout=15)
            except Exception:
                pass
    threading.Thread(target=_fire, daemon=True).start()   # نباید event loop ربات رو ببنده

def _receipts_resolve(uid, ptype=None):
    rs = load_receipts(); n = 0
    for rid, rc in rs.items():
        if isinstance(rc, dict) and rc.get("status") == "waiting" and str(rc.get("uid")) == str(uid)            and (ptype is None or ptype in str(rc.get("ptype") or "")):
            rc["status"] = "done"; rc["done_ts"] = int(time.time()); n += 1
    if n:
        save_receipts(rs)
    return n

def _receipt_approve(rc):
    uid = str(rc.get("uid", "")); ptype = str(rc.get("ptype") or "")
    amount = int(rc.get("amount") or 0); plan_id = str(rc.get("plan") or "")
    if ptype == "charge":
        add_balance(int(uid), amount)
        _tg_send(uid, f"✅ کیف پول {amount:,} تومان شارژ شد!")
        return f"شارژ {amount:,} تومان اعمال شد"
    if "config" in ptype:
        p = load_pending()
        p[str(uid)] = {"waiting": True, "type": "config_receipt_name", "plan": plan_id,
                       "plan_data": CONFIG_PLANS.get(plan_id, {})}
        save_pending(p)
        _tg_send(uid, "✅ **پرداخت تایید شد!**\n\n📝 اسمی که میخوای روی کانفیگ بیاد رو بفرست:")
        return "پرداخت تایید شد — منتظر اسم کاربر"
    p = load_pending()
    p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_express", "user_id": uid, "plan": plan_id}
    save_pending(p)
    _tg_send(uid, "✅ **پرداخت تایید شد!** به‌زودی لینک اشتراک ارسال می‌شود.")
    _tg_send(OWNER_ID, f"📝 **لینک ExpressVPN رو بفرست**\n\n👤 {uid}")
    return "پرداخت تایید شد — لینک رو بفرست"

async def admin_requests(request):
    err = _denied(request)
    if err: return err
    items = _pending_items()
    for it in items:
        if it["kind"] == "deliver" or it["kind"] == "receipt":
            it["actionable"] = True
    return web.json_response({"items": items})

async def admin_request_action(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    key = str(data.get("key", "")); action = str(data.get("action", ""))
    if not key:
        return web.json_response({"error": "key لازم"}, status=400)

    if key.startswith("receipt:"):
        rid = key.split(":", 1)[1]
        rs = load_receipts(); rc = rs.get(rid)
        if not isinstance(rc, dict) or rc.get("status") != "waiting":
            return web.json_response({"error": "رسید پیدا نشد یا حل شده"}, status=404)
        if action == "reject":
            rc["status"] = "rejected"; rc["done_ts"] = int(time.time())
            save_receipts(rs)
            _tg_send(str(rc.get("uid", "")), "❌ رسید تایید نشد.\nبا پشتیبانی تماس بگیرید.")
            return web.json_response({"ok": True, "note": "رسید رد شد"})
        if action == "approve":
            note = _receipt_approve(rc)
            rc["status"] = "done"; rc["done_ts"] = int(time.time())
            save_receipts(rs)
            return web.json_response({"ok": True, "note": note})
        return web.json_response({"error": "عملیات نامعتبر"}, status=400)

    p = load_pending(); st = p.get(key)
    if not isinstance(st, dict):
        return web.json_response({"error": "درخواست پیدا نشد"}, status=404)
    target = str(st.get("user_id") or key); typ = str(st.get("type") or "")

    if action == "deliver":
        link = str(data.get("link", "")).strip()[:300]
        if not st.get("waiting_admin"):
            return web.json_response({"error": "این درخواست منتظر لینک نیست"}, status=400)
        if not link:
            return web.json_response({"error": "لینک لازم"}, status=400)
        del p[key]; save_pending(p)
        configs = load_configs(); configs.setdefault(target, [])
        configs[target].append({"type": typ, "data": st.get("plan", ""), "link": link})
        save_configs(configs)
        try: mark_order_sent(target, link)
        except Exception: pass
        label = TYPE_LABELS.get(typ, typ)
        _tg_send(target, f"✅ **سفارش شما تأیید شد!**\n\n📦 **نوع:** {label}\n\n🔑 **اطلاعات:**\n`{link}`\n\nاز پنل کاربری قابل مشاهده است.")
        return web.json_response({"ok": True, "note": f"برای {target} ارسال شد"})

    if action == "reject":
        del p[key]; save_pending(p)
        _tg_send(target, "❌ **سفارش شما لغو شد.**\nبا پشتیبانی تماس بگیرید.")
        return web.json_response({"ok": True, "note": "درخواست رد شد"})

    if action == "cancel":
        del p[key]; save_pending(p)
        return web.json_response({"ok": True, "note": "درخواست حذف شد"})

    return web.json_response({"error": "عملیات نامعتبر"}, status=400)

async def admin_order_action(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    uid = str(data.get("uid", ""))
    try:
        oid = int(data.get("id"))
    except Exception:
        return web.json_response({"error": "id نامعتبر"}, status=400)
    action = str(data.get("action", ""))
    o = load_orders(); lst = o.get(uid) or []
    it = next((x for x in lst if int(x.get("id", -1)) == oid), None)
    if not it:
        return web.json_response({"error": "سفارش پیدا نشد"}, status=404)
    if action == "deliver":
        link = str(data.get("link", "")).strip()[:300]
        it["status"] = "sent"; it["delivered_ts"] = int(time.time())
        it["days"] = _plan_days(it.get("kind", ""), it.get("plan", ""))
        if link: it["link"] = link
        save_orders(o)
        msg = f"✅ **سفارش شما تحویل شد:** {it.get('name') or it.get('plan')}"
        if link: msg += f"\n\n`{link}`"
        _tg_send(uid, msg)
        return web.json_response({"ok": True, "status": "sent"})
    if action == "reject":
        price = int(it.get("price") or 0)
        it["status"] = "rejected"; it["rejected_ts"] = int(time.time())
        save_orders(o)
        if price > 0:
            add_balance(int(uid), price)
        _tg_send(uid, f"❌ **سفارش شما لغو شد:** {it.get('name') or it.get('plan')}"
                      + (f"\n\n💰 {price:,} تومان به کیف پول بازگشت." if price > 0 else ""))
        return web.json_response({"ok": True, "status": "rejected", "refunded": price})
    return web.json_response({"error": "عملیات نامعتبر"}, status=400)

# ─── Main: Web Server (thread) + Bot (main thread) ──────
def main():
    PORT = int(os.environ.get("PORT", 8080))
    try:
        kv_boot()
    except Exception as e:
        logger.warning(f"KV boot error: {e}")
    try:
        apply_plan_overrides()
    except Exception as e:
        logger.warning(f"plan overrides error: {e}")

    def run_web():
        import asyncio as _aio
        loop = _aio.new_event_loop()
        _aio.set_event_loop(loop)
        runner = web.AppRunner(create_web_app())
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "0.0.0.0", PORT).start())
        logger.info(f"Web server on port {PORT}")
        if _KV_ENABLED:
            loop.create_task(_kv_push_loop())
        loop.run_forever()

    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_member, pattern="^check_member$"))
    app.add_handler(CallbackQueryHandler(buy_config, pattern="^buy_config$"))
    app.add_handler(CallbackQueryHandler(select_config, pattern="^config_"))
    app.add_handler(CallbackQueryHandler(pay_config, pattern="^pay_config_"))
    app.add_handler(CallbackQueryHandler(pay_wallet_config, pattern="^pay_wallet_config_"))
    app.add_handler(CallbackQueryHandler(receipt_received, pattern="^receipt_(?!express_)"))
    app.add_handler(CallbackQueryHandler(buy_express, pattern="^buy_express$"))
    app.add_handler(CallbackQueryHandler(select_express, pattern="^express_"))
    app.add_handler(CallbackQueryHandler(pay_express, pattern="^pay_express_"))
    app.add_handler(CallbackQueryHandler(pay_wallet_express, pattern="^pay_wallet_express_"))
    app.add_handler(CallbackQueryHandler(receipt_express_received, pattern="^receipt_express_"))
    app.add_handler(CallbackQueryHandler(free_sub_menu, pattern="^free_sub$"))
    app.add_handler(CallbackQueryHandler(claim_free_sub, pattern="^claim_free_sub$"))
    app.add_handler(CallbackQueryHandler(wallet_menu, pattern="^wallet_menu$"))
    app.add_handler(CallbackQueryHandler(charge_wallet, pattern="^charge_wallet$"))
    app.add_handler(CallbackQueryHandler(charge_custom, pattern="^charge_custom$"))
    app.add_handler(CallbackQueryHandler(charge_amount, pattern="^charge_[0-9]+$"))
    app.add_handler(CallbackQueryHandler(charge_receipt_step, pattern="^charge_receipt_"))
    app.add_handler(CallbackQueryHandler(wallet_history, pattern="^wallet_history$"))
    app.add_handler(CallbackQueryHandler(user_panel, pattern="^user_panel$"))
    app.add_handler(CallbackQueryHandler(sub_status, pattern="^sub_status$"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(approve_express, pattern="^approve_express_"))
    app.add_handler(CallbackQueryHandler(approve_config, pattern="^approve_config_"))
    app.add_handler(CallbackQueryHandler(approve_receipt, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_receipt, pattern="^reject_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
# v3 cache clear
# v4

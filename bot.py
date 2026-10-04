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
_CH_RAW = (os.environ.get("CHANNEL_ID") or "").strip()
# کانال عضویت = diazshopcom؛ مقدار قدیمی @diazplaylist که در env ریل‌وی مانده نادیده گرفته می‌شود
CHANNEL_ID = "@diazshopcom" if _CH_RAW.lstrip("@").lower() in ("", "diazplaylist") \
    else ("@" + _CH_RAW.lstrip("@"))
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
    "10gb": {"name": "۱۰ گیگ", "price": "۱۰,۰۰۰", "data": "10GB", "duration": "۱ ماه", "price_int": 10000, "limit_gb": 10, "days": 30},
    "20gb": {"name": "۲۰ گیگ", "price": "۲۶,۰۰۰", "data": "20GB", "duration": "۱ ماه", "price_int": 26000, "limit_gb": 20, "days": 30},
    "50gb": {"name": "۵۰ گیگ", "price": "۶۲,۰۰۰", "data": "50GB", "duration": "۱ ماه", "price_int": 62000, "limit_gb": 50, "days": 30},
    "80gb": {"name": "۸۰ گیگ", "price": "۹۸,۰۰۰", "data": "80GB", "duration": "۱ ماه", "price_int": 98000, "limit_gb": 80, "days": 30},
}

EXPRESS_PLANS = {
    "1m": {"name": "۱ ماهه", "price": "۱۹۰,۰۰۰", "price_int": 190000, "days": 30},
    "3m": {"name": "۳ ماهه", "price": "۳۰۰,۰۰۰", "price_int": 300000, "days": 90},
    "6m": {"name": "۶ ماهه", "price": "۴۶۰,۰۰۰", "price_int": 460000, "days": 180},
    "1y": {"name": "۱ ساله", "price": "۹۰۰,۰۰۰", "price_int": 900000, "days": 365},
}

DEEZER_PLANS = {
    "family": {"name": "فمیلی یک‌ماهه", "price": "۱۳۵,۰۰۰", "price_int": 135000},
    "personal": {"name": "شخصی یک‌ماهه", "price": "۲۰۰,۰۰۰", "price_int": 200000},
}

AI_PLANS = {
    "gemini18m": {"name": "جمنای ۱۸ ماهه پرو • نامحدود", "price": "۳,۲۵۰,۰۰۰", "price_int": 3250000, "days": 548, "brand": "gemini"},
    "gemfam1m": {"name": "جمنای پرو فمیلی • نامحدود — ۱ ماهه", "price": "۸۰۰,۰۰۰", "price_int": 800000, "days": 30, "brand": "gemini"},
    "gemfam3m": {"name": "جمنای پرو فمیلی • نامحدود — ۳ ماهه", "price": "۱,۱۵۰,۰۰۰", "price_int": 1150000, "days": 90, "brand": "gemini"},
    "gemfam6m": {"name": "جمنای پرو فمیلی • نامحدود — ۶ ماهه", "price": "۱,۸۰۰,۰۰۰", "price_int": 1800000, "days": 180, "brand": "gemini"},
    "gemfam1y": {"name": "جمنای پرو فمیلی • نامحدود — ۱ ساله", "price": "۲,۵۰۰,۰۰۰", "price_int": 2500000, "days": 365, "brand": "gemini"},
    "claudepro": {"name": "Claude Pro یک‌ماهه", "price": "۵,۸۵۰,۰۰۰", "price_int": 5850000, "days": 30},
    "gpt_go": {"name": "ChatGPT Go یک‌ماهه", "price": "۲,۳۰۰,۰۰۰", "price_int": 2300000, "days": 30},
    "gpt_plus": {"name": "ChatGPT پلاس آماده یک‌ماهه", "price": "۴,۲۵۰,۰۰۰", "price_int": 4250000, "days": 30},
}

SPOTIFY_PLANS = {
    "spotify1m": {"name": "Spotify اختصاصی یک‌ماهه (نامحدود)", "price": "۱,۳۵۰,۰۰۰", "price_int": 1350000, "days": 30},
}

SPECIAL_PLANS = {
    "gta": {"name": "GTA VI Ultimate Edition — Xbox Home", "price": "۱۲,۰۰۰,۰۰۰", "price_int": 12000000},
}

REFERRAL_TARGET = 1
REFERRAL_PERCENT = 5  # 🎁 درصد هدیه رفرال از مبلغ خرید دوست

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


# ─── نوت بازگشایی فروشگاه (اطلاعیهٔ روی صفحه) ──────────────
ANNOUNCE_FILE = "announcement.json"
DEFAULT_ANNOUNCE = {
    "enabled": False,  # نوت برای مشتری‌ها خاموشه — ادمین از پنل روشنش میکنه
    "title": "🎉 به مناسب بازگشایی فروشگاه",
    "text": "رو همهٔ محصولات تخفیف ویژه زدیم 🔥\nتا پایان شمارش معکوس فرصت داری!",
    "sale_end": "",  # حراج تموم شده — تایمر خالی = نوار بالای صفحه نمیاد
}

def load_announce():
    d = _load(ANNOUNCE_FILE)
    if not isinstance(d, dict): d = {}
    out = dict(DEFAULT_ANNOUNCE); out.update(d)
    return out

def save_announce(d): _save(ANNOUNCE_FILE, d)

# ─── تیکت پشتیبانی (جایگزین آیدی شخصی ادمین) ────────────────
TICKETS_FILE = "tickets.json"
FAQ_FILE = "faq.json"

def load_tickets():
    d = _load(TICKETS_FILE)
    return d if isinstance(d, dict) else {}

def save_tickets(d): _save(TICKETS_FILE, d)

FAQ_DEFAULT = [
    "کی سفارشم تحویل داده می‌شه؟",
    "گارانتی ویژه دیاز شاپ یعنی چی؟",
    "روش پرداخت چطوریه؟",
    "اگه اشتراکم مشکل پیدا کرد چیکار کنم؟",
]

def load_faq():
    """سوالات پرتکراری که ادمین خودش مدیریتشون می‌کنه"""
    d = _load(FAQ_FILE)
    if isinstance(d, dict) and "questions" in d:
        return [str(x) for x in (d.get("questions") or []) if str(x).strip()]
    if isinstance(d, list):
        return [str(x) for x in d if str(x).strip()]
    return list(FAQ_DEFAULT)

def save_faq(qs): _save(FAQ_FILE, {"questions": qs})

def create_ticket(uid, user, text, source="bot"):
    ts = load_tickets()
    tid = str(max([int(k) for k in ts.keys() if str(k).isdigit()] + [0]) + 1)
    now = int(time.time())
    ts[tid] = {"uid": str(uid),
               "name": (getattr(user, "first_name", "") or "") if user is not None else "",
               "uname": (getattr(user, "username", "") or "") if user is not None else "",
               "text": (text or "")[:1000], "ts": now,
               "status": "open", "reply": "", "reply_ts": 0, "source": source,
               "messages": [{"from": "user", "text": (text or "")[:1000], "ts": now}]}
    save_tickets(ts)
    return tid

def _ticket_msgs(t):
    """تاریخچهٔ پیام‌ها؛ تیکت‌های قدیمی (بدون messages) مهاجرت داده می‌شن."""
    if not isinstance(t, dict): return []
    m = t.get("messages")
    if isinstance(m, list) and m: return m
    out = []
    if t.get("text"):
        out.append({"from": "user", "text": str(t.get("text"))[:2000], "ts": int(t.get("ts") or 0)})
    if t.get("reply"):
        out.append({"from": "admin", "text": str(t.get("reply"))[:2000], "ts": int(t.get("reply_ts") or 0)})
    return out

def _open_ticket_for(uid):
    """آخرین تیکتِ بازِ این کاربر (بسته‌شده = چت پاک شده)."""
    ts = load_tickets(); best = None; bi = -1
    for k, t in ts.items():
        if not isinstance(t, dict) or not str(k).isdigit(): continue
        if str(t.get("uid")) != str(uid): continue
        if t.get("status") == "closed": continue
        if int(k) > bi: bi = int(k); best = (str(k), t)
    return best

def _ticket_reply(tid, uid, reply, by=""):
    ts = load_tickets(); t = ts.get(str(tid))
    if not isinstance(t, dict): return False
    msgs = list(_ticket_msgs(t))                      # قبل از ست کردن reply
    t["status"] = "answered"; t["reply"] = (reply or "")[:2000]; t["reply_ts"] = int(time.time())
    msgs.append({"from": "admin", "text": t["reply"], "ts": t["reply_ts"],
                 "name": (str(by or "").strip() or "Diaz support")[:40]})
    t["messages"] = msgs
    ts[str(tid)] = t; save_tickets(ts)
    return True

def _ticket_push(tid, text, who="user"):
    ts = load_tickets(); t = ts.get(str(tid))
    if not isinstance(t, dict): return None
    msgs = list(_ticket_msgs(t))
    msgs.append({"from": who, "text": str(text)[:2000], "ts": int(time.time())})
    t["messages"] = msgs
    if who == "user":
        t["text"] = str(text)[:1000]                   # آخرین پیام کاربر برای اعلان/لیست
        t["status"] = t.get("status") or "open"
    ts[str(tid)] = t; save_tickets(ts)
    return t

def notify_admins_ticket(tid):
    """اعلام تیکت جدید به ادمین‌های تلگرام (با دکمهٔ «پاسخ») — توی thread تا لوپ رو نبنده."""
    t = load_tickets().get(str(tid))
    if not isinstance(t, dict): return 0
    uid = str(t.get("uid", ""))
    nm = t.get("name") or "کاربر"; un = t.get("uname") or ""
    src = "مینی‌اپ" if t.get("source") == "app" else "ربات"
    txt = (f"🎫 تیکت پشتیبانی #{tid}\n\n"
           f"👤 {nm} — {uid}" + (f" @{un}" if un else "") +
           f"\n📌 {src}\n\n💬 {t.get('text', '')}")
    kb = None
    try:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ پاسخ", callback_data=f"ticket_reply_{tid}")]]).to_dict()
    except Exception:
        kb = None

    def _fire():
        for a in admin_uids():
            if str(a) == uid: continue
            try:
                payload = {"chat_id": int(a), "text": txt}
                if kb: payload["reply_markup"] = kb
                httpx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload, timeout=12)
            except Exception as e:
                logger.error(f"ticket notify {a}: {e}")

    threading.Thread(target=_fire, daemon=True).start()
    return 1

async def ticket_new(update, context):
    q = update.callback_query
    try: await q.answer()
    except Exception: pass
    uid = str(q.from_user.id)
    p = load_pending(); p[uid] = {"waiting": True, "type": "ticket"}; save_pending(p)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 انصراف", callback_data="ticket_cancel")],
                               [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_main")]])
    msg = ("🎫 ثبت تیکت پشتیبانی\n\n"
           "متن مشکل یا سوالت رو همین‌جا بفرست تا ثبت بشه و جوابش بیاد 👇 ✌️")
    try:
        await q.edit_message_text(msg, reply_markup=kb)
    except Exception:
        try:
            if q.message: await q.message.reply_text(msg, reply_markup=kb)
        except Exception: pass

async def ticket_cancel(update, context):
    q = update.callback_query
    uid = str(q.from_user.id)
    p = load_pending(); st = p.get(uid)
    if st and st.get("type") == "ticket":
        del p[uid]; save_pending(p)
    try: await q.answer("انصراف شد")
    except Exception: pass
    try: await q.edit_message_text("❌ ثبت تیکت لغو شد.")
    except Exception: pass

async def ticket_reply_cb(update, context):
    q = update.callback_query
    uid = str(q.from_user.id)
    if not _is_admin(uid):
        try: await q.answer("فقط ادمین ❌", show_alert=True)
        except Exception: pass
        return
    tid = str(q.data).split("_")[-1]
    t = load_tickets().get(tid)
    if not isinstance(t, dict):
        try: await q.answer("تیکت پیدا نشد", show_alert=True)
        except Exception: pass
        return
    try: await q.answer()
    except Exception: pass
    p = load_pending()
    p[uid] = {"waiting_admin": True, "type": "ticket_reply", "tid": tid, "user_id": str(t.get("uid", ""))}
    save_pending(p)
    body = (t.get("text", "") or "")[:400]
    await q.edit_message_text(
        f"✍️ پاسخ تیکت #{tid} رو بفرست:\n\n"
        f"💬 {t.get('name', 'کاربر')} ({t.get('uid', '')}):\n{body}")

# ─── endpoint های نوت و تیکت ──────────────────────────────
async def api_faq(request):
    """سوالات پرتکرار (برای چیپ‌های بالای کادر پیام پشتیبانی)"""
    return web.json_response({"questions": load_faq()})

async def admin_faq(request):
    """افزودن/حذف سوال توسط ادمین"""
    err = _denied(request)
    if err: return err
    data = await request.json()
    action = str(data.get("action", ""))
    qs = load_faq()
    if action == "add":
        t = str(data.get("text", "")).strip()[:200]
        if t and t not in qs: qs.append(t)
    elif action == "del":
        try: i = int(data.get("index"))
        except Exception: return web.json_response({"error": "index نامعتبر"}, status=400)
        if 0 <= i < len(qs): qs.pop(i)
    elif action == "save":
        raw = data.get("questions") or []
        qs = [str(x).strip()[:200] for x in raw if str(x).strip()][:50]
    else:
        return web.json_response({"error": "action نامعتبر"}, status=400)
    save_faq(qs)
    return web.json_response({"questions": qs})

async def api_announcement(request):
    try:
        return web.json_response(load_announce())
    except Exception as e:
        logger.error(f"announcement: {e}")
        return web.json_response({"enabled": False})

async def admin_announcement_save(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    a = load_announce()
    if "enabled" in data: a["enabled"] = bool(data.get("enabled"))
    if data.get("title") is not None: a["title"] = str(data.get("title") or "")[:120]
    if data.get("text") is not None: a["text"] = str(data.get("text") or "")[:800]
    if data.get("sale_end") is not None:
        se = str(data.get("sale_end") or "").strip()
        if se:
            try:
                from datetime import datetime as _dtx
                _dtx.fromisoformat(se)
            except Exception:
                return web.json_response({"error": "تاریخ نامعتبر. مثال: 2026-10-06T23:59:00+03:30"}, status=400)
        a["sale_end"] = se
    save_announce(a)
    return web.json_response({"ok": True, "announce": a})

async def api_ticket_new(request):
    data = await request.json()
    uid = str(data.get("uid") or "").strip()
    txt = str(data.get("text") or "").strip()
    if not uid.isdigit():
        return web.json_response({"error": "invalid uid"}, status=400)
    if len(txt) < 3 or len(txt) > 1000:
        return web.json_response({"error": "متن تیکت باید بین ۳ تا ۱۰۰۰ کاراکتر باشه"}, status=400)
    import types as _types
    raw = _load(USERS_FILE)
    u = raw.get(uid) if isinstance(raw, dict) else None
    if not isinstance(u, dict): u = {}
    shim = _types.SimpleNamespace(first_name=u.get("name") or u.get("first_name") or "کاربر مینی‌اپ",
                                  username=u.get("username") or "")
    found = _open_ticket_for(uid)
    if found:
        tid, _t = found
        t2 = _ticket_push(tid, txt, "user")
        msgs = (t2 or {}).get("messages") or _ticket_msgs(_t)
        # فقط وقتی آخرین پیام از ادمین بوده اطلاع بده تا اسپم نشه
        if len(msgs) >= 2 and msgs[-2].get("from") == "admin":
            notify_admins_ticket(tid)
        return web.json_response({"ok": True, "id": tid, "messages": msgs, "reused": True})
    tid = create_ticket(uid, shim, txt, "app")
    notify_admins_ticket(tid)
    return web.json_response({"ok": True, "id": tid,
                              "messages": _ticket_msgs(load_tickets().get(tid) or {})})

async def api_ticket_get(request):
    uid = str(request.query.get("uid") or "").strip()
    if not uid.isdigit():
        return web.json_response({"error": "invalid uid"}, status=400)
    found = _open_ticket_for(uid)
    if not found:
        return web.json_response({"ticket": None})
    tid, t = found
    return web.json_response({"ticket": {"id": tid, "status": t.get("status", "open"),
                                         "source": t.get("source", "bot"),
                                         "ts": t.get("ts", 0), "messages": _ticket_msgs(t)}})

async def admin_tickets(request):
    err = _denied(request)
    if err: return err
    ts = load_tickets(); out = []
    for k, t in ts.items():
        if not isinstance(t, dict): continue
        out.append({"id": str(k), "uid": t.get("uid", ""), "name": t.get("name", ""),
                    "uname": t.get("uname", ""), "text": t.get("text", ""),
                    "ts": t.get("ts", 0), "status": t.get("status", "open"),
                    "reply": t.get("reply", ""), "source": t.get("source", "bot"),
                    "messages": _ticket_msgs(t)})
    out.sort(key=lambda x: -int(x.get("ts") or 0))
    return web.json_response({"tickets": out})

async def admin_ticket_reply(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    tid = str(data.get("id") or "")
    txt = str(data.get("text") or "").strip()
    if len(txt) < 1:
        return web.json_response({"error": "متن خالی است"}, status=400)
    t = load_tickets().get(tid)
    if not isinstance(t, dict):
        return web.json_response({"error": "تیکت پیدا نشد"}, status=404)
    nm = admin_name(str(data.get("uid") or ""), str(data.get("name") or ""))
    _ticket_reply(tid, str(t.get("uid", "")), txt[:2000], nm)
    if t.get("uid"):
        _tg_send(str(t.get("uid")), f"📩 پاسخ {nm} (تیکت #{tid}):\n\n{txt[:2000]}")
    return web.json_response({"ok": True})

async def admin_ticket_close(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    tid = str(data.get("id") or "")
    ts = load_tickets(); t = ts.get(tid)
    if not isinstance(t, dict):
        return web.json_response({"error": "تیکت پیدا نشد"}, status=404)
    if t.get("status") != "closed":
        t["status"] = "closed"; ts[tid] = t; save_tickets(ts)
        if t.get("uid"):
            _tg_send(str(t.get("uid")),
                     f"🔒 تیکت #{tid} بسته شد.\nاگه سوال جدیدی داشتی دوباره از پنل کاربری → پشتیبانی بفرست.")
    return web.json_response({"ok": True})

def _kv_files():
    return [PENDING_FILE, WALLET_FILE, CONFIGS_FILE, REFERRALS_FILE,
            ACCOUNTS_FILE, ORDERS_FILE, DISCOUNTS_FILE,
            PLAN_OVERRIDES_FILE, CUSTOM_PLANS_FILE, RECEIPTS_FILE, USERS_FILE, ADMINS_FILE,
            ANNOUNCE_FILE, TICKETS_FILE, FAQ_FILE, UI_FILE]

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
    if kind == "spotify": return SPOTIFY_PLANS.get(key, {}).get("days", 30)
    if kind == "config": return CONFIG_PLANS.get(key, {}).get("days", 30)
    if kind == "deezer": return DEEZER_PLANS.get(key, {}).get("days", 30)
    if kind == "special": return 0   # GTA یک‌بار مصرفه — انقضا نداره
    return 30

def _order_expiry(it):
    """تاریخ انقضای سفارش: لحظه تحویل (یا خرید) + روزهای پلن"""
    if not isinstance(it, dict): return 0
    try:
        base = int(it.get("delivered_ts") or it.get("ts") or 0)
        days = int(it.get("days") or _plan_days(it.get("kind", ""), it.get("plan", "")) or 0)
        return (base + days * 86400) if (base and days) else 0
    except Exception:
        return 0
_KIND_OF_TYPE = {"config": "config", "express": "express", "deezer": "deezer",
                 "spotify": "music", "ai": "ai", "gta": "special"}

def _kind_from_type(typ):
    """نوع درخواست (send_express / config_receipt_name / ...) → kind سفارش."""
    t = str(typ or "").lower()
    if "config" in t: return "config"
    if "express" in t: return "express"
    if "deezer" in t: return "deezer"
    if "spotify" in t: return "music"
    if "gta" in t: return "special"
    if "ai" in t or "gemini" in t: return "ai"
    for key, val in _KIND_OF_TYPE.items():
        if key in t: return val
    return "config"

def _plan_info(kind, key):
    """نام و قیمت پلن از روی kind+کلید (برای ثبت سفارشِ بدون اطلاعات قبلی)."""
    plans = {"config": CONFIG_PLANS, "express": EXPRESS_PLANS, "ai": AI_PLANS,
             "music": SPOTIFY_PLANS, "spotify": SPOTIFY_PLANS, "deezer": DEEZER_PLANS}.get(kind, {})
    p = plans.get(str(key)) if isinstance(plans, dict) else None
    if not isinstance(p, dict): p = {}
    return (p.get("name") or str(key) or str(kind)), int(p.get("price_int") or 0)

def _ensure_pending_order(uid, typ, plan_key=""):
    """مسیرهای رسید/کارتی سفارشی ثبت نمی‌کردن → اگه سفارش در انتظاری نیست، الان بسازش
    تا هم تو پنل ادمین دیده بشه و هم بعد از تحویل، انقضای ۳۰ روزهٔ مشتری درست حساب بشه."""
    try:
        kind = _kind_from_type(typ)
        o = load_orders(); lst = o.setdefault(str(uid), [])
        pend = [x for x in lst if isinstance(x, dict) and x.get("status") == "pending"]
        if any(x.get("kind") == kind for x in pend) or (not kind and pend):
            return None
        if pend:
            return None                       # یه سفارش در انتظار دیگه هست؛ همون تحویل داده میشه
        name, price = _plan_info(kind, plan_key)
        add_order(uid, kind, str(plan_key or ""), name, price)   # از مسیر add_order → هدیه رفرال هم پرداخت بشه
        rec = [x for x in load_orders().get(str(uid), [])
               if isinstance(x, dict) and x.get("status") == "pending"]
        logger.info(f"ensure order uid={uid} kind={kind} plan={plan_key}")
        return rec[-1] if rec else None
    except Exception as e:
        logger.warning(f"ensure order failed: {e}")
        return None

def add_order(uid, kind, plan_key, plan_name, price, email=""):
    o = load_orders(); lst = o.setdefault(str(uid), [])
    _rec = {"id": int(time.time()), "kind": kind, "plan": plan_key, "name": plan_name, "price": price, "status": "pending", "ts": int(time.time())}
    if email: _rec["email"] = email
    lst.append(_rec)
    try:
        _amt, _to = pay_referral(uid, price)
        if _amt > 0 and _to:
            _rec["ref_bonus"] = _amt; _rec["ref_to"] = _to
    except Exception as e:
        logger.warning(f"referral hook: {e}")
    save_orders(o)
def mark_order_sent(uid, link="", kind=""):
    o = load_orders(); lst = o.get(str(uid), [])
    target = None
    if kind:
        for it in reversed(lst):
            if isinstance(it, dict) and it.get("status") == "pending" and it.get("kind") == kind:
                target = it; break
    if target is None:
        for it in reversed(lst):
            if isinstance(it, dict) and it.get("status") == "pending":
                target = it; break
    if target is not None:
        target["status"] = "sent"; target["delivered_ts"] = int(time.time())
        target["days"] = _plan_days(target.get("kind", ""), target.get("plan", ""))
        if link: target["link"] = link[:300]
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

def inviter_of(uid):
    """کسی که این کاربر رو با لینک start=ref دعوت کرده"""
    u = str(uid)
    try:
        for inv, d in load_referrals().items():
            if str(inv) == u: continue
            if u in [str(x) for x in (d.get("invited") or [])]:
                return str(inv)
    except Exception as e:
        logger.warning(f"inviter_of: {e}")
    return None

def referral_earned(uid):
    """جمع کل هدیه‌های رفرالی که به کیف پول این کاربر رفته"""
    try:
        h = load_wallet().get(str(uid), {}).get("history", []) or []
        return int(sum(int(x.get("amount") or 0) for x in h if x.get("type") == "referral" and int(x.get("amount") or 0) > 0))
    except Exception:
        return 0

def pay_referral(uid, price):
    """۵٪ از مبلغ خرید رو به کیف پول دعوت‌کننده می‌ریزه. خروجی: (مبلغ، کیف)"""
    try:
        price = int(price or 0)
        if price <= 0: return (0, None)
        inv = inviter_of(uid)
        if not inv or inv == str(uid): return (0, None)
        amt = price * REFERRAL_PERCENT // 100
        if amt <= 0: return (0, None)
        w = load_wallet()
        if inv not in w: w[inv] = {"balance": 0, "history": []}
        w[inv]["balance"] = int(w[inv].get("balance", 0)) + amt
        w[inv]["history"].append({"amount": amt, "type": "referral", "ts": time.time(),
                                  "note": f"هدیه رفرال {REFERRAL_PERCENT}٪"})
        save_wallet(w)
        _tg_send(int(inv), f"🎁 **هدیه رفرال**\n`{amt:,}` تومان به کیف پولت اضافه شد ({REFERRAL_PERCENT}٪ خرید دوستت).")
        return (amt, inv)
    except Exception as e:
        logger.warning(f"pay_referral: {e}")
        return (0, None)

def refund_referral(rec):
    """برگشت هدیه رفرال موقع لغو سفارش"""
    try:
        amt = int(rec.get("ref_bonus") or 0); to = rec.get("ref_to")
        if amt <= 0 or not to: return 0
        w = load_wallet(); k = str(to)
        if k in w:
            w[k]["balance"] = max(0, int(w[k].get("balance", 0)) - amt)
            w[k]["history"].append({"amount": -amt, "type": "referral", "ts": time.time(),
                                    "note": "برگشت هدیه (سفارش لغو شد)"})
            save_wallet(w)
        return amt
    except Exception as e:
        logger.warning(f"refund_referral: {e}")
        return 0

def spend_balance(uid, amount):
    amount = int(amount or 0)
    if amount <= 0:
        return True  # کد تخفیف ۱۰۰٪ → مبلغ صفر، بدون نیاز به موجودی
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
    " محصولات ما زیر قیمت و تضمینی هستند! ✅"
)

SHOP_ORIGIN = os.environ.get("SHOP_ORIGIN", "https://worker-production-e8dd.up.railway.app")
SHOP_ALT_ORIGIN = os.environ.get("SHOP_ALT_ORIGIN", "https://diazshop.arateafc.workers.dev")

def support_url(uid):
    "لینک مستقیم مینی‌اپ روی صفحهٔ چت تیکت."
    import time as _ts
    return f"{SHOP_ORIGIN}/?uid={uid}&t={int(_ts.time())}&sec=ticket"

def main_menu_kb(uid=0):
    import time as _ts; _t = int(_ts.time()); shop_url = f"{SHOP_ORIGIN}/?uid={uid}&t={_t}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕷️ فروشگاه", web_app=WebAppInfo(url=shop_url))],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet_menu")],
        [InlineKeyboardButton("🎁 اشتراک رایگان", callback_data="free_sub")],
        [InlineKeyboardButton("🎫 پشتیبانی", web_app=WebAppInfo(url=support_url(uid)))],
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


# ─── گیت عضویت کانال (کش ۲ دقیقه؛ «عضو شدم» همیشه چک تازه میزنه) ───
_MEMBER_CACHE = {}
_MEMBER_TTL = 120

async def is_member(uid, force=False):
    """عضویت در کانال — True/False. force=True یعنی از تلگرام بپرس (بدون کش)."""
    try:
        key = str(int(uid))
    except Exception:
        return False
    now = time.time()
    if not force and key in _MEMBER_CACHE and now - _MEMBER_CACHE[key][0] < _MEMBER_TTL:
        return _MEMBER_CACHE[key][1]
    val = False
    try:
        import httpx
        async with httpx.AsyncClient() as hc:
            r = await hc.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
                             params={"chat_id": CHANNEL_ID, "user_id": int(key)}, timeout=8)
            d = r.json()
            if d.get("ok"):
                val = d["result"].get("status") in ("member", "administrator", "creator")
    except Exception as e:
        logger.error(f"is_member({key}): {e}")
        return False          # خطا = عضو نیست (همیشه fail-closed)
    _MEMBER_CACHE[key] = (now, val)
    return val

async def _member_ok(uid):
    """حق خرید/استفاده: ادمین همیشه آزاد، بقیه باید عضو کانال باشن."""
    try:
        if _is_admin(str(uid)): return True
    except Exception:
        pass
    return await is_member(uid)

def require_member(fn):
    """دکمه‌ای که گیت نخوره = عضویت هر بار چک میشه و در صورت نبودن، گیت نشون داده میشه."""
    import functools
    @functools.wraps(fn)
    async def _wrapped(update, context):
        q = getattr(update, "callback_query", None)
        uid = q.from_user.id if q else None
        if uid is not None and not await _member_ok(uid):
            try:
                await q.answer("📢 ابتدا در کانال عضو شوید", show_alert=True)
            except Exception:
                pass
            kb = [[InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
                  [InlineKeyboardButton("✅ عضو شدم", callback_data="check_member")]]
            msg = "⚠️ برای استفاده از ربات ابتدا باید در کانال عضو شوید!"
            try:
                await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))
            except Exception:
                try:
                    if q.message:
                        await q.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    pass
            return
        return await fn(update, context)
    return _wrapped

async def start(update, context):
    user = update.effective_user
    touch_user(user)
    if context.args:
        payload = context.args[0]
        if payload.startswith("ref"):
            try:
                inviter_id = int(payload[3:])
                if inviter_id != user.id:
                    context.user_data["pending_ref"] = inviter_id
                    await _process_referral(context, inviter_id, user.id)
            except: pass
    is_m = await is_member(user.id, force=True)
    logger.info(f"Channel check for {user.id}: is_m={is_m}")
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
    is_m = await is_member(q.from_user.id, force=True)
    if not is_m:
        await q.edit_message_text("❌ هنوز عضو کانال نشدید!"); return
    pr = context.user_data.pop("pending_ref", None)
    if pr: await _process_referral(context, pr, q.from_user.id)
    await q.message.delete()
    await q.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_kb(uid=q.from_user.id))

@require_member
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

@require_member
async def back_main(update, context):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu_kb(uid=q.from_user.id))

@require_member
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

@require_member
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

@require_member
async def wallet_menu(update, context):
    q = update.callback_query; await q.answer(); bal = get_balance(q.from_user.id)
    kb = [[InlineKeyboardButton("💳 افزایش موجودی", callback_data="charge_wallet")],
          [InlineKeyboardButton("📊 تاریخچه", callback_data="wallet_history")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"💰 **کیف پول:** {bal:,} تومان", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
async def charge_wallet(update, context):
    q = update.callback_query; await q.answer()
    kb = [[InlineKeyboardButton(f"{n:,} تومان", callback_data=f"charge_{n}")] for n in [50000,100000,200000,500000]]
    kb.append([InlineKeyboardButton("📝 مبلغ دلخواه", callback_data="charge_custom")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")])
    await q.edit_message_text("💳 **افزایش موجودی**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
async def charge_amount(update, context):
    q = update.callback_query; await q.answer()
    amount = int(q.data.replace("charge_", ""))
    kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"charge_receipt_{amount}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text(f"💳 **{amount:,} تومان**\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
async def charge_custom(update, context):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "type": "charge_custom"}; save_pending(p)
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text("📝 **مبلغ دلخواه (فقط عدد):**", reply_markup=InlineKeyboardMarkup(kb))

@require_member
async def charge_receipt_step(update, context):
    q = update.callback_query; await q.answer()
    amount = int(q.data.replace("charge_receipt_", ""))
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "type": "charge", "amount": amount}; save_pending(p)
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text(f"📸 **رسید ({amount:,} تومان) رو بفرستید:**", reply_markup=InlineKeyboardMarkup(kb))

@require_member
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

@require_member
async def buy_config(update, context):
    q = update.callback_query; await q.answer()
    kb = [[InlineKeyboardButton(f"📦 {v['name']} — {v['price']} 🛡️", callback_data=f"config_{k}")] for k,v in CONFIG_PLANS.items()]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await q.edit_message_text("📦 **انتخاب پلن:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
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

@require_member
async def pay_config(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_config_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_{pid}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"💳 **{plan['price']} تومان**\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
async def receipt_received(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("receipt_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "plan": pid, "type": "config"}; save_pending(p)
    await q.edit_message_text("📸 **رسید رو بفرستید:**")

@require_member
async def pay_wallet_config(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_wallet_config_", ""); plan = CONFIG_PLANS.get(pid)
    if not plan: return
    uid = q.from_user.id
    if not spend_balance(uid, plan["price_int"]):
        await q.edit_message_text("❌ موجودی کافی نیست!"); return
    p = load_pending(); p[str(uid)] = {"waiting": True, "type": "config_wallet_name", "plan": pid, "plan_data": plan}; save_pending(p)
    await q.edit_message_text(f"✅ **{plan['price']} تومان کسر شد!**\n\n📝 **اسمتون رو بفرستید:**")

@require_member
async def buy_express(update, context):
    q = update.callback_query; await q.answer()
    kb = [[InlineKeyboardButton(f"⏰ {v['name']} — {v['price']} 🛡️", callback_data=f"express_{k}")] for k,v in EXPRESS_PLANS.items()]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await q.edit_message_text("🔐 **ExpressVPN**\n\n• Killswitch\n• ۳۰۰ سرور از ۱۰۰ کشور\n• مناسب گیمینگ\n\n**انتخاب پلن:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
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

@require_member
async def pay_express(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("pay_express_", ""); plan = EXPRESS_PLANS.get(pid)
    if not plan: return
    kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_express_{pid}")],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"💳 **{plan['price']} تومان**\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

@require_member
async def receipt_express_received(update, context):
    q = update.callback_query; await q.answer()
    pid = q.data.replace("receipt_express_", ""); plan = EXPRESS_PLANS.get(pid)
    if not plan: return
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "plan": pid, "type": "express"}; save_pending(p)
    await q.edit_message_text("📸 **رسید رو بفرستید:**")

@require_member
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
        await _admin_send(context,
            text=f"💰 **خرید ExpressVPN از کیف پول!**\n\n👤 {q.from_user.first_name} (@{q.from_user.username or ''})\n🆔 {uid}\n📦 {plan['name']}\n💰 {plan['price']} تومان\n\nلطفاً اشتراک رو بفرستید.",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except: pass
    kb2 = [[InlineKeyboardButton("🏠 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(f"✅ **پرداخت موفق!** {plan['price']} تومان کسر شد.\n\n⏳ سفارش شما ثبت شد. به زودی اشتراک به پنل کاربری شما اضافه می‌شود!", reply_markup=InlineKeyboardMarkup(kb2), parse_mode="Markdown")

@require_member
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
          [InlineKeyboardButton("🎫 پشتیبانی", web_app=WebAppInfo(url=support_url(uid)))],
          [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ─── Receipt & Text Handlers ─────────────────────────────
async def handle_photo(update, context):
    touch_user(update.effective_user)
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
        try: await _admin_photo(context, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
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
    try: await _admin_photo(context, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except: pass
    await update.message.reply_text("✅ رسید دریافت شد!")

async def handle_text(update, context):
    touch_user(update.effective_user)
    uid = str(update.effective_user.id); p = load_pending(); key = uid; state = p.get(uid)
    # ادمین دیگه‌ای ممکنه این درخواستِ تحویل رو زیر کلید خودش ذخیره کرده باشه
    if (not state or not state.get("waiting")) and _is_admin(uid):
        for _k, _v in p.items():
            if isinstance(_v, dict) and _v.get("waiting_admin"):
                state = _v; key = _k; break
    # Admin sending subscription/config link — check FIRST
    if state and state.get("waiting_admin"):
        # پاسخ پشتیبانی: باید قبل از شاخهٔ «لینک اشتراک» جدا بشه
        if state.get("type") == "ticket_reply":
            tid = str(state.get("tid", "")); target = str(state.get("user_id", ""))
            reply = update.message.text.strip()[:2000]
            if not reply:
                await update.message.reply_text("❌ متن خالی است."); return
            del p[key]; save_pending(p)
            _by = admin_name(key, getattr(update.effective_user, "first_name", "") or "")
            _ticket_reply(tid, target, reply, _by)
            try:
                await update.message.reply_text(f"✅ پاسخ تیکت #{tid} برای کاربر ارسال شد.")
            except Exception: pass
            _tg_send(target, f"📩 **پاسخ { _by }** (تیکت #{tid}):\n\n{reply}")
            return
        admin_type = state["type"]; target_user = state["user_id"]
        link = update.message.text.strip()
        del p[key]; save_pending(p)
        configs = load_configs(); k = str(target_user)
        if k not in configs: configs[k] = []
        configs[k].append({"type": TYPE_LABELS.get(admin_type, admin_type), "data": state.get("plan", ""), "link": link[:300]})
        save_configs(configs)
        try: _ensure_pending_order(str(target_user), admin_type, state.get("plan", ""))
        except Exception: pass
        try: mark_order_sent(str(target_user), link, kind=_kind_from_type(admin_type))
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
    if state["type"] == "ticket":
        txt = update.message.text.strip()[:1000]
        if len(txt) < 3:
            await update.message.reply_text("❌ متن تیکت کوتاه است؛ کمی توضیح بده."); return
        del p[uid]; save_pending(p)
        found = _open_ticket_for(str(uid))
        if found:
            tid, _t = found
            _ticket_push(tid, txt, "user")
            _m = (load_tickets().get(tid) or {}).get("messages") or []
            if len(_m) >= 2 and _m[-2].get("from") == "admin":
                notify_admins_ticket(tid)
            await update.message.reply_text(
                f"📩 پیامت به گفتگوی تیکت **#{tid}** اضافه شد.\nپاسخ پشتیبانی همین‌جا میاد.",
                parse_mode="Markdown")
            return
        tid = create_ticket(uid, update.effective_user, txt, "bot")
        await update.message.reply_text(
            f"🎫 تیکت شما ثبت شد — شماره **#{tid}**\n\nپاسخ پشتیبانی رو همین‌جا دریافت میکنی. ممنون از صبرت 🙌",
            parse_mode="Markdown")
        notify_admins_ticket(tid)
        return
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
                await _admin_send(context,
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
            await _admin_send(context,
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
    try:
        _n = _receipts_resolve(user_id, ptype)
        if _n == 0:
            _rs = [rc for rc in load_receipts().values() if isinstance(rc, dict)
                   and str(rc.get("uid")) == str(user_id)
                   and ptype in str(rc.get("ptype") or "")]
            if _rs and all(rc.get("status") == "done" for rc in _rs):
                # قبلاً توسط ادمین دیگه‌ای رسیدگی شده — دوباره اعمال نکن
                await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n✅ قبلاً تایید شد!", parse_mode="Markdown")
                return
    except Exception:
        pass
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
        await _admin_send(context, text=f"📝 **لینک ExpressVPN رو بفرست:**\n\n👤 {user_id}", parse_mode="Markdown")
    await q.edit_message_caption(caption=q.message.caption + "\n\n✅ تایید شد!", parse_mode="Markdown")

async def reject_receipt(update, context):
    q = update.callback_query; await q.answer()
    user_id = int(q.data.split("_")[1])
    try: _receipts_resolve(user_id)
    except Exception: pass
    await context.bot.send_message(chat_id=user_id, text="❌ رسید تایید نشد.\nبا پشتیبانی تماس بگیرید.")
    await q.edit_message_caption(caption=q.message.caption + "\n\n❌ رد شد!", parse_mode="Markdown")


async def _admin_send(context, text, reply_markup=None, parse_mode="Markdown"):
    """فرستادن پیام به همهٔ ادمین‌ها"""
    for a in admin_uids():
        try:
            await context.bot.send_message(chat_id=int(a), text=text,
                                           reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass

async def _admin_photo(context, photo, caption, reply_markup=None, parse_mode="Markdown"):
    """فرستادن عکس (+دکمه‌ها) به همهٔ ادمین‌ها"""
    for a in admin_uids():
        try:
            await context.bot.send_photo(chat_id=int(a), photo=photo, caption=caption,
                                         reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass

def _notify_admin(text):
    """Send notification to ALL admins via Telegram HTTP API (thread-safe)"""
    for _a in admin_uids():
        try:
            import httpx
            httpx.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": int(_a), "text": text, "parse_mode": "Markdown"},
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
    import hashlib as _hashlib
    raw = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    build = _hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    html = raw
    for i, label in enumerate(["روز", "ساعت", "دقیقه", "ثانیه"]):
        pos = html.find(label)
        if pos > 0:
            before = html.rfind(">00</div>", 0, pos)
            if before > 0:
                html = html[:before + 1] + str(vals[i]).zfill(2) + html[before + 3:]
    html = html.replace("window.__V='000000000000'", "window.__V='" + build + "'", 1)
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

def _orders_with_expiry(uid):
    """سفارش‌ها + تاریخ انقضای هرکدام (برای نمایش در پنل کاربری)"""
    lst = _orders_with_heal(uid)
    for it in lst:
        if isinstance(it, dict):
            it["expires"] = _order_expiry(it)
    return lst

def _cfgs_with_expiry(uid):
    """لینک‌های اشتراک کاربر + انقضای سفارش مربوطه (تطبیق از روی لینک)"""
    try:
        cfgs = [dict(c) for c in (load_configs().get(uid, []) or [])]
    except Exception:
        return []
    by_link = {}
    for it in (_orders_with_heal(uid) or []):
        if isinstance(it, dict) and it.get("link"):
            by_link[str(it.get("link"))] = _order_expiry(it)
    for c in cfgs:
        c["expires"] = by_link.get(str(c.get("link") or ""), 0)
    return cfgs

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
    _ui = load_users().get(str(uid), {}) or {}
    return web.json_response({
        "balance": get_balance(uid),
        "referral_count": get_referral_count(int(uid)),
        "free_done": has_free_sub(int(uid)),
        "configs": _cfgs_with_expiry(uid),
        "history": load_wallet().get(uid, {}).get("history", [])[-10:],
        "card_number": CARD_NUMBER, "card_name": CARD_NAME,
        "referral_target": REFERRAL_TARGET, "bot_username": "Diazpshopbot",
        "referral_earned": referral_earned(uid), "referral_percent": REFERRAL_PERCENT,
        "name": _ui.get("first_name", "") or "",
        "username": _ui.get("username", "") or "",
        "is_member": is_member,
        "orders": _orders_with_expiry(uid),
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
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
    plan = CONFIG_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    _blk = _plan_block(plan)
    if _blk:
        return web.json_response({"error": _blk}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method, consume=(method != "wallet"))
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "موجودی کافی نیست"}, status=400)
        _code_consume(data.get("code"))
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
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
    plan = EXPRESS_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    _blk = _plan_block(plan)
    if _blk:
        return web.json_response({"error": _blk}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method, consume=(method != "wallet"))
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "موجودی کافی نیست"}, status=400)
        _code_consume(data.get("code"))
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_express", "user_id": uid, "plan": plan_id}
        save_pending(p)
        _notify_admin(f"⚡ **سفارش ExpressVPN (مینی\u200cاپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "express", plan_id, plan["name"], plan["price_int"])
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid"})


    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

# ─── API: Buy GTA VI ─────────────────────────────────────
async def api_buy_gta(request):
    data = await request.json()
    uid = data.get("uid")
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
    if not uid: return web.json_response({"error": "uid required"})
    uid = str(uid)
    plan = dict(SPECIAL_PLANS["gta"])
    _blk = _plan_block(plan)
    if _blk:
        return web.json_response({"error": _blk}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, "wallet", consume=False)
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if not spend_balance(int(uid), plan["price_int"]):
        return web.json_response({"error": "موجودی کافی نیست"}, status=400)
    _code_consume(data.get("code"))
    p = load_pending()
    p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_gta", "user_id": uid, "plan": plan["name"]}
    save_pending(p)
    _notify_admin(f"🎮 **سفارش GTA VI (مینی\u200cاپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔑 ظرفیت هوم رو بفرستید:")
    try: add_order(uid, "special", "gta", plan["name"], plan["price_int"])
    except Exception: pass
    return web.json_response({"ok": True, "action": "wallet_paid"})

async def api_buy_deezer(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
    plan = DEEZER_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    _blk = _plan_block(plan)
    if _blk:
        return web.json_response({"error": _blk}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method, consume=(method != "wallet"))
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "موجودی کافی نیست"}, status=400)
        _code_consume(data.get("code"))
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
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
    plan = SPOTIFY_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    _blk = _plan_block(plan)
    if _blk:
        return web.json_response({"error": _blk}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method, consume=(method != "wallet"))
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "موجودی کافی نیست"}, status=400)
        _code_consume(data.get("code"))
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_spotify", "user_id": uid, "plan": plan["name"]}
        save_pending(p)
        _notify_admin(f"🎧 **سفارش Spotify (مینی‌اپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "music", plan_id, plan["name"], plan["price_int"])
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

def _valid_email(s):
    try:
        import re as _re
        return bool(_re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", s or ""))
    except Exception:
        return False

async def api_buy_ai(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
    plan = AI_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    _blk = _plan_block(plan)
    if _blk:
        return web.json_response({"error": _blk}, status=400)
    email = str(data.get("email") or "").strip()
    if str(plan.get("brand", "")) == "gemini" and not _valid_email(email):
        return web.json_response({"error": "📧 ایمیل فعال‌سازی جمنا رو درست وارد کن"}, status=400)
    try: plan = _apply_code(plan, data.get("code"), uid, method, consume=(method != "wallet"))
    except ValueError as _e: return web.json_response({"error": str(_e)}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "موجودی کافی نیست"}, status=400)
        _code_consume(data.get("code"))
        p = load_pending()
        p[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_ai", "user_id": uid, "plan": plan["name"], "email": email}
        save_pending(p)
        _notify_admin(f"🤖 **سفارش هوش مصنوعی (مینی‌اپ)**\n\n👤 کاربر: {uid}\n📦 پلن: {plan['name']}\n💰 {plan['price']} تومان"
                      + (f"\n📧 ایمیل فعال‌سازی: `{email}`" if email else "")
                      + "\n\n🔗 لینک اشتراک رو بفرستید:")
        try: add_order(uid, "ai", plan_id, plan["name"], plan["price_int"], email=email)
        except Exception: pass
        return web.json_response({"ok": True, "action": "wallet_paid", "email": email})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME, "email": email})

async def api_wallet_charge(request):
    data = await request.json()
    uid = data.get("uid"); amount = data.get("amount", 0)
    if not await _member_ok(uid):
        return web.json_response({"error": "member_required", "message": "📢 member_required"}, status=403)
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

BUILD_TAG = "2026-09-30-jobs"   # تگ نسخهٔ دیپلوی — از /api/status خوانده میشه

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
    return web.json_response({"ok": _status_cache["ok"], "ms": _status_cache["ms"],
                              "ts": int(time.time()), "shop_origin": SHOP_ORIGIN, "build": BUILD_TAG})

# ─── ADMIN PANEL API (پنل مدیریت — فقط مالک) ──────────────
import hmac as _hmac, hashlib as _hashlib, asyncio as _asyncio

ADMIN_UID = int(os.environ.get("ADMIN_UID", str(OWNER_ID)))
DISCOUNTS_FILE = "discounts.json"
def load_discounts(): return _load(DISCOUNTS_FILE)
def save_discounts(d): _save(DISCOUNTS_FILE, d)

ADMINS_FILE = "admins.json"  # ادمین‌های اضافه (علاوه بر مالک) — از پنل افزوده/حذف می‌شوند
def load_admins(): return _load(ADMINS_FILE)
def save_admins(d): _save(ADMINS_FILE, d)

def admin_uids():
    """همهٔ uid هایی که دسترسی ادمین دارن: مالک + ADMIN_UIDS از env + لیست پنل"""
    ids = {str(OWNER_ID)}
    try:
        for x in str(os.environ.get("ADMIN_UIDS", "")).split(","):
            x = x.strip()
            if x.isdigit(): ids.add(x)
    except Exception: pass
    try: ids |= {str(k) for k in load_admins().keys()}
    except Exception: pass
    return {i for i in ids if i}

def _is_admin(uid): return str(uid) != "" and str(uid) in admin_uids()

OWNER_NAME = str(os.environ.get("ADMIN_OWNER_NAME", "Arat"))  # اسم مالک زیر جواب‌ها

def admin_name(uid="", explicit=""):
    """اسمی که زیر جواب ادمین توی چت مشتری نوشته میشه.

    اولویت: نامِ ثبت‌شده برای uid → اسم مالک → اسمی که پنل فرستاده → Diaz support
    """
    u = str(uid or "").strip()
    if u:
        try:
            a = load_admins().get(u)
            if isinstance(a, dict) and str(a.get("name") or "").strip():
                return str(a["name"]).strip()[:40]
        except Exception:
            pass
        if u == str(OWNER_ID):
            return OWNER_NAME
    nm = str(explicit or "").strip()
    if nm:
        return nm[:40]
    return "Diaz support"

USERS_FILE = "users.json"   # رجیستری همهٔ کاربرانی که /start زدن (برای پیام همگانی)
def load_users(): return _load(USERS_FILE)
def save_users(d): _save(USERS_FILE, d)

def touch_user(user):
    """هر کاربری که با ربات حرف زد اینجا ثبت می‌شود — تا پیام همگانی به همه برسد."""
    if not user: return
    try:
        us = load_users(); k = str(user.id)
        cur = us.get(k) if isinstance(us.get(k), dict) else {}
        cur.update({"first_name": user.first_name or cur.get("first_name", ""),
                    "username": user.username or cur.get("username", ""),
                    "first_seen": cur.get("first_seen") or time.time(),
                    "last_seen": time.time()})
        us[k] = cur; save_users(us)
    except Exception as e:
        logger.warning(f"touch_user: {e}")

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

def _code_consume(code):
    """ثبت مصرف کد تخفیف — فقط بعد از پرداخت موفق."""
    code = (code or "").strip().lower()
    if not code: return
    ds = load_discounts(); d = ds.get(code)
    if not d: return
    d["used"] = int(d.get("used", 0)) + 1
    ds[code] = d; save_discounts(ds)

def _apply_code(plan, code, uid=None, method="wallet", consume=True):
    """نسخه‌ تخفیف‌خوردهٔ پلن. کد نامعتبر → ValueError. مصرف کد فقط بعد از پرداخت موفق ثبت می‌شود."""
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
    if consume:
        _code_consume(code)
    out = dict(plan); out["price_int"] = final; out["price"] = _fa(final); out["discount"] = code
    return out

def _all_uids():
    u = set()
    for d in (load_wallet(), load_configs(), load_orders(), load_users()):
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
    """آیا این uid دسترسی ادمین دارد؟ (بدون لو دادن شناسه‌ها)"""
    uid = str(request.query.get("uid", ""))
    return web.json_response({"ok": _is_admin(uid)})

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
    w = load_wallet(); c = load_configs(); o = load_orders(); us_r = load_users()
    users = []
    for uid in _all_uids():
        _u = us_r.get(uid) or {}
        users.append({
            "uid": uid,
            "name": _u.get("first_name", "") or "",
            "username": _u.get("username", "") or "",
            "is_admin": _is_admin(uid),
            "balance": int(w.get(uid, {}).get("balance", 0)) if isinstance(w.get(uid), dict) else 0,
            "subs": len(c.get(uid, []) or []),
            "orders": len(o.get(uid, []) or []),
        })
    users.sort(key=lambda x: -x["orders"])
    return web.json_response({"users": users})

async def admin_expiry_scan(request):
    """اجرای دستی اسکن انقضا + گزارش سفارش‌های نزدیک به انقضا.
    با {"preview_uid": "..."} یه پیش‌نمایش از متن یادآوری براش میفرسته (برای تست)."""
    err = _denied(request)
    if err: return err
    try: data = await request.json()
    except Exception: data = {}
    pv = str((data or {}).get("preview_uid", "") or "")
    if pv.isdigit():
        txt = ("🧪 **پیش‌نمایش یادآوری انقضا**\n\n"
               "⏳ **اشتراک داره تموم میشه!**\n\n"
               "📦 نمونه اشتراک\n"
               "⏰ حدود **۱۲ ساعت** دیگه انقضا\n\n"
               "از 👤 پنل کاربری مینی‌اپ تمدیدش کن تا قطع نشه.")
        try:
            import httpx as _hx
            _r = _hx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": int(pv), "text": txt, "parse_mode": "Markdown"}, timeout=15)
            _j = _r.json()
            return web.json_response({"ok": True, "delivered": bool(_j.get("ok")),
                                      "detail": _j.get("description", "sent")})
        except Exception as _e:
            return web.json_response({"ok": False, "error": str(_e)}, status=502)
    now = int(time.time()); near = []
    o = load_orders()
    for uid, lst in o.items():
        if not str(uid).isdigit() or not isinstance(lst, list): continue
        for it in lst:
            if not isinstance(it, dict) or it.get("status") != "sent": continue
            exp = _order_expiry(it)
            if not exp: continue
            left = exp - now
            if left <= 0: continue
            if left <= 86400 and not it.get("reminded"):
                near.append({"uid": uid, "name": it.get("name", ""), "hours": int(left // 3600)})
    sent_n = _expiry_reminder_scan()
    return web.json_response({"ok": True, "reminded_now": sent_n, "near": near[:50], "near_count": len(near)})

async def admin_admins_list(request):
    err = _denied(request)
    if err: return err
    us_r = load_users(); out = []
    for a in sorted(admin_uids(), key=lambda x: 0 if x == str(OWNER_ID) else 1):
        u = us_r.get(a) or {}
        out.append({"uid": a, "owner": a == str(OWNER_ID),
                    "name": u.get("first_name", ""), "username": u.get("username", "")})
    return web.json_response({"admins": out})

async def admin_admin_save(request):
    """افزودن/حذف ادمین — هر ادمینی دسترسی دارد"""
    err = _denied(request)
    if err: return err
    data = await request.json()
    uid = str(data.get("uid", "")).strip()
    if not uid.isdigit():
        return web.json_response({"error": "uid نامعتبر"}, status=400)
    if uid == str(OWNER_ID):
        return web.json_response({"error": "دسترسی مالک رو نمیشه تغییر داد"}, status=400)
    adm = load_admins()
    if data.get("on"):
        if uid in adm:
            return web.json_response({"ok": True, "admins": sorted(admin_uids())})
        adm[uid] = {"added_ts": int(time.time())}
        _nm = str(data.get("name") or "").strip()
        if _nm:
            adm[uid]["name"] = _nm[:40]
        save_admins(adm)
        _tg_send(uid, "🛡️ شما به عنوان **ادمین** به پنل فروشگاه اضافه شدید.\n\nبرای ورود: پنل کاربری → 🛠️ پنل مدیریت (همون رمز ادمین).")
        logger.info(f"admin added: {uid}")
        return web.json_response({"ok": True, "added": uid, "admins": sorted(admin_uids())})
    adm.pop(uid, None)
    save_admins(adm)
    _tg_send(uid, "🛑 دسترسی ادمین شما برداشته شد.")
    logger.info(f"admin removed: {uid}")
    return web.json_response({"ok": True, "removed": uid, "admins": sorted(admin_uids())})

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
    out = []
    now = time.time()
    for rec in _flat_orders()[:200]:
        r = dict(rec)
        try:
            r["expires"] = _order_expiry(r)
            r["days_left"] = max(0, int((r["expires"] - now) // 86400)) if r.get("expires") else 0
        except Exception:
            r["expires"] = 0; r["days_left"] = 0
        out.append(r)
    return web.json_response({"orders": out})

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


BC_STATUS = {"running": False, "targets": 0, "sent": 0, "failed": 0, "ts": 0, "scope": ""}

async def _broadcast_run(uids, text):
    """در بک‌گراند می‌فرستد تا درخواست وب معطل نماند (و ربات قفل نشود)."""
    sent = failed = 0
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            for u in uids:
                try:
                    r = await hc.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                      json={"chat_id": int(u), "text": text})
                    if r.json().get("ok"): sent += 1
                    else: failed += 1
                except Exception:
                    failed += 1
                BC_STATUS.update({"sent": sent, "failed": failed})
                await _asyncio.sleep(0.05)
    except Exception as e:
        logger.warning(f"broadcast: {e}")
    BC_STATUS.update({"running": False, "sent": sent, "failed": failed, "ts": int(time.time())})
    logger.info(f"broadcast done: sent={sent} failed={failed}")

async def admin_broadcast(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    text = str(data.get("text", "")).strip()
    scope = str(data.get("scope", "all"))
    if not text: return web.json_response({"error": "متن خالی است"}, status=400)
    if BC_STATUS.get("running"):
        return web.json_response({"error": "یک ارسال دیگه در جریانه — صبر کن"}, status=409)
    uids = _all_uids()
    if scope == "buyers":
        o = load_orders(); uids = [u for u in uids if o.get(u)]
    if not uids:
        return web.json_response({"error": "گیرنده‌ای وجود نداره (هنوز کسی با ربات شروع نکرده)"}, status=400)
    BC_STATUS.update({"running": True, "targets": len(uids), "sent": 0, "failed": 0,
                      "ts": int(time.time()), "scope": scope})
    _asyncio.get_event_loop().create_task(_broadcast_run(uids[:3000], text))
    return web.json_response({"ok": True, "targets": len(uids), "running": True})

async def admin_broadcast_status(request):
    err = _denied(request)
    if err: return err
    return web.json_response(dict(BC_STATUS))

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

async def api_build(request):
    import hashlib as _hashlib
    raw = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return web.json_response({"build": _hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]})

def create_web_app():
    app = web.Application()
    app.router.add_get("/", serve_index)
    app.router.add_get("/api/build", api_build)
    app.router.add_get("/api/ui", api_ui)
    app.router.add_get("/api/ui_img", api_ui_img)
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
    app.router.add_post("/api/admin/plan_add", admin_plan_add)
    app.router.add_post("/api/admin/plan_del", admin_plan_del)
    app.router.add_get("/api/admin/admins", admin_admins_list)
    app.router.add_post("/api/admin/expiry_scan", admin_expiry_scan)
    app.router.add_post("/api/admin/admin_save", admin_admin_save)
    app.router.add_get("/api/admin/subs", admin_subs)
    app.router.add_post("/api/admin/sub", admin_sub_action)
    app.router.add_get("/api/admin/requests", admin_requests)
    app.router.add_post("/api/admin/request", admin_request_action)
    app.router.add_post("/api/admin/ui", admin_ui_save)
    app.router.add_post("/api/admin/order", admin_order_action)
    app.router.add_post("/api/admin/user_delete", admin_user_delete)
    app.router.add_get("/api/announcement", api_announcement)
    app.router.add_get("/api/faq", api_faq)
    app.router.add_post("/api/admin/faq", admin_faq)
    app.router.add_post("/api/ticket", api_ticket_new)
    app.router.add_get("/api/ticket", api_ticket_get)
    app.router.add_post("/api/admin/announcement", admin_announcement_save)
    app.router.add_get("/api/admin/tickets", admin_tickets)
    app.router.add_post("/api/admin/ticket_reply", admin_ticket_reply)
    app.router.add_post("/api/admin/ticket_close", admin_ticket_close)
    app.router.add_post("/api/discount_preview", discount_preview)
    app.router.add_post("/api/buy_gta", api_buy_gta)
    app.router.add_get("/api/admin/broadcast/status", admin_broadcast_status)
    # Static files — must come AFTER specific routes
    app.router.add_get("/{name:.*}", serve_static)
    return app

# ─── Admin panel: plan overrides / subscriptions / requests ────────────
PLAN_OVERRIDES_FILE = "plan_overrides.json"
RECEIPTS_FILE = "receipts.json"
REPORT_STATE_FILE = "daily_report_state.json"

def load_plan_overrides(): return _load(PLAN_OVERRIDES_FILE)
def save_plan_overrides(d): _save(PLAN_OVERRIDES_FILE, d)
CUSTOM_PLANS_FILE = "custom_plans.json"

def load_custom_plans(): return _load(CUSTOM_PLANS_FILE)
def save_custom_plans(d): _save(CUSTOM_PLANS_FILE, d)

_CUSTOM_ADDED = set()   # (kind, key) که از استور سفارشی تزریق شده

def apply_custom_plans():
    """آیتم‌های سفارشی ادمین رو داخل جدول‌های زنده می‌شینونه؛ حذف‌شده‌ها رو جمع می‌کنه."""
    store = load_custom_plans()
    if not isinstance(store, dict): store = {}
    for (kind, key) in list(_CUSTOM_ADDED):
        table = PLAN_KINDS.get(kind)
        if table is None: continue
        if key not in (store.get(kind) or {}):
            table.pop(key, None)
            _CUSTOM_ADDED.discard((kind, key))
    n = 0
    for kind, items in store.items():
        table = PLAN_KINDS.get(kind)
        if not isinstance(table, dict) or not isinstance(items, dict): continue
        for key, o in items.items():
            if not isinstance(o, dict): continue
            try: pi = max(0, int(o.get("price_int") or 0))
            except Exception: pi = 0
            d = {"name": str(o.get("name") or key), "price_int": pi,
                 "price": _fa(pi), "custom": True}
            if o.get("days") is not None:
                try: d["days"] = int(o.get("days"))
                except Exception: pass
            for f in ("data", "duration", "limit_gb", "brand", "icon"):
                v = o.get(f)
                if v not in (None, ""): d[f] = v
            table[key] = d
            _CUSTOM_ADDED.add((kind, key))
            n += 1
    if n: logger.info(f"custom plans applied: {n}")
    return n
def load_receipts(): return _load(RECEIPTS_FILE)
def save_receipts(d): _save(RECEIPTS_FILE, d)

PLAN_KINDS = {"config": CONFIG_PLANS, "express": EXPRESS_PLANS, "deezer": DEEZER_PLANS,
              "ai": AI_PLANS, "spotify": SPOTIFY_PLANS, "special": SPECIAL_PLANS}

TYPE_LABELS = {
    "send_config": "📦 کانفیگ VPN", "send_express": "⚡ ExpressVPN",
    "send_deezer": "🎵 Deezer", "send_spotify": "🎧 Spotify",
    "send_ai": "🤖 هوش مصنوعی", "send_gta": "🎮 GTA VI",
    "charge": "💰 رسید شارژ کیف پول", "charge_custom": "💳 درخواست شارژ",
    "charge_receipt": "💳 رسید شارژ", "config_wallet_name": "📝 اسم کانفیگ",
    "config_receipt_name": "📝 اسم کانفیگ (پس از پرداخت)",
    "config": "📦 رسید کانفیگ", "express": "📸 رسید ExpressVPN",
}

def _plan_block(plan):
    """اگه پلن الان قابل خرید نباشه، متن دلیل برمی‌گردونه، وگرنه None."""
    if not isinstance(plan, dict):
        return None
    if plan.get("active") is False:
        return "این پلن موقتاً غیرفعال است"
    if plan.get("out"):
        return "این پلن اتمام موجودیه"
    return None

def apply_plan_overrides():
    try:
        apply_custom_plans()   # اول آیتم‌های سفارشی، بعد قیمت/وضعیت روی همون‌ها
    except Exception as e:
        logger.warning(f"custom plans error: {e}")
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
            opi = o.get("old_price_int")
            if isinstance(opi, int) and opi >= 0:
                if opi > 0:
                    t["old_price_int"] = opi
                else:
                    t.pop("old_price_int", None)
            t["active"] = bool(o.get("active", True))
            t["out"] = bool(o.get("out"))
            if "icon" in o:
                ic = str(o.get("icon") or "").strip()[:300]
                if ic: t["icon"] = ic
                else: t.pop("icon", None)
            n += 1
    logger.info(f"plan overrides applied: {n}")

def _plan_state(kind, key):
    t = PLAN_KINDS.get(kind, {}).get(key)
    if not isinstance(t, dict):
        return None
    return {"key": key, "name": t.get("name", key), "price": t.get("price", ""),
            "price_int": t.get("price_int", 0), "old_price_int": t.get("old_price_int", 0),
            "active": t.get("active", True),
            "out": bool(t.get("out")), "custom": bool(t.get("custom")),
            "days": t.get("days"), "brand": t.get("brand"), "icon": t.get("icon")}

async def api_plans(request):
    """عمومی — مینی‌اپ قیمت/فعال بودن پلن‌ها رو از همین‌جا می‌گیره"""
    out = {}
    for kind, table in PLAN_KINDS.items():
        out[kind] = {k: {"price": v.get("price", ""), "price_int": v.get("price_int", 0),
                         "old_price_int": v.get("old_price_int", 0),
                         "active": v.get("active", True), "out": bool(v.get("out")),
                         "name": v.get("name", k), "custom": bool(v.get("custom")),
                         "days": v.get("days"), "brand": v.get("brand"), "icon": v.get("icon")}
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
    if "out" in data:
        cur["out"] = bool(data.get("out"))
    if data.get("price_int") is not None:
        try:
            p = int(data.get("price_int"))
        except Exception:
            return web.json_response({"error": "قیمت نامعتبر"}, status=400)
        if p < 0:
            return web.json_response({"error": "قیمت نامعتبر"}, status=400)
        cur["price_int"] = p
    if "old_price_int" in data:
        try:
            opi = int(data.get("old_price_int") or 0)
        except Exception:
            return web.json_response({"error": "قیمت قبل نامعتبر"}, status=400)
        if opi < 0:
            return web.json_response({"error": "قیمت قبل نامعتبر"}, status=400)
        cur["old_price_int"] = opi   # صفر = برداشتن حراج (در override هم ثبت میشه)
    if "icon" in data:
        cur["icon"] = str(data.get("icon") or "").strip()[:300]
    if data.get("name") is not None:
        nm = str(data.get("name") or "").strip()[:60]
        if not nm:
            return web.json_response({"error": "اسم خالی است"}, status=400)
        cst = load_custom_plans()
        if key in (cst.get(kind) or {}):
            cst[kind][key]["name"] = nm
            save_custom_plans(cst)
    slot[key] = cur
    save_plan_overrides(ov)
    apply_plan_overrides()
    return web.json_response({"ok": True, "plan": _plan_state(kind, key)})

async def admin_plan_add(request):
    """افزودن آیتم/پلن جدید از پنل ادمین"""
    err = _denied(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "bad request"}, status=400)
    kind = str(data.get("kind", ""))
    if kind not in PLAN_KINDS:
        return web.json_response({"error": "دسته‌بندی نامعتبر است"}, status=400)
    name = str(data.get("name") or "").strip()[:60]
    if not name:
        return web.json_response({"error": "اسم آیتم را وارد کنید"}, status=400)
    try:
        pi = int(data.get("price_int"))
    except Exception:
        return web.json_response({"error": "قیمت نامعتبر است"}, status=400)
    if pi < 0:
        return web.json_response({"error": "قیمت نامعتبر است"}, status=400)
    store = load_custom_plans()
    if not isinstance(store, dict): store = {}
    slot = store.setdefault(kind, {})
    key = "c" + _secrets.token_hex(3)
    while key in PLAN_KINDS[kind] or key in slot:
        key = "c" + _secrets.token_hex(3)
    entry = {"name": name, "price_int": pi, "ts": int(time.time())}
    for f in ("days", "limit_gb"):
        if data.get(f) not in (None, ""):
            try: entry[f] = max(0, int(data.get(f)))
            except Exception: return web.json_response({"error": f"{f} نامعتبر است"}, status=400)
    if "icon" in data:
        ic = str(data.get("icon") or "").strip()[:300]
        if ic: entry["icon"] = ic
    for f in ("data", "duration", "brand"):
        v = str(data.get(f) or "").strip()[:30]
        if v: entry[f] = v
    slot[key] = entry
    save_custom_plans(store)
    apply_plan_overrides()
    return web.json_response({"ok": True, "key": key, "plan": _plan_state(kind, key)})

async def admin_plan_del(request):
    """حذف آیتم ساخته‌شده توسط ادمین (پلن‌های پیش‌فرض فقط غیرفعال می‌شوند)"""
    err = _denied(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "bad request"}, status=400)
    kind = str(data.get("kind", "")); key = str(data.get("key", ""))
    if kind not in PLAN_KINDS:
        return web.json_response({"error": "دسته‌بندی نامعتبر است"}, status=400)
    store = load_custom_plans()
    if key not in (store.get(kind) or {}):
        return web.json_response({"error": "فقط آیتم‌های ساخته‌شده از پنل حذف می‌شوند"}, status=404)
    del store[kind][key]
    if not store.get(kind): store.pop(kind, None)
    save_custom_plans(store)
    ov = load_plan_overrides()
    if key in (ov.get(kind) or {}):
        ov.get(kind, {}).pop(key, None)
        if not ov.get(kind): ov.pop(kind, None)
        save_plan_overrides(ov)
    apply_plan_overrides()
    return web.json_response({"ok": True, "key": key})

# ─── Discount preview (مینی‌اپ قبل از پرداخت) ──────────────────────────
async def discount_preview(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "bad request"}, status=400)
    code = str(data.get("code", "")).strip().lower()
    kind = str(data.get("kind", "")); key = str(data.get("plan", ""))
    if not code:
        return web.json_response({"error": "کد تخفیف را وارد کنید"}, status=400)
    plan = PLAN_KINDS.get(kind, {}).get(key)
    if not plan:
        return web.json_response({"error": "پلن پیدا نشد"}, status=400)
    d = load_discounts().get(code)
    if not d or not d.get("active", True):
        return web.json_response({"error": "کد تخفیف معتبر نیست"}, status=400)
    if d.get("expires") and time.time() > float(d["expires"]):
        return web.json_response({"error": "کد تخفیف منقضی شده"}, status=400)
    if d.get("max_uses") and int(d.get("used", 0)) >= int(d["max_uses"]):
        return web.json_response({"error": "سقف استفاده از کد تخفیف تمام شده"}, status=400)
    price = int(plan.get("price_int", 0))
    off = price * int(d.get("value", 0)) // 100 if d.get("type") == "percent" else int(d.get("value", 0))
    final = max(0, price - off)
    return web.json_response({"ok": True, "code": code, "price_int": final, "price": _fa(final),
                              "type": d.get("type"), "value": int(d.get("value", 0)),
                              "save": price - final})

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
    now_ts = int(time.time())
    for rid, rc in load_receipts().items():
        if not isinstance(rc, dict):
            continue
        st = str(rc.get("status") or "")
        if st not in ("waiting", "done", "rejected"):
            continue
        if st != "waiting" and (now_ts - int(rc.get("done_ts") or 0)) > 900:
            continue        # رسید حل‌شده فقط ۱۵ دقیقه برای همه نشون داده میشه
        typ = str(rc.get("ptype") or "")
        items.append({"key": f"receipt:{rid}", "kind": "receipt", "type": typ,
                      "label": TYPE_LABELS.get(typ, "📸 رسید"), "user_id": str(rc.get("uid", "")),
                      "plan": rc.get("plan") or "", "amount": rc.get("amount", 0),
                      "price": rc.get("price", 0), "ts": rc.get("ts", 0),
                      "status": st, "by": str(rc.get("by") or "")})
    items.sort(key=lambda x: -x.get("ts", 0))
    return items

def _tg_send_md(uid, text, kb=None):
    """ارسال پیام مارکداون با دکمهٔ اختیاری — True اگه تلگرام قبول کرد (برای تست قابل جایگزینی)."""
    payload = {"chat_id": int(uid), "text": text, "parse_mode": "Markdown"}
    if kb is not None:
        try:
            payload["reply_markup"] = kb.to_dict() if hasattr(kb, "to_dict") else kb
        except Exception:
            pass
    try:
        import httpx as _hx
        _r = _hx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload, timeout=15)
        if bool(_r.json().get("ok")): return True
    except Exception as e:
        logger.warning(f"send failed ({uid}): {e}")
    try:  # تلاش دوم بدون مارکداون
        import httpx as _hx
        _r = _hx.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": int(uid), "text": text.replace("**", "")}, timeout=15)
        return bool(_r.json().get("ok"))
    except Exception:
        return False

# (کلید, حداکثر باقی‌مانده, حداقل باقی‌مانده) — سه مرحلهٔ یادآوری انقضا
_EXPIRY_STAGES = (("3d", 3 * 86400, 86400), ("1d", 86400, 6 * 3600), ("6h", 6 * 3600, 0))

def _expiry_stage_for(left):
    """کدام مرحله برای این باقی‌مانده فعاله (وگرنه None)."""
    if left <= 0: return None
    for key, hi, lo in _EXPIRY_STAGES:
        if lo < left <= hi: return key
    return None

def _expiry_reminder_text(it, stage, left):
    name = it.get("name", "") or "اشتراک"
    if stage == "3d":
        head = f"⏳ **۳ روز تا انقضای اشتراکت مونده**\n\n"
        when = f"⏰ حدود **{_fa(max(1, int(left // 86400)))} روز** دیگه منقضی میشه"
    elif stage == "1d":
        head = f"⚠️ **فردا اشتراکتم تموم میشه!**\n\n"
        when = f"⏰ حدود **{_fa(max(1, int(left // 3600)))} ساعت** دیگه منقضی میشه"
    else:
        head = f"🚨 **چند ساعت دیگه قطع میشه!**\n\n"
        when = f"⏰ حدود **{_fa(max(1, int(left // 3600)))} ساعت** دیگه منقضی میشه"
    return head + f"📦 {name}\n{when}\n\nبا دکمهٔ پایین تمدیدش کن تا قطع نشه."

def _renew_kb(uid):
    try:
        _t = int(time.time())
        return InlineKeyboardMarkup([[InlineKeyboardButton(
            "🔁 تمدید اشتراک", web_app=WebAppInfo(url=f"{SHOP_ORIGIN}/?uid={uid}&t={_t}&sec=panel"))]])
    except Exception:
        return None

def _expiry_reminder_scan():
    """یادآوری انقضا در سه مرحله: ۳ روز، ۱ روز و ۶ ساعت مانده — هر مرحله فقط یک بار."""
    now = int(time.time()); changed = False; sent_n = 0
    o = load_orders()
    for uid, lst in list(o.items()):
        if not str(uid).isdigit() or not isinstance(lst, list): continue
        for it in lst:
            if not isinstance(it, dict) or it.get("status") != "sent": continue
            exp = _order_expiry(it)
            if not exp: continue
            stage = _expiry_stage_for(exp - now)
            if not stage: continue
            done = [str(s) for s in (it.get("remind_stages") or [])]
            if it.get("reminded") and "1d" not in done:
                done.append("1d")   # یادآوری قدیمیِ ۲۴ ساعته معادل مرحلهٔ «۱ روز»
            if stage in done: continue
            left = exp - now
            ok = _tg_send_md(uid, _expiry_reminder_text(it, stage, left), _renew_kb(uid))
            if ok:
                done.append(stage)
                it["remind_stages"] = done
                it["remind_try"] = 0
                if stage == "6h": it["reminded"] = now
                sent_n += 1
            else:
                it["remind_try"] = int(it.get("remind_try", 0)) + 1
                if it["remind_try"] >= 3:      # بعد از ۳ تلاش همون مرحله رو رد کن
                    done.append(stage)
                    it["remind_stages"] = done
                    it["remind_try"] = 0
            changed = True
            logger.info(f"expiry reminder uid={uid} plan={it.get('name','')} stage={stage} ok={ok}")
    if changed:
        save_orders(o)
    return sent_n

TEH_OFFSET = 3 * 3600 + 1800          # تهران = UTC+3:30

def _teh_date(ts):
    g = time.gmtime(int(ts) + TEH_OFFSET)
    return f"{g.tm_year:04d}-{g.tm_mon:02d}-{g.tm_mday:02d}"

def _teh_midnight(ts):
    """نیمه‌شب به وقت تهرانِ همون روزِ ts (epoch)."""
    import calendar
    g = time.gmtime(int(ts) + TEH_OFFSET)
    return calendar.timegm((g.tm_year, g.tm_mon, g.tm_mday, 0, 0, 0)) - TEH_OFFSET

_KIND_FA = {"config": "کانفیگ VPN", "ai": "هوش مصنوعی", "music": "موزیک",
            "express": "اکسپرس", "deezer": "Deezer", "special": "محصول ویژه"}

def _build_daily_report(day_start, day_end):
    """متن گزارش فروش بازهٔ [day_start, day_end) — معمولاً دیروز به وقت تهران."""
    orders = [o for o in _flat_orders()
              if day_start <= int(o.get("ts", 0) or 0) < day_end and o.get("status") != "rejected"]
    total = sum(int(o.get("price", 0) or 0) for o in orders)
    by_kind = {}
    for o in orders:
        k = str(o.get("kind") or "دیگر")
        c, a = by_kind.get(k, (0, 0))
        by_kind[k] = (c + 1, a + int(o.get("price", 0) or 0))
    users = load_users()
    new_users = sum(1 for u in users.values()
                    if isinstance(u, dict) and day_start <= int(u.get("first_seen") or 0) < day_end)
    today_end = day_end + 86400
    expiring = 0
    for lst in load_orders().values():
        for it in (lst or []):
            if not isinstance(it, dict) or it.get("status") != "sent": continue
            e = _order_expiry(it)
            if e and day_end <= e < today_end: expiring += 1
    waiting = len([1 for v in load_pending().values()
                   if isinstance(v, dict) and v.get("waiting_admin")])
    L = ["", f"📊 **گزارش فروش {_teh_date(day_end - 1)}**", ""]
    if orders:
        L.append(f"📦 سفارش‌ها: **{_fa(len(orders))}**")
        L.append(f"💰 درآمد: **{_fa(total)} تومان**")
        for k, (c, a) in sorted(by_kind.items(), key=lambda x: -x[1][0]):
            L.append(f"   • {_KIND_FA.get(k, k)}: {_fa(c)} — {_fa(a)}")
    else:
        L.append("📦 سفارشی ثبت نشد")
    L.append(f"🆕 کاربر جدید: **{_fa(new_users)}**")
    L.append(f"⏳ انقضای امروز: **{_fa(expiring)}** اشتراک")
    if waiting:
        L.append(f"🔔 منتظر پاسخ شما: **{_fa(waiting)}** سفارش")
    return "\n".join(L)

def _daily_report_due(now):
    """گزارش امروز فقط یک بار و بعد از ساعت ۹ صبح به وقت تهران."""
    st = _load(REPORT_STATE_FILE) or {}
    if st.get("last_date") == _teh_date(now): return False
    return int(now) >= _teh_midnight(now) + 9 * 3600

def _daily_report_loop():
    """هر ۵ دقیقه: اگه ساعت ۹ صبح تهران رد شده و گزارش امروز نرفته، برای ادمین‌ها میفرسته."""
    time.sleep(60)
    while True:
        try:
            now = int(time.time())
            if _daily_report_due(now):
                y_start = _teh_midnight(now - 86400)
                _notify_admin(_build_daily_report(y_start, _teh_midnight(now)))
                _save(REPORT_STATE_FILE, {"last_date": _teh_date(now)})
                logger.info("daily report sent")
        except Exception as e:
            logger.warning(f"daily report: {e}")
        time.sleep(300)

def _expiry_reminder_loop():
    """هر ۵ دقیقه اسکن انقضا — از استارت ربات شروع میشه"""
    time.sleep(90)
    while True:
        try:
            _expiry_reminder_scan()
        except Exception as e:
            logger.warning(f"expiry scan: {e}")
        time.sleep(300)

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
    _ensure_pending_order(uid, ptype, plan_id)          # سفارش باید ثبت بشه
    _tg_send(uid, "✅ **پرداخت تایید شد!** به‌زودی لینک اشتراک ارسال می‌شود.")
    for _a in admin_uids():
        _tg_send(_a, f"📝 **لینک ExpressVPN رو بفرست**\n\n👤 {uid}")
    return "پرداخت تایید شد — لینک رو بفرست"

# ── ظاهر سایت (بنر، تیترها، رنگ‌ها، تم) ──────────────────────
UI_FILE = "bot_ui.json"
UI_SECTIONS = ("home", "ai", "vpn", "music", "games", "referral", "ticket", "wallet", "panel", "gtavi")
UI_DEFAULTS = {
    "banner_on": True, "banner_icon": "✨",
    "banner_title": "پلن فمیلی جدید",
    "banner_sub": "جمنای پرو فمیلی • نامحدود — ۱ ماهه، فقط ۸۰۰,۰۰۰ تومان",
    "banner_target": "ai", "banner_img": "",
    "gta_on": True, "gta_icon": "VI",
    "gta_title": "GTA VI پیش‌فروش", "gta_sub": "Ultimate Edition — ظرفیت هوم",
    "gta_target": "gtavi", "gta_img": "",
    "ref_on": True, "ref_icon": "🎁",
    "ref_title": "رفرال و هدیه", "ref_sub": "با هر خرید دوستت ۵٪ هدیه بگیر",
    "ref_target": "referral", "ref_img": "",
    "hero_title": "🕷️ Diaz Shop", "hero_sub": "فروشگاه دیجیتال دیاز", "hero_img": "",
    "accent1": "#7c3aed", "accent2": "#e23636",
    "theme": "dark",
}
IMG_KEYS = ("banner_img", "gta_img", "ref_img", "hero_img")
UI_IMG_CAP = 600000          # حداکثر طول data-URI عکس (بعد از فشرده‌سازی سمت مرورگر)
UI_ON_KEYS = ("banner_on", "gta_on", "ref_on")

def _img_ok(v):
    """خالی، لینک http(s)، یا data:image/...base64 — بقیه رد میشن."""
    v = str(v or "").strip()
    if v == "":
        return ""
    if v.startswith("data:image/") and ";base64," in v and len(v) <= UI_IMG_CAP:
        return v
    if v.startswith(("http://", "https://")) and len(v) <= 400:
        return v
    return None

def _hex6(v):
    v = str(v or "").strip()
    if len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return v.lower()
    return None

def load_ui():
    d = _load(UI_FILE)
    out = dict(UI_DEFAULTS)
    if isinstance(d, dict):
        for k in UI_DEFAULTS:
            if k in d:
                out[k] = d[k]
    return out

def save_ui(d):
    _save(UI_FILE, d)

async def api_ui(request):
    # عکس‌ها جدا فرستاده میشن تا بار صفحهٔ مشتری سبک بمونه
    u = load_ui()
    small = {k: v for k, v in u.items() if k not in IMG_KEYS}
    small["has_img"] = sorted([k for k in IMG_KEYS if u.get(k)])
    return web.json_response({"ok": True, "ui": small})

async def api_ui_img(request):
    u = load_ui()
    return web.json_response({"ok": True, "imgs": {k: u.get(k, "") for k in IMG_KEYS if u.get(k)}})

async def admin_ui_save(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    cur = load_ui()
    caps = {"banner_icon": 12, "gta_icon": 8, "ref_icon": 8,
            "banner_title": 60, "gta_title": 60, "ref_title": 60, "hero_title": 40,
            "banner_sub": 140, "gta_sub": 140, "ref_sub": 140, "hero_sub": 60}
    for k, cap in caps.items():
        if k in data:
            cur[k] = str(data.get(k) or "").strip()[:cap]
    for k in UI_ON_KEYS:
        if k in data:
            cur[k] = bool(data.get(k))
    for k in IMG_KEYS:
        if k in data:
            ok_v = _img_ok(data.get(k))
            if ok_v is None:
                return web.json_response({"error": "عکس نامعتبره (لینک http یا عکس انتخاب‌شده لازمه)"}, status=400)
            cur[k] = ok_v
    for tgt in ("banner_target", "gta_target", "ref_target"):
        if tgt in data and str(data.get(tgt)) in UI_SECTIONS:
            cur[tgt] = str(data[tgt])
    if "theme" in data and str(data.get("theme")) in ("dark", "light"):
        cur["theme"] = str(data["theme"])
    for k in ("accent1", "accent2"):
        if k in data:
            hx = _hex6(data.get(k))
            if hx:
                cur[k] = hx
    save_ui(cur)
    out = dict(cur)
    out["has_img"] = sorted([k for k in IMG_KEYS if out.get(k)])
    return web.json_response({"ok": True, "ui": out})

async def admin_requests(request):
    err = _denied(request)
    if err: return err
    items = _pending_items()
    for it in items:
        if (it["kind"] == "deliver" or it["kind"] == "receipt") and it.get("status", "waiting") == "waiting":
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
            return web.json_response({"error": "رسید قبلاً توسط ادمین دیگه‌ای حل شده"}, status=404)
        by = str(data.get("by") or "")
        def _tell_others(txt):
            # به بقیهٔ ادمین‌ها خبر بده تا دوباره تایید نکنن
            for _a in admin_uids():
                if str(_a) != by:
                    _tg_send(_a, txt)
        amt = int(rc.get("amount") or 0)
        who = str(rc.get("uid", ""))
        if action == "reject":
            rc["status"] = "rejected"; rc["done_ts"] = int(time.time()); rc["by"] = by
            save_receipts(rs)
            _tg_send(who, "❌ رسید تایید نشد.\nبا پشتیبانی تماس بگیرید.")
            _tell_others(f"❌ **رسید رد شد**\n👤 کاربر {who}\n💰 {amt:,} تومان")
            return web.json_response({"ok": True, "note": "رسید رد شد"})
        if action == "approve":
            note = _receipt_approve(rc)
            rc["status"] = "done"; rc["done_ts"] = int(time.time()); rc["by"] = by
            save_receipts(rs)
            _tell_others(f"✅ **رسید تایید شد**\n👤 کاربر {who}\n💰 {amt:,} تومان")
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
        configs[target].append({"type": TYPE_LABELS.get(typ, typ), "data": st.get("plan", ""), "link": link})
        save_configs(configs)
        try: _ensure_pending_order(target, typ, st.get("plan", ""))   # مسیرهای بدون سفارش
        except Exception: pass
        try: mark_order_sent(target, link, kind=_kind_from_type(typ))
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
        refund_referral(it)
        if price > 0:
            add_balance(int(uid), price)
        _tg_send(uid, f"❌ **سفارش شما لغو شد:** {it.get('name') or it.get('plan')}"
                      + (f"\n\n💰 {price:,} تومان به کیف پول بازگشت." if price > 0 else ""))
        return web.json_response({"ok": True, "status": "rejected", "refunded": price})
    return web.json_response({"error": "عملیات نامعتبر"}, status=400)

async def admin_user_delete(request):
    err = _denied(request)
    if err: return err
    data = await request.json()
    uid = str(data.get("uid", "")).strip()
    if not uid:
        return web.json_response({"error": "uid لازم"}, status=400)
    w = load_wallet()
    if isinstance(w.get(uid), dict): w.pop(uid, None)   # کیف پول تخت است: {uid: {balance, history}}
    save_wallet(w)
    cf = load_configs(); cf.pop(uid, None); save_configs(cf)
    od = load_orders(); od.pop(uid, None); save_orders(od)
    rf = load_referrals(); rf.pop(uid, None); save_referrals(rf)
    pn = load_pending()
    dropped = [k for k, v in pn.items() if isinstance(v, dict) and str(v.get("user_id") or k) == uid]
    for k in dropped: pn.pop(k, None)
    if dropped: save_pending(pn)
    return web.json_response({"ok": True, "note": f"کاربر {uid} حذف شد"})

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
    threading.Thread(target=_expiry_reminder_loop, daemon=True).start()
    threading.Thread(target=_daily_report_loop, daemon=True).start()

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
    app.add_handler(CallbackQueryHandler(ticket_new, pattern="^ticket_new$"))
    app.add_handler(CallbackQueryHandler(ticket_cancel, pattern="^ticket_cancel$"))
    app.add_handler(CallbackQueryHandler(ticket_reply_cb, pattern=r"^ticket_reply_[0-9]+$"))
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

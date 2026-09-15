#!/usr/bin/env python3
"""Diaz Shop — Telegram Bot + Web Server + Mini App API (all-in-one)"""

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
# Data directory — use /data/ if it exists (Railway volume), else current dir
DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent.resolve()
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

REFERRAL_TARGET = 3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# ─── Local JSON Storage ──────────────────────────────────
DATA_DIR = Path(__file__).parent.resolve()

def _load(fn):
    fp = DATA_DIR / fn
    try:
        if fp.exists():
            with open(fp) as f: return json.load(f)
    except: pass
    return {}

def _save(fn, d):
    fp = DATA_DIR / fn
    with open(fp, "w") as f: json.dump(d, f, indent=2, ensure_ascii=False)

def load_pending(): return _load(PENDING_FILE)
def save_pending(d): _save(PENDING_FILE, d)
def load_configs(): return _load(CONFIGS_FILE)
def save_configs(d): _save(CONFIGS_FILE, d)
def load_wallet(): return _load(WALLET_FILE)
def save_wallet(d): _save(WALLET_FILE, d)
def load_referrals(): return _load(REFERRALS_FILE)
def save_referrals(d): _save(REFERRALS_FILE, d)
def load_accounts(): return _load(ACCOUNTS_FILE) if os.path.exists(str(DATA_DIR / ACCOUNTS_FILE)) else []
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
    railway_url = "worker-production-e8dd.up.railway.app"
    mini_url = railway_url if railway_url else "https://arawtttt.github.io/diaz-shop-bot/"
    if railway_url and not railway_url.startswith("http"):
        mini_url = f"https://{railway_url}"
    shop_url = f"https://worker-production-e8dd.up.railway.app/?uid={uid}"
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
                text="🎉 <b>تبریک!</b>\n\nشما ۳ نفر رو دعوت کردید!\n\nروی دکمه زیر کلیک کنید 👇",
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
    except: is_m = False
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
    await q.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_kb())

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
        text = (f"🎁 <b>اشتراک رایگان</b>\n\nبا دعوت {REFERRAL_TARGET} نفر، اشتراک رایگان بگیرید!\n\n"
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
    await q.edit_message_text("📝 **مبلغ دلخواه (فقط عدد):**")

async def charge_receipt_step(update, context):
    q = update.callback_query; await q.answer()
    amount = int(q.data.replace("charge_receipt_", ""))
    uid = str(q.from_user.id); p = load_pending(); p[uid] = {"waiting": True, "type": "charge", "amount": amount}; save_pending(p)
    await q.edit_message_text(f"📸 **رسید ({amount:,} تومان) رو بفرستید:**")

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
    kb = [[InlineKeyboardButton("✅ تایید", callback_data=f"approve_{ptype}_{user.id}_{plan_id}"),
           InlineKeyboardButton("❌ رد", callback_data=f"reject_{user.id}")]]
    try: await context.bot.send_photo(chat_id=OWNER_ID, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except: pass
    await update.message.reply_text("✅ رسید دریافت شد!")

async def handle_text(update, context):
    uid = str(update.effective_user.id); p = load_pending(); state = p.get(uid)
    if not state or not state.get("waiting"): return
    if state["type"] == "charge_custom":
        try: amount = int(update.message.text.strip())
        except: await update.message.reply_text("❌ فقط عدد."); return
        del p[uid]; save_pending(p)
        kb = [[InlineKeyboardButton("📸 ارسال رسید", callback_data=f"charge_receipt_{amount}")]]
        await update.message.reply_text(f"💳 واریز {amount:,} تومان\n\n🏦 `{CARD_NUMBER}`\n👤 {CARD_NAME}\n\n📸 رسید بفرستید.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return
    # Admin sending subscription/config link to user
    if state.get("waiting_admin"):
        admin_type = state["type"]; target_user = state["user_id"]
        link = update.message.text.strip()
        del p[uid]; save_pending(p)
        configs = load_configs(); k = str(target_user)
        if k not in configs: configs[k] = []
        configs[k].append({"type": admin_type, "data": state.get("plan", ""), "link": link[:300]})
        save_configs(configs)
        await update.message.reply_text(f"✅ اشتراک برای کاربر {target_user} ارسال شد!")
        try:
            await context.bot.send_message(chat_id=target_user,
                text=f"✅ **اشتراک شما فعال شد!**\n\n📦 **نوع:** {admin_type}\n🔗 **لینک:**\n`{link[:500]}`\n\nاز پنل کاربری قابل مشاهده است.",
                parse_mode="Markdown")
        except: pass
        return

    if state["type"] in ("config_wallet_name", "config_receipt_name"):
        name = update.message.text.strip(); plan = state.get("plan_data", {})
        del p[uid]; save_pending(p)
        # Notify admin to create config
        try:
            await context.bot.send_message(chat_id=OWNER_ID,
                text=f"📝 **کانفیگ جدید!**\n\n👤 {update.effective_user.first_name}\n🆔 {uid}\n📝 اسم: {name}\n📦 پلن: {plan.get('name', '')}\n\nلطفاً لینک کانفیگ رو بفرستید.",
                parse_mode="Markdown")
        except: pass
        # Set pending for admin to send config
        pending2 = load_pending()
        pending2[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_config", "user_id": uid, "plan": plan.get("name", "")}
        save_pending(pending2)
        await update.message.reply_text("✅ **سفارش شما ثبت شد!**\n\n⏳ به زودی اشتراک به پنل کاربری شما اضافه می‌شود.")

# ─── Admin Approve/Reject ────────────────────────────────

async def approve_express(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); user_id = int(parts[2]); plan_id = parts[3]
    plan = EXPRESS_PLANS.get(plan_id)
    # Ask admin for the subscription link
    pending = load_pending()
    pending[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_express", "user_id": user_id, "plan": plan_id}
    save_pending(pending)
    await q.edit_message_caption(caption=q.message.caption + "\n\n📝 **لینک اشتراک رو بفرستید:**", parse_mode="Markdown")


async def approve_config(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); user_id = int(parts[2]); plan_id = parts[3]
    pending = load_pending()
    pending[str(OWNER_ID)] = {"waiting_admin": True, "type": "send_config", "user_id": user_id, "plan": plan_id}
    save_pending(pending)
    await q.edit_message_caption(caption=q.message.caption + "\n\n📝 **لینک کانفیگ رو بفرستید:**", parse_mode="Markdown")

async def approve_receipt(update, context):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); ptype = parts[1]; user_id = int(parts[2])
    if ptype == "charge":
        amount = int(parts[3]); add_balance(user_id, amount)
        await context.bot.send_message(chat_id=user_id, text=f"✅ کیف پول {amount:,} تومان شارژ شد!")
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
    await context.bot.send_message(chat_id=user_id, text="❌ رسید تایید نشد.\nبا پشتیبانی تماس بگیرید.")
    await q.edit_message_caption(caption=q.message.caption + "\n\n❌ رد شد!", parse_mode="Markdown")

# ─── Web Server (serves mini app + API) ──────────────────
STATIC_DIR = Path(__file__).parent.resolve()

async def serve_index(request):
    return web.FileResponse(str(STATIC_DIR / "index.html"))

async def serve_static(request):
    fname = request.match_info["name"]
    fpath = STATIC_DIR / fname
    if fpath.exists() and fpath.is_file():
        return web.FileResponse(str(fpath))
    return web.Response(status=404)

# API handlers
def _extract_uid_from_initdata(initdata):
    """Parse Telegram initData to get user ID"""
    if not initdata:
        return None
    try:
        from urllib.parse import parse_qs
        params = parse_qs(initdata)
        if "user" in params:
            import json
            user = json.loads(params["user"][0])
            return str(user.get("id", ""))
    except:
        pass
    return None

async def api_user(request):
    uid = request.match_info.get("uid", "")
    if not uid:
        initdata = request.headers.get("X-Telegram-Init-Data", "")
        uid = _extract_uid_from_initdata(initdata) or ""
    return web.json_response({
        "balance": get_balance(uid),
        "referral_count": get_referral_count(int(uid)),
        "free_done": has_free_sub(int(uid)),
        "configs": load_configs().get(uid, []),
        "history": load_wallet().get(uid, {}).get("history", [])[-10:],
        "card_number": CARD_NUMBER, "card_name": CARD_NAME,
        "referral_target": REFERRAL_TARGET, "bot_username": "Diazpshopbot",
    })

async def api_buy_config(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = CONFIG_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        p = load_pending(); p[uid] = {"waiting": True, "type": "config_wallet_name", "plan": plan_id, "plan_data": plan}; save_pending(p)
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
    result = await spider.create_user(name, plan.get("limit_gb", 0), plan.get("days", 30))
    if result:
        configs = load_configs()
        if uid not in configs: configs[uid] = []
        cfg = result.get("config", "") or result.get("subscription_url", "")
        configs[uid].append({"type": "کانفیگ", "data": plan.get("name", ""), "link": cfg[:200]})
        save_configs(configs)
        return web.json_response({"ok": True, "config": cfg, "expire_at": result.get("expire_at", ""), "plan": plan.get("name", "")})
    return web.json_response({"error": "creation failed"}, status=500)

async def api_buy_express(request):
    data = await request.json()
    uid = data.get("uid"); plan_id = data.get("plan"); method = data.get("method", "wallet")
    plan = EXPRESS_PLANS.get(plan_id)
    if not plan: return web.json_response({"error": "invalid plan"}, status=400)
    if method == "wallet":
        if not spend_balance(int(uid), plan["price_int"]):
            return web.json_response({"error": "insufficient balance"})
        return web.json_response({"ok": True, "action": "wallet_paid"})
    return web.json_response({"ok": True, "action": "card_payment", "card": CARD_NUMBER, "card_name": CARD_NAME})

async def api_wallet_charge(request):
    data = await request.json()
    uid = data.get("uid"); amount = data.get("amount", 0)
    if amount <= 0: return web.json_response({"error": "invalid amount"}, status=400)
    p = load_pending(); p[uid] = {"waiting": True, "type": "charge", "amount": amount}; save_pending(p)
    return web.json_response({"ok": True, "card": CARD_NUMBER, "card_name": CARD_NAME, "amount": amount})

def create_web_app():
    app = web.Application()
    app.router.add_get("/", serve_index)
    app.router.add_get("/index.html", serve_index)
    app.router.add_get("/api/user/{uid}", api_user)
    app.router.add_post("/api/buy_config", api_buy_config)
    app.router.add_post("/api/buy_config_name", api_buy_config_name)
    app.router.add_post("/api/buy_express", api_buy_express)
    app.router.add_post("/api/wallet_charge", api_wallet_charge)
    # Static files — must come AFTER specific routes
    app.router.add_get("/{name}", serve_static)
    return app

# ─── Main: Web Server (thread) + Bot (main thread) ──────
def main():
    PORT = int(os.environ.get("PORT", 8080))

    # Web server in daemon thread
    def run_web():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(create_web_app())
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "0.0.0.0", PORT).start())
        logger.info(f"Web server on port {PORT}")
        loop.run_forever()

    threading.Thread(target=run_web, daemon=True).start()

    # Bot on main thread — use run_polling() directly (non-async)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(open_shop, pattern="^open_shop$"))
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
# Diaz Shop Bot


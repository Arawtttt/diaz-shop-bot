#!/usr/bin/env python3
"""Diaz Shop - Telegram Bot for VPN Config Sales with SpiderPanel Integration"""

import os
import json
import time
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

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

# SpiderPanel settings
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── SpiderPanel API Client ───────────────────────────────

class SpiderPanel:
    def __init__(self, base_url, password):
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.session_token = None
        self.client = httpx.AsyncClient(timeout=30, verify=False)

    async def _ensure_auth(self):
        if not self.session_token:
            await self.login()

    async def login(self):
        for pw in [self.password, "admin"]:
            try:
                r = await self.client.post(f"{self.base_url}/api/login", json={"password": pw})
                if r.status_code == 200:
                    for cookie in r.cookies.jar:
                        if cookie.name == "spider_session":
                            self.session_token = cookie.value
                            if pw != self.password:
                                logger.info(f"SpiderPanel login OK with fallback password '{pw}'")
                            else:
                                logger.info("SpiderPanel login OK")
                            return True
                    cookies = dict(r.cookies)
                    if cookies:
                        self.session_token = list(cookies.values())[0]
                        logger.info(f"SpiderPanel login OK (cookie: {list(cookies.keys())[0]})")
                        return True
            except Exception as e:
                logger.error(f"SpiderPanel login error ({pw}): {e}")
        logger.error("SpiderPanel login failed with all passwords")
        return False

    def _cookies(self):
        if self.session_token:
            return {"spider_session": self.session_token}
        return {}

    async def _retry_request(self, method, url, **kwargs):
        """Request with auto-retry on 401"""
        await self._ensure_auth()
        func = getattr(self.client, method)
        r = await func(url, cookies=self._cookies(), **kwargs)
        if r.status_code == 401:
            self.session_token = None
            await self.login()
            r = await func(url, cookies=self._cookies(), **kwargs)
        return r

    async def create_user(self, username, limit_gb=0, days=30):
        """Create a SpiderPanel USER and return config details. Auto-retries with suffix on 409."""
        import secrets as _secrets
        body = {
            "username": username,
            "traffic_limit_gb": limit_gb,
            "expire_days": days,
            "protocol": "vless",
            "concurrent_connections": 1,
            "inbound_ids": ["default-reverse", "default"],
        }
        r = await self._retry_request("post", f"{self.base_url}/api/users", json=body)
        # If 409 (username exists), retry with random suffix
        if r.status_code == 409:
            suffix = _secrets.token_hex(2)
            body["username"] = f"{username}-{suffix}"
            logger.info(f"Username exists, retrying with: {body['username']}")
            r = await self._retry_request("post", f"{self.base_url}/api/users", json=body)
        if r.status_code == 200:
            data = r.json()
            user_id = data.get("user_id", "")
            logger.info(f"SpiderPanel user created: {data.get('username')} ({user_id})")
            # Config is not included in create response — fetch it separately
            config = data.get("config", "")
            if not config and user_id:
                try:
                    cr = await self._retry_request("get", f"{self.base_url}/api/users/{user_id}/config")
                    if cr.status_code == 200:
                        config = cr.json().get("config", "")
                except Exception as e:
                    logger.error(f"Failed to fetch config for {user_id}: {e}")
            return {
                "user_id": user_id,
                "username": data.get("username"),
                "config": config,
                "config_uuid": data.get("config_uuid", ""),
                "subscription_uuid": data.get("subscription_uuid", ""),
                "subscription_url": data.get("subscription_url", ""),
                "traffic_limit_bytes": data.get("traffic_limit_bytes", 0),
                "expire_at": data.get("expire_at", ""),
            }
        logger.error(f"SpiderPanel create_user failed: {r.status_code} {r.text[:200]}")
        return None

    async def get_users(self):
        """Get all users with traffic info"""
        r = await self._retry_request("get", f"{self.base_url}/api/users")
        if r.status_code == 200:
            return r.json().get("users", [])
        return []

    async def get_user_config(self, user_id):
        """Get single config for a specific user"""
        r = await self._retry_request("get", f"{self.base_url}/api/users/{user_id}/config")
        if r.status_code == 200:
            return r.json().get("config", "")
        return ""

    async def get_user_all_configs(self, subscription_uuid):
        """Get ALL configs via subscription endpoint (Reality + VLESS+WS + XHTTP)"""
        import base64
        r = await self._retry_request("get", f"{self.base_url}/subs/{subscription_uuid}")
        if r.status_code == 200:
            try:
                decoded = base64.b64decode(r.text).decode()
                configs = [c.strip() for c in decoded.strip().split("\n") if c.strip()]
                return configs
            except Exception as e:
                logger.error(f"Failed to decode subscription configs: {e}")
        return []

    async def close(self):
        await self.client.aclose()


spider = SpiderPanel(SPIDER_URL, SPIDER_PASSWORD)

# ─── File Helpers ─────────────────────────────────────────

def _load(filename):
    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Load {filename} error: {e}")
    return {}

def _save(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save {filename} error: {e}")

def load_pending(): return _load(PENDING_FILE)
def save_pending(d): _save(PENDING_FILE, d)
def load_configs(): return _load(CONFIGS_FILE)
def save_configs(d): _save(CONFIGS_FILE, d)
def load_wallet(): return _load(WALLET_FILE)
def save_wallet(d): _save(WALLET_FILE, d)
def load_referrals(): return _load(REFERRALS_FILE)
def save_referrals(d): _save(REFERRALS_FILE, d)
def load_accounts(): return _load(ACCOUNTS_FILE) if os.path.exists(ACCOUNTS_FILE) else []
def save_accounts(d): _save(ACCOUNTS_FILE, d)

REFERRAL_TARGET = 3

def get_referral_count(inviter_id):
    refs = load_referrals()
    return len(refs.get(str(inviter_id), {}).get("invited", []))

def add_referral(inviter_id, invited_id):
    refs = load_referrals()
    uid = str(inviter_id)
    if uid not in refs:
        refs[uid] = {"invited": [], "free_given": False}
    if invited_id not in refs[uid]["invited"]:
        refs[uid]["invited"].append(invited_id)
        save_referrals(refs)
        return True
    return False

def has_free_sub(uid):
    refs = load_referrals()
    return refs.get(str(uid), {}).get("free_given", False)

def mark_free_given(uid):
    refs = load_referrals()
    uid_str = str(uid)
    if uid_str in refs:
        refs[uid_str]["free_given"] = True
        save_referrals(refs)

def get_next_account():
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("used_count", 0) < acc.get("max_uses", 3):
            acc["used_count"] = acc.get("used_count", 0) + 1
            save_accounts(accounts)
            return acc
    return None

def get_balance(user_id):
    wallet = load_wallet()
    return wallet.get(str(user_id), {}).get("balance", 0)

def add_balance(user_id, amount):
    wallet = load_wallet()
    uid = str(user_id)
    if uid not in wallet:
        wallet[uid] = {"balance": 0, "history": []}
    wallet[uid]["balance"] += amount
    wallet[uid]["history"].append({"amount": amount, "type": "charge"})
    save_wallet(wallet)

def spend_balance(user_id, amount):
    wallet = load_wallet()
    uid = str(user_id)
    if uid not in wallet or wallet[uid]["balance"] < amount:
        return False
    wallet[uid]["balance"] -= amount
    wallet[uid]["history"].append({"amount": -amount, "type": "spend"})
    save_wallet(wallet)
    return True

async def is_member(chat_username, user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_username, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        return False

def _bytes_to_human(n):
    if n <= 0:
        return "نامحدود"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"

# ─── Main Menu ────────────────────────────────────────────

WELCOME_TEXT = (
    "🎮 به ربات اختصاصی Diaz Shop خوش آمدید 🚀!\n\n"
    " محصولات ما زیر قیمت و تضمینی هستند! ✅\n\n"
    "━━━━━━━━━━━━━━━━━\n"
    f" پشتیبانی: @{SUPPORT_USERNAME}"
)

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 خرید ExpressVPN", callback_data="buy_express")],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet_menu")],
        [InlineKeyboardButton("🎁 اشتراک رایگان", callback_data="free_sub")],
        [InlineKeyboardButton("👤 پنل کاربری", callback_data="user_panel")],
        [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

# ─── Start & Membership ───────────────────────────────────

async def start(update, context):
    user = update.effective_user
    logger.info(f"START from {user.id} ({user.first_name}), args={context.args}")

    # Track referral directly
    if context.args:
        payload = context.args[0]
        if payload.startswith("ref"):
            try:
                inviter_id = int(payload[3:])
                if inviter_id != user.id:
                    added = add_referral(inviter_id, user.id)
                    count = get_referral_count(inviter_id)
                    logger.info(f"REFERRAL: user={user.id} by {inviter_id}, added={added}, total={count}")
                    if added and count >= REFERRAL_TARGET and not has_free_sub(inviter_id):
                        mark_free_given(inviter_id)
                        kb = [[InlineKeyboardButton("🎁 اشتراک رایگان", callback_data="claim_free_sub")]]
                        try:
                            await context.bot.send_message(
                                chat_id=inviter_id,
                                text="🎉 <b>تبریک!</b>\n\nشما ۳ نفر رو دعوت کردید و اشتراک رایگان دریافت کردید!\n\nروی دکمه زیر کلیک کنید 👇",
                                reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Notify inviter failed: {e}")
            except (ValueError, IndexError) as e:
                logger.error(f"Ref parse error: {e}")

    if not await is_member(CHANNEL_ID, user.id, context):
        kb = [
            [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_member")]
        ]
        await update.message.reply_text(
            "⚠️ برای استفاده از ربات ابتدا باید در کانال عضو شوید!\n\n"
            " روی دکمه زیر کلیک کنید و عضو شوید، سپس دکمه «عضو شدم» را بزنید.",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return
    await send_welcome_msg(update.message)

async def check_member(update, context):
    query = update.callback_query
    await query.answer()
    if not await is_member(CHANNEL_ID, query.from_user.id, context):
        await query.edit_message_text("❌ هنوز عضو کانال نشدید!\nاول عضو شوید و دوباره دکمه «عضو شدم» را بزنید.")
        return
    await query.message.delete()
    await send_welcome_msg(query.message)

async def send_welcome_msg(message_obj):
    await message_obj.reply_text(WELCOME_TEXT, reply_markup=main_menu_kb())

async def back_main(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(WELCOME_TEXT, reply_markup=main_menu_kb())

# ─── Free Subscription (Referral) ─────────────────────────

async def free_sub_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    count = get_referral_count(uid)
    free_done = has_free_sub(uid)
    username = context.bot.username

    if free_done:
        text = "🎁 <b>اشتراک رایگان</b>\n\nشما قبلاً اشتراک رایگان خود را دریافت کرده‌اید! ✅\n\n━━━━━━━━━━━━━━━━━"
    elif count >= REFERRAL_TARGET:
        text = f"🎉 <b>تبریک!</b>\n\nشما {count} نفر را دعوت کرده‌اید!\n\nروی «دریافت اشتراک» کلیک کنید 👇\n\n━━━━━━━━━━━━━━━━━"
    else:
        remaining = REFERRAL_TARGET - count
        text = (
            f"🎁 <b>اشتراک رایگان</b>\n\n"
            f"با دعوت {REFERRAL_TARGET} نفر به ربات، اشتراک رایگان بگیرید!\n\n"
            f"📊 <b>وضعیت شما:</b>\n"
            f"   تعداد دعوت‌شده: <b>{count}/{REFERRAL_TARGET}</b>\n"
            f"   باقی‌مانده: <b>{remaining} نفر</b>\n\n"
            f"🔗 لینک دعوت اختصاصی شما:\n"
            f"<code>https://t.me/{username}?start=ref{uid}</code>\n\n"
            f"این لینک رو با دوستات به اشتراک بذارید!\n\n"
            f"━━━━━━━━━━━━━━━━━"
        )

    kb = []
    if count >= REFERRAL_TARGET and not free_done:
        kb.append([InlineKeyboardButton("🎁 دریافت اشتراک رایگان", callback_data="claim_free_sub")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")


async def claim_free_sub(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    count = get_referral_count(uid)

    if count < REFERRAL_TARGET:
        await q.edit_message_text(f"❌ هنوز {REFERRAL_TARGET - count} نفر دیگه لازم دارید.")
        return

    account = get_next_account()
    if not account:
        await q.edit_message_text("❌ اشتراک رایگان تمام شده! با پشتیبانی تماس بگیرید.")
        return

    kb = [[InlineKeyboardButton("🏠 بازگشت", callback_data="back_main")]]
    await q.edit_message_text(
        f"🎉 <b>اشتراک رایگان شما فعال شد!</b>\n\n"
        f"📧 <b>ایمیل:</b> <code>{account['email']}</code>\n"
        f"🔑 <b>پسورد:</b> <code>{account['password']}</code>\n\n"
        f"⏰ <b>اعتبار:</b> {account['days_left']} روز\n\n"
        "━━━━━━━━━━━━━━━━━\nموفق باشید! 🙏",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
    )
    mark_free_given(uid)
    logger.info(f"FREE SUB claimed by {uid}, account={account['email']}")

# ─── Wallet ───────────────────────────────────────────────

def wallet_text(user_id):
    bal = get_balance(user_id)
    return f"💰 **کیف پول شما:**\n\n💳 **موجودی:** {bal:,} تومان\n\n━━━━━━━━━━━━━━━━━\nموجودی خود را افزایش دهید و از آن برای خرید استفاده کنید."

async def wallet_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    kb = [
        [InlineKeyboardButton("💳 افزایش موجودی", callback_data="charge_wallet")],
        [InlineKeyboardButton("📊 تاریخچه تراکنش‌ها", callback_data="wallet_history")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")],
    ]
    await q.edit_message_text(wallet_text(uid), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def charge_wallet(update, context):
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("۵۰,۰۰۰ تومان", callback_data="charge_50000")],
        [InlineKeyboardButton("۱۰۰,۰۰۰ تومان", callback_data="charge_100000")],
        [InlineKeyboardButton("۲۰۰,۰۰۰ تومان", callback_data="charge_200000")],
        [InlineKeyboardButton("۵۰۰,۰۰۰ تومان", callback_data="charge_500000")],
        [InlineKeyboardButton("📝 مبلغ دلخواه", callback_data="charge_custom")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")],
    ]
    await q.edit_message_text(
        "💳 **افزایش موجودی کیف پول**\n\nمبلغ مورد نظر را انتخاب کنید:\n\n━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def charge_custom(update, context):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    pending = load_pending()
    pending[uid] = {"waiting": True, "type": "charge_custom"}
    save_pending(pending)
    await q.edit_message_text(
        "📝 **مبلغ دلخواه را وارد کنید:**\n\nفقط عدد را تایپ کنید (مثال: 75000)\n\n━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

async def charge_amount(update, context):
    q = update.callback_query
    await q.answer()
    amount_str = q.data.replace("charge_", "")
    try:
        amount = int(amount_str)
    except ValueError:
        return
    kb = [
        [InlineKeyboardButton("📸 ارسال رسید", callback_data=f"charge_receipt_{amount}")],
        [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")],
    ]
    await q.edit_message_text(
        f"💳 **افزایش موجودی:** {amount:,} تومان\n\n"
        f"🏦 **شماره کارت:**\n`{CARD_NUMBER}`\n👤 **به نام:** {CARD_NAME}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💰 مبلغ را به شماره کارت واریز کنید.\n📸 سپس رسید پرداخت را ارسال کنید.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def charge_receipt_step(update, context):
    q = update.callback_query
    await q.answer()
    amount = int(q.data.replace("charge_receipt_", ""))
    uid = str(q.from_user.id)
    pending = load_pending()
    pending[uid] = {"waiting": True, "type": "charge", "amount": amount}
    save_pending(pending)
    await q.edit_message_text(
        f"📸 **لطفاً رسید پرداخت ({amount:,} تومان) را ارسال کنید:**\n\n(عکس رسید را اینجا بفرستید)\n\n━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

async def wallet_history(update, context):
    q = update.callback_query
    await q.answer()
    wallet = load_wallet()
    uid = str(q.from_user.id)
    user_wallet = wallet.get(uid, {})
    history = user_wallet.get("history", [])
    bal = user_wallet.get("balance", 0)
    if not history:
        text = "📊 **تاریخچه تراکنش‌ها:**\n\nهنوز تراکنشی ثبت نشده.\n\n━━━━━━━━━━━━━━━━━"
    else:
        text = "📊 **تاریخچه تراکنش‌ها:**\n\n"
        for h in history[-10:]:
            sign = "+" if h["amount"] > 0 else ""
            text += f"{'💳' if h['type'] == 'charge' else '📦'} {sign}{h['amount']:,} تومان\n"
        text += f"\n━━━━━━━━━━━━━━━━━\n💰 **موجودی فعلی:** {bal:,} تومان"
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ─── Config Purchase Flow ─────────────────────────────────
# Steps: select plan → choose payment → (if wallet: ask name → auto-create) / (if card: ask receipt → admin approve → ask name → auto-create)

async def buy_config(update, context):
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("📦 ۱۰ گیگ - ۱۲,۰۰۰ تومان", callback_data="config_10gb")],
        [InlineKeyboardButton("📦 ۲۰ گیگ - ۳۰,۰۰۰ تومان", callback_data="config_20gb")],
        [InlineKeyboardButton("📦 ۵۰ گیگ - ۷۰,۰۰۰ تومان", callback_data="config_50gb")],
        [InlineKeyboardButton("📦 ۸۰ گیگ - ۱۱۰,۰۰۰ تومان", callback_data="config_80gb")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")],
    ]
    await q.edit_message_text(
        "📦 **انتخاب پلن کانفیگ:**\n\n همه پلن‌ها یک ماهه هستند.\n━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def select_config(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("config_", "")
    plan = CONFIG_PLANS.get(pid)
    if not plan:
        return
    uid = q.from_user.id
    bal = get_balance(uid)
    can_wallet = bal >= plan["price_int"]
    kb = []
    if can_wallet:
        kb.append([InlineKeyboardButton(f"💰 پرداخت از کیف پول ({plan['price']})", callback_data=f"pay_wallet_config_{pid}")])
    kb.append([InlineKeyboardButton("💳 پرداخت با کارت", callback_data=f"pay_config_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="buy_config")])
    wallet_note = f"\n💰 موجودی کیف پول: {bal:,} تومان" if can_wallet else f"\n💰 موجودی کیف پول: {bal:,} تومان (نافicient)"
    await q.edit_message_text(
        f"📦 **پلن انتخابی:** {plan['name']}\n💰 **قیمت:** {plan['price']} تومان\n⏰ **مدت:** {plan['duration']}{wallet_note}\n\n━━━━━━━━━━━━━━━━━\n روش پرداخت را انتخاب کنید.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def pay_config(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("pay_config_", "")
    plan = CONFIG_PLANS.get(pid)
    if not plan:
        return
    kb = [
        [InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_{pid}")],
        [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")],
    ]
    await q.edit_message_text(
        f"💳 **اطلاعات پرداخت:**\n\n💰 **مبلغ:** {plan['price']} تومان\n📦 **پلن:** {plan['name']} ({plan['duration']})\n\n🏦 **شماره کارت:**\n`{CARD_NUMBER}`\n👤 **به نام:** {CARD_NAME}\n\n━━━━━━━━━━━━━━━━━\n💰 مبلغ را به شماره کارت واریز کنید.\n📸 سپس رسید پرداخت را ارسال کنید.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def receipt_received(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("receipt_", "")
    plan = CONFIG_PLANS.get(pid)
    if not plan:
        return
    await q.edit_message_text(
        "📸 **لطفاً رسید پرداخت را ارسال کنید:**\n\n (عکس رسید را اینجا بفرستید)\n━━━━━━━━━━━━━━━━━"
    )
    uid = str(q.from_user.id)
    pending = load_pending()
    pending[uid] = {"waiting": True, "plan": pid, "type": "config"}
    save_pending(pending)

# ─── Wallet Payment → Ask Name → Auto-Create User ─────────

async def pay_wallet_config(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("pay_wallet_config_", "")
    plan = CONFIG_PLANS.get(pid)
    if not plan:
        return
    uid = q.from_user.id
    price = plan["price_int"]

    if not spend_balance(uid, price):
        await q.edit_message_text("❌ موجودی کیف پول کافی نیست!",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 شارژ کیف پول", callback_data="charge_wallet")]]))
        return

    # Save plan info and ask for name
    pending = load_pending()
    pending[str(uid)] = {
        "waiting": True,
        "type": "config_wallet_name",
        "plan": pid,
        "plan_data": plan,
    }
    save_pending(pending)

    await q.edit_message_text(
        f"✅ **پرداخت موفق!** {plan['price']} تومان از کیف پول کسر شد.\n\n"
        f"📝 **حالا اسم مورد نظرتون رو بفرستید:**\n"
        f"(این اسم روی کانفیگ شما در پنل ثبت میشه)\n\n"
        f"━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ─── Express Purchase ─────────────────────────────────────

async def buy_express(update, context):
    q = update.callback_query
    await q.answer()
    text = (
        "🔐 **ExpressVPN**\n\n • اسپانسر رسمی جام جهانی ۲۰۲۶\n • دارای قابلیت Killswitch\n • دارای پروتکل‌های قدرمند\n • قابلیت اتصال در تمامی دستگاه‌ها\n • قابلیت مسدودسازی تبلیغات\n • قابلیت Auto Connect\n • دارای ۳۰۰ سرور از ۱۰۰ کشور\n • دارای آیپی‌های ثابت\n • مناسب گیمینگ\n • مناسب اینستاگرام\n • مناسب دانلود و آپلود\n • سرعت بی‌نظیر\n • سرورهای قدرمند و نامحدود\n\n━━━━━━━━━━━━━━━━━\n **انتخاب پلن:**"
    )
    kb = [
        [InlineKeyboardButton("⏰ ۱ ماهه - ۲۲۰,۰۰۰ تومان", callback_data="express_1m")],
        [InlineKeyboardButton("⏰ ۳ ماهه - ۳۳۰,۰۰۰ تومان", callback_data="express_3m")],
        [InlineKeyboardButton("⏰ ۶ ماهه - ۴۹۰,۰۰۰ تومان", callback_data="express_6m")],
        [InlineKeyboardButton("⏰ ۱ ساله - ۹۵۰,۰۰۰ تومان", callback_data="express_1y")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def select_express(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("express_", "")
    plan = EXPRESS_PLANS.get(pid)
    if not plan:
        return
    uid = q.from_user.id
    bal = get_balance(uid)
    can_wallet = bal >= plan["price_int"]
    kb = []
    if can_wallet:
        kb.append([InlineKeyboardButton(f"💰 پرداخت از کیف پول ({plan['price']})", callback_data=f"pay_wallet_express_{pid}")])
    kb.append([InlineKeyboardButton("💳 پرداخت با کارت", callback_data=f"pay_express_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="buy_express")])
    wallet_note = f"\n💰 موجودی کیف پول: {bal:,} تومان" if can_wallet else f"\n💰 موجودی کیف پول: {bal:,} تومان (نافicient)"
    await q.edit_message_text(
        f"🔐 **پلن انتخابی:** {plan['name']}\n💰 **قیمت:** {plan['price']} تومان\n{wallet_note}\n\n━━━━━━━━━━━━━━━━━\n روش پرداخت را انتخاب کنید.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def pay_express(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("pay_express_", "")
    plan = EXPRESS_PLANS.get(pid)
    if not plan:
        return
    kb = [
        [InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_express_{pid}")],
        [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")],
    ]
    await q.edit_message_text(
        f"💳 **اطلاعات پرداخت:**\n\n💰 **مبلغ:** {plan['price']} تومان\n📦 **پلن:** {plan['name']}\n\n🏦 **شماره کارت:**\n`{CARD_NUMBER}`\n👤 **به نام:** {CARD_NAME}\n\n━━━━━━━━━━━━━━━━━\n💰 مبلغ را به شماره کارت واریز کنید.\n📸 سپس رسید پرداخت را ارسال کنید.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def receipt_express_received(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("receipt_express_", "")
    plan = EXPRESS_PLANS.get(pid)
    if not plan:
        return
    await q.edit_message_text(
        "📸 **لطفاً رسید پرداخت را ارسال کنید:**\n\n (عکس رسید را اینجا بفرستید)\n━━━━━━━━━━━━━━━━━"
    )
    uid = str(q.from_user.id)
    pending = load_pending()
    pending[uid] = {"waiting": True, "plan": pid, "type": "express"}
    save_pending(pending)

async def pay_wallet_express(update, context):
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("pay_wallet_express_", "")
    plan = EXPRESS_PLANS.get(pid)
    if not plan:
        return
    uid = q.from_user.id
    price = plan["price_int"]
    if not spend_balance(uid, price):
        await q.edit_message_text("❌ موجودی کیف پول کافی نیست!",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 شارژ کیف پول", callback_data="charge_wallet")]]))
        return
    pending = load_pending()
    pending[str(uid)] = {"waiting": True, "plan": pid, "type": "express_wallet", "amount": price}
    save_pending(pending)
    kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
    await q.edit_message_text(
        f"✅ **پرداخت از کیف پول موفق!**\n\n📦 **پلن:** {plan['name']}\n💰 **مبلغ کسر شده:** {plan['price']} تومان\n\n━━━━━━━━━━━━━━━━━\n⏳ سفارش شما ثبت شد و به زودی اشتراک برایتان ارسال می‌شود!",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=f"💰 **خرید ExpressVPN از کیف پول!**\n\n👤 **کاربر:** {q.from_user.first_name} (@{q.from_user.username or 'ندارد'})\n🆔 **آیدی:** {uid}\n📦 **پلن:** {plan['name']}\n💰 **مبلغ:** {plan['price']} تومان\n\nلطفاً اشتراک ExpressVPN را برای کاربر ارسال کنید.",
        parse_mode="Markdown"
    )

# ─── User Panel ───────────────────────────────────────────

async def user_panel(update, context):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    bal = get_balance(int(uid))

    # Get user's ExpressVPN subscriptions (stored locally)
    configs = load_configs()
    user_configs = configs.get(uid, [])

    if not user_configs:
        text = (
            f"👤 **پنل کاربری:**\n\n"
            f"💰 **کیف پول:** {bal:,} تومان\n\n"
            f"📦 شما هنوز هیچ اشتراکی ندارید.\n"
            f"━━━━━━━━━━━━━━━━━"
        )
    else:
        text = f"👤 **پنل کاربری:**\n\n💰 **کیف پول:** {bal:,} تومان\n\n"
        for i, cfg in enumerate(user_configs, 1):
            text += f"**{i}.** {cfg.get('type', 'ExpressVPN')} - {cfg.get('data', '')}\n"
            link = cfg.get("link", "")
            if link:
                text += f"   🔗 `{link}`\n\n"
            else:
                text += "\n"
        text += "━━━━━━━━━━━━━━━━━"

    kb = [
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="user_panel")],
        [InlineKeyboardButton("🔐 خرید ExpressVPN", callback_data="buy_express")],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet_menu")],
        [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ─── Handle Receipt Photo ─────────────────────────────────

async def handle_photo(update, context):
    uid = str(update.effective_user.id)
    pending = load_pending()
    state = pending.get(uid)
    if not state or not state.get("waiting"):
        return

    ptype = state.get("type", "config")
    user = update.effective_user

    # ─── Wallet charge receipt ───
    if ptype == "charge":
        amount = state.get("amount", 0)
        del pending[uid]
        save_pending(pending)
        caption = (
            f"💰 **رسید شارژ کیف پول!**\n\n"
            f"👤 **کاربر:** {user.first_name} (@{user.username or 'ندارد'})\n"
            f"🆔 **آیدی:** {user.id}\n"
            f"💰 **مبلغ:** {amount:,} تومان"
        )
        kb = [
            [InlineKeyboardButton("✅ تایید و شارژ کیف پول", callback_data=f"approve_charge_{user.id}_{amount}")],
            [InlineKeyboardButton("❌ رد", callback_data=f"reject_{user.id}")],
        ]
        try:
            await context.bot.send_photo(
                chat_id=OWNER_ID, photo=update.message.photo[-1].file_id,
                caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to forward charge receipt: {e}")
        kb2 = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
        await update.message.reply_text(
            "✅ رسید شما دریافت شد!\nخیلی زود کیف پول شما شارژ می‌شه 😉\n━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(kb2)
        )
        return

    # ─── Custom amount charge ───
    if ptype == "charge_custom":
        del pending[uid]
        save_pending(pending)
        await update.message.reply_text("❌ لطفاً ابتدا مبلغ را به صورت عدد تایپ کنید.")
        return

    # ─── Config / Express receipt ───
    plan_id = state.get("plan")
    plan = CONFIG_PLANS.get(plan_id) if ptype in ("config", "config_wallet") else EXPRESS_PLANS.get(plan_id)
    if not plan:
        return
    del pending[uid]
    save_pending(pending)
    caption = (
        f"📸 **رسید جدید!**\n\n"
        f"👤 **کاربر:** {user.first_name} (@{user.username or 'ندارد'})\n"
        f"🆔 **آیدی:** {user.id}\n"
        f"📦 **پلن:** {plan['name']}\n"
        f"💰 **مبلغ:** {plan['price']} تومان\n"
        f"📦 **نوع:** {'کانفیگ' if 'config' in ptype else 'ExpressVPN'}"
    )
    kb = [
        [InlineKeyboardButton("✅ تایید و ارسال", callback_data=f"approve_{ptype}_{user.id}_{plan_id}")],
        [InlineKeyboardButton("❌ رد", callback_data=f"reject_{user.id}")],
    ]
    try:
        await context.bot.send_photo(
            chat_id=OWNER_ID, photo=update.message.photo[-1].file_id,
            caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to forward receipt: {e}")
    kb2 = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
    await update.message.reply_text(
        "✅ رسید شما دریافت شد!\nخیلی زود سفارشت پیگیری و تحویل داده میشه 😉\n━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(kb2)
    )

# ─── Admin: Approve Charge ────────────────────────────────

async def approve_charge(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    user_id = int(parts[2])
    amount = int(parts[3])
    add_balance(user_id, amount)
    kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ **کیف پول شما شارژ شد!**\n\n💰 **مبلغ اضافه شده:** {amount:,} تومان\n\n━━━━━━━━━━━━━━━━━\nاز خرید شما متشکریم! 🙏",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    await q.edit_message_caption(caption=q.message.caption + "\n\n✅ **تایید و شارژ شد!**", parse_mode="Markdown")

# ─── Admin: Approve Config/Express ────────────────────────
# After approval → ask for NAME → auto-create on SpiderPanel

async def approve_receipt(update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    ptype = parts[1]
    user_id = int(parts[2])
    plan_id = parts[3]

    if ptype == "charge":
        await approve_charge(update, context)
        return

    plan = CONFIG_PLANS.get(plan_id) if ptype in ("config", "config_wallet") else EXPRESS_PLANS.get(plan_id)
    plan_name = plan["name"] if plan else plan_id

    # Save approval state and ask admin for name or auto-proceed
    # For configs: ask admin to confirm, then ask user for name
    context.bot_data[f"pending_approve_{OWNER_ID}"] = {
        "user_id": user_id, "plan_type": ptype, "plan_id": plan_id, "plan_name": plan_name,
    }

    await q.edit_message_caption(
        caption=q.message.caption + "\n\n✅ **تایید شد!** در حال ساخت کانفیگ...",
        parse_mode="Markdown"
    )

    # For config payments: ask user for their name, then auto-create
    if "config" in ptype:
        # Save state for user to provide name
        pending = load_pending()
        pending[str(user_id)] = {
            "waiting": True,
            "type": "config_receipt_name",
            "plan": plan_id,
            "plan_data": plan,
            "paid_via": "receipt",
        }
        save_pending(pending)

        kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ **پرداخت شما تایید شد!**\n\n"
                f"📦 **پلن:** {plan_name}\n\n"
                f"📝 **حالا اسم مورد نظرتون رو بفرستید:**\n"
                f"(این اسم روی کانفیگ شما در پنل ثبت میشه)\n\n"
                f"━━━━━━━━━━━━━━━━━"
            ),
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
    else:
        # Express: admin sends manually
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"📝 **لطفاً لینک اشتراک ExpressVPN رو بفرست:**\n\n👤 **کاربر:** {user_id}\n📦 **پلن:** {plan_name}\n\nلینک رو تایپ کن و بفرست 👇",
            parse_mode="Markdown"
        )

async def reject_receipt(update, context):
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split("_")[1])
    kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
    await context.bot.send_message(
        chat_id=user_id,
        text=f"❌ **رسید شما تایید نشد.**\n\nلطفاً با پشتیبانی تماس بگیرید.\n💬 @{SUPPORT_USERNAME}\n━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    await q.edit_message_caption(caption=q.message.caption + "\n\n❌ **رد شد!**", parse_mode="Markdown")

async def handle_admin_text(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    pending = context.bot_data.get(f"pending_approve_{OWNER_ID}")
    if not pending:
        return

    config_link = update.message.text.strip()
    user_id = pending["user_id"]
    plan_name = pending["plan_name"]

    # Save to user's configs
    configs = load_configs()
    uid_str = str(user_id)
    if uid_str not in configs:
        configs[uid_str] = []
    configs[uid_str].append({
        "type": "ExpressVPN",
        "data": plan_name,
        "link": config_link,
        "date": time.strftime("%Y-%m-%d"),
    })
    save_configs(configs)

    kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ **پرداخت شما تایید شد!**\n\n📦 **پلن:** {plan_name}\n🔗 **لینک اشتراک:**\n`{config_link}`\n\n━━━━━━━━━━━━━━━━━\nاز خرید شما متشکریم! 🙏",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    await update.message.reply_text(f"✅ **اشتراک با موفقیت ارسال شد!**\n\n👤 کاربر: {user_id}\n📦 پلن: {plan_name}")
    del context.bot_data[f"pending_approve_{OWNER_ID}"]

# ─── Handle Text (name input for config creation) ─────────

async def handle_text(update, context):
    uid = str(update.effective_user.id)
    pending = load_pending()
    state = pending.get(uid)

    if not state:
        if update.effective_user.id == OWNER_ID:
            await handle_admin_text(update, context)
        return

    # ─── Custom amount charge ───
    if state.get("type") == "charge_custom":
        try:
            amount = int(update.message.text.strip().replace(",", "").replace("،", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد صحیح وارد کنید.")
            return
        kb = [
            [InlineKeyboardButton("📸 ارسال رسید", callback_data=f"charge_receipt_{amount}")],
            [InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet_menu")],
        ]
        await update.message.reply_text(
            f"💳 **افزایش موجودی:** {amount:,} تومان\n\n"
            f"🏦 **شماره کارت:**\n`{CARD_NUMBER}`\n👤 **به نام:** {CARD_NAME}\n\n"
            f"━━━━━━━━━━━━━━━━━\n💰 مبلغ را به شماره کارت واریز کنید.\n📸 سپس رسید پرداخت را ارسال کنید.",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
        pending[uid]["amount"] = amount
        pending[uid]["type"] = "charge"
        save_pending(pending)
        return

    # ─── User providing name for config (wallet payment) ───
    if state.get("type") == "config_wallet_name":
        name = update.message.text.strip()
        plan_data = state.get("plan_data")
        plan_id = state.get("plan")

        if not name or len(name) < 1:
            await update.message.reply_text("❌ لطفاً یک اسم وارد کنید.")
            return

        # Delete pending state
        del pending[uid]
        save_pending(pending)

        # Show loading
        await update.message.reply_text("⏳ **در حال ساخت کانفیگ...**\n\nلطفاً صبر کنید...", parse_mode="Markdown")

        # Create SpiderPanel user
        try:
            user_data = await spider.create_user(
                username=f"diaz-{name}",
                limit_gb=plan_data.get("limit_gb", 0),
                days=plan_data.get("days", 30),
            )

            if user_data and user_data.get("subscription_uuid"):
                sub_uuid = user_data["subscription_uuid"]
                # Get ALL configs from subscription endpoint
                all_configs = await spider.get_user_all_configs(sub_uuid)
                # Only keep VLESS+WS configs from Worker (the only ones that work)
                all_configs = [c for c in all_configs if "reality" not in c.lower() and c.strip()]
                if not all_configs and user_data.get("config"):
                    all_configs = [user_data["config"]]
                # Send configs to user
                kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
                header = (
                    f"✅ **کانفیگ شما آماده است!**\n\n"
                    f"📦 **پلن:** {plan_data['name']}\n"
                    f"👤 **اسم:** {name}\n"
                    f"⏰ **اعتبار:** {plan_data.get('days', 30)} روز\n"
                    f"📊 **حجم:** {plan_data.get('limit_gb', 0)} گیگ\n"
                    f"🔗 **اتصالات همزمان:** ۱\n\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                )
                await context.bot.send_message(
                    chat_id=int(uid), text=header, parse_mode="Markdown"
                )
                for i, cfg in enumerate(all_configs, 1):
                    label = "Reality+XHTTP" if "reality" in cfg else ("VLESS+WS" if "type=ws" in cfg else "XHTTP")
                    await context.bot.send_message(
                        chat_id=int(uid),
                        text=f"**{i}. {label}:**\n`{cfg}`",
                        parse_mode="Markdown"
                    )
                await context.bot.send_message(
                    chat_id=int(uid),
                    text="━━━━━━━━━━━━━━━━━\nاز خرید شما متشکریم! 🙏",
                    reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
                )
                # Notify admin
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        f"✅ **کانفیگ خودکار ساخته شد!**\n\n"
                        f"👤 **کاربر:** {uid}\n"
                        f"📝 **اسم:** {name}\n"
                        f"📦 **پلن:** {plan_data['name']}\n"
                        f"💰 **نوع پرداخت:** کیف پول\n"
                        f"🔗 **تعداد کانفیگ:** {len(all_configs)}"
                    ),
                    parse_mode="Markdown"
                )
                logger.info(f"Auto configs created for {uid}: {name} ({len(all_configs)} configs)")
            else:
                # SpiderPanel failed
                kb = [[InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")]]
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"⚠️ **خطا در ساخت کانفیگ!**\n\n"
                        f"لطفاً با پشتیبانی تماس بگیرید.\n💬 @{SUPPORT_USERNAME}\n"
                        f"━━━━━━━━━━━━━━━━━"
                    ),
                    reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
                )
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"⚠️ **خطا در ساخت خودکار کانفیگ!**\n\n👤 کاربر: {uid}\n📝 اسم: {name}\n📦 پلن: {plan_data['name']}\n\nلطفاً دستی بفرستید."
                )
        except Exception as e:
            logger.error(f"Error creating user for {uid}: {e}")
            kb = [[InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")]]
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"⚠️ **خطا در ساخت کانفیگ!**\n\nلطفاً با پشتیبانی تماس بگیرید.\n💬 @{SUPPORT_USERNAME}",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
            )
        return

    # ─── User providing name for config (receipt payment) ───
    if state.get("type") == "config_receipt_name":
        name = update.message.text.strip()
        plan_data = state.get("plan_data")
        plan_id = state.get("plan")

        if not name or len(name) < 1:
            await update.message.reply_text("❌ لطفاً یک اسم وارد کنید.")
            return

        # Delete pending state
        del pending[uid]
        save_pending(pending)

        # Show loading
        await update.message.reply_text("⏳ **در حال ساخت کانفیگ...**\n\nلطفاً صبر کنید...", parse_mode="Markdown")

        # Create SpiderPanel user
        try:
            user_data = await spider.create_user(
                username=f"diaz-{name}",
                limit_gb=plan_data.get("limit_gb", 0),
                days=plan_data.get("days", 30),
            )

            if user_data and user_data.get("subscription_uuid"):
                sub_uuid = user_data["subscription_uuid"]
                all_configs = await spider.get_user_all_configs(sub_uuid)
                # Only keep VLESS+WS configs from Worker (the only ones that work)
                all_configs = [c for c in all_configs if "reality" not in c.lower() and c.strip()]
                if not all_configs and user_data.get("config"):
                    all_configs = [user_data["config"]]
                kb = [[InlineKeyboardButton("🏠 بازگشت به صفحه اصلی", callback_data="back_main")]]
                header = (
                    f"✅ **کانفیگ شما آماده است!**\n\n"
                    f"📦 **پلن:** {plan_data['name']}\n"
                    f"👤 **اسم:** {name}\n"
                    f"⏰ **اعتبار:** {plan_data.get('days', 30)} روز\n"
                    f"📊 **حجم:** {plan_data.get('limit_gb', 0)} گیگ\n"
                    f"🔗 **اتصالات همزمان:** ۱\n\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                )
                await context.bot.send_message(
                    chat_id=int(uid), text=header, parse_mode="Markdown"
                )
                for i, cfg in enumerate(all_configs, 1):
                    label = "Reality+XHTTP" if "reality" in cfg else ("VLESS+WS" if "type=ws" in cfg else "XHTTP")
                    await context.bot.send_message(
                        chat_id=int(uid),
                        text=f"**{i}. {label}:**\n`{cfg}`",
                        parse_mode="Markdown"
                    )
                await context.bot.send_message(
                    chat_id=int(uid),
                    text="━━━━━━━━━━━━━━━━━\nاز خرید شما متشکریم! 🙏",
                    reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
                )
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        f"✅ **کانفیگ خودکار ساخته شد!**\n\n"
                        f"👤 **کاربر:** {uid}\n"
                        f"📝 **اسم:** {name}\n"
                        f"📦 **پلن:** {plan_data['name']}\n"
                        f"💰 **نوع پرداخت:** رسید\n"
                        f"🔗 **تعداد کانفیگ:** {len(all_configs)}"
                    ),
                    parse_mode="Markdown"
                )
                logger.info(f"Auto configs created (receipt) for {uid}: {name} ({len(all_configs)} configs)")
            else:
                kb = [[InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")]]
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"⚠️ **خطا در ساخت کانفیگ!**\n\nلطفاً با پشتیبانی تماس بگیرید.\n💬 @{SUPPORT_USERNAME}",
                    reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
                )
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"⚠️ **خطا در ساخت خودکار کانفیگ!**\n\n👤 کاربر: {uid}\n📝 اسم: {name}\n📦 پلن: {plan_data['name']}\n\nلطفاً دستی بفرستید."
                )
        except Exception as e:
            logger.error(f"Error creating user (receipt) for {uid}: {e}")
            kb = [[InlineKeyboardButton("💬 پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}")]]
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"⚠️ **خطا در ساخت کانفیگ!**\n\nلطفاً با پشتیبانی تماس بگیرید.\n💬 @{SUPPORT_USERNAME}",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
            )
        return

# ─── Main ─────────────────────────────────────────────────

async def post_init(application):
    logger.info("Logging in to SpiderPanel...")
    ok = await spider.login()
    if ok:
        logger.info("SpiderPanel connected! ✅")
    else:
        logger.warning("SpiderPanel login failed ⚠️")

async def post_shutdown(application):
    await spider.close()

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    logger.info(f"Starting Diaz Shop Bot... OWNER_ID={OWNER_ID}")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_member, pattern="^check_member$"))

    # Config purchase
    app.add_handler(CallbackQueryHandler(buy_config, pattern="^buy_config$"))
    app.add_handler(CallbackQueryHandler(select_config, pattern="^config_"))
    app.add_handler(CallbackQueryHandler(pay_config, pattern="^pay_config_"))
    app.add_handler(CallbackQueryHandler(pay_wallet_config, pattern="^pay_wallet_config_"))
    app.add_handler(CallbackQueryHandler(receipt_received, pattern="^receipt_(?!express_)"))

    # Express purchase
    app.add_handler(CallbackQueryHandler(buy_express, pattern="^buy_express$"))
    app.add_handler(CallbackQueryHandler(select_express, pattern="^express_"))
    app.add_handler(CallbackQueryHandler(pay_express, pattern="^pay_express_"))
    app.add_handler(CallbackQueryHandler(pay_wallet_express, pattern="^pay_wallet_express_"))
    app.add_handler(CallbackQueryHandler(receipt_express_received, pattern="^receipt_express_"))

    # Wallet
    # Free subscription
    app.add_handler(CallbackQueryHandler(free_sub_menu, pattern="^free_sub$"))
    app.add_handler(CallbackQueryHandler(claim_free_sub, pattern="^claim_free_sub$"))

    # Wallet
    app.add_handler(CallbackQueryHandler(wallet_menu, pattern="^wallet_menu$"))
    app.add_handler(CallbackQueryHandler(charge_wallet, pattern="^charge_wallet$"))
    app.add_handler(CallbackQueryHandler(charge_custom, pattern="^charge_custom$"))
    app.add_handler(CallbackQueryHandler(charge_amount, pattern="^charge_[0-9]+$"))
    app.add_handler(CallbackQueryHandler(charge_receipt_step, pattern="^charge_receipt_"))
    app.add_handler(CallbackQueryHandler(wallet_history, pattern="^wallet_history$"))

    # User panel & nav
    app.add_handler(CallbackQueryHandler(user_panel, pattern="^user_panel$"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))

    # Admin approve/reject
    app.add_handler(CallbackQueryHandler(approve_receipt, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_receipt, pattern="^reject_"))

    # Photos
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Text (name input, custom amount, admin link)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

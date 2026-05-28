"""
bot.py — Entry point utama
Daftarkan semua handler command dan message di sini.
"""

import logging
import re
import asyncio

from telegram import Update, BotCommand, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
    ContextTypes,
)

from config import BOT_TOKEN
from converter import convert_crypto
from commands import cmd_start, cmd_help, cmd_examples, cmd_supported, cmd_about, cmd_ping
from market import cmd_price, cmd_top, cmd_fear, cmd_market, cmd_compare

# ── Subscriber tracking: simpan user_id unik yang pernah pakai bot ────────────
_subscribers: set[int] = set()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Semaphore: maks 5 konversi bersamaan ─────────────────────────────────────
_semaphore = asyncio.Semaphore(5)

# ── Per-user rate limit: maks 1 request per 2 detik ──────────────────────────
_user_last_request: dict[int, float] = {}
_USER_COOLDOWN = 2.0  # detik

DEFAULT_TARGETS = ["USD", "IDR"]

_NUM = r"([\d]+(?:[.,][\d]+)?[kKmMbB]?)"
PATTERN_WITH_TARGET = re.compile(
    rf"^{_NUM}\s+([a-zA-Z]+)(?:\s+to)?\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*)$",
    re.IGNORECASE,
)
PATTERN_NO_TARGET = re.compile(
    rf"^{_NUM}\s+([a-zA-Z]+)$",
    re.IGNORECASE,
)

# Semua koin yang dikenal (untuk typo detection)
KNOWN_SYMBOLS = {
    "BTC","ETH","USDT","BNB","SOL","XRP","DOGE","ADA","AVAX","SHIB",
    "DOT","LINK","MATIC","TRX","TON","LTC","BCH","NEAR","UNI","XLM",
    "APT","OP","ARB","ATOM","FIL","VET","HBAR","ALGO","ICP","ETC",
    "MANA","SAND","AXS","GRT","AAVE","MKR","CRV","ENJ","ZEC","XMR",
    "DASH","XTZ","EOS","ZIL","BAT","CRO","FTM","CHZ","LRC","SUSHI",
    "YFI","CAKE","RUNE","LUNA","DYDX","IMX","LDO","PENDLE","JUP",
    "PYTH","WIF","BONK","PEPE","FLOKI","SUI","SEI","INJ","TIA","STRK",
    "NOT","RENDER","WLD","ZK","CYBER","HMSTR","BOME","IO","PIXEL",
}

KNOWN_FIATS = {
    "IDR","USD","EUR","GBP","JPY","KRW","CNY","SGD","MYR","THB",
    "PHP","VND","INR","AUD","CAD","CHF","HKD","NZD","TRY","BRL",
    "AED","SAR","RUB","UAH","PKR","BDT","EGP","NGN","ZAR","MAD",
}


def parse_amount(amount_str: str) -> float | None:
    s = amount_str.strip().lower()
    multiplier = 1
    if s.endswith("k"):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith("m"):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith("b"):
        multiplier = 1_000_000_000
        s = s[:-1]
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        value = float(s) * multiplier
    except ValueError:
        return None
    return value if value > 0 else None


def suggest_typo(symbol: str) -> str | None:
    """
    Deteksi typo sederhana: cari koin yang paling mirip
    menggunakan jarak karakter (difflib).
    """
    import difflib
    all_known = KNOWN_SYMBOLS | KNOWN_FIATS
    matches = difflib.get_close_matches(symbol.upper(), all_known, n=1, cutoff=0.7)
    return matches[0] if matches else None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    text = message.text.strip()

    match = PATTERN_WITH_TARGET.match(text)
    if match:
        amount_str = match.group(1)
        from_coin  = match.group(2).upper()
        targets    = match.group(3).upper().split()
    else:
        match = PATTERN_NO_TARGET.match(text)
        if not match:
            return
        amount_str = match.group(1)
        from_coin  = match.group(2).upper()
        targets    = DEFAULT_TARGETS

    amount = parse_amount(amount_str)
    if amount is None:
        return

    targets = [t for t in targets if t != from_coin]
    if not targets:
        return

    # ── Per-user cooldown: cegah spam ────────────────────────────────────────
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id:
        _subscribers.add(user_id)
    now = asyncio.get_event_loop().time()
    last = _user_last_request.get(user_id, 0)
    if now - last < _USER_COOLDOWN:
        return  # Diam saja, jangan balas — cegah spam loop
    _user_last_request[user_id] = now

    logger.info(f"Konversi: {amount} {from_coin} → {targets}")

    async with _semaphore:
        try:
            result_lines = await asyncio.wait_for(
                convert_crypto(amount, from_coin, targets),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            await message.reply_text("⏱ Request timeout. Coba lagi sebentar.")
            return
        except Exception as e:
            logger.error(f"convert_crypto error: {e}")
            await message.reply_text("⚠️ Terjadi error. Coba lagi.")
            return

    if result_lines is None:
        # API error (rate limit / timeout) — koin valid tapi data gagal diambil
        await message.reply_text(
            "⚠️ Gagal mengambil data harga\. "
            "CoinGecko sedang sibuk, coba lagi dalam beberapa detik\.",
            parse_mode="MarkdownV2"
        )
    elif result_lines:
        await message.reply_text("\n".join(result_lines), parse_mode="Markdown")
    else:
        # Koin benar-benar tidak ditemukan — baru tampilkan saran typo
        suggestion = suggest_typo(from_coin)
        # Pastikan saran bukan koin yang sama (mencegah "Maksud kamu BTC?" saat ketik BTC)
        if suggestion and suggestion.upper() != from_coin.upper():
            await message.reply_text(
                f"❌ Koin *{from_coin}* tidak ditemukan\\.\n"
                f"💡 Maksud kamu *{suggestion}*?",
                parse_mode="MarkdownV2"
            )
        else:
            await message.reply_text(
                f"❌ Koin *{from_coin}* tidak ditemukan\\. "
                f"Cek simbol di coingecko\.com",
                parse_mode="MarkdownV2"
            )


# ── Inline mode: ketik "@botusername 1 btc" di chat mana pun ─────────────────
async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return

    text = query.query.strip()
    if not text:
        return

    match = PATTERN_WITH_TARGET.match(text) or PATTERN_NO_TARGET.match(text)
    if not match:
        return

    if len(match.groups()) == 3:
        amount_str, from_coin, targets_str = match.groups()
        targets = targets_str.upper().split()
    else:
        amount_str, from_coin = match.groups()
        targets = DEFAULT_TARGETS

    from_coin = from_coin.upper()
    amount = parse_amount(amount_str)
    if not amount:
        return

    targets = [t for t in targets if t != from_coin]
    if not targets:
        return

    try:
        result_lines = await asyncio.wait_for(
            convert_crypto(amount, from_coin, targets),
            timeout=10.0
        )
    except Exception:
        return

    if not result_lines:
        return

    result_text = "\n".join(result_lines)

    from uuid import uuid4
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()),
            title=f"Konversi {amount_str} {from_coin}",
            description=" | ".join(result_lines[1:-1]),
            input_message_content=InputTextMessageContent(
                message_text=result_text,
                parse_mode="Markdown"
            )
        )
    ]
    await query.answer(results, cache_time=60)


# ── Setup command menu di Telegram ────────────────────────────────────────────
async def post_init(application: Application):
    try:
        await application.bot.set_my_commands([
            BotCommand("start",      "Penjelasan bot & cara pakai"),
            BotCommand("help",       "Semua command yang tersedia"),
            BotCommand("examples",   "Contoh-contoh input"),
            BotCommand("supported",  "Daftar koin & fiat populer"),
            BotCommand("price",      "Harga realtime satu koin"),
            BotCommand("top",        "Top 10 crypto by market cap"),
            BotCommand("fear",       "Crypto Fear & Greed Index"),
            BotCommand("market",     "Kondisi pasar global"),
            BotCommand("compare",    "Bandingkan dua koin"),
            BotCommand("subscriber", "Statistik pengguna bot"),
            BotCommand("about",      "Info bot & sumber data"),
            BotCommand("ping",       "Cek bot online"),
        ])
        logger.info("✅ Command menu berhasil didaftarkan ke Telegram.")
    except Exception as e:
        logger.error(f"❌ Gagal mendaftarkan command menu: {e}")


# ── /subscriber ───────────────────────────────────────────────────────────────
async def cmd_subscriber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = len(_subscribers)

    if count == 0:
        bar_filled = 0
    elif count < 10:
        bar_filled = 1
    elif count < 50:
        bar_filled = 3
    elif count < 100:
        bar_filled = 5
    elif count < 500:
        bar_filled = 7
    else:
        bar_filled = 10

    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    # Milestone label
    if count < 10:
        milestone = "🌱 Baru mulai"
    elif count < 50:
        milestone = "🚀 Berkembang"
    elif count < 100:
        milestone = "⭐ Populer"
    elif count < 500:
        milestone = "🔥 Trending"
    elif count < 1000:
        milestone = "💎 Elite"
    else:
        milestone = "👑 Legendary"

    text = (
        "👥 *Statistik Pengguna Bot*\n\n"
        f"`{bar}` {count}\n\n"
        f"📊 *Total Pengguna:* `{count:,}` orang\n"
        f"🏅 *Status:* {milestone}\n\n"
        "📌 *Info Bot:*\n"
        "• Data harga dari CoinGecko API\n"
        "• Kurs fiat dari ExchangeRate\\-API\n"
        "• Cache harga diperbarui setiap 60 detik\n"
        "• Mendukung 10\\.000\\+ koin CoinGecko\n"
        "• Mendukung 150\\+ mata uang fiat\n"
        "• Inline mode tersedia \\(@bot query\\)\n\n"
        "💡 _Pengguna dihitung sejak bot terakhir restart\\._"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("examples",   cmd_examples))
    app.add_handler(CommandHandler("supported",  cmd_supported))
    app.add_handler(CommandHandler("about",      cmd_about))
    app.add_handler(CommandHandler("ping",       cmd_ping))
    app.add_handler(CommandHandler("subscriber", cmd_subscriber))
    app.add_handler(CommandHandler("price",      cmd_price))
    app.add_handler(CommandHandler("top",        cmd_top))
    app.add_handler(CommandHandler("fear",       cmd_fear))
    app.add_handler(CommandHandler("market",     cmd_market))
    app.add_handler(CommandHandler("compare",    cmd_compare))

    # Inline query handler (ketik @botusername 1 btc di chat mana pun)
    app.add_handler(InlineQueryHandler(handle_inline))

    # Pesan biasa (konversi langsung)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot berjalan… tekan Ctrl+C untuk berhenti.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

"""
commands.py
Semua handler command /start /help /examples /supported /about /ping
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def _safe_reply(message, text: str, **kwargs):
    """Wrapper reply_text dengan error logging agar silent failure terdeteksi."""
    try:
        await message.reply_text(text, **kwargs)
    except Exception as e:
        logger.error(f"[commands] Gagal kirim pesan: {e}\nTeks: {text[:200]}")
        # Coba kirim versi plain text sebagai fallback
        try:
            plain = text.replace("\\", "").replace("*", "").replace("`", "")
            await message.reply_text(plain)
        except Exception as e2:
            logger.error(f"[commands] Fallback plain text juga gagal: {e2}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Kawan"
    # Escape nama user agar tidak merusak MarkdownV2
    safe_name = name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
    text = (
        f"👋 Halo, *{safe_name}*\\! Selamat datang di *Crypto Converter Bot* by SaberChan 🚀\n\n"
        "Bot ini bisa mengkonversi harga cryptocurrency secara *real\\-time* "
        "langsung di grup atau chat\\.\n\n"
        "📌 *Cara pakai:*\n"
        "`1 btc` → konversi ke USDT \\& IDR otomatis\n"
        "`1 eth idr` → konversi ETH ke IDR\n"
        "`1 btc idr usdt bnb` → multi target sekaligus\n"
        "`1k doge idr` → 1\\.000 DOGE ke IDR\n"
        "`0\\.5 sol usdt` → 0\\.5 SOL ke USDT\n\n"
        "Ketik /help untuk semua command\\."
    )
    await _safe_reply(update.message, text, parse_mode="MarkdownV2")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Daftar Command*\n\n"
        "/start \\- Penjelasan bot \\& contoh pakai\n"
        "/help \\- Tampilkan semua command ini\n"
        "/examples \\- Contoh\\-contoh input valid\n"
        "/supported \\- Daftar coin \\& fiat populer\n"
        "/about \\- Info bot \\& sumber data\n"
        "/ping \\- Cek bot online\n\n"
        "📊 *Command Data*\n\n"
        "/price `<coin>` \\- Harga realtime satu koin\n"
        "/top \\- Top 10 crypto by market cap\n"
        "/fear \\- Crypto Fear \\& Greed Index\n"
        "/market \\- Kondisi pasar saat ini\n"
        "/compare `<coin1>` `<coin2>` \\- Bandingkan dua koin\n\n"
        "💱 *Konversi Langsung* \\(tanpa command\\)\n\n"
        "`1 btc` → auto ke USDT \\& IDR\n"
        "`1 eth idr usdt` → multi target\n"
        "`1k sol idr` → 1\\.000 SOL ke IDR"
    )
    await _safe_reply(update.message, text, parse_mode="MarkdownV2")


async def cmd_examples(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💡 *Contoh Input Valid*\n\n"
        "🔹 *Format dasar:*\n"
        "`1 btc` → 1 BTC ke USDT \\& IDR\n"
        "`1 eth` → 1 ETH ke USDT \\& IDR\n"
        "`1 doge` → 1 DOGE ke USDT \\& IDR\n\n"
        "🔹 *Dengan target:*\n"
        "`1 btc idr` → BTC ke IDR\n"
        "`1 btc usdt` → BTC ke USDT\n"
        "`1 eth to idr` → ETH ke IDR\n\n"
        "🔹 *Multi target:*\n"
        "`1 btc idr usdt bnb` → BTC ke 3 target\n"
        "`1 sol idr usdt eth btc` → SOL ke 4 target\n\n"
        "🔹 *Suffix angka:*\n"
        "`1k doge idr` → 1\\.000 DOGE ke IDR\n"
        "`1\\.5k usdt idr` → 1\\.500 USDT ke IDR\n"
        "`2m shib usdt` → 2\\.000\\.000 SHIB ke USDT\n"
        "`1b pepe idr` → 1 Miliar PEPE ke IDR\n\n"
        "🔹 *Fiat ke crypto:*\n"
        "`1000000 idr btc` → 1 juta IDR ke BTC\n"
        "`100 usd eth` → 100 USD ke ETH\n\n"
        "🔹 *Command data:*\n"
        "`/price btc` → harga BTC sekarang\n"
        "`/compare btc eth` → bandingkan BTC vs ETH\n"
        "`/top` → top 10 crypto\n"
        "`/fear` → fear \\& greed index"
    )
    await _safe_reply(update.message, text, parse_mode="MarkdownV2")


async def cmd_supported(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🪙 *Crypto Populer yang Didukung*\n"
        "`BTC ETH USDT BNB SOL XRP DOGE ADA`\n"
        "`AVAX SHIB DOT LINK MATIC TRX TON LTC`\n"
        "`BCH NEAR UNI XLM APT ARB ATOM FIL`\n"
        "`PEPE WIF BONK FLOKI SUI SEI INJ TIA`\n"
        "`RENDER WLD NOT HMSTR BOME JUP PYTH`\n"
        "\\+ 10\\.000\\+ koin lain dari CoinGecko\n\n"
        "🏦 *Fiat yang Didukung*\n"
        "`IDR USD EUR GBP JPY KRW CNY SGD`\n"
        "`MYR THB PHP VND INR AUD CAD CHF`\n"
        "`HKD NZD TRY BRL AED SAR RUB UAH`\n"
        "`MAD EGP NGN KES ZAR PKR BDT`\n"
        "\\+ 150\\+ mata uang lain\n\n"
        "💡 Jika koin tidak ditemukan, cek simbol di coingecko\\.com"
    )
    await _safe_reply(update.message, text, parse_mode="MarkdownV2")


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Crypto Converter Bot*\n\n"
        "Bot konversi cryptocurrency real\\-time untuk Telegram\\.\n\n"
        "📡 *Sumber Data:*\n"
        "• [CoinGecko API](https://coingecko.com/api) \\- Harga crypto\n"
        "• [ExchangeRate\\-API](https://open.er-api.com) \\- Kurs fiat\n"
        "• [Alternative\\.me](https://alternative.me/crypto/fear-and-greed-index/) \\- Fear \\& Greed\n\n"
        "⚙️ *Teknologi:*\n"
        "• Python 3\\.10\\+\n"
        "• python\\-telegram\\-bot 21\\.x\n"
        "• aiohttp \\(async HTTP\\)\n\n"
        "🔄 *Cache:* Harga diperbarui setiap 60 detik\n"
        "🌐 *Rate limit:* Ditangani otomatis dengan retry"
    )
    await _safe_reply(update.message, text, parse_mode="MarkdownV2",
                      disable_web_page_preview=True)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _safe_reply(update.message, "🟢 Bot online dan siap\\!", parse_mode="MarkdownV2")
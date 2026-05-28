"""
market.py
Handler untuk command data pasar:
/price <coin>     - harga realtime
/top              - top 10 by market cap
/fear             - fear & greed index
/market           - kondisi pasar
/compare c1 c2   - bandingkan dua koin
"""

import aiohttp
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from converter import _resolve_id, _get_crypto_price_in_usd as _get_price_usd, POPULAR

logger = logging.getLogger(__name__)

CG_BASE = "https://api.coingecko.com/api/v3"


def _escape(text: str) -> str:
    """Escape karakter MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _fmt(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1:
        return f"${value:,.4f}"
    elif value >= 0.01:
        return f"${value:.6f}"
    else:
        return f"${value:.8f}"


def _pct(value: float) -> str:
    arrow = "🟢" if value >= 0 else "🔴"
    return f"{arrow} {value:+.2f}%"


# ── /price <coin> ─────────────────────────────────────────────────────────────
async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Contoh penggunaan: `/price btc`", parse_mode="MarkdownV2"
        )
        return

    symbol = context.args[0].upper()

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: resolve ID (pakai cache POPULAR → langsung, tanpa request)
            coin_id = await asyncio.wait_for(
                _resolve_id(session, symbol), timeout=8.0
            )
            if not coin_id:
                await update.message.reply_text(
                    f"❌ Koin `{_escape(symbol)}` tidak ditemukan\\.", parse_mode="MarkdownV2"
                )
                return

            # Step 2: ambil data pasar — pakai simple/price (ringan & cepat)
            # vs /coins/{id} yang berat dan sering timeout di free tier
            params = {
                "ids": coin_id,
                "vs_currencies": "usd,idr",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "false",
                "precision": "full",
            }
            async with session.get(
                f"{CG_BASE}/simple/price",
                params=params,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                raw = await resp.json()

    except asyncio.TimeoutError:
        await update.message.reply_text(
            "⏱ Timeout\\. CoinGecko lambat, coba lagi sebentar\\.", parse_mode="MarkdownV2"
        )
        return
    except Exception as e:
        logger.error(f"[market] cmd_price error: {e}")
        await update.message.reply_text("❌ Gagal mengambil data\\.", parse_mode="MarkdownV2")
        return

    d = raw.get(coin_id, {})
    if not d:
        await update.message.reply_text(
            f"❌ Tidak ada data untuk `{_escape(symbol)}`\\.", parse_mode="MarkdownV2"
        )
        return

    price     = d.get("usd", 0) or 0
    price_idr = d.get("idr", 0) or 0
    chg_24h   = d.get("usd_24h_change", 0) or 0
    cap       = d.get("usd_market_cap", 0) or 0
    vol       = d.get("usd_24hr_vol", 0) or 0

    def fu(v): return _escape(_fmt(v))
    def fi(v): return _escape(f"Rp {v:,.0f}")

    text = (
        f"💰 *{_escape(symbol)}*\n\n"
        f"💵 USD: `{fu(price)}`\n"
        f"🇮🇩 IDR: `{fi(price_idr)}`\n\n"
        f"📈 *Perubahan 24h:* {_escape(_pct(chg_24h))}\n\n"
        f"🏦 Market Cap: `{fu(cap)}`\n"
        f"📊 Volume 24h: `{fu(vol)}`\n\n"
        f"_📡 CoinGecko real\\-time_"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ── /top ──────────────────────────────────────────────────────────────────────
async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loading_msg = await update.message.reply_text("📊 Mengambil data top 10\\.\\.\\.", parse_mode="MarkdownV2")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CG_BASE}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 10,
                    "page": 1,
                    "price_change_percentage": "24h"
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                coins = await resp.json()
    except Exception:
        await loading_msg.delete()
        await update.message.reply_text("❌ Gagal mengambil data\\.", parse_mode="MarkdownV2")
        return

    lines = ["🏆 *Top 10 Crypto by Market Cap*\n"]
    for i, coin in enumerate(coins, 1):
        name   = _escape(coin.get("name", ""))
        sym    = _escape(coin.get("symbol", "").upper())
        price  = coin.get("current_price", 0)
        chg    = coin.get("price_change_percentage_24h", 0) or 0
        arrow  = "🟢" if chg >= 0 else "🔴"
        price_str = _escape(_fmt(price))
        chg_str   = _escape(f"{chg:+.2f}%")
        lines.append(f"{i}\\. *{name}* \\({sym}\\)\n   `{price_str}` {arrow} {chg_str}")

    await loading_msg.delete()
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


# ── /fear ─────────────────────────────────────────────────────────────────────
async def cmd_fear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                data = await resp.json()
        item  = data["data"][0]
        value = int(item["value"])
        label = item["value_classification"]
    except Exception:
        await update.message.reply_text("❌ Gagal mengambil data Fear \\& Greed\\.", parse_mode="MarkdownV2")
        return

    # Emoji bar
    filled = round(value / 10)
    bar = "█" * filled + "░" * (10 - filled)

    if value <= 24:
        mood, emoji = "Extreme Fear", "😱"
    elif value <= 44:
        mood, emoji = "Fear", "😨"
    elif value <= 54:
        mood, emoji = "Neutral", "😐"
    elif value <= 74:
        mood, emoji = "Greed", "😏"
    else:
        mood, emoji = "Extreme Greed", "🤑"

    text = (
        f"😰 *Crypto Fear \\& Greed Index*\n\n"
        f"`{_escape(bar)}`\n\n"
        f"Nilai: *{_escape(str(value))}/100*\n"
        f"Status: {emoji} *{_escape(mood)}*\n\n"
        f"_Sumber: alternative\\.me_"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ── /market ───────────────────────────────────────────────────────────────────
async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loading_msg = await update.message.reply_text("🌐 Mengambil data pasar\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CG_BASE}/global",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                raw = await resp.json()
        d = raw["data"]
    except Exception:
        await loading_msg.delete()
        await update.message.reply_text("❌ Gagal mengambil data market\\.", parse_mode="MarkdownV2")
        return

    cap       = d.get("total_market_cap", {}).get("usd", 0)
    vol       = d.get("total_volume", {}).get("usd", 0)
    btc_dom   = d.get("market_cap_percentage", {}).get("btc", 0)
    eth_dom   = d.get("market_cap_percentage", {}).get("eth", 0)
    chg_24h   = d.get("market_cap_change_percentage_24h_usd", 0) or 0
    n_coins   = d.get("active_cryptocurrencies", 0)

    trend = "🟢 *BULLISH*" if chg_24h >= 0 else "🔴 *BEARISH*"

    text = (
        f"🌐 *Global Crypto Market*\n\n"
        f"Tren: {trend}\n"
        f"Perubahan 24h: {_escape(_pct(chg_24h))}\n\n"
        f"💰 Total Market Cap: `{_escape(_fmt(cap))}`\n"
        f"📊 Volume 24h: `{_escape(_fmt(vol))}`\n\n"
        f"🟠 BTC Dominance: `{_escape(f'{btc_dom:.1f}%')}`\n"
        f"🔵 ETH Dominance: `{_escape(f'{eth_dom:.1f}%')}`\n\n"
        f"🪙 Koin Aktif: `{_escape(str(n_coins))}`"
    )
    await loading_msg.delete()
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ── /compare coin1 coin2 ──────────────────────────────────────────────────────
async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Gunakan: `/compare btc eth`", parse_mode="MarkdownV2"
        )
        return

    sym1, sym2 = context.args[0].upper(), context.args[1].upper()
    loading_msg = await update.message.reply_text(
        f"🔍 Membandingkan *{_escape(sym1)}* vs *{_escape(sym2)}*\\.\\.\\.",
        parse_mode="MarkdownV2"
    )

    async with aiohttp.ClientSession() as session:
        id1 = await _resolve_id(session, sym1)
        id2 = await _resolve_id(session, sym2)

        if not id1:
            await loading_msg.delete()
            await update.message.reply_text(f"❌ Koin `{_escape(sym1)}` tidak ditemukan\\.", parse_mode="MarkdownV2")
            return
        if not id2:
            await loading_msg.delete()
            await update.message.reply_text(f"❌ Koin `{_escape(sym2)}` tidak ditemukan\\.", parse_mode="MarkdownV2")
            return

        try:
            ids_param = f"{id1},{id2}"
            async with session.get(
                f"{CG_BASE}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": ids_param,
                    "price_change_percentage": "1h,24h,7d"
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                coins = await resp.json()
        except Exception:
            await loading_msg.delete()
            await update.message.reply_text("❌ Gagal mengambil data\\.", parse_mode="MarkdownV2")
            return

    if len(coins) < 2:
        await loading_msg.delete()
        await update.message.reply_text("❌ Tidak bisa mengambil data salah satu koin\\.", parse_mode="MarkdownV2")
        return

    # Pastikan urutan sesuai sym1, sym2
    coin_map = {c["symbol"].upper(): c for c in coins}
    c1 = coin_map.get(sym1, coins[0])
    c2 = coin_map.get(sym2, coins[1])

    def row(coin):
        p    = _escape(_fmt(coin.get("current_price", 0)))
        cap  = _escape(_fmt(coin.get("market_cap", 0)))
        chg  = coin.get("price_change_percentage_24h", 0) or 0
        chg7 = coin.get("price_change_percentage_7d_in_currency", 0) or 0
        rank = _escape(str(coin.get("market_cap_rank", "?")))
        name = _escape(coin.get("name", ""))
        sym  = _escape(coin.get("symbol", "").upper())
        return name, sym, p, cap, _escape(_pct(chg)), _escape(_pct(chg7)), rank

    n1, s1, p1, mc1, c24_1, c7_1, r1 = row(c1)
    n2, s2, p2, mc2, c24_2, c7_2, r2 = row(c2)

    text = (
        f"⚔️ *{n1}* vs *{n2}*\n\n"
        f"{'Metrik':<14} {s1:<12} {s2}\n"
        f"{'─'*36}\n"
        f"Harga USD    `{p1}` vs `{p2}`\n"
        f"Market Cap   `{mc1}` vs `{mc2}`\n"
        f"24h          {c24_1} vs {c24_2}\n"
        f"7 Hari       {c7_1} vs {c7_2}\n"
        f"Rank         \\#{r1} vs \\#{r2}"
    )
    # Hapus pesan loading, kirim hasil
    await loading_msg.delete()
    await update.message.reply_text(text, parse_mode="MarkdownV2")
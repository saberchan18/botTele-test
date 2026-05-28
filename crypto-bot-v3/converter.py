"""
converter.py
Mengambil harga real-time dari CoinGecko API (gratis, tanpa API key).
Mendukung semua koin yang terdaftar di CoinGecko.
Mendukung semua mata uang fiat dunia via ExchangeRate-API.
"""

import aiohttp
import asyncio
import logging
import time
from typing import List, Optional
from currency import get_fiat_rate_async, is_fiat, normalize_fiat

logger = logging.getLogger(__name__)

COINGECKO_BASE  = "https://api.coingecko.com/api/v3"
SEARCH_URL      = f"{COINGECKO_BASE}/search"
PRICE_URL       = f"{COINGECKO_BASE}/simple/price"

# Cache sederhana: {symbol: coingecko_id}
_symbol_cache: dict[str, str] = {}

# ── Price cache: {coin_id: (price_usd, timestamp)} ────────────────────────────
# Mengurangi API call ke CoinGecko secara drastis saat banyak user
_price_cache: dict[str, tuple[float, float]] = {}
_PRICE_CACHE_TTL: float = 60.0  # detik — harga stale max 60 detik

# ── Simbol populer → CoinGecko ID ─────────────────────────────────────────────
POPULAR: dict[str, str] = {
    "BTC": "bitcoin",       "ETH": "ethereum",        "USDT": "tether",
    "BNB": "binancecoin",   "SOL": "solana",           "USDC": "usd-coin",
    "XRP": "ripple",        "DOGE": "dogecoin",        "ADA": "cardano",
    "AVAX": "avalanche-2",  "SHIB": "shiba-inu",       "DOT": "polkadot",
    "LINK": "chainlink",    "MATIC": "matic-network",  "TRX": "tron",
    "TON": "the-open-network","LTC": "litecoin",       "BCH": "bitcoin-cash",
    "NEAR": "near",         "UNI": "uniswap",          "XLM": "stellar",
    "APT": "aptos",         "OP":  "optimism",         "ARB": "arbitrum",
    "ATOM": "cosmos",       "FIL": "filecoin",         "VET": "vechain",
    "HBAR": "hedera-hashgraph","ALGO": "algorand",     "ICP": "internet-computer",
    "EGLD": "elrond-erd-2", "THETA": "theta-token",    "ETC": "ethereum-classic",
    "MANA": "decentraland", "SAND": "the-sandbox",     "AXS": "axie-infinity",
    "GRT": "the-graph",     "AAVE": "aave",            "MKR": "maker",
    "SNX": "synthetix-network-token","COMP": "compound-governance-token",
    "CRV": "curve-dao-token","1INCH": "1inch",         "ENJ": "enjincoin",
    "ZEC": "zcash",         "XMR": "monero",           "DASH": "dash",
    "NEO": "neo",           "IOTA": "iota",            "XTZ": "tezos",
    "EOS": "eos",           "ONT": "ontology",         "ZIL": "zilliqa",
    "WAVES": "waves",       "ICX": "icon",             "QTUM": "qtum",
    "LSK": "lisk",          "STEEM": "steem",          "BAT": "basic-attention-token",
    "KCS": "kucoin-shares", "HT": "huobi-token",       "OKB": "okb",
    "CRO": "crypto-com-chain","GT": "gatechain-token", "WOO": "woo-network",
    "FTM": "fantom",        "ONE": "harmony",          "FLOW": "flow",
    "CHZ": "chiliz",        "HOT": "holotoken",        "ZRX": "0x",
    "LRC": "loopring",      "BAL": "balancer",         "SUSHI": "sushi",
    "YFI": "yearn-finance", "CAKE": "pancakeswap-token","RUNE": "thorchain",
    "LUNA": "terra-luna-2", "SRM": "serum",            "RAY": "raydium",
    "DYDX": "dydx",         "IMX": "immutable-x",      "LDO": "lido-dao",
    "RPL": "rocket-pool",   "PENDLE": "pendle",        "JUP": "jupiter-exchange-solana",
    "PYTH": "pyth-network", "WIF": "dogwifcoin",       "BONK": "bonk",
    "PEPE": "pepe",         "FLOKI": "floki",          "BABYDOGE": "baby-doge-coin",
    "SUI": "sui",           "SEI": "sei-network",      "INJ": "injective-protocol",
    "TIA": "celestia",      "STRK": "starknet",        "MANTA": "manta-network",
    "JTO": "jito-governance-token","BOME": "book-of-meme",
    "NOT": "notcoin",       "RENDER": "render-token",  "WLD": "worldcoin-org",
    "ZK": "zksync",         "CYBER": "cyberconnect",   "PIXEL": "pixels",
}


async def _resolve_id(session: aiohttp.ClientSession, symbol: str) -> Optional[str]:
    """Kembalikan CoinGecko ID untuk simbol koin. Gunakan cache."""
    if symbol in _symbol_cache:
        return _symbol_cache[symbol]

    if symbol in POPULAR:
        _symbol_cache[symbol] = POPULAR[symbol]
        return POPULAR[symbol]

    # Fallback: cari via CoinGecko search API — retry sampai 3x
    for attempt in range(3):
        try:
            async with session.get(
                SEARCH_URL,
                params={"query": symbol},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 429:
                    # Rate limited — tunggu sebentar lalu retry
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"[converter] Rate limit CoinGecko search, retry {attempt+1} dalam {wait}s")
                    await asyncio.sleep(wait)
                    continue
                data = await resp.json()
                for coin in data.get("coins", []):
                    if coin["symbol"].upper() == symbol:
                        _symbol_cache[symbol] = coin["id"]
                        logger.info(f"[converter] Resolved {symbol} → {coin['id']} via search")
                        return coin["id"]
                # Search berhasil tapi tidak ada hasil → tidak perlu retry
                logger.info(f"[converter] Koin {symbol} tidak ditemukan di CoinGecko search")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"[converter] Timeout search {symbol} (attempt {attempt+1})")
        except Exception as e:
            logger.warning(f"[converter] Search error untuk {symbol}: {e}")
        if attempt < 2:
            await asyncio.sleep(1)

    return None


async def _get_crypto_price_in_usd(
    session: aiohttp.ClientSession, coin_id: str
) -> Optional[float]:
    """Ambil harga koin dalam USD dari CoinGecko, dengan cache 60 detik."""
    now = time.time()
    cached = _price_cache.get(coin_id)
    if cached and now - cached[1] < _PRICE_CACHE_TTL:
        return cached[0]

    try:
        params = {"ids": coin_id, "vs_currencies": "usd"}
        async with session.get(
            PRICE_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            data = await resp.json()
            price = data.get(coin_id, {}).get("usd")
            if price is not None:
                _price_cache[coin_id] = (price, now)
            return price
    except Exception as e:
        logger.warning(f"[converter] Price error untuk {coin_id}: {e}")
        # Kembalikan nilai cache lama jika ada (lebih baik stale data daripada error)
        return cached[0] if cached else None


async def _get_prices_batch(
    session: aiohttp.ClientSession, coin_ids: list[str]
) -> dict[str, float]:
    """
    Ambil harga banyak koin sekaligus dalam 1 API call.
    Return dict {coin_id: price_usd}. Koin yang gagal tidak masuk dict.
    Pakai cache jika masih fresh; hanya fetch yang sudah expired.
    """
    now = time.time()
    result: dict[str, float] = {}
    to_fetch: list[str] = []

    for coin_id in coin_ids:
        cached = _price_cache.get(coin_id)
        if cached and now - cached[1] < _PRICE_CACHE_TTL:
            result[coin_id] = cached[0]
        else:
            to_fetch.append(coin_id)

    if not to_fetch:
        return result

    try:
        params = {"ids": ",".join(to_fetch), "vs_currencies": "usd"}
        async with session.get(
            PRICE_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()
            for coin_id in to_fetch:
                price = data.get(coin_id, {}).get("usd")
                if price is not None:
                    _price_cache[coin_id] = (price, now)
                    result[coin_id] = price
                else:
                    # Fallback ke cache lama jika ada
                    old_cached = _price_cache.get(coin_id)
                    if old_cached:
                        result[coin_id] = old_cached[0]
    except Exception as e:
        logger.warning(f"[converter] Batch price error: {e}")
        # Fallback semua ke cache lama
        for coin_id in to_fetch:
            old_cached = _price_cache.get(coin_id)
            if old_cached:
                result[coin_id] = old_cached[0]

    return result


def _fmt(value: float) -> str:
    """Format angka: besar → 2 desimal, kecil → presisi lebih."""
    if value >= 1_000_000_000:
        return f"{value:,.0f}"
    elif value >= 1_000_000:
        return f"{value:,.2f}"
    elif value >= 1:
        return f"{value:,.4f}"
    elif value >= 0.01:
        return f"{value:.6f}"
    elif value >= 0.000001:
        return f"{value:.8f}"
    else:
        return f"{value:.10f}"


# ── Emoji bendera per kode mata uang ──────────────────────────────────────────
# Dipakai untuk mempercantik output fiat
_FIAT_EMOJI: dict[str, str] = {
    "IDR": "🇮🇩", "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "CNY": "🇨🇳", "CNH": "🇨🇳", "KRW": "🇰🇷", "SGD": "🇸🇬", "HKD": "🇭🇰",
    "TWD": "🇹🇼", "MYR": "🇲🇾", "THB": "🇹🇭", "PHP": "🇵🇭", "VND": "🇻🇳",
    "INR": "🇮🇳", "PKR": "🇵🇰", "BDT": "🇧🇩", "LKR": "🇱🇰", "NPR": "🇳🇵",
    "AED": "🇦🇪", "SAR": "🇸🇦", "QAR": "🇶🇦", "KWD": "🇰🇼", "BHD": "🇧🇭",
    "OMR": "🇴🇲", "JOD": "🇯🇴", "ILS": "🇮🇱", "TRY": "🇹🇷", "RUB": "🇷🇺",
    "UAH": "🇺🇦", "PLN": "🇵🇱", "CZK": "🇨🇿", "HUF": "🇭🇺", "RON": "🇷🇴",
    "SEK": "🇸🇪", "NOK": "🇳🇴", "DKK": "🇩🇰", "CHF": "🇨🇭", "AUD": "🇦🇺",
    "NZD": "🇳🇿", "CAD": "🇨🇦", "MXN": "🇲🇽", "BRL": "🇧🇷", "ARS": "🇦🇷",
    "CLP": "🇨🇱", "COP": "🇨🇴", "PEN": "🇵🇪", "NGN": "🇳🇬", "ZAR": "🇿🇦",
    "KES": "🇰🇪", "GHS": "🇬🇭", "EGP": "🇪🇬", "MAD": "🇲🇦", "KZT": "🇰🇿",
    "MMK": "🇲🇲", "KHR": "🇰🇭", "BND": "🇧🇳", "MNT": "🇲🇳", "GEL": "🇬🇪",
    "AMD": "🇦🇲", "AZN": "🇦🇿", "UZS": "🇺🇿", "IRR": "🇮🇷", "IQD": "🇮🇶",
}


def _fiat_emoji(code: str) -> str:
    """Return emoji bendera untuk kode fiat, default 🏦 jika tidak ada."""
    return _FIAT_EMOJI.get(code.upper(), "🏦")


async def convert_crypto(
    amount: float, from_symbol: str, targets: List[str]
) -> Optional[List[str]]:
    """
    Konversi `amount` dari `from_symbol` ke setiap simbol di `targets`.
    - from_symbol bisa crypto (BTC, ETH, dll) atau fiat (IDR, JPY, dll)
    - targets bisa campur crypto dan fiat apapun

    Return:
      - List[str]  → berhasil, berisi baris hasil (Markdown)
      - []         → from_symbol tidak dikenal / tidak ditemukan
      - None       → API error (rate limit, timeout, dsb) — bukan salah user
    """
    async with aiohttp.ClientSession() as session:

        # ── Step 1: Hitung nilai dalam USD ────────────────────────────────────
        if is_fiat(from_symbol):
            iso_from = normalize_fiat(from_symbol)
            rate = await get_fiat_rate_async(iso_from)
            if rate is None or rate == 0:
                logger.warning(f"[converter] Tidak dapat rate untuk fiat {iso_from}")
                # Fiat dikenal tapi data tidak tersedia → API error
                return None
            usd_amount = amount / rate
            emoji_from = _fiat_emoji(iso_from)
            from_display = f"{emoji_from} {_fmt(amount)} {iso_from}"
        else:
            from_id = await _resolve_id(session, from_symbol)
            if from_id is None:
                # Koin benar-benar tidak dikenal
                logger.warning(f"[converter] Koin tidak ditemukan: {from_symbol}")
                return []
            price_usd = await _get_crypto_price_in_usd(session, from_id)
            if price_usd is None:
                # Koin ada di CoinGecko tapi harga gagal diambil → API error
                logger.warning(f"[converter] Tidak dapat harga USD untuk {from_symbol}")
                return None
            usd_amount = amount * price_usd
            from_display = f"🪙 {_fmt(amount)} {from_symbol}"

        # ── Step 2: Resolve semua target crypto sekaligus ─────────────────────
        crypto_targets = [t for t in targets if not is_fiat(t)]
        fiat_targets   = [t for t in targets if is_fiat(t)]

        # Resolve semua ID crypto (masih sequential tapi pakai cache)
        target_id_map: dict[str, Optional[str]] = {}
        for t in crypto_targets:
            target_id_map[t] = await _resolve_id(session, t)

        # Batch price request untuk semua crypto target yang berhasil di-resolve
        resolved_ids = [tid for tid in target_id_map.values() if tid is not None]
        # Tambahkan juga ID from_symbol jika sudah ada agar cache terisi
        batch_prices = await _get_prices_batch(session, resolved_ids) if resolved_ids else {}

        # ── Step 3: Susun baris hasil ─────────────────────────────────────────
        lines: List[str] = [f"💱 *Konversi {from_display}*\n"]

        for target in targets:
            display_target = target
            if is_fiat(target):
                iso_target = normalize_fiat(target)
                display_target = iso_target
                rate = await get_fiat_rate_async(iso_target)
                if rate is None:
                    lines.append(f"❓ *{display_target}*: data tidak tersedia")
                    continue
                result = usd_amount * rate
                emoji = _fiat_emoji(iso_target)
                lines.append(f"{emoji} *{display_target}*: `{_fmt(result)}`")
            else:
                target_id = target_id_map.get(target)
                if target_id is None:
                    lines.append(f"❓ *{target}*: koin tidak ditemukan")
                    continue
                target_price_usd = batch_prices.get(target_id)
                if target_price_usd is None or target_price_usd == 0:
                    lines.append(f"❓ *{target}*: harga tidak tersedia")
                    continue
                result = usd_amount / target_price_usd
                lines.append(f"🪙 *{target}*: `{_fmt(result)}`")

        lines.append(f"\n_📡 CoinGecko + ExchangeRate-API • real-time_")
        return lines
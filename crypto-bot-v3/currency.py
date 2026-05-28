"""
currency.py
Menyediakan konversi semua mata uang fiat dunia.
Menggunakan ExchangeRate-API (https://open.er-api.com) — gratis, tanpa API key.
Cache rate selama 1 jam agar tidak spam request.
"""

import asyncio
import aiohttp
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Endpoint ───────────────────────────────────────────────────────────────────
EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"

# ── Cache ──────────────────────────────────────────────────────────────────────
_rates_cache: dict[str, float] = {}   # {"IDR": 16200.0, "JPY": 157.3, ...}
_cache_timestamp: float = 0.0
_CACHE_TTL: float = 3600.0            # 1 jam

# ── Daftar lengkap kode fiat ISO 4217 yang dikenali ───────────────────────────
# Digunakan untuk membedakan fiat vs crypto di bot.py
FIAT_SYMBOLS: set[str] = {
    # Asia Tenggara
    "IDR",  # Indonesia Rupiah
    "MYR",  # Malaysia Ringgit
    "SGD",  # Singapura Dolar
    "THB",  # Thailand Baht
    "PHP",  # Filipina Peso
    "VND",  # Vietnam Dong
    "MMK",  # Myanmar Kyat
    "KHR",  # Kamboja Riel
    "LAK",  # Laos Kip
    "BND",  # Brunei Dolar

    # Asia Timur
    "JPY",  # Jepang Yen
    "CNY",  # China Yuan Renminbi
    "CNH",  # China Yuan (offshore)
    "KRW",  # Korea Selatan Won
    "TWD",  # Taiwan Dolar
    "HKD",  # Hong Kong Dolar
    "MOP",  # Macau Pataca
    "MNT",  # Mongolia Tugrik

    # Asia Selatan
    "INR",  # India Rupee
    "PKR",  # Pakistan Rupee
    "BDT",  # Bangladesh Taka
    "LKR",  # Sri Lanka Rupee
    "NPR",  # Nepal Rupee
    "BTN",  # Bhutan Ngultrum
    "MVR",  # Maladewa Rufiyaa
    "AFN",  # Afghanistan Afghani

    # Asia Tengah
    "KZT",  # Kazakhstan Tenge
    "UZS",  # Uzbekistan Som
    "TMT",  # Turkmenistan Manat
    "KGS",  # Kyrgyzstan Som
    "TJS",  # Tajikistan Somoni

    # Asia Barat / Timur Tengah
    "AED",  # UAE Dirham
    "SAR",  # Arab Saudi Riyal
    "QAR",  # Qatar Riyal
    "KWD",  # Kuwait Dinar
    "BHD",  # Bahrain Dinar
    "OMR",  # Oman Riyal
    "JOD",  # Yordania Dinar
    "ILS",  # Israel Shekel
    "LBP",  # Lebanon Pound
    "SYP",  # Suriah Pound
    "IQD",  # Irak Dinar
    "IRR",  # Iran Rial
    "YER",  # Yaman Rial
    "TRY",  # Turki Lira
    "GEL",  # Georgia Lari
    "AMD",  # Armenia Dram
    "AZN",  # Azerbaijan Manat

    # Eropa
    "EUR",  # Euro
    "GBP",  # Inggris Pound
    "CHF",  # Swiss Franc
    "NOK",  # Norwegia Krone
    "SEK",  # Swedia Krona
    "DKK",  # Denmark Krone
    "ISK",  # Islandia Krona
    "PLN",  # Polandia Zloty
    "CZK",  # Ceko Koruna
    "HUF",  # Hungaria Forint
    "RON",  # Romania Leu
    "BGN",  # Bulgaria Lev
    "HRK",  # Kroasia Kuna
    "RSD",  # Serbia Dinar
    "BAM",  # Bosnia Mark
    "MKD",  # Makedonia Denar
    "ALL",  # Albania Lek
    "MDL",  # Moldova Leu
    "UAH",  # Ukraina Hryvnia
    "RUB",  # Rusia Rubel
    "BYN",  # Belarus Rubel
    "GBP",  # Inggris Pound (duplikat aman)

    # Amerika Utara
    "USD",  # Amerika Serikat Dolar
    "CAD",  # Kanada Dolar
    "MXN",  # Meksiko Peso
    "GTQ",  # Guatemala Quetzal
    "BZD",  # Belize Dolar
    "HNL",  # Honduras Lempira
    "NIO",  # Nikaragua Cordoba
    "CRC",  # Kosta Rika Colon
    "PAB",  # Panama Balboa
    "CUP",  # Kuba Peso
    "DOP",  # Dominika Peso
    "HTG",  # Haiti Gourde
    "JMD",  # Jamaika Dolar
    "TTD",  # Trinidad Dolar
    "BBD",  # Barbados Dolar
    "XCD",  # Karibia Timur Dolar
    "BSD",  # Bahama Dolar

    # Amerika Selatan
    "BRL",  # Brasil Real
    "ARS",  # Argentina Peso
    "CLP",  # Chile Peso
    "COP",  # Kolombia Peso
    "PEN",  # Peru Sol
    "VES",  # Venezuela Bolivar
    "BOB",  # Bolivia Boliviano
    "PYG",  # Paraguay Guarani
    "UYU",  # Uruguay Peso
    "GYD",  # Guyana Dolar
    "SRD",  # Suriname Dolar

    # Afrika Utara
    "EGP",  # Mesir Pound
    "DZD",  # Aljazair Dinar
    "MAD",  # Maroko Dirham
    "TND",  # Tunisia Dinar
    "LYD",  # Libya Dinar
    "SDG",  # Sudan Pound

    # Afrika Barat
    "NGN",  # Nigeria Naira
    "GHS",  # Ghana Cedi
    "XOF",  # Afrika Barat CFA Franc
    "XAF",  # Afrika Tengah CFA Franc
    "GMD",  # Gambia Dalasi
    "GNF",  # Guinea Franc
    "SLL",  # Sierra Leone Leone
    "LRD",  # Liberia Dolar
    "CVE",  # Tanjung Verde Escudo
    "SEN",  # (alias Senegal XOF)

    # Afrika Timur
    "KES",  # Kenya Shilling
    "TZS",  # Tanzania Shilling
    "UGX",  # Uganda Shilling
    "ETB",  # Etiopia Birr
    "SOS",  # Somalia Shilling
    "DJF",  # Djibouti Franc
    "ERN",  # Eritrea Nakfa
    "RWF",  # Rwanda Franc
    "BIF",  # Burundi Franc
    "MWK",  # Malawi Kwacha
    "ZMW",  # Zambia Kwacha
    "MZN",  # Mozambik Metical
    "MGA",  # Madagaskar Ariary
    "SCR",  # Seychelles Rupee
    "KMF",  # Komoro Franc
    "MUR",  # Mauritius Rupee

    # Afrika Selatan
    "ZAR",  # Afrika Selatan Rand
    "BWP",  # Botswana Pula
    "NAD",  # Namibia Dolar
    "SZL",  # Eswatini Lilangeni
    "LSL",  # Lesotho Loti
    "ZWL",  # Zimbabwe Dolar
    "AOA",  # Angola Kwanza
    "CDF",  # Kongo Franc

    # Oseania & Pasifik
    "AUD",  # Australia Dolar
    "NZD",  # Selandia Baru Dolar
    "PGK",  # Papua Nugini Kina
    "FJD",  # Fiji Dolar
    "SBD",  # Solomon Dolar
    "VUV",  # Vanuatu Vatu
    "WST",  # Samoa Tala
    "TOP",  # Tonga Pa'anga
    "XPF",  # Polinesia Prancis Franc

    # Alias populer (non-standar tapi sering dipakai)
    "YUAN", # alias CNY
    "RMB",  # alias CNY
    "WON",  # alias KRW
    "BAHT", # alias THB
    "PESO", # alias generik
    "POUND",# alias GBP
}

# ── Alias non-standar → kode ISO ──────────────────────────────────────────────
FIAT_ALIAS: dict[str, str] = {
    "YUAN":  "CNY",
    "RMB":   "CNY",
    "WON":   "KRW",
    "BAHT":  "THB",
    "POUND": "GBP",
    "EURO":  "EUR",
    "BUCK":  "USD",
    "RUPIAH":"IDR",
    "RUPEE": "INR",
    "RUBLE": "RUB",
    "FRANC": "CHF",
    "REAL":  "BRL",
    "PESO":  "MXN",  # default peso = Meksiko
}


def normalize_fiat(symbol: str) -> str:
    """Normalisasi simbol fiat: alias → kode ISO standar."""
    upper = symbol.upper()
    return FIAT_ALIAS.get(upper, upper)


def is_fiat(symbol: str) -> bool:
    """Return True jika simbol adalah mata uang fiat (bukan crypto)."""
    upper = symbol.upper()
    return upper in FIAT_SYMBOLS or upper in FIAT_ALIAS


async def _fetch_rates() -> bool:
    """
    Fetch semua rate dari ExchangeRate-API (base USD).
    Return True jika berhasil.
    """
    global _rates_cache, _cache_timestamp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                EXCHANGE_RATE_URL,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if data.get("result") == "success":
                    _rates_cache = data["rates"]
                    _cache_timestamp = time.time()
                    logger.info(f"[currency] Fetched {len(_rates_cache)} rates dari ExchangeRate-API")
                    return True
                else:
                    logger.warning(f"[currency] ExchangeRate-API error: {data}")
                    return False
    except Exception as e:
        logger.error(f"[currency] Fetch rates gagal: {e}")
        return False


async def _ensure_rates() -> bool:
    """Pastikan cache rates masih fresh (< 1 jam). Fetch ulang jika perlu."""
    global _cache_timestamp
    if time.time() - _cache_timestamp > _CACHE_TTL or not _rates_cache:
        return await _fetch_rates()
    return True


async def get_fiat_rate_async(symbol: str) -> Optional[float]:
    """
    Async: kembalikan berapa unit `symbol` per 1 USD.
    Contoh: get_fiat_rate_async("IDR") → 16200.0
    """
    iso = normalize_fiat(symbol)
    ok = await _ensure_rates()
    if not ok:
        return None
    rate = _rates_cache.get(iso)
    if rate is None:
        logger.warning(f"[currency] Kode '{iso}' tidak ditemukan di rate list")
    return rate


def get_fiat_rate(symbol: str) -> Optional[float]:
    """
    Sync wrapper — jalankan di event loop yang sedang berjalan.
    Dipanggil dari converter.py yang sudah async, tapi get_fiat_rate
    bisa dipanggil juga secara sync jika diperlukan.
    Lebih disarankan pakai get_fiat_rate_async() langsung.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Sudah ada event loop (dipanggil dari async context)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, get_fiat_rate_async(symbol))
                return future.result(timeout=15)
        else:
            return loop.run_until_complete(get_fiat_rate_async(symbol))
    except Exception as e:
        logger.error(f"[currency] get_fiat_rate sync error: {e}")
        return None
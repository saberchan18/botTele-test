# 🤖 Crypto Converter Bot — Telegram

Bot Telegram untuk konversi cryptocurrency & fiat secara real-time langsung di grup.

---

## 📁 Struktur File

```
crypto-bot/
├── bot.py           # Entry point, handler pesan
├── converter.py     # Logika konversi crypto (CoinGecko API)
├── currency.py      # Kurs fiat real-time (ExchangeRate-API)
├── config.py        # Konfigurasi token bot
├── requirements.txt # Dependensi Python
└── README.md
```

---

## ⚙️ Langkah 1 — Buat Bot di @BotFather

1. Buka Telegram, cari **@BotFather**
2. Ketik `/newbot`
3. Masukkan **nama** bot, misal: `Crypto Converter`
4. Masukkan **username** bot, misal: `MyCryptoConverterBot`
5. Salin **token** yang diberikan, contoh:
   ```
   123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. (Opsional) Nonaktifkan privacy mode agar bot bisa baca pesan grup:
   - Ketik `/mybots` → pilih bot → **Bot Settings** → **Group Privacy** → **Turn off**

---

## ⚙️ Langkah 2 — Setup di Server / PC

### Prasyarat
- Python 3.10+
- pip

### Instalasi

```bash
# Clone / salin folder crypto-bot ke server
cd crypto-bot

# Install dependensi
pip install -r requirements.txt
```

### Konfigurasi Token

**Cara A — Environment variable (disarankan):**
```bash
export TELEGRAM_BOT_TOKEN="123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
python bot.py
```

**Cara B — Edit langsung di config.py:**
```python
BOT_TOKEN = "123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## ⚙️ Langkah 3 — Jalankan Bot

```bash
python bot.py
```

Output:
```
2024-01-01 00:00:00 | INFO | __main__ | Bot berjalan… tekan Ctrl+C untuk berhenti.
```

---

## ⚙️ Langkah 4 — Tambahkan Bot ke Grup

1. Buka grup Telegram Anda
2. Tap nama grup → **Add Members** → cari username bot Anda
3. Jadikan bot sebagai **Admin** (minimal izin: baca & kirim pesan)

---

## 💬 Cara Pakai (Format Pesan)

### Format Dasar
```
<jumlah> <koin_asal> <target>
<jumlah> <koin_asal> to <target>
```

### Contoh — 1 target
```
1 usdt idr         → 1 USDT ke IDR
1 btc idr          → 1 BTC ke IDR
0.5 eth usdt       → 0.5 ETH ke USDT
100 doge usd       → 100 DOGE ke USD
```

### Contoh — Multi target
```
1 btc idr usdt             → 1 BTC ke IDR dan USDT
1 eth idr usdt btc         → 1 ETH ke IDR, USDT, dan BTC
50 sol idr usdt bnb eth    → 50 SOL ke 4 mata uang sekaligus
1000 doge idr usd eur      → 1000 DOGE ke IDR, USD, EUR
```

### Contoh — Fiat ke crypto
```
1000000 idr btc    → 1 juta IDR ke BTC
100 usd eth        → 100 USD ke ETH
```

---

## 🪙 Koin yang Didukung

Semua koin yang terdaftar di CoinGecko (10.000+ koin).

Koin populer yang langsung dikenali tanpa pencarian:
`BTC, ETH, USDT, BNB, SOL, XRP, DOGE, ADA, AVAX, SHIB, DOT, LINK, MATIC, TRX, TON, LTC, BCH, NEAR, UNI, PEPE, WIF, BONK, SUI, SEI, INJ` dan 100+ lainnya.

---

## 🏦 Fiat yang Didukung

`IDR, USD, EUR, GBP, JPY, KRW, CNY, SGD, MYR, THB, PHP, VND, INR, AUD, CAD, CHF, HKD, NZD, TRY, BRL, AED, SAR` dan lainnya.

---

## 🔄 API yang Digunakan

| API | Fungsi | Batas |
|-----|--------|-------|
| [CoinGecko](https://coingecko.com/api) | Harga crypto | 30 req/menit (gratis) |
| [ExchangeRate-API](https://open.er-api.com) | Kurs fiat | 1500 req/bulan (gratis) |

Kedua API **gratis & tanpa API key** untuk penggunaan dasar.

---

## 🚀 Jalankan sebagai Service (Linux / VPS)

Buat file `/etc/systemd/system/cryptobot.service`:

```ini
[Unit]
Description=Crypto Converter Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto-bot
Environment="TELEGRAM_BOT_TOKEN=TOKEN_ANDA_DISINI"
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Aktifkan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cryptobot
sudo systemctl start cryptobot
sudo systemctl status cryptobot
```

---

## ❓ Troubleshooting

| Masalah | Solusi |
|---------|--------|
| Bot tidak merespons di grup | Pastikan Group Privacy **OFF** di BotFather |
| `Conflict` error | Hanya boleh 1 instance bot berjalan |
| Rate limit CoinGecko | Tunggu 1 menit, atau upgrade ke CoinGecko Pro |
| Koin tidak ditemukan | Periksa simbol di coingecko.com |

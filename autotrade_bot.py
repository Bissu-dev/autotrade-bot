import os
import telebot
import anthropic
import requests
import base64
import time
from collections import defaultdict

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ALPHA_VANTAGE_KEY = "2O26IQTEBFWYLALV"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

user_question_count = defaultdict(int)
MAX_FREE_QUESTIONS = 5

CRYPTO_IDS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "bnb": "binancecoin", "sol": "solana", "solana": "solana",
    "xrp": "ripple", "ripple": "ripple",
    "ada": "cardano", "doge": "dogecoin", "dogecoin": "dogecoin",
    "dot": "polkadot", "matic": "matic-network",
    "ltc": "litecoin", "avax": "avalanche-2", "link": "chainlink",
}

FOREX_SYMBOLS = {
    "eurusd": ("EUR", "USD"), "eur/usd": ("EUR", "USD"),
    "gbpusd": ("GBP", "USD"), "gbp/usd": ("GBP", "USD"),
    "usdjpy": ("USD", "JPY"), "usd/jpy": ("USD", "JPY"),
    "usdchf": ("USD", "CHF"), "usd/chf": ("USD", "CHF"),
    "audusd": ("AUD", "USD"), "aud/usd": ("AUD", "USD"),
    "usdcad": ("USD", "CAD"), "usd/cad": ("USD", "CAD"),
    "euro dollar": ("EUR", "USD"),
}

COMMODITY_KEYWORDS = {
    "gold": "XAU", "or": "XAU", "xau": "XAU",
    "silver": "XAG", "argent": "XAG", "xag": "XAG",
}

INDEX_SYMBOLS = {
    "nasdaq": "^IXIC", "nasdaq100": "^NDX",
    "sp500": "^GSPC", "s&p500": "^GSPC", "s&p 500": "^GSPC",
    "cac40": "^FCHI", "cac 40": "^FCHI",
    "dax": "^GDAXI",
}

def get_crypto_price(coin_id, symbol):
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=" + coin_id + "&vs_currencies=usd,eur&include_24hr_change=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        price_usd = data[coin_id]["usd"]
        price_eur = data[coin_id]["eur"]
        change = data[coin_id]["usd_24h_change"]
        emoji = "🟢" if change >= 0 else "🔴"
        return emoji + " *" + symbol.upper() + "*\n💵 $" + "{:,.2f}".format(price_usd) + " USD\n💶 €" + "{:,.2f}".format(price_eur) + " EUR\n📊 24h: " + "{:+.2f}".format(change) + "%"
    except:
        return None

def get_forex_price(from_currency, to_currency):
    try:
        url = "https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=" + from_currency + "&to_currency=" + to_currency + "&apikey=" + ALPHA_VANTAGE_KEY
        r = requests.get(url, timeout=5)
        data = r.json()
        rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        pair = from_currency + "/" + to_currency
        return "💱 *" + pair + "*\n💵 " + "{:.4f}".format(rate)
    except:
        return None

def get_commodity_price(symbol, label):
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/" + symbol + "/USD"
        r = requests.get(url, timeout=5)
        data = r.json()
        ask = data[0]["spreadProfilePrices"][0]["ask"]
        bid = data[0]["spreadProfilePrices"][0]["bid"]
        price = (ask + bid) / 2
        emoji = "🥇" if symbol == "XAU" else "🥈"
        name = "OR (XAU/USD)" if symbol == "XAU" else "ARGENT (XAG/USD)"
        return emoji + " *" + name + "*\n💵 $" + "{:,.2f}".format(price) + " USD/oz"
    except:
        return None

def get_index_price(yahoo_symbol, label):
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + yahoo_symbol + "?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta["previousClose"]
        change = ((price - prev) / prev) * 100
        emoji = "🟢" if change >= 0 else "🔴"
        return emoji + " *" + label.upper() + "*\n💵 " + "{:,.2f}".format(price) + "\n📊 24h: " + "{:+.2f}".format(change) + "%"
    except:
        return None

def detect_asset(text):
    text_lower = text.lower()
    for keyword, sym in COMMODITY_KEYWORDS.items():
        if keyword in text_lower:
            return ("commodity", sym, keyword)
    for keyword, coin_id in CRYPTO_IDS.items():
        if keyword in text_lower:
            return ("crypto", coin_id, keyword)
    for keyword, (fc, tc) in FOREX_SYMBOLS.items():
        if keyword in text_lower:
            return ("forex", (fc, tc), keyword)
    for keyword, sym in INDEX_SYMBOLS.items():
        if keyword in text_lower:
            return ("index", sym, keyword)
    return None

def get_language(text):
    italian_words = ["ciao", "come", "cosa", "perche", "quando", "dove", "grazie", "aiuto"]
    if any(w in text.lower() for w in italian_words):
        return "it"
    return "fr"

def get_blocked_message(lang):
    messages = {
        "fr": "🚫 Vous avez utilisé vos 5 questions gratuites.\n\nPour continuer, rejoignez notre canal premium : @AutoTrade",
        "it": "🚫 Hai utilizzato le tue 5 domande gratuite.\n\nPer continuare, unisciti al nostro canale premium: @AutoTrade",
    }
    return messages.get(lang, messages["fr"])

def download_image_as_base64(file_id):
    try:
        file_info = bot.get_file(file_id)
        file_url = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
        r = requests.get(file_url, timeout=10)
        return base64.b64encode(r.content).decode("utf-8")
    except:
        return None

@bot.message_handler(commands=["start"])
def send_welcome(message):
    lang = get_language(message.text)
    welcome = {
        "fr": "👋 Bienvenue sur AutoTrade Bot !\n\nJe suis votre assistant trading alimenté par Claude AI.\n\n✅ Crypto en temps réel (BTC, ETH, SOL...)\n✅ Forex en temps réel (EUR/USD, GBP/USD...)\n✅ Matières premières (Or, Argent)\n✅ Indices (Nasdaq, S&P500, CAC40...)\n✅ Analyse de screenshots de trades\n✅ Calcul de lots (min 0.01)\n\nVous avez droit à *5 questions gratuites*.\n\nPostez votre question ou screenshot ! 📈",
        "it": "👋 Benvenuto su AutoTrade Bot!\n\nSono il tuo assistente trading powered by Claude AI.\n\n✅ Crypto in tempo reale\n✅ Forex in tempo reale\n✅ Materie prime (Oro, Argento)\n✅ Indici (Nasdaq, S&P500...)\n✅ Analisi screenshot\n✅ Calcolo lotti (min 0.01)\n\nHai diritto a *5 domande gratuite*!\n\nFai la tua domanda o invia uno screenshot! 📈",
    }
    bot.reply_to(message, welcome.get(lang, welcome["fr"]), parse_mode="Markdown")

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id

    if user_question_count[user_id] >= MAX_FREE_QUESTIONS:
        bot.reply_to(message, get_blocked_message("fr"))
        return

    user_question_count[user_id] += 1
    remaining = MAX_FREE_QUESTIONS - user_question_count[user_id]

    bot.reply_to(message, "🔍 Analyse du screenshot en cours...")

    try:
        file_id = message.photo[-1].file_id
        image_base64 = download_image_as_base64(file_id)

        if not image_base64:
            bot.reply_to(message, "Impossible de lire l'image.")
            return

        caption = message.caption or "Analyse ce screenshot de trading. Sois concis et direct. Donne les infos cles : actif, direction, niveaux importants. Si capital mentionne, calcule le lot (min 0.01)."

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=600,
            system="Tu es un expert en trading concis. Reponds UNIQUEMENT a ce qui est demande. Pour les calculs de lots, minimum 0.01 lot (MT5, Vantage, StarTrader, VT Markets). Ne jamais suggerer moins de 0.01. Reponds en francais.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": caption
                        }
                    ],
                }
            ],
        )

        answer = response.content[0].text
        footer = "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_"
        bot.reply_to(message, answer + footer, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    lang = get_language(message.text)

    if user_question_count[user_id] >= MAX_FREE_QUESTIONS:
        bot.reply_to(message, get_blocked_message(lang))
        return

    user_question_count[user_id] += 1
    remaining = MAX_FREE_QUESTIONS - user_question_count[user_id]

    price_info = ""
    asset = detect_asset(message.text)
    if asset:
        asset_type, symbol, keyword = asset
        if asset_type == "crypto":
            price_data = get_crypto_price(symbol, keyword)
        elif asset_type == "forex":
            price_data = get_forex_price(symbol[0], symbol[1])
        elif asset_type == "commodity":
            price_data = get_commodity_price(symbol, keyword)
        elif asset_type == "index":
            price_data = get_index_price(symbol, keyword)
        else:
            price_data = None
        if price_data:
            price_info = "📡 *Prix en temps réel :*\n" + price_data + "\n\n"

    try:
        user_content = message.text
        if price_info:
            user_content = message.text + "\n\n[DONNEES EN TEMPS REEL: " + price_info + "]"

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="Tu es un assistant trading expert et concis. Reponds UNIQUEMENT a ce qui est demande, sans analyse supplementaire non sollicitee. Si on te demande un cours, donne juste le cours. Si on demande une resistance, donne juste la resistance. Pour les calculs de lots, la taille minimale est 0.01 lot sur MT5 et les brokers standards (Vantage, StarTrader, VT Markets). Ne jamais suggerer des lots inferieurs a 0.01. Reponds en francais sauf si l utilisateur ecrit en italien. Les prix en temps reel sont deja affiches en haut. Ne dis JAMAIS que tu n as pas acces aux donnees de marche.",
            messages=[{"role": "user", "content": user_content}]
        )
        answer = response.content[0].text
        footer = {
            "fr": "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_",
            "it": "\n\n_" + str(remaining) + " domanda/e gratuita/e rimanente/i_",
        }
        full_response = price_info + answer + footer.get(lang, footer["fr"])
        bot.reply_to(message, full_response, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

if __name__ == "__main__":
    while True:
        try:
            print("AutoTrade Bot is running...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("Erreur, redemarrage dans 5s: " + str(e))
            time.sleep(5)

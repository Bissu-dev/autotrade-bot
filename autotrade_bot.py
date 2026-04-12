import os
import telebot
import anthropic
import requests
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
    "eurusd": ("EUR", "USD"), "eur/usd": ("EUR", "USD"), "euro": ("EUR", "USD"),
    "gbpusd": ("GBP", "USD"), "gbp/usd": ("GBP", "USD"),
    "usdjpy": ("USD", "JPY"), "usd/jpy": ("USD", "JPY"),
    "usdchf": ("USD", "CHF"), "usd/chf": ("USD", "CHF"),
    "audusd": ("AUD", "USD"), "aud/usd": ("AUD", "USD"),
    "usdcad": ("USD", "CAD"), "usd/cad": ("USD", "CAD"),
}

COMMODITY_SYMBOLS = {
    "gold": "XAU", "or": "XAU",
    "silver": "XAG", "argent": "XAG",
}

INDEX_SYMBOLS = {
    "nasdaq": "^IXIC", "nasdaq100": "^NDX",
    "sp500": "^GSPC", "s&p500": "^GSPC",
    "cac40": "^FCHI", "cac 40": "^FCHI",
    "dax": "^GDAXI",
}

def get_crypto_price(coin_id, symbol):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,eur&include_24hr_change=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        price_usd = data[coin_id]["usd"]
        price_eur = data[coin_id]["eur"]
        change = data[coin_id]["usd_24h_change"]
        emoji = "🟢" if change >= 0 else "🔴"
        return f"{emoji} *{symbol.upper()}*\n💵 ${price_usd:,.2f} USD\n💶 €{price_eur:,.2f} EUR\n📊 24h: {change:+.2f}%"
    except:
        return None

def get_forex_price(from_currency, to_currency):
    try:
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={ALPHA_VANTAGE_KEY}"
        r = requests.get(url, timeout=5)
        data = r.json()
        rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        pair = f"{from_currency}/{to_currency}"
        return f"💱 *{pair}*\n💵 {rate:.4f}"
    except:
        return None

def get_commodity_price(symbol, label):
    try:
        # Or et Argent via Alpha Vantage (cotés en USD)
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={symbol}&to_currency=USD&apikey={ALPHA_VANTAGE_KEY}"
        r = requests.get(url, timeout=5)
        data = r.json()
        rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        emoji = "🥇" if symbol == "XAU" else "🥈"
        return f"{emoji} *{label.upper()}*\n💵 ${rate:,.2f} USD/oz"
    except:
        return None

def get_index_price(yahoo_symbol, label):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta["previousClose"]
        change = ((price - prev) / prev) * 100
        emoji = "🟢" if change >= 0 else "🔴"
        return f"{emoji} *{label.upper()}*\n💵 {price:,.2f}\n📊 24h: {change:+.2f}%"
    except:
        return None

def detect_asset(text):
    text_lower = text.lower()
    for keyword, coin_id in CRYPTO_IDS.items():
        if keyword in text_lower:
            return ("crypto", coin_id, keyword)
    for keyword, (fc, tc) in FOREX_SYMBOLS.items():
        if keyword in text_lower:
            return ("forex", (fc, tc), keyword)
    for keyword, sym in COMMODITY_SYMBOLS.items():
        if keyword in text_lower:
            return ("commodity", sym, keyword)
    for keyword, sym in INDEX_SYMBOLS.items():
        if keyword in text_lower:
            return ("index", sym, keyword)
    return None

def get_language(text):
    italian_words = ["ciao", "come", "cosa", "perché", "quando", "dove", "grazie", "aiuto"]
    if any(w in text.lower() for w in italian_words):
        return "it"
    return "fr"

def get_blocked_message(lang):
    messages = {
        "fr": "🚫 Vous avez utilisé vos 5 questions gratuites.\n\nPour continuer, rejoignez notre canal premium : @AutoTrade",
        "it": "🚫 Hai utilizzato le tue 5 domande gratuite.\n\nPer continuare, unisciti al nostro canale premium: @AutoTrade",
    }
    return messages.get(lang, messages["fr"])

@bot.message_handler(commands=["start"])
def send_welcome(message):
    lang = get_language(message.text)
    welcome = {
        "fr": "👋 Bienvenue sur AutoTrade Bot !\n\nJe suis votre assistant trading alimenté par Claude AI.\n\n✅ Crypto en temps réel (BTC, ETH, SOL...)\n✅ Forex en temps réel (EUR/USD, GBP/USD...)\n✅ Matières premières (Or, Argent)\n✅ Indices (Nasdaq, S&P500, CAC40...)\n✅ Analyse de marché par IA\n\nVous avez droit à *5 questions gratuites*.\n\nPostez votre question sur le trading ! 📈",
        "it": "👋 Benvenuto su AutoTrade Bot!\n\nSono il tuo assistente trading powered by Claude AI.\n\n✅ Crypto in tempo reale\n✅ Forex in tempo reale\n✅ Materie prime (Oro, Argento)\n✅ Indici (Nasdaq, S&P500...)\n✅ Analisi AI\n\nHai diritto a *5 domande gratuite*!\n\nFai la tua domanda sul trading! 📈",
    }
    bot.reply_to(message, welcome.get(lang, welcome["fr"]), parse_mode="Markdown")

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
        if price_data:
            price_info = f"📡 *Prix en temps réel :*\n{price_data}\n\n"

    try:
        user_content = message.text
        if price_info:
            user_content = f"{message.text}\n\n[DONNÉES EN TEMPS RÉEL: {price_info}]"

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="Tu es un expert en trading (crypto, forex, indices, matières premières). Réponds en français sauf si l'utilisateur écrit en italien. Les prix en temps réel sont déjà affichés — ne dis JAMAIS que tu n'as pas accès aux données de marché. Base ton analyse uniquement sur les prix fournis en temps réel.",
            messages=[{"role": "user", "content": user_content}]
        )
        answer = response.content[0].text
        footer = {
            "fr": f"\n\n_{remaining} question(s) gratuite(s) restante(s)_",
            "it": f"\n\n_{remaining} domanda/e gratuita/e rimanente/i_",
        }
        full_response = price_info + answer + footer.get(lang, footer["fr"])
        bot.reply_to(message, full_response, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Erreur : {str(e)}")

if __name__ == "__main__":
    print("AutoTrade Bot is running...")
    bot.infinity_polling()

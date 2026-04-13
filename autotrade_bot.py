import os
import telebot
import anthropic
import requests
import base64
import time
import stripe
import json
from flask import Flask, request, jsonify
from threading import Thread
from collections import defaultdict

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_MENSUEL = os.environ.get("STRIPE_PRICE_MENSUEL")
STRIPE_PRICE_TRIMESTRIEL = os.environ.get("STRIPE_PRICE_TRIMESTRIEL")
STRIPE_PRICE_ANNUEL = os.environ.get("STRIPE_PRICE_ANNUEL")
ALPHA_VANTAGE_KEY = "2O26IQTEBFWYLALV"

stripe.api_key = STRIPE_SECRET_KEY

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
app = Flask(__name__)

user_question_count = defaultdict(int)
premium_users = set()
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

def create_checkout_session(user_id, price_id, plan_name):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url="https://t.me/autotrade_vip_bot?start=success",
            cancel_url="https://t.me/autotrade_vip_bot?start=cancel",
            metadata={"telegram_user_id": str(user_id), "plan": plan_name},
        )
        return session.url
    except:
        return None

def get_blocked_message(user_id):
    mensuel_url = create_checkout_session(user_id, STRIPE_PRICE_MENSUEL, "mensuel")
    trimestriel_url = create_checkout_session(user_id, STRIPE_PRICE_TRIMESTRIEL, "trimestriel")
    annuel_url = create_checkout_session(user_id, STRIPE_PRICE_ANNUEL, "annuel")

    msg = "🚫 *Vous avez utilisé vos 5 questions gratuites.*\n\n"
    msg += "Pour continuer, choisissez votre abonnement :\n\n"
    if mensuel_url:
        msg += "📅 [Mensuel — 24,99€/mois](" + mensuel_url + ")\n"
    if trimestriel_url:
        msg += "📆 [Trimestriel — 69,99€/3 mois](" + trimestriel_url + ")\n"
    if annuel_url:
        msg += "🗓️ [Annuel — 199,99€/an](" + annuel_url + ")\n"
    msg += "\n✅ Paiement sécurisé par Stripe"
    return msg

def download_image_as_base64(file_id):
    try:
        file_info = bot.get_file(file_id)
        file_url = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
        r = requests.get(file_url, timeout=10)
        return base64.b64encode(r.content).decode("utf-8")
    except:
        return None

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except:
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("telegram_user_id")
        if user_id:
            premium_users.add(int(user_id))
            try:
                bot.send_message(int(user_id), "🎉 *Paiement confirmé !*\n\nBienvenue dans AutoTrade Premium !\nVous avez maintenant un accès illimité. 🚀", parse_mode="Markdown")
            except:
                pass

    elif event["type"] == "customer.subscription.deleted":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("telegram_user_id")
        if user_id and int(user_id) in premium_users:
            premium_users.discard(int(user_id))
            try:
                bot.send_message(int(user_id), "❌ Votre abonnement AutoTrade a été annulé.\n\nVous pouvez vous réabonner à tout moment avec /abonnement.", parse_mode="Markdown")
            except:
                pass

    return jsonify({"status": "ok"})

@app.route("/", methods=["GET"])
def health():
    return "AutoTrade Bot is running!", 200

@bot.message_handler(commands=["start"])
def send_welcome(message):
    welcome = "👋 *Bienvenue sur AutoTrade Bot !*\n\nJe suis votre assistant trading alimenté par Claude AI.\n\n✅ Crypto en temps réel (BTC, ETH, SOL...)\n✅ Forex en temps réel (EUR/USD, GBP/USD...)\n✅ Matières premières (Or, Argent)\n✅ Indices (Nasdaq, S&P500, CAC40...)\n✅ Analyse de screenshots de trades\n✅ Calcul de lots (min 0.01)\n\nVous avez droit à *5 questions gratuites*.\n\nPostez votre question ou screenshot ! 📈"
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=["abonnement"])
def send_subscription(message):
    user_id = message.from_user.id
    msg = get_blocked_message(user_id)
    bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id

    if user_id not in premium_users and user_question_count[user_id] >= MAX_FREE_QUESTIONS:
        msg = get_blocked_message(user_id)
        bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)
        return

    if user_id not in premium_users:
        user_question_count[user_id] += 1

    remaining = MAX_FREE_QUESTIONS - user_question_count.get(user_id, 0)

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
            messages=[{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}}, {"type": "text", "text": caption}]}],
        )

        answer = response.content[0].text
        if user_id in premium_users:
            footer = "\n\n_✨ Membre Premium_"
        else:
            footer = "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_"
        bot.reply_to(message, answer + footer, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    lang = get_language(message.text)

    if user_id not in premium_users and user_question_count[user_id] >= MAX_FREE_QUESTIONS:
        msg = get_blocked_message(user_id)
        bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)
        return

    if user_id not in premium_users:
        user_question_count[user_id] += 1

    remaining = MAX_FREE_QUESTIONS - user_question_count.get(user_id, 0)

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
        if user_id in premium_users:
            footer = "\n\n_✨ Membre Premium_"
        else:
            footer = "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_"
        full_response = price_info + answer + footer
        bot.reply_to(message, full_response, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def run_bot():
    while True:
        try:
            print("AutoTrade Bot is running...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("Erreur bot, redemarrage dans 5s: " + str(e))
            time.sleep(5)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()

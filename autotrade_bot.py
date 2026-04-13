import os
import telebot
import anthropic
import requests
import base64
import time
import stripe
import psycopg2
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
DATABASE_URL = os.environ.get("DATABASE_URL")
ALPHA_VANTAGE_KEY = "2O26IQTEBFWYLALV"
ADMIN_ID = 7244221695

stripe.api_key = STRIPE_SECRET_KEY

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
app = Flask(__name__)

MAX_FREE_QUESTIONS = 5

PRICE_ONLY_KEYWORDS = [
    "cours", "prix", "price", "combien", "coute", "vaut", "valeur",
    "cote", "coté", "tarif", "quote", "rate"
]

def is_price_only_request(text):
    text_lower = text.lower()
    has_price_keyword = any(w in text_lower for w in PRICE_ONLY_KEYWORDS)
    has_analysis_keyword = any(w in text_lower for w in [
        "analyse", "analysis", "resistance", "support", "tendance",
        "signal", "lot", "strategie", "avis", "opinion", "bullish",
        "bearish", "haussier", "baissier", "pourquoi", "comment"
    ])
    return has_price_keyword and not has_analysis_keyword

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            is_premium BOOLEAN DEFAULT FALSE,
            question_count INTEGER DEFAULT 0,
            stripe_customer_id TEXT,
            subscription_id TEXT,
            plan TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("BDD initialisee !")

def is_premium(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT is_premium FROM users WHERE telegram_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row and row[0]
    except:
        return False

def get_question_count(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT question_count FROM users WHERE telegram_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else 0
    except:
        return 0

def increment_question(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, question_count)
            VALUES (%s, 1)
            ON CONFLICT (telegram_id)
            DO UPDATE SET question_count = users.question_count + 1, updated_at = NOW()
        """, (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def set_premium(user_id, status=True, plan=None, stripe_customer_id=None, subscription_id=None):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, is_premium, plan, stripe_customer_id, subscription_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET is_premium = %s, plan = %s, stripe_customer_id = %s, subscription_id = %s, updated_at = NOW()
        """, (user_id, status, plan, stripe_customer_id, subscription_id, status, plan, stripe_customer_id, subscription_id))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def get_all_premium():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT telegram_id, plan FROM users WHERE is_premium = TRUE")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except:
        return []

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
        pair = from_currency + "/" + to_currency
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/" + from_currency + "/" + to_currency
        r = requests.get(url, timeout=5)
        data = r.json()
        ask = data[0]["spreadProfilePrices"][0]["ask"]
        bid = data[0]["spreadProfilePrices"][0]["bid"]
        price = (ask + bid) / 2
        return "💱 *" + pair + "*\n💵 " + "{:.4f}".format(price)
    except:
        return None

def get_commodity_price(symbol, label):
    try:
        if symbol == "XAU":
            url = "https://api.gold-api.com/price/XAU"
            r = requests.get(url, timeout=5)
            data = r.json()
            price = data["price"]
            return "🥇 *OR (XAU/USD)*\n💵 $" + "{:,.2f}".format(price) + " USD/oz"
        elif symbol == "XAG":
            url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAG/USD"
            r = requests.get(url, timeout=5)
            data = r.json()
            ask = data[0]["spreadProfilePrices"][0]["ask"]
            bid = data[0]["spreadProfilePrices"][0]["bid"]
            price = (ask + bid) / 2
            return "🥈 *ARGENT (XAG/USD)*\n💵 $" + "{:,.2f}".format(price) + " USD/oz"
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
        plan = session.get("metadata", {}).get("plan")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        if user_id:
            set_premium(int(user_id), True, plan, customer_id, subscription_id)
            try:
                bot.send_message(int(user_id), "🎉 *Paiement confirmé !*\n\nBienvenue dans AutoTrade Premium !\nVous avez maintenant un accès illimité. 🚀", parse_mode="Markdown")
            except:
                pass

    elif event["type"] == "customer.subscription.deleted":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT telegram_id FROM users WHERE stripe_customer_id = %s", (customer_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                user_id = row[0]
                set_premium(user_id, False)
                try:
                    bot.send_message(user_id, "❌ Votre abonnement AutoTrade a été annulé.\n\nVous pouvez vous réabonner avec /abonnement.", parse_mode="Markdown")
                except:
                    pass
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
    if is_premium(user_id):
        bot.reply_to(message, "✅ Vous êtes déjà membre Premium ! Profitez de vos questions illimitées. 🚀")
        return
    msg = get_blocked_message(user_id)
    bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=["premium"])
def activate_premium(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    args = message.text.split()
    if len(args) > 1:
        target_id = int(args[1])
        set_premium(target_id, True, "test")
        bot.reply_to(message, "✅ Utilisateur " + str(target_id) + " activé en Premium !")
        try:
            bot.send_message(target_id, "🎉 *Accès Premium activé !*\n\nVous avez maintenant un accès illimité à AutoTrade Bot. 🚀", parse_mode="Markdown")
        except:
            pass
    else:
        set_premium(user_id, True, "test")
        bot.reply_to(message, "✅ Votre accès Premium est activé !")

@bot.message_handler(commands=["revoquer"])
def revoke_premium(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    args = message.text.split()
    if len(args) > 1:
        target_id = int(args[1])
        set_premium(target_id, False)
        bot.reply_to(message, "✅ Accès Premium révoqué pour " + str(target_id))
        try:
            bot.send_message(target_id, "❌ Votre accès test AutoTrade a été révoqué.", parse_mode="Markdown")
        except:
            pass
    else:
        bot.reply_to(message, "Usage: /revoquer ID_TELEGRAM")

@bot.message_handler(commands=["membres"])
def list_members(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    members = get_all_premium()
    if not members:
        bot.reply_to(message, "Aucun membre premium.")
        return
    msg = "👥 *Membres Premium :*\n\n"
    for m in members:
        msg += "• ID: " + str(m[0]) + " — Plan: " + str(m[1]) + "\n"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id
    count = get_question_count(user_id)

    if not is_premium(user_id) and count >= MAX_FREE_QUESTIONS:
        msg = get_blocked_message(user_id)
        bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)
        return

    if not is_premium(user_id):
        increment_question(user_id)
        count += 1

    remaining = MAX_FREE_QUESTIONS - count
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
        if is_premium(user_id):
            footer = "\n\n_✨ Membre Premium_"
        else:
            footer = "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_"
        bot.reply_to(message, answer + footer, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    count = get_question_count(user_id)

    if not is_premium(user_id) and count >= MAX_FREE_QUESTIONS:
        msg = get_blocked_message(user_id)
        bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)
        return

    if not is_premium(user_id):
        increment_question(user_id)
        count += 1

    remaining = MAX_FREE_QUESTIONS - count

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

    # Si c'est juste une demande de prix, on retourne uniquement le prix sans Claude
    if price_info and is_price_only_request(message.text):
        if is_premium(user_id):
            footer = "\n\n_✨ Membre Premium_"
        else:
            footer = "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_"
        bot.reply_to(message, price_info + footer, parse_mode="Markdown")
        return

    try:
        user_content = message.text
        if price_info:
            user_content = message.text + "\n\n[DONNEES EN TEMPS REEL: " + price_info + "]"

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="Tu es un assistant trading expert et concis. Reponds UNIQUEMENT a ce qui est demande. Si on te demande un cours, utilise UNIQUEMENT le prix fourni dans les donnees en temps reel. Pour les calculs de lots, minimum 0.01 lot sur MT5 et brokers standards. Ne jamais suggerer moins de 0.01. Reponds en francais. Ne dis JAMAIS que tu n as pas acces aux donnees de marche.",
            messages=[{"role": "user", "content": user_content}]
        )
        answer = response.content[0].text
        if is_premium(user_id):
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
    init_db()
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()

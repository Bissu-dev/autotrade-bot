import os
import telebot
import anthropic
import requests
import base64
import time
import stripe
import psycopg2
import re
from datetime import datetime
import pytz
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
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
ALPHA_VANTAGE_KEY = "2O26IQTEBFWYLALV"
ADMIN_ID = 7244221695
CANAL_ID = -1003587224431
TIMEZONE = pytz.timezone("Europe/Paris")

stripe.api_key = STRIPE_SECRET_KEY

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
app = Flask(__name__)

MAX_FREE_QUESTIONS = 5
MAX_HISTORY = 20

PRICE_ONLY_KEYWORDS = [
    "cours", "prix", "price", "combien", "coute", "vaut", "valeur",
    "cote", "coté", "tarif", "quote", "rate"
]

TP_REPARTITION = [0.40, 0.25, 0.15, 0.10, 0.05, 0.03, 0.02]
BROKERS = ["Vantage", "VT Markets", "StarTrader", "ACY Trading", "Puprime", "Autre"]
RISK_OPTIONS = ["1%", "2.5%", "5%", "10%", "Personnalisé"]

SIGNAL_DIRECTIONS = ["SELL", "BUY", "LONG", "SHORT"]
SIGNAL_ASSETS = {
    "BTC": "BTCUSD", "BITCOIN": "BTCUSD", "BTCUSD": "BTCUSD",
    "ETH": "ETHUSD", "ETHEREUM": "ETHUSD", "ETHUSD": "ETHUSD",
    "SOL": "SOLUSD", "SOLANA": "SOLUSD", "SOLUSDT": "SOLUSD",
    "XRP": "XRPUSD", "RIPPLE": "XRPUSD", "XRPUSD": "XRPUSD",
    "ADA": "ADAUSD", "CARDANO": "ADAUSD",
    "BNB": "BNBUSD", "BNBUSD": "BNBUSD",
    "DOGE": "DOGEUSD", "DOGEUSD": "DOGEUSD",
    "LTC": "LTCUSD", "LITECOIN": "LTCUSD",
    "AVAX": "AVAXUSD", "AVAXUSD": "AVAXUSD",
    "LINK": "LINKUSD", "LINKUSD": "LINKUSD",
    "DOT": "DOTUSD", "DOTUSD": "DOTUSD",
    "MATIC": "MATICUSD", "MATICUSD": "MATICUSD",
    "XAU": "XAUUSD", "GOLD": "XAUUSD", "OR": "XAUUSD", "XAUUSD": "XAUUSD",
    "XAG": "XAGUSD", "SILVER": "XAGUSD", "ARGENT": "XAGUSD",
    "EUR": "EURUSD", "EURUSD": "EURUSD",
    "GBP": "GBPUSD", "GBPUSD": "GBPUSD",
    "NAS": "NASDAQ", "NASDAQ": "NASDAQ", "NAS100": "NASDAQ",
    "DAX": "DAX", "CAC": "CAC40", "CAC40": "CAC40",
    "SP500": "SP500", "SPX": "SP500",
    "OIL": "OILUSD", "PETROLE": "OILUSD", "WTI": "OILUSD",
}

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
            broker TEXT,
            capital FLOAT,
            capital_initial FLOAT,
            risk_percent FLOAT DEFAULT 1.0,
            onboarding_step INTEGER DEFAULT 0,
            alerte_danger_envoyee BOOLEAN DEFAULT FALSE,
            alerte_profit_envoyee BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for col in [
        "broker TEXT", "capital FLOAT", "capital_initial FLOAT",
        "risk_percent FLOAT DEFAULT 1.0", "onboarding_step INTEGER DEFAULT 0",
        "alerte_danger_envoyee BOOLEAN DEFAULT FALSE",
        "alerte_profit_envoyee BOOLEAN DEFAULT FALSE"
    ]:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS " + col)
        except:
            pass
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_signals (
            telegram_id BIGINT PRIMARY KEY,
            signal_text TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("BDD initialisee !")

def get_user(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT telegram_id, is_premium, question_count, stripe_customer_id,
            subscription_id, plan, broker, capital, capital_initial, risk_percent,
            onboarding_step, alerte_danger_envoyee, alerte_profit_envoyee
            FROM users WHERE telegram_id = %s
        """, (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            cols = ["telegram_id", "is_premium", "question_count", "stripe_customer_id",
                    "subscription_id", "plan", "broker", "capital", "capital_initial",
                    "risk_percent", "onboarding_step", "alerte_danger_envoyee", "alerte_profit_envoyee"]
            return dict(zip(cols, row))
        return None
    except:
        return None

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

def get_all_users():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT telegram_id, is_premium FROM users WHERE onboarding_step = 0")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except:
        return []

def set_onboarding_step(user_id, step):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, onboarding_step)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET onboarding_step = %s, updated_at = NOW()
        """, (user_id, step, step))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def set_broker(user_id, broker):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, broker)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET broker = %s, updated_at = NOW()
        """, (user_id, broker, broker))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def set_capital(user_id, capital, is_initial=False):
    try:
        conn = get_db()
        cur = conn.cursor()
        if is_initial:
            cur.execute("""
                INSERT INTO users (telegram_id, capital, capital_initial)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET capital = %s, capital_initial = %s, updated_at = NOW()
            """, (user_id, capital, capital, capital, capital))
        else:
            cur.execute("""
                INSERT INTO users (telegram_id, capital)
                VALUES (%s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET capital = %s, updated_at = NOW()
            """, (user_id, capital, capital))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def set_risk(user_id, risk_percent):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, risk_percent)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET risk_percent = %s, updated_at = NOW()
        """, (user_id, risk_percent, risk_percent))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def check_and_send_alerts(user_id, capital_actuel):
    try:
        user = get_user(user_id)
        if not user:
            return
        capital_initial = user.get("capital_initial") or capital_actuel
        broker = user.get("broker", "?")
        alerte_danger = user.get("alerte_danger_envoyee", False)
        alerte_profit = user.get("alerte_profit_envoyee", False)
        if capital_initial <= 0:
            return
        variation = ((capital_actuel - capital_initial) / capital_initial) * 100

        if not alerte_danger and (capital_actuel < 250 or variation <= -50):
            msg = "🔴 *ALERTE DANGER — Client en difficulté*\n\n"
            msg += "👤 ID : " + str(user_id) + "\n"
            msg += "🏦 Broker : " + broker + "\n"
            msg += "💰 Capital initial : " + str(capital_initial) + "€\n"
            msg += "📉 Capital actuel : " + str(capital_actuel) + "€\n"
            msg += "📊 Variation : *" + "{:+.1f}".format(variation) + "%*\n"
            if capital_actuel < 250:
                msg += "⚠️ Capital sous 250€ — intervention recommandée"
            else:
                msg += "⚠️ Perte > 50% — intervention recommandée"
            bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET alerte_danger_envoyee = TRUE WHERE telegram_id = %s", (user_id,))
            conn.commit()
            cur.close()
            conn.close()

        if not alerte_profit and variation >= 100:
            msg = "🟢 *ALERTE PERFORMANCE — Client en forte progression*\n\n"
            msg += "👤 ID : " + str(user_id) + "\n"
            msg += "🏦 Broker : " + broker + "\n"
            msg += "💰 Capital initial : " + str(capital_initial) + "€\n"
            msg += "📈 Capital actuel : " + str(capital_actuel) + "€\n"
            msg += "📊 Performance : *+" + "{:.1f}".format(variation) + "%*\n"
            msg += "💡 À orienter vers une offre supérieure"
            bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET alerte_profit_envoyee = TRUE WHERE telegram_id = %s", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print("Erreur alerte : " + str(e))

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

def save_message(user_id, role, content):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO conversation_history (telegram_id, role, content) VALUES (%s, %s, %s)", (user_id, role, content))
        cur.execute("""
            DELETE FROM conversation_history
            WHERE telegram_id = %s AND id NOT IN (
                SELECT id FROM conversation_history WHERE telegram_id = %s
                ORDER BY created_at DESC LIMIT %s
            )
        """, (user_id, user_id, MAX_HISTORY))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def get_history(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM conversation_history WHERE telegram_id = %s ORDER BY created_at ASC", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"role": row[0], "content": row[1]} for row in rows]
    except:
        return []

def clear_history(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM conversation_history WHERE telegram_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def save_pending_signal(user_id, signal_text):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pending_signals (telegram_id, signal_text)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET signal_text = %s, created_at = NOW()
        """, (user_id, signal_text, signal_text))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def get_pending_signal(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT signal_text FROM pending_signals WHERE telegram_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except:
        return None

def delete_pending_signal(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM pending_signals WHERE telegram_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def get_macro_news():
    try:
        keywords = "Fed OR FOMC OR BCE OR Trump OR inflation OR interest rate OR crypto OR bitcoin OR gold OR dollar"
        url = "https://newsapi.org/v2/everything?q=" + requests.utils.quote(keywords) + "&language=fr&sortBy=publishedAt&pageSize=5&apiKey=" + NEWS_API_KEY
        r = requests.get(url, timeout=5)
        data = r.json()
        articles = data.get("articles", [])
        if not articles:
            url = "https://newsapi.org/v2/everything?q=" + requests.utils.quote(keywords) + "&language=en&sortBy=publishedAt&pageSize=5&apiKey=" + NEWS_API_KEY
            r = requests.get(url, timeout=5)
            data = r.json()
            articles = data.get("articles", [])
        return articles[:5]
    except:
        return []

def get_morning_briefing():
    now = datetime.now(TIMEZONE)
    date_str = now.strftime("%A %d %B %Y").capitalize()
    msg = "🌅 *Morning Briefing — " + date_str + "*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    msg += "📊 *Marchés en temps réel :*\n"
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
        r = requests.get(url, timeout=5)
        data = r.json()
        btc = data["bitcoin"]["usd"]
        btc_change = data["bitcoin"]["usd_24h_change"]
        eth = data["ethereum"]["usd"]
        eth_change = data["ethereum"]["usd_24h_change"]
        btc_emoji = "🟢" if btc_change >= 0 else "🔴"
        eth_emoji = "🟢" if eth_change >= 0 else "🔴"
        msg += btc_emoji + " BTC : $" + "{:,.0f}".format(btc) + " (" + "{:+.1f}".format(btc_change) + "%)\n"
        msg += eth_emoji + " ETH : $" + "{:,.0f}".format(eth) + " (" + "{:+.1f}".format(eth_change) + "%)\n"
    except:
        pass
    try:
        url = "https://api.gold-api.com/price/XAU"
        r = requests.get(url, timeout=5)
        data = r.json()
        gold = data["price"]
        msg += "🥇 OR : $" + "{:,.0f}".format(gold) + "/oz\n"
    except:
        pass
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/EUR/USD"
        r = requests.get(url, timeout=5)
        data = r.json()
        eurusd = (data[0]["spreadProfilePrices"][0]["ask"] + data[0]["spreadProfilePrices"][0]["bid"]) / 2
        msg += "💱 EUR/USD : " + "{:.4f}".format(eurusd) + "\n"
    except:
        pass

    msg += "\n"
    articles = get_macro_news()
    if articles:
        msg += "📰 *News à surveiller :*\n\n"
        for article in articles[:4]:
            title = article.get("title", "").split(" - ")[0][:80]
            msg += "• " + title + "\n"
        msg += "\n"

    if articles:
        try:
            news_text = "\n".join([a.get("title", "") for a in articles[:4]])
            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=200,
                system="Tu es un expert en trading. En 2-3 phrases maximum, dis quel impact ces news peuvent avoir sur BTC, Gold et EUR/USD aujourd'hui. Sois direct et concis. Reponds en francais.",
                messages=[{"role": "user", "content": "News du jour :\n" + news_text + "\n\nQuel impact sur les marchés ?"}]
            )
            analyse = response.content[0].text
            msg += "🤖 *Analyse IA :*\n" + analyse + "\n\n"
        except:
            pass

    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += "_Bonne journée et bon trading ! 📈_"
    return msg

def send_morning_briefing_to_all():
    try:
        briefing = get_morning_briefing()
        members = get_all_premium()
        sent = 0
        for member in members:
            try:
                bot.send_message(member[0], briefing, parse_mode="Markdown")
                sent += 1
                time.sleep(0.1)
            except:
                pass
        print("Morning briefing envoyé à " + str(sent) + " abonnés")
    except Exception as e:
        print("Erreur morning briefing : " + str(e))

def morning_briefing_scheduler():
    already_sent_today = False
    while True:
        try:
            now = datetime.now(TIMEZONE)
            if now.hour == 8 and now.minute == 30 and not already_sent_today:
                send_morning_briefing_to_all()
                already_sent_today = True
            elif now.hour == 8 and now.minute == 31:
                already_sent_today = False
            elif now.hour != 8:
                already_sent_today = False
            time.sleep(30)
        except Exception as e:
            print("Erreur scheduler : " + str(e))
            time.sleep(30)

def is_trading_signal(text):
    text_upper = text.upper()
    has_direction = any(d in text_upper for d in SIGNAL_DIRECTIONS)
    has_asset = any(a in text_upper for a in SIGNAL_ASSETS.keys())
    has_sl = "STOP LOSS" in text_upper or "SL" in text_upper or "🔐" in text
    return has_direction and has_asset and has_sl

def parse_signal(text):
    signal = {}
    text_upper = text.upper()
    for d in SIGNAL_DIRECTIONS:
        if d in text_upper:
            signal["direction"] = "SELL" if d in ["SELL", "SHORT"] else "BUY"
            break
    for keyword, normalized in SIGNAL_ASSETS.items():
        if keyword in text_upper:
            signal["asset"] = normalized
            break
    sl_match = re.search(r"Stop Loss\s*:?\s*([\d,\.]+)", text, re.IGNORECASE)
    if sl_match:
        signal["sl"] = float(sl_match.group(1).replace(",", ""))
    entry_match = re.search(r"(\d[\d,\.]+)\s*[-–]\s*(\d[\d,\.]+)", text)
    if entry_match:
        signal["entry_low"] = float(entry_match.group(1).replace(",", ""))
        signal["entry_high"] = float(entry_match.group(2).replace(",", ""))
        signal["entry_mid"] = (signal["entry_low"] + signal["entry_high"]) / 2
    tp_matches = re.findall(r"^\s*\d+[\.\)]\s*([\d,\.]+)", text, re.MULTILINE)
    if tp_matches:
        signal["tps"] = [float(tp.replace(",", "")) for tp in tp_matches]
    return signal

def calculate_lots(capital, risk_percent, signal):
    if not signal.get("sl") or not signal.get("entry_mid") or not signal.get("tps"):
        return None
    entry = signal["entry_mid"]
    sl = signal["sl"]
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return None
    risque_total = capital * (risk_percent / 100)
    lot_total = risque_total / sl_distance
    lot_total = max(0.01, round(lot_total / 0.01) * 0.01)
    tps = signal["tps"]
    result = []
    for i, tp in enumerate(tps):
        pct = TP_REPARTITION[i] if i < len(TP_REPARTITION) else 0.02
        lot = max(0.01, round((lot_total * pct) / 0.01) * 0.01)
        tp_distance = abs(tp - entry)
        gain_potentiel = round(lot * tp_distance, 2)
        risque_tp = round(lot * sl_distance, 2)
        rr = round(tp_distance / sl_distance, 1) if sl_distance > 0 else 0
        result.append({
            "tp_num": i + 1,
            "tp_price": tp,
            "lot": lot,
            "pct": int(pct * 100),
            "risque": risque_tp,
            "gain": gain_potentiel,
            "rr": rr,
            "optional": i >= 3
        })
    return result

def format_signal_with_lots(signal, lots, capital, risk_percent, broker=""):
    direction = signal.get("direction", "")
    asset = signal.get("asset", "")
    entry_low = signal.get("entry_low", "")
    entry_high = signal.get("entry_high", "")
    sl = signal.get("sl", "")
    emoji = "📈" if direction == "BUY" else "📉"
    broker_str = " — " + broker if broker else ""
    risque_total = round(capital * (risk_percent / 100), 2)
    msg = emoji + " *" + direction + " " + asset + "*" + broker_str + "\n"
    msg += "💰 Entrée : " + str(entry_low) + " - " + str(entry_high) + "\n"
    msg += "🔐 Stop Loss : " + str(sl) + "\n"
    msg += "💼 Capital : " + str(capital) + "€ | Risque : " + str(risk_percent) + "% (" + str(risque_total) + "€)\n\n"
    msg += "📊 *Tailles de lot par TP :*\n\n"
    for tp in lots:
        optional_tag = " _(optionnel)_" if tp["optional"] else ""
        msg += "TP" + str(tp["tp_num"]) + " — " + str(tp["tp_price"]) + optional_tag + "\n"
        msg += "   • Lot : *" + str(tp["lot"]) + "* (" + str(tp["pct"]) + "%)\n"
        msg += "   • Risque : " + str(tp["risque"]) + "€ | Gain potentiel : " + str(tp["gain"]) + "€\n"
        msg += "   • R/R : 1:" + str(tp["rr"]) + "\n\n"
    msg += "⚠️ _Tailles indicatives — adaptez selon votre levier_"
    return msg

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
    "gold": "XAU", "xau": "XAU",
    "silver": "XAG", "argent": "XAG", "xag": "XAG",
}

OR_WORDS = ["or", "l'or", "du or", "l or", "xauusd", "xau/usd"]

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

def get_live_prices_context():
    prices = {}
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,ripple,solana&vs_currencies=usd"
        r = requests.get(url, timeout=5)
        data = r.json()
        prices["BTC"] = data["bitcoin"]["usd"]
        prices["ETH"] = data["ethereum"]["usd"]
        prices["XRP"] = data["ripple"]["usd"]
        prices["SOL"] = data["solana"]["usd"]
    except:
        pass
    try:
        url = "https://api.gold-api.com/price/XAU"
        r = requests.get(url, timeout=5)
        data = r.json()
        prices["XAU"] = data["price"]
    except:
        pass
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/EUR/USD"
        r = requests.get(url, timeout=5)
        data = r.json()
        ask = data[0]["spreadProfilePrices"][0]["ask"]
        bid = data[0]["spreadProfilePrices"][0]["bid"]
        prices["EURUSD"] = (ask + bid) / 2
    except:
        pass
    return prices

def detect_asset(text):
    text_lower = text.lower()
    words = text_lower.split()
    for or_word in OR_WORDS:
        if or_word in ["xauusd", "xau/usd", "xau"]:
            if or_word in text_lower:
                return ("commodity", "XAU", "or")
        if or_word in words or ("l'or" in text_lower) or ("du or" in text_lower):
            return ("commodity", "XAU", "or")
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
        msg += "📅 [Mensuel — 29,99€/mois](" + mensuel_url + ")\n"
    if trimestriel_url:
        msg += "📆 [Trimestriel — 74,99€/3 mois](" + trimestriel_url + ")\n"
    if annuel_url:
        msg += "🗓️ [Annuel — 239,99€/an](" + annuel_url + ")\n"
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

def send_broker_keyboard(user_id):
    keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(*[telebot.types.KeyboardButton(b) for b in BROKERS])
    bot.send_message(user_id, "🏦 *Quel broker utilisez-vous ?*\n\n_Sélectionnez dans la liste :_", parse_mode="Markdown", reply_markup=keyboard)

def send_risk_keyboard(user_id):
    keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(*[telebot.types.KeyboardButton(r) for r in RISK_OPTIONS])
    bot.send_message(
        user_id,
        "📊 *Quel % de risque par trade ?*\n\n• 1% = conservateur\n• 2.5% = modéré\n• 5% = agressif\n• 10% = très agressif",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

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
                bot.send_message(int(user_id), "🎉 *Paiement confirmé !*\n\nBienvenue dans AutoTrade Premium !\nVous avez maintenant un accès illimité. 🚀\n\n🌅 Chaque matin à 8h30, vous recevrez votre briefing des marchés.\n\n📖 Tapez /aide pour voir toutes les commandes !", parse_mode="Markdown")
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
                clear_history(user_id)
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

@bot.channel_post_handler(func=lambda message: True)
def handle_channel_post(message):
    if message.chat.id != CANAL_ID:
        return
    if not message.text:
        return
    if not is_trading_signal(message.text):
        return
    members = get_all_premium()
    for member in members:
        user_id = member[0]
        user = get_user(user_id)
        save_pending_signal(user_id, message.text)
        try:
            capital_info = ""
            if user and user.get("capital"):
                capital_info = "\n_Dernier capital enregistré : " + str(user["capital"]) + "€_"
            bot.send_message(
                user_id,
                "📡 *Nouveau signal !*\n\n" + message.text + "\n\n💰 *Quel est votre capital actuel ?*" + capital_info + "\n_(ex: 2000)_",
                parse_mode="Markdown"
            )
        except:
            pass

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    clear_history(user_id)
    set_onboarding_step(user_id, 1)
    bot.send_message(user_id, """👋 *Bienvenue sur AutoTrade Bot !*

Je suis votre assistant trading personnel, disponible 24h/24 et 7j/7.

💹 *Ce que je peux faire pour vous :*

✅ Prix en temps réel — Crypto, Forex, Or, Indices
✅ Signaux automatiques avec calcul de lots
✅ Morning briefing à 8h30 tous les matins
✅ Analyse de vos graphiques TradingView
✅ Niveaux clés — Support, Résistance, Objectifs
✅ Gestion du risque personnalisée

_Avant de commencer, j'ai besoin de 3 informations rapides_ 👇""", parse_mode="Markdown")
    time.sleep(1)
    send_broker_keyboard(user_id)

@bot.message_handler(commands=["morning"])
def send_morning_command(message):
    user_id = message.from_user.id
    if not is_premium(user_id):
        bot.reply_to(message, "⭐ Cette fonctionnalité est réservée aux membres Premium.\n\nAbonnez-vous avec /abonnement 🚀")
        return
    bot.reply_to(message, "⏳ Génération du briefing en cours...")
    briefing = get_morning_briefing()
    bot.send_message(user_id, briefing, parse_mode="Markdown")

@bot.message_handler(commands=["profil"])
def show_profil(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "Aucun profil trouvé. Tapez /start pour commencer.")
        return
    broker = user.get("broker") or "Non renseigné"
    capital = user.get("capital")
    capital_initial = user.get("capital_initial")
    risk = user.get("risk_percent") or 1.0
    capital_str = str(capital) + "€" if capital else "Non renseigné"
    capital_initial_str = str(capital_initial) + "€" if capital_initial else "Non renseigné"
    risque_euros = round(capital * risk / 100, 2) if capital else 0
    premium = "✅ Premium" if user.get("is_premium") else "❌ Gratuit"
    variation_str = ""
    if capital and capital_initial and capital_initial > 0:
        variation = ((capital - capital_initial) / capital_initial) * 100
        variation_str = "\n📊 Performance : *" + "{:+.1f}".format(variation) + "%*"
    msg = "👤 *Votre profil :*\n\n"
    msg += "🏦 Broker : *" + broker + "*\n"
    msg += "💰 Capital initial : *" + capital_initial_str + "*\n"
    msg += "💰 Capital actuel : *" + capital_str + "*"
    msg += variation_str + "\n"
    msg += "📊 Risque : *" + str(risk) + "%* (" + str(risque_euros) + "€ par trade)\n"
    msg += "⭐ Statut : *" + premium + "*\n\n"
    msg += "_Modifier : /broker, /capital ou /risque_"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=["aide"])
def send_aide(message):
    msg = """📖 *Commandes disponibles :*

💹 *Trading*
/morning — Briefing des marchés du jour ⭐
/profil — Voir votre profil et performance

⚙️ *Paramètres*
/broker — Changer de broker
/capital — Mettre à jour votre capital
/risque — Modifier votre % de risque
/nouveau — Nouvelle conversation

💳 *Abonnement*
/abonnement — Voir les offres Premium

_Posez vos questions en texte ou envoyez un screenshot de graphique !_"""
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=["broker"])
def change_broker(message):
    set_onboarding_step(message.from_user.id, 1)
    send_broker_keyboard(message.from_user.id)

@bot.message_handler(commands=["capital"])
def change_capital(message):
    set_onboarding_step(message.from_user.id, 2)
    keyboard = telebot.types.ReplyKeyboardRemove()
    bot.send_message(message.from_user.id, "💰 *Quel est votre capital actuel ?*\n_(ex: 2000 pour 2000€)_", parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(commands=["risque"])
def change_risk(message):
    set_onboarding_step(message.from_user.id, 3)
    send_risk_keyboard(message.from_user.id)

@bot.message_handler(commands=["abonnement"])
def send_subscription(message):
    user_id = message.from_user.id
    if is_premium(user_id):
        bot.reply_to(message, "✅ Vous êtes déjà membre Premium ! Profitez de vos questions illimitées. 🚀")
        return
    msg = get_blocked_message(user_id)
    bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=["nouveau"])
def new_conversation(message):
    clear_history(message.from_user.id)
    bot.reply_to(message, "🔄 Nouvelle conversation démarrée !")

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
            bot.send_message(target_id, "🎉 *Accès Premium activé !*\n\nVous avez maintenant un accès illimité à AutoTrade Bot.\n\n🌅 Chaque matin à 8h30, vous recevrez votre briefing des marchés.\n\n📖 Tapez /aide pour voir toutes les commandes ! 🚀", parse_mode="Markdown")
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
        clear_history(target_id)
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
        user = get_user(m[0])
        broker = user.get("broker", "?") if user else "?"
        capital = str(user.get("capital", "?")) + "€" if user and user.get("capital") else "?"
        capital_initial = user.get("capital_initial") if user else None
        risk = str(user.get("risk_percent", "?")) + "%" if user and user.get("risk_percent") else "?"
        perf = ""
        if user and user.get("capital") and capital_initial and capital_initial > 0:
            variation = ((user["capital"] - capital_initial) / capital_initial) * 100
            perf = " (" + "{:+.0f}".format(variation) + "%)"
        msg += "• " + str(m[0]) + " — " + broker + " — " + capital + perf + " — " + risk + "\n"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=["stats"])
def show_stats(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    try:
        all_users = get_all_users()
        premium = get_all_premium()
        total = len(all_users)
        total_premium = len(premium)
        total_free = total - total_premium
        msg = "📊 *Statistiques AutoTrade Bot :*\n\n"
        msg += "👥 Total utilisateurs : *" + str(total) + "*\n"
        msg += "⭐ Premium : *" + str(total_premium) + "*\n"
        msg += "🆓 Gratuits : *" + str(total_free) + "*\n"
        if total > 0:
            taux = round(total_premium / total * 100, 1)
            msg += "📈 Taux de conversion : *" + str(taux) + "%*\n"
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

@bot.message_handler(commands=["broadcast"])
def broadcast_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.reply_to(message, "Usage : /broadcast Votre message\n\nExemple :\n/broadcast 🎯 Zoom ce soir 20h ! Lien : https://zoom.us/xxx\n\n_Envoi aux membres Premium uniquement._")
        return
    members = get_all_premium()
    if not members:
        bot.reply_to(message, "Aucun membre Premium pour le moment.")
        return
    sent = 0
    failed = 0
    for member in members:
        try:
            bot.send_message(member[0], "📢 *Message de votre coach :*\n\n" + text, parse_mode="Markdown")
            sent += 1
            time.sleep(0.1)
        except:
            failed += 1
    bot.reply_to(message, "✅ Envoyé à *" + str(sent) + "* membres Premium\n❌ Échec : " + str(failed), parse_mode="Markdown")

@bot.message_handler(commands=["upsell"])
def upsell_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    text = message.text.replace("/upsell", "").strip()
    if not text:
        bot.reply_to(message, "Usage : /upsell Votre message\n\nExemple :\n/upsell 🚀 Accédez aux signaux en temps réel et au morning briefing ! Abonnez-vous : /abonnement\n\n_Envoi à TOUS les utilisateurs (gratuits + Premium)._")
        return
    users = get_all_users()
    if not users:
        bot.reply_to(message, "Aucun utilisateur pour le moment.")
        return
    sent_free = 0
    sent_premium = 0
    failed = 0
    for user in users:
        try:
            bot.send_message(user[0], "💡 *Message de votre coach :*\n\n" + text, parse_mode="Markdown")
            if user[1]:
                sent_premium += 1
            else:
                sent_free += 1
            time.sleep(0.1)
        except:
            failed += 1
    bot.reply_to(
        message,
        "✅ Envoyé à *" + str(sent_free + sent_premium) + "* utilisateurs\n📊 Gratuits : *" + str(sent_free) + "* | Premium : *" + str(sent_premium) + "*\n❌ Échec : " + str(failed),
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["briefing"])
def force_briefing_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    bot.reply_to(message, "📤 Envoi du briefing à tous les abonnés Premium...")
    send_morning_briefing_to_all()
    bot.send_message(ADMIN_ID, "✅ Briefing envoyé !")

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
    bot.reply_to(message, "🔍 Analyse du graphique en cours...")
    try:
        file_id = message.photo[-1].file_id
        image_base64 = download_image_as_base64(file_id)
        if not image_base64:
            bot.reply_to(message, "Impossible de lire l'image.")
            return
        live_prices = get_live_prices_context()
        prices_context = "PRIX EN TEMPS REEL ACTUELS :\n"
        for symbol, price in live_prices.items():
            prices_context += "- " + symbol + ": $" + "{:,.2f}".format(price) + "\n"
        user = get_user(user_id)
        user_context = ""
        if user and user.get("broker"):
            user_context += "Broker : " + user["broker"] + "\n"
        if user and user.get("capital"):
            user_context += "Capital : " + str(user["capital"]) + "€\n"
        if user and user.get("risk_percent"):
            user_context += "Risque par trade : " + str(user["risk_percent"]) + "%\n"
        caption = message.caption or "Analyse ce screenshot de trading. Sois concis et direct. Donne les infos cles : actif, direction, niveaux importants. Si capital mentionne, calcule le lot (min 0.01). IMPORTANT: Les chiffres de vues/likes/reactions ne sont pas des prix ni des dates."
        full_prompt = prices_context + "\n" + user_context + "\n" + caption
        history = get_history(user_id)
        messages_with_history = history + [
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}},
                {"type": "text", "text": full_prompt}
            ]}
        ]
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=600,
            system="Tu es un expert en trading concis. Reponds UNIQUEMENT a ce qui est demande. Utilise TOUJOURS les prix en temps reel fournis. Pour les calculs de lots, minimum 0.01 lot. Tiens compte du broker, capital et % risque si fournis. Les chiffres de vues/likes ne sont pas des prix ni des dates. Reponds en francais. Tu te souviens du contexte des echanges precedents.",
            messages=messages_with_history,
        )
        answer = response.content[0].text
        save_message(user_id, "user", "[Screenshot] " + caption)
        save_message(user_id, "assistant", answer)
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
    user = get_user(user_id)
    onboarding_step = user.get("onboarding_step", 0) if user else 0

    if onboarding_step == 1:
        broker = message.text.strip()
        if broker not in BROKERS:
            send_broker_keyboard(user_id)
            return
        set_broker(user_id, broker)
        set_onboarding_step(user_id, 2)
        keyboard = telebot.types.ReplyKeyboardRemove()
        bot.send_message(user_id, "✅ Broker : *" + broker + "*\n\n💰 *Quel est votre capital de trading ?*\n_(ex: 2000 pour 2000€)_", parse_mode="Markdown", reply_markup=keyboard)
        return

    if onboarding_step == 2:
        try:
            capital = float(message.text.strip().replace("€", "").replace(",", ".").replace(" ", ""))
            if capital <= 0:
                raise ValueError
            set_capital(user_id, capital, is_initial=True)
            set_onboarding_step(user_id, 3)
            time.sleep(0.5)
            send_risk_keyboard(user_id)
        except:
            bot.send_message(user_id, "⚠️ Veuillez entrer un montant valide (ex: 2000)")
        return

    if onboarding_step == 3:
        text = message.text.strip()
        if text == "Personnalisé":
            set_onboarding_step(user_id, 4)
            keyboard = telebot.types.ReplyKeyboardRemove()
            bot.send_message(user_id, "✏️ *Entrez votre % de risque personnalisé*\n_(ex: 3 pour 3%)_", parse_mode="Markdown", reply_markup=keyboard)
            return
        try:
            risk = float(text.replace("%", "").replace(",", "."))
            if risk <= 0 or risk > 100:
                raise ValueError
            set_risk(user_id, risk)
            set_onboarding_step(user_id, 0)
            user = get_user(user_id)
            broker = user.get("broker", "") if user else ""
            capital = user.get("capital", 0) if user else 0
            risque_euros = round(capital * risk / 100, 2)
            keyboard = telebot.types.ReplyKeyboardRemove()
            bot.send_message(
                user_id,
                "✅ *Profil configuré !*\n\n🏦 Broker : *" + broker + "*\n💰 Capital : *" + str(capital) + "€*\n📊 Risque : *" + str(risk) + "%* (" + str(risque_euros) + "€ par trade)\n\n_Modifier : /broker, /capital ou /risque_\n\n📖 Tapez /aide pour voir toutes les commandes\n🎁 Vous avez *5 questions gratuites* — Postez votre question ou screenshot ! 📈",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except:
            send_risk_keyboard(user_id)
        return

    if onboarding_step == 4:
        try:
            risk = float(message.text.strip().replace("%", "").replace(",", "."))
            if risk <= 0 or risk > 100:
                raise ValueError
            set_risk(user_id, risk)
            set_onboarding_step(user_id, 0)
            user = get_user(user_id)
            broker = user.get("broker", "") if user else ""
            capital = user.get("capital", 0) if user else 0
            risque_euros = round(capital * risk / 100, 2)
            bot.send_message(
                user_id,
                "✅ *Profil configuré !*\n\n🏦 Broker : *" + broker + "*\n💰 Capital : *" + str(capital) + "€*\n📊 Risque : *" + str(risk) + "%* (" + str(risque_euros) + "€ par trade)\n\n_Modifier : /broker, /capital ou /risque_\n\n📖 Tapez /aide pour voir toutes les commandes\n🎁 Vous avez *5 questions gratuites* — Postez votre question ou screenshot ! 📈",
                parse_mode="Markdown"
            )
        except:
            bot.send_message(user_id, "⚠️ Entrez un nombre valide (ex: 3)")
        return

    # Signal en attente — extraction intelligente du capital
    pending = get_pending_signal(user_id)
    if pending:
        try:
            numbers = re.findall(r'\d+(?:[.,]\d+)?', message.text.strip())
            if numbers:
                capital_input = float(numbers[0].replace(",", "."))
                if capital_input > 0:
                    set_capital(user_id, capital_input, is_initial=False)
                    check_and_send_alerts(user_id, capital_input)
                    signal = parse_signal(pending)
                    risk = user.get("risk_percent", 1.0) if user else 1.0
                    broker = user.get("broker", "") if user else ""
                    lots = calculate_lots(capital_input, risk, signal)
                    delete_pending_signal(user_id)
                    if lots:
                        result = format_signal_with_lots(signal, lots, capital_input, risk, broker)
                        bot.reply_to(message, result, parse_mode="Markdown")
                    else:
                        bot.reply_to(message, "⚠️ Impossible de calculer les lots pour ce signal.")
                    return
            else:
                delete_pending_signal(user_id)
        except:
            delete_pending_signal(user_id)

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

    if price_info and is_price_only_request(message.text):
        if is_premium(user_id):
            footer = "\n\n_✨ Membre Premium_"
        else:
            footer = "\n\n_" + str(remaining) + " question(s) gratuite(s) restante(s)_"
        bot.reply_to(message, price_info + footer, parse_mode="Markdown")
        return

    try:
        user_context = ""
        if user and user.get("broker"):
            user_context += "Broker : " + user["broker"] + ". "
        if user and user.get("capital"):
            user_context += "Capital actuel : " + str(user["capital"]) + "€. "
        if user and user.get("risk_percent"):
            user_context += "Risque par trade : " + str(user["risk_percent"]) + "%. "

        user_content = message.text
        if price_info:
            user_content = message.text + "\n\n[DONNEES EN TEMPS REEL: " + price_info + "]"
        if user_context:
            user_content = "[PROFIL: " + user_context + "]\n\n" + user_content

        history = get_history(user_id)
        messages_with_history = history + [{"role": "user", "content": user_content}]

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="Tu es un assistant trading expert et concis. Reponds UNIQUEMENT a ce qui est demande. Si on te demande un cours, utilise UNIQUEMENT le prix fourni. Pour les calculs de lots, minimum 0.01 lot. Tiens compte du broker, capital et % risque si fournis. Reponds en francais. Tu te souviens du contexte des echanges precedents et tu gardes une conversation coherente et professionnelle.",
            messages=messages_with_history,
        )
        answer = response.content[0].text
        save_message(user_id, "user", user_content)
        save_message(user_id, "assistant", answer)

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
    scheduler_thread = Thread(target=morning_briefing_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()

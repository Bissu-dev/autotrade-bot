import os
import telebot
import anthropic
import requests
from collections import defaultdict

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

user_question_count = defaultdict(int)
MAX_FREE_QUESTIONS = 5

def get_crypto_price(symbol):
    """Récupère le prix en temps réel depuis CoinGecko"""
    ids = {
        "btc": "bitcoin", "bitcoin": "bitcoin",
        "eth": "ethereum", "ethereum": "ethereum",
        "bnb": "binancecoin", "sol": "solana", "solana": "solana",
        "xrp": "ripple", "ripple": "ripple",
        "ada": "cardano", "cardano": "cardano",
        "doge": "dogecoin", "dogecoin": "dogecoin",
        "usdt": "tether", "usdc": "usd-coin",
        "dot": "polkadot", "matic": "matic-network",
        "ltc": "litecoin", "litecoin": "litecoin",
        "avax": "avalanche-2", "link": "chainlink",
    }
    coin_id = ids.get(symbol.lower())
    if not coin_id:
        return None
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

def detect_crypto_in_message(text):
    """Détecte si le message parle d'une crypto"""
    cryptos = ["btc", "bitcoin", "eth", "ethereum", "bnb", "sol", "solana",
               "xrp", "ripple", "ada", "cardano", "doge", "dogecoin",
               "usdt", "usdc", "dot", "matic", "ltc", "litecoin", "avax", "link"]
    text_lower = text.lower()
    for crypto in cryptos:
        if crypto in text_lower:
            return crypto
    return None

def get_language(text):
    italian_words = ["ciao", "come", "cosa", "perché", "quando", "dove", "grazie", "aiuto"]
    text_lower = text.lower()
    if any(w in text_lower for w in italian_words):
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
        "fr": "👋 Bienvenue sur AutoTrade Bot !\n\nJe suis votre assistant trading alimenté par Claude AI.\n✅ Prix crypto en temps réel\n✅ Analyse de marché\n✅ Conseils trading\n\nVous avez droit à *5 questions gratuites*.\n\nPostez votre question sur le trading ! 📈",
        "it": "👋 Benvenuto su AutoTrade Bot!\n\nSono il tuo assistente trading powered by Claude AI.\n✅ Prezzi crypto in tempo reale\n✅ Analisi di mercato\n✅ Consigli di trading\n\nHai diritto a *5 domande gratuite*.\n\nFai la tua domanda sul trading! 📈",
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

    # Vérifier si prix crypto demandé
    crypto = detect_crypto_in_message(message.text)
    price_info = ""
    if crypto:
        price_data = get_crypto_price(crypto)
        if price_data:
            price_info = f"\n\n📡 *Prix en temps réel :*\n{price_data}\n\n"

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="Tu es un expert en trading crypto et finance. Réponds de manière concise et professionnelle. Réponds toujours en français sauf si l'utilisateur écrit en italien. Ne donne pas de prix car ils sont fournis séparément en temps réel.",
            messages=[{"role": "user", "content": message.text}]
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

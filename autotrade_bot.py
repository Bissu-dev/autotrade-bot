import os
import telebot
import anthropic
from collections import defaultdict

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Compteur de questions par utilisateur
user_question_count = defaultdict(int)
MAX_FREE_QUESTIONS = 5

def get_language(text):
    """Détecte la langue approximativement"""
    italian_words = ["ciao", "come", "cosa", "perché", "quando", "dove", "grazie", "aiuto"]
    french_words = ["bonjour", "comment", "pourquoi", "quand", "merci", "aide", "qu'est", "c'est"]
    text_lower = text.lower()
    if any(w in text_lower for w in italian_words):
        return "it"
    elif any(w in text_lower for w in french_words):
        return "fr"
    return "en"

def get_blocked_message(lang):
    messages = {
        "fr": "🚫 Vous avez utilisé vos 5 questions gratuites.\n\nPour continuer, rejoignez notre canal premium : @AutoTrade",
        "it": "🚫 Hai utilizzato le tue 5 domande gratuite.\n\nPer continuare, unisciti al nostro canale premium: @AutoTrade",
        "en": "🚫 You've used your 5 free questions.\n\nTo continue, join our premium channel: @AutoTrade"
    }
    return messages.get(lang, messages["en"])

@bot.message_handler(commands=["start"])
def send_welcome(message):
    lang = get_language(message.text)
    welcome = {
        "fr": "👋 Bienvenue sur AutoTrade Bot !\n\nJe suis votre assistant trading alimenté par Claude AI.\nVous avez droit à *5 questions gratuites*.\n\nPostez votre question sur le trading ! 📈",
        "it": "👋 Benvenuto su AutoTrade Bot!\n\nSono il tuo assistente trading powered by Claude AI.\nHai diritto a *5 domande gratuite*.\n\nFai la tua domanda sul trading! 📈",
        "en": "👋 Welcome to AutoTrade Bot!\n\nI'm your trading assistant powered by Claude AI.\nYou have *5 free questions*.\n\nAsk me anything about trading! 📈"
    }
    bot.reply_to(message, welcome.get(lang, welcome["en"]), parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    lang = get_language(message.text)

    if user_question_count[user_id] >= MAX_FREE_QUESTIONS:
        bot.reply_to(message, get_blocked_message(lang))
        return

    user_question_count[user_id] += 1
    remaining = MAX_FREE_QUESTIONS - user_question_count[user_id]

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="You are an expert trading assistant. Answer concisely and professionally about trading, crypto, stocks, forex. Respond in the same language as the user.",
            messages=[{"role": "user", "content": message.text}]
        )
        answer = response.content[0].text
        footer = {
            "fr": f"\n\n_{remaining} question(s) gratuite(s) restante(s)_",
            "it": f"\n\n_{remaining} domanda/e gratuita/e rimanente/i_",
            "en": f"\n\n_{remaining} free question(s) remaining_"
        }
        bot.reply_to(message, answer + footer.get(lang, footer["en"]), parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {str(e)}")

if __name__ == "__main__":
    print("AutoTrade Bot is running...")
    bot.infinity_polling()

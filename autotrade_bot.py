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
TP_REPARTITION = [0.40, 0.25, 0.15, 0.10, 0.05, 0.03, 0.02]
BROKERS = ["Vantage", "VT Markets", "StarTrader", "ACY Trading", "Puprime", "Autre"]
RISK_OPTIONS_LABELS = ["1%", "2.5%", "5%", "10%"]
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

T = {
    "welcome": {
        "fr": """👋 *Bienvenue sur AutoTrade Bot !*

Je suis votre assistant trading personnel, disponible 24h/24 et 7j/7.

💹 *Ce que je peux faire pour vous :*

✅ Prix en temps réel — Crypto, Forex, Or, Indices
✅ Signaux automatiques avec calcul de lots
✅ Morning briefing à 8h30 tous les matins
✅ Analyse de vos graphiques TradingView
✅ Niveaux clés — Support, Résistance, Objectifs
✅ Gestion du risque personnalisée
✅ Live exclusif chaque semaine réservé aux abonnés

📖 Tapez /aide pour voir toutes les commandes

_Avant de commencer, j'ai besoin de 3 informations rapides_ 👇""",

        "en": """👋 *Welcome to AutoTrade Bot!*

I am your personal trading assistant, available 24/7.

💹 *What I can do for you:*

✅ Real-time prices — Crypto, Forex, Gold, Indices
✅ Automatic signals with lot calculation
✅ Morning briefing every day at 8:30 AM
✅ TradingView chart analysis
✅ Key levels — Support, Resistance, Targets
✅ Personalized risk management
✅ Exclusive weekly live for subscribers only

📖 Type /help to see all commands

_Before we start, I need 3 quick details_ 👇""",

        "it": """👋 *Benvenuto su AutoTrade Bot!*

Sono il tuo assistente di trading personale, disponibile 24 ore su 24, 7 giorni su 7.

💹 *Cosa posso fare per te:*

✅ Prezzi in tempo reale — Crypto, Forex, Oro, Indici
✅ Segnali automatici con calcolo dei lotti
✅ Morning briefing ogni mattina alle 8:30
✅ Analisi dei grafici TradingView
✅ Livelli chiave — Supporto, Resistenza, Obiettivi
✅ Gestione del rischio personalizzata
✅ Live esclusivo ogni settimana per gli abbonati

📖 Digita /aiuto per vedere tutti i comandi

_Prima di iniziare, ho bisogno di 3 informazioni rapide_ 👇""",

        "es": """👋 *¡Bienvenido a AutoTrade Bot!*

Soy tu asistente de trading personal, disponible las 24 horas del día, los 7 días de la semana.

💹 *Lo que puedo hacer por ti:*

✅ Precios en tiempo real — Cripto, Forex, Oro, Índices
✅ Señales automáticas con cálculo de lotes
✅ Morning briefing todos los días a las 8:30
✅ Análisis de gráficos TradingView
✅ Niveles clave — Soporte, Resistencia, Objetivos
✅ Gestión de riesgo personalizada
✅ Live exclusivo cada semana para suscriptores

📖 Escribe /ayuda para ver todos los comandos

_Antes de empezar, necesito 3 datos rápidos_ 👇""",
    },

    "choose_lang": {
        "fr": "🌍 *Choisissez votre langue / Choose your language / Scegli la lingua / Elige tu idioma :*",
        "en": "🌍 *Choisissez votre langue / Choose your language / Scegli la lingua / Elige tu idioma :*",
        "it": "🌍 *Choisissez votre langue / Choose your language / Scegli la lingua / Elige tu idioma :*",
        "es": "🌍 *Choisissez votre langue / Choose your language / Scegli la lingua / Elige tu idioma :*",
    },

    "lang_saved": {
        "fr": "✅ Langue définie : Français 🇫🇷",
        "en": "✅ Language set: English 🇬🇧",
        "it": "✅ Lingua impostata: Italiano 🇮🇹",
        "es": "✅ Idioma establecido: Español 🇪🇸",
    },

    "choose_broker": {
        "fr": "🏦 *Quel broker utilisez-vous ?*\n\n_Sélectionnez dans la liste :_",
        "en": "🏦 *Which broker do you use?*\n\n_Select from the list:_",
        "it": "🏦 *Quale broker utilizzi?*\n\n_Seleziona dalla lista:_",
        "es": "🏦 *¿Qué broker utilizas?*\n\n_Selecciona de la lista:_",
    },

    "broker_saved": {
        "fr": "✅ Broker : *{broker}*\n\n💰 *Quel est votre capital de trading ?*\n_(ex: 2000 pour 2000€)_",
        "en": "✅ Broker: *{broker}*\n\n💰 *What is your trading capital?*\n_(e.g. 2000 for €2000)_",
        "it": "✅ Broker: *{broker}*\n\n💰 *Qual è il tuo capitale di trading?*\n_(es: 2000 per €2000)_",
        "es": "✅ Broker: *{broker}*\n\n💰 *¿Cuál es tu capital de trading?*\n_(ej: 2000 para €2000)_",
    },

    "invalid_broker": {
        "fr": "⚠️ Veuillez sélectionner un broker dans la liste.",
        "en": "⚠️ Please select a broker from the list.",
        "it": "⚠️ Per favore seleziona un broker dalla lista.",
        "es": "⚠️ Por favor selecciona un broker de la lista.",
    },

    "invalid_capital": {
        "fr": "⚠️ Veuillez entrer un montant valide (ex: 2000)",
        "en": "⚠️ Please enter a valid amount (e.g. 2000)",
        "it": "⚠️ Per favore inserisci un importo valido (es: 2000)",
        "es": "⚠️ Por favor ingresa un monto válido (ej: 2000)",
    },

    "choose_risk": {
        "fr": "📊 *Quel % de risque par trade ?*\n\n• 1% = conservateur\n• 2.5% = modéré\n• 5% = agressif\n• 10% = très agressif",
        "en": "📊 *What % risk per trade?*\n\n• 1% = conservative\n• 2.5% = moderate\n• 5% = aggressive\n• 10% = very aggressive",
        "it": "📊 *Quale % di rischio per trade?*\n\n• 1% = conservativo\n• 2.5% = moderato\n• 5% = aggressivo\n• 10% = molto aggressivo",
        "es": "📊 *¿Qué % de riesgo por operación?*\n\n• 1% = conservador\n• 2.5% = moderado\n• 5% = agresivo\n• 10% = muy agresivo",
    },

    "custom_risk": {
        "fr": "Personnalisé", "en": "Custom", "it": "Personalizzato", "es": "Personalizado",
    },

    "enter_custom_risk": {
        "fr": "✏️ *Entrez votre % de risque personnalisé*\n_(ex: 3 pour 3%)_",
        "en": "✏️ *Enter your custom risk %*\n_(e.g. 3 for 3%)_",
        "it": "✏️ *Inserisci la tua % di rischio personalizzata*\n_(es: 3 per 3%)_",
        "es": "✏️ *Ingresa tu % de riesgo personalizado*\n_(ej: 3 para 3%)_",
    },

    "invalid_risk": {
        "fr": "⚠️ Entrez un nombre valide (ex: 3)",
        "en": "⚠️ Enter a valid number (e.g. 3)",
        "it": "⚠️ Inserisci un numero valido (es: 3)",
        "es": "⚠️ Ingresa un número válido (ej: 3)",
    },

    "profile_complete": {
        "fr": "✅ *Profil configuré !*\n\n🏦 Broker : *{broker}*\n💰 Capital : *{capital}€*\n📊 Risque : *{risk}%* ({risk_eur}€ par trade)\n\n_Modifier : /broker, /capital ou /risque_\n\n📖 Tapez /aide pour voir toutes les commandes\n🎁 Vous avez *5 questions gratuites* — Postez votre question ou screenshot ! 📈",
        "en": "✅ *Profile configured!*\n\n🏦 Broker: *{broker}*\n💰 Capital: *{capital}€*\n📊 Risk: *{risk}%* ({risk_eur}€ per trade)\n\n_Edit: /broker, /capital or /risk_\n\n📖 Type /help to see all commands\n🎁 You have *5 free questions* — Post your question or screenshot! 📈",
        "it": "✅ *Profilo configurato!*\n\n🏦 Broker: *{broker}*\n💰 Capitale: *{capital}€*\n📊 Rischio: *{risk}%* ({risk_eur}€ per trade)\n\n_Modifica: /broker, /capitale o /rischio_\n\n📖 Digita /aiuto per vedere tutti i comandi\n🎁 Hai *5 domande gratuite* — Pubblica la tua domanda o screenshot! 📈",
        "es": "✅ *¡Perfil configurado!*\n\n🏦 Broker: *{broker}*\n💰 Capital: *{capital}€*\n📊 Riesgo: *{risk}%* ({risk_eur}€ por operación)\n\n_Editar: /broker, /capital o /riesgo_\n\n📖 Escribe /ayuda para ver todos los comandos\n🎁 Tienes *5 preguntas gratuitas* — ¡Publica tu pregunta o screenshot! 📈",
    },

    "new_signal": {
        "fr": "📡 *Nouveau signal !*\n\n{signal}\n\n💰 *Quel est votre capital actuel ?*{capital_info}\n_(ex: 2000)_",
        "en": "📡 *New signal!*\n\n{signal}\n\n💰 *What is your current capital?*{capital_info}\n_(e.g. 2000)_",
        "it": "📡 *Nuovo segnale!*\n\n{signal}\n\n💰 *Qual è il tuo capitale attuale?*{capital_info}\n_(es: 2000)_",
        "es": "📡 *¡Nueva señal!*\n\n{signal}\n\n💰 *¿Cuál es tu capital actual?*{capital_info}\n_(ej: 2000)_",
    },

    "last_capital": {
        "fr": "\n_Dernier capital enregistré : {capital}€_",
        "en": "\n_Last recorded capital: {capital}€_",
        "it": "\n_Ultimo capitale registrato: {capital}€_",
        "es": "\n_Último capital registrado: {capital}€_",
    },

    "signal_error": {
        "fr": "⚠️ Impossible de calculer les lots pour ce signal.",
        "en": "⚠️ Unable to calculate lots for this signal.",
        "it": "⚠️ Impossibile calcolare i lotti per questo segnale.",
        "es": "⚠️ No se pueden calcular los lotes para esta señal.",
    },

    "analyzing": {
        "fr": "🔍 Analyse du graphique en cours...",
        "en": "🔍 Analyzing chart...",
        "it": "🔍 Analisi del grafico in corso...",
        "es": "🔍 Analizando gráfico...",
    },

    "morning_generating": {
        "fr": "⏳ Génération du briefing en cours...",
        "en": "⏳ Generating briefing...",
        "it": "⏳ Generazione del briefing in corso...",
        "es": "⏳ Generando briefing...",
    },

    "morning_premium_only": {
        "fr": "⭐ Cette fonctionnalité est réservée aux membres Premium.\n\nAbonnez-vous avec /abonnement 🚀",
        "en": "⭐ This feature is reserved for Premium members.\n\nSubscribe with /subscription 🚀",
        "it": "⭐ Questa funzionalità è riservata ai membri Premium.\n\nAbbonati con /abbonamento 🚀",
        "es": "⭐ Esta función está reservada para miembros Premium.\n\nSuscríbete con /suscripcion 🚀",
    },

    "already_premium": {
        "fr": "✅ Vous êtes déjà membre Premium ! Profitez de vos avantages exclusifs. 🚀",
        "en": "✅ You are already a Premium member! Enjoy your exclusive benefits. 🚀",
        "it": "✅ Sei già un membro Premium! Goditi i tuoi vantaggi esclusivi. 🚀",
        "es": "✅ ¡Ya eres miembro Premium! Disfruta de tus beneficios exclusivos. 🚀",
    },

    "new_conversation": {
        "fr": "🔄 Nouvelle conversation démarrée !",
        "en": "🔄 New conversation started!",
        "it": "🔄 Nuova conversazione avviata!",
        "es": "🔄 ¡Nueva conversación iniciada!",
    },

    "profil": {
        "fr": "👤 *Votre profil :*\n\n🏦 Broker : *{broker}*\n💰 Capital initial : *{capital_initial}*\n💰 Capital actuel : *{capital}*{perf}\n📊 Risque : *{risk}%* ({risk_eur}€ par trade)\n⭐ Statut : *{status}*\n\n_Modifier : /broker, /capital ou /risque_",
        "en": "👤 *Your profile:*\n\n🏦 Broker: *{broker}*\n💰 Initial capital: *{capital_initial}*\n💰 Current capital: *{capital}*{perf}\n📊 Risk: *{risk}%* ({risk_eur}€ per trade)\n⭐ Status: *{status}*\n\n_Edit: /broker, /capital or /risk_",
        "it": "👤 *Il tuo profilo:*\n\n🏦 Broker: *{broker}*\n💰 Capitale iniziale: *{capital_initial}*\n💰 Capitale attuale: *{capital}*{perf}\n📊 Rischio: *{risk}%* ({risk_eur}€ per trade)\n⭐ Stato: *{status}*\n\n_Modifica: /broker, /capitale o /rischio_",
        "es": "👤 *Tu perfil:*\n\n🏦 Broker: *{broker}*\n💰 Capital inicial: *{capital_initial}*\n💰 Capital actual: *{capital}*{perf}\n📊 Riesgo: *{risk}%* ({risk_eur}€ por operación)\n⭐ Estado: *{status}*\n\n_Editar: /broker, /capital o /riesgo_",
    },

    "premium_status": {"fr": "✅ Premium", "en": "✅ Premium", "it": "✅ Premium", "es": "✅ Premium"},
    "free_status": {"fr": "❌ Gratuit", "en": "❌ Free", "it": "❌ Gratuito", "es": "❌ Gratuito"},

    "not_found": {
        "fr": "Aucun profil trouvé. Tapez /start pour commencer.",
        "en": "No profile found. Type /start to begin.",
        "it": "Nessun profilo trovato. Digita /start per iniziare.",
        "es": "No se encontró perfil. Escribe /start para comenzar.",
    },

    "aide": {
        "fr": """📖 *Commandes disponibles :*

💹 *Trading*
/morning — Briefing des marchés du jour ⭐
/profil — Voir votre profil et performance

⚙️ *Paramètres*
/broker — Changer de broker
/capital — Mettre à jour votre capital
/risque — Modifier votre % de risque
/nouveau — Nouvelle conversation
/langue — Changer de langue

💳 *Abonnement*
/abonnement — Voir les offres Premium

_Posez vos questions en texte ou envoyez un screenshot !_""",

        "en": """📖 *Available commands:*

💹 *Trading*
/morning — Market briefing of the day ⭐
/profile — View your profile and performance

⚙️ *Settings*
/broker — Change broker
/capital — Update your capital
/risk — Modify your risk %
/new — New conversation
/language — Change language

💳 *Subscription*
/subscription — View Premium offers

_Ask questions in text or send a screenshot!_""",

        "it": """📖 *Comandi disponibili:*

💹 *Trading*
/morning — Briefing di mercato del giorno ⭐
/profilo — Visualizza il tuo profilo e performance

⚙️ *Impostazioni*
/broker — Cambia broker
/capitale — Aggiorna il tuo capitale
/rischio — Modifica la tua % di rischio
/nuovo — Nuova conversazione
/lingua — Cambia lingua

💳 *Abbonamento*
/abbonamento — Visualizza le offerte Premium

_Fai domande in testo o invia uno screenshot!_""",

        "es": """📖 *Comandos disponibles:*

💹 *Trading*
/morning — Briefing de mercado del día ⭐
/perfil — Ver tu perfil y rendimiento

⚙️ *Configuración*
/broker — Cambiar broker
/capital — Actualizar tu capital
/riesgo — Modificar tu % de riesgo
/nuevo — Nueva conversación
/idioma — Cambiar idioma

💳 *Suscripción*
/suscripcion — Ver ofertas Premium

_¡Haz preguntas en texto o envía una captura de pantalla!_""",
    },

    "subscription_included": {
        "fr": "⭐ *Inclus dans chaque abonnement :*\n✅ Questions illimitées 24h/24\n✅ Signaux automatiques avec calcul de lots\n✅ Morning briefing à 8h30 tous les matins\n✅ Live exclusif chaque semaine réservé aux abonnés\n\n",
        "en": "⭐ *Included in every subscription:*\n✅ Unlimited questions 24/7\n✅ Automatic signals with lot calculation\n✅ Morning briefing every day at 8:30 AM\n✅ Exclusive weekly live for subscribers only\n\n",
        "it": "⭐ *Incluso in ogni abbonamento:*\n✅ Domande illimitate 24 ore su 24\n✅ Segnali automatici con calcolo dei lotti\n✅ Morning briefing ogni mattina alle 8:30\n✅ Live esclusivo ogni settimana per gli abbonati\n\n",
        "es": "⭐ *Incluido en cada suscripción:*\n✅ Preguntas ilimitadas 24/7\n✅ Señales automáticas con cálculo de lotes\n✅ Morning briefing todos los días a las 8:30\n✅ Live exclusivo cada semana para suscriptores\n\n",
    },

    "subscription_blocked": {
        "fr": "🚫 *Vous avez utilisé vos 5 questions gratuites.*\n\nPour continuer, choisissez votre abonnement :\n\n",
        "en": "🚫 *You have used your 5 free questions.*\n\nTo continue, choose your subscription:\n\n",
        "it": "🚫 *Hai utilizzato le tue 5 domande gratuite.*\n\nPer continuare, scegli il tuo abbonamento:\n\n",
        "es": "🚫 *Has usado tus 5 preguntas gratuitas.*\n\nPara continuar, elige tu suscripción:\n\n",
    },

    "subscription_secure": {
        "fr": "\n✅ Paiement sécurisé par Stripe",
        "en": "\n✅ Secure payment by Stripe",
        "it": "\n✅ Pagamento sicuro tramite Stripe",
        "es": "\n✅ Pago seguro por Stripe",
    },

    "premium_activated": {
        "fr": "🎉 *Accès Premium activé !*\n\n✅ Questions illimitées 24h/24\n✅ Signaux automatiques avec calcul de lots\n✅ Morning briefing à 8h30 tous les matins\n✅ Live exclusif chaque semaine\n\n📖 Tapez /aide pour voir toutes les commandes ! 🚀",
        "en": "🎉 *Premium access activated!*\n\n✅ Unlimited questions 24/7\n✅ Automatic signals with lot calculation\n✅ Morning briefing every day at 8:30 AM\n✅ Exclusive weekly live\n\n📖 Type /help to see all commands! 🚀",
        "it": "🎉 *Accesso Premium attivato!*\n\n✅ Domande illimitate 24 ore su 24\n✅ Segnali automatici con calcolo dei lotti\n✅ Morning briefing ogni mattina alle 8:30\n✅ Live esclusivo ogni settimana\n\n📖 Digita /aiuto per vedere tutti i comandi! 🚀",
        "es": "🎉 *¡Acceso Premium activado!*\n\n✅ Preguntas ilimitadas 24/7\n✅ Señales automáticas con cálculo de lotes\n✅ Morning briefing todos los días a las 8:30\n✅ Live exclusivo cada semana\n\n📖 Escribe /ayuda para ver todos los comandos! 🚀",
    },

    "payment_confirmed": {
        "fr": "🎉 *Paiement confirmé !*\n\nBienvenue dans AutoTrade Premium ! 🚀\n\n✅ Questions illimitées 24h/24\n✅ Signaux automatiques avec calcul de lots\n✅ Morning briefing à 8h30 tous les matins\n✅ Live exclusif chaque semaine\n\n📖 Tapez /aide pour voir toutes les commandes !",
        "en": "🎉 *Payment confirmed!*\n\nWelcome to AutoTrade Premium! 🚀\n\n✅ Unlimited questions 24/7\n✅ Automatic signals with lot calculation\n✅ Morning briefing every day at 8:30 AM\n✅ Exclusive weekly live\n\n📖 Type /help to see all commands!",
        "it": "🎉 *Pagamento confermato!*\n\nBenvenuto in AutoTrade Premium! 🚀\n\n✅ Domande illimitate 24 ore su 24\n✅ Segnali automatici con calcolo dei lotti\n✅ Morning briefing ogni mattina alle 8:30\n✅ Live esclusivo ogni settimana\n\n📖 Digita /aiuto per vedere tutti i comandi!",
        "es": "🎉 *¡Pago confirmado!*\n\n¡Bienvenido a AutoTrade Premium! 🚀\n\n✅ Preguntas ilimitadas 24/7\n✅ Señales automáticas con cálculo de lotes\n✅ Morning briefing todos los días a las 8:30\n✅ Live exclusivo cada semana\n\n📖 Escribe /ayuda para ver todos los comandos!",
    },

    "subscription_cancelled": {
        "fr": "❌ Votre abonnement AutoTrade a été annulé.\n\nVous pouvez vous réabonner avec /abonnement.",
        "en": "❌ Your AutoTrade subscription has been cancelled.\n\nYou can resubscribe with /subscription.",
        "it": "❌ Il tuo abbonamento AutoTrade è stato annullato.\n\nPuoi riabbonarti con /abbonamento.",
        "es": "❌ Tu suscripción AutoTrade ha sido cancelada.\n\nPuedes volver a suscribirte con /suscripcion.",
    },

    "footer_premium": {
        "fr": "\n\n_✨ Membre Premium_",
        "en": "\n\n_✨ Premium Member_",
        "it": "\n\n_✨ Membro Premium_",
        "es": "\n\n_✨ Miembro Premium_",
    },

    "footer_free": {
        "fr": "\n\n_{count} question(s) gratuite(s) restante(s)_",
        "en": "\n\n_{count} free question(s) remaining_",
        "it": "\n\n_{count} domanda/e gratuita/e rimanente/i_",
        "es": "\n\n_{count} pregunta(s) gratuita(s) restante(s)_",
    },

    "signal_lots_header": {
        "fr": "📊 *Tailles de lot par TP :*\n\n",
        "en": "📊 *Lot sizes per TP:*\n\n",
        "it": "📊 *Dimensioni del lotto per TP:*\n\n",
        "es": "📊 *Tamaños de lote por TP:*\n\n",
    },

    "signal_optional": {
        "fr": " _(optionnel)_", "en": " _(optional)_",
        "it": " _(opzionale)_", "es": " _(opcional)_",
    },

    "signal_footer": {
        "fr": "⚠️ _Tailles indicatives — adaptez selon votre levier_",
        "en": "⚠️ _Indicative sizes — adjust according to your leverage_",
        "it": "⚠️ _Dimensioni indicative — adatta in base alla tua leva_",
        "es": "⚠️ _Tamaños indicativos — ajusta según tu apalancamiento_",
    },

    "image_error": {
        "fr": "Impossible de lire l'image.",
        "en": "Unable to read the image.",
        "it": "Impossibile leggere l'immagine.",
        "es": "No se puede leer la imagen.",
    },

    "change_capital": {
        "fr": "💰 *Quel est votre capital actuel ?*\n_(ex: 2000 pour 2000€)_",
        "en": "💰 *What is your current capital?*\n_(e.g. 2000 for €2000)_",
        "it": "💰 *Qual è il tuo capitale attuale?*\n_(es: 2000 per €2000)_",
        "es": "💰 *¿Cuál es tu capital actual?*\n_(ej: 2000 para €2000)_",
    },

    "price_realtime": {
        "fr": "Prix en temps réel", "en": "Real-time price",
        "it": "Prezzo in tempo reale", "es": "Precio en tiempo real",
    },
}

MORNING_SYSTEM_PROMPT = {
    "fr": """Tu es un analyste financier expert qui rédige un morning briefing quotidien pour des traders.
Tu dois produire un briefing COMPLET et QUALITATIF en français avec ces sections EXACTES :

1. 📰 ACTUALITÉS MACRO DU JOUR
Liste 4-5 thèmes macro importants qui peuvent impacter les marchés AUJOURD'HUI :
- Événements économiques prévus (réunions Fed/BCE, publications de données : CPI, NFP, PIB, ISM...)
- Tensions géopolitiques actuelles impactant les marchés
- Actualités sur les devises majeures
- Nouvelles crypto/réglementation
- Prix des matières premières et pétrole
Chaque point doit être une phrase COMPLÈTE et INFORMATIVE de 1-2 lignes.

2. 🎯 ANALYSE DES MARCHÉS
Pour chaque actif (BTC, ETH, OR, EUR/USD), donne :
- La tendance du jour (haussière/baissière/neutre)
- Le niveau clé à surveiller
- L'impact probable des news sur cet actif

3. ⚡ NIVEAUX CLÉS À SURVEILLER
- Support et résistance principaux pour BTC et OR
- Zone d'entrée potentielle si signal

Sois précis, professionnel et concis. Pas de phrases génériques.""",

    "en": """You are an expert financial analyst writing a daily morning briefing for traders.
Produce a COMPLETE and QUALITY briefing in English with these EXACT sections:

1. 📰 TODAY'S MACRO NEWS
List 4-5 important macro themes that can impact markets TODAY:
- Scheduled economic events (Fed/ECB meetings, data releases: CPI, NFP, GDP, ISM...)
- Current geopolitical tensions impacting markets
- Major currency news
- Crypto/regulation news
- Commodity and oil prices
Each point must be a COMPLETE and INFORMATIVE sentence of 1-2 lines.

2. 🎯 MARKET ANALYSIS
For each asset (BTC, ETH, GOLD, EUR/USD):
- Today's trend (bullish/bearish/neutral)
- Key level to watch
- Probable impact of news

3. ⚡ KEY LEVELS TO WATCH
- Main support and resistance for BTC and GOLD
- Potential entry zone if signal

Be precise, professional and concise. No generic sentences.""",

    "it": """Sei un analista finanziario esperto che scrive un morning briefing quotidiano per i trader.
Produci un briefing COMPLETO e di QUALITÀ in italiano con queste sezioni ESATTE:

1. 📰 NOTIZIE MACRO DI OGGI
Elenca 4-5 temi macro importanti che possono influenzare i mercati OGGI:
- Eventi economici programmati (riunioni Fed/BCE, pubblicazioni dati: CPI, NFP, PIL, ISM...)
- Tensioni geopolitiche attuali che impattano i mercati
- Notizie sulle valute principali
- Notizie crypto/regolamentazione
- Prezzi delle materie prime e del petrolio
Ogni punto deve essere una frase COMPLETA e INFORMATIVA di 1-2 righe.

2. 🎯 ANALISI DEI MERCATI
Per ogni asset (BTC, ETH, ORO, EUR/USD):
- Il trend del giorno (rialzista/ribassista/neutro)
- Il livello chiave da monitorare
- L'impatto probabile delle notizie

3. ⚡ LIVELLI CHIAVE DA MONITORARE
- Supporto e resistenza principali per BTC e ORO
- Zona di entrata potenziale se segnale

Sii preciso, professionale e conciso.""",

    "es": """Eres un analista financiero experto que redacta un morning briefing diario para traders.
Produce un briefing COMPLETO y de CALIDAD en español con estas secciones EXACTAS:

1. 📰 NOTICIAS MACRO DE HOY
Lista 4-5 temas macro importantes que pueden impactar los mercados HOY:
- Eventos económicos programados (reuniones Fed/BCE, publicaciones de datos: CPI, NFP, PIB, ISM...)
- Tensiones geopolíticas actuales que impactan los mercados
- Noticias sobre divisas principales
- Noticias crypto/regulación
- Precios de materias primas y petróleo
Cada punto debe ser una frase COMPLETA e INFORMATIVA de 1-2 líneas.

2. 🎯 ANÁLISIS DE MERCADOS
Para cada activo (BTC, ETH, ORO, EUR/USD):
- La tendencia del día (alcista/bajista/neutral)
- El nivel clave a vigilar
- El impacto probable de las noticias

3. ⚡ NIVELES CLAVE A VIGILAR
- Soporte y resistencia principales para BTC y ORO
- Zona de entrada potencial si señal

Sé preciso, profesional y conciso.""",
}

def t(key, lang, **kwargs):
    text = T.get(key, {}).get(lang, T.get(key, {}).get("fr", ""))
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text

PRICE_ONLY_KEYWORDS = {
    "fr": ["cours", "prix", "combien", "coute", "vaut", "valeur", "cote", "tarif"],
    "en": ["price", "cost", "worth", "value", "rate", "how much", "quote"],
    "it": ["prezzo", "quanto", "vale", "valore", "costo", "quotazione"],
    "es": ["precio", "cuanto", "vale", "valor", "costo", "cotizacion"],
}

def is_price_only_request(text, lang="fr"):
    text_lower = text.lower()
    keywords = PRICE_ONLY_KEYWORDS.get(lang, PRICE_ONLY_KEYWORDS["fr"])
    has_price = any(w in text_lower for w in keywords)
    has_analysis = any(w in text_lower for w in [
        "analyse", "analysis", "analisi", "analisis", "resistance", "support",
        "tendance", "trend", "signal", "lot", "strategie", "strategy", "strategia",
        "bullish", "bearish", "pourquoi", "why", "perche", "porque"
    ])
    return has_price and not has_analysis

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
            langue TEXT DEFAULT 'fr',
            alerte_danger_envoyee BOOLEAN DEFAULT FALSE,
            alerte_profit_envoyee BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for col in [
        "broker TEXT", "capital FLOAT", "capital_initial FLOAT",
        "risk_percent FLOAT DEFAULT 1.0", "onboarding_step INTEGER DEFAULT 0",
        "langue TEXT DEFAULT 'fr'",
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
            onboarding_step, langue, alerte_danger_envoyee, alerte_profit_envoyee
            FROM users WHERE telegram_id = %s
        """, (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            cols = ["telegram_id", "is_premium", "question_count", "stripe_customer_id",
                    "subscription_id", "plan", "broker", "capital", "capital_initial",
                    "risk_percent", "onboarding_step", "langue",
                    "alerte_danger_envoyee", "alerte_profit_envoyee"]
            return dict(zip(cols, row))
        return None
    except:
        return None

def get_lang(user_id):
    user = get_user(user_id)
    if user and user.get("langue"):
        return user["langue"]
    return "fr"

def get_all_premium():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT telegram_id, plan, langue FROM users WHERE is_premium = TRUE")
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

def set_field(user_id, field, value):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO users (telegram_id, {field})
            VALUES (%s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET {field} = %s, updated_at = NOW()
        """, (user_id, value, value))
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
        """, (user_id, status, plan, stripe_customer_id, subscription_id,
              status, plan, stripe_customer_id, subscription_id))
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
            msg += "🌍 Langue : " + str(user.get("langue", "fr")).upper() + "\n"
            msg += "⚠️ Capital sous 250€" if capital_actuel < 250 else "⚠️ Perte > 50%"
            bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET alerte_danger_envoyee = TRUE WHERE telegram_id = %s", (user_id,))
            conn.commit()
            cur.close()
            conn.close()

        if not alerte_profit and variation >= 100:
            msg = "🟢 *ALERTE PERFORMANCE*\n\n"
            msg += "👤 ID : " + str(user_id) + "\n"
            msg += "🏦 Broker : " + broker + "\n"
            msg += "💰 Initial : " + str(capital_initial) + "€ → Actuel : " + str(capital_actuel) + "€\n"
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
    lot_total = max(0.01, round((risque_total / sl_distance) / 0.01) * 0.01)
    result = []
    for i, tp in enumerate(signal["tps"]):
        pct = TP_REPARTITION[i] if i < len(TP_REPARTITION) else 0.02
        lot = max(0.01, round((lot_total * pct) / 0.01) * 0.01)
        tp_distance = abs(tp - entry)
        gain_potentiel = round(lot * tp_distance, 2)
        risque_tp = round(lot * sl_distance, 2)
        rr = round(tp_distance / sl_distance, 1) if sl_distance > 0 else 0
        result.append({
            "tp_num": i + 1, "tp_price": tp, "lot": lot,
            "pct": int(pct * 100), "risque": risque_tp,
            "gain": gain_potentiel, "rr": rr, "optional": i >= 3
        })
    return result

def format_signal_with_lots(signal, lots, capital, risk_percent, lang="fr", broker=""):
    direction = signal.get("direction", "")
    asset = signal.get("asset", "")
    entry_low = signal.get("entry_low", "")
    entry_high = signal.get("entry_high", "")
    sl = signal.get("sl", "")
    emoji = "📈" if direction == "BUY" else "📉"
    broker_str = " — " + broker if broker else ""
    risque_total = round(capital * (risk_percent / 100), 2)
    entry_label = {"fr": "Entrée", "en": "Entry", "it": "Entrata", "es": "Entrada"}.get(lang, "Entrée")
    risk_label = {"fr": "Risque", "en": "Risk", "it": "Rischio", "es": "Riesgo"}.get(lang, "Risque")
    gain_label = {"fr": "Gain potentiel", "en": "Potential gain", "it": "Guadagno potenziale", "es": "Ganancia potencial"}.get(lang, "Gain potentiel")
    msg = emoji + " *" + direction + " " + asset + "*" + broker_str + "\n"
    msg += "💰 " + entry_label + " : " + str(entry_low) + " - " + str(entry_high) + "\n"
    msg += "🔐 Stop Loss : " + str(sl) + "\n"
    msg += "💼 Capital : " + str(capital) + "€ | " + risk_label + " : " + str(risk_percent) + "% (" + str(risque_total) + "€)\n\n"
    msg += t("signal_lots_header", lang)
    for tp in lots:
        optional_tag = t("signal_optional", lang) if tp["optional"] else ""
        msg += "TP" + str(tp["tp_num"]) + " — " + str(tp["tp_price"]) + optional_tag + "\n"
        msg += "   • Lot : *" + str(tp["lot"]) + "* (" + str(tp["pct"]) + "%)\n"
        msg += "   • " + risk_label + " : " + str(tp["risque"]) + "€ | " + gain_label + " : " + str(tp["gain"]) + "€\n"
        msg += "   • R/R : 1:" + str(tp["rr"]) + "\n\n"
    msg += t("signal_footer", lang)
    return msg

def get_live_market_data():
    data = {}
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,ripple&vs_currencies=usd&include_24hr_change=true"
        r = requests.get(url, timeout=5)
        d = r.json()
        data["BTC"] = {"price": d["bitcoin"]["usd"], "change_24h": d["bitcoin"]["usd_24h_change"]}
        data["ETH"] = {"price": d["ethereum"]["usd"], "change_24h": d["ethereum"]["usd_24h_change"]}
        data["SOL"] = {"price": d["solana"]["usd"], "change_24h": d["solana"]["usd_24h_change"]}
        data["XRP"] = {"price": d["ripple"]["usd"], "change_24h": d["ripple"]["usd_24h_change"]}
    except:
        pass
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        data["XAU"] = {"price": r.json()["price"], "change_24h": 0}
    except:
        pass
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/EUR/USD"
        r = requests.get(url, timeout=5)
        d = r.json()
        price = (d[0]["spreadProfilePrices"][0]["ask"] + d[0]["spreadProfilePrices"][0]["bid"]) / 2
        data["EURUSD"] = {"price": price, "change_24h": 0}
    except:
        pass
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC?interval=1d&range=2d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        meta = r.json()["chart"]["result"][0]["meta"]
        prev = meta["previousClose"]
        price = meta["regularMarketPrice"]
        data["NASDAQ"] = {"price": price, "change_24h": ((price - prev) / prev) * 100}
    except:
        pass
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=2d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        meta = r.json()["chart"]["result"][0]["meta"]
        prev = meta["previousClose"]
        price = meta["regularMarketPrice"]
        data["SP500"] = {"price": price, "change_24h": ((price - prev) / prev) * 100}
    except:
        pass
    return data

def get_morning_briefing(lang="fr"):
    now = datetime.now(TIMEZONE)
    date_labels = {
        "fr": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "it": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
        "es": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
    }
    month_labels = {
        "fr": ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"],
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
        "it": ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"],
        "es": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
    }
    day_name = date_labels.get(lang, date_labels["fr"])[now.weekday()]
    month_name = month_labels.get(lang, month_labels["fr"])[now.month - 1]
    date_str = day_name + " " + str(now.day) + " " + month_name + " " + str(now.year)

    market_data = get_live_market_data()

    msg = "🌅 *Morning Briefing — " + date_str + "*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    markets_label = {"fr": "📊 *Marchés en temps réel :*", "en": "📊 *Real-time markets:*", "it": "📊 *Mercati in tempo reale:*", "es": "📊 *Mercados en tiempo real:*"}.get(lang, "📊 *Marchés:*")
    msg += markets_label + "\n"

    prices_text = ""
    for symbol, info in market_data.items():
        price = info["price"]
        change = info["change_24h"]
        emoji = "🟢" if change >= 0 else "🔴"
        if symbol == "BTC":
            prices_text += emoji + " BTC : $" + "{:,.0f}".format(price) + " (" + "{:+.1f}".format(change) + "%)\n"
        elif symbol in ["ETH", "SOL", "XRP"]:
            prices_text += emoji + " " + symbol + " : $" + "{:,.2f}".format(price) + " (" + "{:+.1f}".format(change) + "%)\n"
        elif symbol == "XAU":
            prices_text += "🥇 OR : $" + "{:,.0f}".format(price) + "/oz\n"
        elif symbol == "EURUSD":
            prices_text += "💱 EUR/USD : " + "{:.4f}".format(price) + "\n"
        elif symbol == "NASDAQ":
            prices_text += emoji + " NASDAQ : " + "{:,.0f}".format(price) + " (" + "{:+.1f}".format(change) + "%)\n"
        elif symbol == "SP500":
            prices_text += emoji + " S&P500 : " + "{:,.0f}".format(price) + " (" + "{:+.1f}".format(change) + "%)\n"

    msg += prices_text + "\n"

    try:
        market_summary = "Données de marché en temps réel :\n" + prices_text
        market_summary += "\nDate : " + date_str + " | Jour : " + day_name
        system_prompt = MORNING_SYSTEM_PROMPT.get(lang, MORNING_SYSTEM_PROMPT["fr"])
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=800,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": market_summary + "\n\nRédige le morning briefing complet basé sur ces données et ta connaissance des événements macro actuels."
            }]
        )
        msg += response.content[0].text + "\n\n"
    except Exception as e:
        print("Erreur IA briefing : " + str(e))

    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    footer = {"fr": "_Bonne journée et bon trading ! 📈_", "en": "_Have a great day and good trading! 📈_", "it": "_Buona giornata e buon trading! 📈_", "es": "_¡Que tengas un gran día y buen trading! 📈_"}.get(lang, "_Bonne journée ! 📈_")
    msg += footer
    return msg

def send_morning_briefing_to_all():
    try:
        members = get_all_premium()
        sent = 0
        briefings_cache = {}
        for member in members:
            user_id = member[0]
            lang = member[2] if member[2] else "fr"
            try:
                if lang not in briefings_cache:
                    briefings_cache[lang] = get_morning_briefing(lang)
                bot.send_message(user_id, briefings_cache[lang], parse_mode="Markdown")
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
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        prices["XAU"] = r.json()["price"]
    except:
        pass
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/EUR/USD"
        r = requests.get(url, timeout=5)
        d = r.json()
        prices["EURUSD"] = (d[0]["spreadProfilePrices"][0]["ask"] + d[0]["spreadProfilePrices"][0]["bid"]) / 2
    except:
        pass
    return prices

CRYPTO_IDS = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "eth": "ethereum", "ethereum": "ethereum",
    "bnb": "binancecoin", "sol": "solana", "solana": "solana", "xrp": "ripple",
    "ripple": "ripple", "ada": "cardano", "doge": "dogecoin", "dogecoin": "dogecoin",
    "dot": "polkadot", "matic": "matic-network", "ltc": "litecoin",
    "avax": "avalanche-2", "link": "chainlink",
}

FOREX_SYMBOLS = {
    "eurusd": ("EUR", "USD"), "eur/usd": ("EUR", "USD"),
    "gbpusd": ("GBP", "USD"), "gbp/usd": ("GBP", "USD"),
    "usdjpy": ("USD", "JPY"), "usd/jpy": ("USD", "JPY"),
    "usdchf": ("USD", "CHF"), "audusd": ("AUD", "USD"),
    "usdcad": ("USD", "CAD"), "euro dollar": ("EUR", "USD"),
}

COMMODITY_KEYWORDS = {
    "gold": "XAU", "xau": "XAU", "silver": "XAG",
    "argent": "XAG", "xag": "XAG", "oro": "XAU", "plata": "XAG",
}

OR_WORDS = ["or", "l'or", "du or", "l or", "xauusd", "xau/usd"]

INDEX_SYMBOLS = {
    "nasdaq": "^IXIC", "nasdaq100": "^NDX", "sp500": "^GSPC",
    "s&p500": "^GSPC", "cac40": "^FCHI", "cac 40": "^FCHI", "dax": "^GDAXI",
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
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/" + from_currency + "/" + to_currency
        r = requests.get(url, timeout=5)
        data = r.json()
        price = (data[0]["spreadProfilePrices"][0]["ask"] + data[0]["spreadProfilePrices"][0]["bid"]) / 2
        return "💱 *" + from_currency + "/" + to_currency + "*\n💵 " + "{:.4f}".format(price)
    except:
        return None

def get_commodity_price(symbol, label):
    try:
        if symbol == "XAU":
            r = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
            return "🥇 *OR (XAU/USD)*\n💵 $" + "{:,.2f}".format(r.json()["price"]) + " USD/oz"
        elif symbol == "XAG":
            url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAG/USD"
            r = requests.get(url, timeout=5)
            data = r.json()
            price = (data[0]["spreadProfilePrices"][0]["ask"] + data[0]["spreadProfilePrices"][0]["bid"]) / 2
            return "🥈 *ARGENT (XAG/USD)*\n💵 $" + "{:,.2f}".format(price) + " USD/oz"
    except:
        return None

def get_index_price(yahoo_symbol, label):
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + yahoo_symbol + "?interval=1d&range=2d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        meta = r.json()["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta["previousClose"]
        change = ((price - prev) / prev) * 100
        emoji = "🟢" if change >= 0 else "🔴"
        return emoji + " *" + label.upper() + "*\n💵 " + "{:,.2f}".format(price) + "\n📊 24h: " + "{:+.2f}".format(change) + "%"
    except:
        return None

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

def get_blocked_message(user_id, lang="fr"):
    mensuel_url = create_checkout_session(user_id, STRIPE_PRICE_MENSUEL, "mensuel")
    trimestriel_url = create_checkout_session(user_id, STRIPE_PRICE_TRIMESTRIEL, "trimestriel")
    annuel_url = create_checkout_session(user_id, STRIPE_PRICE_ANNUEL, "annuel")
    msg = t("subscription_blocked", lang)
    msg += t("subscription_included", lang)
    if mensuel_url:
        msg += "📅 [Mensuel — 29,99€/mois](" + mensuel_url + ")\n"
    if trimestriel_url:
        msg += "📆 [Trimestriel — 74,99€/3 mois](" + trimestriel_url + ")\n"
    if annuel_url:
        msg += "🗓️ [Annuel — 239,99€/an](" + annuel_url + ")\n"
    msg += t("subscription_secure", lang)
    return msg

def download_image_as_base64(file_id):
    try:
        file_info = bot.get_file(file_id)
        file_url = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
        r = requests.get(file_url, timeout=10)
        return base64.b64encode(r.content).decode("utf-8")
    except:
        return None

def send_lang_keyboard(user_id):
    keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(
        telebot.types.KeyboardButton("🇫🇷 Français"),
        telebot.types.KeyboardButton("🇬🇧 English"),
        telebot.types.KeyboardButton("🇮🇹 Italiano"),
        telebot.types.KeyboardButton("🇪🇸 Español"),
    )
    bot.send_message(user_id, t("choose_lang", "fr"), parse_mode="Markdown", reply_markup=keyboard)

def send_broker_keyboard(user_id, lang="fr"):
    keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(*[telebot.types.KeyboardButton(b) for b in BROKERS])
    bot.send_message(user_id, t("choose_broker", lang), parse_mode="Markdown", reply_markup=keyboard)

def send_risk_keyboard(user_id, lang="fr"):
    keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    for r in RISK_OPTIONS_LABELS:
        keyboard.add(telebot.types.KeyboardButton(r))
    keyboard.add(telebot.types.KeyboardButton(t("custom_risk", lang)))
    bot.send_message(user_id, t("choose_risk", lang), parse_mode="Markdown", reply_markup=keyboard)

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("Webhook error: " + str(e))
        return jsonify({"error": "Invalid signature"}), 400

    print("Stripe event recu: " + event["type"])

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("telegram_user_id")
        plan = session.get("metadata", {}).get("plan")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        print("Paiement confirme pour user_id: " + str(user_id))
        if user_id:
            set_premium(int(user_id), True, plan, customer_id, subscription_id)
            lang = get_lang(int(user_id))
            try:
                bot.send_message(int(user_id), t("payment_confirmed", lang), parse_mode="Markdown")
                # Notifie aussi l'admin
                bot.send_message(ADMIN_ID, "💰 *Nouveau paiement !*\n\n👤 ID : " + str(user_id) + "\n📦 Plan : " + str(plan) + "\n🌍 Langue : " + str(lang).upper(), parse_mode="Markdown")
            except Exception as ex:
                print("Erreur envoi message: " + str(ex))

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
                lang = get_lang(user_id)
                set_premium(user_id, False)
                clear_history(user_id)
                try:
                    bot.send_message(user_id, t("subscription_cancelled", lang), parse_mode="Markdown")
                except:
                    pass
        except:
            pass

    return jsonify({"status": "ok"})

@app.route("/webhook/test", methods=["GET"])
def webhook_test():
    """Endpoint de test pour vérifier que le webhook est accessible"""
    return jsonify({"status": "webhook endpoint actif", "timestamp": str(datetime.now(TIMEZONE))}), 200

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
        lang = member[2] if member[2] else "fr"
        user = get_user(user_id)
        save_pending_signal(user_id, message.text)
        try:
            capital_info = ""
            if user and user.get("capital"):
                capital_info = t("last_capital", lang, capital=user["capital"])
            bot.send_message(
                user_id,
                t("new_signal", lang, signal=message.text, capital_info=capital_info),
                parse_mode="Markdown"
            )
        except:
            pass

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    clear_history(user_id)
    set_field(user_id, "onboarding_step", 0)
    send_lang_keyboard(user_id)

@bot.message_handler(commands=["morning"])
def send_morning_command(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    if not is_premium(user_id):
        bot.reply_to(message, t("morning_premium_only", lang))
        return
    bot.reply_to(message, t("morning_generating", lang))
    briefing = get_morning_briefing(lang)
    bot.send_message(user_id, briefing, parse_mode="Markdown")

@bot.message_handler(commands=["profil", "profile", "profilo", "perfil"])
def show_profil(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, t("not_found", lang))
        return
    broker = user.get("broker") or "—"
    capital = user.get("capital")
    capital_initial = user.get("capital_initial")
    risk = user.get("risk_percent") or 1.0
    capital_str = str(capital) + "€" if capital else "—"
    capital_initial_str = str(capital_initial) + "€" if capital_initial else "—"
    risque_euros = round(capital * risk / 100, 2) if capital else 0
    status = t("premium_status", lang) if user.get("is_premium") else t("free_status", lang)
    perf = ""
    if capital and capital_initial and capital_initial > 0:
        variation = ((capital - capital_initial) / capital_initial) * 100
        perf = "\n📊 Performance : *" + "{:+.1f}".format(variation) + "%*"
    msg = t("profil", lang, broker=broker, capital_initial=capital_initial_str,
            capital=capital_str, perf=perf, risk=risk, risk_eur=risque_euros, status=status)
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=["aide", "help", "aiuto", "ayuda"])
def send_aide(message):
    lang = get_lang(message.from_user.id)
    bot.reply_to(message, t("aide", lang), parse_mode="Markdown")

@bot.message_handler(commands=["langue", "language", "lingua", "idioma"])
def change_lang(message):
    set_field(message.from_user.id, "onboarding_step", 0)
    send_lang_keyboard(message.from_user.id)

@bot.message_handler(commands=["broker"])
def change_broker(message):
    lang = get_lang(message.from_user.id)
    set_field(message.from_user.id, "onboarding_step", 2)
    send_broker_keyboard(message.from_user.id, lang)

@bot.message_handler(commands=["capital", "capitale"])
def change_capital(message):
    lang = get_lang(message.from_user.id)
    set_field(message.from_user.id, "onboarding_step", 3)
    keyboard = telebot.types.ReplyKeyboardRemove()
    bot.send_message(message.from_user.id, t("change_capital", lang), parse_mode="Markdown", reply_markup=keyboard)

@bot.message_handler(commands=["risque", "risk", "rischio", "riesgo"])
def change_risk(message):
    lang = get_lang(message.from_user.id)
    set_field(message.from_user.id, "onboarding_step", 4)
    send_risk_keyboard(message.from_user.id, lang)

@bot.message_handler(commands=["abonnement", "subscription", "abbonamento", "suscripcion"])
def send_subscription(message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    if is_premium(user_id):
        bot.reply_to(message, t("already_premium", lang))
        return
    bot.reply_to(message, get_blocked_message(user_id, lang), parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=["nouveau", "new", "nuovo", "nuevo"])
def new_conversation(message):
    lang = get_lang(message.from_user.id)
    clear_history(message.from_user.id)
    bot.reply_to(message, t("new_conversation", lang))

@bot.message_handler(commands=["premium"])
def activate_premium(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    args = message.text.split()
    if len(args) > 1:
        target_id = int(args[1])
        set_premium(target_id, True, "manual")
        bot.reply_to(message, "✅ Utilisateur " + str(target_id) + " activé en Premium !")
        try:
            lang = get_lang(target_id)
            bot.send_message(target_id, t("premium_activated", lang), parse_mode="Markdown")
        except:
            pass
    else:
        set_premium(user_id, True, "manual")
        bot.reply_to(message, "✅ Votre accès Premium est activé !")

@bot.message_handler(commands=["revoquer"])
def revoke_premium(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Commande réservée à l'administrateur.")
        return
    args = message.text.split()
    if len(args) > 1:
        target_id = int(args[1])
        lang = get_lang(target_id)
        set_premium(target_id, False)
        clear_history(target_id)
        bot.reply_to(message, "✅ Accès Premium révoqué pour " + str(target_id))
        try:
            bot.send_message(target_id, t("subscription_cancelled", lang), parse_mode="Markdown")
        except:
            pass
    else:
        bot.reply_to(message, "Usage: /revoquer ID_TELEGRAM")

@bot.message_handler(commands=["membres"])
def list_members(message):
    if message.from_user.id != ADMIN_ID:
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
        lang = user.get("langue", "fr") if user else "fr"
        perf = ""
        if user and user.get("capital") and capital_initial and capital_initial > 0:
            variation = ((user["capital"] - capital_initial) / capital_initial) * 100
            perf = " (" + "{:+.0f}".format(variation) + "%)"
        flag = {"fr": "🇫🇷", "en": "🇬🇧", "it": "🇮🇹", "es": "🇪🇸"}.get(lang, "🌍")
        msg += "• " + str(m[0]) + " " + flag + " — " + broker + " — " + capital + perf + " — " + risk + "\n"
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
            msg += "📈 Taux de conversion : *" + str(taux) + "%*\n\n"
        lang_count = {}
        for m in premium:
            l = m[2] if m[2] else "fr"
            lang_count[l] = lang_count.get(l, 0) + 1
        if lang_count:
            msg += "🌍 *Premium par langue :*\n"
            for l, count in lang_count.items():
                flag = {"fr": "🇫🇷", "en": "🇬🇧", "it": "🇮🇹", "es": "🇪🇸"}.get(l, "🌍")
                msg += flag + " " + l.upper() + " : " + str(count) + "\n"
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
        bot.reply_to(message, "Usage : /broadcast Votre message\n_Envoi aux membres Premium uniquement._")
        return
    members = get_all_premium()
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
        bot.reply_to(message, "Usage : /upsell Votre message\n_Envoi à TOUS les utilisateurs._")
        return
    users = get_all_users()
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
    bot.reply_to(message, "✅ Envoyé à *" + str(sent_free + sent_premium) + "* utilisateurs\n📊 Gratuits : *" + str(sent_free) + "* | Premium : *" + str(sent_premium) + "*\n❌ Échec : " + str(failed), parse_mode="Markdown")

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
    lang = get_lang(user_id)
    count = get_question_count(user_id)
    if not is_premium(user_id) and count >= MAX_FREE_QUESTIONS:
        bot.reply_to(message, get_blocked_message(user_id, lang), parse_mode="Markdown", disable_web_page_preview=True)
        return
    if not is_premium(user_id):
        increment_question(user_id)
        count += 1
    remaining = MAX_FREE_QUESTIONS - count
    bot.reply_to(message, t("analyzing", lang))
    try:
        file_id = message.photo[-1].file_id
        image_base64 = download_image_as_base64(file_id)
        if not image_base64:
            bot.reply_to(message, t("image_error", lang))
            return
        live_prices = get_live_prices_context()
        prices_context = "REAL-TIME PRICES:\n"
        for symbol, price in live_prices.items():
            prices_context += "- " + symbol + ": $" + "{:,.2f}".format(price) + "\n"
        user = get_user(user_id)
        user_context = ""
        if user and user.get("broker"):
            user_context += "Broker: " + user["broker"] + "\n"
        if user and user.get("capital"):
            user_context += "Capital: " + str(user["capital"]) + "€\n"
        if user and user.get("risk_percent"):
            user_context += "Risk: " + str(user["risk_percent"]) + "%\n"
        caption = message.caption or "Analyze this trading screenshot. Be concise. Key info: asset, direction, levels. Min lot 0.01. View/like numbers are NOT prices or dates."
        full_prompt = prices_context + "\n" + user_context + "\n" + caption
        lang_instruction = {"fr": "Réponds en français.", "en": "Reply in English.", "it": "Rispondi in italiano.", "es": "Responde en español."}.get(lang, "Réponds en français.")
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
            system="You are a concise trading expert. ALWAYS use real-time prices provided. Min 0.01 lot. View/like numbers are NOT prices. " + lang_instruction,
            messages=messages_with_history,
        )
        answer = response.content[0].text
        save_message(user_id, "user", "[Screenshot] " + caption)
        save_message(user_id, "assistant", answer)
        footer = t("footer_premium", lang) if is_premium(user_id) else t("footer_free", lang, count=remaining)
        bot.reply_to(message, answer + footer, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    onboarding_step = user.get("onboarding_step", 0) if user else 0
    lang = user.get("langue", "fr") if user else "fr"

    # ============================================================
    # PRIORITÉ 1 : Signal en attente — traité AVANT tout le reste
    # ============================================================
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
                        result = format_signal_with_lots(signal, lots, capital_input, risk, lang, broker)
                        bot.reply_to(message, result, parse_mode="Markdown")
                    else:
                        bot.reply_to(message, t("signal_error", lang))
                    return
            else:
                delete_pending_signal(user_id)
        except:
            delete_pending_signal(user_id)

    # ============================================================
    # PRIORITÉ 2 : Onboarding en cours (étapes 1-5)
    # ============================================================

    # Étape 0 : choix de la langue (seulement si pas encore configuré)
    if onboarding_step == 0:
        lang_map = {
            "🇫🇷 Français": "fr", "🇬🇧 English": "en",
            "🇮🇹 Italiano": "it", "🇪🇸 Español": "es"
        }
        chosen = lang_map.get(message.text.strip())

        if chosen:
            # L'utilisateur choisit une langue
            set_field(user_id, "langue", chosen)
            set_field(user_id, "onboarding_step", 1)
            lang = chosen
            keyboard = telebot.types.ReplyKeyboardRemove()
            bot.send_message(user_id, t("lang_saved", lang), parse_mode="Markdown", reply_markup=keyboard)
            time.sleep(0.5)
            bot.send_message(user_id, t("welcome", lang), parse_mode="Markdown")
            time.sleep(1)
            send_broker_keyboard(user_id, lang)
            return

        # Profil complet → traitement normal, pas de redemande de langue
        if user and user.get("langue") and user.get("broker") and user.get("capital") and user.get("risk_percent"):
            pass  # Continue vers le traitement normal
        elif not user or not user.get("langue"):
            # Nouveau utilisateur → demande la langue
            send_lang_keyboard(user_id)
            return
        elif not user.get("broker"):
            set_field(user_id, "onboarding_step", 1)
            send_broker_keyboard(user_id, lang)
            return
        elif not user.get("capital"):
            set_field(user_id, "onboarding_step", 3)
            keyboard = telebot.types.ReplyKeyboardRemove()
            bot.send_message(user_id, t("change_capital", lang), parse_mode="Markdown", reply_markup=keyboard)
            return

    # Étape 1 : broker (onboarding initial)
    elif onboarding_step == 1:
        broker = message.text.strip()
        if broker not in BROKERS:
            bot.send_message(user_id, t("invalid_broker", lang))
            send_broker_keyboard(user_id, lang)
            return
        set_field(user_id, "broker", broker)
        set_field(user_id, "onboarding_step", 3)
        keyboard = telebot.types.ReplyKeyboardRemove()
        bot.send_message(user_id, t("broker_saved", lang, broker=broker), parse_mode="Markdown", reply_markup=keyboard)
        return

    # Étape 2 : broker (modification via /broker)
    elif onboarding_step == 2:
        broker = message.text.strip()
        if broker not in BROKERS:
            send_broker_keyboard(user_id, lang)
            return
        set_field(user_id, "broker", broker)
        set_field(user_id, "onboarding_step", 0)
        keyboard = telebot.types.ReplyKeyboardRemove()
        bot.send_message(user_id, "✅ Broker mis à jour : *" + broker + "*", parse_mode="Markdown", reply_markup=keyboard)
        return

    # Étape 3 : capital
    elif onboarding_step == 3:
        try:
            capital = float(message.text.strip().replace("€", "").replace(",", ".").replace(" ", ""))
            if capital <= 0:
                raise ValueError
            set_capital(user_id, capital, is_initial=True)
            set_field(user_id, "onboarding_step", 4)
            time.sleep(0.5)
            send_risk_keyboard(user_id, lang)
        except:
            bot.send_message(user_id, t("invalid_capital", lang))
        return

    # Étape 4 : risque
    elif onboarding_step == 4:
        text = message.text.strip()
        if text == t("custom_risk", lang):
            set_field(user_id, "onboarding_step", 5)
            keyboard = telebot.types.ReplyKeyboardRemove()
            bot.send_message(user_id, t("enter_custom_risk", lang), parse_mode="Markdown", reply_markup=keyboard)
            return
        try:
            risk = float(text.replace("%", "").replace(",", "."))
            if risk <= 0 or risk > 100:
                raise ValueError
            set_field(user_id, "risk_percent", risk)
            set_field(user_id, "onboarding_step", 0)
            user = get_user(user_id)
            broker = user.get("broker", "") if user else ""
            capital = user.get("capital", 0) if user else 0
            risque_euros = round(capital * risk / 100, 2)
            keyboard = telebot.types.ReplyKeyboardRemove()
            bot.send_message(user_id, t("profile_complete", lang, broker=broker, capital=capital, risk=risk, risk_eur=risque_euros), parse_mode="Markdown", reply_markup=keyboard)
        except:
            send_risk_keyboard(user_id, lang)
        return

    # Étape 5 : risque personnalisé
    elif onboarding_step == 5:
        try:
            risk = float(message.text.strip().replace("%", "").replace(",", "."))
            if risk <= 0 or risk > 100:
                raise ValueError
            set_field(user_id, "risk_percent", risk)
            set_field(user_id, "onboarding_step", 0)
            user = get_user(user_id)
            broker = user.get("broker", "") if user else ""
            capital = user.get("capital", 0) if user else 0
            risque_euros = round(capital * risk / 100, 2)
            bot.send_message(user_id, t("profile_complete", lang, broker=broker, capital=capital, risk=risk, risk_eur=risque_euros), parse_mode="Markdown")
        except:
            bot.send_message(user_id, t("invalid_risk", lang))
        return

    # ============================================================
    # PRIORITÉ 3 : Traitement normal — utilisateur avec profil complet
    # ============================================================
    count = get_question_count(user_id)
    if not is_premium(user_id) and count >= MAX_FREE_QUESTIONS:
        bot.reply_to(message, get_blocked_message(user_id, lang), parse_mode="Markdown", disable_web_page_preview=True)
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
            price_info = "📡 *" + t("price_realtime", lang) + " :*\n" + price_data + "\n\n"

    if price_info and is_price_only_request(message.text, lang):
        footer = t("footer_premium", lang) if is_premium(user_id) else t("footer_free", lang, count=remaining)
        bot.reply_to(message, price_info + footer, parse_mode="Markdown")
        return

    try:
        user_context = ""
        if user and user.get("broker"):
            user_context += "Broker: " + user["broker"] + ". "
        if user and user.get("capital"):
            user_context += "Capital: " + str(user["capital"]) + "€. "
        if user and user.get("risk_percent"):
            user_context += "Risk: " + str(user["risk_percent"]) + "%. "

        user_content = message.text
        if price_info:
            user_content = message.text + "\n\n[REAL-TIME DATA: " + price_info + "]"
        if user_context:
            user_content = "[PROFILE: " + user_context + "]\n\n" + user_content

        lang_instruction = {
            "fr": "Réponds en français.",
            "en": "Reply in English.",
            "it": "Rispondi in italiano.",
            "es": "Responde en español."
        }.get(lang, "Réponds en français.")

        history = get_history(user_id)
        messages_with_history = history + [{"role": "user", "content": user_content}]

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system="You are a concise trading expert. Use ONLY provided prices. Min 0.01 lot. Remember conversation context. " + lang_instruction,
            messages=messages_with_history,
        )
        answer = response.content[0].text
        save_message(user_id, "user", user_content)
        save_message(user_id, "assistant", answer)
        footer = t("footer_premium", lang) if is_premium(user_id) else t("footer_free", lang, count=remaining)
        bot.reply_to(message, price_info + answer + footer, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, "Erreur : " + str(e))

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def run_bot():
    while True:
        try:
            print("AutoTrade Bot is running!")
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

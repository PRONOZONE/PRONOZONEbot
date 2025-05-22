import os
import datetime
import time
from flask import Flask
from threading import Thread
from telegram import Bot
from telegram.ext import Updater, CallbackContext

# Récupère les variables Render
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = Bot(token=TOKEN)
updater = Updater(token=TOKEN)
job_queue = updater.job_queue

# Envoie des pronos chaque jour à 9h
def send_pronos(context: CallbackContext):
    date = datetime.datetime.now().strftime("%d/%m/%Y")
    pronos = [
        "1️⃣ Napoli gagne & +2,5 buts (1.57)",
        "2️⃣ Inter gagne & les 2 équipes marquent (2.75)",
        "3️⃣ BTTS Betis vs Valencia (1.80)"
    ]
    message = f"📅 {date}\n\n📊 PRONOSTICS DU JOUR\n\n" + "\n".join(pronos) + "\n\nBonne chance la zone !"
    bot.send_message(chat_id=CHANNEL_ID, text=message)

job_queue.run_daily(send_pronos, time=datetime.time(hour=9, minute=0))

# Fausse appli web pour Render
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running."

# Lancer Flask dans un thread séparé
def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Lancer le faux serveur et le bot
keep_alive()
updater.start_polling()
updater.idle()

import time
while True:
    time.sleep(60)


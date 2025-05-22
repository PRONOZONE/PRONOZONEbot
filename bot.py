import os
from telegram import Bot
from telegram.ext import Updater, CallbackContext
import datetime

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = Bot(token=TOKEN)

def send_pronos(context: CallbackContext):
    date = datetime.datetime.now().strftime("%d/%m/%Y")
    pronos = [
        "1️⃣ Napoli gagne & +2,5 buts (1.57)",
        "2️⃣ Inter gagne & les 2 équipes marquent (2.75)",
        "3️⃣ BTTS Betis vs Valencia (1.80)"
    ]
    message = f"📅 {date}\n\n📊 PRONOSTICS DU JOUR\n\n" + "\n".join(pronos) + "\n\nBonne chance la zone !"
    bot.send_message(chat_id=CHANNEL_ID, text=message)

updater = Updater(token=TOKEN)
job_queue = updater.job_queue
job_queue.run_daily(send_pronos, time=datetime.time(hour=9, minute=0))  # Envoi à 09h chaque jour

updater.start_polling()
updater.idle()

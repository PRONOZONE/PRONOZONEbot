
import os
import datetime
import time
import requests
import csv
from flask import Flask
from threading import Thread
from telegram import Bot
from telegram.ext import Updater, CallbackContext

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSIj6Rl6MpN_R3MLEcMLinq-3G10mJ_WqofqthKuGh8XKYBgQuCmM-bfWU54qhc_BNsSqgx8J-qs6V1/pub?output=csv"

bot = Bot(token=TOKEN)
updater = Updater(token=TOKEN)
job_queue = updater.job_queue

def send_prono_for_hour(context: CallbackContext, target_hour: str):
    try:
        response = requests.get(CSV_URL)
        lines = response.text.splitlines()
        reader = csv.DictReader(lines)

        today = datetime.datetime.now().strftime("%Y-%m-%d")

        for row in reader:
            if row["Heure"] == target_hour and row["Date"] == today:
                message = row["Message"]
                bot.send_message(chat_id=CHANNEL_ID, text=message)
                break
    except Exception as e:
        print(f"Erreur lors de l'envoi du prono ({target_hour}) :", e)

def send_9h(context: CallbackContext):
    send_prono_for_hour(context, "9h")

def send_12h(context: CallbackContext):
    send_prono_for_hour(context, "12h")

def send_20h(context: CallbackContext):
    send_prono_for_hour(context, "20h")

job_queue.run_daily(send_9h, time=datetime.time(hour=9, minute=0))
job_queue.run_daily(send_12h, time=datetime.time(hour=12, minute=0))
job_queue.run_daily(send_20h, time=datetime.time(hour=20, minute=0))

# Fausse appli web pour Render
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running."

def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()
updater.start_polling()
updater.idle()

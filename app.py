from datetime import datetime, timedelta
# import datetime
import time
from os import getenv

from dotenv import load_dotenv
from requests import get
import requests
import schedule
from telegram import Update
from telegram.ext import CallbackContext
from telegram.ext import Updater, CommandHandler, JobQueue

import settings
from db import MegalohobotDB
from structures import Chat, Event
from telegram import Bot

# All confidential info is stored as environment vars
load_dotenv(".env")
bot = Bot(getenv('TOKEN'))
API_TOKEN = getenv("MLB_TELEGRAM_TOKEN")
BOT_NAME = "@" + getenv("MLB_BOT_NAME")
BOT_OWNER_ID = int(getenv("MLB_TELEGRAM_BOT_OWNER"))
URL_TDA = getenv('URL_TDA')
URL_YDA = getenv('URL_YDA')


def get_sun():
    day_length_today = datetime.strptime(
        requests.get(URL_TDA).json()['results']['day_length'], '%H:%M:%S'
    )
    day_length_yda = datetime.strptime(
        requests.get(URL_YDA).json()['results']['day_length'],  '%H:%M:%S'
    )
    day_length = (((day_length_today-day_length_yda).total_seconds())/60)
    if day_length < 0:
        message = (
            f'Сегодня день стал короче на {abs(round(day_length, 2))} минуты'
        )
    if day_length > 0:
        message = (
            f'+{abs(round(day_length, 2))} к световому дню! '
        )
    if day_length == 0:
        message = ('А у нас дни солнцестояния!')
    return bot.send_message(BOT_OWNER_ID, message)


def timer_say():
    schedule.every().day.at('17:49').do(get_sun)
    while True:
        schedule.run_pending()
        time.sleep(1)


def _get_text_from_say_command(update: Update):
    command = update.message.text
    if BOT_NAME.lower() in command.lower():
        command_len = len(BOT_NAME) + 5
    else:
        command_len = 5
    text = update.message.text[command_len:]
    entities = []
    for i in update.message.entities:
        if i.type != "bot_command":
            i.offset -= command_len
            entities.append(i)
    text = text.strip()
    return text, entities


def _is_valid_date(date_text):
    if len(date_text) != 5:
        return False
    try:
        datetime.strptime(date_text, "%d.%m")
    except ValueError:
        return False
    return True


# Bot Handlers
def help_handler(update: Update, _: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    message = """Привет! Меня зовут megalohobot и на данный момент я поддерживаю следующие команды:
  Общее:
    /help, /info - вывод этой справки.
    /start - инициализация чата (для работы с событиями и т.п.).
    /stop - прекратить работу в чате (все данные сохранятся). Возобновить работу можно командой /start.
    /ip - сказать свой айпишник (только владельцу бота в привате).
    /say <текст> - сказать <текст>. Твое сообщение с этой командой удалится (боту нужны права админа в чате).
  Работа с событиями:
    /events - посмотреть все события чата. Я напомню о каждом из них в 6 утра МСК в нужную дату.
    /add_event <date> <title> - добавить событие, формат даты дд.мм (напр., "/add_event 01.01 Новый год!!!").
    /del_event <date> <title> - удалить событие."""
    update.effective_chat.send_message(message)


def start_handler(update: Update, _: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)
    status = db.add_chat(chat)
    if status:
        update.effective_chat.send_message("Готово. Теперь можно пользоваться всеми моими функциями.")
    else:
        update.effective_chat.send_message("Что-то пошло не так, позовите айтишника.")


def stop_handler(update: Update, _: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)
    status = db.disable_chat(chat)
    if status:
        update.effective_chat.send_message("Замолкаю. Чтоб продолжить мою работу здесь, запустите меня заново командой /start.")
    else:
        update.effective_chat.send_message("Что-то пошло не так, позовите айтишника.")


def ip_handler(update: Update, _: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)
    if not db.check_chat_status(chat):
        update.effective_message.reply_text("Меня выключили или забыли запустить в этом чате. Скомандуйте /start, чтобы я смог начать работу.")
        return
    if chat.chat_id == BOT_OWNER_ID:
        host_ip = get('https://api.ipify.org').text
        update.effective_message.reply_text(host_ip)
    else:
        update.effective_message.reply_text("Это конфиденциальная инфа, я могу её озвучить только в привате с хозяином.")


def say_handler(update: Update, _: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)

    if update.effective_chat.type not in ("group", "supergroup", "channel"):
        update.effective_chat.send_message("Я не поддерживаю эту команду в приватных чатах :(")
        return

    if not db.check_chat_status(chat):
        update.effective_message.reply_text("Меня выключили или забыли запустить в этом чате. Скомандуйте /start, чтобы я смог начать работу.")
        return

    text, entities = _get_text_from_say_command(update)
    if not text:
        text = "Мне нечего тебе ответить. Напиши в запросе, что сказать."
        update.effective_chat.send_message(text=text, entities=entities)
        return

    try:
        update.effective_message.delete()
    except Exception:
        text = "Я не могу удалить твое сообщение. Видимо, прав не хватает, дайте права на удаление сообщений."
        update.effective_chat.send_message(text=text, entities=entities)
        return

    update.effective_chat.send_message(text=text, entities=entities)


def events_handler(update: Update, _: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)
    if not db.check_chat_status(chat):
        update.effective_message.reply_text("Меня выключили или забыли запустить в этом чате. Скомандуйте /start, чтобы я смог начать работу.")
        return
    events = db.get_chat_events(chat)
    events.sort(key=lambda x: datetime.strptime(x.date, "%d.%m"))
    if not events:
        msg = "В этом чате пока нет событий."
    else:
        msg = "Список событий чата:\n"
        for i in events:
            msg += f"{i.date} {i.title}\n"
    update.effective_chat.send_message(msg)


def add_event_handler(update: Update, context: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)
    if not db.check_chat_status(chat):
        update.effective_message.reply_text("Меня выключили или забыли запустить в этом чате. Скомандуйте /start, чтобы я смог начать работу.")
        return
    # Check if event string is legit: date format and title presence
    try:
        date = context.args[0]
        if not _is_valid_date(date):
            raise ValueError
        if not context.args[1]:
            raise ValueError
        title = ' '.join(i for i in context.args[1:])
        title_sql_ready = title.replace("'", "''")  # escaping ' symbol in sql query
    except (IndexError, ValueError):
        update.effective_message.reply_text("Что-то я не пойму тебя. События надо добавлять в формате: дд.мм описание события")
        return
    event = Event(chat.chat_id, title, date)
    event_sql_ready = Event(chat.chat_id, title_sql_ready, date)
    existing_events = db.get_chat_events(chat)
    if event in existing_events:
        update.effective_message.reply_text("Такое событие у меня уже записано. Обязательно напомню, не переживай.")
        return
    status = db.add_event(event_sql_ready)
    if status:
        update.effective_chat.send_message(f"Добавил событие: {date} - {title}")
    else:
        update.effective_chat.send_message("Что-то пошло не так, позовите айтишника.")


def del_event_handler(update: Update, context: CallbackContext):
    if not update.effective_chat:  # Bypass non-chat updates (inline queries, polls etc)
        return
    db = MegalohobotDB(settings.DB_PATH)
    chat = Chat(update.effective_chat.id)
    if not db.check_chat_status(chat):
        update.effective_message.reply_text("Меня выключили или забыли запустить в этом чате. Скомандуйте /start, чтобы я смог начать работу.")
        return
    # Check if event string is legit: date format and title presence
    try:
        date = context.args[0]
        if not _is_valid_date(date):
            raise ValueError
        if not context.args[1]:
            raise ValueError
        title = ' '.join(i for i in context.args[1:])
        title_sql_ready = title.replace("'", "''")  # escaping ' symbol in sql query
    except (IndexError, ValueError):
        update.effective_message.reply_text("Что-то я не пойму тебя. События надо добавлять в формате: дд.мм описание события")
        return
    event = Event(chat.chat_id, title, date)
    event_sql_ready = Event(chat.chat_id, title_sql_ready, date)
    existing_events = db.get_chat_events(chat)
    if event in existing_events:
        status = db.delete_event(event_sql_ready)
        if status:
            update.effective_chat.send_message(f"Удалил событие: {date} - {title}.")
        else:
            update.effective_chat.send_message("Что-то пошло не так, позовите айтишника.")
    else:
        update.effective_chat.send_message("Не нашел такого события у себя, удалять нечего.")


def remind_events_worker(context: CallbackContext):
    db = MegalohobotDB(settings.DB_PATH)
    events = db.get_all_events()
    now = datetime.utcnow().replace(second=0, microsecond=0) + timedelta(hours=settings.DEFAULT_REMIND_TZ)
    now_events = []
    for i in events:
        event_time = datetime.strptime(f"{i.date} {i.time}", "%d.%m %H:%M").replace(year=now.year)
        if event_time == now:
            now_events.append(i)
    if now_events:
        chats = set((i.chat_id for i in now_events))
        for chat in chats:
            if not db.check_chat_status(Chat(chat)):
                continue
            greeting = f"Вспомним, что сегодня у нас особенный день. Вот что у меня записано:\n"
            for event in now_events:
                if event.chat_id == chat:
                    greeting += event.title + "\n"
            greeting += "*Поздравим же всех причастных!!!*"
            context.dispatcher.bot.send_message(chat, greeting, parse_mode="Markdown")


def main():
    # Initializing bot
    updater = Updater(API_TOKEN)
    dispatcher = updater.dispatcher

    # Adding command handlers
    dispatcher.add_handler(CommandHandler("help", help_handler))
    dispatcher.add_handler(CommandHandler("info", help_handler))
    dispatcher.add_handler(CommandHandler("start", start_handler))
    dispatcher.add_handler(CommandHandler("stop", stop_handler))
    dispatcher.add_handler(CommandHandler("ip", ip_handler))
    dispatcher.add_handler(CommandHandler("say", say_handler))
    dispatcher.add_handler(CommandHandler("events", events_handler))
    dispatcher.add_handler(CommandHandler("add_event", add_event_handler))
    dispatcher.add_handler(CommandHandler("del_event", del_event_handler))

    # Adding event jobs
    events_job_queue = JobQueue()
    events_job_queue.set_dispatcher(dispatcher)
    events_job_queue.run_repeating(remind_events_worker, 60)
    events_job_queue.start()

    # Starting bot
    updater.start_polling(drop_pending_updates=True)
    updater.running(timer_say())
    updater.idle()


if __name__ == "__main__":
    main()

import os
import time
import logging
from email.mime.application import MIMEApplication
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib

# Чтение переменных окружения и логирование
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
admin_id = os.getenv('ADMIN_ID')
accountant_id = os.getenv('ACCOUNTANT_ID')
gmail_password = os.getenv('GMAIL_PASSWORD')

logging.info(f"API_ID: {api_id}")
logging.info(f"API_HASH: {api_hash}")
logging.info(f"BOT_TOKEN: {bot_token}")
logging.info(f"ADMIN_ID: {admin_id}")
logging.info(f"ACCOUNTANT_ID: {accountant_id}")
logging.info(f"GMAIL_PASSWORD: {'set' if gmail_password else 'not set'}")

# Проверка наличия всех переменных окружения
if not all([api_id, api_hash, bot_token, admin_id, accountant_id, gmail_password]):
    raise ValueError("One or more environment variables are not set.")

# Преобразование переменных к нужному типу
api_id = int(api_id)
admin_id = int(admin_id)
accountant_id = int(accountant_id)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

def create_telegram_client():
    return TelegramClient('bot', api_id, api_hash)

client = create_telegram_client()

# Статусы для отслеживания шагов
users_status = {}
users_data = {}

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    sender = await event.get_sender()
    sender_id = sender.id

    if sender_id != admin_id and sender_id != accountant_id:
        await event.respond("Добро пожаловать! Нажмите кнопку ниже, чтобы загрузить счет на оплату.", buttons=[
            Button.text("Загрузить счет на оплату")
        ])

@client.on(events.NewMessage)
async def handler(event):
    sender = await event.get_sender()
    sender_id = sender.id

    if event.raw_text == "Загрузить счет на оплату":
        users_status[sender_id] = 'start'
        users_data[sender_id] = {}
        await event.respond('Пожалуйста, введите сумму счета:')
        return

    if sender_id not in users_status:
        return

    status = users_status[sender_id]

    if status == 'start':
        users_data[sender_id]['amount'] = event.raw_text
        await event.respond('Пожалуйста, введите дату счета:')
        users_status[sender_id] = 'date'

    elif status == 'date':
        users_data[sender_id]['date'] = event.raw_text
        await event.respond('Пожалуйста, введите комментарии:')
        users_status[sender_id] = 'comments'

    elif status == 'comments':
        users_data[sender_id]['comments'] = event.raw_text
        await event.respond('Пожалуйста, загрузите файл счета:')
        users_status[sender_id] = 'file'

    elif status == 'file':
        if event.message.file:
            file_name = event.message.file.name
            file_path = await event.message.download_media()
            users_data[sender_id]['file_name'] = file_name
            users_data[sender_id]['file_path'] = file_path
            users_data[sender_id]['uploader_id'] = sender_id

            logging.info(f"File {file_name} received from user {sender_id}")

            amount = int(users_data[sender_id]['amount'])
            if amount > 100000:
                await client.send_message(
                    admin_id,
                    f'Сотрудник {sender_id} отправил счет на согласование.\nСумма: {amount}\nДата: {users_data[sender_id]["date"]}\nКомментарии: {users_data[sender_id]["comments"]}',
                    buttons=[
                        [Button.inline("Принять", f'approve_gen:{sender_id}'), Button.inline("Отклонить", f'reject_gen:{sender_id}')]
                    ],
                    file=file_path
                )
                await event.respond('Счет отправлен на согласование гендиректору.')
            else:
                await client.send_message(
                    accountant_id,
                    f'Сотрудник {sender_id} отправил счет на согласование.\nСумма: {amount}\nДата: {users_data[sender_id]["date"]}\nКомментарии: {users_data[sender_id]["comments"]}',
                    buttons=[
                        [Button.inline("Принять", f'approve_acc:{sender_id}'), Button.inline("Отклонить", f'reject_acc:{sender_id}')]
                    ],
                    file=file_path
                )
                await event.respond('Счет отправлен на согласование бухгалтеру.')

            users_status[sender_id] = 'start'
        else:
            await event.respond('Пожалуйста, загрузите файл счета.')
            logging.warning(f"User {sender_id} did not upload a file.")
    else:
        await event.respond('Пожалуйста, следуйте инструкциям и загрузите файл счета.')

@client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8').split(':')
    action = data[0]
    sender_id = int(data[1])

    if action == 'approve_gen' and event.query.user_id == admin_id:
        await event.respond('Счет принят гендиректором и отправлен на согласование бухгалтеру.')
        await client.send_message(
            accountant_id,
            f'Гендиректор одобрил счет от сотрудника {sender_id}.\nСумма: {users_data[sender_id]["amount"]}\nДата: {users_data[sender_id]["date"]}\nКомментарии: {users_data[sender_id]["comments"]}',
            buttons=[
                [Button.inline("Принять", f'approve_acc:{sender_id}'), Button.inline("Отклонить", f'reject_acc:{sender_id}')]
            ],
            file=users_data[sender_id]['file_path']
        )
        await client.send_message(sender_id, 'Ваш счет был одобрен гендиректором и отправлен на согласование бухгалтеру.')
        await event.answer()

    elif action == 'reject_gen' and event.query.user_id == admin_id:
        await event.respond('Счет отклонен гендиректором.')
        await client.send_message(sender_id, 'Ваш счет был отклонен гендиректором.')
        await event.answer()

    elif action == 'approve_acc' and event.query.user_id == accountant_id:
        await event.respond('Счет принят бухгалтером и отправлен в бухгалтерию.')
        file_name = users_data[sender_id]['file_name']
        file_path = users_data[sender_id]['file_path']
        await send_email(file_path, file_name, sender_id)
        await client.send_message(sender_id, 'Ваш счет был одобрен бухгалтером и отправлен в бухгалтерию.')
        await event.answer()

    elif action == 'reject_acc' and event.query.user_id == accountant_id:
        await event.respond('Счет отклонен бухгалтером.')
        await client.send_message(sender_id, 'Ваш счет был отклонен бухгалтером.')
        await event.answer()

async def send_email(file_path, file_name, sender_id):
    from_addr = 'mturysbek.00@gmail.com'
    to_addr = 'zhanaurpak2021@gmail.com'
    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = 'Счет на оплату'

    amount = users_data[sender_id]['amount']
    date = users_data[sender_id]['date']
    comments = users_data[sender_id]['comments']

    body = f'Вложение содержит новый счет на оплату от сотрудника {sender_id}.\n\nСумма: {amount}\nДата: {date}\nКомментарии: {comments}'
    msg.attach(MIMEText(f"<html><body>{body}</body></html>", "html", "utf-8"))

    with open(file_path, 'rb') as attachment:
        part = MIMEApplication(attachment.read(), Name=file_name)
        part['Content-Disposition'] = f'attachment; filename="{file_name}"'
        msg.attach(part)

    message = msg.as_string()

    smtp_host = 'smtp.gmail.com'
    smtp_port = 587
    smtp_user = from_addr
    smtp_password = os.getenv('GMAIL_PASSWORD')

    if not smtp_password:
        logging.error("GMAIL_PASSWORD environment variable is not set")
        return

    await aiosmtplib.send(
        message,
        recipients=[to_addr],
        sender=from_addr,
        hostname=smtp_host,
        port=smtp_port,
        start_tls=True,
        username=smtp_user,
        password=smtp_password
    )

def run_bot():
    while True:
        try:
            client.start(bot_token=bot_token)
            client.run_until_disconnected()
        except FloodWaitError as e:
            wait_time = e.seconds
            logging.warning(f"FloodWaitError: Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)

if __name__ == '__main__':
    run_bot()

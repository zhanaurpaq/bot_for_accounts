import os
import time
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import logging

api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
admin_id = int(os.getenv('ADMIN_ID'))

# Настройка логирования
logging.basicConfig(level=logging.INFO)

def create_telegram_client():
    return TelegramClient('bot', api_id, api_hash)

client = create_telegram_client()

# Статусы для отслеживания шагов
users_status = {}
users_data = {}

@client.on(events.NewMessage)
async def handler(event):
    sender = await event.get_sender()
    sender_id = sender.id

    if sender_id not in users_status:
        users_status[sender_id] = 'start'
        users_data[sender_id] = {}

    status = users_status[sender_id]

    if status == 'start':
        await event.reply('Пожалуйста, введите сумму счета:')
        users_status[sender_id] = 'amount'

    elif status == 'amount':
        users_data[sender_id]['amount'] = event.raw_text
        await event.reply('Пожалуйста, введите дату счета:')
        users_status[sender_id] = 'date'

    elif status == 'date':
        users_data[sender_id]['date'] = event.raw_text
        await event.reply('Пожалуйста, введите комментарии:')
        users_status[sender_id] = 'comments'

    elif status == 'comments':
        users_data[sender_id]['comments'] = event.raw_text
        await event.reply('Пожалуйста, загрузите файл счета:')
        users_status[sender_id] = 'file'

    elif status == 'file':
        if event.message.file:
            file_name = await event.message.download_media()
            users_data[sender_id]['file_name'] = file_name

            await client.send_message(
                admin_id,
                f'Сотрудник {sender_id} отправил счет на согласование.\nСумма: {users_data[sender_id]["amount"]}\nДата: {users_data[sender_id]["date"]}\nКомментарии: {users_data[sender_id]["comments"]}',
                buttons=[
                    [Button.inline("Принять", f'approve:{sender_id}'), Button.inline("Отклонить", f'reject:{sender_id}')]
                ],
                file=file_name
            )

            await event.reply('Счет отправлен на согласование.')
            users_status[sender_id] = 'start'
        else:
            await event.reply('Пожалуйста, загрузите файл счета.')
    else:
        await event.reply('Пожалуйста, следуйте инструкциям и загрузите файл счета.')

@client.on(events.CallbackQuery)
async def callback_handler(event):
    if event.query.user_id == admin_id:
        data = event.data.decode('utf-8').split(':')
        action = data[0]
        sender_id = int(data[1])

        if action == 'approve':
            await event.reply('Счет принят и отправлен в бухгалтерию.')
            file_name = users_data[sender_id]['file_name']
            send_email(file_name, sender_id)
            await client.send_message(sender_id, 'Ваш счет был согласован и отправлен в бухгалтерию.')

        elif action == 'reject':
            await event.reply('Счет отклонен.')
            await client.send_message(sender_id, 'Ваш счет был отклонен.')
        await event.answer()

def send_email(file_path, sender_id):
    from_addr = 'mturysbek.00@gmail.com'
    to_addr = 'zhanaurpak2021@gmail.com'
    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = 'Счет на оплату'

    # Получение данных пользователя
    amount = users_data[sender_id]['amount']
    date = users_data[sender_id]['date']
    comments = users_data[sender_id]['comments']

    # Тело письма
    body = f'Вложение содержит новый счет на оплату от сотрудника {sender_id}.\n\nСумма: {amount}\nДата: {date}\nКомментарии: {comments}'
    msg.attach(MIMEText(body, 'plain'))

    # Присоединение файла
    with open(file_path, 'rb') as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
        msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    
    gmail_password = os.getenv('GMAIL_PASSWORD')
    if not gmail_password:
        logging.error("GMAIL_PASSWORD environment variable is not set")
        return
    
    logging.info(f"GMAIL_PASSWORD is set: {gmail_password is not None}")  # Проверка, что пароль загружен
    server.login(from_addr, gmail_password)
    text = msg.as_string()
    server.sendmail(from_addr, to_addr, text)
    server.quit()

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

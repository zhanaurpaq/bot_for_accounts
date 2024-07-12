import os
import time
import smtplib
import logging
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from telethon import TelegramClient, events, Button
from telethon.errors.rpcerrorlist import FloodWaitError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
admin_id = int(os.getenv('ADMIN_ID'))
encryption_key = os.getenv('ENCRYPTION_KEY').encode()  # Используйте безопасный ключ

# Настройка логирования
logging.basicConfig(level=logging.INFO)

def create_telegram_client():
    return TelegramClient('bot', api_id, api_hash)

client = create_telegram_client()

# Статусы для отслеживания шагов
users_status = {}
users_data = {}

def encrypt_file(file_path, key):
    backend = default_backend()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()

    with open(file_path, 'rb') as f:
        data = f.read()

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(data) + padder.finalize()

    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

    encrypted_file_path = file_path + '.enc'
    with open(encrypted_file_path, 'wb') as f:
        f.write(iv + encrypted_data)  # Сохраняем IV вместе с зашифрованными данными

    return encrypted_file_path

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
        await event.reply('Пожалуйста, загрузите файл счета (только PDF):')
        users_status[sender_id] = 'file'

    elif status == 'file':
        if event.message.file:
            # Получаем имя файла и проверяем его расширение
            file_name = event.message.file.name
            if file_name.endswith('.pdf'):
                file_path = await event.message.download_media()
                users_data[sender_id]['file_name'] = file_name
                users_data[sender_id]['file_path'] = file_path

                logging.info(f"File {file_name} received from user {sender_id}")

                await client.send_message(
                    admin_id,
                    f'Сотрудник {sender_id} отправил счет на согласование.\nСумма: {users_data[sender_id]["amount"]}\nДата: {users_data[sender_id]["date"]}\nКомментарии: {users_data[sender_id]["comments"]}',
                    buttons=[
                        [Button.inline("Принять", f'approve:{sender_id}'), Button.inline("Отклонить", f'reject:{sender_id}')]
                    ],
                    file=file_path
                )

                await event.reply('Счет отправлен на согласование.')
                users_status[sender_id] = 'start'
            else:
                await event.reply('Пожалуйста, загрузите файл в формате PDF.')
                logging.warning(f"User {sender_id} tried to upload a non-PDF file: {file_name}")
        else:
            await event.reply('Пожалуйста, загрузите файл счета.')
            logging.warning(f"User {sender_id} did not upload a file.")
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
            file_path = users_data[sender_id]['file_path']
            encrypted_file_path = encrypt_file(file_path, encryption_key)
            send_email(encrypted_file_path, file_name + '.enc', sender_id)
            await client.send_message(sender_id, 'Ваш счет был согласован и отправлен в бухгалтерию.')

        elif action == 'reject':
            await event.reply('Счет отклонен.')
            await client.send_message(sender_id, 'Ваш счет был отклонен.')
        await event.answer()

def send_email(file_path, file_name, sender_id):
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
        part.add_header('Content-Disposition', f'attachment; filename="{file_name}"')
        msg.attach(part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    
    gmail_password = os.getenv('GMAIL_PASSWORD')
    if not gmail_password:
        logging.error("GMAIL_PASSWORD environment variable is not set")
        return
    
    logging.info(f"GMAIL_PASSWORD is set: {gmail_password}")  # Проверка, что пароль загружен
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

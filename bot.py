import os
from telethon import TelegramClient, events
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

api_id = 24776163
api_hash = 'a8d42769a63635142337f1e7b7202a27'
bot_token = '7228511139:AAFIiS9spuZElvef1h8DACHLuUK0GEYjFMQ'
admin_id = 698359191  # ID гендиректора

client = TelegramClient('bot', api_id, api_hash).start(bot_token=bot_token)

@client.on(events.NewMessage)
async def handler(event):
    if event.message.file:
        sender = await event.get_sender()
        sender_id = sender.id
        if sender_id == int(admin_id):
            await event.message.download_media('approved_invoice.pdf')
            send_email('approved_invoice.pdf')
            await event.reply('Счет отправлен в бухгалтерию.')
        else:
            await client.send_message(admin_id, f'Сотрудник {sender_id} отправил счет на согласование.', file=event.message)

def send_email(file_path):
    from_addr = 'madi.turysbek.00@mail.ru'
    to_addr = 'mturysbek.00@gmail.com'
    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = 'Счет на оплату'

    body = 'Вложение содержит новый счет на оплату.'
    msg.attach(MIMEText(body, 'plain'))

    attachment = open(file_path, 'rb')
    part = MIMEBase('application', 'octet-stream')
    part.set_payload((attachment).read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(file_path)}')

    msg.attach(part)
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(from_addr, os.getenv('EMAIL_PASSWORD'))
    text = msg.as_string()
    server.sendmail(from_addr, to_addr, text)
    server.quit()

client.start()
client.run_until_disconnected()


from .config import TG_TOKEN, TG_USER_ID


async def send_tg_bot_request(session, message):
    token = TG_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': TG_USER_ID,
        'text': message,
        'parse_mode': 'MarkdownV2'
    }
    await session.post(url, data=payload)
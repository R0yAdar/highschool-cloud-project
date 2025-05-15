""" This file is for utilities at tools for the main server."""
import random
from PIL import Image, UnidentifiedImageError
import verification_db as verf_db
import asyncio
from email.message import EmailMessage
from datetime import timedelta
import aiosmtplib
import io
from file_encryption import EncryptedFile
import unicodedata
import re

def slugify(value, allow_unicode=False):
    """
    https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if len(value) == 0:
        value = '_'
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value)
    return re.sub(r'[-\s]+', '-', value).strip('-_')


async def send_auth_mail(to: str):
    """ Send confirmation code to: registeration email (string)"""
    message = EmailMessage()
    message["From"] = "appnoreplyauth@gmail.com"
    message["To"] = to
    message["Subject"] = "Verification Code For Cloud App"
    code = str(random.randrange(10**5, 10**6)) # Only To Validate Email Ownership... Can be changed to a real random function.
    code = await verf_db.create_signup_session(to, code, timedelta(minutes=15))
    message.set_content(f"Hi! Thanks for signing up to my cloud, your code is: {code}")
    await aiosmtplib.send(
    message,
    hostname="smtp.gmail.com",
    port=587,
    username="appnoreplyauth@gmail.com",
    password="jcasgdhxhrsyvljw",
    start_tls=True)

async def check_auth_code(email: str, code: str) -> bool:
    """ Check that the code that the user entered is the 
        one that was sent to him."""
    session = await verf_db.get_signup_session_by_email(email)
    if session:
        return session.verification_code == code # type: ignore
    return False

async def get_code(email: str) -> str:
    """ Utility, isn't needed because there's the above function."""
    return await verf_db.get_signup_session_by_email(email)

async def get_ico(path: str) -> bytes:
    """ Make an icon ( .ico) from an image in *path* using PIL."""
    try:
        async with EncryptedFile(path).get_read() as file:
            file.close()
            img = Image.open(file.name)

            def get_icon(img: Image):
                size = img.size
                container = Image.new(mode="RGBA", size=(max(size), max(size)), color=(0, 0, 0, 0))
                container.paste(img, (int((max(size)-size[0])/2), int((max(size)-size[1])/2)))
                
                with io.BytesIO() as output:
                    container.save(output, format='ico', sizes=[(40, 40), (64, 64)], quality=90)
                    return output.getvalue()
                
            return await asyncio.to_thread(get_icon, img)
    except UnidentifiedImageError:
            return None

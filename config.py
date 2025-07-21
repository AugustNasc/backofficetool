import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'AS212AHUSUH111!@!@UHSAUH@@@SAU2121a21UHS33AUHSAUHSAUH##AUHS')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR}/instance/backoffice.db')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    UPLOAD_LOGO_FOLDER = os.path.join(BASE_DIR, 'logos')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
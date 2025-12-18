import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
DB_PATH = os.getenv("DB_PATH", "data/posts.db")
# HANNEL_ID = "@testformybotirinaa"
# DB_PATH = "data/posts.db"

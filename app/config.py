import os

ENGINE_URL = os.getenv("ENGINE_URL", "https://cscratch-171510694317.us-central1.run.app")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "local-dev-secret")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "badtoken")
PORT = int(os.getenv("PORT", 8080))
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "171510694317")

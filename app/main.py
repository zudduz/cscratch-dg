from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import logging
import os

from . import gateway
from . import config

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    logger.info("Starting Gateway Bot...")
    if not config.DISCORD_TOKEN:
        logger.error("FATAL: DISCORD_TOKEN is missing!")
        
    # Start the bot in the background
    asyncio.create_task(gateway.client.start(config.DISCORD_TOKEN))
    
    yield
    
    # SHUTDOWN
    logger.info("Stopping Gateway Bot...")
    await gateway.client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/ping")
async def ping():
    return {"status": "ok", "bot_connected": gateway.client.is_ready()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
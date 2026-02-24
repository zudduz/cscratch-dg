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
        
    async def run_bot():
        try:
            await gateway.client.start(config.DISCORD_TOKEN)
        except Exception as e:
            logger.critical(f"Discord gateway connection failed: {e}")
        finally:
            # If the bot task exits for any reason, kill the container.
            # Cloud Run will automatically restart it.
            logger.critical("Bot task ended unexpectedly. Forcing container exit.")
            os._exit(1)
            
    # Start the bot in the background with crash handling
    asyncio.create_task(run_bot())
    
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
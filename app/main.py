import asyncio
import logging
from contextlib import asynccontextmanager
import nest_asyncio
from fastapi import FastAPI, Response, status

from . import gateway
from . import config

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    asyncio.create_task(gateway.client.start(config.DISCORD_TOKEN))
    
    yield
    
    # --- SHUTDOWN ---
    logging.info("Gateway: Shutting down...")
    await gateway.client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/ping")
async def ping(response: Response):
    """
    Health check for Cloud Run.
    Also reports if the Discord Socket is actually connected.
    """
    is_connected = gateway.client.is_ready() and not gateway.client.is_closed()
    
    if is_connected:
        return {
            "status": "ok", 
            "service": "cscratch-dg",
            "discord": "connected"
        }
    
    # If Discord isn't ready, we return 200 (so Cloud Run doesn't kill the container)
    # but we log the status as initializing or disconnected.
    # Note: Returning 500 here might cause Cloud Run to restart the container repeatedly
    # during a slow startup, so we stick to 200 with status detail.
    return {
        "status": "initializing", 
        "service": "cscratch-dg",
        "discord": "disconnected"
    }

@app.get("/")
async def root():
    return {"msg": "cscratch Gateway Proxy Online"}
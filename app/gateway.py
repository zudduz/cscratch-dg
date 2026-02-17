import discord
import logging
import aiohttp
import asyncio
import json
from discord import app_commands
from discord.ext import commands
from . import config

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

class GatewayBot(commands.Bot):
    def __init__(self):
        # Gateway needs intent to see messages to forward them
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # Needed to get user names/avatars reliably
        super().__init__(command_prefix="!", intents=intents)
        
        self.http_session = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        
        # Add Commands
        self.tree.add_command(cscratch_group)
        self.tree.add_command(version_cmd)
        
        logger.info("Gateway: Syncing commands...")
        await self.tree.sync()

    async def on_ready(self):
        logger.info(f"Gateway Online: {self.user} (ID: {self.user.id})")
        logger.info(f"Forwarding targets to: {config.ENGINE_URL}")

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def forward_event(self, event_type: str, payload: dict):
        """
        Fire-and-forget POST to the Engine.
        """
        if not self.http_session:
            return

        headers = {
            "Content-Type": "application/json",
            "X-Internal-Auth": config.INTERNAL_API_KEY
        }

        # Wrap in a task to ensure we don't block the Gateway event loop waiting for the Engine
        asyncio.create_task(self._post_to_engine(event_type, payload, headers))

    async def _post_to_engine(self, event_type: str, payload: dict, headers: dict):
        url = f"{config.ENGINE_URL}/ingress/{event_type}"
        try:
            async with self.http_session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.error(f"Engine Error {resp.status}: {await resp.text()}")
        except Exception as e:
            logger.error(f"Failed to forward to Engine: {e}")

client = GatewayBot()

# --- FORWARDING LOGIC ---

@client.event
async def on_message(message):
    if message.author.bot:
        return

    # 1. VISUAL FEEDBACK: Typing Indicator
    await message.channel.typing()

    # 2. CONSTRUCT PAYLOAD
    payload = {
        "guild_id": str(message.guild.id) if message.guild else None,
        "channel_id": str(message.channel.id),
        "user_id": str(message.author.id),
        "user_name": message.author.name,
        "content": message.content,
        "message_id": str(message.id)
    }

    # 3. FORWARD
    await client.forward_event("message", payload)

@client.event
async def on_interaction(interaction: discord.Interaction):
    # Handle Buttons/Dropdowns (Persistent Views)
    if interaction.type == discord.InteractionType.component:
        # 1. DEFER IMMEDIATELY (Prevents "Interaction Failed")
        await interaction.response.defer()
        
        payload = {
            "type": "component",
            "custom_id": interaction.data.get("custom_id"),
            "guild_id": str(interaction.guild.id) if interaction.guild else None,
            "channel_id": str(interaction.channel_id),
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "values": interaction.data.get("values", []) # For dropdowns
        }
        
        await client.forward_event("interaction", payload)

# --- COMMAND PROXIES ---

cscratch_group = app_commands.Group(name="cscratch", description="Manage cscratch games")

@cscratch_group.command(name="start", description="Start a new game")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    # 1. DEFER HIDDEN (ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    
    # 2. FORWARD
    payload = {
        "command": "start",
        "cartridge": cartridge,
        "guild_id": str(interaction.guild.id),
        "channel_id": str(interaction.channel_id),
        "user_id": str(interaction.user.id),
        "user_name": interaction.user.name
    }
    await client.forward_event("command", payload)

    # 3. SILENT CLEANUP
    await interaction.delete_original_response()

@cscratch_group.command(name="end", description="Clean up the current game")
async def end(interaction: discord.Interaction):
    # 1. DEFER HIDDEN
    await interaction.response.defer(ephemeral=True)

    # 2. FORWARD
    payload = {
        "command": "end",
        "guild_id": str(interaction.guild.id),
        "channel_id": str(interaction.channel_id),
        "user_id": str(interaction.user.id),
        "user_name": interaction.user.name
    }
    await client.forward_event("command", payload)

    # 3. SILENT CLEANUP
    await interaction.delete_original_response()

@app_commands.command(name="version", description="Check Gateway Version")
async def version_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Gateway: v1.0.0 (Proxy Mode)", ephemeral=True)
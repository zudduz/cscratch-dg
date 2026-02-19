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
        
        # Add Command Groups/Trees
        self.tree.add_command(cscratch_group)
        self.tree.add_command(admin_group)
        
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

# --- HELPER: PROXY ---

async def proxy_command(interaction: discord.Interaction, command_name: str, ephemeral: bool = False, **kwargs):
    """
    Generic forwarder for Slash Commands.
    """
    # 1. Defer (Ephemeral or Public) with Error Handling
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except discord.NotFound:
        logger.warning(f"Cmd {command_name}: Interaction timed out before defer (Gateway Lag)")
        return
    except Exception as e:
        logger.error(f"Cmd {command_name}: Defer failed: {e}")
        return

    # 2. Build Payload
    payload = {
        "command": command_name,
        "context": {
            "guild_id": str(interaction.guild.id) if interaction.guild else None,
            "channel_id": str(interaction.channel_id),
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "interaction_token": interaction.token,
            "application_id": str(interaction.application_id)
        },
        "params": {}
    }

    # 3. Serialize Params
    for k, v in kwargs.items():
        if isinstance(v, (discord.User, discord.Member)):
            payload["params"][k] = str(v.id)
        else:
            payload["params"][k] = v

    # 4. Forward
    await client.forward_event("command", payload)

    # 5. Cleanup UI
    # We clean up public responses so the "Thinking..." state goes away.
    # Ephemeral states cannot be deleted easily, relying on Engine to followup.
    if not ephemeral:
        try:
            await interaction.delete_original_response()
        except:
            pass

# --- FORWARDING LOGIC (EVENTS) ---

@client.event
async def on_message(message):
    if message.author.bot:
        return

    # Don't trigger typing/forwarding for empty messages (system msgs)
    if not message.content:
        return

    # Legacy flat payload for messages
    payload = {
        "guild_id": str(message.guild.id) if message.guild else None,
        "channel_id": str(message.channel.id),
        "user_id": str(message.author.id),
        "user_name": message.author.name,
        "content": message.content,
        "message_id": str(message.id)
    }

    await client.forward_event("message", payload)

@client.event
async def on_interaction(interaction: discord.Interaction):
    # Handle Buttons/Dropdowns (Persistent Views)
    if interaction.type == discord.InteractionType.component:
        
        custom_id = interaction.data.get("custom_id")
        is_ephemeral = (custom_id == "start_btn")
        
        # 1. Defer
        try:
            await interaction.response.defer(ephemeral=is_ephemeral)
        except discord.NotFound:
            logger.warning(f"Interaction {custom_id}: Timed out before defer")
            return
        except Exception as e:
            logger.error(f"Interaction {custom_id}: Error {e}")
            return
        
        # 2. Forward
        payload = {
            "type": "component",
            "custom_id": custom_id,
            "guild_id": str(interaction.guild.id) if interaction.guild else None,
            "channel_id": str(interaction.channel_id),
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "values": interaction.data.get("values", []),
            "interaction_token": interaction.token,
            "application_id": str(interaction.application_id)
        }
        
        await client.forward_event("interaction", payload)

        # 3. Cleanup Public Interactions (like Join Button)
        # If we don't delete this, the button will spin "Thinking..." forever
        # because the Engine sends a *new* message instead of replying to this interaction.
        if not is_ephemeral:
            try:
                await interaction.delete_original_response()
            except:
                pass

# --- COMMAND DEFINITIONS ---

# 1. cscratch group (Existing)
cscratch_group = app_commands.Group(name="cscratch", description="Manage cscratch games")

@cscratch_group.command(name="start", description="Start a new game")
async def start(interaction: discord.Interaction, cartridge: str = "foster-protocol"):
    await proxy_command(interaction, "start", cartridge=cartridge)

@cscratch_group.command(name="end", description="Clean up the current game")
async def end(interaction: discord.Interaction):
    await proxy_command(interaction, "end")

@cscratch_group.command(name="balance", description="Check your scratch balance (Private)")
async def balance_cmd(interaction: discord.Interaction):
    await proxy_command(interaction, "balance", ephemeral=True)

# 2. Admin Group (New)
admin_group = app_commands.Group(name="admin", description="Admin tools")

@admin_group.command(name="gift", description="Gift tokens to a user")
@app_commands.describe(amount="Amount to gift", recipient="Who gets it?")
async def gift(interaction: discord.Interaction, amount: int, recipient: discord.User):
    await proxy_command(interaction, "admin.gift", amount=amount, recipient=recipient)

@admin_group.command(name="balance", description="Check a user's balance")
@app_commands.describe(user="The user to check")
async def check_balance(interaction: discord.Interaction, user: discord.User):
    await proxy_command(interaction, "admin.balance", user=user)

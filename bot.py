import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import string
from datetime import datetime, timedelta
import json

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = 1477695445408022639  # Only YOU

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

KEYS_FILE = "keys.json"

def load_keys():
    try:
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_keys(keys):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, default=str)

def generate_key():
    return "LP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def get_expiry(duration):
    now = datetime.now()
    if duration == "1d": return (now + timedelta(days=1)).isoformat()
    if duration == "1w": return (now + timedelta(weeks=1)).isoformat()
    if duration == "1m": return (now + timedelta(days=30)).isoformat()
    if duration == "1y": return (now + timedelta(days=365)).isoformat()
    if duration == "lifetime": return (now + timedelta(days=3650)).isoformat()
    return (now + timedelta(days=7)).isoformat()

@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")
    print(f"✅ Owner ID: {OWNER_ID}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LightPanel Pro"))
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync error: {e}")

# ========== EVERYONE CAN USE (ONLY REDEEM) ==========

@bot.tree.command(name="redeem", description="Redeem your license key")
@app_commands.describe(key="Your license key (LP-XXXX-XXXX)")
async def redeem(interaction: discord.Interaction, key: str):
    keys = load_keys()
    key = key.upper()
    
    if key not in keys:
        await interaction.response.send_message("❌ Invalid license key!", ephemeral=True)
        return
    
    data = keys[key]
    if data.get("used_by"):
        await interaction.response.send_message("❌ License already in use!", ephemeral=True)
        return
    
    expiry_date = datetime.fromisoformat(data["expiry"])
    if expiry_date < datetime.now():
        await interaction.response.send_message("❌ License has expired!", ephemeral=True)
        return
    
    data["used_by"] = str(interaction.user.id)
    data["used_by_discord"] = str(interaction.user)
    save_keys(keys)
    
    await interaction.response.send_message(f"✅ License redeemed!\n📅 Expires: {expiry_date.strftime('%Y-%m-%d')}")

# ========== OWNER ONLY COMMANDS ==========

@bot.tree.command(name="gen", description="Generate license key")
@app_commands.describe(duration="1d, 1w, 1m, 1y, lifetime", amount="Number of keys")
async def gen(interaction: discord.Interaction, duration: str = "7d", amount: int = 1):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    valid = ["1d", "1w", "1m", "1y", "lifetime", "7d"]
    if duration not in valid:
        await interaction.response.send_message(f"❌ Invalid duration", ephemeral=True)
        return
    if amount > 10:
        await interaction.response.send_message("❌ Max 10 keys", ephemeral=True)
        return
    
    keys = load_keys()
    generated = []
    
    for _ in range(amount):
        key = generate_key()
        keys[key] = {
            "key": key,
            "duration": duration,
            "expiry": get_expiry(duration),
            "used_by": None,
            "created_by": str(interaction.user.id),
            "created_at": datetime.now().isoformat()
        }
        generated.append(key)
    
    save_keys(keys)
    await interaction.response.send_message(f"✅ Generated {amount} key(s):\n```\n" + "\n".join(generated) + "\n```")

@bot.tree.command(name="grant", description="Extend user's license")
@app_commands.describe(user="User to grant", duration="1d, 1w, 1m, 1y, lifetime", reason="Reason")
async def grant(interaction: discord.Interaction, user: discord.User, duration: str, reason: str = "No reason"):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    keys = load_keys()
    
    user_key = None
    for key, data in keys.items():
        if data.get("used_by") == str(user.id):
            user_key = key
            break
    
    if not user_key:
        await interaction.response.send_message(f"❌ {user.mention} has no license", ephemeral=True)
        return
    
    now = datetime.now()
    old_expiry = datetime.fromisoformat(keys[user_key]["expiry"])
    
    if duration == "1d": new_expiry = now + timedelta(days=1)
    elif duration == "1w": new_expiry = now + timedelta(weeks=1)
    elif duration == "1m": new_expiry = now + timedelta(days=30)
    elif duration == "1y": new_expiry = now + timedelta(days=365)
    else: new_expiry = now + timedelta(days=3650)
    
    if old_expiry > now:
        new_expiry = old_expiry + (new_expiry - now)
    
    keys[user_key]["expiry"] = new_expiry.isoformat()
    save_keys(keys)
    
    await interaction.response.send_message(f"✅ Granted {duration} to {user.mention}\n📅 New expiry: {new_expiry.strftime('%Y-%m-%d')}\n📝 Reason: {reason}")
    
    try:
        embed = discord.Embed(title="✅ License Extended", color=discord.Color.green())
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="New Expiry", value=new_expiry.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.tree.command(name="terminate", description="Revoke user's license")
@app_commands.describe(user="User to terminate", reason="Reason")
async def terminate(interaction: discord.Interaction, user: discord.User, reason: str = "No reason"):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    keys = load_keys()
    
    user_key = None
    for key, data in keys.items():
        if data.get("used_by") == str(user.id):
            user_key = key
            break
    
    if not user_key:
        await interaction.response.send_message(f"❌ {user.mention} has no license", ephemeral=True)
        return
    
    keys[user_key]["expiry"] = (datetime.now() - timedelta(days=1)).isoformat()
    save_keys(keys)
    
    await interaction.response.send_message(f"✅ Terminated {user.mention}'s license\n📝 Reason: {reason}")
    
    try:
        embed = discord.Embed(title="❌ License Terminated", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.tree.command(name="stats", description="License stats")
async def stats(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    keys = load_keys()
    total = len(keys)
    used = sum(1 for data in keys.values() if data.get("used_by"))
    await interaction.response.send_message(f"📊 Total: {total} | Used: {used}")

@bot.tree.command(name="users", description="List users")
async def users(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    keys = load_keys()
    user_list = []
    for key, data in keys.items():
        if data.get("used_by_discord"):
            expiry_str = datetime.fromisoformat(data["expiry"]).strftime('%Y-%m-%d')
            user_list.append(f"• {data['used_by_discord']} - Expires: {expiry_str}")
    
    if not user_list:
        await interaction.response.send_message("No users")
        return
    
    await interaction.response.send_message("\n".join(user_list[:20]))

@bot.tree.command(name="ping", description="Check bot")
async def ping(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="dashboard", description="Dashboard link")
async def dashboard(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
        return
    
    await interaction.response.send_message(f"📊 https://botskigaun-production.up.railway.app/")

bot.run(TOKEN)
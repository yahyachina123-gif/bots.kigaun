import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import string
from datetime import datetime, timedelta

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory storage (no MongoDB needed for now)
temp_keys = {}

def generate_key():
    return "LP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def get_expiry(duration):
    now = datetime.now()
    if duration == "1d": return now + timedelta(days=1)
    if duration == "1w": return now + timedelta(weeks=1)
    if duration == "1m": return now + timedelta(days=30)
    if duration == "1y": return now + timedelta(days=365)
    if duration == "lifetime": return now + timedelta(days=3650)
    return now + timedelta(days=7)

@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LightPanel Pro"))
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync error: {e}")

# ========== BASIC COMMANDS ==========

@bot.tree.command(name="ping", description="Check if bot is working")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="gen", description="Generate a license key")
@app_commands.describe(duration="1d, 1w, 1m, 1y, lifetime")
async def slash_gen(interaction: discord.Interaction, duration: str = "7d"):
    key = generate_key()
    expiry = get_expiry(duration)
    
    # Store in memory
    temp_keys[key] = {
        "key": key,
        "duration": duration,
        "expiry": expiry,
        "used_by": None,
        "revoked": False
    }
    
    await interaction.response.send_message(f"✅ Generated key:\n```\n{key}\n```\n📅 Expires: {expiry.strftime('%Y-%m-%d')}")

@bot.tree.command(name="redeem", description="Redeem your license key")
@app_commands.describe(key="Your license key (LP-XXXX-XXXX)")
async def slash_redeem(interaction: discord.Interaction, key: str):
    key = key.upper()
    
    if key not in temp_keys:
        await interaction.response.send_message("❌ Invalid license key!")
        return
    
    key_data = temp_keys[key]
    
    if key_data.get("revoked"):
        await interaction.response.send_message("❌ License has been revoked!")
        return
    if key_data.get("used_by"):
        await interaction.response.send_message("❌ License already in use!")
        return
    if key_data["expiry"] < datetime.now():
        await interaction.response.send_message("❌ License has expired!")
        return
    
    # Mark as used
    key_data["used_by"] = str(interaction.user.id)
    key_data["used_by_discord"] = str(interaction.user)
    
    await interaction.response.send_message(f"✅ License redeemed!\n📅 Expires: {key_data['expiry'].strftime('%Y-%m-%d')}")

@bot.tree.command(name="grant", description="Extend a user's license")
@app_commands.describe(user="User to grant", duration="1d, 1w, 1m, 1y, lifetime", reason="Reason for grant")
async def slash_grant(interaction: discord.Interaction, user: discord.User, duration: str, reason: str = "No reason provided"):
    # Find user's key
    user_key = None
    for key, data in temp_keys.items():
        if data.get("used_by") == str(user.id):
            user_key = key
            break
    
    if not user_key:
        await interaction.response.send_message(f"❌ {user.mention} doesn't have a license!")
        return
    
    new_expiry = get_expiry(duration)
    old_expiry = temp_keys[user_key]["expiry"]
    if old_expiry and old_expiry > datetime.now():
        new_expiry = old_expiry + (new_expiry - datetime.now())
    
    temp_keys[user_key]["expiry"] = new_expiry
    
    await interaction.response.send_message(f"✅ Granted {duration} to {user.mention}\n📅 New expiry: {new_expiry.strftime('%Y-%m-%d')}\n📝 Reason: {reason}")
    
    # DM the user
    try:
        embed = discord.Embed(title="✅ License Extended - LightPanel Pro", color=discord.Color.green())
        embed.add_field(name="Duration Added", value=duration, inline=True)
        embed.add_field(name="New Expiry", value=new_expiry.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.tree.command(name="terminate", description="Revoke a user's license")
@app_commands.describe(user="User to terminate", reason="Reason for termination")
async def slash_terminate(interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):
    # Find user's key
    user_key = None
    for key, data in temp_keys.items():
        if data.get("used_by") == str(user.id):
            user_key = key
            break
    
    if not user_key:
        await interaction.response.send_message(f"❌ {user.mention} doesn't have a license!")
        return
    
    temp_keys[user_key]["revoked"] = True
    
    await interaction.response.send_message(f"✅ Terminated {user.mention}'s license\n📝 Reason: {reason}")
    
    # DM the user
    try:
        embed = discord.Embed(title="❌ License Terminated - LightPanel Pro", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.tree.command(name="stats", description="Show license statistics")
async def slash_stats(interaction: discord.Interaction):
    total = len(temp_keys)
    used = sum(1 for data in temp_keys.values() if data.get("used_by"))
    active = sum(1 for data in temp_keys.values() if data.get("expiry") and data["expiry"] > datetime.now() and not data.get("revoked"))
    
    await interaction.response.send_message(f"📊 **Statistics:**\nTotal Licenses: {total}\nUsed: {used}\nActive: {active}")

@bot.tree.command(name="dashboard", description="Get dashboard link")
async def slash_dashboard(interaction: discord.Interaction):
    await interaction.response.send_message(f"📊 **Dashboard:**\nhttps://botskigaun-production.up.railway.app/")

@bot.tree.command(name="users", description="List all users with licenses")
async def slash_users(interaction: discord.Interaction):
    user_list = []
    for key, data in temp_keys.items():
        if data.get("used_by_discord"):
            expiry_str = data["expiry"].strftime('%Y-%m-%d') if data.get("expiry") else 'Never'
            user_list.append(f"• {data['used_by_discord']} - {data['key']} - Expires: {expiry_str}")
    
    if not user_list:
        await interaction.response.send_message("No users found.")
        return
    
    await interaction.response.send_message(f"**Users:**\n" + "\n".join(user_list[:20]))

bot.run(TOKEN)
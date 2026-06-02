import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import string
from datetime import datetime, timedelta
import motor.motor_asyncio

TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
OWNER_ID = 1477695445408022639  # YOUR Discord ID

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.lightpanel
licenses = db.licenses
users = db.users

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
    print(f"✅ Owner ID: {OWNER_ID}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LightPanel Pro"))
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync error: {e}")

# ========== SLASH COMMANDS ==========

@bot.tree.command(name="gen", description="Generate a license key")
@app_commands.describe(duration="1d, 1w, 1m, 1y, lifetime", amount="Number of keys (1-10)")
async def slash_gen(interaction: discord.Interaction, duration: str = "7d", amount: int = 1):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    valid = ["1d", "1w", "1m", "1y", "lifetime", "7d"]
    if duration not in valid:
        await interaction.response.send_message(f"❌ Invalid duration. Use: {', '.join(valid)}", ephemeral=True)
        return
    if amount > 10:
        await interaction.response.send_message("❌ Max 10 keys", ephemeral=True)
        return
    
    keys = []
    for _ in range(amount):
        key = generate_key()
        await licenses.insert_one({
            "key": key, "duration": duration, "expiry": get_expiry(duration),
            "used_by": None, "used_by_discord": None, "used_at": None, "hwid": None,
            "created_by": str(interaction.user.id), "created_at": datetime.now(), "revoked": False
        })
        keys.append(key)
    
    await interaction.response.send_message(f"✅ Generated {amount} key(s):\n```\n" + "\n".join(keys) + "\n```")

@bot.tree.command(name="redeem", description="Redeem your license key")
@app_commands.describe(key="Your license key (LP-XXXX-XXXX)")
async def slash_redeem(interaction: discord.Interaction, key: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    data = await licenses.find_one({"key": key.upper()})
    
    if not data:
        await interaction.response.send_message("❌ Invalid license key!", ephemeral=True)
        return
    if data.get("revoked"):
        await interaction.response.send_message("❌ License revoked!", ephemeral=True)
        return
    if data.get("used_by"):
        await interaction.response.send_message("❌ License already in use!", ephemeral=True)
        return
    if data["expiry"] < datetime.now():
        await interaction.response.send_message("❌ License expired!", ephemeral=True)
        return
    
    await licenses.update_one(
        {"key": key.upper()},
        {"$set": {"used_by": str(interaction.user.id), "used_by_discord": str(interaction.user), "used_at": datetime.now()}}
    )
    
    await users.update_one(
        {"discord_id": str(interaction.user.id)},
        {"$set": {"name": str(interaction.user), "license_key": key.upper(), "expiry": data["expiry"]}},
        upsert=True
    )
    
    await interaction.response.send_message(f"✅ License redeemed!\n📅 Expires: {data['expiry'].strftime('%Y-%m-%d')}")

@bot.tree.command(name="grant", description="Extend a user's license")
@app_commands.describe(user="User to grant", duration="1d, 1w, 1m, 1y, lifetime", reason="Reason for grant")
async def slash_grant(interaction: discord.Interaction, user: discord.User, duration: str, reason: str = "No reason provided"):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    user_data = await users.find_one({"discord_id": str(user.id)})
    if not user_data:
        await interaction.response.send_message(f"❌ {user.mention} doesn't have a license!", ephemeral=True)
        return
    
    new_expiry = get_expiry(duration)
    old_expiry = user_data.get("expiry")
    if old_expiry and old_expiry > datetime.now():
        new_expiry = old_expiry + (new_expiry - datetime.now())
    
    await users.update_one({"discord_id": str(user.id)}, {"$set": {"expiry": new_expiry}})
    await licenses.update_one({"key": user_data["license_key"]}, {"$set": {"expiry": new_expiry}})
    
    await interaction.response.send_message(f"✅ Granted {duration} to {user.mention}\n📅 New expiry: {new_expiry.strftime('%Y-%m-%d')}\n📝 Reason: {reason}")
    
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
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    user_data = await users.find_one({"discord_id": str(user.id)})
    if not user_data:
        await interaction.response.send_message(f"❌ {user.mention} doesn't have a license!", ephemeral=True)
        return
    
    await users.update_one({"discord_id": str(user.id)}, {"$set": {"expiry": datetime.now(), "revoked": True}})
    await licenses.update_one({"key": user_data["license_key"]}, {"$set": {"revoked": True}})
    
    await interaction.response.send_message(f"✅ Terminated {user.mention}'s license\n📝 Reason: {reason}")
    
    try:
        embed = discord.Embed(title="❌ License Terminated - LightPanel Pro", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.tree.command(name="stats", description="Show license statistics")
async def slash_stats(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    total = await licenses.count_documents({})
    used = await licenses.count_documents({"used_by": {"$ne": None}})
    active = await users.count_documents({"expiry": {"$gt": datetime.now()}})
    await interaction.response.send_message(f"📊 **Statistics:**\nTotal Licenses: {total}\nUsed: {used}\nActive Users: {active}")

@bot.tree.command(name="dashboard", description="Get dashboard link")
async def slash_dashboard(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    await interaction.response.send_message(f"📊 **Dashboard:**\nhttps://botskigaun-production.up.railway.app/")

@bot.tree.command(name="ping", description="Check bot latency")
async def slash_ping(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="users", description="List all users with licenses")
async def slash_users(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    cursor = users.find()
    user_list = []
    async for doc in cursor:
        user_list.append(f"• {doc.get('name', 'Unknown')} - Expires: {doc['expiry'].strftime('%Y-%m-%d') if doc.get('expiry') else 'Never'}")
    
    if not user_list:
        await interaction.response.send_message("No users found.")
        return
    
    await interaction.response.send_message(f"**Users:**\n" + "\n".join(user_list[:20]))

bot.run(TOKEN)
import discord
from discord.ext import commands
import asyncio
import os
import random
import string
from datetime import datetime, timedelta
import motor.motor_asyncio

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ===== DATABASE =====
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.lightpanel
licenses = db.licenses
users = db.users

# ===== BOT SETUP =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def generate_key():
    return "LP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def get_expiry(duration):
    if duration == "1d": return datetime.now() + timedelta(days=1)
    if duration == "1w": return datetime.now() + timedelta(weeks=1)
    if duration == "1m": return datetime.now() + timedelta(days=30)
    if duration == "1y": return datetime.now() + timedelta(days=365)
    if duration == "lifetime": return datetime.now() + timedelta(days=3650)
    return datetime.now() + timedelta(days=7)

@bot.event
async def on_ready():
    print(f"✅ Bot online as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LightPanel Pro"))

@bot.command(name="gen")
@commands.has_permissions(administrator=True)
async def gen_key(ctx, duration: str = "7d", amount: int = 1):
    """!gen 1d/1w/1m/1y/lifetime [amount]"""
    valid = ["1d", "1w", "1m", "1y", "lifetime"]
    if duration not in valid:
        await ctx.send(f"❌ Use: {', '.join(valid)}")
        return
    if amount > 10:
        await ctx.send("❌ Max 10 keys")
        return
    
    keys = []
    for _ in range(amount):
        key = generate_key()
        expiry = get_expiry(duration)
        await licenses.insert_one({
            "key": key,
            "duration": duration,
            "expiry": expiry,
            "used_by": None,
            "used_at": None,
            "hwid": None,
            "created_by": str(ctx.author.id),
            "created_at": datetime.now(),
            "revoked": False
        })
        keys.append(key)
    
    msg = f"✅ Generated {amount} key(s):\n```\n" + "\n".join(keys) + "\n```"
    await ctx.send(msg)

@bot.command(name="redeem")
async def redeem_key(ctx, key: str = None):
    """!redeem LP-XXXX-XXXX"""
    if not key:
        await ctx.send("❌ Usage: `!redeem LP-XXXX-XXXX`")
        return
    
    license_data = await licenses.find_one({"key": key.upper()})
    
    if not license_data:
        await ctx.send("❌ Invalid license key!")
        return
    if license_data.get("revoked"):
        await ctx.send("❌ License revoked!")
        return
    if license_data.get("used_by"):
        await ctx.send("❌ License already used!")
        return
    if license_data["expiry"] < datetime.now():
        await ctx.send("❌ License expired!")
        return
    
    await licenses.update_one(
        {"key": key.upper()},
        {"$set": {
            "used_by": str(ctx.author.id),
            "used_at": datetime.now(),
            "discord_name": str(ctx.author)
        }}
    )
    
    await users.update_one(
        {"discord_id": str(ctx.author.id)},
        {"$set": {
            "name": str(ctx.author),
            "license_key": key.upper(),
            "expiry": license_data["expiry"]
        }},
        upsert=True
    )
    
    await ctx.send(f"✅ License redeemed!\n📅 Expires: {license_data['expiry'].strftime('%Y-%m-%d')}")

@bot.command(name="list")
@commands.has_permissions(administrator=True)
async def list_keys(ctx):
    """!list - Show all licenses"""
    cursor = licenses.find().limit(25)
    results = await cursor.to_list(length=25)
    if not results:
        await ctx.send("No licenses found")
        return
    
    msg = "**📋 Licenses:**\n```\n"
    for lic in results:
        used = "USED" if lic.get("used_by") else "FREE"
        revoked = "REVOKED" if lic.get("revoked") else ""
        msg += f"{lic['key']} | {used} | {lic['expiry'].strftime('%Y-%m-%d')} {revoked}\n"
    msg += "```"
    await ctx.send(msg)

@bot.command(name="revoke")
@commands.has_permissions(administrator=True)
async def revoke_key(ctx, key: str):
    """!revoke LP-XXXX-XXXX"""
    result = await licenses.update_one(
        {"key": key.upper()},
        {"$set": {"revoked": True}}
    )
    if result.modified_count:
        await ctx.send(f"✅ Revoked: {key}")
    else:
        await ctx.send(f"❌ Key not found")

@bot.command(name="grant")
@commands.has_permissions(administrator=True)
async def grant_time(ctx, user: discord.User, duration: str):
    """!grant @user 1m/1w/1y"""
    user_data = await users.find_one({"discord_id": str(user.id)})
    if not user_data:
        await ctx.send(f"❌ {user.mention} has no license")
        return
    
    new_expiry = get_expiry(duration)
    await users.update_one(
        {"discord_id": str(user.id)},
        {"$set": {"expiry": new_expiry}}
    )
    await licenses.update_one(
        {"key": user_data["license_key"]},
        {"$set": {"expiry": new_expiry}}
    )
    await ctx.send(f"✅ Granted {duration} to {user.mention}\n📅 New expiry: {new_expiry.strftime('%Y-%m-%d')}")

@bot.command(name="stats")
async def bot_stats(ctx):
    total = await licenses.count_documents({})
    used = await licenses.count_documents({"used_by": {"$ne": None}})
    await ctx.send(f"📊 **Stats:**\nTotal Licenses: {total}\nUsed: {used}")

bot.run(TOKEN)
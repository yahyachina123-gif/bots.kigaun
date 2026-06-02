import discord
from discord.ext import commands
import os
import random
import string
from datetime import datetime, timedelta
import motor.motor_asyncio

TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.lightpanel
licenses = db.licenses
users = db.users

# ========== BOT SETUP ==========
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.message_content = True

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
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LightPanel Pro"))
    
    # Sync commands and send startup message
    channel = bot.get_channel(123456789012345678)  # Replace with your channel ID or remove
    print("Bot is ready! Commands: !gen, !redeem, !grant, !terminate, !ping, !commands")

# ========== LICENSE COMMANDS ==========

@bot.command(name="gen")
@commands.has_permissions(administrator=True)
async def gen_key(ctx, duration: str = "7d", amount: int = 1):
    """Generate a license key - !gen 1d/1w/1m/1y/lifetime [amount]"""
    valid = ["1d", "1w", "1m", "1y", "lifetime", "7d"]
    if duration not in valid:
        await ctx.send(f"❌ Invalid duration. Use: {', '.join(valid)}")
        return
    if amount > 10:
        await ctx.send("❌ Max 10 keys at once")
        return
    
    keys = []
    for _ in range(amount):
        key = generate_key()
        await licenses.insert_one({
            "key": key, "duration": duration, "expiry": get_expiry(duration),
            "used_by": None, "used_by_discord": None, "used_at": None, "hwid": None,
            "created_by": str(ctx.author.id), "created_at": datetime.now(), "revoked": False, "type": duration
        })
        keys.append(key)
    
    await ctx.send(f"✅ Generated {amount} key(s):\n```\n" + "\n".join(keys) + "\n```")

@bot.command(name="redeem")
async def redeem_key(ctx, key: str = None):
    """Redeem a license key - !redeem LP-XXXX-XXXX"""
    if not key:
        await ctx.send("❌ Usage: `!redeem LP-XXXX-XXXX`")
        return
    
    data = await licenses.find_one({"key": key.upper()})
    
    if not data:
        await ctx.send("❌ Invalid license key!")
        return
    if data.get("revoked"):
        await ctx.send("❌ This license has been revoked!")
        return
    if data.get("used_by"):
        await ctx.send("❌ This license is already in use!")
        return
    if data["expiry"] < datetime.now():
        await ctx.send("❌ This license has expired!")
        return
    
    await licenses.update_one(
        {"key": key.upper()},
        {"$set": {
            "used_by": str(ctx.author.id), "used_by_discord": str(ctx.author),
            "used_at": datetime.now(), "hwid": str(ctx.author.id)
        }}
    )
    
    await users.update_one(
        {"discord_id": str(ctx.author.id)},
        {"$set": {
            "name": str(ctx.author), "license_key": key.upper(),
            "expiry": data["expiry"], "type": data.get("duration", "unknown")
        }},
        upsert=True
    )
    
    await ctx.send(f"✅ License redeemed!\n📅 Expires: {data['expiry'].strftime('%Y-%m-%d')}")

@bot.command(name="grant")
@commands.has_permissions(administrator=True)
async def grant_time(ctx, user: discord.User, duration: str, *, reason: str = "No reason"):
    """Grant extension - !grant @user 1m/1w/1y [reason]"""
    user_data = await users.find_one({"discord_id": str(user.id)})
    if not user_data:
        await ctx.send(f"❌ {user.mention} doesn't have a license!")
        return
    
    new_expiry = get_expiry(duration)
    old_expiry = user_data.get("expiry")
    if old_expiry and old_expiry > datetime.now():
        new_expiry = old_expiry + (new_expiry - datetime.now())
    
    await users.update_one({"discord_id": str(user.id)}, {"$set": {"expiry": new_expiry}})
    await licenses.update_one({"key": user_data["license_key"]}, {"$set": {"expiry": new_expiry}})
    
    await ctx.send(f"✅ Granted {duration} to {user.mention}\n📅 New expiry: {new_expiry.strftime('%Y-%m-%d')}\n📝 Reason: {reason}")
    
    try:
        embed = discord.Embed(title="✅ License Extended", color=discord.Color.green())
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="New Expiry", value=new_expiry.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.command(name="terminate")
@commands.has_permissions(administrator=True)
async def terminate_key(ctx, user: discord.User, *, reason: str = "No reason"):
    """Terminate license - !terminate @user [reason]"""
    user_data = await users.find_one({"discord_id": str(user.id)})
    if not user_data:
        await ctx.send(f"❌ {user.mention} doesn't have a license!")
        return
    
    await users.update_one({"discord_id": str(user.id)}, {"$set": {"expiry": datetime.now(), "revoked": True}})
    await licenses.update_one({"key": user_data["license_key"]}, {"$set": {"revoked": True}})
    
    await ctx.send(f"✅ Terminated {user.mention}'s license\n📝 Reason: {reason}")
    
    try:
        embed = discord.Embed(title="❌ License Terminated", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason, inline=False)
        await user.send(embed=embed)
    except:
        pass

@bot.command(name="dashboard")
async def dashboard_link(ctx):
    """Get dashboard link"""
    await ctx.send(f"📊 **LightPanel Pro Dashboard**\nhttps://lightpanel-bot.up.railway.app/\n\nLogin with admin key")

@bot.command(name="stats")
async def show_stats(ctx):
    """Show license statistics"""
    total = await licenses.count_documents({})
    used = await licenses.count_documents({"used_by": {"$ne": None}})
    active = await users.count_documents({"expiry": {"$gt": datetime.now()}})
    await ctx.send(f"📊 **Statistics:**\nTotal Licenses: {total}\nUsed: {used}\nActive Users: {active}")

@bot.command(name="ping")
async def ping(ctx):
    """Check bot latency"""
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command(name="helpme")
async def help_command(ctx):
    """Show all commands"""
    embed = discord.Embed(title="LightPanel Pro Commands", color=discord.Color.blue())
    embed.add_field(name="!gen 1d/1w/1m/1y/lifetime", value="Generate license key (Admin only)", inline=False)
    embed.add_field(name="!redeem LP-XXXX-XXXX", value="Redeem your license key", inline=False)
    embed.add_field(name="!grant @user 1m/1w/1y", value="Extend user's license (Admin)", inline=False)
    embed.add_field(name="!terminate @user", value="Revoke user's license (Admin)", inline=False)
    embed.add_field(name="!stats", value="Show license statistics", inline=False)
    embed.add_field(name="!dashboard", value="Get dashboard link", inline=False)
    embed.add_field(name="!ping", value="Check bot latency", inline=False)
    await ctx.send(embed=embed)

# ========== MODERATION COMMANDS ==========

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_user(ctx, user: discord.User, *, reason: str = "No reason"):
    """Ban a user"""
    await ctx.guild.ban(user, reason=reason)
    await ctx.send(f"✅ Banned {user.mention}\nReason: {reason}")

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_user(ctx, user: discord.User, *, reason: str = "No reason"):
    """Kick a user"""
    await ctx.guild.kick(user, reason=reason)
    await ctx.send(f"✅ Kicked {user.mention}\nReason: {reason}")

@bot.command(name="timeout")
@commands.has_permissions(moderate_members=True)
async def timeout_user(ctx, user: discord.User, minutes: int = 5, *, reason: str = "No reason"):
    """Timeout a user"""
    duration = timedelta(minutes=minutes)
    await user.timeout(duration, reason=reason)
    await ctx.send(f"✅ Timed out {user.mention} for {minutes} minutes\nReason: {reason}")

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int = 10):
    """Clear messages"""
    if amount > 100:
        amount = 100
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"✅ Cleared {len(deleted)} messages", delete_after=3)

bot.run(TOKEN)
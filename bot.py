import discord
from discord import app_commands
from discord.ext import commands
import os
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TIKAPI_KEY = os.getenv("TIKAPI_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Set up bot
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True  # Required for role assignments

bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_message(message):
    """Deletes any messages in #get-verified that are not /verify or /confirmverify."""
    
    # Ignore bot messages to prevent infinite loops
    if message.author.bot:
        return

    # Set the correct channel ID for #get-verified
    GET_VERIFIED_CHANNEL_ID = 1339695387782549685  # Replace with your actual channel ID

    # If the message is in #get-verified and not a valid command, delete it
    if message.channel.id == GET_VERIFIED_CHANNEL_ID:
        if not (message.content.startswith("/verify") or message.content.startswith("/confirmverify")):
            try:
                await message.delete()
                await message.author.send("⚠️ Please only use `/verify` or `/confirmverify` in #get-verified.", delete_after=10)
            except discord.Forbidden:
                print("❌ Bot lacks permission to delete messages in #get-verified.")
            except discord.HTTPException as e:
                print(f"⚠️ Failed to delete message: {e}")

    # Process commands so that slash commands still work
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()  
        
# ✅ Sync global slash commands
        print(f"🔄 Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# ✅ Convert /verify to a Slash Command
@bot.tree.command(name="verify", description="Verify your TikTok or YouTube account.")
@app_commands.describe(platform="Select platform (TikTok/YouTube)", username="Enter your TikTok/YouTube username")
async def verify(interaction: discord.Interaction, platform: str, username: str):
    """Verify a user by linking their TikTok or YouTube account."""
    platforms = ["tiktok", "youtube"]
    if platform.lower() not in platforms:
        await interaction.response.send_message("❌ Invalid platform. Use `/verify tiktok <username>` or `/verify youtube <username>`.", ephemeral=True)
        return

    # Generate verification code
    verification_code = f"{interaction.user.id}-{platform.upper()}"

    await interaction.response.send_message(
        f"🔍 @{interaction.user.mention}, to verify your {platform} account:\n"
        f"1️⃣ Add the code `{verification_code}` to your **bio** or latest post.\n"
        f"2️⃣ Reply here when done with `/confirmverify {platform} {username}`.",
        ephemeral=True
    )

    # Store verification request
    if not hasattr(bot, "pending_verifications"):
        bot.pending_verifications = {}

    bot.pending_verifications[interaction.user.id] = {
        "platform": platform,
        "username": username,
        "code": verification_code
    }

# ✅ Convert /confirmverify to a Slash Command
@bot.tree.command(name="confirmverify", description="Confirm your TikTok or YouTube verification.")
@app_commands.describe(platform="Select platform (TikTok/YouTube)", username="Enter your TikTok/YouTube username")
async def confirmverify(interaction: discord.Interaction, platform: str, username: str):
    """Confirm verification after adding the code to TikTok/YouTube bio."""
    if interaction.user.id not in bot.pending_verifications:
        await interaction.response.send_message("❌ You don't have a pending verification request.", ephemeral=True)
        return

    verification_data = bot.pending_verifications[interaction.user.id]
    verification_code = verification_data["code"]

    verified = False
    if platform.lower() == "tiktok":
        verified = check_tiktok_bio(username, verification_code)
    elif platform.lower() == "youtube":
        verified = check_youtube_bio(username, verification_code)

    if not verified:
        await interaction.response.send_message("❌ Verification code not found in your bio. Please add it and try again.", ephemeral=True)
        return

    # Assign Verified role
    verified_role = discord.utils.get(interaction.guild.roles, name="Verified")
    if verified_role:
        await interaction.user.add_roles(verified_role)
        await interaction.response.send_message(f"✅ @{interaction.user.mention} is now **Verified**!")
    else:
        await interaction.response.send_message("⚠️ 'Verified' role not found! Please create it in server settings.", ephemeral=True)

    # Remove from pending verifications
    del bot.pending_verifications[interaction.user.id]

# ✅ TikTok Bio Check
def check_tiktok_bio(username, verification_code):
    """Fetch TikTok bio and check for the verification code."""
    url = f"https://api.tikapi.io/public/check?username={username}"
    headers = {"X-API-KEY": TIKAPI_KEY}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        bio = data.get("userInfo", {}).get("user", {}).get("signature", "")
        print(f"📢 TikTok Bio for {username}: {bio}")
        return verification_code.strip().lower() in bio.strip().lower()

    print(f"❌ TikTok API Error: {response.status_code} - {response.text}")
    return False

# ✅ YouTube Bio Check
def check_youtube_bio(username, verification_code):
    """Fetch YouTube channel description and check for the verification code."""
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    
    request = youtube.channels().list(
        part="snippet",
        forUsername=username
    )
    response = request.execute()

    if "items" in response and len(response["items"]) > 0:
        bio = response["items"][0]["snippet"].get("description", "")
        print(f"📢 YouTube Bio for {username}: {bio}")
        return verification_code.strip().lower() in bio.strip().lower()

    return False


import json
import time

# Store submitted videos
if not hasattr(bot, "video_submissions"):
    bot.video_submissions = {}

# ✅ /submitvideo Command
@bot.tree.command(name="submitvideo", description="Submit a TikTok or YouTube video to track views.")
@app_commands.describe(platform="Select the platform", video_url="Paste your video link")
async def submitvideo(interaction: discord.Interaction, platform: str, video_url: str):
    """Allows users to submit their video link for tracking."""
    platforms = ["tiktok", "youtube"]
    if platform.lower() not in platforms:
        await interaction.response.send_message("❌ Invalid platform. Use `/submitvideo tiktok <video_url>` or `/submitvideo youtube <video_url>`.", ephemeral=True)
        return

    # Fetch initial views
    initial_views = 0
    if platform == "tiktok":
        initial_views = get_tiktok_views(video_url)
    elif platform == "youtube":
        initial_views = get_youtube_views(video_url)

    # Store video submission with server ID (campaign)
    bot.video_submissions[interaction.user.id] = {
        "server_id": interaction.guild.id,  # Store campaign ID
        "server_name": interaction.guild.name,  # Store campaign name
        "platform": platform,
        "video_url": video_url,
        "submitted_at": time.time(),
        "initial_views": initial_views,
        "latest_views": initial_views
    }

    await interaction.response.send_message(
        f"✅ @{interaction.user.mention}, your video has been submitted for tracking in **{interaction.guild.name}**!\n"
        f"📊 Initial Views: **{initial_views}**", ephemeral=True
    )

# ✅ /allsubmissions Command    
@bot.tree.command(name="allsubmissions", description="View all submitted videos across campaigns (admin & server team Only).")
async def allsubmissions(interaction: discord.Interaction):
    """Shows all submitted videos grouped by campaign (admin & server team Team Only)."""
    
    # 🔹 Check if user is an admin
    is_admin = interaction.user.guild_permissions.administrator

    # 🔹 Check if user has "Server Team" role
    server_team_role = discord.utils.get(interaction.guild.roles, name="server team")
    has_server_team_role = server_team_role in interaction.user.roles if server_team_role else False

    # 🔹 If neither admin nor "Server Team" role, deny access
    if not is_admin and not has_server_team_role:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    if not bot.video_submissions:
        await interaction.response.send_message("❌ No video submissions found.", ephemeral=True)
        return

    # 🔹 Group videos by campaign
    campaign_videos = {}
    for user_id, video in bot.video_submissions.items():
        campaign_name = video["server_name"]
        if campaign_name not in campaign_videos:
            campaign_videos[campaign_name] = []
        campaign_videos[campaign_name].append(video)

    # 🔹 Format response
    response = "**📊 All Submitted Videos by Campaign:**\n\n"
    for campaign, videos in campaign_videos.items():
        response += f"**🎯 {campaign}:**\n"
        for vid in videos:
            response += f"- 🔗 [{vid['video_url']}]({vid['video_url']}) on **{vid['platform'].capitalize()}**\n"
        response += "\n"

    await interaction.response.send_message(response, ephemeral=True)


# ✅ /checkviews Command
@bot.tree.command(name="checkviews", description="Check the current views of your submitted video.")
async def checkviews(interaction: discord.Interaction):
    """Allows users to check the view count of their submitted video."""
    if interaction.user.id not in bot.video_submissions:
        await interaction.response.send_message("❌ You haven't submitted a video yet. Use `/submitvideo` first.", ephemeral=True)
        return

    video_data = bot.video_submissions[interaction.user.id]
    platform = video_data["platform"]
    video_url = video_data["video_url"]

    # Fetch views from the appropriate API
    if platform == "tiktok":
        views = get_tiktok_views(video_url)
    elif platform == "youtube":
        views = get_youtube_views(video_url)
    else:
        views = 0

    # Update stored views
    bot.video_submissions[interaction.user.id]["views"] = views

    await interaction.response.send_message(f"📊 Your video has **{views}** views on {platform.capitalize()}!\n🔗 [View Video]({video_url})", ephemeral=True)

# ✅ Function to Fetch TikTok Views
def get_tiktok_views(video_url):
    """Fetches the view count of a TikTok video using the correct TikAPI endpoint."""
    
    # Extract the video ID from the TikTok URL
    try:
        video_id = video_url.split("/video/")[-1].split("?")[0]  # Extracts only the numeric video ID
        print(f"📢 Extracted TikTok Video ID: {video_id}")  # Debugging line
    except Exception as e:
        print(f"❌ Error extracting video ID: {e}")
        return 0

    # Check if the extracted ID is valid (should be numeric)
    if not video_id.isdigit():
        print(f"❌ Invalid TikTok Video ID: {video_id}")
        return 0

    # ✅ Use the correct TikAPI endpoint
    url = f"https://api.tikapi.io/public/video?id={video_id}"
    headers = {
        "X-API-KEY": TIKAPI_KEY,
        "accept": "application/json"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        views = data.get("data", {}).get("video", {}).get("stats", {}).get("playCount", 0)
        print(f"✅ TikTok Video Views: {views}")
        return views

    print(f"❌ TikTok API Error: {response.status_code} - {response.text}")
    return 0


# ✅ Function to Fetch YouTube

# ✅ Global Leaderboard

import asyncio

# 🔹 Replace these with actual channel IDs
CAMPAIGN_LEADERBOARD_CHANNELS = {
    1336579716383117312: 1339557250607616002,  # Server ID -> Leaderboard Channel ID
    #234567890123456789: 876543210987654321   # Add more campaign servers
}
GLOBAL_LEADERBOARD_CHANNEL_ID = 1339557250607616002  # Main server global leaderboard

async def update_leaderboards():
    """Completely clears the leaderboard channels and posts the latest leaderboard."""
    await bot.wait_until_ready()

    print("🔄 Updating leaderboards...")

    # 🔹 Update Campaign Leaderboards
    for guild_id, channel_id in CAMPAIGN_LEADERBOARD_CHANNELS.items():
        guild = bot.get_guild(guild_id)
        if guild:
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    # ✅ Purge entire channel history
                    await channel.purge()
                    print(f"✅ Cleared all messages in {channel.name} ({guild.name})")
                except discord.Forbidden:
                    print(f"❌ Missing permissions to delete messages in {channel.name} ({guild.name})")
                except discord.HTTPException as e:
                    print(f"⚠️ Failed to clear messages in {channel.name} ({guild.name}): {e}")

                # Get videos for this campaign
                campaign_videos = [
                    video for video in bot.video_submissions.values() if video["server_id"] == guild_id
                ]
                if campaign_videos:
                    campaign_videos.sort(key=lambda v: v["latest_views"], reverse=True)
                    response = f"**📊 {guild.name} Leaderboard (Top Videos):**\n\n"
                    for i, vid in enumerate(campaign_videos[:10], start=1):  # Limit to top 10
                        response += f"**#{i}** - [{vid['video_url']}]({vid['video_url']}) on **{vid['platform'].capitalize()}** - **{vid['latest_views']} Views**\n"

                    await channel.send(response)
                    print(f"✅ Leaderboard updated for {guild.name}")

    # 🔹 Update Global Leaderboard in Main Server
    global_channel = bot.get_channel(GLOBAL_LEADERBOARD_CHANNEL_ID)
    if global_channel:
        try:
            # ✅ Purge entire global leaderboard channel
            await global_channel.purge()
            print("✅ Cleared all messages in the global leaderboard channel")
        except discord.Forbidden:
            print("❌ Missing permissions to delete messages in the global leaderboard channel.")
        except discord.HTTPException as e:
            print(f"⚠️ Failed to clear messages in the global leaderboard channel: {e}")

        all_videos = sorted(bot.video_submissions.values(), key=lambda v: v["latest_views"], reverse=True)
        if all_videos:
            response = "**🌎 Global Leaderboard (Top Videos Across All Campaigns):**\n\n"
            for i, vid in enumerate(all_videos[:10], start=1):  # Limit to top 10
                response += f"**#{i}** - [{vid['video_url']}]({vid['video_url']}) on **{vid['platform'].capitalize()}** - **{vid['latest_views']} Views**\n"
                response += f"🎯 Campaign: **{vid['server_name']}**\n"

            await global_channel.send(response)
            print("✅ Global leaderboard updated!")

    print("✅ Leaderboard update complete!")



    await asyncio.sleep(3600)  # Update every hour

    bot.loop.create_task(update_leaderboards())
        
#📌 Add /forceupdate Command to Manually Update Leaderboards

@bot.tree.command(name="forceupdate", description="Manually update the leaderboard (Admin Only).")
async def forceupdate(interaction: discord.Interaction):
    """Allows admins to manually update the leaderboard."""
    
    # 🔹 Check if the user is an admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    # Run the leaderboard update function
    await update_leaderboards()

    await interaction.response.send_message("✅ Leaderboards updated!", ephemeral=True)


#📌 Add /requestpayout Command to Open Tickets

@bot.tree.command(name="requestpayout", description="Request a payout based on video views.")
async def requestpayout(interaction: discord.Interaction):
    """Opens a private payout ticket for Admins & Server Team to review."""
    
    user_id = interaction.user.id
    if user_id not in bot.video_submissions:
        await interaction.response.send_message("❌ You haven’t submitted any videos yet.", ephemeral=True)
        return

    video = bot.video_submissions[user_id]
    campaign_id = video["server_id"]
    views = video["latest_views"]

    # 🔹 Define Payout Per Campaign
    CAMPAIGN_PAYOUTS = {
        123456789012345678: 0.002,  # Example: Campaign 1 pays $0.002 per view
        234567890123456789: 0.005,  # Example: Campaign 2 pays $0.005 per view
    }
    payout_rate = CAMPAIGN_PAYOUTS.get(campaign_id, 0.001)  # Default rate

    # 🔹 Calculate payout amount
    payout_amount = round(views * payout_rate, 2)

    # 🔹 Check if a ticket already exists for this user
    guild = interaction.guild
    ticket_channel_name = f"payout-{interaction.user.name}".lower()
    existing_channel = discord.utils.get(guild.text_channels, name=ticket_channel_name)
    if existing_channel:
        await interaction.response.send_message("⚠️ You already have a payout request open.", ephemeral=True)
        return

    # ✅ Get the roles safely
    server_team_role = discord.utils.find(lambda r: r.name.lower() == "server team", guild.roles)
    admin_role = discord.utils.find(lambda r: r.name.lower() == "admin", guild.roles)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),  # Hide from everyone
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),  # Requester can see
    }

    if server_team_role:  # ✅ Only add if role exists
        overwrites[server_team_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    else:
        print("⚠️ Warning: 'server team' role not found. Skipping role permissions.")

    if admin_role:  # ✅ Only add if role exists
        overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    else:
        print("⚠️ Warning: 'admin' role not found. Skipping role permissions.")

    # 🔹 Create a private channel for the payout request
    try:
        ticket_channel = await guild.create_text_channel(name=ticket_channel_name, overwrites=overwrites)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Bot lacks permission to create channels.", ephemeral=True)
        return
    except Exception as e:
        print(f"❌ Error creating ticket channel: {e}")
        await interaction.response.send_message("❌ An error occurred while creating your payout ticket.", ephemeral=True)
        return

    # 🔹 Store pending payout request
    if not hasattr(bot, "pending_payouts"):
        bot.pending_payouts = {}

    bot.pending_payouts[user_id] = {
        "username": interaction.user.name,
        "campaign": guild.name,
        "views": views,
        "amount": payout_amount,
        "status": "Pending",
        "channel_id": ticket_channel.id
    }

    # 🔹 Send payout details in the ticket channel
    await ticket_channel.send(
        f"📌 **Payout Request for {interaction.user.mention}**\n"
        f"📊 **Views:** {views}\n"
        f"💰 **Requested Amount:** ${payout_amount}\n"
        f"🔍 **Campaign:** {guild.name}\n\n"
        f"🔹 **Admins & Server Team**, use `/approvepayout @{interaction.user.name}` to approve.\n"
        f"❌ Use `/closepayout @{interaction.user.name}` to deny."
    )

    await interaction.response.send_message(f"✅ Your payout request has been opened in {ticket_channel.mention}!", ephemeral=True)

    

     


# Run the bot
bot.run(TOKEN)

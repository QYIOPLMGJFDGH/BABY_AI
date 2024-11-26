import asyncio
import logging
import os
from typing import Dict

import google.generativeai as genai
from pymongo import MongoClient
from telegram import Update, error
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler,
)
from flask import Flask, request, jsonify

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get API keys and settings from environment variables
TELEGRAM_TOKEN = os.environ.get("7711977179:AAFxPfbCD14LJLTekHKkHKTq6zRUCDscNEo")
GEMINI_API_KEY = os.environ.get("AIzaSyDq47CQUgrNXQ5WCgw9XDJCudlUrhyC-pY")
CHANNEL_USERNAME = os.environ.get("@BABY09_WORLD")
OWNER_ID = int(os.environ.get("7400383704"))  # Convert OWNER_ID to integer
MONGO_URI = os.environ.get("mongodb+srv://Yash_607:Yash_607@cluster0.r3s9sbo.mongodb.net/?retryWrites=true&w=majority")

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Cache to store recent responses (optional, for performance)
response_cache = {}

# Initialize MongoDB client
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
authorized_users_collection = db[COLLECTION_NAME]


async def ask_gemini(question):
    # Check if the response is in the cache (optional)
    if question in response_cache:
        return response_cache[question]

    # Use the generative model from Google Gemini
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(question)  # Removed max_tokens

    # Return the response text
    reply = response.text if response.text else "Sorry, no response."

    # Store the response in the cache (optional)
    response_cache[question] = reply
    return reply


async def is_authorized(user_id: int):
    """Checks if a user is authorized to use the bot."""
    # Automatically authorize the owner
    if user_id == OWNER_ID:
        return True
    user = authorized_users_collection.find_one({"user_id": user_id})
    return user is not None


async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approves a user to use the bot."""
    logger.info("Approve user command received.")

    if update.effective_user.id != OWNER_ID:
        logger.warning(
            f"Unauthorized user tried to approve: {update.effective_user.id}"
        )
        await update.message.reply_text("You are not authorized to approve users.")
        return

    try:
        username = context.args[0]  # Get username from command arguments
        logger.info(f"Attempting to approve user: {username}")
        try:
            # Fetch user details using the provided username
            user = await context.bot.get_chat(username)
            user_id = user.id
            logger.info(f"Fetched user ID: {user_id}")

            # Store the authorized user in MongoDB
            result = authorized_users_collection.insert_one(
                {"user_id": user_id, "username": username}
            )
            logger.info(f"MongoDB insertion result: {result.acknowledged}")

            await update.message.reply_text(f"User {username} has been approved!")

        except error.TelegramError as e:
            if e.message == "Chat not found":
                await update.message.reply_text(
                    f"Error: User '{username}' not found. Please check the username and ensure the bot has access to it."
                )
            else:
                logger.error(f"Error getting user chat: {e}")
                await update.message.reply_text(
                    "An unexpected error occurred while fetching user information."
                )

    except IndexError:
        await update.message.reply_text(
            "Please provide a username to approve. Usage: `/approve @username`"
        )
    except Exception as e:
        logger.exception(f"Error approving user: {e}")
        await update.message.reply_text("An error occurred while approving the user.")


async def disapprove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disapproves a user, removing them from the authorized list."""
    logger.info("Disapprove user command received.")

    if update.effective_user.id != OWNER_ID:
        logger.warning(
            f"Unauthorized user tried to disapprove: {update.effective_user.id}"
        )
        await update.message.reply_text("You are not authorized to disapprove users.")
        return

    try:
        username = context.args[0]  # Get username from command arguments
        logger.info(f"Attempting to disapprove user: {username}")

        try:
            # Fetch user details using the provided username (optional)
            user = await context.bot.get_chat(username)
            user_id = user.id
            logger.info(f"Fetched user ID: {user_id}")

            # Delete the user from MongoDB using their username
            result = authorized_users_collection.delete_one({"username": username})

            if result.deleted_count == 1:
                await update.message.reply_text(f"User {username} has been disapproved.")
            else:
                await update.message.reply_text(
                    f"User {username} not found in the approved list."
                )

        except error.TelegramError as e:
            if e.message == "Chat not found":
                await update.message.reply_text(f"Error: User '{username}' not found.")
            else:
                logger.error(f"Error getting user chat: {e}")
                await update.message.reply_text(
                    "An unexpected error occurred while fetching user information."
                )

    except IndexError:
        await update.message.reply_text(
            "Please provide a username to disapprove. Usage: `/disapprove @username`"
        )
    except Exception as e:
        logger.exception(f"Error disapproving user: {e}")
        await update.message.reply_text(
            "An error occurred while disapproving the user."
        )


async def check_user_in_channel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.message.from_user.id
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        logger.info(f"Chat member status: {chat_member.status}")
        return chat_member.status in ["member", "administrator", "creator"]
    except error.TelegramError as e:
        logger.error(f"Error checking user in channel: {e}")
        return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check authorization AND channel membership
    authorized = await is_authorized(user_id)
    member_of_channel = await check_user_in_channel(update, context)

    if not authorized:
        await update.message.reply_text(
            "You are not authorized to use this bot. Please contact @UTTAM470 for authorize."
        )
        return

    if not member_of_channel:
        await update.message.reply_text(
            f"Please join the channel {CHANNEL_USERNAME} to use the bot:",
            parse_mode=ParseMode.HTML,
        )
        return

    user_message = update.message.text.lower()

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Get the response from Gemini
    reply = await ask_gemini(user_message)

    # Combine typing action and response
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    try:
        # Create the inline button
        join_button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Join 👋", url="https://t.me/BABY09_WORLD")]]
        )
        # Send a welcome message with the button
        await update.message.reply_text(
            "Hey! I am team baby AI. How can I help you today? ask me any query",
            reply_markup=join_button,
        )
    except Exception as e:
        logger.error(f"Error in /start command: {e}")


async def approved_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /approved command to list all approved users in numbered format."""
    # Check if the sender is the owner
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(
            "You are not authorized to use this command."
        )
        return

    # Fetch all approved users from the MongoDB collection
    approved_users = authorized_users_collection.find()

    # Prepare the message with numbered list
    mentions = ""
    count = 1
    for user in approved_users:
        mentions += f"{count}. {user['username']} \n"
        count += 1

    # If no approved users found
    if not mentions:
        await update.message.reply_text("No approved users found.")
        return

    # Send the list of approved users in numbered format
    await update.message.reply_text(
        f"List of approved users:\n\n{mentions}", parse_mode=ParseMode.MARKDOWN
    )

# Initialize Flask app for webhook
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    This function handles incoming Telegram updates through a webhook.
    """
    if request.method == 'POST':
        update = request.get_json()
        
        # ---  Here you need to adapt the update handling ---
        # 1. Create an Update object from the incoming JSON
        # update = Update.de_json(update, bot)  # 'bot' needs to be your bot instance
        
        # 2. Pass the update to your Telegram bot's dispatcher
        # application.process_update(update) 
        # ---------------------------------------------------

        return jsonify({'status': 'success'})  # Acknowledge update received


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("disapprove", disapprove_user))
    application.add_handler(CommandHandler("approved", approved_users))

    # Message handler for all text messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Start the bot
    logger.info("Bot is running...")
    # application.run_polling()  # Comment out for webhook mode

    # --- Start Flask app for webhook ---
    app.run(debug=True, host='0.0.0.0', port=8000)

if __name__ == "__main__":
    main()

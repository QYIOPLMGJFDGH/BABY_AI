import asyncio
import requests
import threading
from flask import Flask 
import logging
from typing import Dict
import traceback
import sys
import html
from io import StringIO
from telegram.ext import CallbackQueryHandler  # Missing import for handling callbacks
import google.generativeai as genai
from pymongo import MongoClient
from telegram.ext import filters
from telegram import Update, error, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    CommandHandler,
)
from time import time


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot Token
TELEGRAM_TOKEN = "8007949478:AAGVaf6zO-V1aS2CH4fgJLoxbRXT_gKvm1o"
# Gemini API Key
GEMINI_API_KEY = "AIzaSyDq47CQUgrNXQ5WCgw9XDJCudlUrhyC-pY"  # Replace with your actual Gemini API key

# Channel Link
CHANNEL_USERNAME = "@BABY09_WORLD"

# Owner ID
OWNER_ID = 7400383704

# MongoDB Connection
MONGO_URI = "mongodb+srv://Yash_607:Yash_607@cluster0.r3s9sbo.mongodb.net/?retryWrites=true&w=majority"
DATABASE_NAME = "telegram_bot"
COLLECTION_NAME = "authorized_users"

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
            result = authorized_users_collection.insert_one({
                "user_id": user_id,
                "username": username
            })
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
            "Please provide a username to approve. Usage: `/approve userid`"
        )
    except Exception as e:
        logger.exception(f"Error approving user: {e}")
        await update.message.reply_text(
            "An error occurred while approving the user.")


async def disapprove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disapproves a user, removing them from the authorized list."""
    logger.info("Disapprove user command received.")

    if update.effective_user.id != OWNER_ID:
        logger.warning(
            f"Unauthorized user tried to disapprove: {update.effective_user.id}"
        )
        await update.message.reply_text(
            "You are not authorized to disapprove users."
        )
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
                await update.message.reply_text(
                    f"User {username} has been disapproved.")
            else:
                await update.message.reply_text(
                    f"User {username} not found in the approved list.")

        except error.TelegramError as e:
            if e.message == "Chat not found":
                await update.message.reply_text(
                    f"Error: User '{username}' not found.")
            else:
                logger.error(f"Error getting user chat: {e}")
                await update.message.reply_text(
                    "An unexpected error occurred while fetching user information."
                )

    except IndexError:
        await update.message.reply_text(
            "Please provide a username to disapprove. Usage: `/disapprove userid`"
        )
    except Exception as e:
        logger.exception(f"Error disapproving user: {e}")
        await update.message.reply_text(
            "An error occurred while disapproving the user.")


async def check_user_in_channel(update: Update,
                               context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_USERNAME,
                                                        user_id)
        logger.info(f"Chat member status: {chat_member.status}")
        return chat_member.status in ["member", "administrator", "creator"]
    except error.TelegramError as e:
        logger.error(f"Error checking user in channel: {e}")
        return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    authorized = await is_authorized(user_id)
    member_of_channel = await check_user_in_channel(update, context)

    if not authorized:
        await update.message.reply_text("You are not authorized to use this bot. Contact @UTTAM470 for approval.")
        return
    if not member_of_channel:
        await update.message.reply_text(
            f"Please join the channel {CHANNEL_USERNAME} to use the bot:",
            parse_mode=ParseMode.HTML,
        )
        return

    user_message = update.message.text.lower()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply = await ask_gemini(user_message)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    try:
        # Inline button to join the channel
        join_button = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Join 👋", url="https://t.me/BABY09_WORLD")]
            ]
        )
        
        # Message with all commands information
        start_message = """
Hey! I am Team Baby AI. How can I help you today? Below are the available commands you can use:

<b>Commands:</b>
1. <code>/start</code> - Start the bot and see this help message.
2. <code>/approve &lt;username&gt;</code> - Approve a user to access the bot. (Admin only)
3. <code>/disapprove &lt;username&gt;</code> - Revoke access of a user. (Admin only)
4. <code>/approved</code> - List all approved users. (Admin only)
5. <code>/tb &lt;query&gt;</code> - Ask any query or get an baby AI response. 
   - Example: <code>/tb i want make ai tools?</code>
6. <code>/run &lt;code&gt;</code> - Execute Python code dynamically (only for authorized users).

<b>Note:</b> You must join our channel @BABY09_WORLD to use this bot.

Feel free to ask any question using the <code>/tb</code> command!
        """

        # Send the message
        await update.message.reply_text(
            start_message,
            reply_markup=join_button,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in /start command: {e}")


async def approved_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /approved command to list all approved users in numbered format."""
    # Check if the sender is the owner
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
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
        f"List of approved users:\n\n{mentions}",
        parse_mode=ParseMode.MARKDOWN
    )

async def aexec(code: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Asynchronous execution of the provided code string.
    Injects variables: `update`, `context`, and `application`.
    """
    exec(
        f"async def __aexec(update, context, application): " +
        "".join(f"\n {line}" for line in code.split("\n"))
    )
    return await locals()["__aexec"](update, context, context.application)

async def eval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /eval command for dynamic code execution.
    Only authorized users can execute this command.
    """
    user_id = update.effective_user.id

    # Check if the user is authorized
    if not await is_authorized(user_id):
        await update.message.reply_text(
            "You are not authorized to use this command. Please contact @UTTAM470 for approval."
        )
        return

    if len(context.args) < 1:
        await update.message.reply_text("<b>What do you want to execute?</b>", parse_mode=ParseMode.HTML)
        return

    cmd = " ".join(context.args)  # Extract the code to be executed
    t1 = time()
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    redirected_error = sys.stderr = StringIO()
    stdout, stderr, exc = None, None, None

    try:
        await aexec(cmd, update, context)
    except Exception:
        exc = traceback.format_exc()

    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = "\n"
    if exc:
        evaluation += exc
    elif stderr:
        evaluation += stderr
    elif stdout:
        evaluation += stdout
    else:
        evaluation += "Success"

    # Escape the evaluation output for safe HTML rendering
    evaluation = html.escape(evaluation)

    final_output = f"<b>⥤ Result :</b>\n<pre>{evaluation}</pre>"
    t2 = time()
    execution_time = round(t2 - t1, 3)

    if len(final_output) > 4096:
        filename = "output.txt"
        with open(filename, "w+", encoding="utf8") as out_file:
            out_file.write(str(evaluation))
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="Time",
                        callback_data=f"runtime {execution_time} Seconds",
                    )
                ]
            ]
        )
        await update.message.reply_document(
            document=filename,
            caption=f"<b>⥤ Eval :</b>\n<code>{html.escape(cmd[0:980])}</code>\n\n<b>⥤ Result :</b>\nAttached Document",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        os.remove(filename)
    else:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="Time",
                        callback_data=f"runtime {execution_time} Seconds",
                    ),
                    InlineKeyboardButton(
                        text="Close",
                        callback_data=f"forceclose abc|{update.effective_user.id}",
                    ),
                ]
            ]
        )
        await update.message.reply_text(final_output, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# Handler for Execution Time button
async def runtime_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    data = query.data

    if data.startswith("runtime"):
        execution_time = data.split(" ")[1]
        await query.answer(f"Execution Time: {execution_time}")

# Handler for Close button
async def close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: CallbackQuery = update.callback_query
    data = query.data

    if data.startswith("forceclose"):
        user_id = data.split("|")[1]
        if str(query.from_user.id) == user_id:  # Ensure only the initiating user can close
            await query.message.delete()
            await query.answer("Closed")
        else:
            await query.answer("You are not authorized to close this message.", show_alert=True)

async def handle_tb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the user has only sent "/tb" without additional text
    if update.message.text.strip() == "/tb":
        await update.message.reply_text("Please provide me your query after /tb. For example: `/tb your question`", parse_mode=ParseMode.MARKDOWN)
    else:
        # If there's more text, process it as a normal query
        await handle_message(update, context)


import requests

async def handle_bb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /bb command to fetch responses from the external API."""
    user_id = update.effective_user.id

    # Check if the user is authorized
    if not await is_authorized(user_id):
        await update.message.reply_text(
            "You are not authorized to use this command. Please contact @UTTAM470 for approval."
        )
        return

    # Check if the user is a member of the channel
    if not await check_user_in_channel(update, context):
        await update.message.reply_text(
            f"Please join the channel {CHANNEL_USERNAME} to use the bot.",
            parse_mode=ParseMode.HTML
        )
        return

    # Ensure a query is provided
    if len(context.args) < 1:
        await update.message.reply_text(
            "Please provide me your query after /bb. For example: `/bb your question`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Extract the query
    query = " ".join(context.args)

    # Inform the user that the bot is processing their request
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # API request logic
    API_KEY = "abacf43bf0ef13f467283e5bc03c2e1f29dae4228e8c612d785ad428b32db6ce"
    BASE_URL = "https://api.together.xyz/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "messages": [
            {
                "role": "user",
                "content": query
            }
        ]
    }
    
    try:
        response = requests.post(BASE_URL, json=payload, headers=headers)
        if response.status_code == 200 and response.text.strip():
            response_data = response.json()
            if "choices" in response_data and len(response_data["choices"]) > 0:
                result = response_data["choices"][0]["message"]["content"]
                await update.message.reply_text(
                    f"{result}\n\nＡɴsᴡᴇʀᴇᴅ ʙʏ ➛ [˹ ʙᴀʙʏ-ᴍᴜsɪᴄ ™˼𓅂](https://t.me/BABY09_WORLD)",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text("❍ ᴇʀʀᴏʀ: No response from the API.")
        else:
            await update.message.reply_text(f"❍ ᴇʀʀᴏʀ: API request failed. Status code: {response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"❍ ᴇʀʀᴏʀ: {str(e)}")


def create_application():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("approved", approved_users))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("disapprove", disapprove_user))
    application.add_handler(CommandHandler("run", eval_command))  # Eval command
    application.add_handler(CommandHandler("bb", handle_bb_command))  # /bb command
    application.add_handler(CallbackQueryHandler(runtime_callback, pattern="^runtime"))  # Execution time handler
    application.add_handler(CallbackQueryHandler(close_callback, pattern="^forceclose"))  # Close button handler
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/tb$'), handle_tb_command))  # Handle only "/tb"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/tb .*'), handle_message))  # Handle "/tb <query>"

    return application


# Flask app
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "BABYMUSIC is running"


def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)


def run_bot():
    # Start the bot
    application = create_application()
    application.run_polling()


if __name__ == "__main__":
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # Ensure Flask stops when the main program stops
    flask_thread.start()

    # Start the bot in the main thread
    run_bot()  # Run the bot directly without asyncio

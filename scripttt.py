import os
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)

# --- 1. Define Conversation States ---
FORM_FILLED, NAME, POSITION, LOCATION, EXPERIENCE, GROUP_PROOF, END = range(7)

# --- 2. Setup Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3. Persistent Storage Setup (Google Sheets) ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
CREDS_FILE = 'credentials.json'
SPREADSHEET_NAME = 'job application'
SHEET = None

# --- Configuration Parameters for Choreo/Gunicorn ---
# CRITICAL: The bot token is read from the environment variable 'TOKEN' provided by the hosting platform (Choreo).
# The hardcoded token is included as a fallback but should not be relied upon in production.
TOKEN = os.environ.get('TOKEN', "7683646109:AAFNeKBDnO0P1Ug0cu0O28797smnrK7mc4k")


# --- Helper Functions (Google Sheets Integration) ---

def initialize_google_sheets():
    """Initializes gspread client and opens the target sheet."""
    global SHEET
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        client = gspread.authorize(creds)
        SHEET = client.open(SPREADSHEET_NAME).sheet1
        logger.info("Successfully connected to Google Sheets.")
    except Exception as e:
        logger.error(f"Error connecting to Google Sheets. Check credentials.json and sharing permissions: {e}")
        SHEET = None


def store_application_data(update: Update, chat_id, data):
    """Writes the collected data to the Google Sheet."""
    if not SHEET:
        logger.error("Google Sheets is not active. Application data was NOT saved externally.")
        return

    try:
        # Get the timestamp from the update message
        timestamp = str(update.effective_message.date)

        row = [
            timestamp,
            str(chat_id),
            data.get('full_name', 'N/A'),
            data.get('position', 'N/A'),
            data.get('location', 'N/A'),
            data.get('experience', 'N/A'),
        ]
        SHEET.append_row(row)
        logger.info(f"Application saved to Google Sheets for user {chat_id}")
    except Exception as e:
        logger.error(f"Failed to append row to Google Sheet: {e}")


# ----------------------------------------------------
# --- Bot Steps (Handlers) ---
# ----------------------------------------------------

async def start(update: Update, context) -> int:
    """Sends a welcome message and asks about the Google Form."""
    chat_id = update.effective_chat.id
    context.user_data['application'] = {'chat_id': chat_id}

    keyboard = [
        [
            InlineKeyboardButton("Yes, I have.", callback_data='yes_form'),
            InlineKeyboardButton("No, I haven't.", callback_data='no_form'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 **Welcome to Gebeta Tutors Application Bot!**\n\nHave you already filled out our Google Form?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return FORM_FILLED


async def form_check_callback(update: Update, context) -> int:
    """Handles the 'Yes' or 'No' button click."""
    query = update.callback_query
    await query.answer()

    if query.data == 'no_form':
        form_link = 'https://forms.gle/aKBVuH9BHvwQYf4v9'
        keyboard = [[InlineKeyboardButton("I have completed the form.", callback_data='form_completed')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Please fill out the Google Form here:\n\n🔗 **{form_link}**\n\nClick the button once you are done.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return FORM_FILLED

    await query.edit_message_text(
        "Great! To begin your Telegram application, please send us your full name."
    )
    return NAME


async def get_name(update: Update, context) -> int:
    """Stores the name and asks for the job position."""
    name = update.message.text
    context.user_data['application']['full_name'] = name
    await update.message.reply_text(
        f"Thank you, {name}. Now, please enter the specific job position you are applying for as per the job post code (e.g., GT-1023)."
    )
    return POSITION


async def get_position(update: Update, context) -> int:
    """Stores the position and asks for location."""
    context.user_data['application']['position'] = update.message.text
    await update.message.reply_text(
        "Please provide your living address and your preferred working address/city (e.g., Living: Megenagna; Working: Mexico)."
    )
    return LOCATION


async def get_location(update: Update, context) -> int:
    """Stores the location and asks for experience details."""
    context.user_data['application']['location'] = update.message.text
    await update.message.reply_text(
        "📝 Please mention your experience (if any). Specify your experience as in National curriculum, International curriculum, and General teaching or tutoring experience."
    )
    return EXPERIENCE


async def get_experience(update: Update, context) -> int:
    """Stores the experience and asks for group join confirmation."""
    context.user_data['application']['experience'] = update.message.text
    group_link = 'https://t.me/Gebeta_Tutors_Circle'

    keyboard = [[InlineKeyboardButton("I have added people to the group.", callback_data='group_joined')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"The next step is to add at least 20 people in our tutors circle group,adding more people is a plus:\n\n🔗 **{group_link}**\n\nClick the button below to confirm you have added.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return GROUP_PROOF


async def complete_application(update: Update, context) -> int:
    """Saves the final data to Google Sheets and sends the completion message."""
    query = update.callback_query
    await query.answer()

    # The update.effective_message is not available on a CallbackQuery, use query.message
    # We pass the original update object to store_application_data to maintain the required signature
    # However, since store_application_data only needs the timestamp/date, we'll ensure we use
    # a proper Update object or pass the date separately. Since the application flow assumes a conversation,
    # the date from the query message should suffice for timestamping the final step.
    chat_id = query.message.chat_id
    store_application_data(update, chat_id, context.user_data['application'])

    await query.edit_message_text(
        "✅ Thank you! We have received your complete application. We will review it and get back to you soon."
    )
    return ConversationHandler.END


async def fallback_text(update: Update, context) -> None:
    """Informs the user they need to stick to the conversation flow."""
    await update.message.reply_text("Please provide the required information for the current step.")


async def cancel(update: Update, context) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text(
        'Application cancelled. Use /start to begin again.', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ----------------------------------------------------
# --- Application Initialization Function ---
# ----------------------------------------------------

def initialize_application() -> Application:
    """Initializes the bot application and all handlers.

    This function is called by the Gunicorn web server to set up the Application object
    before processing webhook requests. It does NOT run polling.
    """

    # 1. Initialize Google Sheets connection first
    initialize_google_sheets()

    # 2. Build the Application
    app = Application.builder().token(TOKEN).build()

    # 3. Create the ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FORM_FILLED: [
                CallbackQueryHandler(form_check_callback, pattern='^(yes_form|no_form|form_completed)$')
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_position)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_experience)],
            GROUP_PROOF: [
                CallbackQueryHandler(complete_application, pattern='^group_joined$')
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    # Add a fallback handler for non-command text outside of the conversation
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    return app

# ----------------------------------------------------
# --- Choreo/Gunicorn Global Entry Point ---
# ----------------------------------------------------

# CRITICAL: Gunicorn needs a global variable named 'application' (or similar, based on Procfile)
# which contains the fully configured Application object.
try:
    application = initialize_application()
    logger.info("Telegram Bot Application object initialized successfully.")
except Exception as e:
    logger.critical(f"FATAL ERROR during application initialization: {e}")
    # In case of initialization failure, 'application' might be needed for the Procfile,
    # so we assign None or handle it gracefully, though Gunicorn will likely fail.
    application = None

# No main() function or if __name__ == '__main__': is needed.
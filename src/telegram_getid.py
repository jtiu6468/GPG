import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Replace 'YOUR_BOT_TOKEN' with the actual token you received from BotFather
BOT_TOKEN = '8130891924:AAETe99LGiL5HzuFKEDC7KVmNZBfGeas1PY'

async def start(update, context):
    """Sends a welcome message and the chat ID."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Hello! Your chat ID is: {chat_id}")

async def get_chat_id(update, context):
    """Sends the chat ID of the current chat."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"The chat ID of this chat is: {chat_id}")

def main():
    """Starts the Telegram bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Command handler to get the chat ID when the user sends /start
    application.add_handler(CommandHandler("start", start))
    
    # Command handler to explicitly get the chat ID with /chatid
    application.add_handler(CommandHandler("chatid", get_chat_id))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
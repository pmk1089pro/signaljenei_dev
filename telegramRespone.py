from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Replace with your token
BOT_TOKEN = '8265133867:AAHHPOOnHu5n_wWoXfNYHGvyyBNA4_6ztxY'

# When user sends /start
async def start(update, context):
    await update.message.reply_text("Bot started! Send me something.")

# When user sends ANY text
async def handle_message(update, context):
    received_text = update.message.text
    print("User sent:", received_text)

    # Send back response
    await update.message.reply_text(f"You said: {received_text}")

# Run the bot
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()

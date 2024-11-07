from callback import CallbackHandlers
from commands import CommandHandlers
from db import Database
from dotenv import dotenv_values
from telegram.ext import Application, CommandHandler, CallbackQueryHandler


config = dotenv_values(".env")


def main() -> None:
    # Initialize services
    db = Database()

    # Initialize handlers
    command_handlers = CommandHandlers(db)
    callback_handlers = CallbackHandlers(db)

    application = Application.builder().token(config["API"]).build()

    # Add other command handlers
    application.add_handler(
        CallbackQueryHandler(callback_handlers.handle_buy_callback, pattern="^buy_")
    )
    application.add_handler(
        CallbackQueryHandler(callback_handlers.handle_sell_callback, pattern="^sell_")
    )

    application.add_handler(CommandHandler("start", command_handlers.start))
    application.add_handler(CommandHandler("reload", command_handlers.reload))
    application.add_handler(CommandHandler("portfolio", command_handlers.portfolio))
    application.add_handler(CommandHandler("help", command_handlers.help))
    application.add_handler(CommandHandler("buy", command_handlers.buy))
    application.add_handler(CommandHandler("sell", command_handlers.sell))
    application.run_polling()


if __name__ == "__main__":
    main()

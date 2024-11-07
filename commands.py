import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from db import Database
from services import PortfolioService, DexScreenerAPI

logger = logging.getLogger(__name__)


class CommandHandlers:
    def __init__(self, db: Database):
        self.db = db
        self.dex_api = DexScreenerAPI()
        self.portfolio_service = PortfolioService(db, self.dex_api)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        account = self.db.get_account(user_id)

        if account:
            await update.message.reply_text(
                "You already have an account. Use /portfolio to view your positions or "
                "/reload <amount> to reset your account with a new balance."
            )
            return

        # Create new account with 10 SOL
        account = self.db.create_account(user_id, 10.0)

        await update.message.reply_text(
            "Welcome to the Paper Trading Bot! 🚀\n\n"
            f"Your account has been created with 10 SOL\n\n"
            "Available commands:\n"
            "/portfolio - View your current portfolio\n"
            "/reload <amount> - Reset account with new balance\n"
            "/help - Show this help message"
        )

    async def reload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(
                    "Please provide the amount of SOL to reload.\n"
                    "Usage: /reload <amount>"
                )
                return

            try:
                new_balance = float(context.args[0])
            except ValueError:
                await update.message.reply_text(
                    "Invalid amount provided. Please enter a valid number."
                )
                return

            if new_balance <= 0:
                await update.message.reply_text("Balance must be greater than 0 SOL")
                return

            user_id = update.effective_user.id
            account = self.db.reset_account(user_id, new_balance)

            await update.message.reply_text(
                f"Account reset successfully!\n"
                f"New balance: {account.sol_balance:.3f} SOL"
            )

        except Exception as e:
            logger.error(f"Error in reload command: {e}")
            await update.message.reply_text(
                "An error occurred while processing your request. Please try again."
            )

    async def portfolio(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user_id = update.effective_user.id
        account = self.db.get_account(user_id)

        if not account:
            await update.message.reply_text(
                "You don't have an account yet. Use /start to create one."
            )
            return

        positions = self.db.get_positions(user_id)
        summary = self.portfolio_service.get_portfolio_summary(account, positions)
        await update.message.reply_text(summary, parse_mode="Markdown")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Paper Trading Bot Commands:\n\n"
            "/start - Create new account with 10 SOL\n"
            "/reload <amount> - Reset account with new balance\n"
            "/portfolio - View your current portfolio\n"
            "/help - Show this help message"
        )

    async def buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(
                    "Please provide the token address.\n" "Usage: /buy <token_address>"
                )
                return

            token_address = context.args[0]
            token_info = self.dex_api.get_token_data(token_address)

            if not token_info:
                await update.message.reply_text(
                    "Unable to fetch token information. Please verify the token address."
                )
                return

            symbol, price_native, price_usd, market_cap = token_info

            account = self.db.get_account(update.effective_user.id)
            if not account:
                await update.message.reply_text(
                    "Please use /start to create an account first."
                )
                return

            # Display token info and buy options
            message = (
                f"Token Information:\n"
                f"Symbol : {symbol}"
                f"Price: ${price_usd:.4f} SOL ({price_native:.9f})\n"
                f"Market Cap: ${market_cap:,.0f}\n"
                f"Your Balance: {account.sol_balance:.3f} SOL\n\n"
                f"Select amount to buy:"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "1 SOL", callback_data=f"buy_{token_address}_fixed_1"
                        ),
                        InlineKeyboardButton(
                            "3 SOL", callback_data=f"buy_{token_address}_fixed_3"
                        ),
                        InlineKeyboardButton(
                            "5 SOL", callback_data=f"buy_{token_address}_fixed_5"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "25%", callback_data=f"buy_{token_address}_percent_25"
                        ),
                        InlineKeyboardButton(
                            "50%", callback_data=f"buy_{token_address}_percent_50"
                        ),
                        InlineKeyboardButton(
                            "75%", callback_data=f"buy_{token_address}_percent_75"
                        ),
                        InlineKeyboardButton(
                            "100%", callback_data=f"buy_{token_address}_percent_100"
                        ),
                    ],
                ]
            )
            await update.message.reply_text(message, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error in buy command: {e}")
            await update.message.reply_text(
                "An error occurred while processing your request. Please try again."
            )

    async def sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(
                    "Please provide the token address.\n" "Usage: /sell <token_address>"
                )
                return

            token_address = context.args[0]
            position = self.db.get_position(update.effective_user.id, token_address)

            if not position:
                await update.message.reply_text(
                    "You don't have any position in this token."
                )
                return

            token_info = self.dex_api.get_token_data(token_address)
            if not token_info:
                await update.message.reply_text(
                    "Unable to fetch token information. Please try again."
                )
                return

            _, price_native, price_usd, market_cap = token_info

            # Calculate current position value
            position_value = position.quantity * price_native
            cost_basis = position.quantity * position.entry_price
            unrealized_pl = position_value - cost_basis
            pl_percent = (unrealized_pl / cost_basis) * 100 if cost_basis > 0 else 0

            # Display position info and sell options
            message = (
                f"Position Information:\n"
                f"Quantity: {position.quantity:.9f}\n"
                f"Entry: {position.entry_price:.9f} SOL\n"
                f"Current: ${price_usd:.4f} ({price_native:.9f} SOL) \n"
                f"Value: {position_value:.3f} SOL\n"
                f"Select amount to sell:"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "25%", callback_data=f"sell_{token_address}_percent_25"
                        ),
                        InlineKeyboardButton(
                            "50%", callback_data=f"sell_{token_address}_percent_50"
                        ),
                        InlineKeyboardButton(
                            "75%", callback_data=f"sell_{token_address}_percent_75"
                        ),
                        InlineKeyboardButton(
                            "100%", callback_data=f"sell_{token_address}_percent_100"
                        ),
                    ]
                ]
            )
            await update.message.reply_text(message, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error in sell command: {e}")
            await update.message.reply_text(
                "An error occurred while processing your request. Please try again."
            )

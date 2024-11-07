from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from db import Database
from services import DexScreenerAPI

AWAITING_CUSTOM_AMOUNT = 1


class CallbackHandlers:
    def __init__(self, db: Database):
        self.db = db
        self.dex_api = DexScreenerAPI()

    async def execute_buy(
        self, telegram_id: int, token_address: str, sol_amount: float
    ) -> Optional[str]:
        """Execute buy operation and return status message."""
        account = self.db.get_account(telegram_id)
        if not account or account.sol_balance < sol_amount:
            return "Insufficient SOL balance for this purchase."

        token_info = self.dex_api.get_token_data(token_address)
        if not token_info:
            return "Unable to fetch token price information."

        _, price_native, price_usd, market_cap = token_info

        # Calculate token quantity based on SOL amount
        token_quantity = sol_amount / price_native

        # Update or create position
        position = self.db.get_position(telegram_id, token_address)
        if position:
            # Update existing position
            total_quantity = position.quantity + token_quantity
            total_cost = (position.quantity * position.entry_price) + sol_amount
            new_entry_price = total_cost / total_quantity
            new_entry_mcap = (
                market_cap * token_quantity + position.quantity * position.entry_mcap
            ) / total_quantity

            self.db.update_position(
                telegram_id=telegram_id,
                token_address=token_address,
                quantity=total_quantity,
                entry_price=new_entry_price,
                entry_mcap=new_entry_mcap,
            )
        else:
            # Create new position
            self.db.create_position(
                telegram_id=telegram_id,
                token_address=token_address,
                quantity=token_quantity,
                entry_price=price_native,
                entry_mcap=market_cap,
            )

        # Update account balance
        account.sol_balance -= sol_amount
        self.db.update_account(account)

        return (
            f"Purchase successful!\n"
            f"Bought: {token_quantity:.9f} tokens\n"
            f"Price: {price_native:.9f} SOL\n"
            f"Total: {sol_amount:.3f} SOL\n"
            f"Market Cap: ${market_cap:,.0f}"
        )

    async def handle_buy_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> Optional[int]:
        query = update.callback_query
        await query.answer()

        # Parse callback data
        _, token_address, buy_type, amount = query.data.split("_")

        # if buy_type == "custom":
        #     context.user_data["pending_buy"] = token_address
        #     await query.message.chat.send_message(
        #         "Please enter the amount of SOL you want to spend:"
        #     )
        #     return AWAITING_CUSTOM_AMOUNT

        account = self.db.get_account(query.from_user.id)
        if not account:
            await query.message.chat.send_message(
                "Account not found. Please use /start first."
            )
            return ConversationHandler.END

        try:
            if buy_type == "fixed":
                sol_amount = float(amount)
            else:  # percent
                percentage = float(amount)
                sol_amount = account.sol_balance * (percentage / 100)

            result = await self.execute_buy(
                query.from_user.id, token_address, sol_amount
            )
            await query.message.chat.send_message(result)

        except ValueError as e:
            await query.message.chat.send_message(
                f"Error processing transaction: {str(e)}"
            )

        return ConversationHandler.END

    # async def handle_custom_amount(
    #     self, update: Update, context: ContextTypes.DEFAULT_TYPE
    # ) -> int:
    #     try:
    #         sol_amount = float(update.message.text)
    #         if sol_amount <= 0:
    #             await update.message.reply_text("Amount must be greater than 0 SOL")
    #             return ConversationHandler.END

    #         token_address = context.user_data.pop("pending_buy", None)
    #         if not token_address:
    #             await update.message.reply_text(
    #                 "No pending buy order found. Please try again."
    #             )
    #             return ConversationHandler.END

    #         result = await self.execute_buy(
    #             update.message.from_user.id, token_address, sol_amount
    #         )
    #         await update.message.reply_text(result)

    #     except ValueError:
    #         await update.message.reply_text(
    #             "Invalid amount. Please enter a valid number."
    #         )

    #     return ConversationHandler.END
    async def execute_sell(
        self, telegram_id: int, token_address: str, percentage: float
    ) -> Optional[str]:
        """Execute sell operation and return status message."""
        position = self.db.get_position(telegram_id, token_address)
        if not position:
            return "No position found for this token."

        token_info = self.dex_api.get_token_data(token_address)
        if not token_info:
            return "Unable to fetch token price information."

        _, price_native, price_usd, market_cap = token_info

        # Calculate sell amount
        sell_quantity = position.quantity * (percentage / 100)
        sol_received = sell_quantity * price_native

        try:
            # Update position
            remaining_quantity = position.quantity - sell_quantity
            if remaining_quantity > 0:
                self.db.update_position(
                    telegram_id=telegram_id,
                    token_address=token_address,
                    quantity=remaining_quantity,
                    entry_price=position.entry_price,
                    entry_mcap=position.entry_mcap,
                )
            else:
                self.db.delete_position(telegram_id, token_address)

            # Update account balance
            account = self.db.get_account(telegram_id)
            account.sol_balance += sol_received
            self.db.update_account(account)

            # Calculate profit/loss
            cost_basis = sell_quantity * position.entry_price
            profit_loss = sol_received - cost_basis
            profit_loss_percent = (
                (profit_loss / cost_basis) * 100 if cost_basis > 0 else 0
            )

            return (
                f"Sell successful!\n"
                f"Sold: {sell_quantity:.9f} tokens ({percentage}%)\n"
                f"Price: {price_native:.9f} SOL\n"
                f"Received: {sol_received:.3f} SOL\n"
                f"P/L: {profit_loss:.3f} SOL ({profit_loss_percent:+.2f}%)"
            )
        except Exception as e:
            print(e)
            return "Error executing sale. Please try again."

    async def handle_sell_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        query = update.callback_query
        await query.answer()

        # Parse callback data
        _, token_address, _, percentage = query.data.split("_")

        try:
            # First update the message to remove keyboard
            await query.message.chat.send_message(
                f"Processing transaction...", reply_markup=None
            )

            # Execute the sell
            result = await self.execute_sell(
                query.from_user.id, token_address, float(percentage)
            )
            await query.message.chat.send_message(result)

        except ValueError as e:
            await query.message.chat.send_message(
                f"Error processing transaction: {str(e)}", reply_markup=None
            )

        return ConversationHandler.END

# database/db.py
from sqlmodel import SQLModel, Session, create_engine, select
from typing import Optional, List
from models import Account, Position
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_url: str = "sqlite:///paper_trading.db"):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        SQLModel.metadata.create_all(self.engine)

    def get_account(self, telegram_id: int) -> Optional[Account]:
        with Session(self.engine) as session:
            statement = select(Account).where(Account.telegram_id == telegram_id)
            return session.exec(statement).first()

    def get_positions(self, telegram_id: int) -> List[Position]:
        with Session(self.engine) as session:
            statement = select(Position).where(Position.telegram_id == telegram_id)
            return session.exec(statement).all()

    def get_position(self, telegram_id: int, token_address: str) -> Optional[Position]:
        """Get a specific position for a user and token."""
        with Session(self.engine) as session:
            statement = select(Position).where(
                Position.telegram_id == telegram_id,
                Position.token_address == token_address,
            )
            return session.exec(statement).first()

    def create_account(self, telegram_id: int, initial_balance: float) -> Account:
        with Session(self.engine) as session:
            account = Account(telegram_id=telegram_id, sol_balance=initial_balance)
            session.add(account)
            session.commit()
            session.refresh(account)
            return account

    def reset_account(self, telegram_id: int, new_balance: float) -> Account:
        with Session(self.engine) as session:
            # Delete all positions
            statement = select(Position).where(Position.telegram_id == telegram_id)
            positions = session.exec(statement).all()
            for position in positions:
                session.delete(position)

            # Update account balance
            account = session.exec(
                select(Account).where(Account.telegram_id == telegram_id)
            ).first()

            if account:
                account.sol_balance = new_balance
            else:
                account = Account(telegram_id=telegram_id, sol_balance=new_balance)
                session.add(account)

            session.commit()
            session.refresh(account)
            return account

    def update_account(self, account: Account) -> None:
        """Update account information."""
        with Session(self.engine) as session:
            session.add(account)
            session.commit()
            session.refresh(account)

    def create_position(
        self,
        telegram_id: int,
        token_address: str,
        quantity: float,
        entry_price: float,
        entry_mcap: float,
    ) -> Position:
        """Create a new position."""
        with Session(self.engine) as session:
            position = Position(
                telegram_id=telegram_id,
                token_address=token_address,
                quantity=quantity,
                entry_price=entry_price,
                entry_mcap=entry_mcap,
            )
            session.add(position)
            session.commit()
            session.refresh(position)
            return position

    def update_position(
        self,
        telegram_id: int,
        token_address: str,
        quantity: float,
        entry_price: float,
        entry_mcap: float,
    ) -> Position:
        """Update an existing position."""
        with Session(self.engine) as session:
            statement = select(Position).where(
                Position.telegram_id == telegram_id,
                Position.token_address == token_address,
            )
            position = session.exec(statement).first()

            if position:
                position.quantity = quantity
                position.entry_price = entry_price
                session.add(position)
                session.commit()
                session.refresh(position)
                return position
            else:
                return self.create_position(
                    telegram_id, token_address, quantity, entry_price, entry_mcap
                )

    def delete_position(self, telegram_id: int, token_address: str) -> bool:
        """Delete a position. Returns True if position was deleted."""
        with Session(self.engine) as session:
            statement = select(Position).where(
                Position.telegram_id == telegram_id,
                Position.token_address == token_address,
            )
            position = session.exec(statement).first()

            if position:
                session.delete(position)
                session.commit()
                return True
            return False

    def upsert_position(
        self, telegram_id: int, token_address: str, quantity: float, entry_price: float
    ) -> Position:
        """Create or update a position based on whether it exists."""
        existing_position = self.get_position(telegram_id, token_address)

        if existing_position:
            # Calculate new average entry price
            total_cost = (
                existing_position.quantity * existing_position.entry_price
            ) + (quantity * entry_price)
            total_quantity = existing_position.quantity + quantity
            new_entry_price = (
                total_cost / total_quantity if total_quantity > 0 else entry_price
            )

            return self.update_position(
                telegram_id=telegram_id,
                token_address=token_address,
                quantity=total_quantity,
                entry_price=new_entry_price,
            )
        else:
            return self.create_position(
                telegram_id=telegram_id,
                token_address=token_address,
                quantity=quantity,
                entry_price=entry_price,
            )

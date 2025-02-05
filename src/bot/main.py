# src/bot/main.py

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from dotenv import load_dotenv
import logging
import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from src.services.firebase import FirebaseService
from src.bot.handlers.admin import AdminHandler
from src.bot.handlers.auth import AuthHandler
from src.bot.handlers.calc import CalculationHandler
from src.bot.keyboards import get_keyboard
from src.bot.states import State

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ArbitrageBot:
    def __init__(self):
        """Initialize the bot with required services and handlers."""
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

        # Initialize services
        self.firebase = FirebaseService()

        # Initialize handlers
        self.admin_handler = AdminHandler(self.firebase)
        self.auth_handler = AuthHandler(self.firebase)
        self.calc_handler = CalculationHandler(self.firebase)

    def create_conversation_handler(self) -> ConversationHandler:
        """Create the main conversation handler."""
        return ConversationHandler(
            entry_points=[
                CommandHandler("start", self.auth_handler.start),
                CommandHandler("admin", self.admin_handler.handle_admin_command),
                MessageHandler(
                    filters.Regex('^(📊 Stats|👥 Users|📢 Broadcast|💎 Premium|📈 Activity|�� Export Users)$'),
                    self.admin_handler.handle_admin_command
                )
            ],
            states={
                State.AWAITING_CONTACT: [
                    MessageHandler(filters.CONTACT, self.auth_handler.handle_contact)
                ],
                State.AWAITING_VERIFICATION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.auth_handler.handle_verification
                    )
                ],
                State.AWAITING_TERMS: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.auth_handler.handle_terms
                    )
                ],
                State.MAIN_MENU: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_main_menu
                    )
                ],
                State.AWAITING_INVESTMENT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_investment
                    )
                ],
                State.AWAITING_CUSTOM_INVESTMENT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_custom_investment
                    )
                ],
                State.AWAITING_SPORT_SELECTION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_sport_selection
                    )
                ],
                State.AWAITING_DRAW_OPTION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_draw_option
                    )
                ],
                State.AWAITING_TAX_CHOICE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_tax_choice
                    )
                ],
                State.AWAITING_TAX_TYPE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_tax_type
                    )
                ],
                State.AWAITING_TAX_PERCENTAGE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_tax_percentage
                    )
                ],
                State.AWAITING_BOOKMAKER_CHOICE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_bookmaker_choice
                    )
                ],
                State.AWAITING_HOME_ODDS: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_home_odds
                    )
                ],
                State.AWAITING_HOME_COMMISSION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_home_commission
                    )
                ],
                State.AWAITING_HOME_DEPOSIT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_home_deposit
                    )
                ],
                State.AWAITING_HOME_WITHDRAWAL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_home_withdrawal
                    )
                ],
                State.AWAITING_AWAY_ODDS: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_away_odds
                    )
                ],
                State.AWAITING_AWAY_COMMISSION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_away_commission
                    )
                ],
                State.AWAITING_AWAY_DEPOSIT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_away_deposit
                    )
                ],
                State.AWAITING_AWAY_WITHDRAWAL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_away_withdrawal
                    )
                ],
                State.AWAITING_DRAW_ODDS: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_draw_odds
                    )
                ],
                State.AWAITING_DRAW_COMMISSION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_draw_commission
                    )
                ],
                State.AWAITING_DRAW_DEPOSIT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_draw_deposit
                    )
                ],
                State.AWAITING_DRAW_WITHDRAWAL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_draw_withdrawal
                    )
                ],
                State.AWAITING_CALCULATION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.calculate_arbitrage
                    )
                ],
                State.AWAITING_ODDS_SPORT_SELECTION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.calc_handler.handle_odds_sport_selection
                    )
                ],
                State.ADMIN_AWAITING_BROADCAST: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.admin_handler.handle_broadcast_message
                    )
                ],
                State.ADMIN_AWAITING_BROADCAST_CONFIRM: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.admin_handler.handle_broadcast_confirm
                    )
                ],
                State.ADMIN_AWAITING_PREMIUM_ACTION: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.admin_handler.handle_premium_action
                    )
                ],
                State.ADMIN_AWAITING_USER_ID: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.admin_handler.handle_premium_user_id
                    )
                ],
                State.ADMIN_AWAITING_PREMIUM_DAYS: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.admin_handler.handle_premium_days
                    )
                ]
            },
            fallbacks=[
                CommandHandler("start", self.auth_handler.start),
                CommandHandler("admin", self.admin_handler.handle_admin_command),
                MessageHandler(
                    filters.Regex('^(📊 Stats|👥 Users|📢 Broadcast|💎 Premium|📈 Activity|�� Export Users)$'),
                    self.admin_handler.handle_admin_command
                )
            ],
            name="main_conversation",
            persistent=False
        )

    def run(self):
        """Run the bot."""
        try:
            # Initialize bot application
            application = Application.builder().token(self.token).build()

            # Add handlers
            application.add_handler(self.create_conversation_handler())
            application.add_handler(
                CommandHandler("admin", self.admin_handler.handle_admin_command)
            )

            # Start polling
            logger.info("Starting bot...")
            application.run_polling()

        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise

def main():
    """Main function to start the bot."""
    try:
        bot = ArbitrageBot()
        bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
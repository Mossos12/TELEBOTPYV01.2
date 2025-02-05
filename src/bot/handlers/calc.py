# src/bot/handlers/calc.py

from telegram import Update
from telegram.ext import ContextTypes
import json
import os
from datetime import datetime
from src.bot.states import State
from src.bot.keyboards import get_keyboard
from src.services.firebase import FirebaseService
from src.services.arbitrage import ArbitrageCalculator
from src.services.odds import OddsService
import logging
from src.utils.validators import InputValidator
from typing import Dict, List
import re
import requests


logger = logging.getLogger(__name__)

# Bookmaker fees directly in the code
BOOKMAKER_FEES = {
    "Bet365": {"commission": 2.5, "deposit": 1.0, "withdrawal": 1.5},
    "William Hill": {"commission": 3.0, "deposit": 0.5, "withdrawal": 2.0},
    "Unibet": {"commission": 2.0, "deposit": 0.0, "withdrawal": 1.8},
    "Betfair": {"commission": 2.0, "deposit": 0.0, "withdrawal": 1.0},
    "888sport": {"commission": 2.2, "deposit": 1.0, "withdrawal": 1.5},
    "SBOBET": {"commission": 1.5, "deposit": 0.0, "withdrawal": 2.5},
    "Pinnacle": {"commission": 0.0, "deposit": 0.0, "withdrawal": 0.0},
    "Dafabet": {"commission": 2.0, "deposit": 0.5, "withdrawal": 1.5},
    "DraftKings": {"commission": 4.0, "deposit": 0.0, "withdrawal": 2.0},
    "FanDuel": {"commission": 3.5, "deposit": 0.0, "withdrawal": 1.8},
    "Caesars": {"commission": 3.0, "deposit": 1.0, "withdrawal": 2.5},
    "Cloudbet": {"commission": 1.0, "deposit": 0.0, "withdrawal": 0.0},
    "Stake": {"commission": 0.0, "deposit": 0.0, "withdrawal": 0.0},
    "SportyBet": {"commission": 3.0, "deposit": 2.0, "withdrawal": 3.0},
    "BetKing": {"commission": 2.5, "deposit": 1.5, "withdrawal": 2.5},
    "Sportsbet": {"commission": 2.0, "deposit": 0.0, "withdrawal": 1.0},
    "Tabcorp": {"commission": 2.2, "deposit": 0.5, "withdrawal": 1.2},
    "Marathon Bet": {"commission": 1.8, "deposit": 0.0, "withdrawal": 1.0},
    "LeoVegas": {"commission": 2.5, "deposit": 0.0, "withdrawal": 1.5}
}

# Sport mappings with emojis
SPORT_MAPPING = {
    '⚽ Football/Soccer': 'soccer_epl',
    '🏀 Basketball': 'basketball_nba',
    '🏈 American Football': 'americanfootball_nfl',
    '⚾ Baseball': 'baseball_mlb',
    '🏒 Hockey': 'icehockey_nhl',
    '🎾 Tennis': 'tennis_atp',
    '🥊 Boxing': 'boxing_boxing',
    '🥋 MMA': 'mma_mixed_martial_arts',
    '🏏 Cricket': 'cricket_test_match'
}

class CalculationHandler:
    def __init__(self, firebase_service):
        self.firebase = firebase_service
        self.odds_service = OddsService()
        self.arbitrage_calc = ArbitrageCalculator()
        self.bookmaker_fees = BOOKMAKER_FEES
        logger.info("CalculationHandler initialized successfully")

    async def handle_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle main menu selections."""
        text = update.message.text
        chat_id = update.effective_chat.id

        if text == '🔍 Search Odds':
            # Check daily limit
            if not await self.firebase.increment_daily_limit(chat_id, 'searches'):
                await update.message.reply_text(
                    "❌ Daily search limit reached!\n"
                    "Upgrade to premium for unlimited searches.",
                    reply_markup=get_keyboard('main_menu')
                )
                return State.MAIN_MENU

            # Show loading message
            await update.message.reply_text("🔄 Fetching latest odds...")

            try:
                # Get and display sports list
                sports = await self.odds_service.get_sports()
                sports_message = "📊 Available Sports and Leagues\n\n"
                
                # Group sports by group
                sport_groups = {}
                for sport in sports:
                    group = sport.get('group', 'OTHER').upper()
                    if group not in sport_groups:
                        sport_groups[group] = []
                    sport_groups[group].append(sport)

                # Format message by group
                for group, group_sports in sorted(sport_groups.items()):
                    if group_sports:  # Only show groups with sports
                        sports_message += f"\n{group}\n"
                        for sport in sorted(group_sports, key=lambda x: x.get('title', '')):
                            sports_message += f"• {sport.get('title', '')}\n"

                sports_message += "\n📈 Usage Information:\n"
                sports_message += "• Updates every 5 minutes\n\n"
                sports_message += "Select a sport or league to see matches:"

                # Store sports list for later use
                context.user_data['available_sports'] = sports

                await update.message.reply_text(sports_message)
                return State.AWAITING_ODDS_SPORT_SELECTION

            except Exception as e:
                logger.error(f"Error fetching sports: {e}")
                await update.message.reply_text(
                    "❌ Error fetching sports data. Please try again.",
                    reply_markup=get_keyboard('main_menu')
                )
                return State.MAIN_MENU

        elif text == '💹 Calculate Arbitrage':
            return await self.start_calculation(update, context)
        elif text == '📊 My History':
            return await self.show_history(update, context)
        elif text == '⚙️ Settings':
            return await self.show_settings(update, context)

        await update.message.reply_text(
            "Please select an option from the menu.",
            reply_markup=get_keyboard('main_menu')
        )
        return State.MAIN_MENU

    async def start_calculation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Start the arbitrage calculation process."""
        chat_id = update.effective_chat.id
        
        # Check daily limit
        if not await self.firebase.increment_daily_limit(chat_id, 'calculations'):
            await update.message.reply_text(
                "❌ Daily calculation limit reached!\n"
                "Upgrade to premium for unlimited calculations.",
                reply_markup=get_keyboard('main_menu')
            )
            return State.MAIN_MENU

        await update.message.reply_text(
            "Enter your investment amount:",
            reply_markup=get_keyboard('investment')
        )
        return State.AWAITING_INVESTMENT

    async def handle_investment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle investment amount input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        # Check if user selected custom amount
        if update.message.text == '💰 Custom Amount':
            await update.message.reply_text(
                "💡 Please enter your custom investment amount:\n"
                "• Must be between $10 and $1,000,000\n"
                "• Example: 750 or 1500.50",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_CUSTOM_INVESTMENT

        # Extract investment amount from predefined keyboard inputs
        input_text = update.message.text.replace('💰 ', '').replace('$', '').replace(',', '').strip()

        # Validate and convert investment amount
        try:
            # Remove any non-numeric characters except decimal point
            cleaned_input = re.sub(r'[^\d.]', '', input_text)
            
            # Convert to float
            amount = float(cleaned_input) if cleaned_input else None
            
            # Validate amount range
            if amount is None or amount < 10 or amount > 1000000:
                raise ValueError("Invalid investment amount")

            # Store the validated investment amount
            context.user_data['investment'] = amount
            
            # Move to sport selection
            await update.message.reply_text(
                "Select a sport:",
                reply_markup=get_keyboard('sports')
            )
            return State.AWAITING_SPORT_SELECTION

        except ValueError:
            await update.message.reply_text(
                "❌ Invalid investment amount! Please choose from preset options or select 'Custom Amount'.",
                reply_markup=get_keyboard('investment')
            )
            return State.AWAITING_INVESTMENT

    async def handle_custom_investment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle custom investment amount input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        # Validate custom investment amount
        validated_amount = InputValidator.validate_investment_amount(update.message.text)
        
        if validated_amount is None:
            await update.message.reply_text(
                "❌ Invalid investment amount!\n"
                "• Must be a number between $10 and $1,000,000\n"
                "• Example: 750 or 1500.50",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_CUSTOM_INVESTMENT

        # Store the validated investment amount
        context.user_data['investment'] = validated_amount
        
        # Move to sport selection
        await update.message.reply_text(
            "Select a sport:",
            reply_markup=get_keyboard('sports')
        )
        return State.AWAITING_SPORT_SELECTION

    async def handle_sport_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle sport selection."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        sport = update.message.text
        context.user_data['sport'] = sport
        
        await update.message.reply_text(
            "Would you like to include draw option?",
            reply_markup=get_keyboard('draw_option')
        )
        return State.AWAITING_DRAW_OPTION

    async def handle_draw_option(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Enhanced draw option handler."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)
        
        if update.message.text == 'ℹ️ What is Draw Option?':
            await update.message.reply_text(
                "🤝 Draw Option Explained\n\n"
                "In some sports like Soccer, matches can end in a draw.\n"
                "• Include Draw: Calculate stakes for Home Win, Away Win, and Draw\n"
                "• Exclude Draw: Calculate only for Home and Away outcomes\n\n"
                "Tip: Including draw provides more comprehensive arbitrage analysis"
            )
            return State.AWAITING_DRAW_OPTION

        include_draw = update.message.text == '✅ Include Draw'
        context.user_data['include_draw'] = include_draw
        
        await update.message.reply_text(
            "Would you like to include tax calculations?",
            reply_markup=get_keyboard('yes_no')
        )
        return State.AWAITING_TAX_CHOICE

    async def handle_tax_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle tax calculation choice."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        if update.message.text == '✅ Yes':
            tax_message = (
                "🏦 Tax Configuration\n"
                "Select your tax type:\n"
                "1️⃣ Tax on Profit\n"
                "- Applied only to winning amount\n"
                "- Calculated after winnings\n"
                "- Common in most regions\n"
                "2️⃣ Tax on Stake\n"
                "- Applied to betting amount\n"
                "- Calculated before placing bet\n"
                "- Varies by jurisdiction\n"
                "Current Selection: None"
            )
            await update.message.reply_text(
                tax_message,
                reply_markup=get_keyboard('tax_type')
            )
            return State.AWAITING_TAX_TYPE

        # If the user does not want to include tax
        context.user_data['include_tax'] = False
        return await self.ask_bookmaker_fees_choice(update, context)

    async def handle_tax_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle tax type selection."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        tax_type = update.message.text
        context.user_data['tax_type'] = tax_type

        # Validate the selected tax type
        if tax_type not in ['💰 From Profit', '💸 From Stake']:
            await update.message.reply_text(
                "❌ Please select a valid tax type from the keyboard options.",
                reply_markup=get_keyboard('tax_type')
            )
            return State.AWAITING_TAX_TYPE

        tax_message = (
            "💱 Enter Tax Percentage\n"
            "Please enter the tax percentage (e.g., 20 for 20%).\n"
            "Current Configuration:\n"
            f"• Type: {tax_type}\n"
            "• Rate: Awaiting input"
        )
        
        await update.message.reply_text(
            tax_message,
            reply_markup=get_keyboard('back_to_main')
        )
        return State.AWAITING_TAX_PERCENTAGE

    async def handle_tax_percentage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle tax percentage input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            tax = float(update.message.text.replace('%', ''))
            if not 0 <= tax <= 100:
                raise ValueError("Tax percentage must be between 0 and 100.")
            
            context.user_data['tax_percentage'] = tax / 100
            return await self.ask_bookmaker_fees_choice(update, context)
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_TAX_PERCENTAGE

    async def handle_bookmaker_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle bookmaker fees choice."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        if update.message.text == '✅ Yes':
            fees_message = "📊 Known Bookmaker Fees:\n\n"
            for bookie, fees in self.bookmaker_fees.items():
                fees_message += (
                    f"{bookie}:\n"
                    f"• Commission: {fees['commission']}%\n"
                    f"• Deposit: {fees['deposit']}%\n"
                    f"• Withdrawal: {fees['withdrawal']}%\n\n"
                )
            await update.message.reply_text(fees_message)

        explanation = (
            "📋 Home vs Away Team Explanation:\n\n"
            "🏠 Home Team means:\n"
            "- The team playing in their stadium\n"
            "- Usually listed first in fixtures\n"
            "- Often has home advantage\n\n"
            "✈️ Away Team means:\n"
            "- The team playing at opponent's stadium\n"
            "- Usually listed second in fixtures\n"
            "- Playing as visitors\n\n"
            "❗ Important:\n"
            "- Always check which team is home/away\n"
            "- Odds can vary significantly\n"
            "- Some sports may be at neutral venues\n\n"
            "Please enter the Home Team odds first:"
        )
        
        context.user_data['home_odds_explanation_shown'] = True
        await update.message.reply_text(explanation)
        return State.AWAITING_HOME_ODDS

    async def handle_home_odds(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle home odds input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        # First time showing the explanation
        if not context.user_data.get('home_odds_explanation_shown'):
            explanation = (
                "📋 Home vs Away Team Explanation:\n\n"
                "🏠 Home Team means:\n"
                "- The team playing in their stadium\n"
                "- Usually listed first in fixtures\n"
                "- Often has home advantage\n\n"
                "✈️ Away Team means:\n"
                "- The team playing at opponent's stadium\n"
                "- Usually listed second in fixtures\n"
                "- Playing as visitors\n\n"
                "❗ Important:\n"
                "- Always check which team is home/away\n"
                "- Odds can vary significantly\n"
                "- Some sports may be at neutral venues\n\n"
                "Please enter the Home Team odds first:"
            )
            context.user_data['home_odds_explanation_shown'] = True
            await update.message.reply_text(explanation)
            return State.AWAITING_HOME_ODDS

        # Handle odds input
        try:
            odds = float(update.message.text)
            if odds <= 1:
                raise ValueError("Odds must be greater than 1.")
            
            context.user_data['home_odds'] = odds
            await update.message.reply_text(
                "🏠 Home Bookmaker Fees\n"
                "Please enter COMMISSION percentage:\n"
                "(e.g., 2 for 2% of stake)"
            )
            return State.AWAITING_HOME_COMMISSION
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter valid odds (greater than 1)."
            )
            return State.AWAITING_HOME_ODDS

    async def handle_home_commission(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle home bookmaker commission."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            commission = float(update.message.text.replace('%', ''))
            if not 0 <= commission <= 100:
                raise ValueError()
            
            context.user_data['home_commission'] = commission / 100
            await update.message.reply_text(
                "🏠 Home Bookmaker Fees\n"
                "Please enter Deposit fee percentage:\n"
                "(e.g., 2 for 2% of stake)",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_HOME_DEPOSIT
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_HOME_COMMISSION

    async def handle_home_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle home bookmaker deposit fee."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            deposit = float(update.message.text.replace('%', ''))
            if not 0 <= deposit <= 100:
                raise ValueError()
            
            context.user_data['home_deposit'] = deposit / 100
            await update.message.reply_text(
                "🏠 Home Bookmaker Fees\n"
                "Please enter Withdrawal fee percentage:\n"
                "(e.g., 2 for 2% of stake)",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_HOME_WITHDRAWAL
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_HOME_DEPOSIT

    async def handle_home_withdrawal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle home bookmaker withdrawal fee."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            withdrawal = float(update.message.text.replace('%', ''))
            if not 0 <= withdrawal <= 100:
                raise ValueError("Withdrawal percentage must be between 0 and 100.")
            
            context.user_data['home_withdrawal'] = withdrawal / 100
            
            # Check if draw option was selected
            if context.user_data.get('include_draw', False):
                await update.message.reply_text(
                    "🤝 Please enter the DRAW odds:",
                    reply_markup=get_keyboard('back_to_main')
                )
                return State.AWAITING_DRAW_ODDS
            else:
                # If no draw option, proceed to away odds
                await update.message.reply_text(
                    "✈️ Please enter the AWAY team odds:",
                    reply_markup=get_keyboard('back_to_main')
                )
                return State.AWAITING_AWAY_ODDS
                
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_HOME_WITHDRAWAL

    async def handle_away_odds(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle away odds input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            odds = float(update.message.text)
            if odds <= 1:
                raise ValueError("Odds must be greater than 1.")
            
            context.user_data['away_odds'] = odds
            await update.message.reply_text(
                "✈️ *Away Bookmaker Fees*\n"
                "Please enter COMMISSION percentage:",
                parse_mode='Markdown'
            )
            return State.AWAITING_AWAY_COMMISSION
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter valid odds (greater than 1).",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_AWAY_ODDS

    async def handle_away_commission(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle away bookmaker commission."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            commission = float(update.message.text.replace('%', ''))
            if not 0 <= commission <= 100:
                raise ValueError()
            
            context.user_data['away_commission'] = commission / 100
            await update.message.reply_text(
                "✈️ *Away Bookmaker Deposit Fee*\n"
                "Enter DEPOSIT fee percentage:",
                parse_mode='Markdown'
            )
            return State.AWAITING_AWAY_DEPOSIT
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_AWAY_COMMISSION

    async def handle_away_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle away bookmaker deposit fee."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            deposit = float(update.message.text.replace('%', ''))
            if not 0 <= deposit <= 100:
                raise ValueError()
            
            context.user_data['away_deposit'] = deposit / 100
            await update.message.reply_text(
                "✈️ *Away Bookmaker Withdrawal Fee*\n"
                "Enter WITHDRAWAL fee percentage:",
                parse_mode='Markdown'
            )
            return State.AWAITING_AWAY_WITHDRAWAL
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_AWAY_DEPOSIT

    async def handle_away_withdrawal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle away bookmaker withdrawal fee."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            withdrawal = float(update.message.text.replace('%', ''))
            if not 0 <= withdrawal <= 100:
                raise ValueError("Withdrawal percentage must be between 0 and 100.")
            
            context.user_data['away_withdrawal'] = withdrawal / 100
            
            # Once all fees are collected, proceed to calculation
            return await self.calculate_arbitrage(update, context)
                
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_AWAY_WITHDRAWAL

    async def handle_draw_odds(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle draw odds input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            odds = float(update.message.text)
            if odds <= 1:
                raise ValueError("Odds must be greater than 1.")
            
            context.user_data['draw_odds'] = odds
            await update.message.reply_text(
                "🤝 *Draw Bookmaker Fees*\n"
                "Please enter COMMISSION percentage:",
                parse_mode='Markdown'
            )
            return State.AWAITING_DRAW_COMMISSION
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter valid odds (greater than 1).",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_DRAW_ODDS

    async def handle_draw_commission(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle draw bookmaker commission."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            commission = float(update.message.text.replace('%', ''))
            if not 0 <= commission <= 100:
                raise ValueError()
            
            context.user_data['draw_commission'] = commission / 100
            await update.message.reply_text(
                "🤝 *Draw Bookmaker Deposit Fee*\n"
                "Enter DEPOSIT fee percentage:",
                parse_mode='Markdown'
            )
            return State.AWAITING_DRAW_DEPOSIT
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_DRAW_COMMISSION

    async def handle_draw_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle draw bookmaker deposit fee."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            deposit = float(update.message.text.replace('%', ''))
            if not 0 <= deposit <= 100:
                raise ValueError()
            
            context.user_data['draw_deposit'] = deposit / 100
            await update.message.reply_text(
                "🤝 *Draw Bookmaker Withdrawal Fee*\n"
                "Enter WITHDRAWAL fee percentage:",
                parse_mode='Markdown'
            )
            return State.AWAITING_DRAW_WITHDRAWAL
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_DRAW_DEPOSIT

    async def handle_draw_withdrawal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle draw bookmaker withdrawal fee."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            withdrawal = float(update.message.text.replace('%', ''))
            if not 0 <= withdrawal <= 100:
                raise ValueError("Withdrawal percentage must be between 0 and 100.")
            
            context.user_data['draw_withdrawal'] = withdrawal / 100
            
            # After draw fees, proceed to away odds
            await update.message.reply_text(
                "✈️ Please enter the AWAY team odds:",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_AWAY_ODDS
                
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid percentage between 0 and 100.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_DRAW_WITHDRAWAL

    async def calculate_arbitrage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Enhanced arbitrage calculation with improved user experience and error handling."""
        try:
            # Comprehensive data validation
            data = context.user_data
            required_keys = [
                'investment', 
                'home_odds', 'home_commission', 'home_deposit', 'home_withdrawal',
                'away_odds', 'away_commission', 'away_deposit', 'away_withdrawal'
            ]
            
            # Check for missing keys
            missing_keys = [key for key in required_keys if key not in data]
            if missing_keys:
                logger.error(f"Missing calculation data: {missing_keys}")
                await update.message.reply_text(
                    "❌ Incomplete calculation data. Please restart the arbitrage calculation.\n\n"
                    "Missing information for:\n" + 
                    "\n".join(f"• {key.replace('_', ' ').title()}" for key in missing_keys),
                    reply_markup=get_keyboard('main_menu')
                )
                return State.MAIN_MENU

            # Prepare odds data in the enhanced format
            odds_data = {
                'home': {
                    'odds': float(data['home_odds']),
                    'commission': float(data.get('home_commission', 0)),
                    'deposit': float(data.get('home_deposit', 0)),
                    'withdrawal': float(data.get('home_withdrawal', 0))
                },
                'away': {
                    'odds': float(data['away_odds']),
                    'commission': float(data.get('away_commission', 0)),
                    'deposit': float(data.get('away_deposit', 0)),
                    'withdrawal': float(data.get('away_withdrawal', 0))
                }
            }
            
            # Add draw bet data if applicable
            if data.get('include_draw'):
                draw_keys = ['draw_odds', 'draw_commission', 'draw_deposit', 'draw_withdrawal']
                if all(key in data for key in draw_keys):
                    odds_data['draw'] = {
                        'odds': float(data['draw_odds']),
                        'commission': float(data.get('draw_commission', 0)),
                        'deposit': float(data.get('draw_deposit', 0)),
                        'withdrawal': float(data.get('draw_withdrawal', 0))
                    }
                else:
                    logger.warning("Draw option selected but incomplete draw data")
                    await update.message.reply_text(
                        "❌ Incomplete draw data. Please restart the arbitrage calculation.",
                        reply_markup=get_keyboard('main_menu')
                    )
                    return State.MAIN_MENU

            # Prepare tax information
            tax_rate = data.get('tax_percentage', 0)
            tax_type = data.get('tax_type', 'profit')
            investment = data['investment']
            
            # Perform comprehensive arbitrage calculation
            result = self.arbitrage_calc.calculate(
                investment=investment,
                odds_data=odds_data,
                tax_rate=tax_rate,
                tax_type=tax_type
            )
            
            # Enhanced result formatting
            message_parts = [
                "📊 *Comprehensive Arbitrage Analysis* 🧮\n\n"
                f"💰 *Total Investment*: ${investment:.2f}\n"
            ]
            
            # Profit and ROI Section
            message_parts.extend([
                f"📈 *ROI*: {result.get('roi', 0):.2f}%\n",
                f"💵 *Expected Profit*: ${result.get('profit', 0):.2f}\n\n"
            ])
            
            # Tax Handling
            if data.get('include_tax', False):
                tax_amount = result.get('tax_amount', 0)
                message_parts.extend([
                    f"💸 *Tax Details*:\n"
                    f"• Tax Rate: {tax_rate * 100:.2f}%\n"
                    f"• Tax Amount: ${tax_amount:.2f}\n"
                    f"• Net Profit After Tax: ${result.get('net_profit', 0):.2f}\n\n"
                ])
            
            # Detailed Stakes
            message_parts.append("🎲 *Recommended Stakes*:\n")
            stakes = result.get('stakes', {})
            for team, stake_info in stakes.items():
                message_parts.append(
                    f"• *{team.replace('_', ' ').title()}*:\n"
                    f"  💰 Stake: ${stake_info.get('stake', 0):.2f}\n"
                    f"  📊 Odds: {stake_info.get('odds', 0):.2f}\n"
                )
            
            # Comprehensive Disclaimer
            message_parts.extend([
                "\n⚠️ *Important Disclaimer*:\n"
                "• Calculations are theoretical\n"
                "• Actual betting involves additional fees\n"
                "• Odds change rapidly\n"
                "• Always verify current market conditions\n"
                "• Betting carries financial risks\n"
            ])
            
            # Send the formatted message
            await update.message.reply_text(
                ''.join(message_parts),
                parse_mode='Markdown',
                reply_markup=get_keyboard('main_menu')
            )
            
            # Optional: Save calculation to Firebase for history
            await self.firebase.save_calculation(
                update.effective_chat.id,
                {
                    'timestamp': datetime.now().isoformat(),
                    'investment': investment,
                    'odds_data': odds_data,
                    'result': result,
                    'sport': data.get('sport'),
                    'include_draw': data.get('include_draw', False),
                    'include_tax': data.get('include_tax', False)
                }
            )
            
            return State.MAIN_MENU
            
        except ValueError as ve:
            logger.error(f"Arbitrage calculation error: {ve}")
            await update.message.reply_text(
                "❌ Calculation Error\n\n"
                "• Please ensure all odds are greater than 1\n"
                "• Verify all input values are correct\n"
                "• Check for a potential arbitrage opportunity\n"
                "• Restart the calculation if needed",
                reply_markup=get_keyboard('main_menu')
            )
            return State.MAIN_MENU
        except Exception as e:
            logger.error(f"Unexpected calculation error: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ An unexpected error occurred.\n\n"
                "Possible reasons:\n"
                "• Incomplete calculation data\n"
                "• Technical issue\n\n"
                "Please restart the arbitrage calculation.",
                reply_markup=get_keyboard('main_menu')
            )
            return State.MAIN_MENU

    async def back_to_menu(self, update: Update) -> State:
        """Helper to return to main menu."""
        await update.message.reply_text(
            "Returning to main menu.",
            reply_markup=get_keyboard('main_menu')
        )
        return State.MAIN_MENU

    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Show settings menu."""
        # Implementation for settings
        pass

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Show calculation history."""
        chat_id = update.effective_chat.id
        calculations = await self.firebase.get_user_calculations(chat_id)
        
        if not calculations:
            await update.message.reply_text(
                "No calculation history found.",
                reply_markup=get_keyboard('main_menu')
            )
            return State.MAIN_MENU
        
        message = "📊 Recent Calculations:\n\n"
        for calc in calculations[:10]:  # Show last 10 calculations
            message += (
                f"📅 Date: {calc['timestamp']}\n"
                f"🎯 Sport: {calc['sport']}\n"
                f"💰 Investment: ${calc['investment']:,.2f}\n"
                f"📈 ROI: {calc['result']['roi']:.2f}%\n"
                f"💵 Profit: ${calc['result']['profit']:,.2f}\n"
                f"{'🤝 Draw Included' if calc.get('include_draw') else '🚫 No Draw'}\n"
                f"{'💸 Tax Applied' if calc.get('include_tax') else '🚫 No Tax'}\n"
                "-------------------\n"
            )
        
        await update.message.reply_text(
            message,
            reply_markup=get_keyboard('main_menu')
        )
        return State.MAIN_MENU

    async def start_odds_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle odds search."""
        chat_id = update.effective_chat.id
        
        # Check premium status first
        is_premium = await self.firebase.check_premium_status(chat_id)
        
        # If not premium, check daily limit
        if not is_premium:
            if not await self.firebase.increment_daily_limit(chat_id, 'searches'):
                await update.message.reply_text(
                    "❌ Daily search limit reached!\n"
                    "Upgrade to premium for unlimited searches.",
                    reply_markup=get_keyboard('main_menu')
                )
                return State.MAIN_MENU

        # Show loading message
        await update.message.reply_text("🔄 Fetching latest odds...")

        try:
            # Fetch sports list
            sports = await self.odds_service.get_sports()
            sports_message = "📊 Available Sports and Leagues\n\n"

            # Group sports by category
            categories = {}
            for sport in sports:
                category = sport['category']
                if category not in categories:
                    categories[category] = []
                categories[category].append(sport)

            # Format message by category
            for category, sport_list in sorted(categories.items()):
                sports_message += f"\n{category.upper()}\n"
                for sport in sorted(sport_list, key=lambda x: x['title']):
                    sports_message += f"• {sport['title']}\n"

            sports_message += (
                "\n📈 Usage Information:\n"
                "• Updates every 5 minutes\n\n"
                "Select a sport or league to see matches:"
            )

            # Store sports data and send message
            context.user_data['sports_list'] = sports
            await update.message.reply_text(
                sports_message,
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_SPORT_SELECTION

        except Exception as e:
            logger.error(f"Error fetching sports: {e}")
            await update.message.reply_text(
                "❌ Error fetching odds data. Please try again later.",
                reply_markup=get_keyboard('main_menu')
            )
            return State.MAIN_MENU

    async def handle_odds_sport_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle sport selection for odds search."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            sport = update.message.text.strip()
            await update.message.reply_text(f"🔄 Fetching {sport} matches...")
            logger.info(f"Selected Sport: {sport}")

            # Comprehensive mapping of display names to API keys
            SPORT_DISPLAY_TO_API_KEY = {
                # Soccer (Football)
                'UEFA Europa League': 'soccer_uefa_europa_league',
                'Europa League': 'soccer_uefa_europa_league',
                'UEFA Europa Conference League': 'soccer_uefa_europa_conference_league',
                'Conference League': 'soccer_uefa_europa_conference_league',
                'UEFA Champions League': 'soccer_uefa_champs_league',
                'Champions League': 'soccer_uefa_champs_league',
                
                # England
                'Premier League': 'soccer_epl',
                'EPL': 'soccer_epl',
                'Championship': 'soccer_efl_champ',
                'League 1': 'soccer_england_league1',
                'League 2': 'soccer_england_league2',
                'EFL Cup': 'soccer_england_efl_cup',
                'FA Cup': 'soccer_fa_cup',
                
                # Germany
                'Bundesliga': 'soccer_germany_bundesliga',
                'Bundesliga 2': 'soccer_germany_bundesliga2',
                '3. Liga': 'soccer_germany_liga3',
                
                # Spain
                'La Liga': 'soccer_spain_la_liga',
                'La Liga 2': 'soccer_spain_segunda_division',
                
                # Italy
                'Serie A': 'soccer_italy_serie_a',
                'Serie B': 'soccer_italy_serie_b',
                
                # France
                'Ligue 1': 'soccer_france_ligue_one',
                'Ligue 2': 'soccer_france_ligue_two',
                
                # Other Countries
                'Dutch Eredivisie': 'soccer_netherlands_eredivisie',
                'Portuguese Primeira Liga': 'soccer_portugal_primeira_liga',
                'Scottish Premiership': 'soccer_spl',
                'Danish Superliga': 'soccer_denmark_superliga',
                
                # Catch-all for soccer
                'Football/Soccer': [
                    'soccer_epl', 'soccer_uefa_champs_league', 
                    'soccer_germany_bundesliga', 'soccer_spain_la_liga'
                ]
            }

            # Function to find the most likely sport key
            def find_sport_key(sport_name):
                # Exact match in display to API key mapping
                if sport_name in SPORT_DISPLAY_TO_API_KEY:
                    return SPORT_DISPLAY_TO_API_KEY[sport_name]
                
                # Case-insensitive partial match
                for display_name, api_key in SPORT_DISPLAY_TO_API_KEY.items():
                    if sport_name.lower() in display_name.lower():
                        return api_key
                
                # Check available sports
                available_sports = context.user_data.get('available_sports', [])
                for s in available_sports:
                    if (sport_name.lower() in s.get('title', '').lower() or 
                        sport_name.lower() in s.get('description', '').lower()):
                        return s.get('key')
                
                return None

            # Find the sport key
            sport_key = find_sport_key(sport)

            # Validate sport key
            if not sport_key:
                logger.warning(f"No matching sport key found for: {sport}")
                await update.message.reply_text(
                    f"❌ Could not find matches for '{sport}'.\n"
                    "Please choose a sport from the list or try a different name.",
                    reply_markup=get_keyboard('back_to_main')
                )
                return State.AWAITING_ODDS_SPORT_SELECTION

            logger.info(f"Matched Sport Key: {sport_key}")

            # Ensure sport_key is a list
            if isinstance(sport_key, str):
                sport_key = [sport_key]

            # Fetch matches
            all_matches = []
            for key in sport_key:
                matches = await self.odds_service.get_odds(key)
                all_matches.extend(matches)
            
            if not all_matches:
                await update.message.reply_text(
                    f"No matches found for {sport}.",
                    reply_markup=get_keyboard('back_to_main')
                )
                return State.AWAITING_ODDS_SPORT_SELECTION

            # Format and send matches
            formatted_message = self.format_matches_message(all_matches)
            
            # Send message in chunks if needed
            if len(formatted_message) > 4096:
                for i in range(0, len(formatted_message), 4096):
                    await update.message.reply_text(
                        formatted_message[i:i+4096],
                        reply_markup=get_keyboard('back_to_main')
                    )
            else:
                await update.message.reply_text(
                    formatted_message,
                    reply_markup=get_keyboard('back_to_main')
                )

            return State.AWAITING_ODDS_SPORT_SELECTION

        except Exception as e:
            logger.error(f"Comprehensive error in sport selection: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Error fetching matches. Please try again.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_ODDS_SPORT_SELECTION

    def format_matches_message(self, matches):
        """Format matches with detailed odds and quick arbitrage info."""
        message_parts = []
        
        # Group matches by date
        matches_by_date = {}
        for match in matches:
            date = match.get('commence_date', 'Unknown Date')
            if date not in matches_by_date:
                matches_by_date[date] = []
            matches_by_date[date].append(match)
        
        # Process matches
        for date, date_matches in sorted(matches_by_date.items()):
            message_parts.append(f"📅 {date}\n")
            
            for i, match in enumerate(date_matches, 1):
                # Match header with extra spacing
                match_message = (
                    f"{i}. {match['home_team']} vs {match['away_team']}\n\n"
                    f"⏰ {match['commence_time']}\n"
                    f"🏠 Home: {match['home_odds']} ({match['home_bookie']})\n"
                    f"✈️ Away: {match['away_odds']} ({match['away_bookie']})\n"
                )
                
                # Add draw odds if available
                if match.get('draw_odds'):
                    match_message += f"🤝 Draw: {match['draw_odds']} ({match['draw_bookie']})\n\n"
                
                # Calculate probabilities
                home_prob = 1 / match['home_odds'] * 100
                away_prob = 1 / match['away_odds'] * 100
                total_prob = home_prob + away_prob
                
                # Add probabilities section with spacing
                match_message += "📊 Probabilities:\n\n"
                match_message += f"🏠 Home: {home_prob:.2f}%\n"
                match_message += f"✈️ Away: {away_prob:.2f}%\n"
                
                # Add draw probability if draw odds exist
                if match.get('draw_odds'):
                    draw_prob = 1 / match['draw_odds'] * 100
                    total_prob += draw_prob
                    match_message += f"🤝 Draw: {draw_prob:.2f}%\n\n"
                
                # Total market probability and margin with spacing
                match_message += f"📈 Total Market Probability: {total_prob:.2f}%\n"
                match_message += f"🎲 Margin: {total_prob - 100:.2f}%\n\n"
                
                # Arbitrage opportunity indicator
                if total_prob < 100:
                    match_message += "💸🚨✅ Potential Arbitrage Opportunity!\n\n"
                else:
                    match_message += "🚫 No Clear Arbitrage Opportunity\n\n"
                
                message_parts.append(match_message)
            
            # Add an extra line between dates
            message_parts.append("\n")
        
        # Add disclaimer with extra spacing
        message_parts.append("⚠️ Important Notes:\n\n")
        message_parts.append("• Calculations are simplified\n")
        message_parts.append("• Does NOT account for fees or commissions\n")
        message_parts.append("• Odds update frequently\n")
        message_parts.append("• Always verify before betting\n")
        
        return ''.join(message_parts)

    async def generate_detailed_arbitrage_analysis(self, odds_data: Dict, investment: float) -> str:
        """
        Generate a comprehensive arbitrage analysis UI 
        with detailed explanations and market insights.
        """
        try:
            # Validate input data
            if not all(key in odds_data for key in ['home', 'away', 'draw']):
                raise ValueError("Incomplete odds data")

            # Calculate implied probabilities
            def calculate_implied_prob(odds):
                return 1 / max(float(odds), 1.01) * 100 if odds > 0 else 0

            # Extract odds
            home_odds = float(odds_data['home']['odds'])
            away_odds = float(odds_data['away']['odds'])
            draw_odds = float(odds_data['draw']['odds'])

            # Calculate individual and total probabilities
            home_prob = calculate_implied_prob(home_odds)
            away_prob = calculate_implied_prob(away_odds)
            draw_prob = calculate_implied_prob(draw_odds)
            total_prob = home_prob + away_prob + draw_prob

            # Determine arbitrage opportunity
            arbitrage_opportunity = total_prob < 100

            # Generate detailed message
            message_parts = [
                "📊 Comprehensive Market Analysis \n\n"
            ]

            # Probability Breakdown
            message_parts.append(
                "📈 Probability Breakdown:\n"
                f"🏠 Home Team: {home_prob:.2f}%\n"
                f"✈️ Away Team: {away_prob:.2f}%\n"
                f"🤝 Draw: {draw_prob:.2f}%\n\n"
            )

            # Market Probability Analysis
            message_parts.append(
                "📊 Market Probability Assessment:\n"
                f"• Combined Market Probability: {total_prob:.2f}%\n"
                f"• Market Margin: {total_prob - 100:.2f}%\n"
                f"• Arbitrage Potential: {'✅ Possible' if arbitrage_opportunity else '❌ Not Possible'}\n\n"
            )

            # Detailed Explanations
            if arbitrage_opportunity:
                # Calculate potential arbitrage stakes
                total_implied_prob = sum(1/odds for odds in [home_odds, away_odds, draw_odds])
                
                stakes = {
                    'home': (investment * (1/home_odds) / total_implied_prob),
                    'away': (investment * (1/away_odds) / total_implied_prob),
                    'draw': (investment * (1/draw_odds) / total_implied_prob)
                }

                potential_returns = {
                    'home': stakes['home'] * home_odds,
                    'away': stakes['away'] * away_odds,
                    'draw': stakes['draw'] * draw_odds
                }

                min_return = min(potential_returns.values())
                profit = min_return - investment
                roi = (profit / investment) * 100

                message_parts.extend([
                    "💡 Arbitrage Opportunity Detected!\n\n"
                    "🎲 Recommended Stakes:\n"
                    f"🏠 Home Team: ${stakes['home']:.2f}\n"
                    f"✈️ Away Team: ${stakes['away']:.2f}\n"
                    f"🤝 Draw: ${stakes['draw']:.2f}\n\n"
                    
                    "💰 Potential Returns:\n"
                    f"🏠 Home Team Return: ${potential_returns['home']:.2f}\n"
                    f"✈️ Away Team Return: ${potential_returns['away']:.2f}\n"
                    f"🤝 Draw Return: ${potential_returns['draw']:.2f}\n\n"
                    
                    f"💵 Estimated Profit: ${profit:.2f}\n"
                    f"📈 Estimated ROI: {roi:.2f}%\n\n"
                ])
            else:
                message_parts.extend([
                    "❌ No Arbitrage Opportunity\n\n"
                    "🔍 Why No Arbitrage?\n"
                    "• Total market probability exceeds 100%\n"
                    "• Bookmakers have built-in margin\n"
                    "• Current odds do not present a risk-free opportunity\n\n"
                ])

            # Comprehensive Explanations
            message_parts.append(
                "📘 Understanding the Analysis:\n"
                "• Implied Probability: Converts odds to percentage chance\n"
                "• Market Margin: Bookmaker's built-in profit percentage\n"
                "• Arbitrage: Exploiting price differences across markets\n\n"
                
                "⚠️ Important Disclaimer:\n"
                "• Calculations are theoretical\n"
                "• Actual betting involves additional fees\n"
                "• Odds change rapidly\n"
                "• Always verify current market conditions\n"
                "• Betting carries financial risks\n"
            )

            return ''.join(message_parts)

        except Exception as e:
            logger.error(f"Arbitrage analysis error: {e}")
            return (
                "❌ Analysis Error\n\n"
                "Unable to generate detailed arbitrage analysis. "
                "Please check your input and try again."
            )

    async def get_sports(self) -> List[Dict]:
        """Get list of in-season sports."""
        try:
            # Check cache
            cache_key = 'sports'
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

            response = requests.get(
                f'{self.base_url}/sports',
                params={
                    'api_key': self.api_key
                }
            )

            if response.status_code != 200:
                logger.error(
                    f'Failed to get sports: status_code {response.status_code}, '
                    f'response body {response.text}'
                )
                return []

            # Update quota
            self._update_quota(response)
            
            # Process sports data
            raw_sports = response.json()
            
            # Group sports by their keys to determine category
            processed_sports = []
            for sport in raw_sports:
                if sport.get('active'):
                    # Determine group from key
                    key = sport.get('key', '').lower()
                    if 'soccer' in key:
                        group = 'SOCCER'
                    elif 'basketball' in key:
                        group = 'BASKETBALL'
                    elif 'football' in key or 'nfl' in key or 'ncaaf' in key:
                        group = 'AMERICAN FOOTBALL'
                    elif 'baseball' in key:
                        group = 'BASEBALL'
                    elif 'hockey' in key or 'nhl' in key:
                        group = 'ICE HOCKEY'
                    elif 'mma' in key or 'ufc' in key:
                        group = 'MIXED MARTIAL ARTS'
                    elif 'boxing' in key:
                        group = 'BOXING'
                    elif 'cricket' in key:
                        group = 'CRICKET'
                    elif 'rugby' in key:
                        group = 'RUGBY'
                    elif 'tennis' in key:
                        group = 'TENNIS'
                    elif 'golf' in key:
                        group = 'GOLF'
                    else:
                        group = 'OTHER SPORTS'
                    
                    processed_sports.append({
                        'key': sport.get('key'),
                        'title': sport.get('title'),
                        'group': group,
                        'description': sport.get('description', ''),
                        'active': True
                    })
            
            # Sort by group and title
            processed_sports.sort(key=lambda x: (x['group'], x['title']))

            return processed_sports

        except Exception as e:
            logger.error(f"Error fetching sports: {e}")
            return []  # Return an empty list or handle the error as needed

    async def ask_bookmaker_fees_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Ask if user wants to see known bookmaker fees."""
        await update.message.reply_text(
            "Would you like to see known bookmaker fees?",
            reply_markup=get_keyboard('yes_no')  # Keyboard with 'Yes' and 'No' options
        )
        return State.AWAITING_BOOKMAKER_CHOICE  # Transition to the state waiting for user's choice
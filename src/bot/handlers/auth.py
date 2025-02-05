# src/bot/handlers/auth.py

from telegram import Update
from telegram.ext import ContextTypes
import random
import string
import logging
from src.bot.states import State
from src.bot.keyboards import get_keyboard

logger = logging.getLogger(__name__)

class AuthHandler:
    def __init__(self, firebase_service):
        self.firebase = firebase_service

    def generate_verification_code(self) -> str:
        """Generate a 6-digit verification code."""
        return ''.join(random.choices(string.digits, k=6))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle /start command."""
        chat_id = update.effective_chat.id
        user = await self.firebase.get_user(chat_id)

        if not user:
            # New user - create profile and start verification
            await self.firebase.create_user(chat_id)
            await update.message.reply_text(
                "Welcome to the Sports Arbitrage Bot! 🎯\n\n"
                "To get started, we need to verify your phone number.",
                reply_markup=get_keyboard('contact_request')
            )
            return State.AWAITING_CONTACT

        if not user.get('verification_status'):
            # Unverified user
            await update.message.reply_text(
                "Please complete phone verification to continue.",
                reply_markup=get_keyboard('contact_request')
            )
            return State.AWAITING_CONTACT

        if not user.get('terms_accepted'):
            # Unverified user
            await update.message.reply_text(
                "Please accept the terms to continue.",
                reply_markup=get_keyboard('terms')
            )
            return State.AWAITING_TERMS

        # Existing verified user
        await update.message.reply_text(
            "Welcome back to Sports Arbitrage Bot! 🎯\n"
            "What would you like to do?",
            reply_markup=get_keyboard('main_menu')
        )
        return State.MAIN_MENU

    async def handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle phone number verification."""
        if not update.message.contact:
            await update.message.reply_text(
                "Please share your contact using the button provided.",
                reply_markup=get_keyboard('contact_request')
            )
            return State.AWAITING_CONTACT

        chat_id = update.effective_chat.id
        phone_number = update.message.contact.phone_number

        # Generate and store verification code
        verification_code = self.generate_verification_code()
        context.user_data['verification_code'] = verification_code
        context.user_data['phone_number'] = phone_number

        # Update user in Firebase
        await self.firebase.update_user(chat_id, {
            'phone_number': phone_number,
            'verification_code': verification_code
        })

        # In production, send this via SMS
        await update.message.reply_text(
            f"📱 A verification code has been sent to {phone_number}\n"
            f"For testing purposes, your code is: {verification_code}",
            reply_markup=get_keyboard('back_to_main')
        )
        return State.AWAITING_VERIFICATION

    async def handle_verification(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle verification code validation."""
        entered_code = update.message.text
        stored_code = context.user_data.get('verification_code')
        
        if entered_code != stored_code:
            await update.message.reply_text(
                "❌ Invalid verification code. Please try again.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.AWAITING_VERIFICATION

        chat_id = update.effective_chat.id
        await self.firebase.update_user(chat_id, {
            'verification_status': True,
            'verification_code': None  # Clear the code
        })

        # Show terms and conditions
        terms_text = (
            "📜 Terms and Conditions:\n\n"
            "1. This bot is for informational purposes only\n"
            "2. Users must be 18+ years old\n"
            "3. We are not responsible for any losses\n"
            "4. Premium features require subscription\n"
            "5. Daily limits apply to free users\n\n"
            "Please accept these terms to continue."
        )
        
        await update.message.reply_text(
            terms_text,
            reply_markup=get_keyboard('terms')
        )
        return State.AWAITING_TERMS

    async def handle_terms(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle terms acceptance."""
        response = update.message.text

        if response != "✅ Accept Terms":
            await update.message.reply_text(
                "You must accept the terms to use this bot.",
                reply_markup=get_keyboard('terms')
            )
            return State.AWAITING_TERMS

        chat_id = update.effective_chat.id
        await self.firebase.update_user(chat_id, {
            'terms_accepted': True
        })

        welcome_msg = (
            "🎉 Welcome to Sports Arbitrage Bot!\n\n"
            "You can now:\n"
            "💹 Calculate arbitrage opportunities\n"
            "🔍 Search for the best odds\n"
            "📊 View your calculation history\n"
            "⚙️ Adjust your settings\n\n"
            "Get started by selecting an option below!"
        )

        await update.message.reply_text(
            welcome_msg,
            reply_markup=get_keyboard('main_menu')
        )
        return State.MAIN_MENU
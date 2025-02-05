# src/bot/handlers/admin.py

from telegram import Update
from telegram.ext import ContextTypes
import os
from datetime import datetime, timedelta
from typing import List, Dict
import csv
import io
import logging
from src.bot.keyboards import get_keyboard
from src.bot.states import State

logger = logging.getLogger(__name__)

class AdminHandler:
    def __init__(self, firebase_service):
        """Initialize admin handler with Firebase service."""
        self.firebase = firebase_service
        self.admin_ids = set(map(int, os.getenv('ADMIN_CHAT_IDS', '').split(',')))

    def is_admin(self, chat_id: int) -> bool:
        """Check if user is an admin."""
        return chat_id in self.admin_ids

    async def handle_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle admin commands."""
        if not self.is_admin(update.effective_chat.id):
            await update.message.reply_text("🚫 This command is only available to administrators.")
            return None

        text = update.message.text

        if text == "📢 Broadcast":
            await update.message.reply_text(
                "✍️ Enter your broadcast message:",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.ADMIN_AWAITING_BROADCAST

        elif text == "💎 Premium":
            await update.message.reply_text(
                "Premium User Management\n\n"
                "Select action:\n"
                "• Add Premium Access\n"
                "• Remove Premium Access",
                reply_markup=get_keyboard('premium_action')
            )
            return State.ADMIN_AWAITING_PREMIUM_ACTION

        elif text == "📊 Stats":
            await self.show_stats(update, context)
        elif text == "👥 Users":
            await self.list_users(update, context)
        elif text == "📈 Activity":
            await self.generate_activity_report(update, context)
        elif text == "📥 Export Users":
            await self.export_users_data(update, context)
        else:
            await update.message.reply_text(
                "Welcome to Admin Mode. Select an option:",
                reply_markup=get_keyboard('admin')
            )
        return None

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show system statistics."""
        try:
            # Get user stats from Firebase
            users_ref = self.firebase.db.collection('users')
            calcs_ref = self.firebase.db.collection('calculations')
            
            # Count total users
            users_snapshot = users_ref.get()
            total_users = len(users_snapshot)
            
            # Count premium users
            premium_users = len([user for user in users_snapshot 
                if user.to_dict().get('subscription_type') == 'premium'])
            
            # Get today's calculations
            today = datetime.now().date()
            today_calcs = len([calc for calc in calcs_ref.get() 
                if calc.to_dict()['timestamp'].date() == today])
            
            stats_message = (
                "📊 System Statistics\n\n"
                f"👥 Total Users: {total_users}\n"
                f"💎 Premium Users: {premium_users}\n"
                f"🔢 Today's Calculations: {today_calcs}\n"
                f"💻 System Status: Online\n"
                f"🕒 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await update.message.reply_text(stats_message)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching statistics: {str(e)}")

    async def list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List recent users and their activity."""
        try:
            # Get recent users from Firebase
            users_ref = self.firebase.db.collection('users')
            users_snapshot = users_ref.order_by('last_activity', direction='DESCENDING').limit(10).get()
            
            message = ["👥 Recent Users:\n"]
            for user in users_snapshot:
                user_data = user.to_dict()
                message.append(
                    f"ID: {user_data.get('chat_id')}\n"
                    f"Type: {user_data.get('subscription_type', 'free')}\n"
                    f"Last Active: {user_data.get('last_activity').strftime('%Y-%m-%d %H:%M:%S')}\n"
                    "-------------------"
                )
            
            await update.message.reply_text("\n".join(message))
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error listing users: {str(e)}")

    async def handle_broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle broadcast message input."""
        message = update.message.text
        
        if message == '⬅️ Back to Main Menu':
            await update.message.reply_text(
                "Broadcast cancelled.",
                reply_markup=get_keyboard('admin')
            )
            return None

        # Store the pending broadcast message
        context.user_data['pending_broadcast'] = message
        await update.message.reply_text(
            f"📢 Preview of broadcast message:\n\n"
            f"{message}\n\n"
            "Are you sure you want to send this to all users?",
            reply_markup=get_keyboard('confirm_broadcast')
        )
        return State.ADMIN_AWAITING_BROADCAST_CONFIRM

    async def handle_premium_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle premium action selection."""
        action = update.message.text
        
        if action == '⬅️ Back to Main Menu':
            await update.message.reply_text(
                "Action cancelled.",
                reply_markup=get_keyboard('admin')
            )
            return None
        
        if action == "Add Premium Access":
            context.user_data['premium_action'] = 'add'
        elif action == "Remove Premium Access":
            context.user_data['premium_action'] = 'remove'
        else:
            await update.message.reply_text("Please select a valid action.")
            return State.ADMIN_AWAITING_PREMIUM_ACTION

        await update.message.reply_text(
            "Enter user's Telegram ID:",
            reply_markup=get_keyboard('back_to_main')
        )
        return State.ADMIN_AWAITING_USER_ID

    async def generate_activity_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate comprehensive user activity report."""
        try:
            # Get time range parameters (optional)
            days = 30  # Default to 30 days
            if context.args and len(context.args) > 1:
                try:
                    days = int(context.args[1])
                except ValueError:
                    days = 30

            # Calculate start date
            start_date = datetime.now() - timedelta(days=days)

            # Fetch users and their activities
            report = []
            users_ref = self.firebase.db.collection('users').get()
            
            for user_doc in users_ref:
                user_data = user_doc.to_dict()
                user_id = user_doc.id

                # Fetch user calculations
                calcs_query = (self.firebase.db.collection('calculations')
                               .where('user_id', '==', int(user_id))
                               .where('timestamp', '>', start_date)
                               .get())
                calculations = [calc.to_dict() for calc in calcs_query]

                # Fetch searches 
                searches_query = (self.firebase.db.collection('searches')
                                  .where('user_id', '==', int(user_id))
                                  .where('timestamp', '>', start_date)
                                  .get())
                searches = [search.to_dict() for search in searches_query]

                # Compile user activity
                report.append({
                    'user_id': user_id,
                    'phone_number': user_data.get('phone_number', 'N/A'),
                    'subscription_type': user_data.get('subscription_type', 'free'),
                    'total_calculations': len(calculations),
                    'total_searches': len(searches),
                    'last_activity': user_data.get('last_activity', 'N/A'),
                    'premium_expiry': user_data.get('premium_expiry', 'N/A')
                })

            # Format and send report
            report_message = "📊 User Activity Report\n\n"
            for entry in report:
                report_message += (
                    f"👤 User ID: {entry['user_id']}\n"
                    f"📱 Phone: {entry['phone_number']}\n"
                    f"💎 Subscription: {entry['subscription_type']}\n"
                    f"🧮 Calculations: {entry['total_calculations']}\n"
                    f"🔍 Searches: {entry['total_searches']}\n"
                    f"⏰ Last Activity: {entry['last_activity']}\n"
                    f"🕒 Premium Expiry: {entry['premium_expiry']}\n\n"
                )

            # Send report in chunks if too long
            for i in range(0, len(report_message), 4096):
                await update.message.reply_text(report_message[i:i+4096])

        except Exception as e:
            await update.message.reply_text(f"❌ Error generating activity report: {str(e)}")

    async def export_users_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Export users data to CSV file."""
        try:
            # Fetch all users
            users_ref = self.firebase.db.collection('users').get()
            
            # Prepare CSV file in memory
            output = io.StringIO()
            csv_writer = csv.writer(output)
            
            # Write headers
            headers = [
                'User ID', 'Phone Number', 'Verification Status', 
                'Subscription Type', 'Premium Expiry', 'Daily Searches', 
                'Daily Calculations', 'Last Activity', 'Created At'
            ]
            csv_writer.writerow(headers)
            
            # Write user data
            for user_doc in users_ref:
                user_data = user_doc.to_dict()
                csv_writer.writerow([
                    user_doc.id,
                    user_data.get('phone_number', 'N/A'),
                    'Verified' if user_data.get('verification_status') else 'Unverified',
                    user_data.get('subscription_type', 'free'),
                    str(user_data.get('premium_expiry', 'N/A')),
                    user_data.get('daily_searches', 0),
                    user_data.get('daily_calculations', 0),
                    str(user_data.get('last_activity', 'N/A')),
                    str(user_data.get('created_at', 'N/A'))
                ])
            
            # Send CSV file
            output.seek(0)
            await update.message.reply_document(
                document=output.getvalue().encode('utf-8'),
                filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error exporting users data: {str(e)}")

    async def show_admin_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show admin help message with expanded commands."""
        help_message = (
            "🔧 Admin Commands:\n\n"
            "/admin stats - Show system statistics 📊\n"
            "/admin users - List recent users 👥\n"
            "/admin broadcast [msg] - Send message to all users 📢\n"
            "/admin premium [add/remove] [user_id] [days] - Manage premium users 💎\n"
            "/admin activity [days] - Generate user activity report (default 30 days) 🕵️\n"
            "/admin users_export - Export full users data to CSV 💾\n"
            "/admin help - Show this message ❓"
        )
        await update.message.reply_text(help_message)

    async def handle_broadcast_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle broadcast confirmation."""
        if update.message.text == '✅ Send Broadcast':
            message = context.user_data.get('pending_broadcast')
            try:
                users_ref = self.firebase.db.collection('users').get()
                success = 0
                failed = 0
                
                for user in users_ref:
                    try:
                        chat_id = user.to_dict().get('chat_id')
                        if chat_id:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"📢 Broadcast Message:\n\n{message}"
                            )
                            success += 1
                    except Exception:
                        failed += 1
                        
                await update.message.reply_text(
                    f"Broadcast completed:\n"
                    f"✅ Successful: {success}\n"
                    f"❌ Failed: {failed}",
                    reply_markup=get_keyboard('admin')
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error broadcasting message: {str(e)}",
                    reply_markup=get_keyboard('admin')
                )
        else:
            await update.message.reply_text(
                "Broadcast cancelled.",
                reply_markup=get_keyboard('admin')
            )
        
        return None

    async def handle_premium_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle premium user ID input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            user_id = int(update.message.text)
            context.user_data['premium_user_id'] = user_id
            
            action = context.user_data.get('premium_action')
            if action == 'add':
                await update.message.reply_text(
                    "Enter number of days for premium access:",
                    reply_markup=get_keyboard('back_to_main')
                )
                return State.ADMIN_AWAITING_PREMIUM_DAYS
            else:
                return await self.handle_premium_remove(update, context)
            
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid user ID (numbers only).",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.ADMIN_AWAITING_USER_ID

    async def handle_premium_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        """Handle premium days input."""
        if update.message.text == '⬅️ Back to Main Menu':
            return await self.back_to_menu(update)

        try:
            days = int(update.message.text)
            if days <= 0:
                raise ValueError("Days must be positive")
            
            user_id = context.user_data.get('premium_user_id')
            expiry_date = datetime.now() + timedelta(days=days)
            
            # Update user's premium status
            user_ref = self.firebase.db.collection('users').document(str(user_id))
            user_ref.update({
                'subscription_type': 'premium',
                'premium_expiry': expiry_date
            })
            
            await update.message.reply_text(
                f"✅ Premium access granted to user {user_id}\n"
                f"Duration: {days} days\n"
                f"Expiry: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}",
                reply_markup=get_keyboard('admin')
            )
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Premium access granted!\n"
                         f"Duration: {days} days\n"
                         f"Expiry: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
        except ValueError as e:
            await update.message.reply_text(
                "❌ Please enter a valid number of days.",
                reply_markup=get_keyboard('back_to_main')
            )
            return State.ADMIN_AWAITING_PREMIUM_DAYS
        
        return None

    async def handle_premium_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle premium removal."""
        user_id = context.user_data.get('premium_user_id')
        
        try:
            # Remove premium status
            user_ref = self.firebase.db.collection('users').document(str(user_id))
            user_ref.update({
                'subscription_type': 'free',
                'premium_expiry': None
            })
            
            await update.message.reply_text(
                f"✅ Premium access removed from user {user_id}",
                reply_markup=get_keyboard('admin')
            )
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Your premium access has been removed."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error removing premium access: {str(e)}",
                reply_markup=get_keyboard('admin')
            )
        
        return None

    async def back_to_menu(self, update: Update) -> None:
        """Helper to return to admin menu."""
        await update.message.reply_text(
            "Returning to admin menu.",
            reply_markup=get_keyboard('admin')  # Show the admin menu keyboard
        )
        return None
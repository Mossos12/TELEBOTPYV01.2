# src/services/firebase.py

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
import os
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FirebaseService:
    def __init__(self):
        """Initialize Firebase connection using environment variables."""
        try:
            # Create credentials dictionary from environment variables
            cred_dict = {
                "type": "service_account",
                "project_id": os.getenv('FIREBASE_PROJECT_ID'),
                "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
                "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
            }

            # Initialize Firebase with credentials dictionary
            if not firebase_admin._apps:
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)

            self.db = firestore.client()
            logger.info("✅ Firebase initialized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Firebase initialization error: {e}")
            logger.error(f"📝 Project ID: {os.getenv('FIREBASE_PROJECT_ID')}")
            logger.error(f"📧 Client Email: {os.getenv('FIREBASE_CLIENT_EMAIL')}")
            raise

    async def create_user(self, chat_id: int) -> Dict:
        """Create a new user in Firebase."""
        try:
            user_ref = self.db.collection('users').document(str(chat_id))
            user_data = {
                'chat_id': chat_id,
                'created_at': firestore.SERVER_TIMESTAMP,
                'subscription_type': 'free',
                'daily_searches': 0,
                'daily_calculations': 0,
                'verification_status': False,
                'terms_accepted': False,
                'last_activity': firestore.SERVER_TIMESTAMP,
                'phone_number': None,
                'verification_code': None,
                'verification_attempts': 0,
                'is_blocked': False,
                'block_reason': None,
                'premium_expiry': None
            }
            user_ref.set(user_data)
            return user_data
        except Exception as e:
            logger.error(f"Error creating user {chat_id}: {e}")
            raise

    async def get_user(self, chat_id: int) -> Optional[Dict]:
        """Get user data from Firebase."""
        try:
            user_ref = self.db.collection('users').document(str(chat_id))
            user = user_ref.get()
            if user.exists:
                # Update last activity
                user_ref.update({'last_activity': firestore.SERVER_TIMESTAMP})
                return user.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error getting user {chat_id}: {e}")
            return None

    async def update_user(self, chat_id: int, data: Dict) -> None:
        """Update user data in Firebase."""
        try:
            user_ref = self.db.collection('users').document(str(chat_id))
            
            # Ensure proper date formatting for premium expiry
            if 'premium_expiry' in data:
                # If it's a datetime object, convert to timezone-aware
                if isinstance(data['premium_expiry'], datetime):
                    # Make timezone-aware if not already
                    if data['premium_expiry'].tzinfo is None:
                        data['premium_expiry'] = data['premium_expiry'].replace(tzinfo=timezone.utc)
                    # Convert to ISO format string
                    data['premium_expiry'] = data['premium_expiry'].isoformat()
                # If it's not already a string, try to convert
                elif not isinstance(data['premium_expiry'], str):
                    try:
                        data['premium_expiry'] = str(data['premium_expiry'])
                    except Exception as conversion_error:
                        # If conversion fails, remove the key
                        logger.warning(f"Failed to convert premium_expiry for user {chat_id}: {conversion_error}")
                        del data['premium_expiry']
            
            # Update last activity timestamp
            data['last_activity'] = firestore.SERVER_TIMESTAMP
            
            # Update user data in Firestore
            user_ref.update(data)
        except Exception as e:
            logger.error(f"Error updating user {chat_id}: {e}")
            raise

    async def save_calculation(self, chat_id: int, calculation_data: Dict) -> str:
        """Save arbitrage calculation to Firebase."""
        try:
            calc_ref = self.db.collection('calculations').document()
            calculation_data.update({
                'user_id': chat_id,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'status': 'completed',
                'calculation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            calc_ref.set(calculation_data)
            return calc_ref.id
        except Exception as e:
            logger.error(f"Error saving calculation for user {chat_id}: {e}")
            raise

    async def get_user_calculations(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """Get user's calculation history."""
        try:
            calcs = (self.db.collection('calculations')
                    .where('user_id', '==', chat_id)
                    .order_by('timestamp', direction=firestore.Query.DESCENDING)
                    .limit(limit)
                    .stream())
            return [calc.to_dict() for calc in calcs]
        except Exception as e:
            logger.error(f"Error getting calculations for user {chat_id}: {e}")
            return []

    async def increment_daily_limit(self, chat_id: int, limit_type: str) -> bool:
        """Increment and check daily limits."""
        try:
            user_ref = self.db.collection('users').document(str(chat_id))
            
            @firestore.transactional
            def increment_transaction(transaction, user_ref):
                user = user_ref.get().to_dict()
                if not user:
                    return False
                
                # Check if user is blocked
                if user.get('is_blocked', False):
                    return False
                    
                # Check premium status
                is_premium = user.get('subscription_type') == 'premium'
                premium_expiry = user.get('premium_expiry')
                
                # Verify premium hasn't expired
                if is_premium and premium_expiry:
                    try:
                        # Handle both string and datetime inputs
                        if isinstance(premium_expiry, str):
                            try:
                                premium_expiry_date = datetime.fromisoformat(premium_expiry)
                            except ValueError:
                                # If fromisoformat fails, try adding UTC
                                premium_expiry_date = datetime.fromisoformat(premium_expiry + '+00:00')
                        elif isinstance(premium_expiry, datetime):
                            # Make datetime timezone-aware if it's not
                            premium_expiry_date = premium_expiry.replace(tzinfo=timezone.utc) if premium_expiry.tzinfo is None else premium_expiry
                        else:
                            logger.error(f"Invalid premium_expiry type: {type(premium_expiry)}")
                            return False
                        
                        # Ensure current time is timezone-aware
                        current_time = datetime.now(timezone.utc)
                        
                        # If premium is still valid, allow unlimited searches
                        if premium_expiry_date > current_time:
                            transaction.update(user_ref, {
                                'last_activity': firestore.SERVER_TIMESTAMP
                            })
                            return True
                        else:
                            # Premium expired, revert to free
                            transaction.update(user_ref, {
                                'subscription_type': 'free',
                                'premium_expiry': None
                            })
                    except Exception as date_error:
                        logger.error(f"Error parsing premium expiry: {date_error}")
                        return False
                
                # For free users or expired premium
                limit_field = f'daily_{limit_type}'
                current_count = user.get(limit_field, 0)
                max_limit = 1 if limit_type == 'searches' else 10
                
                if current_count >= max_limit:
                    return False
                    
                transaction.update(user_ref, {
                    limit_field: current_count + 1,
                    'last_activity': firestore.SERVER_TIMESTAMP
                })
                return True
                
            transaction = self.db.transaction()
            return increment_transaction(transaction, user_ref)
        except Exception as e:
            logger.error(f"Error incrementing limit for user {chat_id}: {e}")
            return False

    async def check_premium_status(self, chat_id: int, bot=None) -> bool:
        """
        Check if user has valid premium status and send expiration warning.
        """
        try:
            user = await self.get_user(chat_id)
            if not user:
                return False
            
            # Check subscription type
            if user.get('subscription_type') != 'premium':
                return False
            
            # Check premium expiry
            premium_expiry = user.get('premium_expiry')
            if not premium_expiry:
                return False
            
            # Safely convert to timezone-aware datetime
            try:
                # Handle both string and datetime inputs
                if isinstance(premium_expiry, str):
                    # Ensure timezone awareness
                    try:
                        expiry_date = datetime.fromisoformat(premium_expiry)
                    except ValueError:
                        # If fromisoformat fails, try adding UTC
                        expiry_date = datetime.fromisoformat(premium_expiry + '+00:00')
                elif isinstance(premium_expiry, datetime):
                    # Make datetime timezone-aware if it's not
                    expiry_date = premium_expiry.replace(tzinfo=timezone.utc) if premium_expiry.tzinfo is None else premium_expiry
                else:
                    logger.error(f"Unexpected premium_expiry type: {type(premium_expiry)}")
                    return False
                
                # Ensure current time is also timezone-aware
                current_time = datetime.now(timezone.utc)
            except Exception as date_error:
                logger.error(f"Error parsing premium expiry: {date_error}")
                return False
            
            # Check if premium is still valid
            is_valid = expiry_date > current_time
            
            # Send warning if expiring soon (if bot is provided)
            if is_valid and bot:
                days_remaining = (expiry_date - current_time).days
                if days_remaining <= 3:
                    warning_message = (
                        "⏰ Premium Subscription Expiring Soon! 🚨\n\n"
                        f"• Days Remaining: {days_remaining}\n"
                        "Renew your premium to continue enjoying unlimited features!\n"
                        "Go to Premium Features to extend your subscription. 💎"
                    )
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=warning_message
                        )
                    except Exception as warn_error:
                        logger.error(f"Error sending premium expiration warning to {chat_id}: {warn_error}")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"Error checking premium status for user {chat_id}: {e}")
            return False

    async def block_user(self, chat_id: int, reason: str) -> None:
        """Block a user."""
        try:
            await self.update_user(chat_id, {
                'is_blocked': True,
                'block_reason': reason,
                'blocked_at': firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            logger.error(f"Error blocking user {chat_id}: {e}")
            raise

    async def unblock_user(self, chat_id: int) -> None:
        """Unblock a user."""
        try:
            await self.update_user(chat_id, {
                'is_blocked': False,
                'block_reason': None,
                'blocked_at': None
            })
        except Exception as e:
            logger.error(f"Error unblocking user {chat_id}: {e}")
            raise

    async def reset_daily_limits(self) -> None:
        """Reset all users' daily limits."""
        try:
            batch = self.db.batch()
            users = self.db.collection('users').stream()
            
            for user in users:
                batch.update(user.reference, {
                    'daily_searches': 0,
                    'daily_calculations': 0
                })
            
            batch.commit()
            logger.info("Daily limits reset successfully")
        except Exception as e:
            logger.error(f"Error resetting daily limits: {e}")
            raise
# src/bot/keyboards.py

from telegram import ReplyKeyboardMarkup, KeyboardButton

KEYBOARDS = {
    'contact_request': ReplyKeyboardMarkup([
        [KeyboardButton('📱 Share Contact', request_contact=True)]
    ], resize_keyboard=True),

    'terms': ReplyKeyboardMarkup([
        ['✅ Accept Terms'],
        ['❌ Decline Terms']
    ], resize_keyboard=True),

    'main_menu': ReplyKeyboardMarkup([
        ['💹 Calculate Arbitrage'],
        ['🔍 Search Odds'],
        ['📊 My History', '⚙️ Settings'],
        ['📚 Help', '⭐ Premium Features']
    ], resize_keyboard=True),

    'sports': ReplyKeyboardMarkup([
        ['⚽ Football/Soccer', '🏀 Basketball'],
        ['🏈 American Football', '⚾ Baseball'],
        ['🏒 Hockey', '🎾 Tennis'],
        ['🥊 Boxing', '🥋 MMA'],
        ['🏏 Cricket'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'investment': ReplyKeyboardMarkup([
        ['💰 $100', '💰 $500', '💰 $1000'],
        ['💰 $5000', '💰 $10000'],
        ['💰 Custom Amount'], 
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'draw_option': ReplyKeyboardMarkup([
        ['✅ Include Draw', '❌ No Draw'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'yes_no': ReplyKeyboardMarkup([
        ['✅ Yes', '❌ No'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'tax_type': ReplyKeyboardMarkup([
        ['💰 From Profit', '💸 From Stake'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'admin': ReplyKeyboardMarkup([
        ['📊 Stats', '👥 Users'],
        ['📢 Broadcast', '💎 Premium'],
        ['📈 Activity', '📥 Export Users'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'back_to_main': ReplyKeyboardMarkup([
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),

    'premium_action': ReplyKeyboardMarkup([
        ['Add Premium Access'],
        ['Remove Premium Access'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),
    
    'confirm_broadcast': ReplyKeyboardMarkup([
        ['✅ Send Broadcast', '❌ Cancel'],
        ['⬅️ Back to Main Menu']
    ], resize_keyboard=True),
}

def get_keyboard(keyboard_name: str) -> ReplyKeyboardMarkup:
    """Get keyboard by name."""
    return KEYBOARDS.get(keyboard_name, KEYBOARDS['back_to_main'])
# src/utils/validators.py

import re
from typing import Union, Optional
from decimal import Decimal, InvalidOperation

class InputValidator:
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format."""
        # Remove any non-digit characters
        cleaned = re.sub(r'\D', '', phone)
        # Check if the number is between 10 and 15 digits
        return 10 <= len(cleaned) <= 15

    @staticmethod
    def validate_verification_code(code: str) -> bool:
        """Validate verification code format."""
        return bool(re.match(r'^\d{6}$', code))

    @staticmethod
    def validate_investment_amount(amount: Union[str, float, int]) -> Optional[float]:
        """
        Validate and convert investment amount.
        Handles various input formats like '$500', '💰 $500', '500', etc.
        
        Returns float if valid, None if invalid.
        """
        try:
            # Convert string to float if necessary
            if isinstance(amount, str):
                # Remove non-numeric characters except decimal point
                cleaned = re.sub(r'[^\d.]', '', amount)
                
                # Convert to float
                amount = float(cleaned) if cleaned else None
            
            # Convert to Decimal for precise comparison
            if amount is not None:
                amount_decimal = Decimal(str(amount))
                
                # Check range
                if Decimal('10') <= amount_decimal <= Decimal('1000000'):
                    return float(amount_decimal)
            return None
        except (ValueError, InvalidOperation):
            return None

    @staticmethod
    def validate_tax_rate(rate: Union[str, float, int]) -> Optional[float]:
        """
        Validate tax rate.
        Returns float if valid, None if invalid.
        """
        try:
            # Convert string to float if necessary
            if isinstance(rate, str):
                # Remove percentage symbol
                cleaned = rate.replace('%', '')
                rate = float(cleaned)
            
            # Convert to Decimal for precise comparison
            rate_decimal = Decimal(str(rate))
            
            # Check range (0-100%)
            if Decimal('0') <= rate_decimal <= Decimal('100'):
                return float(rate_decimal / 100)
            return None
        except (ValueError, InvalidOperation):
            return None

    @staticmethod
    def validate_odds(odds: Union[str, float, int]) -> Optional[float]:
        """
        Validate odds value.
        Returns float if valid, None if invalid.
        """
        try:
            # Convert string to float if necessary
            if isinstance(odds, str):
                # Remove any non-numeric characters except decimal point
                cleaned = re.sub(r'[^\d.]', '', odds)
                odds = float(cleaned) if cleaned else None
            
            # Convert to Decimal for precise comparison
            if odds is not None:
                odds_decimal = Decimal(str(odds))
                
                # Check if odds are positive and reasonable
                if Decimal('1.01') <= odds_decimal <= Decimal('1000'):
                    return float(odds_decimal)
            return None
        except (ValueError, InvalidOperation):
            return None

    @staticmethod
    def sanitize_input(text: str, max_length: int = 1000) -> str:
        """
        Sanitize user input by removing potentially dangerous characters
        and limiting length.
        """
        # Remove any non-printable characters
        cleaned = ''.join(char for char in text if char.isprintable())
        # Limit length
        return cleaned[:max_length]

    @staticmethod
    def validate_date(date_str: str) -> bool:
        """Validate date string format (YYYY-MM-DD)."""
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', date_str))

    @staticmethod
    def validate_time(time_str: str) -> bool:
        """Validate time string format (HH:MM)."""
        return bool(re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_str))
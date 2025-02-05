# src/services/arbitrage.py

from dataclasses import dataclass
from typing import List, Dict, Optional
import math
from decimal import Decimal, getcontext
import logging

logger = logging.getLogger(__name__)

# Set high precision for decimal calculations
getcontext().prec = 10

@dataclass
class ArbitrageBet:
    bookmaker: str
    team: str
    odds: float
    stake: float
    potential_return: float
    commission: float = 0.0
    deposit_fee: float = 0.0
    withdrawal_fee: float = 0.0

class ArbitrageCalculator:
    def calculate(
        self, 
        investment: float, 
        odds_data: Dict, 
        tax_rate: float = 0.0,
        tax_type: str = 'profit'
    ) -> Dict:
        """
        Calculate arbitrage opportunity with more robust handling.
        """
        try:
            # Ensure we have at least two valid odds
            valid_bets = []
            for bet_type in ['home', 'away', 'draw']:
                if bet_type in odds_data:
                    bet = odds_data[bet_type]
                    # Use default values if not provided
                    odds = bet.get('odds', 1.01)
                    commission = bet.get('commission', 0)
                    deposit = bet.get('deposit', 0)
                    withdrawal = bet.get('withdrawal', 0)
                    
                    valid_bets.append({
                        'team': bet_type,
                        'odds': float(max(odds, 1.01)),  # Ensure minimum odds
                        'commission': float(commission),
                        'deposit': float(deposit),
                        'withdrawal': float(withdrawal)
                    })
            
            # Require at least 2 bets
            if len(valid_bets) < 2:
                raise ValueError("Not enough valid bets for arbitrage")
            
            # Calculate implied probabilities
            total_implied_prob = sum(1 / bet['odds'] for bet in valid_bets)
            
            # Check for arbitrage opportunity
            if total_implied_prob >= 1:
                raise ValueError("No arbitrage opportunity")
            
            # Calculate stakes and returns
            stakes = {}
            total_stake = 0
            potential_returns = []
            
            for bet in valid_bets:
                # Stake based on implied probability
                implied_prob = 1 / bet['odds']
                stake = (investment * implied_prob) / total_implied_prob
                
                # Apply fees and commissions
                stake_after_commission = stake / (1 + bet['commission'])
                
                # Calculate potential return
                potential_return = stake_after_commission * bet['odds']
                potential_return *= (1 - bet['deposit']) * (1 - bet['withdrawal'])
                
                stakes[bet['team']] = {
                    'stake': round(stake, 2),
                    'odds': bet['odds']
                }
                
                total_stake += stake
                potential_returns.append(potential_return)
            
            # Find minimum guaranteed return
            min_return = min(potential_returns)
            
            # Calculate profit and ROI
            profit = min_return - investment
            roi = (profit / investment) * 100
            
            # Apply tax if specified
            tax_amount = 0
            net_profit = profit
            
            if tax_rate > 0:
                if tax_type == 'profit':
                    tax_amount = max(profit * tax_rate, 0)
                    net_profit = profit - tax_amount
                else:
                    tax_amount = investment * tax_rate
                    net_profit = profit - tax_amount
            
            return {
                'stakes': stakes,
                'total_stake': round(total_stake, 2),
                'investment': round(investment, 2),
                'profit': round(profit, 2),
                'net_profit': round(net_profit, 2),
                'roi': round(roi, 2),
                'tax_amount': round(tax_amount, 2)
            }
        
        except Exception as e:
            logger.error(f"Arbitrage calculation error: {e}")
            raise ValueError(f"Unable to calculate arbitrage: {e}")

    def validate_odds_data(self, odds_data: List[Dict]) -> bool:
        """
        Validate odds data comprehensively.
        
        Args:
            odds_data (List[Dict]): List of odds data entries
        
        Returns:
            bool: Whether the odds data is valid
        """
        if not odds_data or len(odds_data) < 2:
            return False
        
        # Check each bet entry
        for bet in odds_data:
            # Validate required keys
            required_keys = ['bookmaker', 'team', 'odds']
            if not all(key in bet for key in required_keys):
                return False
            
            # Validate odds value
            try:
                odds = float(bet['odds'])
                if odds <= 1:
                    return False
            except (TypeError, ValueError):
                return False
        
        return True

    def quick_arbitrage_check(self, odds_data: Dict) -> Dict:
        """
        Quick arbitrage calculation without fees and taxes.
        Returns if arbitrage exists and potential ROI.
        """
        try:
            # Calculate total implied probability
            total_prob = 0
            for bet_type, bet_data in odds_data.items():
                odds = float(bet_data['odds'])
                if odds > 1:  # Valid odds check
                    total_prob += 1 / odds

            # Arbitrage exists if total probability < 1
            if total_prob >= 1:
                return {
                    'opportunity': False,
                    'message': "No arbitrage opportunity"
                }

            # Calculate potential ROI
            roi = ((1 / total_prob) - 1) * 100

            # Example investment for stake calculations
            investment = 1000
            stakes = {}

            # Calculate individual stakes
            for bet_type, bet_data in odds_data.items():
                odds = float(bet_data['odds'])
                stake = (investment / odds) / total_prob
                stakes[bet_type] = {
                    'stake': round(stake, 2),
                    'return': round(stake * odds, 2)
                }

            return {
                'opportunity': True,
                'roi': round(roi, 2),
                'stakes': stakes,
                'message': "Arbitrage opportunity found!"
            }

        except Exception as e:
            logger.error(f"Quick arbitrage check error: {e}")
            return {
                'opportunity': False,
                'message': f"Calculation error: {str(e)}"
            }
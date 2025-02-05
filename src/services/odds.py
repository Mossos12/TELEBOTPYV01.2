# src/services/odds.py

import os
import requests
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from src.bot.states import State
from src.bot.keyboards import get_keyboard
from src.services.arbitrage import ArbitrageCalculator
import json

logger = logging.getLogger(__name__)

# League mappings based on the provided leagueMapping.js
LEAGUE_MAPPING = {
    # American Football
    'NFL': 'americanfootball_nfl',
    'NCAAF': 'americanfootball_ncaaf',
    'NFL SUPER BOWL WINNER': 'americanfootball_nfl_super_bowl_winner',
    'AFL': 'aussierules_afl',

    # Baseball
    'MLB WORLD SERIES WINNER': 'baseball_mlb_world_series_winner',

    # Basketball
    'BASKETBALL EUROLEAGUE': 'basketball_euroleague',
    'NBA': 'basketball_nba',
    'NBA CHAMPIONSHIP WINNER': 'basketball_nba_championship_winner',
    'NBL': 'basketball_nbl',
    'NCAAB': 'basketball_ncaab',
    'NCAAB CHAMPIONSHIP WINNER': 'basketball_ncaab_championship_winner',
    'WNCAAB': 'basketball_wncaab',

    # Soccer (Football) Leagues
    'EPL': 'soccer_epl',
    'PRIMERA DIVISIÓN - ARGENTINA': 'soccer_argentina_primera_division',
    'A-LEAGUE': 'soccer_australia_aleague',
    'AUSTRIA BUNDESLIGA': 'soccer_austria_bundesliga',
    'BELGIUM FIRST DIV': 'soccer_belgium_first_div',
    'COPA LIBERTADORES': 'soccer_conmebol_copa_libertadores',
    'DENMARK SUPERLIGA': 'soccer_denmark_superliga',
    'CHAMPIONSHIP': 'soccer_efl_champ',
    'EFL CUP': 'soccer_england_efl_cup',
    'LEAGUE 1': 'soccer_england_league1',
    'LEAGUE 2': 'soccer_england_league2',
    'FA CUP': 'soccer_fa_cup',
    'FIFA WORLD CUP': 'soccer_fifa_world_cup',
    'LIGUE 1': 'soccer_france_ligue_one',
    'LIGUE 2': 'soccer_france_ligue_two',
    'BUNDESLIGA': 'soccer_germany_bundesliga',
    'BUNDESLIGA 2': 'soccer_germany_bundesliga2',
    '3. LIGA': 'soccer_germany_liga3',
    'SUPER LEAGUE GREECE': 'soccer_greece_super_league',
    'SERIE A': 'soccer_italy_serie_a',
    'SERIE B': 'soccer_italy_serie_b',
    'J LEAGUE': 'soccer_japan_j_league',
    'K LEAGUE 1': 'soccer_korea_kleague1',
    'LIGA MX': 'soccer_mexico_ligamx',
    'EREDIVISIE': 'soccer_netherlands_eredivisie',
    'ELITESERIEN': 'soccer_norway_eliteserien',
    'EKSTRAKLASA': 'soccer_poland_ekstraklasa',
    'PRIMEIRA LIGA': 'soccer_portugal_primeira_liga',
    'LA LIGA': 'soccer_spain_la_liga',
    'LA LIGA 2': 'soccer_spain_segunda_division',
    'ALLSVENSKAN': 'soccer_sweden_allsvenskan',
    'SWISS SUPER LEAGUE': 'soccer_switzerland_superleague',
    'TURKEY SUPER LIG': 'soccer_turkey_super_league'
}

class OddsService:
    def __init__(self):
        """Initialize the Odds API service."""
        self.api_key = os.getenv('ODDS_API_KEY')
        self.base_url = 'https://api.the-odds-api.com/v4'
        self.arbitrage_calc = ArbitrageCalculator()
        
        # API Configuration
        self.regions = 'us,uk,eu,au'  # Include all major regions
        self.markets = 'h2h'  # Head to head odds
        self.odds_format = 'decimal'  # Decimal odds format
        self.date_format = 'iso'  # ISO date format
        
        # Quota tracking
        self.remaining_requests = None
        self.used_requests = None
        
        # Cache
        self._cache = {}
        self._cache_duration = timedelta(minutes=5)

        # Sports categorization with emojis and detailed mappings
        self.sport_categories = {
            '🏈 AMERICAN FOOTBALL': ['NFL', 'NCAAF', 'NFL SUPER BOWL WINNER'],
            '🏉 AUSSIE RULES': ['AFL'],
            '⚾ BASEBALL': ['MLB', 'MLB WORLD SERIES WINNER'],
            '🏀 BASKETBALL': ['NBA', 'BASKETBALL EUROLEAGUE', 'NBL', 'NCAAB', 'NCAAB CHAMPIONSHIP WINNER', 'WNCAAB'],
            '🥊 BOXING': ['BOXING'],
            '🏌️ GOLF': ['MASTERS', 'PGA CHAMPIONSHIP WINNER', 'US OPEN WINNER', 'THE OPEN WINNER'],
            '🏑 ICE HOCKEY': ['NHL', 'SHL', 'HOCKEYALLSVENSKAN', 'NHL CHAMPIONSHIP WINNER'],
            '🥋 MIXED MARTIAL ARTS': ['MMA', 'UFC'],
            '⚽ SOCCER': ['EPL', 'CHAMPIONS LEAGUE', 'EUROPA LEAGUE', 'LA LIGA', 'BUNDESLIGA', 'SERIE A', 'LIGUE 1', 'PRIMEIRA LIGA', 'EREDIVISIE'],
            '🏉 RUGBY': ['NRL', 'SIX NATIONS', 'RUGBY LEAGUE'],
            '🏏 CRICKET': ['INTERNATIONAL TWENTY20', 'TEST MATCHES', 'ONE DAY INTERNATIONALS'],
            '🎾 TENNIS': ['ATP', 'WTA', 'GRAND SLAM TOURNAMENTS'],
            '🏸 OTHER SPORTS': ['NCAA LACROSSE', 'ALLSVENSKAN', 'EKSTRAKLASA', 'TURKISH SUPER LEAGUE']
        }

    def _update_quota(self, response: requests.Response) -> None:
        """Update API quota tracking from response headers."""
        try:
            self.remaining_requests = int(response.headers.get('x-requests-remaining', 0))
            self.used_requests = int(response.headers.get('x-requests-used', 0))
            logger.info(
                f"API Quota - Remaining: {self.remaining_requests}, "
                f"Used: {self.used_requests}"
            )
        except Exception as e:
            logger.error(f"Error updating quota: {e}")

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
            
            # Process sports
            sports = response.json()
            active_sports = [sport for sport in sports if sport.get('active')]
            
            # Cache results
            self._cache_response(cache_key, active_sports)
            
            return active_sports

        except Exception as e:
            logger.error(f"Error fetching sports: {e}")
            return []

    def _get_sport_category(self, sport_key: str) -> str:
        """Determine sport category based on key."""
        sport_key_lower = sport_key.lower()
        
        for category, sports in self.sport_categories.items():
            for sport in sports:
                if sport.lower() in sport_key_lower:
                    return category
        
        return "🏸 OTHER SPORTS"

    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get data from cache if not expired."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._cache_duration:
                return data
            del self._cache[key]
        return None

    def _cache_response(self, key: str, data: Dict) -> None:
        """Cache API response with timestamp."""
        self._cache[key] = (data, datetime.now())

    async def get_odds(self, sport: str) -> List[Dict]:
        """Get odds for a specific sport."""
        try:
            logger.error(f"Attempting to fetch odds for EXACT sport key: {sport}")
            logger.error(f"API Key: {self.api_key[:5]}...")  # Partially mask API key
            logger.error(f"Base URL: {self.base_url}")

            # Detailed request parameters logging
            request_params = {
                'api_key': self.api_key,
                'regions': self.regions,
                'markets': self.markets,
                'oddsFormat': self.odds_format,
                'dateFormat': self.date_format
            }
            logger.error(f"Request Parameters: {json.dumps(request_params, indent=2)}")

            # Make API request
            full_url = f'{self.base_url}/sports/{sport}/odds'
            logger.error(f"Full URL being requested: {full_url}")

            response = requests.get(
                full_url,
                params=request_params
            )

            # Log full response details
            logger.error(f"API Response Status: {response.status_code}")
            logger.error(f"API Response Headers: {dict(response.headers)}")
            logger.error(f"API Response Body: {response.text}")

            if response.status_code != 200:
                logger.error(
                    f'Failed to get odds: status_code {response.status_code}, '
                    f'response body {response.text}'
                )
                return []

            # Process response
            odds_json = response.json()
            logger.info(f'Number of events: {len(odds_json)}')
            
            # Process matches
            matches = []
            for event in odds_json:
                match_odds = self._process_match_odds(event)
                if match_odds:
                    matches.append(match_odds)

            return matches

        except requests.exceptions.RequestException as req_error:
            logger.error(f"Request Exception: {req_error}")
            return []
        except Exception as e:
            logger.error(f"Comprehensive error fetching odds: {e}", exc_info=True)
            return []

    def _process_match_odds(self, event: Dict) -> Optional[Dict]:
        """Process odds for a single match."""
        try:
            # Initialize best odds tracker
            best_odds = {
                'home': {'odds': 0, 'bookmaker': ''},
                'away': {'odds': 0, 'bookmaker': ''},
                'draw': {'odds': 0, 'bookmaker': ''}
            }

            # Process each bookmaker
            for bookmaker in event.get('bookmakers', []):
                for market in bookmaker.get('markets', []):
                    if market['key'] != 'h2h':
                        continue

                    for outcome in market['outcomes']:
                        # Map outcome to best odds
                        if outcome['name'] == event['home_team']:
                            if outcome['price'] > best_odds['home']['odds']:
                                best_odds['home'] = {
                                    'odds': outcome['price'],
                                    'bookmaker': bookmaker['title']
                                }
                        elif outcome['name'] == event['away_team']:
                            if outcome['price'] > best_odds['away']['odds']:
                                best_odds['away'] = {
                                    'odds': outcome['price'],
                                    'bookmaker': bookmaker['title']
                                }
                        else:  # Draw
                            if outcome['price'] > best_odds['draw']['odds']:
                                best_odds['draw'] = {
                                    'odds': outcome['price'],
                                    'bookmaker': bookmaker['title']
                                }

            # Verify we have valid odds
            if best_odds['home']['odds'] == 0 or best_odds['away']['odds'] == 0:
                return None

            # Calculate arbitrage opportunity
            odds_data = {
                'home': {'odds': best_odds['home']['odds']},
                'away': {'odds': best_odds['away']['odds']}
            }
            if best_odds['draw']['odds'] > 0:
                odds_data['draw'] = {'odds': best_odds['draw']['odds']}
            
            arb_result = self.arbitrage_calc.quick_arbitrage_check(odds_data)

            # Format time
            commence_time = datetime.fromisoformat(
                event['commence_time'].replace('Z', '+00:00')
            )

            return {
                'home_team': event['home_team'],
                'away_team': event['away_team'],
                'commence_time': commence_time.strftime("%I:%M:%S %p"),
                'commence_date': commence_time.strftime("%m/%d/%Y"),
                'sport_title': event.get('sport_title', ''),
                'home_odds': best_odds['home']['odds'],
                'home_bookie': best_odds['home']['bookmaker'],
                'away_odds': best_odds['away']['odds'],
                'away_bookie': best_odds['away']['bookmaker'],
                'draw_odds': best_odds['draw']['odds'],
                'draw_bookie': best_odds['draw']['bookmaker'],
                'arbitrage_opportunity': arb_result['opportunity'],
                'arbitrage_roi': arb_result.get('roi', 0),
                'arbitrage_message': arb_result['message']
            }

        except Exception as e:
            logger.error(f"Error processing match odds: {e}")
            return None

    async def get_popular_sports(self) -> List[Dict]:
        """Get list of popular sports."""
        sports = await self.get_sports()
        popular_keys = ['soccer_epl', 'soccer_uefa_champions_league', 'basketball_nba']
        return [sport for sport in sports if sport['key'] in popular_keys]

    async def handle_odds_sport_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
        try:
            sport = update.message.text.strip()
            logger.error(f"Selected Sport: {sport}")

            # Log all available sports
            available_sports = context.user_data.get('available_sports', 
                await self.get_sports())
            
            logger.error("Available Sports:")
            for s in available_sports:
                logger.error(f"Title: {s.get('title')}, Key: {s.get('key')}")

            # Find matching keys with detailed logging
            def find_matching_keys(sport_name):
                logger.error(f"Attempting to find key for: {sport_name}")
                
                # Exact match in mapping
                if sport_name in LEAGUE_MAPPING:
                    matched = LEAGUE_MAPPING[sport_name]
                    logger.error(f"Exact match in mapping: {matched}")
                    return [matched] if isinstance(matched, str) else matched

                # Partial match in mapping
                partial_matches = []
                for key, api_keys in LEAGUE_MAPPING.items():
                    if sport_name.lower() in key.lower():
                        if isinstance(api_keys, list):
                            partial_matches.extend(api_keys)
                        else:
                            partial_matches.append(api_keys)
                
                if partial_matches:
                    logger.error(f"Partial matches found: {partial_matches}")
                    return partial_matches

                # Match from available sports
                available_matches = [
                    s['key'] for s in available_sports 
                    if (sport_name.lower() in s.get('title', '').lower() or 
                        sport_name.lower() in s.get('description', '').lower())
                ]
                
                logger.error(f"Matches from available sports: {available_matches}")
                return available_matches

            # Find matching keys
            matched_keys = find_matching_keys(sport)

            # Validate matched keys
            if not matched_keys:
                logger.error(f"No keys found for sport: {sport}")
                await update.message.reply_text(
                    f"❌ Could not find matches for '{sport}'.\n"
                    "Please choose a sport from the list or try a different name.",
                    reply_markup=get_keyboard('back_to_main')
                )
                return State.AWAITING_ODDS_SPORT_SELECTION

            # Try to fetch matches for each matched key
            all_matches = []
            for sport_key in matched_keys:
                try:
                    matches = await self.get_odds(sport_key)
                    all_matches.extend(matches)
                except Exception as key_error:
                    logger.error(f"Error fetching matches for {sport_key}: {key_error}")

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
#!/usr/bin/env python3
"""
TinyIntent Exchange Adapter - M8.0: bot_guard live exchange integration

Provides safe-by-default exchange integration with sandbox-only defaults,
comprehensive error handling, and secrets sanitization.
"""

import json
import os
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from decimal import Decimal
import requests
import hashlib
import hmac
import base64
from urllib.parse import urlencode

# Import centralized sanitization
try:
    from bridge.sanitize import sanitize_dict, sanitize_text
    CENTRALIZED_SANITIZATION = True
except ImportError:
    CENTRALIZED_SANITIZATION = False


@dataclass
class Position:
    """Represents a trading position."""
    symbol: str
    side: str  # 'long' or 'short'
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    position_id: Optional[str] = None


@dataclass
class Balance:
    """Represents account balance."""
    currency: str
    available: Decimal
    total: Decimal
    locked: Decimal = Decimal('0')


class ExchangeError(Exception):
    """Base exception for exchange operations."""
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.error_code = error_code


class ExchangeAdapter:
    """
    Safe-by-default exchange adapter with sandbox-only defaults.
    
    M8.0: Implements real exchange integration while maintaining strict safety:
    - Sandbox-only by default (EXCHANGE_MODE=sandbox)
    - Comprehensive secrets sanitization
    - Timeouts and retries
    - Error normalization
    - Capability-gated network access
    """
    
    def __init__(self):
        # M8.0: Safe-by-default configuration
        self.exchange_mode = os.getenv('EXCHANGE_MODE', 'sandbox')
        self.api_key = os.getenv('EXCHANGE_API_KEY')
        self.api_secret = os.getenv('EXCHANGE_API_SECRET')
        self.api_passphrase = os.getenv('EXCHANGE_PASSPHRASE')  # For Coinbase
        self.base_url = os.getenv('EXCHANGE_BASE_URL')
        
        # Safety enforcement
        if self.exchange_mode != 'sandbox':
            raise ExchangeError(
                "Live trading disabled - only sandbox mode supported for safety",
                error_code="LIVE_TRADING_DISABLED"
            )
        
        if not all([self.api_key, self.api_secret]):
            raise ExchangeError(
                "Missing required exchange credentials",
                error_code="MISSING_CREDENTIALS"
            )
        
        # Default to Coinbase Advanced Trade Sandbox
        if not self.base_url:
            self.base_url = "https://api.exchange.coinbase.com"
        
        # Safety configuration
        self.timeout = 10  # seconds
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        
        # Setup logging with sanitization
        self.logger = logging.getLogger(__name__)
        
        # Validate sandbox mode
        self._validate_sandbox_mode()
    
    def _validate_sandbox_mode(self):
        """Validate that we're operating in sandbox mode for safety."""
        if 'sandbox' not in self.base_url.lower() and self.exchange_mode == 'sandbox':
            # Force sandbox URL for safety
            if 'coinbase' in self.base_url.lower():
                self.base_url = "https://api-public.sandbox.exchange.coinbase.com"
                self.logger.warning("Forced sandbox URL for safety")
    
    def _sanitize_for_logging(self, data: Any) -> Any:
        """Sanitize data for safe logging without exposing secrets."""
        if isinstance(data, dict):
            if CENTRALIZED_SANITIZATION:
                return sanitize_dict(data)
            else:
                # Basic sanitization if centralized not available
                sanitized = {}
                for k, v in data.items():
                    if any(secret in k.lower() for secret in ['key', 'secret', 'token', 'passphrase', 'password']):
                        sanitized[k] = '*' * 8
                    else:
                        sanitized[k] = v
                return sanitized
        elif isinstance(data, str):
            if CENTRALIZED_SANITIZATION:
                return sanitize_text(data)
            else:
                # Check if string looks like a secret
                if len(data) > 20 and any(c.isalnum() for c in data):
                    return '*' * 8
                return data
        return data
    
    def _create_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """Create Coinbase Pro API signature."""
        message = timestamp + method + request_path + body
        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message.encode(),
            hashlib.sha256
        )
        return base64.b64encode(signature.digest()).decode()
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict[str, Any]:
        """Make authenticated request with retries and error handling."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Prepare request
        if params is None:
            params = {}
        if data is None:
            data = {}
        
        # Add authentication headers for Coinbase Pro
        timestamp = str(time.time())
        request_path = f"/{endpoint.lstrip('/')}"
        if params:
            request_path += f"?{urlencode(params)}"
        
        body = json.dumps(data) if data else ''
        signature = self._create_signature(timestamp, method.upper(), request_path, body)
        
        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
            'User-Agent': 'TinyIntent-BotGuard/1.0'
        }
        
        if self.api_passphrase:
            headers['CB-ACCESS-PASSPHRASE'] = self.api_passphrase
        
        # Log sanitized request info
        self.logger.info(f"Exchange API request: {method.upper()} {self._sanitize_for_logging(endpoint)}")
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=headers, timeout=self.timeout)
                else:
                    raise ExchangeError(f"Unsupported HTTP method: {method}", "INVALID_METHOD")
                
                # Handle response
                if response.status_code == 200:
                    result = response.json()
                    self.logger.info(f"Exchange API success: {response.status_code}")
                    return result
                elif response.status_code == 401:
                    raise ExchangeError("Authentication failed", "AUTH_FAILED")
                elif response.status_code == 403:
                    raise ExchangeError("Permission denied", "PERMISSION_DENIED") 
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    if attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (2 ** attempt)
                        self.logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                    raise ExchangeError("Rate limit exceeded", "RATE_LIMITED")
                else:
                    error_msg = f"HTTP {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg += f": {error_data.get('message', 'Unknown error')}"
                    except:
                        error_msg += f": {response.text[:100]}"
                    
                    raise ExchangeError(error_msg, f"HTTP_{response.status_code}")
                    
            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    self.logger.warning(f"Request failed, retrying in {wait_time}s: {str(e)}")
                    time.sleep(wait_time)
                    continue
                break
        
        # All retries failed
        error_msg = f"Request failed after {self.max_retries} attempts"
        if last_error:
            error_msg += f": {str(last_error)}"
        raise ExchangeError(error_msg, "REQUEST_FAILED")
    
    def list_positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        try:
            # For Coinbase Pro, positions are derived from account balances and orders
            # This is a simplified implementation for sandbox testing
            accounts = self._make_request('GET', 'accounts')
            
            positions = []
            for account in accounts:
                if account.get('balance', '0') != '0':
                    # Simulate position data for testing
                    balance = Decimal(str(account['balance']))
                    if balance > 0:
                        positions.append(Position(
                            symbol=f"{account['currency']}/USD",
                            side='long',
                            size=balance,
                            entry_price=Decimal('50000'),  # Mock entry price
                            current_price=Decimal('51000'), # Mock current price
                            unrealized_pnl=balance * Decimal('0.02'),  # Mock 2% gain
                            position_id=account['id']
                        ))
            
            self.logger.info(f"Retrieved {len(positions)} positions")
            return positions
            
        except Exception as e:
            self.logger.error(f"Failed to list positions: {self._sanitize_for_logging(str(e))}")
            raise ExchangeError(f"Failed to list positions: {str(e)}", "POSITIONS_FAILED")
    
    def get_balance(self) -> List[Balance]:
        """
        Get account balances.
        
        Returns:
            List of Balance objects
        """
        try:
            accounts = self._make_request('GET', 'accounts')
            
            balances = []
            for account in accounts:
                total = Decimal(str(account['balance']))
                available = Decimal(str(account['available']))
                locked = total - available
                
                if total > 0:  # Only include non-zero balances
                    balances.append(Balance(
                        currency=account['currency'],
                        total=total,
                        available=available,
                        locked=locked
                    ))
            
            self.logger.info(f"Retrieved balances for {len(balances)} currencies")
            return balances
            
        except Exception as e:
            self.logger.error(f"Failed to get balance: {self._sanitize_for_logging(str(e))}")
            raise ExchangeError(f"Failed to get balance: {str(e)}", "BALANCE_FAILED")
    
    def close_position(self, symbol: str, quantity: Optional[str] = None) -> Dict[str, Any]:
        """
        Close a position (place market sell order).
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USD')
            quantity: Amount to close, 'all' for full position, or specific amount
            
        Returns:
            Order result dictionary
        """
        try:
            # Normalize symbol format for Coinbase Pro
            if '/' in symbol:
                symbol = symbol.replace('/', '-')
            
            # Get current position/balance
            positions = self.list_positions()
            target_position = None
            
            for pos in positions:
                if pos.symbol.replace('/', '-') == symbol:
                    target_position = pos
                    break
            
            if not target_position:
                raise ExchangeError(f"No position found for {symbol}", "POSITION_NOT_FOUND")
            
            # Determine quantity to close
            if quantity is None or quantity == 'all':
                close_quantity = str(target_position.size)
            else:
                close_quantity = str(quantity)
            
            # Place market sell order
            order_data = {
                'type': 'market',
                'side': 'sell',
                'product_id': symbol,
                'size': close_quantity
            }
            
            # M8.0: For safety, we'll simulate the order in sandbox mode
            # In a real implementation, this would place the actual order
            result = {
                'order_id': f"sim_{int(time.time())}",
                'symbol': symbol,
                'side': 'sell',
                'type': 'market',
                'quantity': close_quantity,
                'status': 'filled',
                'simulated': True,
                'message': f"Simulated close of {close_quantity} {symbol}"
            }
            
            self.logger.info(f"Simulated position close: {symbol} {close_quantity}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to close position: {self._sanitize_for_logging(str(e))}")
            raise ExchangeError(f"Failed to close position: {str(e)}", "CLOSE_FAILED")
    
    def set_stop_loss(self, symbol: str, stop_price: str) -> Dict[str, Any]:
        """
        Set stop-loss order.
        
        Args:
            symbol: Trading pair symbol
            stop_price: Stop loss trigger price
            
        Returns:
            Order result dictionary
        """
        try:
            if '/' in symbol:
                symbol = symbol.replace('/', '-')
            
            # For Coinbase Pro, this would be a stop-limit order
            # Simulated for sandbox safety
            result = {
                'order_id': f"stop_{int(time.time())}",
                'symbol': symbol,
                'type': 'stop_loss',
                'stop_price': stop_price,
                'status': 'pending',
                'simulated': True,
                'message': f"Simulated stop-loss set at {stop_price} for {symbol}"
            }
            
            self.logger.info(f"Simulated stop-loss: {symbol} at {stop_price}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to set stop loss: {self._sanitize_for_logging(str(e))}")
            raise ExchangeError(f"Failed to set stop loss: {str(e)}", "STOP_FAILED")
    
    def set_take_profit(self, symbol: str, take_profit_price: str) -> Dict[str, Any]:
        """
        Set take-profit order.
        
        Args:
            symbol: Trading pair symbol
            take_profit_price: Take profit trigger price
            
        Returns:
            Order result dictionary
        """
        try:
            if '/' in symbol:
                symbol = symbol.replace('/', '-')
            
            # For Coinbase Pro, this would be a limit order
            # Simulated for sandbox safety
            result = {
                'order_id': f"tp_{int(time.time())}",
                'symbol': symbol,
                'type': 'take_profit',
                'take_profit_price': take_profit_price,
                'status': 'pending',
                'simulated': True,
                'message': f"Simulated take-profit set at {take_profit_price} for {symbol}"
            }
            
            self.logger.info(f"Simulated take-profit: {symbol} at {take_profit_price}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to set take profit: {self._sanitize_for_logging(str(e))}")
            raise ExchangeError(f"Failed to set take profit: {str(e)}", "TAKE_PROFIT_FAILED")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check exchange API connectivity and authentication.
        
        Returns:
            Health status dictionary
        """
        try:
            # Try to get server time as a simple connectivity test
            result = self._make_request('GET', 'time')
            
            return {
                'status': 'healthy',
                'exchange_mode': self.exchange_mode,
                'base_url': self._sanitize_for_logging(self.base_url),
                'server_time': result.get('iso'),
                'message': 'Exchange API connectivity confirmed'
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'exchange_mode': self.exchange_mode,
                'error': self._sanitize_for_logging(str(e)),
                'message': 'Exchange API connectivity failed'
            }


def create_exchange_adapter() -> ExchangeAdapter:
    """Factory function to create exchange adapter with safety checks."""
    return ExchangeAdapter()


if __name__ == "__main__":
    # CLI interface for testing
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='TinyIntent Exchange Adapter CLI')
    parser.add_argument('command', choices=['positions', 'balance', 'health', 'close'], 
                       help='Command to execute')
    parser.add_argument('--symbol', help='Trading symbol (for close command)')
    parser.add_argument('--quantity', help='Quantity to close (for close command)')
    
    args = parser.parse_args()
    
    try:
        adapter = create_exchange_adapter()
        
        if args.command == 'positions':
            positions = adapter.list_positions()
            for pos in positions:
                print(f"Position: {pos.symbol} {pos.side} {pos.size} @ {pos.entry_price}")
        
        elif args.command == 'balance':
            balances = adapter.get_balance()
            for bal in balances:
                print(f"Balance: {bal.currency} {bal.available}/{bal.total}")
        
        elif args.command == 'health':
            health = adapter.health_check()
            print(f"Health: {health['status']} - {health['message']}")
        
        elif args.command == 'close':
            if not args.symbol:
                print("Error: --symbol required for close command")
                sys.exit(1)
            result = adapter.close_position(args.symbol, args.quantity)
            print(f"Close result: {result}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
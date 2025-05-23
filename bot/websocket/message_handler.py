"""Обработчик WebSocket сообщений."""

import orjson
from typing import Optional, Dict, Any
from bot.core.logger import get_logger

logger = get_logger(__name__)


class MessageHandler:
    """Обработчик сообщений от Binance WebSocket."""
    
    def __init__(self):
        self.messages_processed = 0
        self.errors_count = 0
    
    async def handle_message(self, message: str) -> Optional[Dict[str, Any]]:
        """Обработка входящего сообщения.
        
        Args:
            message: JSON строка от WebSocket
            
        Returns:
            Данные свечи, если сообщение содержит закрытую свечу, иначе None
        """
        try:
            self.messages_processed += 1
            
            # Парсим JSON
            data = orjson.loads(message)
            
            # Проверяем структуру сообщения
            if 'data' not in data or 'k' not in data['data']:
                logger.debug("Message doesn't contain candle data")
                return None
            
            kline_data = data['data']['k']
            
            # Извлекаем данные свечи
            candle = {
                'symbol': kline_data['s'],
                'interval': kline_data['i'],
                'open': float(kline_data['o']),
                'high': float(kline_data['h']),
                'low': float(kline_data['l']),
                'close': float(kline_data['c']),
                'volume': float(kline_data['v']),
                'is_closed': kline_data['x']
            }
            
            # Обрабатываем только закрытые свечи
            if candle['is_closed']:
                logger.debug(
                    f"Processed candle: {candle['symbol']} {candle['interval']} "
                    f"O:{candle['open']} H:{candle['high']} "
                    f"L:{candle['low']} C:{candle['close']}"
                )
                return candle
            
            return None
            
        except orjson.JSONDecodeError as e:
            self.errors_count += 1
            logger.error(f"JSON decode error: {e}")
            return None
        except KeyError as e:
            self.errors_count += 1
            logger.error(f"Missing key in message: {e}")
            return None
        except ValueError as e:
            self.errors_count += 1
            logger.error(f"Value conversion error: {e}")
            return None
        except Exception as e:
            self.errors_count += 1
            logger.error(f"Unexpected error handling message: {e}")
            return None
    
    def validate_candle_data(self, candle: Dict[str, Any]) -> bool:
        """Валидация данных свечи.
        
        Args:
            candle: Данные свечи
            
        Returns:
            True, если данные валидны
        """
        try:
            required_fields = ['symbol', 'interval', 'open', 'high', 'low', 'close', 'volume']
            
            # Проверяем наличие всех полей
            for field in required_fields:
                if field not in candle:
                    logger.warning(f"Missing field in candle data: {field}")
                    return False
            
            # Проверяем типы данных
            if not isinstance(candle['symbol'], str) or not candle['symbol']:
                logger.warning("Invalid symbol in candle data")
                return False
            
            if not isinstance(candle['interval'], str) or not candle['interval']:
                logger.warning("Invalid interval in candle data")
                return False
            
            # Проверяем числовые значения
            numeric_fields = ['open', 'high', 'low', 'close', 'volume']
            for field in numeric_fields:
                if not isinstance(candle[field], (int, float)) or candle[field] < 0:
                    logger.warning(f"Invalid {field} in candle data: {candle[field]}")
                    return False
            
            # Проверяем логику цен
            prices = [candle['open'], candle['high'], candle['low'], candle['close']]
            if candle['high'] < max(candle['open'], candle['close']):
                logger.warning("High price is less than max of open/close")
                return False
            
            if candle['low'] > min(candle['open'], candle['close']):
                logger.warning("Low price is greater than min of open/close")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating candle data: {e}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Получение статистики обработки сообщений."""
        return {
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "success_rate": (
                (self.messages_processed - self.errors_count) / max(1, self.messages_processed)
            ) * 100
        }
    
    def reset_stats(self) -> None:
        """Сброс статистики."""
        self.messages_processed = 0
        self.errors_count = 0
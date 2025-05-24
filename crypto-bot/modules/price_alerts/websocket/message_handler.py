# modules/price_alerts/websocket/message_handler.py
"""Адаптированный обработчик WebSocket сообщений."""

import orjson
from typing import Optional, Dict, Any
from shared.utils.logger import get_module_logger

logger = get_module_logger("message_handler")


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
            Данные свечи если это закрытая свеча, иначе None
        """
        try:
            self.messages_processed += 1
            
            # Парсим JSON
            data = orjson.loads(message)
            
            # Проверяем структуру (Binance kline stream)
            if 'data' not in data or 'k' not in data['data']:
                logger.debug("Message doesn't contain kline data")
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
                    f"Change: {((candle['close'] - candle['open']) / candle['open'] * 100):.2f}%"
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
        except (ValueError, TypeError, ZeroDivisionError) as e:
            self.errors_count += 1
            logger.error(f"Data conversion error: {e}")
            return None
        except Exception as e:
            self.errors_count += 1
            logger.error(f"Unexpected error: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики обработки."""
        total = max(1, self.messages_processed)
        success_rate = ((total - self.errors_count) / total) * 100
        
        return {
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "success_rate": round(success_rate, 2)
        }
    
    def reset_stats(self) -> None:
        """Сброс статистики."""
        self.messages_processed = 0
        self.errors_count = 0
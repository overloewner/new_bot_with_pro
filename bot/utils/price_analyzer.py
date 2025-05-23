"""Анализатор изменения цен."""

from decimal import Decimal, getcontext
from typing import Dict, Any
from bot.core.logger import get_logger

logger = get_logger(__name__)


class PriceAnalyzer:
    """Анализатор изменения цен свечей."""
    
    def __init__(self, precision: int = 8):
        """Инициализация анализатора.
        
        Args:
            precision: Точность вычислений для Decimal
        """
        getcontext().prec = precision
        self._zero = Decimal(0)
    
    def calculate_change(self, open_price: float, close_price: float) -> Decimal:
        """Вычисление процентного изменения цены.
        
        Args:
            open_price: Цена открытия
            close_price: Цена закрытия
            
        Returns:
            Процентное изменение цены
        """
        try:
            open_dec = Decimal(str(open_price))
            
            if open_dec == self._zero:
                logger.warning(f"Open price is zero for calculation")
                return self._zero
            
            close_dec = Decimal(str(close_price))
            change = ((close_dec - open_dec) / open_dec) * 100
            
            return change
        except Exception as e:
            logger.error(f"Error calculating price change: {e}")
            return self._zero
    
    def analyze_candle(self, candle_data: Dict[str, Any]) -> Dict[str, Any]:
        """Анализ данных свечи.
        
        Args:
            candle_data: Данные свечи
            
        Returns:
            Результат анализа
        """
        try:
            price_change = self.calculate_change(
                candle_data['open'], 
                candle_data['close']
            )
            
            direction = "🟢" if price_change > 0 else "🔴" if price_change < 0 else "⚪"
            change_percent = f"{abs(price_change):.2f}%"
            
            return {
                "price_change": price_change,
                "direction": direction,
                "change_percent": change_percent,
                "symbol": candle_data['symbol'],
                "interval": candle_data['interval'],
                "open": candle_data['open'],
                "close": candle_data['close'],
                "high": candle_data['high'],
                "low": candle_data['low'],
                "volume": candle_data['volume']
            }
        except Exception as e:
            logger.error(f"Error analyzing candle: {e}")
            return {
                "price_change": self._zero,
                "direction": "❓",
                "change_percent": "0.00%",
                "symbol": candle_data.get('symbol', 'UNKNOWN'),
                "interval": candle_data.get('interval', 'UNKNOWN'),
                "open": candle_data.get('open', 0),
                "close": candle_data.get('close', 0),
                "high": candle_data.get('high', 0),
                "low": candle_data.get('low', 0),
                "volume": candle_data.get('volume', 0)
            }
    
    def format_alert_message(self, analysis: Dict[str, Any]) -> str:
        """Форматирование сообщения алерта.
        
        Args:
            analysis: Результат анализа свечи
            
        Returns:
            Отформатированное сообщение
        """
        return (
            f"{analysis['direction']} {analysis['symbol']} {analysis['interval']}: "
            f"{analysis['change_percent']} "
            f"(O:{analysis['open']} C:{analysis['close']})"
        )
    
    def should_trigger_alert(self, analysis: Dict[str, Any], threshold: float) -> bool:
        """Проверка необходимости отправки алерта.
        
        Args:
            analysis: Результат анализа свечи
            threshold: Пороговое значение в процентах
            
        Returns:
            True, если нужно отправить алерт
        """
        try:
            price_change = abs(analysis['price_change'])
            return price_change >= Decimal(str(threshold))
        except Exception as e:
            logger.error(f"Error checking alert threshold: {e}")
            return False
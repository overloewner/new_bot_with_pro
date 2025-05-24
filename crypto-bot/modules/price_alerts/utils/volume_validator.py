# modules/price_alerts/utils/volume_validator.py
"""Валидатор объемов торгов."""

from typing import List, Dict, Any
from shared.utils.validators import ValidationError
from shared.utils.logger import get_module_logger

logger = get_module_logger("volume_validator")


class VolumeValidator:
    """Валидатор объемов торгов."""
    
    @staticmethod
    def validate_volume(volume: Any) -> float:
        """Валидация минимального объема."""
        if not isinstance(volume, (int, float, str)):
            raise ValidationError("Volume must be a number")
        
        try:
            volume = float(volume)
        except ValueError:
            raise ValidationError("Invalid volume format")
        
        if volume < 0:
            raise ValidationError("Volume cannot be negative")
        
        if volume > 1e12:  # 1 триллион
            raise ValidationError("Volume too large")
        
        return volume
    
    @staticmethod
    def filter_tokens_by_volume(tokens_data: List[Dict[str, Any]], min_volume: float) -> List[str]:
        """Фильтрация токенов по минимальному объему.
        
        Args:
            tokens_data: Список данных токенов с объемами
            min_volume: Минимальный объем
            
        Returns:
            Список символов токенов
        """
        try:
            filtered_tokens = []
            
            for token in tokens_data:
                symbol = token.get('symbol', '')
                volume = float(token.get('quoteVolume', 0))
                
                if volume >= min_volume and symbol.endswith('USDT'):
                    filtered_tokens.append(symbol)
            
            logger.info(f"Filtered {len(filtered_tokens)} tokens with volume >= {min_volume}")
            return filtered_tokens
            
        except Exception as e:
            logger.error(f"Error filtering tokens by volume: {e}")
            return []
    
    @staticmethod
    def get_volume_stats(tokens_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Получение статистики объемов.
        
        Args:
            tokens_data: Список данных токенов
            
        Returns:
            Статистика объемов
        """
        try:
            if not tokens_data:
                return {"total": 0, "min": 0, "max": 0, "avg": 0}
            
            volumes = [float(token.get('quoteVolume', 0)) for token in tokens_data]
            
            return {
                "total": len(volumes),
                "min": min(volumes) if volumes else 0,
                "max": max(volumes) if volumes else 0,
                "avg": sum(volumes) / len(volumes) if volumes else 0,
                "above_1m": len([v for v in volumes if v > 1_000_000]),
                "above_10m": len([v for v in volumes if v > 10_000_000]),
                "above_100m": len([v for v in volumes if v > 100_000_000])
            }
            
        except Exception as e:
            logger.error(f"Error calculating volume stats: {e}")
            return {"total": 0, "min": 0, "max": 0, "avg": 0}
"""Валидаторы для данных."""

import re
from typing import List, Any
from bot.core.exceptions import ValidationError


class PresetValidator:
    """Валидатор данных пресетов."""
    
    @staticmethod
    def validate_preset_name(name: str) -> str:
        """Валидация имени пресета."""
        if not isinstance(name, str):
            raise ValidationError("Preset name must be a string")
        
        name = name.strip()
        if not name:
            raise ValidationError("Preset name cannot be empty")
        
        if len(name) > 50:
            raise ValidationError("Preset name too long (max 50 characters)")
        
        # Проверяем на недопустимые символы
        if not re.match(r'^[a-zA-Z0-9а-яА-Я\s_-]+$', name):
            raise ValidationError("Preset name contains invalid characters")
        
        return name
    
    @staticmethod
    def validate_pairs(pairs: List[str]) -> List[str]:
        """Валидация списка торговых пар."""
        if not isinstance(pairs, list):
            raise ValidationError("Pairs must be a list")
        
        if not pairs:
            raise ValidationError("Pairs list cannot be empty")
        
        if len(pairs) > 500:
            raise ValidationError("Too many pairs (max 500)")
        
        validated_pairs = []
        for pair in pairs:
            if not isinstance(pair, str):
                raise ValidationError(f"Invalid pair type: {type(pair)}")
            
            pair = pair.strip().upper()
            if not re.match(r'^[A-Z0-9]+USDT$', pair):
                raise ValidationError(f"Invalid pair format: {pair}")
            
            validated_pairs.append(pair)
        
        return list(set(validated_pairs))  # Убираем дубли
    
    @staticmethod
    def validate_interval(interval: str) -> str:
        """Валидация интервала."""
        if not isinstance(interval, str):
            raise ValidationError("Interval must be a string")
        
        valid_intervals = ["1s", "1m", "5m", "15m", "1h", "4h", "1d"]
        if interval not in valid_intervals:
            raise ValidationError(f"Invalid interval: {interval}")
        
        return interval
    
    @staticmethod
    def validate_percent(percent: float) -> float:
        """Валидация процента изменения."""
        if not isinstance(percent, (int, float)):
            raise ValidationError("Percent must be a number")
        
        if percent <= 0:
            raise ValidationError("Percent must be positive")
        
        if percent > 1000:
            raise ValidationError("Percent too large (max 1000%)")
        
        return round(float(percent), 2)


class UserValidator:
    """Валидатор данных пользователей."""
    
    @staticmethod
    def validate_user_id(user_id: Any) -> int:
        """Валидация ID пользователя."""
        if not isinstance(user_id, (int, str)):
            raise ValidationError("User ID must be integer or string")
        
        try:
            user_id = int(user_id)
        except ValueError:
            raise ValidationError("Invalid user ID format")
        
        if user_id <= 0:
            raise ValidationError("User ID must be positive")
        
        return user_id


class VolumeValidator:
    """Валидатор объема торгов."""
    
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
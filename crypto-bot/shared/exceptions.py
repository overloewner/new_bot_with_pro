# core/exceptions.py
"""Общие исключения приложения."""

class BotException(Exception):
    """Базовое исключение бота."""
    pass

class ConfigurationError(BotException):
    """Ошибка конфигурации."""
    pass

class DatabaseError(BotException):
    """Ошибка базы данных."""
    pass

class WebSocketError(BotException):
    """Ошибка WebSocket соединения."""
    pass

class ValidationError(BotException):
    """Ошибка валидации данных."""
    pass

class UserNotFoundError(BotException):
    """Пользователь не найден."""
    pass

class PresetNotFoundError(BotException):
    """Пресет не найден."""
    pass

class RateLimitError(BotException):
    """Превышен лимит запросов."""
    pass
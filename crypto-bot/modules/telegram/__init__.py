# modules/telegram/__init__.py
"""Инициализация модуля Telegram."""

from .service import TelegramService
from .handlers.main_handler import MainHandler
from .handlers.price_alerts_handler import PriceAlertsHandler
from .keyboards.main_keyboards import MainKeyboards
from .middleware.logging_middleware import LoggingMiddleware

__all__ = [
    'TelegramService',
    'MainHandler', 
    'PriceAlertsHandler',
    'MainKeyboards',
    'LoggingMiddleware'
]
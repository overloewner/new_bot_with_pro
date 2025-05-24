"""Инициализация модуля отслеживания китов."""

from .service import LimitedWhaleService
from .handlers.whale_handlers import WhaleHandlers, WhaleStates

__all__ = ['LimitedWhaleService', 'WhaleHandlers', 'WhaleStates']
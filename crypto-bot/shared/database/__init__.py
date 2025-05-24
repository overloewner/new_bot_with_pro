# shared/database/__init__.py
"""Инициализация модуля базы данных."""

from .manager import DatabaseManager
from .models import Base, User, PricePreset, GasAlert, WhaleAlert, WalletAlert, AlertLog, SystemStats  # ИСПРАВЛЕНИЕ: Изменено Preset на PricePreset
from .repositories.base_repository import BaseRepository

__all__ = [
    'DatabaseManager',
    'Base',
    'User',
    'PricePreset',  # ИСПРАВЛЕНИЕ: Изменено с Preset на PricePreset
    'GasAlert',
    'WhaleAlert',
    'WalletAlert',
    'AlertLog',
    'SystemStats',
    'BaseRepository'
]
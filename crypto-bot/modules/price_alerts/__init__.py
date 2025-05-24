# modules/price_alerts/__init__.py
"""Модуль ценовых алертов."""

from .service import PriceAlertsService
from .handlers.preset_handler import PresetHandler
from .handlers.config_handler import ConfigHandler

__all__ = [
    'PriceAlertsService',
    'PresetHandler',
    'ConfigHandler'
]
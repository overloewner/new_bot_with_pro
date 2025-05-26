# shared/events/__init__.py
"""Инициализация модуля событий."""

from .bus import EventBus, Event
from .types import *

# Глобальная шина событий
event_bus = EventBus()

__all__ = [
    'EventBus', 
    'Event', 
    'event_bus',
    # Типы событий
    'PRICE_ALERT_TRIGGERED',
    'PRICE_DATA_UPDATED',
    'CANDLE_PROCESSED', 
    'GAS_PRICE_UPDATED',
    'GAS_ALERT_TRIGGERED',
    'WHALE_TRANSACTION_DETECTED',
    'WHALE_ALERT_TRIGGERED',
    'WALLET_TRANSACTION_DETECTED', 
    'WALLET_ALERT_TRIGGERED',
    'USER_COMMAND_RECEIVED',
    'MESSAGE_SENT',
    'MODULE_STARTED',
    'MODULE_STOPPED',
    'ERROR_OCCURRED',
    'HEALTH_CHECK',
    'APPLICATION_STARTED',
    'APPLICATION_STOPPED'
]
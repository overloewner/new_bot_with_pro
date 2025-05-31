# core/events/__init__.py
"""Инициализация модуля событий."""

from .bus import EventBus, Event

# Глобальная шина событий
event_bus = EventBus()

# Типы событий
PRICE_ALERT_TRIGGERED = "price_alert.triggered"
PRICE_DATA_UPDATED = "price_alert.data_updated"
CANDLE_PROCESSED = "price_alert.candle_processed"

GAS_PRICE_UPDATED = "gas.price_updated"
GAS_ALERT_TRIGGERED = "gas.alert_triggered"

WHALE_TRANSACTION_DETECTED = "whale.transaction_detected"
WHALE_ALERT_TRIGGERED = "whale.alert_triggered"

WALLET_TRANSACTION_DETECTED = "wallet.transaction_detected"
WALLET_ALERT_TRIGGERED = "wallet.alert_triggered"

USER_COMMAND_RECEIVED = "telegram.command_received"
MESSAGE_SENT = "telegram.message_sent"

MODULE_STARTED = "system.module_started"
MODULE_STOPPED = "system.module_stopped"
ERROR_OCCURRED = "system.error"
HEALTH_CHECK = "system.health_check"
APPLICATION_STARTED = "system.application_started"
APPLICATION_STOPPED = "system.application_stopped"

__all__ = [
    'EventBus', 
    'Event', 
    'event_bus',
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
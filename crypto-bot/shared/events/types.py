# shared/events/types.py
"""Типы событий для модулей - исправленная версия."""

# События ценовых алертов
PRICE_ALERT_TRIGGERED = "price_alert.triggered"
PRICE_DATA_UPDATED = "price_alert.data_updated"
CANDLE_PROCESSED = "price_alert.candle_processed"

# События газа
GAS_PRICE_UPDATED = "gas.price_updated"
GAS_ALERT_TRIGGERED = "gas.alert_triggered"

# События китов
WHALE_TRANSACTION_DETECTED = "whale.transaction_detected"
WHALE_ALERT_TRIGGERED = "whale.alert_triggered"

# События кошельков
WALLET_TRANSACTION_DETECTED = "wallet.transaction_detected"
WALLET_ALERT_TRIGGERED = "wallet.alert_triggered"

# Telegram события
USER_COMMAND_RECEIVED = "telegram.command_received"
MESSAGE_SENT = "telegram.message_sent"

# Системные события
MODULE_STARTED = "system.module_started"
MODULE_STOPPED = "system.module_stopped"
ERROR_OCCURRED = "system.error"
HEALTH_CHECK = "system.health_check"
APPLICATION_STARTED = "system.application_started"
APPLICATION_STOPPED = "system.application_stopped"
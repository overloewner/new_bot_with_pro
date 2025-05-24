# modules/price_alerts/services/__init__.py
"""Сервисы price alerts (адаптация существующего кода)."""

# Здесь будут адаптированные версии существующих сервисов:
# - candle_service.py (из bot/services/)
# - alert_service.py (из bot/services/)
# - preset_service.py (из bot/services/)
# - token_service.py (из bot/services/)

# Пока импортируем существующие
from bot.services.candle_service import CandleService
from bot.services.alert_service import AlertService
from bot.services.preset_service import PresetService
from bot.services.token_service import TokenService

__all__ = [
    'CandleService',
    'AlertService', 
    'PresetService',
    'TokenService'
]

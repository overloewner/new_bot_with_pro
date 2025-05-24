# modules/price_alerts/services/__init__.py
"""Сервисы price alerts (адаптация существующего кода)."""

# Здесь будут адаптированные версии существующих сервисов:
# - candle_service.py (из bot/services/)
# - alert_service.py (из bot/services/)
# - preset_service.py (из bot/services/)
# - token_service.py (из bot/services/)

# Пока импортируем существующие
from .candle_service import CandleService
from .alert_service import AlertService
from .preset_service import PresetService
from .alert_service import TokenService

__all__ = [
    'CandleService',
    'AlertService', 
    'PresetService',
    'TokenService'
]

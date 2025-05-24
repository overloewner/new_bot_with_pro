# modules/price_alerts/websocket/__init__.py
"""WebSocket компоненты (адаптация существующего кода)."""

# Импортируем существующие компоненты
from bot.websocket.client import BinanceWebSocketClient
from bot.websocket.message_handler import MessageHandler
from bot.websocket.reconnect_manager import ReconnectManager

__all__ = [
    'BinanceWebSocketClient',
    'MessageHandler',
    'ReconnectManager'
]

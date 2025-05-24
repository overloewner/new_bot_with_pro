# modules/telegram/middleware/logging_middleware.py
"""Middleware для логирования действий пользователей."""

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED

import logging

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования и аналитики."""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события."""
        
        # Логируем действие пользователя
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
            username = event.from_user.username
            
            # Определяем тип события
            event_type = "unknown"
            event_data = {"user_id": user_id, "username": username}
            
            if hasattr(event, 'text') and event.text:
                event_type = "message"
                event_data["text"] = event.text[:100]  # Первые 100 символов
            elif hasattr(event, 'data') and event.data:
                event_type = "callback"
                event_data["callback_data"] = event.data
            
            # Публикуем событие
            await event_bus.publish(Event(
                type=USER_COMMAND_RECEIVED,
                data=event_data,
                source_module="telegram"  # ИСПРАВЛЕНО: используем source_module вместо module
            ))
            
            logger.info(f"User {user_id} ({username}) - {event_type}: {event_data}")
        
        # Вызываем основной обработчик
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(f"Error in handler: {e}")
            
            # Публикуем событие об ошибке
            await event_bus.publish(Event(
                type="system.error",
                data={
                    "error": str(e),
                    "handler": handler.__name__,
                    "user_id": getattr(event, 'from_user', {}).get('id') if hasattr(event, 'from_user') else None
                },
                source_module="telegram"  # ИСПРАВЛЕНО: используем source_module вместо module
            ))
            
            # Пробрасываем ошибку дальше
            raise
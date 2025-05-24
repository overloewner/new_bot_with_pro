# shared/events/bus.py
"""Система событий для связи между модулями."""

import asyncio
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Базовый класс события."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_module: str = "unknown"  # ИСПРАВЛЕНО: переименовано с module_source
    correlation_id: Optional[str] = None


class EventBus:
    """Шина событий для модульной коммуникации."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._middleware: List[Callable] = []
        self._event_history: List[Event] = []
        self._max_history = 1000
        
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Подписка на тип события."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__name__} to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Отписка от события."""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
                logger.debug(f"Unsubscribed {handler.__name__} from {event_type}")
            except ValueError:
                pass
    
    def add_middleware(self, middleware: Callable) -> None:
        """Добавление middleware для обработки событий."""
        self._middleware.append(middleware)
    
    async def publish(self, event: Event) -> None:
        """Публикация события."""
        try:
            # Применяем middleware
            for middleware in self._middleware:
                try:
                    await middleware(event)
                except Exception as e:
                    logger.error(f"Middleware error: {e}")
            
            # Сохраняем в историю
            self._store_event(event)
            
            # Отправляем подписчикам
            handlers = self._subscribers.get(event.type, [])
            if handlers:
                tasks = []
                for handler in handlers:
                    task = asyncio.create_task(self._safe_call_handler(handler, event))
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
            
            logger.debug(f"Published event {event.type} to {len(handlers)} handlers")
            
        except Exception as e:
            logger.error(f"Error publishing event {event.type}: {e}")
    
    async def _safe_call_handler(self, handler: Callable, event: Event) -> None:
        """Безопасный вызов обработчика события."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            logger.error(f"Handler {handler.__name__} failed for event {event.type}: {e}")
    
    def _store_event(self, event: Event) -> None:
        """Сохранение события в историю."""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
    
    def get_events_by_type(self, event_type: str, limit: int = 100) -> List[Event]:
        """Получение событий по типу."""
        events = [e for e in self._event_history if e.type == event_type]
        return events[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика шины событий."""
        return {
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
            "middleware_count": len(self._middleware),
            "history_size": len(self._event_history),
            "total_event_types": len(set(e.type for e in self._event_history))
        }
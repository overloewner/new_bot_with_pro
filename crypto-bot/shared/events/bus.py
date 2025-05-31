# core/events/bus.py
"""Упрощенная система событий."""

import asyncio
import time
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)

@dataclass
class Event:
    """Класс события."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_module: str = "unknown"

class EventBus:
    """Упрощенная шина событий."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_history: deque = deque(maxlen=1000)
        self._running = False
    
    async def start(self):
        """Запуск EventBus."""
        if self._running:
            return
        self._running = True
        logger.info("EventBus started")
    
    async def stop(self):
        """Остановка EventBus."""
        self._running = False
        logger.info("EventBus stopped")
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Подписка на тип события."""
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Отписка от события."""
        try:
            self._subscribers[event_type].remove(handler)
        except ValueError:
            pass
    
    async def publish(self, event: Event) -> bool:
        """Публикация события."""
        if not self._running:
            return False
        
        success_count = 0
        
        try:
            # Сохраняем в историю
            self._event_history.append({
                'type': event.type,
                'source_module': event.source_module,
                'timestamp': event.timestamp
            })
            
            # Получаем обработчики
            handlers = self._subscribers.get(event.type, [])
            
            if not handlers:
                return False
            
            # Обрабатываем событие
            tasks = []
            for handler in handlers:
                task = asyncio.create_task(self._safe_call_handler(handler, event))
                tasks.append(task)
            
            # Ждем завершения всех обработчиков
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Подсчитываем успешные обработки
            for result in results:
                if not isinstance(result, Exception):
                    success_count += 1
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error publishing event {event.type}: {e}")
            return False
    
    async def _safe_call_handler(self, handler: Callable, event: Event) -> Any:
        """Безопасный вызов обработчика."""
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(event)
            else:
                return handler(event)
        except Exception as e:
            logger.error(f"Handler {handler.__name__} failed: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика шины событий."""
        return {
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
            "total_handlers": sum(len(handlers) for handlers in self._subscribers.values()),
            "history_size": len(self._event_history),
            "event_types": len(self._subscribers),
            "running": self._running
        }
    
    def get_events_by_type(self, event_type: str, limit: int = 100) -> List[Dict]:
        """Получение событий по типу."""
        events = [e for e in self._event_history if e['type'] == event_type]
        return list(events)[-limit:]
# shared/events/bus.py
"""Улучшенная система событий с error handling и circuit breaker."""

import asyncio
import time
import traceback
from typing import Dict, List, Callable, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, deque
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Приоритет события."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """Улучшенный класс события."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_module: str = "unknown"
    correlation_id: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class HandlerStats:
    """Статистика обработчика."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    avg_execution_time: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    circuit_breaker_open: bool = False
    circuit_breaker_failures: int = 0


class EventBus:
    """Улучшенная шина событий с error handling."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._middleware: List[Callable] = []
        self._event_history: deque = deque(maxlen=5000)  # Увеличен размер истории
        
        # Статистика и мониторинг
        self._handler_stats: Dict[str, HandlerStats] = defaultdict(HandlerStats)
        self._failed_events: deque = deque(maxlen=1000)
        self._event_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'count': 0,
            'last_seen': None,
            'avg_processing_time': 0.0
        })
        
        # Circuit breaker settings
        self._circuit_breaker_threshold = 5  # failures
        self._circuit_breaker_timeout = 300  # 5 minutes
        
        # Background task для очистки
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Запуск EventBus."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("EventBus started")
    
    async def stop(self):
        """Остановка EventBus."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus stopped")
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Подписка на тип события."""
        handler_key = f"{handler.__module__}.{handler.__name__}"
        
        self._subscribers[event_type].append(handler)
        
        # Инициализируем статистику
        if handler_key not in self._handler_stats:
            self._handler_stats[handler_key] = HandlerStats()
        
        logger.debug(f"Subscribed {handler_key} to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Отписка от события."""
        try:
            self._subscribers[event_type].remove(handler)
            handler_key = f"{handler.__module__}.{handler.__name__}"
            logger.debug(f"Unsubscribed {handler_key} from {event_type}")
        except ValueError:
            pass
    
    def add_middleware(self, middleware: Callable) -> None:
        """Добавление middleware."""
        self._middleware.append(middleware)
        logger.debug(f"Added middleware: {middleware.__name__}")
    
    async def publish(self, event: Event) -> bool:
        """
        Публикация события с error handling.
        
        Returns:
            bool: True если хотя бы один handler успешно обработал событие
        """
        if not self._running:
            logger.warning("EventBus not running, dropping event")
            return False
        
        start_time = time.time()
        success_count = 0
        
        try:
            # Применяем middleware
            for middleware in self._middleware:
                try:
                    await self._execute_with_timeout(middleware(event), timeout=5.0)
                except Exception as e:
                    logger.error(f"Middleware {middleware.__name__} failed: {e}")
            
            # Сохраняем в историю
            self._store_event(event)
            
            # Получаем обработчики
            handlers = self._subscribers.get(event.type, [])
            
            if not handlers:
                logger.debug(f"No handlers for event type: {event.type}")
                return False
            
            # Обрабатываем событие параллельно
            tasks = []
            for handler in handlers:
                task = asyncio.create_task(
                    self._safe_call_handler(handler, event)
                )
                tasks.append(task)
            
            # Ждем завершения всех обработчиков
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Подсчитываем успешные обработки
            for result in results:
                if result is True or (result is not None and not isinstance(result, Exception)):
                    success_count += 1
            
            processing_time = time.time() - start_time
            
            # Обновляем метрики
            self._update_event_metrics(event.type, processing_time)
            
            logger.debug(
                f"Published {event.type}: {success_count}/{len(handlers)} handlers succeeded "
                f"in {processing_time:.3f}s"
            )
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Critical error publishing event {event.type}: {e}")
            self._failed_events.append({
                'event': event,
                'error': str(e),
                'timestamp': datetime.utcnow()
            })
            return False
    
    async def _safe_call_handler(self, handler: Callable, event: Event) -> Any:
        """Безопасный вызов обработчика с circuit breaker."""
        handler_key = f"{handler.__module__}.{handler.__name__}"
        stats = self._handler_stats[handler_key]
        
        # Проверяем circuit breaker
        if self._is_circuit_breaker_open(handler_key):
            logger.warning(f"Circuit breaker open for {handler_key}")
            return None
        
        start_time = time.time()
        
        try:
            stats.total_calls += 1
            
            # Выполняем обработчик с таймаутом
            if asyncio.iscoroutinefunction(handler):
                result = await self._execute_with_timeout(
                    handler(event), 
                    timeout=30.0  # 30 секунд максимум на обработчик
                )
            else:
                # Для синхронных обработчиков
                result = await asyncio.get_event_loop().run_in_executor(
                    None, handler, event
                )
            
            execution_time = time.time() - start_time
            
            # Обновляем статистику успеха
            stats.successful_calls += 1
            stats.avg_execution_time = (
                (stats.avg_execution_time * (stats.successful_calls - 1) + execution_time) /
                stats.successful_calls
            )
            stats.circuit_breaker_failures = 0  # Сбрасываем счетчик неудач
            
            if execution_time > 5.0:  # Предупреждение о медленных обработчиках
                logger.warning(f"Slow handler {handler_key}: {execution_time:.3f}s")
            
            return result
            
        except asyncio.TimeoutError:
            stats.failed_calls += 1
            stats.circuit_breaker_failures += 1
            error_msg = f"Handler {handler_key} timed out"
            logger.error(error_msg)
            self._update_handler_error(handler_key, error_msg)
            return None
            
        except Exception as e:
            stats.failed_calls += 1
            stats.circuit_breaker_failures += 1
            error_msg = f"Handler {handler_key} failed: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self._update_handler_error(handler_key, error_msg)
            
            # Проверяем нужно ли открыть circuit breaker
            if stats.circuit_breaker_failures >= self._circuit_breaker_threshold:
                stats.circuit_breaker_open = True
                logger.error(f"Circuit breaker opened for {handler_key}")
            
            return None
    
    async def _execute_with_timeout(self, coro, timeout: float):
        """Выполнение корутины с таймаутом."""
        return await asyncio.wait_for(coro, timeout=timeout)
    
    def _is_circuit_breaker_open(self, handler_key: str) -> bool:
        """Проверка состояния circuit breaker."""
        stats = self._handler_stats[handler_key]
        
        if not stats.circuit_breaker_open:
            return False
        
        # Проверяем таймаут circuit breaker
        if (stats.last_error_time and 
            (datetime.utcnow() - stats.last_error_time).total_seconds() > self._circuit_breaker_timeout):
            # Пробуем восстановить
            stats.circuit_breaker_open = False
            stats.circuit_breaker_failures = 0
            logger.info(f"Circuit breaker reset for {handler_key}")
            return False
        
        return True
    
    def _update_handler_error(self, handler_key: str, error_msg: str):
        """Обновление информации об ошибке обработчика."""
        stats = self._handler_stats[handler_key]
        stats.last_error = error_msg
        stats.last_error_time = datetime.utcnow()
    
    def _store_event(self, event: Event) -> None:
        """Сохранение события в историю."""
        self._event_history.append({
            'type': event.type,
            'source_module': event.source_module,
            'timestamp': event.timestamp,
            'priority': event.priority.name,
            'data_size': len(str(event.data))
        })
    
    def _update_event_metrics(self, event_type: str, processing_time: float):
        """Обновление метрик событий."""
        metrics = self._event_metrics[event_type]
        metrics['count'] += 1
        metrics['last_seen'] = datetime.utcnow()
        
        # Обновляем среднее время обработки
        if metrics['avg_processing_time'] == 0:
            metrics['avg_processing_time'] = processing_time
        else:
            metrics['avg_processing_time'] = (
                metrics['avg_processing_time'] * 0.9 + processing_time * 0.1
            )
    
    async def _cleanup_loop(self):
        """Фоновая задача очистки."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                
                # Очищаем старые ошибки
                cutoff_time = datetime.utcnow().timestamp() - 3600  # 1 час назад
                
                # Сбрасываем circuit breakers если прошло достаточно времени
                reset_count = 0
                for handler_key, stats in self._handler_stats.items():
                    if (stats.circuit_breaker_open and 
                        stats.last_error_time and
                        stats.last_error_time.timestamp() < cutoff_time):
                        stats.circuit_breaker_open = False
                        stats.circuit_breaker_failures = 0
                        reset_count += 1
                
                if reset_count > 0:
                    logger.info(f"Reset {reset_count} circuit breakers")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    def get_events_by_type(self, event_type: str, limit: int = 100) -> List[Dict]:
        """Получение событий по типу."""
        events = [e for e in self._event_history if e['type'] == event_type]
        return list(events)[-limit:]
    
    def get_handler_stats(self, handler_key: Optional[str] = None) -> Dict:
        """Получение статистики обработчиков."""
        if handler_key:
            return self._handler_stats.get(handler_key, HandlerStats()).__dict__
        
        return {
            key: {
                'total_calls': stats.total_calls,
                'successful_calls': stats.successful_calls,
                'failed_calls': stats.failed_calls,
                'success_rate': (
                    stats.successful_calls / max(1, stats.total_calls) * 100
                ),
                'avg_execution_time': round(stats.avg_execution_time, 3),
                'circuit_breaker_open': stats.circuit_breaker_open,
                'last_error': stats.last_error
            }
            for key, stats in self._handler_stats.items()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Расширенная статистика шины событий."""
        total_handlers = sum(len(handlers) for handlers in self._subscribers.values())
        failed_handlers = sum(
            1 for stats in self._handler_stats.values() 
            if stats.circuit_breaker_open
        )
        
        return {
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
            "total_handlers": total_handlers,
            "failed_handlers": failed_handlers,
            "middleware_count": len(self._middleware),
            "history_size": len(self._event_history),
            "failed_events": len(self._failed_events),
            "event_types": len(self._event_metrics),
            "avg_processing_times": {
                event_type: round(metrics['avg_processing_time'], 3)
                for event_type, metrics in self._event_metrics.items()
            },
            "circuit_breakers_open": [
                handler_key for handler_key, stats in self._handler_stats.items()
                if stats.circuit_breaker_open
            ]
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка здоровья EventBus."""
        failed_handlers = [
            handler_key for handler_key, stats in self._handler_stats.items()
            if stats.circuit_breaker_open
        ]
        
        recent_errors = len([
            error for error in self._failed_events
            if (datetime.utcnow() - error['timestamp']).total_seconds() < 300
        ])
        
        health_status = "healthy"
        if failed_handlers:
            health_status = "degraded"
        if recent_errors > 10:
            health_status = "unhealthy"
        
        return {
            "status": health_status,
            "running": self._running,
            "failed_handlers": failed_handlers,
            "recent_errors": recent_errors,
            "total_events_processed": sum(
                stats.total_calls for stats in self._handler_stats.values()
            )
        }
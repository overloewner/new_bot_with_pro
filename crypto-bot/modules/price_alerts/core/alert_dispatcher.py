# modules/price_alerts/core/alert_dispatcher.py
"""Диспетчер алертов с батчингом и rate limiting."""

import asyncio
import time
from typing import Dict, Any, Set, List
from collections import defaultdict, deque

from shared.events import event_bus, Event
from shared.utils.logger import get_module_logger

logger = get_module_logger("alert_dispatcher")


class AlertDispatcher:
    """Диспетчер для отправки алертов с оптимизацией."""
    
    def __init__(self):
        self._running = False
        
        # Очереди для пользователей
        self._user_queues: Dict[int, asyncio.Queue] = defaultdict(
            lambda: asyncio.Queue(maxsize=1000)
        )
        self._user_tasks: Dict[int, asyncio.Task] = {}
        
        # Rate limiting
        self._user_limits: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=10)  # Последние 10 алертов
        )
        
        # Cooldown для предотвращения дублирования
        self._cooldowns: Dict[str, float] = {}
        self._cooldown_time = 60  # 1 минута
        
        # Конфигурация
        self.max_alerts_per_minute = 5
        self.batch_size = 3
        self.batch_timeout = 2.0  # 2 секунды
        
        # Статистика
        self._stats = {
            'total_dispatched': 0,
            'rate_limited': 0,
            'cooldown_blocked': 0,
            'active_users': 0
        }
    
    async def start(self):
        """Запуск диспетчера."""
        if self._running:
            return
        
        self._running = True
        
        # Задача очистки старых cooldown'ов
        asyncio.create_task(self._cleanup_cooldowns())
        
        logger.info("Alert dispatcher started")
    
    async def stop(self):
        """Остановка диспетчера."""
        self._running = False
        
        # Останавливаем все пользовательские задачи
        for task in self._user_tasks.values():
            task.cancel()
        
        if self._user_tasks:
            await asyncio.gather(*self._user_tasks.values(), return_exceptions=True)
        
        self._user_tasks.clear()
        logger.info("Alert dispatcher stopped")
    
    async def dispatch_alert(self, alert_data: Dict[str, Any], user_presets: Dict[int, Set[str]]):
        """Отправка алерта пользователям."""
        if not self._running:
            return
        
        # Создаем ключ для cooldown
        cooldown_key = f"{alert_data['symbol']}_{alert_data['interval']}_{alert_data['change_percent']}"
        
        # Проверяем cooldown
        if self._is_in_cooldown(cooldown_key):
            self._stats['cooldown_blocked'] += 1
            return
        
        # Устанавливаем cooldown
        self._cooldowns[cooldown_key] = time.time() + self._cooldown_time
        
        # Формируем сообщение
        message = self._format_alert_message(alert_data)
        
        # Отправляем каждому пользователю
        for user_id, preset_ids in user_presets.items():
            await self._queue_user_alert(user_id, message, preset_ids)
    
    async def _queue_user_alert(self, user_id: int, message: str, preset_ids: Set[str]):
        """Добавление алерта в очередь пользователя."""
        # Проверяем rate limit
        if not self._check_user_rate_limit(user_id):
            self._stats['rate_limited'] += 1
            return
        
        try:
            # Добавляем в очередь пользователя
            await self._user_queues[user_id].put({
                'message': message,
                'preset_ids': preset_ids,
                'timestamp': time.time()
            })
            
            # Создаем задачу обработки для пользователя если её нет
            if user_id not in self._user_tasks or self._user_tasks[user_id].done():
                self._user_tasks[user_id] = asyncio.create_task(
                    self._process_user_queue(user_id)
                )
            
        except asyncio.QueueFull:
            logger.warning(f"Queue full for user {user_id}")
    
    async def _process_user_queue(self, user_id: int):
        """Обработка очереди алертов для пользователя."""
        queue = self._user_queues[user_id]
        
        while self._running:
            try:
                # Собираем батч алертов
                batch = await self._collect_user_batch(queue)
                
                if not batch:
                    # Если нет алертов, завершаем задачу
                    break
                
                # Отправляем батч
                await self._send_user_batch(user_id, batch)
                
                # Пауза между батчами
                await asyncio.sleep(self.batch_timeout)
                
            except asyncio.CancelledError:
                logger.debug(f"User queue processor {user_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing user {user_id} queue: {e}")
                await asyncio.sleep(5)
    
    async def _collect_user_batch(self, queue: asyncio.Queue) -> List[Dict[str, Any]]:
        """Сбор батча алертов для пользователя."""
        batch = []
        start_time = time.time()
        
        while (len(batch) < self.batch_size and 
               time.time() - start_time < self.batch_timeout):
            
            try:
                remaining_time = self.batch_timeout - (time.time() - start_time)
                if remaining_time <= 0:
                    break
                
                alert = await asyncio.wait_for(
                    queue.get(),
                    timeout=max(0.1, remaining_time)
                )
                batch.append(alert)
                
            except asyncio.TimeoutError:
                break
        
        return batch
    
    async def _send_user_batch(self, user_id: int, batch: List[Dict[str, Any]]):
        """Отправка батча алертов пользователю."""
        if not batch:
            return
        
        try:
            if len(batch) == 1:
                # Одиночный алерт
                message = batch[0]['message']
            else:
                # Группируем множественные алерты
                messages = [alert['message'] for alert in batch]
                message = f"🚨 Групповой алерт ({len(batch)}):\n" + "\n".join(messages)
            
            # Ограничиваем длину сообщения
            if len(message) > 4000:
                message = message[:4000] + "\n... (обрезано)"
            
            # Отправляем через event bus
            await event_bus.publish(Event(
                type="price_alert.triggered",
                data={
                    "user_id": user_id,
                    "message": message,
                    "alert_count": len(batch)
                },
                source_module="price_alerts"
            ))
            
            self._stats['total_dispatched'] += len(batch)
            logger.debug(f"Sent {len(batch)} alerts to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending alerts to user {user_id}: {e}")
    
    def _check_user_rate_limit(self, user_id: int) -> bool:
        """Проверка rate limit для пользователя."""
        current_time = time.time()
        user_history = self._user_limits[user_id]
        
        # Очищаем старые записи (старше минуты)
        while user_history and current_time - user_history[0] > 60:
            user_history.popleft()
        
        # Проверяем лимит
        if len(user_history) >= self.max_alerts_per_minute:
            return False
        
        # Добавляем текущее время
        user_history.append(current_time)
        return True
    
    def _is_in_cooldown(self, key: str) -> bool:
        """Проверка cooldown."""
        cooldown_until = self._cooldowns.get(key, 0)
        return time.time() < cooldown_until
    
    def _format_alert_message(self, alert_data: Dict[str, Any]) -> str:
        """Форматирование сообщения алерта."""
        return (
            f"{alert_data['direction']} {alert_data['symbol']} {alert_data['interval']}: "
            f"{abs(alert_data['change_percent']):.2f}% "
            f"(${alert_data['close']:.4f})"
        )
    
    async def cleanup_user_queue(self, user_id: int):
        """Очистка очереди пользователя."""
        # Останавливаем задачу пользователя
        if user_id in self._user_tasks:
            self._user_tasks[user_id].cancel()
            try:
                await self._user_tasks[user_id]
            except asyncio.CancelledError:
                pass
            del self._user_tasks[user_id]
        
        # Очищаем очередь
        if user_id in self._user_queues:
            queue = self._user_queues[user_id]
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            del self._user_queues[user_id]
        
        # Очищаем rate limit
        if user_id in self._user_limits:
            del self._user_limits[user_id]
        
        logger.debug(f"Cleaned up queue for user {user_id}")
    
    async def _cleanup_cooldowns(self):
        """Периодическая очистка старых cooldown'ов."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                
                current_time = time.time()
                expired_keys = [
                    key for key, expire_time in self._cooldowns.items()
                    if current_time > expire_time
                ]
                
                for key in expired_keys:
                    del self._cooldowns[key]
                
                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired cooldowns")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cooldown cleanup: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        self._stats['active_users'] = len(self._user_tasks)
        self._stats['active_queues'] = len(self._user_queues)
        self._stats['total_cooldowns'] = len(self._cooldowns)
        
        return self._stats.copy()
"""Сервис алертов."""

import asyncio
import time
from collections import defaultdict
from typing import Dict, Set, List, Any
from aiogram import Bot

from bot.core.config import ProcessingConfig, RateLimitConfig
from bot.utils.rate_limiter import GlobalRateLimiter, UserRateLimiter
from bot.utils.price_analyzer import PriceAnalyzer
from bot.core.logger import get_logger

logger = get_logger(__name__)


class AlertService:
    """Сервис для обработки и отправки алертов."""
    
    def __init__(
        self, 
        bot: Bot, 
        processing_config: ProcessingConfig,
        rate_limit_config: RateLimitConfig
    ):
        self.bot = bot
        self.processing_config = processing_config
        self.rate_limit_config = rate_limit_config
        self.analyzer = PriceAnalyzer()
        
        # Ограничители запросов
        self.global_rate_limiter = GlobalRateLimiter(rate_limit_config)
        self.user_rate_limiter = UserRateLimiter(rate_limit_config)
        
        # Очереди для пользователей
        self._user_queues: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._user_flush_tasks: Dict[int, asyncio.Task] = {}
        
        # Кеш для предотвращения дублирования алертов
        self._cooldown: Dict[tuple, bool] = {}
        self._cooldown_lock = asyncio.Lock()
        
        # Блокировка для очередей
        self._queue_lock = asyncio.Lock()
        
        # Флаг работы
        self._running = False
    
    async def start(self) -> None:
        """Запуск сервиса алертов."""
        if self._running:
            return
        
        self._running = True
        logger.info("Alert service started")
    
    async def stop(self) -> None:
        """Остановка сервиса алертов."""
        self._running = False
        
        # Останавливаем все задачи отправки пользователям
        for task in self._user_flush_tasks.values():
            task.cancel()
        
        # Ждем завершения задач
        if self._user_flush_tasks:
            await asyncio.gather(*self._user_flush_tasks.values(), return_exceptions=True)
        
        self._user_flush_tasks.clear()
        logger.info("Alert service stopped")
    
    async def process_candle_alert(
        self, 
        candle_data: Dict[str, Any], 
        subscriptions: Dict[int, Set[str]]
    ) -> None:
        """Обработка алерта по свече.
        
        Args:
            candle_data: Данные свечи
            subscriptions: Подписки пользователей {user_id: {preset_ids}}
        """
        if not self._running or not subscriptions:
            return
        
        try:
            # Анализируем свечу
            analysis = self.analyzer.analyze_candle(candle_data)
            
            # Проверяем кулдаун
            stream_key = f"{candle_data['symbol'].lower()}@kline_{candle_data['interval']}"
            alert_key = (stream_key, str(analysis['price_change']))
            
            async with self._cooldown_lock:
                if alert_key in self._cooldown:
                    return
                self._cooldown[alert_key] = True
            
            # Планируем очистку кулдауна
            asyncio.create_task(self._clear_cooldown(alert_key))
            
            # Формируем сообщение
            message = self.analyzer.format_alert_message(analysis)
            
            # Добавляем алерты в очереди пользователей
            await self._add_alerts_to_queues(message, list(subscriptions.keys()))
            
        except Exception as e:
            logger.error(f"Error processing candle alert: {e}")
    
    async def _add_alerts_to_queues(self, message: str, user_ids: List[int]) -> None:
        """Добавление алертов в очереди пользователей."""
        async with self._queue_lock:
            for user_id in user_ids:
                # Создаем очередь и задачу отправки, если их нет
                if user_id not in self._user_queues:
                    self._user_queues[user_id] = asyncio.Queue()
                
                if user_id not in self._user_flush_tasks:
                    self._user_flush_tasks[user_id] = asyncio.create_task(
                        self._flush_user_alerts(user_id)
                    )
                
                # Добавляем сообщение в очередь
                try:
                    await self._user_queues[user_id].put(message)
                except Exception as e:
                    logger.error(f"Error adding alert to queue for user {user_id}: {e}")
    
    async def _flush_user_alerts(self, user_id: int) -> None:
        """Отправка батчей алертов пользователю."""
        while self._running:
            try:
                start_time = time.time()
                
                # Собираем сообщения из очереди
                messages = []
                queue = self._user_queues[user_id]
                
                # Используем правильный атрибут из конфигурации
                max_messages = getattr(
                    self.processing_config, 
                    'max_messages_per_batch', 
                    50  # значение по умолчанию
                )
                
                while (len(messages) < max_messages and not queue.empty()):
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=0.1)
                        messages.append(message)
                    except asyncio.TimeoutError:
                        break
                
                # Отправляем, если есть сообщения
                if messages:
                    await self._send_batch_to_user(user_id, messages)
                
                # Ждем до следующего интервала
                elapsed = time.time() - start_time
                sleep_time = max(0, self.processing_config.batch_timeout - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    # Короткая пауза, чтобы не блокировать event loop
                    await asyncio.sleep(0.01)
                
            except asyncio.CancelledError:
                logger.debug(f"Alert flush task cancelled for user {user_id}")
                break
            except Exception as e:
                logger.error(f"Error in flush task for user {user_id}: {e}")
                await asyncio.sleep(1)  # Небольшая пауза при ошибке
    
    async def _send_batch_to_user(self, user_id: int, messages: List[str]) -> None:
        """Отправка батча сообщений пользователю."""
        try:
            # Ждем разрешения от ограничителей
            await self.global_rate_limiter.acquire()
            await self.user_rate_limiter.wait_for_user(user_id)
            
            # Формируем итоговое сообщение
            if len(messages) == 1:
                batch_message = messages[0]
            else:
                batch_message = f"🚨 Алерты ({len(messages)}):\n" + "\n".join(messages)
            
            # Ограничиваем длину сообщения для Telegram (максимум 4096 символов)
            if len(batch_message) > 4000:
                batch_message = batch_message[:4000] + "\n... (сообщение обрезано)"
            
            # Отправляем
            await self.bot.send_message(chat_id=user_id, text=batch_message)
            
            logger.debug(f"Sent {len(messages)} alerts to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending alerts to user {user_id}: {e}")
        finally:
            self.global_rate_limiter.release()
    
    async def _clear_cooldown(self, key: tuple) -> None:
        """Очистка кеша алертов."""
        await asyncio.sleep(self.processing_config.cooldown_time)
        async with self._cooldown_lock:
            self._cooldown.pop(key, None)
    
    async def cleanup_user_queue(self, user_id: int) -> None:
        """Очистка очереди пользователя."""
        async with self._queue_lock:
            if user_id in self._user_flush_tasks:
                self._user_flush_tasks[user_id].cancel()
                del self._user_flush_tasks[user_id]
            
            if user_id in self._user_queues:
                # Очищаем очередь
                while not self._user_queues[user_id].empty():
                    try:
                        await self._user_queues[user_id].get()
                    except:
                        break
                del self._user_queues[user_id]
        
        logger.debug(f"Cleaned up queue for user {user_id}")
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Получение статистики очередей."""
        total_messages = sum(
            queue.qsize() for queue in self._user_queues.values()
        )
        
        return {
            "active_users": len(self._user_queues),
            "total_queued_messages": total_messages,
            "active_tasks": len(self._user_flush_tasks),
            "cooldown_entries": len(self._cooldown)
        }
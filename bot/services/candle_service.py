"""Сервис обработки свечей."""

import asyncio
import time
from typing import Dict, Any, List, Set
from collections import defaultdict

from bot.services.alert_service import AlertService
from bot.storage import Storage
from bot.core.config import ProcessingConfig
from bot.core.logger import get_logger

logger = get_logger(__name__)


class CandleService:
    """Сервис для обработки данных свечей."""
    
    def __init__(
        self, 
        alert_service: AlertService, 
        storage: Storage, 
        config: ProcessingConfig
    ):
        self.alert_service = alert_service
        self.storage = storage
        self.config = config
        
        # Очередь для входящих свечей
        self._candle_queue = asyncio.Queue(maxsize=config.max_queue_size)
        
        # Флаг работы
        self._running = False
        
        # Задачи обработки
        self._processing_tasks: List[asyncio.Task] = []
    
    async def start(self) -> None:
        """Запуск сервиса обработки свечей."""
        if self._running:
            return
        
        self._running = True
        
        # Запускаем сервис алертов
        await self.alert_service.start()
        
        # Запускаем задачи обработки
        self._processing_tasks = [
            asyncio.create_task(self._process_candles()),
            asyncio.create_task(self._monitor_queues())
        ]
        
        logger.info("Candle service started")
    
    async def stop(self) -> None:
        """Остановка сервиса обработки свечей."""
        self._running = False
        
        # Останавливаем задачи обработки
        for task in self._processing_tasks:
            task.cancel()
        
        if self._processing_tasks:
            await asyncio.gather(*self._processing_tasks, return_exceptions=True)
        
        self._processing_tasks.clear()
        
        # Останавливаем сервис алертов
        await self.alert_service.stop()
        
        logger.info("Candle service stopped")
    
    async def add_candle(self, candle_data: Dict[str, Any]) -> None:
        """Добавление свечи в очередь обработки."""
        if not self._running:
            return
        
        try:
            self._candle_queue.put_nowait(candle_data)
        except asyncio.QueueFull:
            logger.warning("Candle queue overflow, dropping oldest")
            try:
                # Удаляем старую свечу
                await asyncio.wait_for(self._candle_queue.get(), timeout=0.1)
                # Добавляем новую
                await self._candle_queue.put(candle_data)
            except asyncio.TimeoutError:
                logger.error("Failed to manage queue overflow")
    
    async def _process_candles(self) -> None:
        """Основной цикл обработки свечей."""
        while self._running:
            try:
                # Собираем батч свечей
                batch = await self._collect_batch()
                
                if batch:
                    # Обрабатываем батч параллельно
                    await self._process_batch(batch)
                
            except asyncio.CancelledError:
                logger.debug("Candle processing task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in candle processing: {e}")
                await asyncio.sleep(1)  # Пауза при ошибке
    
    async def _collect_batch(self) -> List[Dict[str, Any]]:
        """Сбор батча свечей для обработки."""
        batch = []
        start_time = time.time()
        
        while (len(batch) < self.config.batch_size and 
               self._running and 
               time.time() - start_time < self.config.batch_timeout):
            
            try:
                timeout = self.config.batch_timeout - (time.time() - start_time)
                if timeout <= 0:
                    break
                
                candle = await asyncio.wait_for(
                    self._candle_queue.get(),
                    timeout=max(0.01, timeout)
                )
                batch.append(candle)
                
            except asyncio.TimeoutError:
                break
            except Exception as e:
                logger.error(f"Error collecting candle batch: {e}")
                break
        
        return batch
    
    async def _process_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Параллельная обработка батча свечей."""
        tasks = [
            asyncio.create_task(self._process_single_candle(candle))
            for candle in batch
        ]
        
        # Ждем завершения всех задач
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_single_candle(self, candle_data: Dict[str, Any]) -> None:
        """Обработка одной свечи."""
        try:
            symbol = candle_data['symbol'].lower()
            interval = candle_data['interval']
            stream_key = f"{symbol}@kline_{interval}"
            
            # Получаем подписки для этого стрима
            subscriptions = await self.storage.get_subscriptions_for_stream(stream_key)
            
            if not subscriptions:
                return
            
            # Фильтруем подписки по процентному изменению
            filtered_subscriptions = await self._filter_subscriptions_by_change(
                candle_data, subscriptions
            )
            
            if not filtered_subscriptions:
                return
            
            # Отправляем в сервис алертов только если есть подходящие подписки
            await self.alert_service.process_candle_alert(candle_data, filtered_subscriptions)
            
        except Exception as e:
            logger.error(f"Error processing candle {candle_data}: {e}")
    
    async def _filter_subscriptions_by_change(
        self, 
        candle_data: Dict[str, Any], 
        subscriptions: Dict[int, Set[str]]
    ) -> Dict[int, Set[str]]:
        """Фильтрация подписок по процентному изменению цены."""
        from bot.utils.price_analyzer import PriceAnalyzer
        
        analyzer = PriceAnalyzer()
        analysis = analyzer.analyze_candle(candle_data)
        price_change_abs = abs(float(analysis['price_change']))
        
        filtered = {}
        
        for user_id, preset_ids in subscriptions.items():
            user_data = await self.storage.get_user_data(user_id)
            
            # Проверяем каждый пресет пользователя
            valid_presets = set()
            for preset_id in preset_ids:
                preset = user_data.get("presets", {}).get(preset_id)
                if preset and price_change_abs >= preset["percent"]:
                    valid_presets.add(preset_id)
            
            if valid_presets:
                filtered[user_id] = valid_presets
        
        return filtered
    
    async def _monitor_queues(self) -> None:
        """Мониторинг состояния очередей."""
        while self._running:
            try:
                # Статистика очередей
                candle_queue_size = self._candle_queue.qsize()
                alert_stats = self.alert_service.get_queue_stats()
                
                # Логируем статистику каждую минуту
                logger.info(
                    f"Queue stats - Candles: {candle_queue_size}, "
                    f"Alert users: {alert_stats['active_users']}, "
                    f"Alert messages: {alert_stats['total_queued_messages']}"
                )
                
                # Если очереди переполнены, принимаем меры
                if alert_stats['total_queued_messages'] > 10000:
                    logger.warning("Alert queues overloaded, consider optimizing")
                
                await asyncio.sleep(60)  # Мониторинг каждую минуту
                
            except asyncio.CancelledError:
                logger.debug("Queue monitoring task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in queue monitoring: {e}")
                await asyncio.sleep(60)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики сервиса."""
        alert_stats = self.alert_service.get_queue_stats()
        
        return {
            "running": self._running,
            "candle_queue_size": self._candle_queue.qsize(),
            "processing_tasks": len(self._processing_tasks),
            "alert_service": alert_stats
        }
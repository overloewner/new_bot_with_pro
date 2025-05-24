# bot/services/candle_service.py
"""Сервис обработки свечей с оптимизацией и корреляцией."""

import asyncio
import time
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict, deque
from decimal import Decimal

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
        
        # Кеш последних цен для корреляции
        self._price_cache = {
            'BTCUSDT': deque(maxlen=20),  # Последние 20 свечей
            'ETHUSDT': deque(maxlen=20)
        }
        
        # Кеш пресетов для быстрого доступа
        self._preset_cache = {}
        self._cache_update_time = 0
        
        # Индекс пресетов по порогам для быстрой фильтрации
        self._threshold_index = defaultdict(list)  # {threshold: [preset_ids]}
    
    async def start(self) -> None:
        """Запуск сервиса обработки свечей."""
        if self._running:
            return
        
        self._running = True
        
        # Запускаем сервис алертов
        await self.alert_service.start()
        
        # Загружаем кеш пресетов
        await self._update_preset_cache()
        
        # Запускаем задачи обработки
        self._processing_tasks = [
            asyncio.create_task(self._process_candles()),
            asyncio.create_task(self._monitor_queues()),
            asyncio.create_task(self._update_cache_periodically())
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
            # Сохраняем цены BTC/ETH для корреляции
            symbol = candle_data['symbol']
            if symbol in self._price_cache:
                self._price_cache[symbol].append({
                    'close': candle_data['close'],
                    'time': time.time(),
                    'change': self._calculate_change(candle_data)
                })
            
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
                    await self._process_batch_optimized(batch)
                
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
    
    async def _process_batch_optimized(self, batch: List[Dict[str, Any]]) -> None:
        """Оптимизированная обработка батча свечей."""
        # Группируем свечи по символам для эффективности
        candles_by_stream = defaultdict(list)
        
        for candle in batch:
            symbol = candle['symbol'].lower()
            interval = candle['interval']
            stream_key = f"{symbol}@kline_{interval}"
            
            # Вычисляем изменение цены один раз
            candle['price_change'] = self._calculate_change(candle)
            candle['price_change_abs'] = abs(candle['price_change'])
            
            # Добавляем корреляцию с BTC/ETH
            candle['btc_correlation'] = self._get_correlation('BTCUSDT')
            candle['eth_correlation'] = self._get_correlation('ETHUSDT')
            
            candles_by_stream[stream_key].append(candle)
        
        # Обрабатываем каждый стрим
        tasks = []
        for stream_key, stream_candles in candles_by_stream.items():
            task = asyncio.create_task(
                self._process_stream_candles(stream_key, stream_candles)
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_stream_candles(self, stream_key: str, candles: List[Dict[str, Any]]) -> None:
        """Обработка свечей для конкретного стрима."""
        # Получаем все подписки для стрима один раз
        all_subscriptions = await self.storage.get_subscriptions_for_stream(stream_key)
        
        if not all_subscriptions:
            return
        
        # Обрабатываем каждую свечу
        for candle in candles:
            # Быстрая фильтрация по порогам
            filtered_subscriptions = await self._filter_subscriptions_optimized(
                candle, all_subscriptions
            )
            
            if filtered_subscriptions:
                await self.alert_service.process_candle_alert(candle, filtered_subscriptions)
    
    async def _filter_subscriptions_optimized(
        self, 
        candle: Dict[str, Any], 
        subscriptions: Dict[int, Set[str]]
    ) -> Dict[int, Set[str]]:
        """Оптимизированная фильтрация подписок по процентному изменению."""
        price_change_abs = candle['price_change_abs']
        btc_corr = candle['btc_correlation']
        eth_corr = candle['eth_correlation']
        
        filtered = {}
        
        # Используем кеш пресетов вместо обращения к storage
        for user_id, preset_ids in subscriptions.items():
            valid_presets = set()
            
            for preset_id in preset_ids:
                preset = self._preset_cache.get(preset_id)
                if not preset:
                    continue
                
                # Проверяем основной порог
                if price_change_abs < preset['percent']:
                    continue
                
                # Проверяем корреляцию (если включена)
                if preset.get('check_correlation', False):
                    # Игнорируем движения, которые сильно коррелируют с BTC/ETH
                    if abs(btc_corr) > 0.8 or abs(eth_corr) > 0.8:
                        continue
                
                valid_presets.add(preset_id)
            
            if valid_presets:
                filtered[user_id] = valid_presets
        
        return filtered
    
    def _calculate_change(self, candle: Dict[str, Any]) -> float:
        """Быстрое вычисление процентного изменения."""
        try:
            open_price = candle['open']
            close_price = candle['close']
            
            if open_price == 0:
                return 0.0
            
            return ((close_price - open_price) / open_price) * 100
        except Exception:
            return 0.0
    
    def _get_correlation(self, symbol: str) -> float:
        """Получение корреляции с BTC или ETH."""
        if symbol not in self._price_cache or len(self._price_cache[symbol]) < 2:
            return 0.0
        
        try:
            # Простая корреляция по направлению последних движений
            recent_changes = [item['change'] for item in self._price_cache[symbol][-5:]]
            if not recent_changes:
                return 0.0
            
            # Считаем сколько движений в том же направлении
            same_direction = sum(1 for change in recent_changes if change * recent_changes[-1] > 0)
            correlation = same_direction / len(recent_changes)
            
            # Нормализуем от -1 до 1
            return (correlation - 0.5) * 2
        except Exception:
            return 0.0
    
    async def _update_preset_cache(self) -> None:
        """Обновление кеша пресетов."""
        try:
            # Загружаем все активные пресеты
            all_users_data = self.storage._users_data
            
            new_cache = {}
            new_threshold_index = defaultdict(list)
            
            for user_id, user_data in all_users_data.items():
                if not user_data.get('is_running', False):
                    continue
                
                for preset_id in user_data.get('active_presets', set()):
                    preset = user_data.get('presets', {}).get(preset_id)
                    if preset:
                        new_cache[preset_id] = preset
                        # Индексируем по порогу для быстрого поиска
                        threshold = int(preset['percent'])
                        new_threshold_index[threshold].append(preset_id)
            
            self._preset_cache = new_cache
            self._threshold_index = new_threshold_index
            self._cache_update_time = time.time()
            
            logger.info(f"Updated preset cache with {len(new_cache)} active presets")
        except Exception as e:
            logger.error(f"Error updating preset cache: {e}")
    
    async def _update_cache_periodically(self) -> None:
        """Периодическое обновление кеша."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                await self._update_preset_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache update task: {e}")
    
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
                    f"Alert messages: {alert_stats['total_queued_messages']}, "
                    f"Cached presets: {len(self._preset_cache)}"
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
            "cached_presets": len(self._preset_cache),
            "btc_price_history": len(self._price_cache.get('BTCUSDT', [])),
            "eth_price_history": len(self._price_cache.get('ETHUSDT', [])),
            "alert_service": alert_stats
        }
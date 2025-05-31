# modules/price_alerts/core/candle_processor.py
"""Обработчик свечей с оптимизацией и многопоточностью."""

import asyncio
import time
from typing import Dict, Any, List, Set
from collections import defaultdict, deque
from decimal import Decimal, getcontext

from shared.utils.logger import get_module_logger

logger = get_module_logger("candle_processor")

# Устанавливаем точность для Decimal
getcontext().prec = 10


class CandleProcessor:
    """Обработчик свечей с батчингом и кешированием."""
    
    def __init__(self, alert_dispatcher, preset_manager):
        self.alert_dispatcher = alert_dispatcher
        self.preset_manager = preset_manager
        
        # Очереди и батчинг
        self._candle_queue = asyncio.Queue(maxsize=10000)
        self._running = False
        self._processing_tasks: List[asyncio.Task] = []
        
        # Кеш для корреляции с BTC/ETH
        self._price_cache = {
            'BTCUSDT': deque(maxlen=50),
            'ETHUSDT': deque(maxlen=50)
        }
        
        # Кеш пресетов для быстрого доступа
        self._preset_cache = {}
        self._cache_update_time = 0
        self._cache_ttl = 60  # Обновляем кеш каждую минуту
        
        # Конфигурация батчинга
        self.batch_size = 500
        self.batch_timeout = 0.1  # 100ms
        self.max_queue_size = 10000
        
        # Статистика
        self._processed_count = 0
        self._error_count = 0
        self._last_stats_time = time.time()
    
    async def start(self):
        """Запуск процессора свечей."""
        if self._running:
            return
        
        self._running = True
        
        # Запускаем задачи обработки
        self._processing_tasks = [
            asyncio.create_task(self._process_candles_worker(i))
            for i in range(3)  # 3 воркера для параллельной обработки
        ]
        
        # Задача обновления кеша
        self._processing_tasks.append(
            asyncio.create_task(self._cache_updater())
        )
        
        # Задача мониторинга
        self._processing_tasks.append(
            asyncio.create_task(self._stats_monitor())
        )
        
        logger.info("Candle processor started with 3 workers")
    
    async def stop(self):
        """Остановка процессора."""
        self._running = False
        
        # Останавливаем задачи
        for task in self._processing_tasks:
            task.cancel()
        
        if self._processing_tasks:
            await asyncio.gather(*self._processing_tasks, return_exceptions=True)
        
        self._processing_tasks.clear()
        logger.info("Candle processor stopped")
    
    async def process_candle(self, candle_data: Dict[str, Any]):
        """Добавление свечи в очередь обработки."""
        if not self._running:
            return
        
        try:
            # Добавляем в очередь без блокировки
            self._candle_queue.put_nowait(candle_data)
            
            # Обновляем кеш корреляции для BTC/ETH
            symbol = candle_data.get('symbol')
            if symbol in self._price_cache:
                change_percent = self._calculate_price_change(candle_data)
                self._price_cache[symbol].append({
                    'change': change_percent,
                    'time': time.time(),
                    'close': candle_data.get('close', 0)
                })
                
        except asyncio.QueueFull:
            logger.warning("Candle queue full, dropping candle")
            self._error_count += 1
    
    async def _process_candles_worker(self, worker_id: int):
        """Воркер для обработки свечей."""
        logger.debug(f"Started candle worker {worker_id}")
        
        while self._running:
            try:
                # Собираем батч свечей
                batch = await self._collect_batch()
                
                if batch:
                    await self._process_batch(batch, worker_id)
                
            except asyncio.CancelledError:
                logger.debug(f"Candle worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Error in candle worker {worker_id}: {e}")
                await asyncio.sleep(1)
    
    async def _collect_batch(self) -> List[Dict[str, Any]]:
        """Сбор батча свечей с таймаутом."""
        batch = []
        start_time = time.time()
        
        while (len(batch) < self.batch_size and 
               self._running and 
               time.time() - start_time < self.batch_timeout):
            
            try:
                remaining_time = self.batch_timeout - (time.time() - start_time)
                if remaining_time <= 0:
                    break
                
                candle = await asyncio.wait_for(
                    self._candle_queue.get(),
                    timeout=max(0.001, remaining_time)
                )
                batch.append(candle)
                
            except asyncio.TimeoutError:
                break
        
        return batch
    
    async def _process_batch(self, batch: List[Dict[str, Any]], worker_id: int):
        """Обработка батча свечей."""
        processed_alerts = []
        
        for candle in batch:
            try:
                # Быстрая предварительная фильтрация
                change_percent = self._calculate_price_change(candle)
                if abs(change_percent) < 0.1:  # Игнорируем изменения < 0.1%
                    continue
                
                # Получаем подходящие пресеты
                matching_presets = await self._find_matching_presets(candle, change_percent)
                
                if matching_presets:
                    alert_data = self._create_alert_data(candle, change_percent)
                    processed_alerts.append((alert_data, matching_presets))
                    
                self._processed_count += 1
                
            except Exception as e:
                logger.error(f"Error processing candle: {e}")
                self._error_count += 1
        
        # Отправляем все алерты батчем
        if processed_alerts:
            await self._dispatch_alerts_batch(processed_alerts)
    
    async def _find_matching_presets(self, candle: Dict[str, Any], change_percent: float) -> Dict[int, Set[str]]:
        """Поиск подходящих пресетов для свечи."""
        symbol = candle.get('symbol')
        interval = candle.get('interval')
        change_abs = abs(change_percent)
        
        # Обновляем кеш если нужно
        if time.time() - self._cache_update_time > self._cache_ttl:
            await self._update_preset_cache()
        
        matching = defaultdict(set)
        
        for preset_id, preset_data in self._preset_cache.items():
            # Проверяем символ
            if symbol not in preset_data.get('pairs', []):
                continue
            
            # Проверяем интервал
            if interval != preset_data.get('interval'):
                continue
            
            # Проверяем процент
            if change_abs < preset_data.get('percent', 0):
                continue
            
            # Проверяем корреляцию если включена
            if preset_data.get('check_correlation', False):
                correlation = self._get_market_correlation()
                if correlation > 0.8:  # Сильная корреляция - пропускаем
                    continue
            
            user_id = preset_data.get('user_id')
            if user_id:
                matching[user_id].add(preset_id)
        
        return dict(matching)
    
    def _calculate_price_change(self, candle: Dict[str, Any]) -> float:
        """Быстрое вычисление изменения цены."""
        try:
            open_price = Decimal(str(candle.get('open', 0)))
            close_price = Decimal(str(candle.get('close', 0)))
            
            if open_price == 0:
                return 0.0
            
            change = ((close_price - open_price) / open_price) * 100
            return float(change)
            
        except Exception:
            return 0.0
    
    def _get_market_correlation(self) -> float:
        """Получение корреляции с общим рынком (BTC)."""
        try:
            btc_data = list(self._price_cache['BTCUSDT'])
            if len(btc_data) < 5:
                return 0.0
            
            # Простая корреляция по направлению движения
            recent_changes = [item['change'] for item in btc_data[-5:]]
            positive_moves = sum(1 for change in recent_changes if change > 0)
            
            # Возвращаем силу тренда
            return (positive_moves / len(recent_changes) - 0.5) * 2
            
        except Exception:
            return 0.0
    
    def _create_alert_data(self, candle: Dict[str, Any], change_percent: float) -> Dict[str, Any]:
        """Создание данных алерта."""
        direction = "🟢" if change_percent > 0 else "🔴"
        
        return {
            'symbol': candle.get('symbol'),
            'interval': candle.get('interval'),
            'change_percent': round(change_percent, 2),
            'direction': direction,
            'open': candle.get('open'),
            'close': candle.get('close'),
            'high': candle.get('high'),
            'low': candle.get('low'),
            'volume': candle.get('volume'),
            'timestamp': time.time()
        }
    
    async def _dispatch_alerts_batch(self, alerts_batch: List[tuple]):
        """Отправка батча алертов."""
        for alert_data, user_presets in alerts_batch:
            await self.alert_dispatcher.dispatch_alert(alert_data, user_presets)
    
    async def _update_preset_cache(self):
        """Обновление кеша пресетов."""
        try:
            new_cache = await self.preset_manager.get_active_presets_cache()
            self._preset_cache = new_cache
            self._cache_update_time = time.time()
            
        except Exception as e:
            logger.error(f"Error updating preset cache: {e}")
    
    async def _cache_updater(self):
        """Периодическое обновление кеша."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Обновляем каждые 30 секунд
                await self._update_preset_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache updater: {e}")
    
    async def _stats_monitor(self):
        """Мониторинг статистики."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                
                current_time = time.time()
                time_diff = current_time - self._last_stats_time
                
                if time_diff > 0:
                    processing_rate = self._processed_count / time_diff
                    error_rate = self._error_count / max(1, self._processed_count) * 100
                    
                    logger.info(
                        f"Candle processing stats: "
                        f"Rate: {processing_rate:.1f}/sec, "
                        f"Queue: {self._candle_queue.qsize()}, "
                        f"Errors: {error_rate:.1f}%, "
                        f"Cache: {len(self._preset_cache)} presets"
                    )
                
                # Сбрасываем счетчики
                self._processed_count = 0
                self._error_count = 0
                self._last_stats_time = current_time
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in stats monitor: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        return {
            "running": self._running,
            "queue_size": self._candle_queue.qsize(),
            "workers": len([t for t in self._processing_tasks if not t.done()]),
            "preset_cache_size": len(self._preset_cache),
            "btc_cache_size": len(self._price_cache['BTCUSDT']),
            "eth_cache_size": len(self._price_cache['ETHUSDT']),
            "processed_count": self._processed_count,
            "error_count": self._error_count
        }
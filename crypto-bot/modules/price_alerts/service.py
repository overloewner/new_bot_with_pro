# modules/price_alerts/service.py
"""Обновленный сервис ценовых алертов с репозиторием."""

import asyncio
import aiohttp
import time
import json
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import logging

from shared.events import event_bus, Event, PRICE_ALERT_TRIGGERED, PRICE_DATA_UPDATED
from shared.utils.rate_limiter import get_rate_limiter
from .repository import PriceAlertsRepository

logger = logging.getLogger(__name__)

@dataclass
class PriceData:
    """Данные о цене."""
    symbol: str
    price: float
    change_24h: float
    change_percent_24h: float
    volume_24h: float
    timestamp: datetime
    source: str = "binance"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'price': self.price,
            'change_24h': self.change_24h,
            'change_percent_24h': self.change_percent_24h,
            'volume_24h': self.volume_24h,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source
        }

@dataclass
class PriceAlert:
    """Ценовой алерт."""
    id: int
    user_id: int
    symbol: str
    price_threshold: float
    alert_type: str  # 'above', 'below', 'change_percent'
    percent_threshold: Optional[float] = None
    interval: str = "1h"  # 1m, 5m, 1h, 1d
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_triggered: Optional[datetime] = None
    times_triggered: int = 0
    cooldown_minutes: int = 15
    min_volume: Optional[float] = None

@dataclass
class PricePreset:
    """Пресет для группы алертов."""
    id: int
    user_id: int
    name: str
    symbols: List[str]
    percent_threshold: float
    interval: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    alerts: List[PriceAlert] = field(default_factory=list)

class PriceAlertsService:
    """
    Обновленный сервис ценовых алертов с репозиторием.
    """
    
    def __init__(self, db_manager=None):
        self.running = False
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Репозиторий для данных
        self.repository = PriceAlertsRepository(db_manager)
        
        # Данные
        self._current_prices: Dict[str, PriceData] = {}
        self._price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1440))  # 24 часа по минутам
        self._alerts: Dict[int, List[PriceAlert]] = {}
        
        # Rate limiting
        self.rate_limiter = get_rate_limiter('binance_free')
        
        # Настройки мониторинга
        self.monitored_symbols = set()
        self.update_interval = 30  # секунд
        
        # API конфигурация
        self.api_configs = {
            'binance': {
                'base_url': 'https://api.binance.com/api/v3',
                'endpoints': {
                    'ticker_24hr': '/ticker/24hr',
                    'ticker_price': '/ticker/price'
                },
                'rate_limit': 1200  # requests per minute
            }
        }
        
        # Статистика
        self._stats = {
            'total_updates': 0,
            'failed_updates': 0,
            'api_calls': 0,
            'alerts_triggered': 0,
            'symbols_monitored': 0,
            'avg_response_time': 0.0
        }
        
        # Популярные пары для быстрого доступа
        self.popular_symbols = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT',
            'SOLUSDT', 'DOTUSDT', 'DOGEUSDT', 'AVAXUSDT', 'SHIBUSDT',
            'MATICUSDT', 'UNIUSDT', 'LTCUSDT', 'LINKUSDT', 'ATOMUSDT'
        ]
        
        # Event subscriptions
        event_bus.subscribe("price_alerts.get_user_presets", self._handle_get_user_presets)
        event_bus.subscribe("price_alerts.create_preset", self._handle_create_preset)
        event_bus.subscribe("price_alerts.delete_preset", self._handle_delete_preset)
        event_bus.subscribe("price_alerts.get_current_prices", self._handle_get_current_prices)
        event_bus.subscribe("price_alerts.add_symbol_monitoring", self._handle_add_monitoring)
        event_bus.subscribe("price_alerts.get_statistics", self._handle_get_statistics)
        event_bus.subscribe("price_alerts.activate_preset", self._handle_activate_preset)
        event_bus.subscribe("price_alerts.deactivate_preset", self._handle_deactivate_preset)
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        
        # Создаем HTTP сессию
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=20)
        )
        
        # Загружаем данные из репозитория
        await self._load_from_repository()
        
        # Запускаем мониторинг популярных пар
        self.monitored_symbols.update(self.popular_symbols)
        
        # Запускаем фоновые задачи
        asyncio.create_task(self._monitor_prices())
        asyncio.create_task(self._cleanup_old_data())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={"module": "price_alerts"},
            source_module="price_alerts"
        ))
        
        logger.info(f"Price Alerts service started, monitoring {len(self.monitored_symbols)} symbols")
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        self.running = False
        
        # Закрываем сессию
        if self._session:
            await self._session.close()
        
        await event_bus.publish(Event(
            type="system.module_stopped",
            data={"module": "price_alerts"},
            source_module="price_alerts"
        ))
        
        logger.info("Price Alerts service stopped")
    
    async def _load_from_repository(self) -> None:
        """Загрузка данных из репозитория."""
        try:
            # Загружаем активные пресеты для мониторинга
            active_presets = await self.repository.get_active_presets_cache()
            
            # Добавляем символы в мониторинг
            for preset_data in active_presets.values():
                self.monitored_symbols.update(preset_data.get('symbols', []))
            
            logger.info(f"Loaded {len(active_presets)} active presets from repository")
            
        except Exception as e:
            logger.error(f"Error loading from repository: {e}")
    
    async def _monitor_prices(self) -> None:
        """Основной цикл мониторинга цен."""
        consecutive_failures = 0
        max_failures = 5
        
        while self.running:
            try:
                start_time = time.time()
                
                # Получаем данные по всем отслеживаемым символам
                success = await self._fetch_all_prices()
                
                if success:
                    consecutive_failures = 0
                    
                    # Проверяем все алерты
                    await self._check_all_alerts()
                    
                    # Обновляем статистику
                    self._stats['total_updates'] += 1
                    
                    processing_time = time.time() - start_time
                    self._stats['avg_response_time'] = (
                        self._stats['avg_response_time'] * 0.9 + processing_time * 0.1
                    )
                    
                    logger.debug(f"Price update completed in {processing_time:.2f}s")
                    
                    # Публикуем событие обновления
                    await event_bus.publish(Event(
                        type=PRICE_DATA_UPDATED,
                        data={
                            "symbols_count": len(self._current_prices),
                            "processing_time": processing_time
                        },
                        source_module="price_alerts"
                    ))
                    
                else:
                    consecutive_failures += 1
                    self._stats['failed_updates'] += 1
                    logger.warning(f"Failed to fetch prices, failures: {consecutive_failures}")
                
                # Динамический интервал обновления
                if consecutive_failures == 0:
                    sleep_time = self.update_interval
                else:
                    sleep_time = min(300, self.update_interval * (1 + consecutive_failures))
                
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Error in price monitoring: {e}")
                await asyncio.sleep(min(300, 60 * consecutive_failures))
    
    async def _fetch_all_prices(self) -> bool:
        """Получение цен для всех отслеживаемых символов."""
        if not self.monitored_symbols:
            return True
        
        try:
            # Проверяем rate limit
            rate_limit_result = await self.rate_limiter.acquire('binance')
            if not rate_limit_result.allowed:
                logger.debug(f"Rate limited, waiting {rate_limit_result.wait_time:.2f}s")
                await asyncio.sleep(rate_limit_result.wait_time)
            
            self._stats['api_calls'] += 1
            
            # Получаем данные 24hr ticker для всех символов
            url = f"{self.api_configs['binance']['base_url']}{self.api_configs['binance']['endpoints']['ticker_24hr']}"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Обрабатываем данные
                    updated_count = 0
                    for ticker in data:
                        symbol = ticker['symbol']
                        
                        if symbol in self.monitored_symbols:
                            price_data = PriceData(
                                symbol=symbol,
                                price=float(ticker['lastPrice']),
                                change_24h=float(ticker['priceChange']),
                                change_percent_24h=float(ticker['priceChangePercent']),
                                volume_24h=float(ticker['quoteVolume']),
                                timestamp=datetime.utcnow(),
                                source='binance'
                            )
                            
                            # Сохраняем текущую цену
                            self._current_prices[symbol] = price_data
                            
                            # Добавляем в историю
                            self._price_history[symbol].append({
                                'timestamp': price_data.timestamp.timestamp(),
                                'price': price_data.price,
                                'volume': price_data.volume_24h
                            })
                            
                            updated_count += 1
                    
                    logger.debug(f"Updated prices for {updated_count} symbols")
                    
                    # Записываем успешный API вызов
                    await self.rate_limiter.record_api_call('binance', True, time.time())
                    
                    return updated_count > 0
                else:
                    logger.warning(f"Binance API returned {response.status}")
                    await self.rate_limiter.record_api_call('binance', False, time.time())
                    return False
                    
        except asyncio.TimeoutError:
            logger.warning("Timeout fetching prices from Binance")
            await self.rate_limiter.record_api_call('binance', False, time.time())
            return False
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            await self.rate_limiter.record_api_call('binance', False, time.time())
            return False
    
    async def _check_all_alerts(self) -> None:
        """Проверка всех активных пресетов на алерты."""
        try:
            # Получаем активные пресеты
            active_presets = await self.repository.get_active_presets_cache()
            
            for preset_id, preset_data in active_presets.items():
                user_id = preset_data['user_id']
                
                for symbol in preset_data.get('symbols', []):
                    price_data = self._current_prices.get(symbol)
                    if not price_data:
                        continue
                    
                    # Проверяем условие алерта
                    change_percent = abs(price_data.change_percent_24h)
                    if change_percent >= preset_data.get('percent_threshold', 0):
                        await self._trigger_alert(user_id, preset_data, price_data)
                        
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
    
    async def _trigger_alert(self, user_id: int, preset_data: Dict[str, Any], price_data: PriceData) -> None:
        """Срабатывание алерта."""
        try:
            # Определяем направление
            direction = "🟢" if price_data.change_percent_24h > 0 else "🔴"
            
            # Форматируем цену
            if price_data.price >= 1:
                price_str = f"{price_data.price:.2f}"
            else:
                price_str = f"{price_data.price:.8f}"
            
            change_icon = "🟢" if price_data.change_percent_24h > 0 else "🔴"
            
            message = (
                f"{direction} <b>Price Alert!</b>\n\n"
                
                f"💰 <b>{price_data.symbol}</b>\n"
                f"💵 Цена: <b>${price_str}</b>\n"
                f"📊 Пресет: {preset_data.get('name', 'Unknown')}\n\n"
                
                f"📈 <b>Изменения за 24ч:</b>\n"
                f"{change_icon} {price_data.change_percent_24h:+.2f}% (${price_data.change_24h:+.8f})\n"
                f"📊 Объем: ${price_data.volume_24h:,.0f}\n\n"
                
                f"🕐 <b>Время:</b> {price_data.timestamp.strftime('%H:%M:%S')}"
            )
            
            await event_bus.publish(Event(
                type=PRICE_ALERT_TRIGGERED,
                data={
                    "user_id": user_id,
                    "message": message,
                    "preset_id": preset_data.get('id'),
                    "symbol": price_data.symbol,
                    "current_price": price_data.price,
                    "change_percent": price_data.change_percent_24h
                },
                source_module="price_alerts"
            ))
            
            self._stats['alerts_triggered'] += 1
            
            logger.info(f"Triggered price alert for user {user_id}: {price_data.symbol} ${price_data.price}")
            
        except Exception as e:
            logger.error(f"Error triggering alert: {e}")
    
    async def _cleanup_old_data(self) -> None:
        """Фоновая очистка старых данных."""
        while self.running:
            try:
                await asyncio.sleep(3600)  # Каждый час
                
                # Очищаем старую историю цен
                current_time = time.time()
                cutoff_time = current_time - 86400  # 24 часа
                
                for symbol, history in self._price_history.items():
                    while history and history[0].get('timestamp', 0) < cutoff_time:
                        history.popleft()
                
                logger.debug("Cleaned up old price history data")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup: {e}")
    
    # PUBLIC API METHODS
    
    def get_user_presets(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение пресетов пользователя."""
        # Используем асинхронную обертку для синхронного вызова
        import asyncio
        try:
            return asyncio.create_task(self.repository.get_user_presets(user_id)).result()
        except:
            return []
    
    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение алертов пользователя."""
        alerts = self._alerts.get(user_id, [])
        return [
            {
                "id": alert.id,
                "symbol": alert.symbol,
                "price_threshold": alert.price_threshold,
                "alert_type": alert.alert_type,
                "percent_threshold": alert.percent_threshold,
                "interval": alert.interval,
                "is_active": alert.is_active,
                "created_at": alert.created_at.isoformat(),
                "last_triggered": alert.last_triggered.isoformat() if alert.last_triggered else None,
                "times_triggered": alert.times_triggered,
                "cooldown_minutes": alert.cooldown_minutes
            }
            for alert in alerts
        ]
    
    def get_current_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """Получение текущих цен."""
        if symbols:
            symbols = [s.upper() for s in symbols]
            return {
                symbol: price_data.to_dict()
                for symbol, price_data in self._current_prices.items()
                if symbol in symbols
            }
        else:
            return {
                symbol: price_data.to_dict()
                for symbol, price_data in self._current_prices.items()
            }
    
    def get_popular_symbols(self) -> List[str]:
        """Получение популярных символов."""
        return self.popular_symbols.copy()
    
    def get_price_history(self, symbol: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Получение истории цен."""
        history = self._price_history.get(symbol.upper(), deque())
        cutoff_time = time.time() - (hours * 3600)
        
        return [
            entry for entry in history
            if entry.get('timestamp', 0) > cutoff_time
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики сервиса."""
        # Получаем статистику репозитория
        repo_stats = self.repository.get_cache_stats()
        
        return {
            "running": self.running,
            "monitored_symbols": len(self.monitored_symbols),
            "current_prices_count": len(self._current_prices),
            "repository_stats": repo_stats,
            **self._stats
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Алиас для get_statistics."""
        return self.get_statistics()
    
    # EVENT HANDLERS
    
    async def _handle_get_user_presets(self, event: Event):
        """Обработка запроса пресетов пользователя."""
        user_id = event.data.get("user_id")
        presets = await self.repository.get_user_presets(user_id)
        
        await event_bus.publish(Event(
            type="price_alerts.user_presets_response",
            data={
                "user_id": user_id,
                "presets": presets
            },
            source_module="price_alerts"
        ))
    
    async def _handle_create_preset(self, event: Event):
        """Обработка создания пресета."""
        user_id = event.data.get("user_id")
        preset_data = event.data.get("preset_data")
        
        preset_id = await self.repository.create_preset(user_id, preset_data)
        
        # Добавляем символы в мониторинг
        if preset_id and preset_data.get("symbols"):
            self.monitored_symbols.update(preset_data["symbols"])
        
        await event_bus.publish(Event(
            type="price_alerts.preset_created",
            data={
                "user_id": user_id,
                "preset_id": preset_id,
                "success": preset_id is not None
            },
            source_module="price_alerts"
        ))
    
    async def _handle_delete_preset(self, event: Event):
        """Обработка удаления пресета."""
        user_id = event.data.get("user_id")
        preset_id = event.data.get("preset_id")
        
        success = await self.repository.delete_preset(user_id, preset_id)
        
        await event_bus.publish(Event(
            type="price_alerts.preset_deleted",
            data={
                "user_id": user_id,
                "preset_id": preset_id,
                "success": success
            },
            source_module="price_alerts"
        ))
    
    async def _handle_activate_preset(self, event: Event):
        """Обработка активации пресета."""
        user_id = event.data.get("user_id")
        preset_id = event.data.get("preset_id")
        
        success = await self.repository.update_preset_status(user_id, preset_id, True)
        
        await event_bus.publish(Event(
            type="price_alerts.preset_activated",
            data={
                "user_id": user_id,
                "preset_id": preset_id,
                "success": success
            },
            source_module="price_alerts"
        ))
    
    async def _handle_deactivate_preset(self, event: Event):
        """Обработка деактивации пресета."""
        user_id = event.data.get("user_id")
        preset_id = event.data.get("preset_id")
        
        success = await self.repository.update_preset_status(user_id, preset_id, False)
        
        await event_bus.publish(Event(
            type="price_alerts.preset_deactivated",
            data={
                "user_id": user_id,
                "preset_id": preset_id,
                "success": success
            },
            source_module="price_alerts"
        ))
    
    async def _handle_get_current_prices(self, event: Event):
        """Обработка запроса текущих цен."""
        symbols = event.data.get("symbols")
        prices = self.get_current_prices(symbols)
        
        await event_bus.publish(Event(
            type="price_alerts.current_prices_response",
            data={
                "user_id": event.data.get("user_id"),
                "prices": prices,
                "symbols_requested": symbols
            },
            source_module="price_alerts"
        ))
    
    async def _handle_add_monitoring(self, event: Event):
        """Обработка добавления символа в мониторинг."""
        symbols = event.data.get("symbols", [])
        
        for symbol in symbols:
            self.monitored_symbols.add(symbol.upper())
        
        self._stats['symbols_monitored'] = len(self.monitored_symbols)
        
        await event_bus.publish(Event(
            type="price_alerts.monitoring_updated",
            data={
                "symbols_added": symbols,
                "total_monitored": len(self.monitored_symbols)
            },
            source_module="price_alerts"
        ))
    
    async def _handle_get_statistics(self, event: Event):
        """Обработка запроса статистики."""
        stats = self.get_statistics()
        
        await event_bus.publish(Event(
            type="price_alerts.statistics_response",
            data={
                "user_id": event.data.get("user_id"),
                "statistics": stats
            },
            source_module="price_alerts"
        ))
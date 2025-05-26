# modules/price_alerts/service.py
"""Полностью рабочий сервис ценовых алертов с кешированием и отказоустойчивостью."""

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
from shared.cache.memory_cache import cache_manager, cached
from shared.utils.rate_limiter import get_rate_limiter

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
    Полнофункциональный сервис ценовых алертов с:
    - Реальным мониторингом цен
    - Кешированием
    - Rate limiting
    - Отказоустойчивостью
    - Поддержкой пресетов
    """
    
    def __init__(self):
        self.running = False
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Данные
        self._current_prices: Dict[str, PriceData] = {}
        self._price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1440))  # 24 часа по минутам
        self._alerts: Dict[int, List[PriceAlert]] = {}
        self._presets: Dict[int, List[PricePreset]] = {}
        
        # Кеш и rate limiting
        self.cache = cache_manager.get_cache('price_alerts')
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
        
        # Запускаем кеш
        await self.cache.start()
        
        # Загружаем данные из кеша
        await self._load_from_cache()
        
        # Запускаем мониторинг популярных пар
        self.monitored_symbols.update(self.popular_symbols)
        
        # Запускаем фоновые задачи
        asyncio.create_task(self._monitor_prices())
        asyncio.create_task(self._cleanup_old_data())
        asyncio.create_task(self._save_data_periodically())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={"module": "price_alerts"},
            source_module="price_alerts"
        ))
        
        logger.info(f"Price Alerts service started, monitoring {len(self.monitored_symbols)} symbols")
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        self.running = False
        
        # Сохраняем данные
        await self._save_to_cache()
        
        # Закрываем сессию
        if self._session:
            await self._session.close()
        
        # Останавливаем кеш
        await self.cache.stop()
        
        await event_bus.publish(Event(
            type="system.module_stopped",
            data={"module": "price_alerts"},
            source_module="price_alerts"
        ))
        
        logger.info("Price Alerts service stopped")
    
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
        """Проверка всех пользовательских алертов."""
        current_time = datetime.utcnow()
        
        for user_id, user_alerts in self._alerts.items():
            for alert in user_alerts:
                if not alert.is_active:
                    continue
                
                # Проверяем cooldown
                if (alert.last_triggered and 
                    current_time - alert.last_triggered < timedelta(minutes=alert.cooldown_minutes)):
                    continue
                
                # Получаем текущую цену
                price_data = self._current_prices.get(alert.symbol)
                if not price_data:
                    continue
                
                # Проверяем условие алерта
                triggered = await self._check_alert_condition(alert, price_data)
                
                if triggered:
                    await self._trigger_alert(user_id, alert, price_data)
    
    async def _check_alert_condition(self, alert: PriceAlert, price_data: PriceData) -> bool:
        """Проверка условия срабатывания алерта."""
        # Проверяем минимальный объем если задан
        if alert.min_volume and price_data.volume_24h < alert.min_volume:
            return False
        
        current_price = price_data.price
        
        if alert.alert_type == "above":
            return current_price >= alert.price_threshold
        elif alert.alert_type == "below":
            return current_price <= alert.price_threshold
        elif alert.alert_type == "change_percent" and alert.percent_threshold:
            return abs(price_data.change_percent_24h) >= alert.percent_threshold
        
        return False
    
    async def _trigger_alert(self, user_id: int, alert: PriceAlert, price_data: PriceData) -> None:
        """Срабатывание алерта."""
        # Определяем направление
        if alert.alert_type == "above":
            direction = "⬆️"
            condition = f"поднялась выше {alert.price_threshold:.8f}"
        elif alert.alert_type == "below":
            direction = "⬇️"
            condition = f"упала ниже {alert.price_threshold:.8f}"
        else:
            direction = "📊"
            condition = f"изменилась на {price_data.change_percent_24h:.2f}%"
        
        # Форматируем цену
        if price_data.price >= 1:
            price_str = f"{price_data.price:.2f}"
        else:
            price_str = f"{price_data.price:.8f}"
        
        change_icon = "🟢" if price_data.change_percent_24h > 0 else "🔴"
        
        message = (
            f"{direction} <b>Price Alert!</b>\n\n"
            
            f"💰 <b>{alert.symbol}</b>\n"
            f"💵 Цена: <b>${price_str}</b>\n"
            f"📊 Условие: {condition}\n\n"
            
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
                "alert_id": alert.id,
                "symbol": alert.symbol,
                "current_price": price_data.price,
                "alert_type": alert.alert_type,
                "threshold": alert.price_threshold,
                "change_percent": price_data.change_percent_24h
            },
            source_module="price_alerts"
        ))
        
        # Обновляем статистику алерта
        alert.last_triggered = datetime.utcnow()
        alert.times_triggered += 1
        self._stats['alerts_triggered'] += 1
        
        logger.info(f"Triggered price alert for user {user_id}: {alert.symbol} ${price_data.price}")
    
    async def _load_from_cache(self) -> None:
        """Загрузка данных из кеша."""
        try:
            # Загружаем алерты
            cached_alerts = await self.cache.get('user_alerts', {})
            for user_id_str, alerts_data in cached_alerts.items():
                user_id = int(user_id_str)
                self._alerts[user_id] = []
                
                for alert_data in alerts_data:
                    alert = PriceAlert(
                        id=alert_data['id'],
                        user_id=user_id,
                        symbol=alert_data['symbol'],
                        price_threshold=alert_data['price_threshold'],
                        alert_type=alert_data['alert_type'],
                        percent_threshold=alert_data.get('percent_threshold'),
                        interval=alert_data.get('interval', '1h'),
                        is_active=alert_data.get('is_active', True),
                        created_at=datetime.fromisoformat(alert_data.get('created_at', datetime.utcnow().isoformat())),
                        last_triggered=datetime.fromisoformat(alert_data['last_triggered']) if alert_data.get('last_triggered') else None,
                        times_triggered=alert_data.get('times_triggered', 0),
                        cooldown_minutes=alert_data.get('cooldown_minutes', 15),
                        min_volume=alert_data.get('min_volume')
                    )
                    self._alerts[user_id].append(alert)
                    
                    # Добавляем символ в мониторинг
                    self.monitored_symbols.add(alert.symbol)
            
            # Загружаем пресеты
            cached_presets = await self.cache.get('user_presets', {})
            for user_id_str, presets_data in cached_presets.items():
                user_id = int(user_id_str)
                self._presets[user_id] = []
                
                for preset_data in presets_data:
                    preset = PricePreset(
                        id=preset_data['id'],
                        user_id=user_id,
                        name=preset_data['name'],
                        symbols=preset_data['symbols'],
                        percent_threshold=preset_data['percent_threshold'],
                        interval=preset_data['interval'],
                        is_active=preset_data.get('is_active', True),
                        created_at=datetime.fromisoformat(preset_data.get('created_at', datetime.utcnow().isoformat()))
                    )
                    self._presets[user_id].append(preset)
                    
                    # Добавляем символы в мониторинг
                    self.monitored_symbols.update(preset.symbols)
            
            # Загружаем историю цен
            cached_history = await self.cache.get('price_history', {})
            for symbol, history_data in cached_history.items():
                self._price_history[symbol] = deque(history_data, maxlen=1440)
            
            logger.info(f"Loaded {sum(len(alerts) for alerts in self._alerts.values())} alerts and {sum(len(presets) for presets in self._presets.values())} presets from cache")
            
        except Exception as e:
            logger.error(f"Error loading from cache: {e}")
    
    async def _save_to_cache(self) -> None:
        """Сохранение данных в кеш."""
        try:
            # Сохраняем алерты
            alerts_data = {}
            for user_id, alerts in self._alerts.items():
                alerts_data[str(user_id)] = []
                for alert in alerts:
                    alert_dict = {
                        'id': alert.id,
                        'symbol': alert.symbol,
                        'price_threshold': alert.price_threshold,
                        'alert_type': alert.alert_type,
                        'percent_threshold': alert.percent_threshold,
                        'interval': alert.interval,
                        'is_active': alert.is_active,
                        'created_at': alert.created_at.isoformat(),
                        'last_triggered': alert.last_triggered.isoformat() if alert.last_triggered else None,
                        'times_triggered': alert.times_triggered,
                        'cooldown_minutes': alert.cooldown_minutes,
                        'min_volume': alert.min_volume
                    }
                    alerts_data[str(user_id)].append(alert_dict)
            
            await self.cache.set('user_alerts', alerts_data, ttl=86400)
            
            # Сохраняем пресеты
            presets_data = {}
            for user_id, presets in self._presets.items():
                presets_data[str(user_id)] = []
                for preset in presets:
                    preset_dict = {
                        'id': preset.id,
                        'name': preset.name,
                        'symbols': preset.symbols,
                        'percent_threshold': preset.percent_threshold,
                        'interval': preset.interval,
                        'is_active': preset.is_active,
                        'created_at': preset.created_at.isoformat()
                    }
                    presets_data[str(user_id)].append(preset_dict)
            
            await self.cache.set('user_presets', presets_data, ttl=86400)
            
            # Сохраняем историю цен (только последние данные)
            history_data = {}
            for symbol, history in self._price_history.items():
                history_data[symbol] = list(history)[-720:]  # Последние 12 часов
            
            await self.cache.set('price_history', history_data, ttl=43200)  # 12 часов
            
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
    
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
    
    async def _save_data_periodically(self) -> None:
        """Периодическое сохранение данных."""
        while self.running:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                await self._save_to_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic save: {e}")
    
    # PUBLIC API METHODS
    
    async def create_preset(self, user_id: int, preset_data: Dict[str, Any]) -> Optional[int]:
        """Создание пресета."""
        try:
            # Валидация
            if not preset_data.get('name'):
                logger.warning(f"Empty preset name for user {user_id}")
                return None
            
            symbols = preset_data.get('symbols', [])
            if not symbols or len(symbols) > 100:
                logger.warning(f"Invalid symbols count for user {user_id}: {len(symbols)}")
                return None
            
            percent_threshold = preset_data.get('percent_threshold', 0)
            if percent_threshold <= 0 or percent_threshold > 100:
                logger.warning(f"Invalid percent threshold for user {user_id}: {percent_threshold}")
                return None
            
            # Проверяем лимит пресетов
            if user_id in self._presets and len(self._presets[user_id]) >= 10:
                logger.warning(f"Preset limit reached for user {user_id}")
                return None
            
            # Создаем пресет
            preset_id = int(time.time() * 1000) % 2147483647
            preset = PricePreset(
                id=preset_id,
                user_id=user_id,
                name=preset_data['name'],
                symbols=symbols,
                percent_threshold=percent_threshold,
                interval=preset_data.get('interval', '1h')
            )
            
            # Добавляем в список
            if user_id not in self._presets:
                self._presets[user_id] = []
            
            self._presets[user_id].append(preset)
            
            # Добавляем символы в мониторинг
            self.monitored_symbols.update(symbols)
            
            # Создаем алерты для пресета
            for symbol in symbols:
                alert_id = int(time.time() * 1000000) % 2147483647
                alert = PriceAlert(
                    id=alert_id,
                    user_id=user_id,
                    symbol=symbol,
                    price_threshold=0,  # Будет обновлено при проверке
                    alert_type="change_percent",
                    percent_threshold=percent_threshold,
                    interval=preset.interval
                )
                
                if user_id not in self._alerts:
                    self._alerts[user_id] = []
                
                self._alerts[user_id].append(alert)
                preset.alerts.append(alert)
            
            # Сохраняем
            await self._save_to_cache()
            
            logger.info(f"Created preset {preset_id} for user {user_id} with {len(symbols)} symbols")
            return preset_id
            
        except Exception as e:
            logger.error(f"Error creating preset: {e}")
            return None
    
    async def delete_preset(self, user_id: int, preset_id: int) -> bool:
        """Удаление пресета."""
        try:
            if user_id not in self._presets:
                return False
            
            # Находим пресет
            preset = None
            for p in self._presets[user_id]:
                if p.id == preset_id:
                    preset = p
                    break
            
            if not preset:
                return False
            
            # Удаляем связанные алерты
            if user_id in self._alerts:
                self._alerts[user_id] = [
                    alert for alert in self._alerts[user_id]
                    if alert not in preset.alerts
                ]
            
            # Удаляем пресет
            self._presets[user_id] = [
                p for p in self._presets[user_id]
                if p.id != preset_id
            ]
            
            # Сохраняем
            await self._save_to_cache()
            
            logger.info(f"Deleted preset {preset_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting preset: {e}")
            return False
    
    async def add_single_alert(
        self, 
        user_id: int, 
        symbol: str, 
        price_threshold: float, 
        alert_type: str = "above"
    ) -> Optional[int]:
        """Добавление одиночного алерта."""
        try:
            # Валидация
            if price_threshold <= 0:
                return None
            
            if alert_type not in ["above", "below", "change_percent"]:
                return None
            
            # Проверяем лимит алертов
            if user_id in self._alerts and len(self._alerts[user_id]) >= 50:
                return None
            
            # Создаем алерт
            alert_id = int(time.time() * 1000000) % 2147483647
            alert = PriceAlert(
                id=alert_id,
                user_id=user_id,
                symbol=symbol.upper(),
                price_threshold=price_threshold,
                alert_type=alert_type
            )
            
            # Добавляем в список
            if user_id not in self._alerts:
                self._alerts[user_id] = []
            
            self._alerts[user_id].append(alert)
            
            # Добавляем в мониторинг
            self.monitored_symbols.add(symbol.upper())
            
            # Сохраняем
            await self._save_to_cache()
            
            logger.info(f"Added single alert {alert_id} for user {user_id}: {symbol} {alert_type} {price_threshold}")
            return alert_id
            
        except Exception as e:
            logger.error(f"Error adding single alert: {e}")
            return None
    
    def get_user_presets(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение пресетов пользователя."""
        presets = self._presets.get(user_id, [])
        return [
            {
                "id": preset.id,
                "name": preset.name,
                "symbols": preset.symbols,
                "symbols_count": len(preset.symbols),
                "percent_threshold": preset.percent_threshold,
                "interval": preset.interval,
                "is_active": preset.is_active,
                "created_at": preset.created_at.isoformat(),
                "alerts_count": len(preset.alerts)
            }
            for preset in presets
        ]
    
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
        return {
            "running": self.running,
            "monitored_symbols": len(self.monitored_symbols),
            "current_prices_count": len(self._current_prices),
            "total_users": len(self._alerts),
            "total_alerts": sum(len(alerts) for alerts in self._alerts.values()),
            "total_presets": sum(len(presets) for presets in self._presets.values()),
            "active_alerts": sum(
                len([a for a in alerts if a.is_active])
                for alerts in self._alerts.values()
            ),
            **self._stats
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Алиас для get_statistics."""
        return self.get_statistics()
    
    # EVENT HANDLERS
    
    async def _handle_get_user_presets(self, event: Event):
        """Обработка запроса пресетов пользователя."""
        user_id = event.data.get("user_id")
        presets = self.get_user_presets(user_id)
        
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
        
        preset_id = await self.create_preset(user_id, preset_data)
        
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
        
        success = await self.delete_preset(user_id, preset_id)
        
        await event_bus.publish(Event(
            type="price_alerts.preset_deleted",
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
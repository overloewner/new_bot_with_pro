# modules/gas_tracker/service.py
"""Исправленный сервис отслеживания газа Ethereum."""

import asyncio
import aiohttp
import time
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import logging

from shared.events import event_bus, Event, GAS_PRICE_UPDATED, GAS_ALERT_TRIGGERED
from shared.cache.memory_cache import cache_manager
from shared.utils.rate_limiter import get_rate_limiter
from config.settings import get_config

logger = logging.getLogger(__name__)


@dataclass
class GasPrice:
    """Данные о цене газа."""
    safe: float
    standard: float
    fast: float
    instant: float
    timestamp: datetime
    source: str = "etherscan"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'safe': self.safe,
            'standard': self.standard,
            'fast': self.fast,
            'instant': self.instant,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source
        }


@dataclass
class GasAlert:
    """Алерт на цену газа."""
    id: int
    user_id: int
    threshold_gwei: float
    alert_type: str  # 'below', 'above'
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_triggered: Optional[datetime] = None
    times_triggered: int = 0
    cooldown_minutes: int = 5


class GasTrackerService:
    """Исправленный сервис отслеживания газа."""
    
    def __init__(self):
        self.running = False
        self._current_gas: Optional[GasPrice] = None
        self._alerts: Dict[int, List[GasAlert]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self.config = get_config()
        
        # История цен (последние 24 часа)
        self._price_history: deque = deque(maxlen=1440)  # По точке на минуту
        
        # Кеш и rate limiter
        self.cache = cache_manager.get_cache('gas')
        self.rate_limiter = get_rate_limiter('etherscan_free')
        
        # API источники с корректными ключами
        self.gas_apis = [
            {
                'name': 'etherscan',
                'url': 'https://api.etherscan.io/api',
                'params': {
                    'module': 'gastracker', 
                    'action': 'gasoracle', 
                    'apikey': self.config.api.get_etherscan_api_key()
                },
                'parser': self._parse_etherscan_gas
            },
            {
                'name': 'ethgasstation',
                'url': 'https://ethgasstation.info/api/ethgasAPI.json',
                'params': {},
                'parser': self._parse_ethgasstation_gas
            }
        ]
        
        # Статистика
        self._stats = {
            'total_updates': 0,
            'failed_updates': 0,
            'api_calls': 0,
            'alerts_triggered': 0,
            'avg_gas_price': 0.0,
            'price_sources': {}
        }
        
        # Подписываемся на события
        event_bus.subscribe("gas_tracker.get_current_price", self._handle_get_current_price)
        event_bus.subscribe("gas_tracker.add_alert", self._handle_add_alert)
        event_bus.subscribe("gas_tracker.remove_alert", self._handle_remove_alert)
        event_bus.subscribe("gas_tracker.get_user_alerts", self._handle_get_user_alerts)
        event_bus.subscribe("gas_tracker.get_price_history", self._handle_get_price_history)
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        
        # Создаем HTTP сессию
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=10)
        )
        
        # Запускаем кеш
        await self.cache.start()
        
        # Загружаем алерты из кеша/БД
        await self._load_alerts()
        
        # Загружаем историю цен
        await self._load_price_history()
        
        # Запускаем мониторинг
        asyncio.create_task(self._monitor_gas_prices())
        asyncio.create_task(self._cleanup_old_data())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={"module": "gas_tracker"},
            source_module="gas_tracker"
        ))
        
        api_status = "with API key" if self.config.api.has_etherscan_api() else "free tier"
        logger.info(f"Gas Tracker service started ({api_status})")
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        self.running = False
        
        # Сохраняем данные
        await self._save_alerts()
        await self._save_price_history()
        
        # Закрываем сессию
        if self._session:
            await self._session.close()
        
        # Останавливаем кеш
        await self.cache.stop()
        
        await event_bus.publish(Event(
            type="system.module_stopped",
            data={"module": "gas_tracker"},
            source_module="gas_tracker"
        ))
        
        logger.info("Gas Tracker service stopped")
    
    async def _monitor_gas_prices(self) -> None:
        """Основной цикл мониторинга цен на газ."""
        consecutive_failures = 0
        max_failures = 5
        
        while self.running:
            try:
                # Получаем цены газа
                gas_price = await self._fetch_gas_price_with_fallback()
                
                if gas_price:
                    self._current_gas = gas_price
                    consecutive_failures = 0
                    
                    # Сохраняем в историю
                    self._price_history.append({
                        'timestamp': gas_price.timestamp.timestamp(),
                        'safe': gas_price.safe,
                        'standard': gas_price.standard,
                        'fast': gas_price.fast,
                        'instant': gas_price.instant
                    })
                    
                    # Обновляем кеш
                    await self.cache.set('current_gas', gas_price.to_dict(), ttl=60)
                    
                    # Обновляем статистику
                    self._stats['total_updates'] += 1
                    self._stats['avg_gas_price'] = (
                        self._stats['avg_gas_price'] * 0.9 + gas_price.standard * 0.1
                    )
                    
                    # Публикуем событие обновления
                    await event_bus.publish(Event(
                        type=GAS_PRICE_UPDATED,
                        data=gas_price.to_dict(),
                        source_module="gas_tracker"
                    ))
                    
                    # Проверяем алерты
                    await self._check_all_alerts(gas_price)
                    
                    # Интервал успешного обновления
                    sleep_time = 30
                else:
                    consecutive_failures += 1
                    self._stats['failed_updates'] += 1
                    
                    # Увеличиваем интервал при неудачах
                    sleep_time = min(300, 60 * consecutive_failures)
                    logger.warning(f"Failed to fetch gas price, retry in {sleep_time}s")
                    
                    # Если слишком много неудач подряд
                    if consecutive_failures >= max_failures:
                        logger.error("Too many consecutive failures, using cached data")
                        await self._use_cached_gas_price()
                
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Error in gas monitoring: {e}")
                await asyncio.sleep(min(300, 60 * consecutive_failures))
    
    async def _fetch_gas_price_with_fallback(self) -> Optional[GasPrice]:
        """Получение цены газа с fallback между API."""
        last_error = None
        
        for api_config in self.gas_apis:
            try:
                # Проверяем rate limit
                rate_limit_result = await self.rate_limiter.acquire(api_config['name'])
                if not rate_limit_result.allowed:
                    logger.debug(f"Rate limited for {api_config['name']}, waiting {rate_limit_result.wait_time:.2f}s")
                    continue
                
                self._stats['api_calls'] += 1
                start_time = time.time()
                
                # Делаем запрос
                async with self._session.get(
                    api_config['url'],
                    params=api_config['params']
                ) as response:
                    
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        data = await response.json()
                        gas_price = await api_config['parser'](data)
                        
                        if gas_price:
                            # Записываем успешный вызов API
                            await self.rate_limiter.record_api_call(
                                api_config['name'], True, response_time
                            )
                            
                            # Обновляем статистику источников
                            source_stats = self._stats['price_sources']
                            if api_config['name'] not in source_stats:
                                source_stats[api_config['name']] = {'calls': 0, 'successes': 0}
                            
                            source_stats[api_config['name']]['calls'] += 1
                            source_stats[api_config['name']]['successes'] += 1
                            
                            logger.debug(f"Gas price from {api_config['name']}: {gas_price.standard:.1f} gwei")
                            return gas_price
                    else:
                        # Записываем неудачный вызов API
                        await self.rate_limiter.record_api_call(
                            api_config['name'], False, response_time
                        )
                        
                        last_error = f"HTTP {response.status}"
                        logger.warning(f"{api_config['name']} returned {response.status}")
                        
            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.warning(f"{api_config['name']} timed out")
                await self.rate_limiter.record_api_call(api_config['name'], False, 30.0)
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Error with {api_config['name']}: {e}")
                await self.rate_limiter.record_api_call(api_config['name'], False, 0.0)
        
        logger.error(f"All gas APIs failed, last error: {last_error}")
        return None
    
    async def _parse_etherscan_gas(self, data: Dict[str, Any]) -> Optional[GasPrice]:
        """Парсинг ответа Etherscan."""
        try:
            if data.get("status") != "1":
                return None
            
            result = data["result"]
            return GasPrice(
                safe=float(result["SafeGasPrice"]),
                standard=float(result["ProposeGasPrice"]),
                fast=float(result["FastGasPrice"]),
                instant=float(result["FastGasPrice"]) * 1.2,  # Приблизительно
                timestamp=datetime.utcnow(),
                source="etherscan"
            )
        except Exception as e:
            logger.error(f"Error parsing Etherscan gas data: {e}")
            return None
    
    async def _parse_ethgasstation_gas(self, data: Dict[str, Any]) -> Optional[GasPrice]:
        """Парсинг ответа ETH Gas Station."""
        try:
            return GasPrice(
                safe=data.get("safeLow", 0) / 10,  # Конвертируем в gwei
                standard=data.get("average", 0) / 10,
                fast=data.get("fast", 0) / 10,
                instant=data.get("fastest", 0) / 10,
                timestamp=datetime.utcnow(),
                source="ethgasstation"
            )
        except Exception as e:
            logger.error(f"Error parsing ETH Gas Station data: {e}")
            return None
    
    async def _use_cached_gas_price(self):
        """Использование кешированной цены газа при сбоях API."""
        cached_gas = await self.cache.get('current_gas')
        if cached_gas:
            try:
                self._current_gas = GasPrice(
                    safe=cached_gas['safe'],
                    standard=cached_gas['standard'],
                    fast=cached_gas['fast'],
                    instant=cached_gas['instant'],
                    timestamp=datetime.fromisoformat(cached_gas['timestamp']),
                    source=cached_gas.get('source', 'cache')
                )
                logger.info("Using cached gas price data")
            except Exception as e:
                logger.error(f"Error using cached gas price: {e}")
    
    async def _check_all_alerts(self, gas_price: GasPrice) -> None:
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
                
                # Проверяем условие срабатывания
                current_price = gas_price.standard  # Используем стандартную цену
                triggered = False
                
                if alert.alert_type == "below" and current_price <= alert.threshold_gwei:
                    triggered = True
                elif alert.alert_type == "above" and current_price >= alert.threshold_gwei:
                    triggered = True
                
                if triggered:
                    await self._trigger_alert(user_id, alert, current_price, gas_price)
    
    async def _trigger_alert(self, user_id: int, alert: GasAlert, current_price: float, gas_price: GasPrice):
        """Срабатывание алерта."""
        direction = "⬇️" if alert.alert_type == "below" else "⬆️"
        
        # Определяем рекомендацию
        recommendation = self._get_gas_recommendation(current_price)
        
        message = (
            f"{direction} <b>Gas Alert!</b>\n\n"
            f"💰 <b>Текущая цена:</b> {current_price:.1f} gwei\n"
            f"🎯 <b>Ваш порог:</b> {alert.threshold_gwei:.1f} gwei\n\n"
            
            f"📊 <b>Все уровни:</b>\n"
            f"🟢 Безопасный: {gas_price.safe:.1f} gwei\n"
            f"🟡 Стандартный: {gas_price.standard:.1f} gwei\n"
            f"🟠 Быстрый: {gas_price.fast:.1f} gwei\n"
            f"🔴 Мгновенный: {gas_price.instant:.1f} gwei\n\n"
            
            f"💡 <b>Рекомендация:</b> {recommendation}"
        )
        
        await event_bus.publish(Event(
            type=GAS_ALERT_TRIGGERED,
            data={
                "user_id": user_id,
                "message": message,
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "threshold": alert.threshold_gwei,
                "current_price": current_price,
                "gas_prices": gas_price.to_dict()
            },
            source_module="gas_tracker"
        ))
        
        # Обновляем статистику алерта
        alert.last_triggered = datetime.utcnow()
        alert.times_triggered += 1
        self._stats['alerts_triggered'] += 1
        
        # Сохраняем в кеш
        await self._save_alerts()
        
        logger.info(f"Triggered gas alert for user {user_id}: {alert.threshold_gwei} gwei ({alert.alert_type})")
    
    def _get_gas_recommendation(self, current_price: float) -> str:
        """Получение рекомендации по цене газа."""
        if current_price <= 15:
            return "Отличное время для транзакций! 🟢"
        elif current_price <= 30:
            return "Хорошая цена для обычных операций 🟡"
        elif current_price <= 50:
            return "Высокая цена, рассмотрите отложить операцию 🟠"
        else:
            return "Очень высокая цена! Рекомендуем подождать 🔴"
    
    async def _load_alerts(self) -> None:
        """Загрузка алертов из кеша."""
        try:
            cached_alerts = await self.cache.get('user_alerts', {})
            
            for user_id_str, alerts_data in cached_alerts.items():
                user_id = int(user_id_str)
                self._alerts[user_id] = []
                
                for alert_data in alerts_data:
                    alert = GasAlert(
                        id=alert_data['id'],
                        user_id=user_id,
                        threshold_gwei=alert_data['threshold_gwei'],
                        alert_type=alert_data['alert_type'],
                        is_active=alert_data.get('is_active', True),
                        created_at=datetime.fromisoformat(alert_data.get('created_at', datetime.utcnow().isoformat())),
                        last_triggered=datetime.fromisoformat(alert_data['last_triggered']) if alert_data.get('last_triggered') else None,
                        times_triggered=alert_data.get('times_triggered', 0),
                        cooldown_minutes=alert_data.get('cooldown_minutes', 5)
                    )
                    self._alerts[user_id].append(alert)
            
            logger.info(f"Loaded {sum(len(alerts) for alerts in self._alerts.values())} gas alerts from cache")
            
        except Exception as e:
            logger.error(f"Error loading alerts: {e}")
            self._alerts = {}
    
    async def _save_alerts(self) -> None:
        """Сохранение алертов в кеш."""
        try:
            alerts_data = {}
            
            for user_id, alerts in self._alerts.items():
                alerts_data[str(user_id)] = []
                for alert in alerts:
                    alert_dict = {
                        'id': alert.id,
                        'threshold_gwei': alert.threshold_gwei,
                        'alert_type': alert.alert_type,
                        'is_active': alert.is_active,
                        'created_at': alert.created_at.isoformat(),
                        'last_triggered': alert.last_triggered.isoformat() if alert.last_triggered else None,
                        'times_triggered': alert.times_triggered,
                        'cooldown_minutes': alert.cooldown_minutes
                    }
                    alerts_data[str(user_id)].append(alert_dict)
            
            await self.cache.set('user_alerts', alerts_data, ttl=86400)  # 24 часа
            
        except Exception as e:
            logger.error(f"Error saving alerts: {e}")
    
    async def _load_price_history(self) -> None:
        """Загрузка истории цен из кеша."""
        try:
            cached_history = await self.cache.get('price_history', [])
            
            # Фильтруем старые данные (старше 24 часов)
            current_time = time.time()
            cutoff_time = current_time - 86400  # 24 часа
            
            recent_history = [
                entry for entry in cached_history
                if entry.get('timestamp', 0) > cutoff_time
            ]
            
            self._price_history.extend(recent_history)
            logger.info(f"Loaded {len(recent_history)} price history entries")
            
        except Exception as e:
            logger.error(f"Error loading price history: {e}")
    
    async def _save_price_history(self) -> None:
        """Сохранение истории цен в кеш."""
        try:
            history_data = list(self._price_history)
            await self.cache.set('price_history', history_data, ttl=86400)
        except Exception as e:
            logger.error(f"Error saving price history: {e}")
    
    async def _cleanup_old_data(self) -> None:
        """Фоновая очистка старых данных."""
        while self.running:
            try:
                await asyncio.sleep(3600)  # Каждый час
                
                # Очищаем старую историю цен
                current_time = time.time()
                cutoff_time = current_time - 86400  # 24 часа
                
                # Удаляем старые записи
                while (self._price_history and 
                       self._price_history[0].get('timestamp', 0) < cutoff_time):
                    self._price_history.popleft()
                
                # Сохраняем обновленную историю
                await self._save_price_history()
                
                logger.debug("Cleaned up old price history data")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup: {e}")
    
    # PUBLIC API METHODS
    
    async def add_user_alert(
        self, 
        user_id: int, 
        threshold_gwei: float, 
        alert_type: str = "below",
        cooldown_minutes: int = 5
    ) -> bool:
        """Добавление пользовательского алерта."""
        try:
            # Валидация
            if threshold_gwei <= 0 or threshold_gwei > 1000:
                logger.warning(f"Invalid threshold for user {user_id}: {threshold_gwei}")
                return False
            
            if alert_type not in ["below", "above"]:
                logger.warning(f"Invalid alert type for user {user_id}: {alert_type}")
                return False
            
            # Проверяем лимит алертов на пользователя
            if user_id in self._alerts and len(self._alerts[user_id]) >= 10:
                logger.warning(f"Alert limit reached for user {user_id}")
                return False
            
            # Создаем алерт
            alert_id = int(time.time() * 1000) % 2147483647  # Уникальный ID
            alert = GasAlert(
                id=alert_id,
                user_id=user_id,
                threshold_gwei=threshold_gwei,
                alert_type=alert_type,
                cooldown_minutes=cooldown_minutes
            )
            
            # Добавляем в список
            if user_id not in self._alerts:
                self._alerts[user_id] = []
            
            self._alerts[user_id].append(alert)
            
            # Сохраняем
            await self._save_alerts()
            
            logger.info(f"Added gas alert for user {user_id}: {threshold_gwei} gwei ({alert_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error adding gas alert: {e}")
            return False
    
    async def remove_user_alert(self, user_id: int, alert_id: int) -> bool:
        """Удаление пользовательского алерта."""
        try:
            if user_id not in self._alerts:
                return False
            
            original_count = len(self._alerts[user_id])
            self._alerts[user_id] = [
                alert for alert in self._alerts[user_id] 
                if alert.id != alert_id
            ]
            
            if len(self._alerts[user_id]) < original_count:
                await self._save_alerts()
                logger.info(f"Removed gas alert {alert_id} for user {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error removing gas alert: {e}")
            return False
    
    def get_current_gas_price(self) -> Optional[Dict[str, Any]]:
        """Получение текущей цены газа."""
        if not self._current_gas:
            return None
        
        return self._current_gas.to_dict()
    
    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение алертов пользователя."""
        alerts = self._alerts.get(user_id, [])
        return [
            {
                "id": alert.id,
                "threshold_gwei": alert.threshold_gwei,
                "alert_type": alert.alert_type,
                "is_active": alert.is_active,
                "created_at": alert.created_at.isoformat(),
                "last_triggered": alert.last_triggered.isoformat() if alert.last_triggered else None,
                "times_triggered": alert.times_triggered,
                "cooldown_minutes": alert.cooldown_minutes
            }
            for alert in alerts
        ]
    
    def get_price_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Получение истории цен."""
        cutoff_time = time.time() - (hours * 3600)
        
        return [
            entry for entry in self._price_history
            if entry.get('timestamp', 0) > cutoff_time
        ]
    
    def get_gas_statistics(self) -> Dict[str, Any]:
        """Получение статистики газа."""
        if not self._price_history:
            return {}
        
        recent_prices = [entry['standard'] for entry in self._price_history[-60:]]  # Последний час
        
        if not recent_prices:
            return {}
        
        return {
            "current_price": self._current_gas.standard if self._current_gas else 0,
            "avg_1h": sum(recent_prices) / len(recent_prices),
            "min_1h": min(recent_prices),
            "max_1h": max(recent_prices),
            "trend": "rising" if len(recent_prices) > 1 and recent_prices[-1] > recent_prices[0] else "falling",
            "total_alerts": sum(len(alerts) for alerts in self._alerts.values()),
            "active_alerts": sum(
                len([a for a in alerts if a.is_active])
                for alerts in self._alerts.values()
            )
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики сервиса."""
        return {
            "running": self.running,
            "current_gas_available": self._current_gas is not None,
            "total_users": len(self._alerts),
            "total_alerts": sum(len(alerts) for alerts in self._alerts.values()),
            "price_history_size": len(self._price_history),
            "api_config": {
                "etherscan_api": self.config.api.has_etherscan_api(),
                "sources_count": len(self.gas_apis)
            },
            **self._stats
        }
    
    # EVENT HANDLERS
    
    async def _handle_get_current_price(self, event: Event):
        """Обработка запроса текущей цены."""
        gas_price = self.get_current_gas_price()
        
        await event_bus.publish(Event(
            type="gas_tracker.current_price_response",
            data={
                "user_id": event.data.get("user_id"),
                "gas_price": gas_price,
                "statistics": self.get_gas_statistics()
            },
            source_module="gas_tracker"
        ))
    
    async def _handle_add_alert(self, event: Event):
        """Обработка добавления алерта."""
        user_id = event.data.get("user_id")
        threshold = event.data.get("threshold_gwei")
        alert_type = event.data.get("alert_type", "below")
        cooldown = event.data.get("cooldown_minutes", 5)
        
        success = await self.add_user_alert(user_id, threshold, alert_type, cooldown)
        
        await event_bus.publish(Event(
            type="gas_tracker.alert_added",
            data={
                "user_id": user_id,
                "success": success,
                "threshold": threshold,
                "alert_type": alert_type
            },
            source_module="gas_tracker"
        ))
    
    async def _handle_remove_alert(self, event: Event):
        """Обработка удаления алерта."""
        user_id = event.data.get("user_id")
        alert_id = event.data.get("alert_id")
        
        success = await self.remove_user_alert(user_id, alert_id)
        
        await event_bus.publish(Event(
            type="gas_tracker.alert_removed",
            data={
                "user_id": user_id,
                "alert_id": alert_id,
                "success": success
            },
            source_module="gas_tracker"
        ))
    
    async def _handle_get_user_alerts(self, event: Event):
        """Обработка запроса алертов пользователя."""
        user_id = event.data.get("user_id")
        alerts = self.get_user_alerts(user_id)
        
        await event_bus.publish(Event(
            type="gas_tracker.user_alerts_response",
            data={
                "user_id": user_id,
                "alerts": alerts
            },
            source_module="gas_tracker"
        ))
    
    async def _handle_get_price_history(self, event: Event):
        """Обработка запроса истории цен."""
        hours = event.data.get("hours", 24)
        history = self.get_price_history(hours)
        
        await event_bus.publish(Event(
            type="gas_tracker.price_history_response",
            data={
                "user_id": event.data.get("user_id"),
                "history": history,
                "hours": hours
            },
            source_module="gas_tracker"
        ))
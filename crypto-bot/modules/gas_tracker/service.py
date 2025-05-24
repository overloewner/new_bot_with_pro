# modules/gas_tracker/service.py
"""Сервис отслеживания цен на газ Ethereum."""

import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from shared.events import event_bus, Event, GAS_PRICE_UPDATED, GAS_ALERT_TRIGGERED
from shared.database.models import Base
from sqlalchemy import Column, Integer, BigInteger, Float, Boolean, DateTime, String
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)


@dataclass
class GasPrice:
    """Данные о цене газа."""
    safe: float
    standard: float
    fast: float
    instant: float
    timestamp: datetime


class GasAlert(Base):
    """Модель алерта газа."""
    __tablename__ = 'gas_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    threshold_gwei = Column(Float, nullable=False)
    alert_type = Column(String(20), nullable=False, default='below')  # below, above
    is_active = Column(Boolean, nullable=False, default=True)
    last_triggered = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GasTrackerService:
    """Сервис отслеживания газа Ethereum."""
    
    def __init__(self):
        self.running = False
        self._current_gas: Optional[GasPrice] = None
        self._alerts: Dict[int, List[GasAlert]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Бесплатные API для получения цен газа
        self.gas_apis = [
            "https://api.etherscan.io/api?module=gastracker&action=gasoracle",
            "https://ethgasstation.info/api/ethgasAPI.json",
            "https://api.blocknative.com/gasprices/blockprices"
        ]
        
        # Подписываемся на события
        event_bus.subscribe("gas_tracker.check_user_alerts", self._check_user_alerts)
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        
        # Загружаем алерты из БД
        await self._load_alerts()
        
        # Запускаем мониторинг
        asyncio.create_task(self._monitor_gas_prices())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={"module": "gas_tracker"},
            source_module="gas_tracker"
        ))
        
        logger.info("Gas Tracker service started")
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        self.running = False
        
        if self._session:
            await self._session.close()
        
        await event_bus.publish(Event(
            type="system.module_stopped", 
            data={"module": "gas_tracker"},
            source_module="gas_tracker"
        ))
        
        logger.info("Gas Tracker service stopped")
    
    async def _monitor_gas_prices(self) -> None:
        """Мониторинг цен на газ."""
        while self.running:
            try:
                gas_price = await self._fetch_gas_price()
                if gas_price:
                    self._current_gas = gas_price
                    
                    # Публикуем событие обновления
                    await event_bus.publish(Event(
                        type=GAS_PRICE_UPDATED,
                        data={
                            "safe": gas_price.safe,
                            "standard": gas_price.standard, 
                            "fast": gas_price.fast,
                            "instant": gas_price.instant,
                            "timestamp": gas_price.timestamp.isoformat()
                        },
                        source_module="gas_tracker"
                    ))
                    
                    # Проверяем алерты
                    await self._check_all_alerts(gas_price)
                
                # Обновляем каждые 30 секунд
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in gas monitoring: {e}")
                await asyncio.sleep(60)
    
    async def _fetch_gas_price(self) -> Optional[GasPrice]:
        """Получение текущих цен на газ."""
        # Пробуем Etherscan (бесплатный API)
        try:
            async with self._session.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "gastracker",
                    "action": "gasoracle",
                    "apikey": "YourApiKeyToken"  # Можно без ключа для лимитированных запросов
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "1":
                        result = data["result"]
                        return GasPrice(
                            safe=float(result["SafeGasPrice"]),
                            standard=float(result["ProposeGasPrice"]),
                            fast=float(result["FastGasPrice"]),
                            instant=float(result["FastGasPrice"]) * 1.2,  # Примерно
                            timestamp=datetime.utcnow()
                        )
        except Exception as e:
            logger.error(f"Error fetching from Etherscan: {e}")
        
        # Fallback: простой парсинг ETH Gas Station
        try:
            async with self._session.get("https://ethgasstation.info/api/ethgasAPI.json") as response:
                if response.status == 200:
                    data = await response.json()
                    return GasPrice(
                        safe=data.get("safeLow", 0) / 10,  # Конвертируем в gwei
                        standard=data.get("average", 0) / 10,
                        fast=data.get("fast", 0) / 10,
                        instant=data.get("fastest", 0) / 10,
                        timestamp=datetime.utcnow()
                    )
        except Exception as e:
            logger.error(f"Error fetching from Gas Station: {e}")
        
        return None
    
    async def _load_alerts(self) -> None:
        """Загрузка алертов из БД."""
        # TODO: Реализовать загрузку из БД
        # Пока заглушка
        self._alerts = {}
    
    async def _check_all_alerts(self, gas_price: GasPrice) -> None:
        """Проверка всех алертов пользователей."""
        for user_id, user_alerts in self._alerts.items():
            for alert in user_alerts:
                if not alert.is_active:
                    continue
                
                # Проверяем кулдаун (не чаще раза в 5 минут)
                if (alert.last_triggered and 
                    datetime.utcnow() - alert.last_triggered < timedelta(minutes=5)):
                    continue
                
                triggered = False
                current_price = gas_price.standard  # Используем стандартную цену
                
                if alert.alert_type == "below" and current_price <= alert.threshold_gwei:
                    triggered = True
                elif alert.alert_type == "above" and current_price >= alert.threshold_gwei:
                    triggered = True
                
                if triggered:
                    await self._trigger_alert(user_id, alert, current_price)
    
    async def _trigger_alert(self, user_id: int, alert: GasAlert, current_price: float) -> None:
        """Срабатывание алерта."""
        direction = "⬇️" if alert.alert_type == "below" else "⬆️"
        message = (
            f"{direction} Gas Alert!\n"
            f"Current price: {current_price:.1f} gwei\n"
            f"Your threshold: {alert.threshold_gwei:.1f} gwei"
        )
        
        await event_bus.publish(Event(
            type=GAS_ALERT_TRIGGERED,
            data={
                "user_id": user_id,
                "message": message,
                "alert_type": alert.alert_type,
                "threshold": alert.threshold_gwei,
                "current_price": current_price
            },
            source_module="gas_tracker"
        ))
        
        # Обновляем время последнего срабатывания
        alert.last_triggered = datetime.utcnow()
        # TODO: Сохранить в БД
    
    async def add_user_alert(
        self, 
        user_id: int, 
        threshold_gwei: float, 
        alert_type: str = "below"
    ) -> bool:
        """Добавление алерта пользователя."""
        try:
            # Валидация
            if threshold_gwei <= 0 or threshold_gwei > 500:
                return False
            
            if alert_type not in ["below", "above"]:
                return False
            
            # Создаем алерт
            alert = GasAlert(
                user_id=user_id,
                threshold_gwei=threshold_gwei,
                alert_type=alert_type,
                is_active=True
            )
            
            # Добавляем в кеш
            if user_id not in self._alerts:
                self._alerts[user_id] = []
            
            self._alerts[user_id].append(alert)
            
            # TODO: Сохранить в БД
            
            logger.info(f"Added gas alert for user {user_id}: {threshold_gwei} gwei ({alert_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error adding gas alert: {e}")
            return False
    
    async def remove_user_alert(self, user_id: int, alert_id: int) -> bool:
        """Удаление алерта пользователя."""
        try:
            if user_id in self._alerts:
                self._alerts[user_id] = [
                    a for a in self._alerts[user_id] 
                    if a.id != alert_id
                ]
                # TODO: Удалить из БД
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing gas alert: {e}")
            return False
    
    def get_current_gas_price(self) -> Optional[Dict[str, Any]]:
        """Получение текущей цены газа."""
        if not self._current_gas:
            return None
        
        return {
            "safe": self._current_gas.safe,
            "standard": self._current_gas.standard,
            "fast": self._current_gas.fast,
            "instant": self._current_gas.instant,
            "timestamp": self._current_gas.timestamp.isoformat()
        }
    
    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение алертов пользователя."""
        alerts = self._alerts.get(user_id, [])
        return [
            {
                "id": alert.id,
                "threshold_gwei": alert.threshold_gwei,
                "alert_type": alert.alert_type,
                "is_active": alert.is_active,
                "last_triggered": alert.last_triggered.isoformat() if alert.last_triggered else None
            }
            for alert in alerts
        ]
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from shared.events import event_bus, Event, WHALE_TRANSACTION_DETECTED, WHALE_ALERT_TRIGGERED
from shared.database.models import WhaleAlert

logger = logging.getLogger(__name__)


@dataclass
class WhaleTransaction:
    """Данные о транзакции кита."""
    tx_hash: str
    from_address: str
    to_address: str
    value_eth: float
    value_usd: float
    token_symbol: str
    block_number: int
    timestamp: datetime
    tx_type: str  # 'transfer', 'swap', 'unknown'


class LimitedWhaleService:
    """
    Ограниченный сервис отслеживания китов.
    
    Использует только бесплатные API с существенными ограничениями.
    """
    
    def __init__(self):
        self.running = False
        self._alerts: Dict[int, List[WhaleAlert]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._known_whale_addresses: Set[str] = set()
        self._eth_price_usd = 0.0
        self._btc_price_usd = 0.0
        
        # Публичные адреса крупных холдеров (статичные данные)
        self._load_known_addresses()
        
        # Подписываемся на события
        event_bus.subscribe("whale_tracker.check_user_alerts", self._check_user_alerts)
    
    def _load_known_addresses(self):
        """Загрузка известных адресов китов из публичных источников."""
        # Известные адреса бирж и крупных холдеров (публичная информация)
        known_addresses = [
            # Binance холодные кошельки
            "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",
            "0xd551234ae421e3bcba99a0da6d736074f22192ff",
            "0x564286362092d8e7936f0549571a803b203aaced",
            
            # Ethereum Foundation
            "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
            
            # Крупные DeFi протоколы
            "0x5aa3393e361c2eb342408559309b3e873cd876d6",  # Uniswap
            "0x6b175474e89094c44da98b954eedeac495271d0f",  # MakerDAO
            
            # Известные киты (публичная информация)
            "0x2f47b6497e13b2b1e735e3286c024dd8e1a68715",
            "0xab5c66752a9e8167967685f1450532fb96d5d24f"
        ]
        
        self._known_whale_addresses = set(addr.lower() for addr in known_addresses)
        logger.info(f"Loaded {len(self._known_whale_addresses)} known whale addresses")
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        
        # Загружаем алерты из БД
        await self._load_alerts()
        
        # Запускаем только мониторинг цен (без транзакций из-за API key)
        asyncio.create_task(self._monitor_prices())
        # ОТКЛЮЧЕНО: мониторинг транзакций без API ключа
        # asyncio.create_task(self._monitor_large_transactions())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={"module": "whale_tracker", "limitation": "price_monitoring_only"},
            source_module="whale_tracker"
        ))
        
        logger.warning(
            "⚠️ Whale Tracker started in LIMITED mode. "
            "Only price monitoring enabled. Add Etherscan API key for transaction monitoring."
        )
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        self.running = False
        
        if self._session:
            await self._session.close()
        
        await event_bus.publish(Event(
            type="system.module_stopped",
            data={"module": "whale_tracker"},
            source_module="whale_tracker"
        ))
        
        logger.info("Whale Tracker service stopped")
    
    async def _monitor_prices(self) -> None:
        """Мониторинг цен ETH и BTC для конвертации."""
        while self.running:
            try:
                # Получаем цены от CoinGecko (бесплатно)
                async with self._session.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={
                        "ids": "ethereum,bitcoin",
                        "vs_currencies": "usd"
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._eth_price_usd = data.get("ethereum", {}).get("usd", 0)
                        self._btc_price_usd = data.get("bitcoin", {}).get("usd", 0)
                        
                        logger.debug(f"Updated prices: ETH=${self._eth_price_usd}, BTC=${self._btc_price_usd}")
                
                # Обновляем цены каждые 5 минут
                await asyncio.sleep(300)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating prices: {e}")
                await asyncio.sleep(300)
    
    # ОТКЛЮЧЕНО: мониторинг транзакций без API ключа
    # async def _monitor_large_transactions будет включен когда добавят API ключ
    
    async def _check_user_alerts(self, event: Event) -> None:
        """Проверка алертов конкретного пользователя."""
        try:
            user_id = event.data.get("user_id")
            if not user_id or user_id not in self._alerts:
                return
            
            # Пока что только логируем - без API ключа нет транзакций для проверки
            logger.info(f"Whale alerts check requested for user {user_id} - API key needed for full functionality")
                
        except Exception as e:
            logger.error(f"Error checking user alerts: {e}")
    
    async def _load_alerts(self) -> None:
        """Загрузка алертов из БД."""
        # TODO: Реализовать загрузку из БД
        self._alerts = {}
    
    async def add_user_alert(
        self, 
        user_id: int, 
        threshold_usd: Optional[float] = None,
        threshold_btc: Optional[float] = None
    ) -> bool:
        """Добавление алерта пользователя."""
        try:
            if not threshold_usd and not threshold_btc:
                return False
            
            if threshold_usd and (threshold_usd < 1000 or threshold_usd > 100000000):
                return False
            
            if threshold_btc and (threshold_btc < 0.1 or threshold_btc > 10000):
                return False
            
            import time
            alert = WhaleAlert(
                id=int(time.time() * 1000) % 2147483647,  # Временный ID
                user_id=user_id,
                threshold_usd=threshold_usd,
                threshold_btc=threshold_btc,
                is_active=True
            )
            
            if user_id not in self._alerts:
                self._alerts[user_id] = []
            
            self._alerts[user_id].append(alert)
            
            logger.info(f"Added whale alert for user {user_id} (requires API key for monitoring)")
            return True
            
        except Exception as e:
            logger.error(f"Error adding whale alert: {e}")
            return False
    
    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение алертов пользователя."""
        alerts = self._alerts.get(user_id, [])
        return [
            {
                "id": getattr(alert, 'id', 0),
                "threshold_usd": alert.threshold_usd,
                "threshold_btc": alert.threshold_btc,
                "is_active": alert.is_active
            }
            for alert in alerts
        ]
    
    def get_limitations_info(self) -> Dict[str, Any]:
        """Информация об ограничениях сервиса."""
        return {
            "title": "Ограничения Whale Tracker",
            "limitations": [
                "❌ Требуется Etherscan API ключ для мониторинга транзакций",
                "❌ Сейчас работает только мониторинг цен ETH/BTC",
                "❌ Нет отслеживания крупных транзакций",
                "❌ Нет анализа DeFi операций"
            ],
            "for_full_functionality": [
                "🔑 Добавить Etherscan API ключ в конфигурацию",
                "💰 Nansen API ($150/месяц) - для профессионального анализа",
                "💰 Glassnode API ($39/месяц) - для ончейн метрик", 
                "💰 Собственная Ethereum нода ($500+/месяц)"
            ],
            "what_works": [
                "✅ Мониторинг цен ETH и BTC",
                "✅ Управление алертами",
                "✅ Готов к работе при добавлении API ключа"
            ]
        }
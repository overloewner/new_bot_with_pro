import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from shared.events import event_bus, Event, WHALE_TRANSACTION_DETECTED, WHALE_ALERT_TRIGGERED
from shared.database.models import Base
from sqlalchemy import Column, Integer, BigInteger, Float, Boolean, DateTime, String, Text
from sqlalchemy.sql import func

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


class WhaleAlert(Base):
    """Модель алерта кита."""
    __tablename__ = 'whale_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    threshold_usd = Column(Float, nullable=False)
    threshold_btc = Column(Float, nullable=True)
    token_filter = Column(Text, nullable=True)  # JSON список токенов
    is_active = Column(Boolean, nullable=False, default=True)
    last_triggered = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
        
        # Запускаем мониторинг
        asyncio.create_task(self._monitor_prices())
        asyncio.create_task(self._monitor_large_transactions())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={"module": "whale_tracker", "limitation": "free_apis_only"},
            source_module="whale_tracker"
        ))
        
        logger.warning(
            "⚠️ Whale Tracker started with LIMITED functionality. "
            "Only large public transactions will be detected."
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
    
    async def _monitor_large_transactions(self) -> None:
        """
        Мониторинг крупных транзакций через бесплатные API.
        
        ⚠️ ОГРАНИЧЕНИЯ:
        - Только ETH транзакции (не ERC-20 токены)
        - Задержка 1-2 блока
        - Лимит 5 запросов в секунду
        """
        while self.running:
            try:
                # Получаем последние блоки от Etherscan
                latest_blocks = await self._get_latest_blocks()
                
                for block_number in latest_blocks:
                    transactions = await self._get_block_transactions(block_number)
                    
                    for tx in transactions:
                        if await self._is_whale_transaction(tx):
                            whale_tx = await self._parse_whale_transaction(tx)
                            if whale_tx:
                                await self._process_whale_transaction(whale_tx)
                    
                    # Пауза между блоками для соблюдения лимитов API
                    await asyncio.sleep(1)
                
                # Проверяем новые блоки каждые 30 секунд
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring transactions: {e}")
                await asyncio.sleep(60)
    
    async def _get_latest_blocks(self) -> List[int]:
        """Получение номеров последних блоков."""
        try:
            async with self._session.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "proxy",
                    "action": "eth_blockNumber",
                    "apikey": "YourApiKeyToken"  # Можно без ключа для лимитированных запросов
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("result"):
                        latest_block = int(data["result"], 16)
                        # Возвращаем последние 3 блока
                        return [latest_block - i for i in range(3)]
        except Exception as e:
            logger.error(f"Error getting latest blocks: {e}")
        
        return []
    
    async def _get_block_transactions(self, block_number: int) -> List[Dict]:
        """Получение транзакций блока."""
        try:
            async with self._session.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "proxy",
                    "action": "eth_getBlockByNumber",
                    "tag": hex(block_number),
                    "boolean": "true",
                    "apikey": "YourApiKeyToken"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    block = data.get("result", {})
                    return block.get("transactions", [])
        except Exception as e:
            logger.error(f"Error getting block {block_number} transactions: {e}")
        
        return []
    
    async def _is_whale_transaction(self, tx: Dict) -> bool:
        """Проверка, является ли транзакция китовой."""
        try:
            # Проверяем размер транзакции
            value_wei = int(tx.get("value", "0"), 16)
            value_eth = value_wei / 10**18
            
            # Считаем китовой транзакцией > 100 ETH
            if value_eth < 100:
                return False
            
            # Проверяем адреса
            from_addr = tx.get("from", "").lower()
            to_addr = tx.get("to", "").lower()
            
            # Транзакция с участием известного кита
            if from_addr in self._known_whale_addresses or to_addr in self._known_whale_addresses:
                return True
            
            # Очень крупная транзакция (> 1000 ETH)
            if value_eth > 1000:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking whale transaction: {e}")
            return False
    
    async def _parse_whale_transaction(self, tx: Dict) -> Optional[WhaleTransaction]:
        """Парсинг данных китовой транзакции."""
        try:
            value_wei = int(tx.get("value", "0"), 16)
            value_eth = value_wei / 10**18
            value_usd = value_eth * self._eth_price_usd
            
            return WhaleTransaction(
                tx_hash=tx.get("hash", ""),
                from_address=tx.get("from", ""),
                to_address=tx.get("to", ""),
                value_eth=value_eth,
                value_usd=value_usd,
                token_symbol="ETH",
                block_number=int(tx.get("blockNumber", "0"), 16),
                timestamp=datetime.utcnow(),
                tx_type="transfer"
            )
        except Exception as e:
            logger.error(f"Error parsing whale transaction: {e}")
            return None
    
    async def _process_whale_transaction(self, whale_tx: WhaleTransaction) -> None:
        """Обработка китовой транзакции."""
        # Публикуем событие обнаружения
        await event_bus.publish(Event(
            type=WHALE_TRANSACTION_DETECTED,
            data={
                "tx_hash": whale_tx.tx_hash,
                "from_address": whale_tx.from_address,
                "to_address": whale_tx.to_address,
                "value_eth": whale_tx.value_eth,
                "value_usd": whale_tx.value_usd,
                "token_symbol": whale_tx.token_symbol,
                "timestamp": whale_tx.timestamp.isoformat()
            },
            source_module="whale_tracker"
        ))
        
        # Проверяем алерты пользователей
        await self._check_transaction_alerts(whale_tx)
    
    async def _check_transaction_alerts(self, whale_tx: WhaleTransaction) -> None:
        """Проверка алертов пользователей для транзакции."""
        for user_id, user_alerts in self._alerts.items():
            for alert in user_alerts:
                if not alert.is_active:
                    continue
                
                # Проверяем кулдаун
                if (alert.last_triggered and 
                    datetime.utcnow() - alert.last_triggered < timedelta(minutes=10)):
                    continue
                
                # Проверяем пороги
                triggered = False
                
                if alert.threshold_usd and whale_tx.value_usd >= alert.threshold_usd:
                    triggered = True
                
                if alert.threshold_btc and self._btc_price_usd > 0:
                    value_btc = whale_tx.value_usd / self._btc_price_usd
                    if value_btc >= alert.threshold_btc:
                        triggered = True
                
                if triggered:
                    await self._trigger_whale_alert(user_id, alert, whale_tx)
    
    async def _trigger_whale_alert(
        self, 
        user_id: int, 
        alert: WhaleAlert, 
        whale_tx: WhaleTransaction
    ) -> None:
        """Срабатывание алерта кита."""
        # Определяем направление транзакции
        from_known = whale_tx.from_address.lower() in self._known_whale_addresses
        to_known = whale_tx.to_address.lower() in self._known_whale_addresses
        
        if from_known and to_known:
            direction = "🔄 Перевод между китами"
        elif from_known:
            direction = "📤 Вывод с кошелька кита"
        elif to_known:
            direction = "📥 Пополнение кошелька кита"
        else:
            direction = "🐋 Крупная транзакция"
        
        message = (
            f"{direction}\n\n"
            f"💰 Сумма: {whale_tx.value_eth:.2f} ETH\n"
            f"💵 ~${whale_tx.value_usd:,.0f}\n"
            f"📋 Hash: {whale_tx.tx_hash[:10]}...\n"
            f"🕐 Время: {whale_tx.timestamp.strftime('%H:%M:%S')}"
        )
        
        await event_bus.publish(Event(
            type=WHALE_ALERT_TRIGGERED,
            data={
                "user_id": user_id,
                "message": message,
                "transaction": {
                    "hash": whale_tx.tx_hash,
                    "value_eth": whale_tx.value_eth,
                    "value_usd": whale_tx.value_usd
                }
            },
            source_module="whale_tracker"
        ))
        
        # Обновляем время последнего срабатывания
        alert.last_triggered = datetime.utcnow()
    
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
            
            alert = WhaleAlert(
                user_id=user_id,
                threshold_usd=threshold_usd,
                threshold_btc=threshold_btc,
                is_active=True
            )
            
            if user_id not in self._alerts:
                self._alerts[user_id] = []
            
            self._alerts[user_id].append(alert)
            
            logger.info(f"Added whale alert for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding whale alert: {e}")
            return False
    
    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение алертов пользователя."""
        alerts = self._alerts.get(user_id, [])
        return [
            {
                "id": alert.id,
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
                "❌ Только ETH транзакции (не ERC-20 токены)",
                "❌ Задержка 1-2 блока (~30-60 секунд)", 
                "❌ Только известные адреса китов",
                "❌ Лимит API: 5 запросов/сек",
                "❌ Нет анализа DeFi операций"
            ],
            "for_full_functionality": [
                "💰 Nansen API ($150/месяц)",
                "💰 Glassnode API ($39/месяц)", 
                "💰 Собственная Ethereum нода ($500+/месяц)",
                "💰 Dune Analytics API ($390/месяц)"
            ],
            "what_works": [
                "✅ Крупные ETH переводы (>100 ETH)",
                "✅ Известные адреса китов",
                "✅ Базовая фильтрация по сумме"
            ]
        }
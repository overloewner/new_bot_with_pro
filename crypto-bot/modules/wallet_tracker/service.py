import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from shared.events import event_bus, Event, WALLET_TRANSACTION_DETECTED, WALLET_ALERT_TRIGGERED
from shared.database.models import Base
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)


@dataclass
class WalletTransaction:
    """Данные о транзакции кошелька."""
    tx_hash: str
    from_address: str
    to_address: str
    value_eth: float
    value_usd: float
    gas_used: int
    gas_price: float
    block_number: int
    timestamp: datetime
    status: str  # 'success', 'failed'


class WalletAlert(Base):
    """Модель алерта кошелька."""
    __tablename__ = 'wallet_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    wallet_address = Column(String(42), nullable=False)
    min_value_eth = Column(BigInteger, nullable=True)  # Минимальная сумма для уведомления
    track_incoming = Column(Boolean, nullable=False, default=True)
    track_outgoing = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_checked_block = Column(BigInteger, nullable=True)
    last_triggered = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LimitedWalletTrackerService:
    """
    Ограниченный сервис отслеживания кошельков.
    
    ⚠️ НЕ РАБОТАЕТ В РЕАЛЬНОМ ВРЕМЕНИ!
    Проверяет кошельки каждые 2-5 минут через бесплатный API.
    """
    
    def __init__(self):
        self.running = False
        self._alerts: Dict[int, List[WalletAlert]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._eth_price_usd = 0.0
        self._last_tx_hashes: Dict[str, Set[str]] = {}  # address -> set of tx hashes
        
        # Подписываемся на события
        event_bus.subscribe("wallet_tracker.check_wallet", self._check_specific_wallet)
    
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
        asyncio.create_task(self._monitor_eth_price())
        asyncio.create_task(self._periodic_wallet_check())
        
        await event_bus.publish(Event(
            type="system.module_started",
            data={
                "module": "wallet_tracker", 
                "limitation": "delayed_monitoring_only",
                "check_interval": "2-5 minutes"
            },
            source_module="wallet_tracker"
        ))
        
        logger.warning(
            "⚠️ Wallet Tracker started with SEVERE limitations. "
            "Only delayed monitoring via free API."
        )
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        self.running = False
        
        if self._session:
            await self._session.close()
        
        await event_bus.publish(Event(
            type="system.module_stopped",
            data={"module": "wallet_tracker"},
            source_module="wallet_tracker"
        ))
        
        logger.info("Wallet Tracker service stopped")
    
    async def _monitor_eth_price(self) -> None:
        """Мониторинг цены ETH для конвертации."""
        while self.running:
            try:
                async with self._session.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": "ethereum", "vs_currencies": "usd"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._eth_price_usd = data.get("ethereum", {}).get("usd", 0)
                
                await asyncio.sleep(300)  # Каждые 5 минут
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating ETH price: {e}")
                await asyncio.sleep(300)
    
    async def _periodic_wallet_check(self) -> None:
        """
        Периодическая проверка кошельков.
        
        ⚠️ ОГРАНИЧЕНИЯ:
        - Проверка каждые 2-5 минут (не реальное время)
        - Лимит API Etherscan: 5 запросов/сек
        - Задержка обнаружения: 2-10 минут
        """
        while self.running:
            try:
                all_addresses = set()
                
                # Собираем все отслеживаемые адреса
                for user_alerts in self._alerts.values():
                    for alert in user_alerts:
                        if alert.is_active:
                            all_addresses.add(alert.wallet_address.lower())
                
                # Проверяем каждый адрес
                for address in all_addresses:
                    await self._check_wallet_transactions(address)
                    
                    # Пауза между запросами для соблюдения лимитов
                    await asyncio.sleep(1)
                
                # Интервал между полными циклами проверки
                check_interval = max(120, len(all_addresses) * 2)  # Минимум 2 минуты
                logger.debug(f"Checked {len(all_addresses)} wallets, next check in {check_interval}s")
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic wallet check: {e}")
                await asyncio.sleep(300)
    
    async def _check_wallet_transactions(self, address: str) -> None:
        """Проверка транзакций конкретного кошелька."""
        try:
            # Получаем последние транзакции
            transactions = await self._get_wallet_transactions(address, limit=10)
            
            if not transactions:
                return
            
            # Получаем известные транзакции для этого адреса
            known_hashes = self._last_tx_hashes.get(address, set())
            new_transactions = []
            
            for tx in transactions:
                tx_hash = tx.get('hash', '')
                if tx_hash and tx_hash not in known_hashes:
                    new_transactions.append(tx)
                    known_hashes.add(tx_hash)
            
            # Обновляем кеш
            self._last_tx_hashes[address] = known_hashes
            
            # Обрабатываем новые транзакции
            for tx in new_transactions:
                wallet_tx = await self._parse_wallet_transaction(tx)
                if wallet_tx:
                    await self._process_wallet_transaction(address, wallet_tx)
                    
        except Exception as e:
            logger.error(f"Error checking wallet {address}: {e}")
    
    async def _get_wallet_transactions(self, address: str, limit: int = 10) -> List[Dict]:
        """Получение транзакций кошелька через Etherscan API."""
        try:
            async with self._session.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": limit,
                    "sort": "desc",
                    "apikey": "YourApiKeyToken"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "1":
                        return data.get("result", [])
        except Exception as e:
            logger.error(f"Error getting transactions for {address}: {e}")
        
        return []
    
    async def _parse_wallet_transaction(self, tx: Dict) -> Optional[WalletTransaction]:
        """Парсинг данных транзакции кошелька."""
        try:
            value_wei = int(tx.get("value", "0"))
            value_eth = value_wei / 10**18
            value_usd = value_eth * self._eth_price_usd
            
            gas_used = int(tx.get("gasUsed", "0"))
            gas_price_wei = int(tx.get("gasPrice", "0"))
            gas_price_gwei = gas_price_wei / 10**9
            
            timestamp = datetime.fromtimestamp(int(tx.get("timeStamp", "0")))
            
            return WalletTransaction(
                tx_hash=tx.get("hash", ""),
                from_address=tx.get("from", ""),
                to_address=tx.get("to", ""),
                value_eth=value_eth,
                value_usd=value_usd,
                gas_used=gas_used,
                gas_price=gas_price_gwei,
                block_number=int(tx.get("blockNumber", "0")),
                timestamp=timestamp,
                status="success" if tx.get("isError") == "0" else "failed"
            )
        except Exception as e:
            logger.error(f"Error parsing wallet transaction: {e}")
            return None
    
    async def _process_wallet_transaction(self, watched_address: str, wallet_tx: WalletTransaction) -> None:
        """Обработка транзакции отслеживаемого кошелька."""
        # Публикуем событие обнаружения
        await event_bus.publish(Event(
            type=WALLET_TRANSACTION_DETECTED,
            data={
                "watched_address": watched_address,
                "tx_hash": wallet_tx.tx_hash,
                "from_address": wallet_tx.from_address,
                "to_address": wallet_tx.to_address,
                "value_eth": wallet_tx.value_eth,
                "value_usd": wallet_tx.value_usd,
                "timestamp": wallet_tx.timestamp.isoformat()
            },
            source_module="wallet_tracker"
        ))
        
        # Проверяем алерты пользователей
        await self._check_wallet_alerts(watched_address, wallet_tx)
    
    async def _check_wallet_alerts(self, watched_address: str, wallet_tx: WalletTransaction) -> None:
        """Проверка алертов для транзакции кошелька."""
        for user_id, user_alerts in self._alerts.items():
            for alert in user_alerts:
                if not alert.is_active:
                    continue
                
                if alert.wallet_address.lower() != watched_address.lower():
                    continue
                
                # Проверяем кулдаун
                if (alert.last_triggered and 
                    datetime.utcnow() - alert.last_triggered < timedelta(minutes=5)):
                    continue
                
                # Определяем тип транзакции
                is_incoming = wallet_tx.to_address.lower() == watched_address.lower()
                is_outgoing = wallet_tx.from_address.lower() == watched_address.lower()
                
                # Проверяем настройки отслеживания
                should_notify = False
                
                if is_incoming and alert.track_incoming:
                    should_notify = True
                elif is_outgoing and alert.track_outgoing:
                    should_notify = True
                
                # Проверяем минимальную сумму
                if should_notify and alert.min_value_eth:
                    min_value_eth = alert.min_value_eth / 10**18  # Конвертируем из wei
                    if wallet_tx.value_eth < min_value_eth:
                        should_notify = False
                
                if should_notify:
                    await self._trigger_wallet_alert(user_id, alert, wallet_tx, is_incoming)
    
    async def _trigger_wallet_alert(
        self, 
        user_id: int, 
        alert: WalletAlert, 
        wallet_tx: WalletTransaction,
        is_incoming: bool
    ) -> None:
        """Срабатывание алерта кошелька."""
        direction = "📥 Входящая" if is_incoming else "📤 Исходящая"
        
        message = (
            f"{direction} транзакция\n\n"
            f"👛 Кошелек: {alert.wallet_address[:6]}...{alert.wallet_address[-4:]}\n"
            f"💰 Сумма: {wallet_tx.value_eth:.4f} ETH\n"
            f"💵 ~${wallet_tx.value_usd:.2f}\n"
            f"⛽ Gas: {wallet_tx.gas_price:.1f} gwei\n"
            f"📋 Hash: {wallet_tx.tx_hash[:10]}...\n"
            f"🕐 Время: {wallet_tx.timestamp.strftime('%H:%M:%S')}"
        )
        
        if wallet_tx.status == "failed":
            message += "\n❌ Статус: НЕУСПЕШНАЯ"
        
        await event_bus.publish(Event(
            type=WALLET_ALERT_TRIGGERED,
            data={
                "user_id": user_id,
                "message": message,
                "transaction": {
                    "hash": wallet_tx.tx_hash,
                    "value_eth": wallet_tx.value_eth,
                    "value_usd": wallet_tx.value_usd,
                    "is_incoming": is_incoming
                }
            },
            source_module="wallet_tracker"
        ))
        
        # Обновляем время последнего срабатывания
        alert.last_triggered = datetime.utcnow()
    
    async def _load_alerts(self) -> None:
        """Загрузка алертов из БД."""
        # TODO: Реализовать загрузку из БД
        self._alerts = {}
    
    async def add_wallet_alert(
        self, 
        user_id: int, 
        wallet_address: str,
        min_value_eth: float = 0.0,
        track_incoming: bool = True,
        track_outgoing: bool = True
    ) -> bool:
        """Добавление алерта отслеживания кошелька."""
        try:
            # Валидация адреса
            if not self._is_valid_eth_address(wallet_address):
                return False
            
            # Ограничение на количество кошельков на пользователя
            current_alerts = len(self._alerts.get(user_id, []))
            if current_alerts >= 5:  # Максимум 5 кошельков
                return False
            
            alert = WalletAlert(
                user_id=user_id,
                wallet_address=wallet_address.lower(),
                min_value_eth=int(min_value_eth * 10**18),  # Конвертируем в wei
                track_incoming=track_incoming,
                track_outgoing=track_outgoing,
                is_active=True
            )
            
            if user_id not in self._alerts:
                self._alerts[user_id] = []
            
            self._alerts[user_id].append(alert)
            
            # Инициализируем кеш транзакций для нового адреса
            if wallet_address.lower() not in self._last_tx_hashes:
                await self._initialize_wallet_cache(wallet_address.lower())
            
            logger.info(f"Added wallet alert for user {user_id}: {wallet_address}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding wallet alert: {e}")
            return False
    
    def _is_valid_eth_address(self, address: str) -> bool:
        """Проверка валидности Ethereum адреса."""
        if not address or len(address) != 42:
            return False
        if not address.startswith('0x'):
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False
    
    async def _initialize_wallet_cache(self, address: str) -> None:
        """Инициализация кеша транзакций для нового кошелька."""
        try:
            # Получаем последние 5 транзакций для инициализации кеша
            transactions = await self._get_wallet_transactions(address, limit=5)
            tx_hashes = {tx.get('hash', '') for tx in transactions if tx.get('hash')}
            self._last_tx_hashes[address] = tx_hashes
        except Exception as e:
            logger.error(f"Error initializing cache for {address}: {e}")
    
    async def remove_wallet_alert(self, user_id: int, wallet_address: str) -> bool:
        """Удаление алерта кошелька."""
        try:
            if user_id in self._alerts:
                self._alerts[user_id] = [
                    a for a in self._alerts[user_id] 
                    if a.wallet_address.lower() != wallet_address.lower()
                ]
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing wallet alert: {e}")
            return False
    
    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение алертов пользователя."""
        alerts = self._alerts.get(user_id, [])
        return [
            {
                "id": alert.id,
                "wallet_address": alert.wallet_address,
                "min_value_eth": (alert.min_value_eth or 0) / 10**18,
                "track_incoming": alert.track_incoming,
                "track_outgoing": alert.track_outgoing,
                "is_active": alert.is_active
            }
            for alert in alerts
        ]
    
    async def get_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Получение информации о кошельке."""
        try:
            # Получаем баланс
            async with self._session.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "account",
                    "action": "balance",
                    "address": address,
                    "tag": "latest",
                    "apikey": "YourApiKeyToken"
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "1":
                        balance_wei = int(data.get("result", "0"))
                        balance_eth = balance_wei / 10**18
                        balance_usd = balance_eth * self._eth_price_usd
                        
                        # Получаем последние транзакции
                        recent_txs = await self._get_wallet_transactions(address, limit=5)
                        
                        return {
                            "address": address,
                            "balance_eth": balance_eth,
                            "balance_usd": balance_usd,
                            "recent_transactions_count": len(recent_txs),
                            "last_activity": recent_txs[0].get("timeStamp") if recent_txs else None
                        }
        except Exception as e:
            logger.error(f"Error getting wallet info for {address}: {e}")
        
        return None
    
    def get_limitations_info(self) -> Dict[str, Any]:
        """Информация об ограничениях сервиса."""
        return {
            "title": "Критические ограничения Wallet Tracker",
            "critical_limitations": [
                "❌ НЕ работает в реальном времени",
                "❌ Задержка обнаружения: 2-10 минут",
                "❌ Только ETH транзакции (не ERC-20)",
                "❌ Лимит: 5 кошельков на пользователя",
                "❌ API лимит: 5 запросов/сек"
            ],
            "for_real_time_tracking": [
                "💰 Ethereum нода ($500+/месяц)",
                "💰 Alchemy/Infura Pro ($99+/месяц)",
                "💰 Moralis API ($49+/месяц)",
                "💰 QuickNode ($9-299/месяц)"
            ],
            "what_works": [
                "✅ Проверка кошелька по запросу",
                "✅ Уведомления с задержкой",
                "✅ Фильтрация по сумме",
                "✅ Отслеживание входящих/исходящих"
            ]
        }

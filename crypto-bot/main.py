# main.py
"""Исправленное главное приложение с корректными импортами."""

import asyncio
import signal
import sys
import warnings
from typing import Dict, Any, List
import logging

# Подавляем предупреждения о deprecation
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

from config.settings import get_config
from shared.events.bus import EventBus, Event
from shared.cache.memory_cache import cache_manager
from shared.database.manager import DatabaseManager

# Импорт сервисов
from modules.telegram.service import TelegramService
from modules.price_alerts.service import PriceAlertsService
from modules.gas_tracker.service import GasTrackerService
from modules.whales.service import LimitedWhaleService
from modules.wallet_tracker.service import LimitedWalletTrackerService

logger = logging.getLogger(__name__)


class ModularCryptoBot:
    """Главное приложение с исправленными импортами и полной функциональностью."""
    
    def __init__(self):
        self.config = get_config()
        self.running = False
        
        # Event Bus (создаем новый экземпляр)
        self.event_bus = EventBus()
        
        # Сервисы
        self.db_manager: DatabaseManager = None
        self.telegram_service: TelegramService = None
        self.price_alerts_service: PriceAlertsService = None
        self.gas_tracker_service: GasTrackerService = None
        self.whale_service: LimitedWhaleService = None
        self.wallet_service: LimitedWalletTrackerService = None
        
        # Задачи
        self.tasks: List[asyncio.Task] = []
        
        # Настройка обработчиков сигналов
        self._setup_signal_handlers()
        
        # Счетчик ошибок модулей
        self._module_errors = {}
        self._max_module_errors = 5
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов для graceful shutdown."""
        if sys.platform != 'win32':
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов."""
        logger.info(f"Received signal {signum}")
        if self.running:
            asyncio.create_task(self.stop())
    
    async def initialize(self) -> None:
        """Инициализация всех модулей с error handling."""
        logger.info("🚀 Initializing Modular Crypto Bot v2.0...")
        
        try:
            # Инициализируем Event Bus
            await self._initialize_event_bus()
            
            # Инициализируем кеширование
            await self._initialize_caching()
            
            # Инициализируем базу данных (опционально)
            await self._initialize_database()
            
            # Инициализируем модули
            await self._initialize_modules()
            
            # Настраиваем межмодульные связи
            await self._setup_module_connections()
            
            logger.info("✅ All modules initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize application: {e}")
            raise
    
    async def _initialize_event_bus(self) -> None:
        """Инициализация Event Bus."""
        logger.info("📡 Initializing Event Bus...")
        
        try:
            await self.event_bus.start()
            
            # Настраиваем middleware для мониторинга
            self.event_bus.add_middleware(self._event_monitor_middleware)
            
            logger.info("✅ Event Bus initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Event Bus: {e}")
            raise
    
    async def _initialize_caching(self) -> None:
        """Инициализация системы кеширования."""
        logger.info("💾 Initializing cache system...")
        
        try:
            await cache_manager.start_all()
            
            cache_stats = cache_manager.get_all_stats()
            logger.info(f"✅ Cache system initialized with {len(cache_stats)} caches")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize cache system: {e}")
            raise
    
    async def _initialize_database(self) -> None:
        """Инициализация базы данных (опционально)."""
        logger.info("📊 Initializing database...")
        
        try:
            self.db_manager = DatabaseManager(self.config.get_database_url())
            await self.db_manager.initialize()
            
            # Проверяем подключение
            health = await self.db_manager.health_check()
            if not health:
                logger.warning("⚠️ Database health check failed, using cache-only mode")
                self.db_manager = None
            else:
                logger.info("✅ Database initialized successfully")
            
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed: {e}, using cache-only mode")
            self.db_manager = None
    
    async def _initialize_modules(self) -> None:
        """Инициализация всех модулей."""
        logger.info("🔧 Initializing modules...")
        
        # Инициализируем модули с error handling
        modules_config = [
            ("Price Alerts", self._init_price_alerts),
            ("Gas Tracker", self._init_gas_tracker),
            ("Whale Tracker", self._init_whale_tracker),
            ("Wallet Tracker", self._init_wallet_tracker),
            ("Telegram Service", self._init_telegram_service),
        ]
        
        for module_name, init_func in modules_config:
            try:
                await init_func()
                logger.info(f"✅ {module_name} initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize {module_name}: {e}")
                # Продолжаем работу даже если модуль не инициализирован
        
        logger.info("✅ All modules initialization completed")
    
    async def _init_price_alerts(self):
        """Инициализация Price Alerts."""
        self.price_alerts_service = PriceAlertsService()
    
    async def _init_gas_tracker(self):
        """Инициализация Gas Tracker."""
        self.gas_tracker_service = GasTrackerService()
    
    async def _init_whale_tracker(self):
        """Инициализация Whale Tracker."""
        self.whale_service = LimitedWhaleService()
    
    async def _init_wallet_tracker(self):
        """Инициализация Wallet Tracker."""
        self.wallet_service = LimitedWalletTrackerService()
    
    async def _init_telegram_service(self):
        """Инициализация Telegram Service."""
        self.telegram_service = TelegramService(self.config.bot_token)
    
    async def _setup_module_connections(self) -> None:
        """Настройка связей между модулями через события."""
        logger.info("🔗 Setting up module connections...")
        
        # Подписываемся на системные события
        self.event_bus.subscribe("system.module_started", self._on_module_started)
        self.event_bus.subscribe("system.module_stopped", self._on_module_stopped)
        self.event_bus.subscribe("system.error", self._on_system_error)
        
        # Подписываемся на алерты для Telegram
        self.event_bus.subscribe("price_alert.triggered", self._forward_to_telegram)
        self.event_bus.subscribe("gas_alert_triggered", self._forward_to_telegram)
        self.event_bus.subscribe("whale_alert_triggered", self._forward_to_telegram)
        self.event_bus.subscribe("wallet_alert_triggered", self._forward_to_telegram)
        
        logger.info("✅ Module connections established")
    
    async def _event_monitor_middleware(self, event: Event) -> None:
        """Middleware для мониторинга событий."""
        logger.debug(f"Event: {event.type} from {event.source_module}")
        
        # Обновляем статистику событий
        try:
            cache = cache_manager.get_cache('system_stats')
            stats_key = f"events:{event.type}"
            current_count = await cache.get(stats_key, 0)
            await cache.set(stats_key, current_count + 1, ttl=3600)
        except Exception:
            pass  # Не критично если не удалось обновить статистику
    
    async def _on_module_started(self, event: Event) -> None:
        """Обработка события запуска модуля."""
        module_name = event.data.get("module", "unknown")
        logger.info(f"✅ Module '{module_name}' started")
        
        # Сбрасываем счетчик ошибок
        if module_name in self._module_errors:
            del self._module_errors[module_name]
    
    async def _on_module_stopped(self, event: Event) -> None:
        """Обработка события остановки модуля."""
        module_name = event.data.get("module", "unknown")
        logger.info(f"⏹️ Module '{module_name}' stopped")
    
    async def _on_system_error(self, event: Event) -> None:
        """Обработка системных ошибок."""
        error = event.data.get("error", "unknown")
        module_name = event.source_module
        
        logger.error(f"❌ Error in module '{module_name}': {error}")
        
        # Увеличиваем счетчик ошибок
        if module_name not in self._module_errors:
            self._module_errors[module_name] = 0
        
        self._module_errors[module_name] += 1
        
        # Если слишком много ошибок, пытаемся перезапустить модуль
        if self._module_errors[module_name] >= self._max_module_errors:
            logger.warning(f"⚠️ Module '{module_name}' has too many errors, attempting restart...")
            await self._restart_module(module_name)
    
    async def _forward_to_telegram(self, event: Event) -> None:
        """Пересылка алертов в Telegram."""
        if self.telegram_service:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                try:
                    await self.telegram_service.send_message(user_id, message, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Error forwarding message to Telegram: {e}")
    
    async def _restart_module(self, module_name: str):
        """Перезапуск проблемного модуля."""
        try:
            if module_name == "price_alerts" and self.price_alerts_service:
                await self.price_alerts_service.stop()
                await asyncio.sleep(5)
                await self.price_alerts_service.start()
                
            elif module_name == "gas_tracker" and self.gas_tracker_service:
                await self.gas_tracker_service.stop()
                await asyncio.sleep(5)
                await self.gas_tracker_service.start()
                
            elif module_name == "whale_tracker" and self.whale_service:
                await self.whale_service.stop()
                await asyncio.sleep(5)
                await self.whale_service.start()
                
            elif module_name == "wallet_tracker" and self.wallet_service:
                await self.wallet_service.stop()
                await asyncio.sleep(5)
                await self.wallet_service.start()
            
            # Сбрасываем счетчик ошибок
            self._module_errors[module_name] = 0
            logger.info(f"✅ Module '{module_name}' restarted successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to restart module '{module_name}': {e}")
    
    async def start(self) -> None:
        """Запуск всех модулей с отказоустойчивостью."""
        if self.running:
            return
        
        logger.info("🎯 Starting all modules...")
        self.running = True
        
        try:
            # Запускаем модули в правильном порядке с error handling
            await self._start_core_modules()
            await self._start_feature_modules()
            await self._start_telegram_service()
            
            # Создаем задачи мониторинга
            self.tasks = [
                asyncio.create_task(self._system_monitor()),
                asyncio.create_task(self._health_checker())
            ]
            
            logger.info("🚀 All modules started successfully!")
            
            # Публикуем событие запуска приложения
            await self.event_bus.publish(Event(
                type="system.application_started",
                data={"modules_count": 5, "version": "2.0.0"},
                source_module="main"
            ))
            
            # Ждем завершения
            await self._wait_for_shutdown()
            
        except Exception as e:
            logger.error(f"❌ Error starting application: {e}")
            raise
    
    async def _start_core_modules(self) -> None:
        """Запуск основных модулей."""
        logger.info("🔧 Starting core modules...")
        
        # Price Alerts (основной функционал)
        if self.price_alerts_service:
            try:
                await self.price_alerts_service.start()
                logger.info("✅ Price Alerts started")
            except Exception as e:
                logger.error(f"❌ Failed to start Price Alerts: {e}")
        
        logger.info("✅ Core modules started")
    
    async def _start_feature_modules(self) -> None:
        """Запуск дополнительных модулей."""
        logger.info("⭐ Starting feature modules...")
        
        # Gas Tracker
        if self.gas_tracker_service:
            try:
                await self.gas_tracker_service.start()
                logger.info("✅ Gas Tracker started")
            except Exception as e:
                logger.error(f"❌ Failed to start Gas Tracker: {e}")
        
        # Whale Tracker (с предупреждением об ограничениях)
        if self.whale_service:
            try:
                await self.whale_service.start()
                logger.info("✅ Whale Tracker started (limited mode)")
            except Exception as e:
                logger.error(f"❌ Failed to start Whale Tracker: {e}")
        
        # Wallet Tracker (с предупреждением об ограничениях)
        if self.wallet_service:
            try:
                await self.wallet_service.start()
                logger.info("✅ Wallet Tracker started (limited mode)")
            except Exception as e:
                logger.error(f"❌ Failed to start Wallet Tracker: {e}")
        
        logger.info("✅ Feature modules started")
    
    async def _start_telegram_service(self) -> None:
        """Запуск Telegram сервиса последним."""
        logger.info("📱 Starting Telegram service...")
        
        if self.telegram_service:
            try:
                # Инжектируем сервисы в handlers
                self.telegram_service.set_services(
                    price_alerts=self.price_alerts_service,
                    gas_tracker=self.gas_tracker_service,
                    whale_tracker=self.whale_service,
                    wallet_tracker=self.wallet_service
                )
                
                # Создаем задачу для Telegram (она будет работать бесконечно)
                telegram_task = asyncio.create_task(self.telegram_service.start())
                self.tasks.append(telegram_task)
                
                # Небольшая пауза для инициализации
                await asyncio.sleep(3)
                
                logger.info("✅ Telegram service started")
                
            except Exception as e:
                logger.error(f"❌ Failed to start Telegram service: {e}")
                # Не останавливаем приложение если Telegram не запустился
    
    async def _wait_for_shutdown(self) -> None:
        """Ожидание сигнала завершения."""
        try:
            # Ждем завершения всех задач или сигнала остановки
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("🛑 Shutdown signal received")
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}")
    
    async def stop(self) -> None:
        """Остановка всех модулей."""
        if not self.running:
            return
        
        logger.info("🛑 Stopping application...")
        self.running = False
        
        try:
            # Останавливаем задачи мониторинга
            for task in self.tasks:
                task.cancel()
            
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            
            # Останавливаем модули в обратном порядке
            await self._stop_telegram_service()
            await self._stop_feature_modules()
            await self._stop_core_modules()
            await self._stop_infrastructure()
            
            # Публикуем событие остановки
            await self.event_bus.publish(Event(
                type="system.application_stopped",
                data={"clean_shutdown": True},
                source_module="main"
            ))
            
            logger.info("✅ Application stopped cleanly")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
    
    async def _stop_telegram_service(self) -> None:
        """Остановка Telegram сервиса."""
        if self.telegram_service:
            try:
                await self.telegram_service.stop()
                logger.info("📱 Telegram service stopped")
            except Exception as e:
                logger.error(f"Error stopping Telegram service: {e}")
    
    async def _stop_feature_modules(self) -> None:
        """Остановка дополнительных модулей."""
        logger.info("⭐ Stopping feature modules...")
        
        modules = [
            ("Wallet Tracker", self.wallet_service),
            ("Whale Tracker", self.whale_service),
            ("Gas Tracker", self.gas_tracker_service)
        ]
        
        for module_name, service in modules:
            if service:
                try:
                    await service.stop()
                    logger.info(f"✅ {module_name} stopped")
                except Exception as e:
                    logger.error(f"Error stopping {module_name}: {e}")
    
    async def _stop_core_modules(self) -> None:
        """Остановка основных модулей."""
        logger.info("🔧 Stopping core modules...")
        
        if self.price_alerts_service:
            try:
                await self.price_alerts_service.stop()
                logger.info("✅ Price Alerts stopped")
            except Exception as e:
                logger.error(f"Error stopping Price Alerts: {e}")
    
    async def _stop_infrastructure(self) -> None:
        """Остановка инфраструктуры."""
        logger.info("🏗️ Stopping infrastructure...")
        
        # Останавливаем кеширование
        try:
            await cache_manager.stop_all()
            logger.info("💾 Cache system stopped")
        except Exception as e:
            logger.error(f"Error stopping cache system: {e}")
        
        # Останавливаем Event Bus
        try:
            await self.event_bus.stop()
            logger.info("📡 Event Bus stopped")
        except Exception as e:
            logger.error(f"Error stopping Event Bus: {e}")
        
        # Останавливаем базу данных
        if self.db_manager:
            try:
                await self.db_manager.close()
                logger.info("📊 Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")
    
    async def _system_monitor(self) -> None:
        """Мониторинг состояния системы."""
        while self.running:
            try:
                # Получаем статистику событий
                event_stats = self.event_bus.get_stats()
                cache_stats = cache_manager.get_all_stats()
                
                # Логируем состояние каждые 10 минут
                logger.info(
                    f"📊 System stats - Events: {event_stats.get('event_types', 0)} types, "
                    f"Handlers: {event_stats.get('total_handlers', 0)}, "
                    f"Cache entries: {sum(s.get('total_entries', 0) for s in cache_stats.values())}"
                )
                
                await asyncio.sleep(600)  # 10 минут
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitor: {e}")
                await asyncio.sleep(60)
    
    async def _health_checker(self) -> None:
        """Проверка здоровья модулей."""
        while self.running:
            try:
                # Проверяем состояние Event Bus
                event_health = await self.event_bus.health_check()
                if event_health.get('status') != 'healthy':
                    logger.warning(f"⚠️ Event Bus unhealthy: {event_health}")
                
                # Проверяем состояние базы данных
                if self.db_manager:
                    db_healthy = await self.db_manager.health_check()
                    if not db_healthy:
                        logger.warning("⚠️ Database health check failed")
                
                # Проверяем память кешей
                cache_stats = cache_manager.get_all_stats()
                for cache_name, stats in cache_stats.items():
                    memory_usage = stats.get('memory_usage_percent', 0)
                    if memory_usage > 90:
                        logger.warning(f"⚠️ Cache '{cache_name}' memory usage high: {memory_usage}%")
                
                # Публикуем событие проверки здоровья
                await self.event_bus.publish(Event(
                    type="system.health_check",
                    data={
                        "timestamp": asyncio.get_event_loop().time(),
                        "modules_running": self.running,
                        "event_bus_health": event_health.get('status'),
                        "db_healthy": await self.db_manager.health_check() if self.db_manager else None
                    },
                    source_module="main"
                ))
                
                await asyncio.sleep(120)  # 2 минуты
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health checker: {e}")
                await asyncio.sleep(120)
    
    def get_status(self) -> Dict[str, Any]:
        """Получение статуса приложения."""
        return {
            "running": self.running,
            "modules": {
                "price_alerts": self.price_alerts_service is not None and getattr(self.price_alerts_service, 'running', False),
                "gas_tracker": self.gas_tracker_service is not None and getattr(self.gas_tracker_service, 'running', False),
                "whale_tracker": self.whale_service is not None and getattr(self.whale_service, 'running', False),
                "wallet_tracker": self.wallet_service is not None and getattr(self.wallet_service, 'running', False),
                "telegram": self.telegram_service is not None
            },
            "infrastructure": {
                "event_bus": self.event_bus._running if self.event_bus else False,
                "database": self.db_manager is not None,
                "cache_manager": len(cache_manager._caches) > 0
            },
            "errors": dict(self._module_errors),
            "tasks": len(self.tasks)
        }


async def main():
    """Главная функция приложения."""
    app = ModularCryptoBot()
    
    try:
        await app.initialize()
        await app.start()
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        return 1
    finally:
        await app.stop()
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Unhandled exception: {e}")
        sys.exit(1)
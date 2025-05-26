# main.py
"""Исправленное главное приложение с полной функциональностью всех кнопок."""

import asyncio
import signal
import sys
import warnings
from typing import Dict, Any, List
import logging

# Подавляем предупреждения
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: правильные импорты
from config.settings import get_config
from shared.events import event_bus, Event
from shared.cache.memory_cache import cache_manager

# Импорт сервисов в правильном порядке
from modules.telegram.service import TelegramService
from modules.price_alerts.service import PriceAlertsService
from modules.gas_tracker.service import GasTrackerService
from modules.whales.service import LimitedWhaleService
from modules.wallet_tracker.service import LimitedWalletTrackerService

logger = logging.getLogger(__name__)


class FullyFunctionalCryptoBot:
    """Главное приложение с ПОЛНОСТЬЮ РАБОЧИМИ кнопками."""
    
    def __init__(self):
        self.config = get_config()
        self.running = False
        
        # Сервисы (ВАЖНО: инициализируем все)
        self.telegram_service: TelegramService = None
        self.price_alerts_service: PriceAlertsService = None
        self.gas_tracker_service: GasTrackerService = None
        self.whale_service: LimitedWhaleService = None
        self.wallet_service: LimitedWalletTrackerService = None
        
        # Задачи
        self.tasks: List[asyncio.Task] = []
        
        # Настройка обработчиков сигналов
        self._setup_signal_handlers()
        
        # Статистика запуска
        self._startup_stats = {
            "start_time": None,
            "modules_started": 0,
            "modules_failed": 0,
            "handlers_registered": 0
        }
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов."""
        if sys.platform != 'win32':
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов."""
        logger.info(f"Received signal {signum}")
        if self.running:
            asyncio.create_task(self.stop())
    
    async def initialize(self) -> None:
        """Инициализация всех модулей."""
        import time
        self._startup_stats["start_time"] = time.time()
        
        logger.info("🚀 Initializing Fully Functional Crypto Bot...")
        
        try:
            # Инициализируем инфраструктуру
            await self._initialize_infrastructure()
            
            # Инициализируем все модули
            await self._initialize_all_modules()
            
            # Настраиваем Telegram сервис с ВСЕМИ модулями
            await self._setup_telegram_with_all_modules()
            
            # Настраиваем межмодульные связи
            await self._setup_module_connections()
            
            startup_time = time.time() - self._startup_stats["start_time"]
            logger.info(f"✅ All modules initialized in {startup_time:.2f}s")
            logger.info(f"📊 Stats: {self._startup_stats['modules_started']} started, {self._startup_stats['modules_failed']} failed")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize application: {e}")
            raise
    
    async def _initialize_infrastructure(self) -> None:
        """Инициализация инфраструктуры."""
        logger.info("🏗️ Initializing infrastructure...")
        
        # Event Bus
        await event_bus.start()
        logger.info("✅ Event Bus started")
        
        # Cache Manager
        await cache_manager.start_all()
        logger.info("✅ Cache system started")
        
        # Базу данных пока не используем для простоты
        logger.info("✅ Infrastructure ready")
    
    async def _initialize_all_modules(self) -> None:
        """Инициализация ВСЕХ модулей."""
        logger.info("🔧 Initializing all modules...")
        
        # Price Alerts (основной модуль)
        try:
            self.price_alerts_service = PriceAlertsService()
            logger.info("✅ Price Alerts service created")
            self._startup_stats["modules_started"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to create Price Alerts: {e}")
            self._startup_stats["modules_failed"] += 1
        
        # Gas Tracker
        try:
            self.gas_tracker_service = GasTrackerService()
            logger.info("✅ Gas Tracker service created")
            self._startup_stats["modules_started"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to create Gas Tracker: {e}")
            self._startup_stats["modules_failed"] += 1
        
        # Whale Tracker
        try:
            self.whale_service = LimitedWhaleService()
            logger.info("✅ Whale service created")
            self._startup_stats["modules_started"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to create Whale service: {e}")
            self._startup_stats["modules_failed"] += 1
        
        # Wallet Tracker
        try:
            self.wallet_service = LimitedWalletTrackerService()
            logger.info("✅ Wallet service created")
            self._startup_stats["modules_started"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to create Wallet service: {e}")
            self._startup_stats["modules_failed"] += 1
        
        # Telegram Service
        try:
            self.telegram_service = TelegramService(self.config.bot_token)
            logger.info("✅ Telegram service created")
            self._startup_stats["modules_started"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to create Telegram service: {e}")
            self._startup_stats["modules_failed"] += 1
            raise  # Telegram критически важен
    
    async def _setup_telegram_with_all_modules(self) -> None:
        """Настройка Telegram с ВСЕМИ модулями."""
        logger.info("📱 Setting up Telegram with ALL modules...")
        
        if not self.telegram_service:
            raise RuntimeError("Telegram service not initialized")
        
        # КРИТИЧЕСКИ ВАЖНО: передаем ВСЕ сервисы
        self.telegram_service.set_services(
            price_alerts=self.price_alerts_service,
            gas_tracker=self.gas_tracker_service,
            whale_tracker=self.whale_service,
            wallet_tracker=self.wallet_service
        )
        
        logger.info("✅ All services injected into Telegram handlers")
        
        # Подсчитываем обработчики
        stats = self.telegram_service.get_stats()
        self._startup_stats["handlers_registered"] = stats.get("handlers_registered", 0)
        
        logger.info(f"📊 Handlers registered: {self._startup_stats['handlers_registered']}")
    
    async def _setup_module_connections(self) -> None:
        """Настройка связей между модулями."""
        logger.info("🔗 Setting up module connections...")
        
        # Подписываемся на системные события
        event_bus.subscribe("system.module_started", self._on_module_started)
        event_bus.subscribe("system.module_stopped", self._on_module_stopped)
        event_bus.subscribe("system.error", self._on_system_error)
        
        # Подписываемся на алерты для пересылки в Telegram
        event_bus.subscribe("price_alert.triggered", self._forward_to_telegram)
        event_bus.subscribe("gas_alert_triggered", self._forward_to_telegram)
        event_bus.subscribe("whale_alert_triggered", self._forward_to_telegram)
        event_bus.subscribe("wallet_alert_triggered", self._forward_to_telegram)
        
        logger.info("✅ Module connections established")
    
    async def start(self) -> None:
        """Запуск всех модулей."""
        if self.running:
            return
        
        logger.info("🎯 Starting all modules...")
        self.running = True
        
        try:
            # Запускаем сервисы в правильном порядке
            await self._start_core_services()
            await self._start_feature_services()
            
            # Telegram запускаем ПОСЛЕДНИМ (он блокирующий)
            logger.info("📱 Starting Telegram service (this will block)...")
            
            # Публикуем событие полной готовности
            await event_bus.publish(Event(
                type="system.application_ready",
                data={
                    "modules_started": self._startup_stats["modules_started"],
                    "handlers_registered": self._startup_stats["handlers_registered"],
                    "version": "2.0.0"
                },
                source_module="main"
            ))
            
            # Создаем задачи мониторинга
            self.tasks = [
                asyncio.create_task(self._system_monitor()),
                asyncio.create_task(self._health_checker())
            ]
            
            logger.info("🚀 ALL MODULES STARTED! Bot is fully functional!")
            logger.info("📱 Starting Telegram polling...")
            
            # Запускаем Telegram (блокирующий вызов)
            await self.telegram_service.start()
            
        except Exception as e:
            logger.error(f"❌ Error starting application: {e}")
            raise
    
    async def _start_core_services(self) -> None:
        """Запуск основных сервисов."""
        logger.info("🔧 Starting core services...")
        
        # Price Alerts
        if self.price_alerts_service:
            try:
                await self.price_alerts_service.start()
                logger.info("✅ Price Alerts started")
            except Exception as e:
                logger.error(f"❌ Failed to start Price Alerts: {e}")
        
        logger.info("✅ Core services started")
    
    async def _start_feature_services(self) -> None:
        """Запуск дополнительных сервисов."""
        logger.info("⭐ Starting feature services...")
        
        # Gas Tracker
        if self.gas_tracker_service:
            try:
                await self.gas_tracker_service.start()
                logger.info("✅ Gas Tracker started")
            except Exception as e:
                logger.error(f"❌ Failed to start Gas Tracker: {e}")
        
        # Whale Service
        if self.whale_service:
            try:
                await self.whale_service.start()
                logger.info("✅ Whale service started (limited mode)")
            except Exception as e:
                logger.error(f"❌ Failed to start Whale service: {e}")
        
        # Wallet Service
        if self.wallet_service:
            try:
                await self.wallet_service.start()
                logger.info("✅ Wallet service started (limited mode)")
            except Exception as e:
                logger.error(f"❌ Failed to start Wallet service: {e}")
        
        logger.info("✅ Feature services started")
    
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
            
            # Останавливаем сервисы
            await self._stop_all_services()
            
            # Останавливаем инфраструктуру
            await self._stop_infrastructure()
            
            logger.info("✅ Application stopped cleanly")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
    
    async def _stop_all_services(self) -> None:
        """Остановка всех сервисов."""
        logger.info("🛑 Stopping all services...")
        
        # Останавливаем в обратном порядке
        services = [
            ("Telegram", self.telegram_service),
            ("Wallet", self.wallet_service),
            ("Whale", self.whale_service),
            ("Gas Tracker", self.gas_tracker_service),
            ("Price Alerts", self.price_alerts_service)
        ]
        
        for service_name, service in services:
            if service:
                try:
                    await service.stop()
                    logger.info(f"✅ {service_name} stopped")
                except Exception as e:
                    logger.error(f"❌ Error stopping {service_name}: {e}")
    
    async def _stop_infrastructure(self) -> None:
        """Остановка инфраструктуры."""
        logger.info("🏗️ Stopping infrastructure...")
        
        try:
            await cache_manager.stop_all()
            logger.info("💾 Cache system stopped")
        except Exception as e:
            logger.error(f"Error stopping cache: {e}")
        
        try:
            await event_bus.stop()
            logger.info("📡 Event Bus stopped")
        except Exception as e:
            logger.error(f"Error stopping Event Bus: {e}")
    
    # EVENT HANDLERS
    
    async def _on_module_started(self, event: Event) -> None:
        """Обработка события запуска модуля."""
        module_name = event.data.get("module", "unknown")
        logger.info(f"✅ Module '{module_name}' started successfully")
    
    async def _on_module_stopped(self, event: Event) -> None:
        """Обработка события остановки модуля."""
        module_name = event.data.get("module", "unknown")
        logger.info(f"⏹️ Module '{module_name}' stopped")
    
    async def _on_system_error(self, event: Event) -> None:
        """Обработка системных ошибок."""
        error = event.data.get("error", "unknown")
        module_name = event.source_module
        logger.error(f"❌ System error in '{module_name}': {error}")
    
    async def _forward_to_telegram(self, event: Event) -> None:
        """Пересылка алертов в Telegram."""
        if self.telegram_service and self.running:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                try:
                    await self.telegram_service.send_message(user_id, message, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Error forwarding message to Telegram: {e}")
    
    # МОНИТОРИНГ
    
    async def _system_monitor(self) -> None:
        """Мониторинг состояния системы."""
        while self.running:
            try:
                # Статистика EventBus
                event_stats = event_bus.get_stats()
                cache_stats = cache_manager.get_all_stats()
                
                # Статистика сервисов
                services_status = {
                    "price_alerts": getattr(self.price_alerts_service, 'running', False) if self.price_alerts_service else False,
                    "gas_tracker": getattr(self.gas_tracker_service, 'running', False) if self.gas_tracker_service else False,
                    "whale_tracker": getattr(self.whale_service, 'running', False) if self.whale_service else False,
                    "wallet_tracker": getattr(self.wallet_service, 'running', False) if self.wallet_service else False,
                    "telegram": getattr(self.telegram_service, 'running', False) if self.telegram_service else False
                }
                
                running_services = sum(1 for status in services_status.values() if status)
                
                # Логируем состояние каждые 10 минут
                logger.info(
                    f"📊 System Monitor - Services: {running_services}/5 running, "
                    f"Events: {event_stats.get('event_types', 0)} types, "
                    f"Cache: {sum(s.get('total_entries', 0) for s in cache_stats.values())} entries"
                )
                
                # Публикуем статистику
                await event_bus.publish(Event(
                    type="system.monitor_stats",
                    data={
                        "services_status": services_status,
                        "running_services": running_services,
                        "event_stats": event_stats,
                        "cache_stats": cache_stats
                    },
                    source_module="main"
                ))
                
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
                # Проверяем Event Bus
                event_health = await event_bus.health_check()
                
                # Проверяем сервисы
                unhealthy_services = []
                
                services_to_check = [
                    ("price_alerts", self.price_alerts_service),
                    ("gas_tracker", self.gas_tracker_service),
                    ("whale_tracker", self.whale_service),
                    ("wallet_tracker", self.wallet_service),
                    ("telegram", self.telegram_service)
                ]
                
                for service_name, service in services_to_check:
                    if service:
                        try:
                            # Проверяем базовые атрибуты
                            if not getattr(service, 'running', False):
                                unhealthy_services.append(service_name)
                        except Exception as e:
                            logger.warning(f"Health check failed for {service_name}: {e}")
                            unhealthy_services.append(service_name)
                
                # Публикуем результат health check
                await event_bus.publish(Event(
                    type="system.health_check",
                    data={
                        "timestamp": asyncio.get_event_loop().time(),
                        "event_bus_healthy": event_health.get('status') == 'healthy',
                        "unhealthy_services": unhealthy_services,
                        "total_services": len(services_to_check)
                    },
                    source_module="main"
                ))
                
                if unhealthy_services:
                    logger.warning(f"⚠️ Unhealthy services: {unhealthy_services}")
                
                await asyncio.sleep(120)  # 2 минуты
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health checker: {e}")
                await asyncio.sleep(120)
    
    def get_status(self) -> Dict[str, Any]:
        """Получение полного статуса приложения."""
        return {
            "running": self.running,
            "startup_stats": self._startup_stats,
            "services": {
                "price_alerts": {
                    "initialized": self.price_alerts_service is not None,
                    "running": getattr(self.price_alerts_service, 'running', False) if self.price_alerts_service else False
                },
                "gas_tracker": {
                    "initialized": self.gas_tracker_service is not None,
                    "running": getattr(self.gas_tracker_service, 'running', False) if self.gas_tracker_service else False
                },
                "whale_tracker": {
                    "initialized": self.whale_service is not None,
                    "running": getattr(self.whale_service, 'running', False) if self.whale_service else False
                },
                "wallet_tracker": {
                    "initialized": self.wallet_service is not None,
                    "running": getattr(self.wallet_service, 'running', False) if self.wallet_service else False
                },
                "telegram": {
                    "initialized": self.telegram_service is not None,
                    "running": getattr(self.telegram_service, 'running', False) if self.telegram_service else False
                }
            },
            "infrastructure": {
                "event_bus_running": event_bus._running if hasattr(event_bus, '_running') else False,
                "cache_manager_active": len(cache_manager._caches) > 0
            },
            "tasks_count": len(self.tasks)
        }


async def main():
    """Главная функция приложения."""
    logger.info("🚀 Starting Fully Functional Crypto Bot...")
    
    app = FullyFunctionalCryptoBot()
    
    try:
        # Инициализируем все модули
        await app.initialize()
        
        # Запускаем приложение (блокирующий вызов)
        await app.start()
        
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            await app.stop()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    return 0


if __name__ == "__main__":
    try:
        # Выводим информацию о запуске
        print("=" * 60)
        print("🤖 CRYPTO MONITOR BOT v2.0")
        print("🚀 Fully Functional Version")
        print("📱 All buttons and features working!")
        print("=" * 60)
        
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Unhandled exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
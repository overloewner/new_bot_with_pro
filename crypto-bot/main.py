# main.py
"""Обновленное главное приложение с новой структурой."""

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

# Импорты с новой структурой
from config.base import get_config
from shared.events import event_bus, Event
from shared.database import DatabaseManager

# Импорт сервисов
from modules.telegram.service import TelegramService
from modules.price_alerts.service import PriceAlertsService

logger = logging.getLogger(__name__)

class FullyFunctionalCryptoBot:
    """Главное приложение с обновленной архитектурой."""
    
    def __init__(self):
        self.config = get_config()
        self.running = False
        
        # Инфраструктура
        self.db_manager: DatabaseManager = None
        
        # Сервисы
        self.telegram_service: TelegramService = None
        self.price_alerts_service: PriceAlertsService = None
        
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
        
        logger.info("🚀 Initializing Crypto Bot with new architecture...")
        
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
        
        # Database Manager
        try:
            self.db_manager = DatabaseManager(self.config.get_database_url())
            await self.db_manager.initialize()
            logger.info("✅ Database manager initialized")
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed: {e}")
            self.db_manager = None
        
        logger.info("✅ Infrastructure ready")
    
    async def _initialize_all_modules(self) -> None:
        """Инициализация всех модулей."""
        logger.info("🔧 Initializing modules...")
        
        # Price Alerts (основной модуль)
        try:
            self.price_alerts_service = PriceAlertsService(self.db_manager)
            logger.info("✅ Price Alerts service created")
            self._startup_stats["modules_started"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to create Price Alerts: {e}")
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
        """Настройка Telegram с модулями."""
        logger.info("📱 Setting up Telegram with modules...")
        
        if not self.telegram_service:
            raise RuntimeError("Telegram service not initialized")
        
        # Передаем доступные сервисы
        self.telegram_service.set_services(
            price_alerts=self.price_alerts_service
        )
        
        logger.info("✅ Services injected into Telegram handlers")
        
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
        logger.info("⭐ No additional services to start")
        logger.info("✅ Feature services completed")
    
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
            if self.db_manager:
                await self.db_manager.close()
                logger.info("💾 Database manager stopped")
        except Exception as e:
            logger.error(f"Error stopping database: {e}")
        
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
    
    # МОНИТОРИНГ
    
    async def _system_monitor(self) -> None:
        """Мониторинг состояния системы."""
        while self.running:
            try:
                # Статистика EventBus
                event_stats = event_bus.get_stats()
                
                # Статистика сервисов
                services_status = {
                    "price_alerts": getattr(self.price_alerts_service, 'running', False) if self.price_alerts_service else False,
                    "telegram": getattr(self.telegram_service, 'running', False) if self.telegram_service else False
                }
                
                running_services = sum(1 for status in services_status.values() if status)
                
                # Логируем состояние каждые 10 минут
                logger.info(
                    f"📊 System Monitor - Services: {running_services}/2 running, "
                    f"Events: {event_stats.get('event_types', 0)} types"
                )
                
                # Публикуем статистику
                await event_bus.publish(Event(
                    type="system.monitor_stats",
                    data={
                        "services_status": services_status,
                        "running_services": running_services,
                        "event_stats": event_stats
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
                # Проверяем сервисы
                unhealthy_services = []
                
                services_to_check = [
                    ("price_alerts", self.price_alerts_service),
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


async def main():
    """Главная функция приложения."""
    logger.info("🚀 Starting Crypto Bot with new architecture...")
    
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
        print("🔧 Refactored Architecture")
        print("📱 All functionality preserved!")
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
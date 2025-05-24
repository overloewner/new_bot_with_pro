# main.py
"""Главное приложение с модульной архитектурой."""

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

from config.settings import AppConfig
from shared.events import event_bus, Event
from shared.database.manager import DatabaseManager

# Импорт модулей
from modules.telegram.service import TelegramService
from modules.price_alerts.service import PriceAlertsService
from modules.gas_tracker.service import GasTrackerService
from modules.whales.service import LimitedWhaleService
from modules.wallet_tracker.service import LimitedWalletTrackerService

logger = logging.getLogger(__name__)


class ModularCryptoBot:
    """Главное приложение с модульной архитектурой."""
    
    def __init__(self):
        self.config = AppConfig.from_env()
        self.running = False
        
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
        """Инициализация всех модулей."""
        logger.info("🚀 Initializing Modular Crypto Bot...")
        
        try:
            # Инициализируем базу данных
            await self._initialize_database()
            
            # Инициализируем модули
            await self._initialize_modules()
            
            # Настраиваем межмодульные связи
            await self._setup_module_connections()
            
            logger.info("✅ All modules initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize application: {e}")
            raise
    
    async def _initialize_database(self) -> None:
        """Инициализация базы данных."""
        logger.info("📊 Initializing database...")
        
        self.db_manager = DatabaseManager(self.config.database_url)
        await self.db_manager.initialize()
        
        logger.info("✅ Database initialized")
    
    async def _initialize_modules(self) -> None:
        """Инициализация всех модулей."""
        logger.info("🔧 Initializing modules...")
        
        # Telegram сервис
        self.telegram_service = TelegramService(self.config.bot_token)
        
        # Price Alerts (используем существующий функционал)
        self.price_alerts_service = PriceAlertsService()
        
        # Gas Tracker
        self.gas_tracker_service = GasTrackerService()
        
        # Whale Tracker (ограниченная версия)
        self.whale_service = LimitedWhaleService()
        
        # Wallet Tracker (ограниченная версия)
        self.wallet_service = LimitedWalletTrackerService()
        
        logger.info("✅ All services created")
    
    async def _setup_module_connections(self) -> None:
        """Настройка связей между модулями через события."""
        logger.info("🔗 Setting up module connections...")
        
        # Настраиваем middleware для мониторинга событий
        event_bus.add_middleware(self._event_monitor_middleware)
        
        # Подписываемся на системные события
        event_bus.subscribe("system.module_started", self._on_module_started)
        event_bus.subscribe("system.module_stopped", self._on_module_stopped)
        event_bus.subscribe("system.error", self._on_system_error)
        
        logger.info("✅ Module connections established")
    
    async def _event_monitor_middleware(self, event: Event) -> None:
        """Middleware для мониторинга событий."""
        logger.debug(f"Event: {event.type} from {event.source_module}")
    
    async def _on_module_started(self, event: Event) -> None:
        """Обработка события запуска модуля."""
        module_name = event.data.get("module", "unknown")  # ИСПРАВЛЕНО: переименовано с module
        logger.info(f"✅ Module '{module_name}' started")
    
    async def _on_module_stopped(self, event: Event) -> None:
        """Обработка события остановки модуля."""
        module_name = event.data.get("module", "unknown")  # ИСПРАВЛЕНО: переименовано с module
        logger.info(f"⏹️ Module '{module_name}' stopped")
    
    async def _on_system_error(self, event: Event) -> None:
        """Обработка системных ошибок."""
        error = event.data.get("error", "unknown")
        module_name = event.source_module
        logger.error(f"❌ Error in module '{module_name}': {error}")
    
    async def start(self) -> None:
        """Запуск всех модулей."""
        if self.running:
            return
        
        logger.info("🎯 Starting all modules...")
        self.running = True
        
        try:
            # Запускаем модули в правильном порядке
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
            await event_bus.publish(Event(
                type="system.application_started",
                data={"modules_count": 5},
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
            await self.price_alerts_service.start()
        
        logger.info("✅ Core modules started")
    
    async def _start_feature_modules(self) -> None:
        """Запуск дополнительных модулей."""
        logger.info("⭐ Starting feature modules...")
        
        # Gas Tracker
        if self.gas_tracker_service:
            await self.gas_tracker_service.start()
        
        # Whale Tracker (с предупреждением об ограничениях)
        if self.whale_service:
            await self.whale_service.start()
        
        # Wallet Tracker (с предупреждением об ограничениях)
        if self.wallet_service:
            await self.wallet_service.start()
        
        logger.info("✅ Feature modules started")
    
    async def _start_telegram_service(self) -> None:
        """Запуск Telegram сервиса последним."""
        logger.info("📱 Starting Telegram service...")
        
        # Создаем задачу для Telegram (она будет работать бесконечно)
        if self.telegram_service:
            telegram_task = asyncio.create_task(self.telegram_service.start())
            self.tasks.append(telegram_task)
        
        # Небольшая пауза для инициализации
        await asyncio.sleep(2)
        
        logger.info("✅ Telegram service started")
    
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
            # Останавливаем задачи
            for task in self.tasks:
                task.cancel()
            
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            
            # Останавливаем модули в обратном порядке
            await self._stop_telegram_service()
            await self._stop_feature_modules()
            await self._stop_core_modules()
            await self._stop_database()
            
            # Публикуем событие остановки
            await event_bus.publish(Event(
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
            await self.telegram_service.stop()
    
    async def _stop_feature_modules(self) -> None:
        """Остановка дополнительных модулей."""
        logger.info("⭐ Stopping feature modules...")
        
        if self.wallet_service:
            await self.wallet_service.stop()
        
        if self.whale_service:
            await self.whale_service.stop()
            
        if self.gas_tracker_service:
            await self.gas_tracker_service.stop()
        
        logger.info("✅ Feature modules stopped")
    
    async def _stop_core_modules(self) -> None:
        """Остановка основных модулей."""
        logger.info("🔧 Stopping core modules...")
        
        if self.price_alerts_service:
            await self.price_alerts_service.stop()
        
        logger.info("✅ Core modules stopped")
    
    async def _stop_database(self) -> None:
        """Остановка базы данных."""
        if self.db_manager:
            await self.db_manager.close()
            logger.info("📊 Database connection closed")
    
    async def _system_monitor(self) -> None:
        """Мониторинг состояния системы."""
        while self.running:
            try:
                # Получаем статистику событий
                event_stats = event_bus.get_stats()
                
                # Логируем состояние каждые 5 минут
                logger.info(
                    f"📊 System stats - Events: {event_stats['total_event_types']} types, "
                    f"History: {event_stats['history_size']} events"
                )
                
                await asyncio.sleep(300)  # 5 минут
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitor: {e}")
                await asyncio.sleep(60)
    
    async def _health_checker(self) -> None:
        """Проверка здоровья модулей."""
        while self.running:
            try:
                # Проверяем состояние базы данных
                if self.db_manager:
                    db_healthy = await self.db_manager.health_check()
                    if not db_healthy:
                        logger.warning("⚠️ Database health check failed")
                
                # Публикуем событие проверки здоровья
                await event_bus.publish(Event(
                    type="system.health_check",
                    data={
                        "timestamp": asyncio.get_event_loop().time(),
                        "modules_running": self.running
                    },
                    source_module="main"
                ))
                
                await asyncio.sleep(120)  # 2 минуты
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health checker: {e}")
                await asyncio.sleep(120)


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
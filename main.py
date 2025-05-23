"""Главный модуль приложения с улучшенной архитектурой."""

import asyncio
from aiogram import Bot, Dispatcher

from bot.core.config import AppConfig
from bot.core.logger import setup_logging, get_logger
from bot.core.container import container

from bot.db.database import DatabaseManager
from bot.db.repositories.user_repository import UserRepository
from bot.db.repositories.preset_repository import PresetRepository

from bot.services.user_service import UserService
from bot.services.preset_service import PresetService
from bot.services.token_service import TokenService
from bot.services.alert_service import AlertService
from bot.services.candle_service import CandleService

from bot.websocket.client import BinanceWebSocketClient
from bot.websocket.message_handler import MessageHandler

from bot.storage import Storage
from bot.handlers import setup_handlers

logger = get_logger(__name__)


class Application:
    """Основной класс приложения."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.bot: Bot = None
        self.dp: Dispatcher = None
        
        # Сервисы
        self.db_manager: DatabaseManager = None
        self.storage: Storage = None
        self.candle_service: CandleService = None
        self.websocket_client: BinanceWebSocketClient = None
        
        # Задачи
        self._tasks = []
    
    async def initialize(self) -> None:
        """Инициализация приложения."""
        logger.info("Initializing application...")
        
        # Создаем Bot и Dispatcher
        self.bot = Bot(token=self.config.bot_token)
        self.dp = Dispatcher()
        
        # Инициализируем базу данных
        self.db_manager = DatabaseManager(self.config.database.url)
        await self.db_manager.initialize()
        
        # Регистрируем сервисы в контейнере
        await self._setup_services()
        
        # Настраиваем обработчики
        setup_handlers(self.dp, self.storage)
        
        # Инициализируем WebSocket клиент
        await self._setup_websocket()
        
        logger.info("Application initialized successfully")
    
    async def _setup_services(self) -> None:
        """Настройка сервисов и их регистрация в контейнере."""
        
        # Создаем сессию для репозиториев
        session_factory = self.db_manager.async_session
        
        # Создаем сервисы
        user_repository = UserRepository(await session_factory().__anext__())
        preset_repository = PresetRepository(await session_factory().__anext__())
        
        user_service = UserService(user_repository)
        preset_service = PresetService(preset_repository)
        token_service = TokenService(self.config.token)
        
        # Создаем сервис алертов
        alert_service = AlertService(
            self.bot, 
            self.config.processing, 
            self.config.rate_limit
        )
        
        # Создаем основное хранилище
        self.storage = Storage(user_service, preset_service, token_service)
        await self.storage.initialize()
        
        # Создаем сервис обработки свечей
        self.candle_service = CandleService(
            alert_service, 
            self.storage, 
            self.config.processing
        )
        
        # Регистрируем в контейнере
        container.register_singleton(Storage, self.storage)
        container.register_singleton(CandleService, self.candle_service)
        container.register_singleton(TokenService, token_service)
    
    async def _setup_websocket(self) -> None:
        """Настройка WebSocket клиента."""
        message_handler = MessageHandler()
        
        # Создаем WebSocket клиент с коллбеком
        self.websocket_client = BinanceWebSocketClient(
            self.config.binance,
            message_handler,
            on_message_callback=self.candle_service.add_candle
        )
    
    async def start(self) -> None:
        """Запуск приложения."""
        logger.info("Starting application...")
        
        try:
            # Обновляем список токенов
            await self._update_tokens()
            
            # Запускаем сервис обработки свечей
            await self.candle_service.start()
            
            # Генерируем стримы для WebSocket
            streams = await self._generate_streams()
            
            # Создаем задачи
            self._tasks = [
                asyncio.create_task(self.dp.start_polling(self.bot)),
                asyncio.create_task(self.websocket_client.start(streams)),
                asyncio.create_task(self._monitor_system())
            ]
            
            logger.info(f"Application started with {len(streams)} streams")
            
            # Ждем завершения задач
            await asyncio.gather(*self._tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Error starting application: {e}")
            raise
    
    async def stop(self) -> None:
        """Остановка приложения."""
        logger.info("Stopping application...")
        
        # Останавливаем задачи
        for task in self._tasks:
            task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Останавливаем сервисы
        if self.candle_service:
            await self.candle_service.stop()
        
        if self.websocket_client:
            await self.websocket_client.stop()
        
        # Закрываем бота
        if self.bot:
            await self.bot.session.close()
        
        logger.info("Application stopped")
    
    async def _update_tokens(self) -> None:
        """Обновление списка токенов."""
        token_service = container.resolve(TokenService)
        
        if token_service.needs_update():
            logger.info("Updating token list...")
            success = await token_service.update_token_list()
            if not success:
                logger.warning("Failed to update token list, using cached data")
        else:
            logger.info("Token list is up to date")
    
    async def _generate_streams(self) -> list:
        """Генерация списка стримов для WebSocket."""
        token_service = container.resolve(TokenService)
        
        tokens = token_service.get_all_tokens()
        timeframes = token_service.get_all_timeframes()
        
        streams = [
            f"{token.lower()}@kline_{interval}"
            for token in tokens
            for interval in timeframes
        ]
        
        logger.info(f"Generated {len(streams)} streams for {len(tokens)} tokens")
        return streams
    
    async def _monitor_system(self) -> None:
        """Мониторинг системы."""
        while True:
            try:
                # Получаем статистику
                candle_stats = self.candle_service.get_stats()
                
                logger.info(
                    f"System stats - "
                    f"Candle queue: {candle_stats['candle_queue_size']}, "
                    f"Alert users: {candle_stats['alert_service']['active_users']}, "
                    f"Alert messages: {candle_stats['alert_service']['total_queued_messages']}"
                )
                
                await asyncio.sleep(300)  # Каждые 5 минут
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(60)


async def main():
    """Главная функция приложения."""
    # Настройка логирования
    setup_logging()
    
    # Загрузка конфигурации
    config = AppConfig.from_env()
    
    # Создание и запуск приложения
    app = Application(config)
    
    try:
        await app.initialize()
        await app.start()
    except KeyboardInterrupt:
        logger.info("Application shutdown by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)
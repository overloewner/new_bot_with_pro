# modules/telegram/service.py
"""Исправленный сервис Telegram интерфейса."""

import asyncio
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from shared.events import event_bus, Event, MESSAGE_SENT, USER_COMMAND_RECEIVED
from modules.telegram.handlers.main_handler import MainHandler
from modules.telegram.middleware.logging_middleware import LoggingMiddleware
from modules.gas_tracker.handlers.gas_handlers import GasHandlers

import logging

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для управления Telegram ботом."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.running = False
        
        # Handlers
        self.main_handler = MainHandler()
        self.gas_handlers = None
        
        # Подписываемся на события алертов
        event_bus.subscribe("price_alert.triggered", self._handle_price_alert)
        event_bus.subscribe("gas_alert_triggered", self._handle_gas_alert)
        event_bus.subscribe("whale_alert_triggered", self._handle_whale_alert)
        event_bus.subscribe("wallet_alert_triggered", self._handle_wallet_alert)
    
    def set_services(self, **services):
        """Инъекция сервисов в handlers."""
        self.main_handler.set_services(**services)
        
        # Создаем gas handlers с сервисом
        if 'gas_tracker' in services:
            self.gas_handlers = GasHandlers(services['gas_tracker'])
    
    async def start(self) -> None:
        """Запуск Telegram сервиса."""
        if self.running:
            return
        
        try:
            # Создаем бота и диспетчер
            self.bot = Bot(token=self.bot_token)
            self.dp = Dispatcher(storage=MemoryStorage())
            
            # Устанавливаем middleware
            self.dp.message.middleware(LoggingMiddleware())
            self.dp.callback_query.middleware(LoggingMiddleware())
            
            # Регистрируем обработчики
            await self._setup_handlers()
            
            # Удаляем webhook если есть
            await self._delete_webhook()
            
            self.running = True
            
            logger.info("✅ Telegram service initialized")
            
            # Запускаем polling
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"❌ Failed to start Telegram service: {e}")
            raise
    
    async def stop(self) -> None:
        """Остановка Telegram сервиса."""
        self.running = False
        
        try:
            if self.dp:
                await self.dp.stop_polling()
            
            if self.bot:
                await self.bot.session.close()
            
            logger.info("Telegram service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Telegram service: {e}")
    
    async def _setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        try:
            # Регистрируем основной обработчик
            self.main_handler.register(self.dp)
            
            # Регистрируем gas handlers если есть
            if self.gas_handlers:
                self.gas_handlers.register_handlers(self.dp)
            
            logger.info("✅ Telegram handlers registered")
            
        except Exception as e:
            logger.error(f"❌ Error setting up handlers: {e}")
            raise
    
    async def _delete_webhook(self) -> None:
        """Удаление webhook если активен."""
        try:
            webhook_info = await self.bot.get_webhook_info()
            if webhook_info.url:
                logger.info(f"Deleting webhook: {webhook_info.url}")
                await self.bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning(f"Error deleting webhook: {e}")
    
    async def _handle_price_alert(self, event: Event) -> None:
        """Обработка ценового алерта."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"📈 {message}")
                
        except Exception as e:
            logger.error(f"Error handling price alert: {e}")
    
    async def _handle_gas_alert(self, event: Event) -> None:
        """Обработка алерта газа."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"⛽ {message}")
                
        except Exception as e:
            logger.error(f"Error handling gas alert: {e}")
    
    async def _handle_whale_alert(self, event: Event) -> None:
        """Обработка алерта китов."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"🐋 {message}")
                
        except Exception as e:
            logger.error(f"Error handling whale alert: {e}")
    
    async def _handle_wallet_alert(self, event: Event) -> None:
        """Обработка алерта кошелька."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"👛 {message}")
                
        except Exception as e:
            logger.error(f"Error handling wallet alert: {e}")
    
    async def send_message(self, user_id: int, text: str, **kwargs) -> bool:
        """Отправка сообщения пользователю."""
        try:
            if not self.bot:
                return False
            
            await self.bot.send_message(chat_id=user_id, text=text, **kwargs)
            
            # Публикуем событие отправки
            await event_bus.publish(Event(
                type=MESSAGE_SENT,
                data={
                    "user_id": user_id,
                    "text_length": len(text),
                    "success": True
                },
                source_module="telegram"
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to {user_id}: {e}")
            
            await event_bus.publish(Event(
                type=MESSAGE_SENT,
                data={
                    "user_id": user_id,
                    "text_length": len(text),
                    "success": False,
                    "error": str(e)
                },
                source_module="telegram"
            ))
            
            return False
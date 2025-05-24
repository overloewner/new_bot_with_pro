# modules/telegram/service.py
"""Сервис Telegram интерфейса."""

import asyncio
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from shared.events import event_bus, Event, MESSAGE_SENT, USER_COMMAND_RECEIVED
from modules.telegram.handlers.main_handler import MainHandler
from modules.telegram.handlers.price_alerts_handler import PriceAlertsHandler
from modules.telegram.middleware.logging_middleware import LoggingMiddleware

import logging

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для управления Telegram ботом."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.running = False
        
        # Подписываемся на события алертов
        event_bus.subscribe("price_alert.triggered", self._handle_price_alert)
        event_bus.subscribe("gas.alert_triggered", self._handle_gas_alert)
        event_bus.subscribe("whale.alert_triggered", self._handle_whale_alert)
        event_bus.subscribe("wallet.alert_triggered", self._handle_wallet_alert)
    
    async def start(self) -> None:
        """Запуск Telegram сервиса."""
        if self.running:
            return
        
        # Создаем бота и диспетчер
        self.bot = Bot(token=self.bot_token)
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Подключаем middleware
        self.dp.middleware.setup(LoggingMiddleware())
        
        # Регистрируем обработчики
        await self._setup_handlers()
        
        # Удаляем webhook если есть
        await self._delete_webhook()
        
        self.running = True
        
        # Запускаем polling
        await self.dp.start_polling(self.bot)
    
    async def stop(self) -> None:
        """Остановка Telegram сервиса."""
        self.running = False
        
        if self.dp:
            await self.dp.stop_polling()
        
        if self.bot:
            await self.bot.session.close()
        
        logger.info("Telegram service stopped")
    
    async def _setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        # Получаем сервисы из других модулей через event bus
        from shared.events import event_bus
        
        # Регистрируем основной обработчик
        main_handler = MainHandler()
        main_handler.register(self.dp)
        
        # Регистрируем обработчик ценовых алертов
        price_handler = PriceAlertsHandler()
        price_handler.register(self.dp)
        
        logger.info("Telegram handlers registered")
    
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

# modules/telegram/service.py
"""Сервис Telegram с встроенным диспетчером алертов."""

import asyncio
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from shared.events import event_bus, Event, MESSAGE_SENT, USER_COMMAND_RECEIVED
from .handlers.main_handler import MainHandler
from .middleware.logging_middleware import LoggingMiddleware
from .alert_dispatcher import AlertDispatcher

import logging

logger = logging.getLogger(__name__)

class TelegramService:
    """Сервис для управления Telegram ботом с диспетчером алертов."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.running = False
        
        # Handlers
        self.main_handler = MainHandler()
        self.price_alerts_handler = None
        
        # Alert dispatcher
        self.alert_dispatcher = AlertDispatcher(self)
        
        # Подписываемся на события алертов
        event_bus.subscribe("price_alert.triggered", self._handle_price_alert)
        
        # Подписываемся на системные события
        event_bus.subscribe("system.error", self._handle_system_error)
    
    def set_services(self, **services):
        """Инъекция сервисов в handlers."""
        # Устанавливаем сервисы в главный handler
        self.main_handler.set_services(**services)
        
        # Создаем Price Alerts handler если есть сервис
        if 'price_alerts' in services and services['price_alerts']:
            from .handlers.price_alerts_handler import PriceAlertsHandler
            self.price_alerts_handler = PriceAlertsHandler()
            logger.info("✅ Price Alerts handlers initialized")
    
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
            
            # Запускаем alert dispatcher
            await self.alert_dispatcher.start()
            
            self.running = True
            
            logger.info("✅ Telegram service initialized")
            
            # Публикуем событие готовности
            await event_bus.publish(Event(
                type="telegram.service_ready",
                data={"handlers_count": 1},
                source_module="telegram"
            ))
            
            # Запускаем polling
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"❌ Failed to start Telegram service: {e}")
            raise
    
    async def stop(self) -> None:
        """Остановка Telegram сервиса."""
        self.running = False
        
        try:
            # Останавливаем alert dispatcher
            await self.alert_dispatcher.stop()
            
            if self.dp:
                await self.dp.stop_polling()
            
            if self.bot:
                await self.bot.session.close()
            
            logger.info("📱 Telegram service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Telegram service: {e}")
    
    async def _setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        try:
            handlers_registered = 0
            
            # Регистрируем основной обработчик
            self.main_handler.register(self.dp)
            handlers_registered += 1
            logger.info("✅ Main handlers registered")
            
            # Регистрируем Price Alerts handlers если доступны
            if self.price_alerts_handler:
                self.price_alerts_handler.register_handlers(self.dp)
                handlers_registered += 1
                logger.info("✅ Price Alerts handlers registered")
            
            logger.info(f"✅ Total handlers registered: {handlers_registered}")
            
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
    
    # EVENT HANDLERS
    
    async def _handle_price_alert(self, event: Event) -> None:
        """Обработка ценового алерта."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.alert_dispatcher.dispatch_alert(user_id, f"📈 {message}", "price")
                logger.debug(f"Dispatched price alert to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error handling price alert: {e}")
    
    async def _handle_system_error(self, event: Event) -> None:
        """Обработка системных ошибок."""
        try:
            error = event.data.get("error")
            module = event.source_module
            
            # Можно отправить уведомление администратору
            logger.error(f"System error in {module}: {error}")
            
        except Exception as e:
            logger.error(f"Error handling system error: {e}")
    
    async def send_message(self, user_id: int, text: str, **kwargs) -> bool:
        """Отправка сообщения пользователю."""
        try:
            if not self.bot:
                logger.error("Bot not initialized")
                return False
            
            # Ограничиваем длину сообщения
            if len(text) > 4096:
                text = text[:4093] + "..."
            
            await self.bot.send_message(chat_id=user_id, text=text, **kwargs)
            
            # Публикуем событие успешной отправки
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
            error_message = str(e)
            logger.error(f"Error sending message to {user_id}: {error_message}")
            
            # Публикуем событие неудачной отправки
            await event_bus.publish(Event(
                type=MESSAGE_SENT,
                data={
                    "user_id": user_id,
                    "text_length": len(text),
                    "success": False,
                    "error": error_message
                },
                source_module="telegram"
            ))
            
            return False
    
    async def send_notification(self, user_id: int, title: str, message: str, alert_type: str = "info") -> bool:
        """Отправка форматированного уведомления."""
        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "price": "📈",
            "gas": "⛽",
            "whale": "🐋",
            "wallet": "👛"
        }
        
        icon = icons.get(alert_type, "🔔")
        formatted_text = f"{icon} <b>{title}</b>\n\n{message}"
        
        return await self.send_message(user_id, formatted_text, parse_mode="HTML")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики сервиса."""
        handlers_count = 1  # main_handler
        if self.price_alerts_handler:
            handlers_count += 1
            
        return {
            "running": self.running,
            "bot_initialized": self.bot is not None,
            "dispatcher_initialized": self.dp is not None,
            "handlers_registered": handlers_count,
            "alert_dispatcher_stats": self.alert_dispatcher.get_stats()
        }
# modules/telegram/service.py
"""Исправленный сервис Telegram с полной регистрацией всех handlers."""

import asyncio
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from shared.events import event_bus, Event, MESSAGE_SENT, USER_COMMAND_RECEIVED
from modules.telegram.handlers.main_handler import MainHandler
from modules.telegram.middleware.logging_middleware import LoggingMiddleware

# Импортируем все handlers
from modules.gas_tracker.handlers.gas_handlers import GasHandlers
from modules.price_alerts.handlers.main_handler import PriceAlertsHandler
from modules.whales.handlers.whale_handlers import WhaleHandlers
from modules.wallet_tracker.handlers.wallet_handlers import WalletHandlers

import logging

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для управления Telegram ботом с полной функциональностью."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.running = False
        
        # Все handlers
        self.main_handler = MainHandler()
        self.price_alerts_handler = PriceAlertsHandler()
        self.gas_handlers = None
        self.whale_handlers = None
        self.wallet_handlers = None
        
        # Подписываемся на события алертов
        event_bus.subscribe("price_alert.triggered", self._handle_price_alert)
        event_bus.subscribe("gas_alert_triggered", self._handle_gas_alert)
        event_bus.subscribe("whale_alert_triggered", self._handle_whale_alert)
        event_bus.subscribe("wallet_alert_triggered", self._handle_wallet_alert)
        
        # Подписываемся на системные события
        event_bus.subscribe("system.error", self._handle_system_error)
    
    def set_services(self, **services):
        """Инъекция сервисов в handlers."""
        # Устанавливаем сервисы в главный handler
        self.main_handler.set_services(**services)
        
        # Создаем специализированные handlers с сервисами
        if 'gas_tracker' in services and services['gas_tracker']:
            self.gas_handlers = GasHandlers(services['gas_tracker'])
            logger.info("✅ Gas handlers initialized")
        
        if 'whale_tracker' in services and services['whale_tracker']:
            self.whale_handlers = WhaleHandlers(services['whale_tracker'])
            logger.info("✅ Whale handlers initialized")
        
        if 'wallet_tracker' in services and services['wallet_tracker']:
            self.wallet_handlers = WalletHandlers(services['wallet_tracker'])
            logger.info("✅ Wallet handlers initialized")
    
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
            
            # Регистрируем все обработчики
            await self._setup_all_handlers()
            
            # Удаляем webhook если есть
            await self._delete_webhook()
            
            self.running = True
            
            logger.info("✅ Telegram service initialized with all handlers")
            
            # Публикуем событие готовности
            await event_bus.publish(Event(
                type="telegram.service_ready",
                data={"handlers_count": self._count_registered_handlers()},
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
            if self.dp:
                await self.dp.stop_polling()
            
            if self.bot:
                await self.bot.session.close()
            
            logger.info("📱 Telegram service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Telegram service: {e}")
    
    async def _setup_all_handlers(self) -> None:
        """Настройка всех обработчиков команд."""
        try:
            handlers_registered = 0
            
            # Регистрируем основной обработчик (ОБЯЗАТЕЛЬНО ПЕРВЫМ)
            self.main_handler.register(self.dp)
            handlers_registered += 1
            logger.info("✅ Main handlers registered")
            
            # Регистрируем Price Alerts handlers
            self.price_alerts_handler.register_handlers(self.dp)
            handlers_registered += 1
            logger.info("✅ Price Alerts handlers registered")
            
            # Регистрируем Gas handlers если доступны
            if self.gas_handlers:
                self.gas_handlers.register_handlers(self.dp)
                handlers_registered += 1
                logger.info("✅ Gas handlers registered")
            else:
                logger.warning("⚠️ Gas handlers not available")
            
            # Регистрируем Whale handlers если доступны
            if self.whale_handlers:
                self.whale_handlers.register_handlers(self.dp)
                handlers_registered += 1
                logger.info("✅ Whale handlers registered")
            else:
                logger.warning("⚠️ Whale handlers not available")
            
            # Регистрируем Wallet handlers если доступны
            if self.wallet_handlers:
                self.wallet_handlers.register_handlers(self.dp)
                handlers_registered += 1
                logger.info("✅ Wallet handlers registered")
            else:
                logger.warning("⚠️ Wallet handlers not available")
            
            logger.info(f"✅ Total handlers registered: {handlers_registered}")
            
        except Exception as e:
            logger.error(f"❌ Error setting up handlers: {e}")
            raise
    
    def _count_registered_handlers(self) -> int:
        """Подсчет зарегистрированных handlers."""
        count = 1  # main_handler всегда есть
        
        if self.price_alerts_handler:
            count += 1
        if self.gas_handlers:
            count += 1
        if self.whale_handlers:
            count += 1
        if self.wallet_handlers:
            count += 1
        
        return count
    
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
                await self.send_message(user_id, f"📈 {message}", parse_mode="HTML")
                logger.debug(f"Sent price alert to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error handling price alert: {e}")
    
    async def _handle_gas_alert(self, event: Event) -> None:
        """Обработка алерта газа."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"⛽ {message}", parse_mode="HTML")
                logger.debug(f"Sent gas alert to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error handling gas alert: {e}")
    
    async def _handle_whale_alert(self, event: Event) -> None:
        """Обработка алерта китов."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"🐋 {message}", parse_mode="HTML")
                logger.debug(f"Sent whale alert to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error handling whale alert: {e}")
    
    async def _handle_wallet_alert(self, event: Event) -> None:
        """Обработка алерта кошелька."""
        try:
            user_id = event.data.get("user_id")
            message = event.data.get("message")
            
            if user_id and message:
                await self.send_message(user_id, f"👛 {message}", parse_mode="HTML")
                logger.debug(f"Sent wallet alert to user {user_id}")
                
        except Exception as e:
            logger.error(f"Error handling wallet alert: {e}")
    
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
        """Отправка сообщения пользователю с улучшенной обработкой ошибок."""
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
        return {
            "running": self.running,
            "bot_initialized": self.bot is not None,
            "dispatcher_initialized": self.dp is not None,
            "handlers_registered": self._count_registered_handlers(),
            "handlers_available": {
                "main": True,
                "price_alerts": True,
                "gas": self.gas_handlers is not None,
                "whale": self.whale_handlers is not None,
                "wallet": self.wallet_handlers is not None
            }
        }
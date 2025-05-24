# modules/price_alerts/service.py
"""Основной сервис ценовых алертов с полной функциональностью."""

import asyncio
from typing import Dict, Any, Optional
from shared.events import event_bus, Event
from shared.utils.logger import get_module_logger
from shared.database.manager import DatabaseManager

from .core.candle_processor import CandleProcessor
from .core.alert_dispatcher import AlertDispatcher
from .core.preset_manager import PresetManager
from .core.websocket_manager import WebSocketManager
from .core.token_manager import TokenManager

logger = get_module_logger("price_alerts")


class PriceAlertsService:
    """Основной сервис ценовых алертов с автономной архитектурой."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager
        self.running = False
        
        # Основные компоненты
        self.token_manager = TokenManager()
        self.preset_manager = PresetManager(db_manager)
        self.alert_dispatcher = AlertDispatcher()
        self.candle_processor = CandleProcessor(self.alert_dispatcher, self.preset_manager)
        self.websocket_manager = WebSocketManager(self.candle_processor.process_candle)
        
        # Подписываемся на внешние события
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """Настройка обработчиков событий."""
        event_bus.subscribe("price_alerts.create_preset", self._handle_create_preset)
        event_bus.subscribe("price_alerts.activate_preset", self._handle_activate_preset)
        event_bus.subscribe("price_alerts.deactivate_preset", self._handle_deactivate_preset)
        event_bus.subscribe("price_alerts.get_user_presets", self._handle_get_user_presets)
        event_bus.subscribe("price_alerts.get_all_tokens", self._handle_get_tokens)
        event_bus.subscribe("price_alerts.start_monitoring", self._handle_start_monitoring)
        event_bus.subscribe("price_alerts.stop_monitoring", self._handle_stop_monitoring)
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        logger.info("Starting Price Alerts service...")
        
        try:
            # Инициализируем компоненты в правильном порядке
            await self.token_manager.initialize()
            await self.preset_manager.initialize()
            await self.alert_dispatcher.start()
            await self.candle_processor.start()
            
            # WebSocket запускается только если есть активные пресеты
            await self._check_and_start_websocket()
            
            await event_bus.publish(Event(
                type="system.module_started",
                data={"module": "price_alerts"},
                source_module="price_alerts"
            ))
            
            logger.info("Price Alerts service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Price Alerts service: {e}")
            self.running = False
            raise
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        if not self.running:
            return
        
        logger.info("Stopping Price Alerts service...")
        self.running = False
        
        try:
            # Останавливаем компоненты в обратном порядке
            await self.websocket_manager.stop()
            await self.candle_processor.stop()
            await self.alert_dispatcher.stop()
            
            await event_bus.publish(Event(
                type="system.module_stopped",
                data={"module": "price_alerts"},
                source_module="price_alerts"
            ))
            
            logger.info("Price Alerts service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Price Alerts service: {e}")
    
    async def _check_and_start_websocket(self):
        """Проверка и запуск WebSocket если есть активные пресеты."""
        active_streams = await self.preset_manager.get_required_streams()
        
        if active_streams:
            await self.websocket_manager.start(active_streams)
            logger.info(f"Started WebSocket with {len(active_streams)} streams")
        else:
            logger.info("No active presets, WebSocket not started")
    
    async def _handle_create_preset(self, event: Event):
        """Создание пресета."""
        try:
            user_id = event.data.get("user_id")
            preset_data = event.data.get("preset_data")
            
            preset_id = await self.preset_manager.create_preset(user_id, preset_data)
            
            await event_bus.publish(Event(
                type="price_alerts.preset_created",
                data={"user_id": user_id, "preset_id": preset_id, "success": preset_id is not None},
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error creating preset: {e}")
    
    async def _handle_activate_preset(self, event: Event):
        """Активация пресета."""
        try:
            user_id = event.data.get("user_id")
            preset_id = event.data.get("preset_id")
            
            success = await self.preset_manager.activate_preset(user_id, preset_id)
            
            if success:
                # Обновляем WebSocket стримы
                await self._update_websocket_streams()
            
            await event_bus.publish(Event(
                type="price_alerts.preset_activated",
                data={"user_id": user_id, "preset_id": preset_id, "success": success},
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error activating preset: {e}")
    
    async def _handle_deactivate_preset(self, event: Event):
        """Деактивация пресета."""
        try:
            user_id = event.data.get("user_id")
            preset_id = event.data.get("preset_id")
            
            success = await self.preset_manager.deactivate_preset(user_id, preset_id)
            
            if success:
                # Обновляем WebSocket стримы
                await self._update_websocket_streams()
            
            await event_bus.publish(Event(
                type="price_alerts.preset_deactivated",
                data={"user_id": user_id, "preset_id": preset_id, "success": success},
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error deactivating preset: {e}")
    
    async def _handle_get_user_presets(self, event: Event):
        """Получение пресетов пользователя."""
        try:
            user_id = event.data.get("user_id")
            presets = await self.preset_manager.get_user_presets(user_id)
            
            await event_bus.publish(Event(
                type="price_alerts.user_presets_response",
                data={"user_id": user_id, "presets": presets},
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error getting user presets: {e}")
    
    async def _handle_get_tokens(self, event: Event):
        """Получение списка токенов."""
        try:
            tokens = self.token_manager.get_all_tokens()
            
            await event_bus.publish(Event(
                type="price_alerts.tokens_response",
                data={"tokens": tokens},
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error getting tokens: {e}")
    
    async def _handle_start_monitoring(self, event: Event):
        """Запуск мониторинга для пользователя."""
        try:
            user_id = event.data.get("user_id")
            await self.preset_manager.set_user_monitoring(user_id, True)
            
            # Перезапускаем WebSocket если нужно
            await self._update_websocket_streams()
            
        except Exception as e:
            logger.error(f"Error starting monitoring: {e}")
    
    async def _handle_stop_monitoring(self, event: Event):
        """Остановка мониторинга для пользователя."""
        try:
            user_id = event.data.get("user_id")
            await self.preset_manager.set_user_monitoring(user_id, False)
            
            # Очищаем очереди алертов для пользователя
            await self.alert_dispatcher.cleanup_user_queue(user_id)
            
            # Обновляем WebSocket стримы
            await self._update_websocket_streams()
            
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")
    
    async def _update_websocket_streams(self):
        """Обновление WebSocket стримов на основе активных пресетов."""
        if not self.running:
            return
        
        required_streams = await self.preset_manager.get_required_streams()
        await self.websocket_manager.update_streams(required_streams)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики сервиса."""
        return {
            "running": self.running,
            "token_manager": self.token_manager.get_stats(),
            "preset_manager": self.preset_manager.get_stats(),
            "candle_processor": self.candle_processor.get_stats(),
            "alert_dispatcher": self.alert_dispatcher.get_stats(),
            "websocket_manager": self.websocket_manager.get_stats()
        }
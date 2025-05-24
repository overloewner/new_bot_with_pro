# modules/price_alerts/service.py
"""Основной сервис ценовых алертов."""

import asyncio
from typing import Dict, Any, Optional
from shared.events import event_bus, Event
from shared.utils.logger import get_module_logger
from shared.database.manager import DatabaseManager

# Импортируем существующие сервисы
from .services.candle_service import CandleService
from .services.alert_service import AlertService
from .services.preset_service import PresetService
from .services.token_service import TokenService
from .websocket.client import BinanceWebSocketClient
from .websocket.message_handler import MessageHandler


class PriceAlertsService:
    """Основной сервис ценовых алертов с интеграцией в модульную архитектуру."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager
        self.logger = get_module_logger("price_alerts")
        
        # Существующие сервисы (адаптируем)
        self.token_service: Optional[TokenService] = None
        self.preset_service: Optional[PresetService] = None
        self.alert_service: Optional[AlertService] = None
        self.candle_service: Optional[CandleService] = None
        self.websocket_client: Optional[BinanceWebSocketClient] = None
        
        self.running = False
        
        # Подписываемся на события
        event_bus.subscribe("price_alerts.create_preset", self._handle_create_preset)
        event_bus.subscribe("price_alerts.activate_preset", self._handle_activate_preset)
    
    async def initialize(self) -> None:
        """Инициализация сервиса."""
        try:
            self.logger.info("🔧 Initializing Price Alerts service...")
            
            # Инициализируем существующие сервисы
            self.token_service = TokenService()
            await self.token_service.initialize()
            
            self.preset_service = PresetService()
            self.alert_service = AlertService()
            
            self.candle_service = CandleService(
                alert_service=self.alert_service,
                storage=None,  # Будем использовать через события
                config=None
            )
            
            # WebSocket клиент
            message_handler = MessageHandler()
            self.websocket_client = BinanceWebSocketClient(
                config=None,
                message_handler=message_handler,
                on_message_callback=self._handle_candle_message
            )
            
            self.logger.info("✅ Price Alerts service initialized")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Price Alerts: {e}")
            raise
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        self.logger.info("🚀 Starting Price Alerts service...")
        
        try:
            # Запускаем сервисы
            await self.alert_service.start()
            await self.candle_service.start()
            
            # Генерируем стримы и запускаем WebSocket
            streams = await self._generate_streams()
            if streams:
                await self.websocket_client.start(streams)
            
            # Публикуем событие запуска
            await event_bus.publish(Event(
                type="system.module_started",
                data={"module": "price_alerts"},
                source_module="price_alerts"
            ))
            
            self.logger.info("✅ Price Alerts service started")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start Price Alerts: {e}")
            self.running = False
            raise
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        if not self.running:
            return
        
        self.logger.info("🛑 Stopping Price Alerts service...")
        self.running = False
        
        try:
            if self.websocket_client:
                await self.websocket_client.stop()
            
            if self.candle_service:
                await self.candle_service.stop()
            
            if self.alert_service:
                await self.alert_service.stop()
            
            await event_bus.publish(Event(
                type="system.module_stopped",
                data={"module": "price_alerts"},
                source_module="price_alerts"
            ))
            
            self.logger.info("✅ Price Alerts service stopped")
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping Price Alerts: {e}")
    
    async def _generate_streams(self) -> list:
        """Генерация WebSocket стримов на основе активных пресетов."""
        if not self.token_service:
            return []
        
        tokens = self.token_service.get_all_tokens()
        timeframes = self.token_service.get_all_timeframes()
        
        # TODO: Фильтровать только используемые в активных пресетах
        streams = [
            f"{token.lower()}@kline_{interval}"
            for token in tokens[:100]  # Ограничиваем для начала
            for interval in timeframes
        ]
        
        self.logger.info(f"Generated {len(streams)} WebSocket streams")
        return streams
    
    async def _handle_candle_message(self, candle_data: Dict[str, Any]) -> None:
        """Обработка сообщения свечи от WebSocket."""
        try:
            if self.candle_service:
                await self.candle_service.add_candle(candle_data)
        except Exception as e:
            self.logger.error(f"Error handling candle message: {e}")
    
    async def _handle_create_preset(self, event: Event) -> None:
        """Обработка события создания пресета."""
        try:
            user_id = event.data.get("user_id")
            preset_data = event.data.get("preset_data")
            
            if self.preset_service and user_id and preset_data:
                preset_id = await self.preset_service.create_preset(user_id, preset_data)
                
                # Публикуем ответ
                await event_bus.publish(Event(
                    type="price_alerts.preset_created",
                    data={"user_id": user_id, "preset_id": preset_id, "success": preset_id is not None},
                    source_module="price_alerts"
                ))
        except Exception as e:
            self.logger.error(f"Error creating preset: {e}")
    
    async def _handle_activate_preset(self, event: Event) -> None:
        """Обработка события активации пресета."""
        try:
            user_id = event.data.get("user_id")
            preset_id = event.data.get("preset_id")
            
            if self.preset_service and user_id and preset_id:
                success = await self.preset_service.activate_preset(user_id, preset_id)
                
                await event_bus.publish(Event(
                    type="price_alerts.preset_activated",
                    data={"user_id": user_id, "preset_id": preset_id, "success": success},
                    source_module="price_alerts"
                ))
        except Exception as e:
            self.logger.error(f"Error activating preset: {e}")
# modules/price_alerts/service.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

# Замените существующий файл этим содержимым:

import asyncio
from typing import Dict, Any, Optional, List
from shared.events import event_bus, Event
from shared.utils.logger import get_module_logger
from shared.database.manager import DatabaseManager

# Импортируем наши WebSocket компоненты
from .websocket import BinanceWebSocketClient, WebSocketConfig
from .services.token_service import TokenService

logger = get_module_logger("price_alerts")


class PriceAlertsService:
    """Основной сервис ценовых алертов."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager
        
        # Сервисы (пока заглушки)
        self.token_service: Optional[TokenService] = None
        self.websocket_client: Optional[BinanceWebSocketClient] = None
        
        self.running = False
        
        # Подписываемся на события
        event_bus.subscribe("price_alerts.create_preset", self._handle_create_preset)
        event_bus.subscribe("price_alerts.get_all_tokens", self._handle_get_tokens)
    
    async def initialize(self) -> None:
        """Инициализация сервиса."""
        try:
            logger.info("Initializing Price Alerts service...")
            
            # Создаем заглушку для token service
            self.token_service = MockTokenService()
            
            # Создаем WebSocket клиент
            ws_config = WebSocketConfig()
            self.websocket_client = BinanceWebSocketClient(
                config=ws_config,
                on_message_callback=self._handle_candle_message
            )
            
            logger.info("Price Alerts service initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Price Alerts: {e}")
            raise
    
    async def start(self) -> None:
        """Запуск сервиса."""
        if self.running:
            return
        
        self.running = True
        logger.info("Starting Price Alerts service...")
        
        try:
            # Генерируем стримы для популярных пар
            streams = self._generate_test_streams()
            
            if streams and self.websocket_client:
                # Запускаем WebSocket в отдельной задаче
                asyncio.create_task(self.websocket_client.start(streams))
            
            await event_bus.publish(Event(
                type="system.module_started",
                data={"module": "price_alerts"},
                source_module="price_alerts"
            ))
            
            logger.info("Price Alerts service started")
            
        except Exception as e:
            logger.error(f"Failed to start Price Alerts: {e}")
            self.running = False
            raise
    
    async def stop(self) -> None:
        """Остановка сервиса."""
        if not self.running:
            return
        
        logger.info("Stopping Price Alerts service...")
        self.running = False
        
        try:
            if self.websocket_client:
                await self.websocket_client.stop()
            
            await event_bus.publish(Event(
                type="system.module_stopped",
                data={"module": "price_alerts"},
                source_module="price_alerts"
            ))
            
            logger.info("Price Alerts service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Price Alerts: {e}")
    
    def _generate_test_streams(self) -> List[str]:
        """Генерация тестовых стримов для популярных пар."""
        # Популярные пары для тестирования
        popular_pairs = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
            "XRPUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT"
        ]
        
        # Интервалы
        intervals = ["1m", "5m", "15m", "1h"]
        
        # Генерируем стримы
        streams = []
        for pair in popular_pairs:
            for interval in intervals:
                streams.append(f"{pair.lower()}@kline_{interval}")
        
        logger.info(f"Generated {len(streams)} WebSocket streams")
        return streams
    
    async def _handle_candle_message(self, candle_data: Dict[str, Any]) -> None:
        """Обработка сообщения свечи от WebSocket."""
        try:
            # Простой анализ изменения цены
            open_price = candle_data['open']
            close_price = candle_data['close']
            
            if open_price > 0:
                change_percent = ((close_price - open_price) / open_price) * 100
                
                # Если изменение больше 2%, отправляем тестовый алерт
                if abs(change_percent) > 2.0:
                    direction = "🟢" if change_percent > 0 else "🔴"
                    
                    await event_bus.publish(Event(
                        type="price_alert.triggered",
                        data={
                            "user_id": 123456789,  # Тестовый user_id
                            "message": (
                                f"{direction} {candle_data['symbol']} {candle_data['interval']}: "
                                f"{abs(change_percent):.2f}% "
                                f"(${close_price:.4f})"
                            )
                        },
                        source_module="price_alerts"
                    ))
                    
                    logger.info(
                        f"Price alert: {candle_data['symbol']} {change_percent:.2f}%"
                    )
                    
        except Exception as e:
            logger.error(f"Error processing candle: {e}")
    
    async def _handle_create_preset(self, event: Event) -> None:
        """Обработка создания пресета."""
        try:
            user_id = event.data.get("user_id")
            preset_data = event.data.get("preset_data")
            
            logger.info(f"Creating preset for user {user_id}: {preset_data}")
            
            # Заглушка - возвращаем успех
            await event_bus.publish(Event(
                type="price_alerts.preset_created",
                data={
                    "user_id": user_id, 
                    "preset_id": "test-preset-123",
                    "success": True
                },
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error creating preset: {e}")
    
    async def _handle_get_tokens(self, event: Event) -> None:
        """Обработка запроса списка токенов."""
        try:
            # Возвращаем популярные токены
            tokens = [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
                "XRPUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT"
            ]
            
            await event_bus.publish(Event(
                type="price_alerts.tokens_response",
                data={"tokens": tokens},
                source_module="price_alerts"
            ))
            
        except Exception as e:
            logger.error(f"Error getting tokens: {e}")


class MockTokenService:
    """Заглушка для TokenService."""
    
    def get_all_tokens(self) -> List[str]:
        return [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
            "XRPUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT"
        ]
    
    def get_all_timeframes(self) -> List[str]:
        return ["1m", "5m", "15m", "1h", "4h", "1d"]
# modules/price_alerts/websocket/client.py
"""Адаптированный WebSocket клиент для модульной архитектуры."""

import asyncio
import aiohttp
from typing import List, Callable, Optional, Dict, Any
from dataclasses import dataclass

from shared.utils.logger import get_module_logger
from shared.exceptions import WebSocketError
from .message_handler import MessageHandler
from .reconnect_manager import ReconnectManager

logger = get_module_logger("websocket_client")


@dataclass
class WebSocketConfig:
    """Конфигурация WebSocket клиента."""
    ws_url: str = "wss://stream.binance.com:9443/ws/"
    connection_timeout: int = 30
    max_streams_per_connection: int = 200  # Binance лимит
    reconnect_delay: int = 5


class BinanceWebSocketClient:
    """WebSocket клиент для Binance с модульной архитектурой."""
    
    def __init__(
        self, 
        config: Optional[WebSocketConfig] = None,
        on_message_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.config = config or WebSocketConfig()
        self.on_message_callback = on_message_callback
        
        # Компоненты
        self.message_handler = MessageHandler()
        self.reconnect_manager = ReconnectManager(self.config.reconnect_delay)
        
        # Состояние
        self.session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._connection_tasks: List[asyncio.Task] = []
    
    async def start(self, streams: List[str]) -> None:
        """Запуск WebSocket клиента."""
        if self._running:
            return
        
        self._running = True
        
        try:
            # Создаем HTTP сессию
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.connection_timeout)
            )
            
            # Разбиваем стримы на чанки
            stream_chunks = self._chunk_streams(streams)
            
            logger.info(f"Starting WebSocket with {len(stream_chunks)} connections")
            
            # Создаем задачи подключения
            self._connection_tasks = [
                asyncio.create_task(self._maintain_connection(chunk))
                for chunk in stream_chunks
            ]
            
            # Запускаем все подключения параллельно
            await asyncio.gather(*self._connection_tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket client: {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Остановка WebSocket клиента."""
        self._running = False
        
        # Останавливаем задачи
        for task in self._connection_tasks:
            if not task.done():
                task.cancel()
        
        if self._connection_tasks:
            await asyncio.gather(*self._connection_tasks, return_exceptions=True)
        
        self._connection_tasks.clear()
        
        # Закрываем сессию
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("WebSocket client stopped")
    
    def _chunk_streams(self, streams: List[str]) -> List[List[str]]:
        """Разбивка стримов на чанки по лимиту Binance."""
        chunks = []
        for i in range(0, len(streams), self.config.max_streams_per_connection):
            chunk = streams[i:i + self.config.max_streams_per_connection]
            chunks.append(chunk)
        return chunks
    
    async def _maintain_connection(self, streams: List[str]) -> None:
        """Поддержание WebSocket подключения."""
        url = f"{self.config.ws_url}{'/'.join(streams)}"
        
        while self._running:
            try:
                await self._connect_and_listen(url)
                
            except Exception as e:
                if self._running:
                    logger.error(f"WebSocket connection error: {e}")
                    await self.reconnect_manager.wait_before_reconnect()
                else:
                    break
    
    async def _connect_and_listen(self, url: str) -> None:
        """Подключение и прослушивание WebSocket."""
        if not self.session:
            raise WebSocketError("HTTP session not initialized")
        
        try:
            async with self.session.ws_connect(url) as ws:
                logger.info(f"Connected to WebSocket: {url[:100]}...")
                self.reconnect_manager.reset()
                
                async for msg in ws:
                    if not self._running:
                        break
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logger.warning("WebSocket closed by server")
                        break
                        
        except aiohttp.ClientError as e:
            raise WebSocketError(f"Connection failed: {e}")
        except Exception as e:
            raise WebSocketError(f"Unexpected error: {e}")
    
    async def _handle_message(self, message: str) -> None:
        """Обработка входящего сообщения."""
        try:
            candle_data = await self.message_handler.handle_message(message)
            
            if self.on_message_callback and candle_data:
                await self.on_message_callback(candle_data)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def is_running(self) -> bool:
        """Проверка состояния."""
        return self._running
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        return {
            "running": self._running,
            "connections": len(self._connection_tasks),
            "message_handler": self.message_handler.get_stats(),
            "reconnect_manager": self.reconnect_manager.get_stats()
        }
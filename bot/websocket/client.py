"""WebSocket клиент для Binance."""

import asyncio
import aiohttp
from typing import List, Callable, Optional
from pathlib import Path

from bot.core.config import BinanceConfig
from bot.core.exceptions import WebSocketError
from bot.core.logger import get_logger
from bot.websocket.message_handler import MessageHandler
from bot.websocket.reconnect_manager import ReconnectManager

logger = get_logger(__name__)


class BinanceWebSocketClient:
    """WebSocket клиент для подключения к Binance Stream API."""
    
    def __init__(
        self, 
        config: BinanceConfig,
        message_handler: MessageHandler,
        on_message_callback: Optional[Callable] = None
    ):
        self.config = config
        self.message_handler = message_handler
        self.on_message_callback = on_message_callback
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.reconnect_manager = ReconnectManager(config.reconnect_delay)
        
        # Состояние
        self._running = False
        self._connection_tasks: List[asyncio.Task] = []
    
    async def start(self, streams: List[str]) -> None:
        """Запуск WebSocket клиента с указанными стримами."""
        if self._running:
            return
        
        self._running = True
        
        # Создаем HTTP сессию
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.connection_timeout)
        )
        
        # Разбиваем стримы на чанки и создаем подключения
        stream_chunks = self._chunk_streams(streams)
        
        logger.info(f"Starting WebSocket client with {len(stream_chunks)} connections")
        
        # Создаем задачи подключения для каждого чанка
        self._connection_tasks = [
            asyncio.create_task(self._maintain_connection(chunk))
            for chunk in stream_chunks
        ]
        
        # Запускаем все подключения
        await asyncio.gather(*self._connection_tasks, return_exceptions=True)
    
    async def stop(self) -> None:
        """Остановка WebSocket клиента."""
        self._running = False
        
        # Останавливаем все задачи подключения
        for task in self._connection_tasks:
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
        """Поддержание WebSocket подключения с переподключением."""
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
        """Подключение к WebSocket и обработка сообщений."""
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
                        logger.warning("WebSocket connection closed by server")
                        break
                        
        except aiohttp.ClientError as e:
            raise WebSocketError(f"WebSocket connection failed: {e}")
        except Exception as e:
            raise WebSocketError(f"Unexpected WebSocket error: {e}")
    
    async def _handle_message(self, message: str) -> None:
        """Обработка входящего сообщения."""
        try:
            # Передаем сообщение в обработчик
            candle_data = await self.message_handler.handle_message(message)
            
            # Если есть callback и получены данные свечи, вызываем его
            if self.on_message_callback and candle_data:
                await self.on_message_callback(candle_data)
                
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    def is_running(self) -> bool:
        """Проверка состояния клиента."""
        return self._running
    
    def get_connection_count(self) -> int:
        """Получение количества активных подключений."""
        return len(self._connection_tasks)
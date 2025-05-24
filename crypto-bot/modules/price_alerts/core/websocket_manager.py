# modules/price_alerts/core/websocket_manager.py
"""WebSocket менеджер с оптимизацией подключений."""

import asyncio
import aiohttp
import orjson
import time
from typing import List, Set, Optional, Callable, Dict, Any
from collections import defaultdict

from shared.utils.logger import get_module_logger

logger = get_module_logger("websocket_manager")


class WebSocketManager:
    """Менеджер WebSocket подключений с оптимизацией."""
    
    def __init__(self, message_callback: Callable):
        self.message_callback = message_callback
        
        # Состояние
        self._running = False
        self._current_streams: Set[str] = set()
        self._connection_tasks: List[asyncio.Task] = []
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Конфигурация Binance
        self.base_url = "wss://stream.binance.com:9443/ws/"
        self.max_streams_per_connection = 200  # Лимит Binance
        self.reconnect_delay = 5
        self.connection_timeout = 30
        
        # Статистика
        self._stats = {
            'connections': 0,
            'messages_received': 0,
            'reconnects': 0,
            'errors': 0,
            'last_message_time': 0
        }
        
        # Переподключение
        self._reconnect_attempts = defaultdict(int)
        self._max_reconnect_attempts = 10
    
    async def start(self, streams: List[str]):
        """Запуск WebSocket подключений."""
        if not streams:
            logger.info("No streams provided, WebSocket not started")
            return
        
        await self.stop()  # Останавливаем существующие подключения
        
        self._running = True
        self._current_streams = set(streams)
        
        # Создаем HTTP сессию
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.connection_timeout)
        )
        
        # Разбиваем стримы на чанки
        stream_chunks = self._chunk_streams(streams)
        
        # Создаем подключения
        self._connection_tasks = [
            asyncio.create_task(self._maintain_connection(i, chunk))
            for i, chunk in enumerate(stream_chunks)
        ]
        
        self._stats['connections'] = len(self._connection_tasks)
        logger.info(f"Started WebSocket manager with {len(stream_chunks)} connections ({len(streams)} streams)")
    
    async def stop(self):
        """Остановка всех WebSocket подключений."""
        self._running = False
        
        # Останавливаем задачи
        for task in self._connection_tasks:
            task.cancel()
        
        if self._connection_tasks:
            await asyncio.gather(*self._connection_tasks, return_exceptions=True)
        
        self._connection_tasks.clear()
        
        # Закрываем сессию
        if self._session:
            await self._session.close()
            self._session = None
        
        self._current_streams.clear()
        logger.info("WebSocket manager stopped")
    
    async def update_streams(self, new_streams: List[str]):
        """Обновление списка стримов."""
        new_streams_set = set(new_streams)
        
        # Проверяем нужно ли обновление
        if new_streams_set == self._current_streams:
            return
        
        logger.info(f"Updating streams: {len(self._current_streams)} -> {len(new_streams_set)}")
        
        # Перезапускаем с новыми стримами
        if new_streams_set:
            await self.start(new_streams)
        else:
            await self.stop()
    
    def _chunk_streams(self, streams: List[str]) -> List[List[str]]:
        """Разбивка стримов на чанки."""
        chunks = []
        for i in range(0, len(streams), self.max_streams_per_connection):
            chunk = streams[i:i + self.max_streams_per_connection]
            chunks.append(chunk)
        return chunks
    
    async def _maintain_connection(self, connection_id: int, streams: List[str]):
        """Поддержание одного WebSocket подключения."""
        url = f"{self.base_url}{'/'.join(streams)}"
        
        while self._running:
            try:
                await self._connect_and_listen(connection_id, url)
                
                # Сбрасываем счетчик попыток при успешном подключении
                self._reconnect_attempts[connection_id] = 0
                
            except Exception as e:
                if not self._running:
                    break
                
                self._stats['errors'] += 1
                attempts = self._reconnect_attempts[connection_id]
                
                if attempts >= self._max_reconnect_attempts:
                    logger.error(f"Connection {connection_id}: Max reconnect attempts reached")
                    break
                
                # Экспоненциальная задержка
                delay = min(self.reconnect_delay * (2 ** attempts), 300)
                logger.warning(f"Connection {connection_id} error: {e}. Reconnecting in {delay}s...")
                
                self._reconnect_attempts[connection_id] += 1
                await asyncio.sleep(delay)
    
    async def _connect_and_listen(self, connection_id: int, url: str):
        """Подключение и прослушивание WebSocket."""
        if not self._session:
            raise RuntimeError("HTTP session not initialized")
        
        try:
            async with self._session.ws_connect(url) as ws:
                logger.info(f"Connection {connection_id}: Connected ({len(url.split('/')[-1].split('/'))} streams)")
                self._stats['reconnects'] += 1
                
                async for msg in ws:
                    if not self._running:
                        break
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"Connection {connection_id}: WebSocket error: {ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logger.warning(f"Connection {connection_id}: WebSocket closed by server")
                        break
                        
        except aiohttp.ClientError as e:
            raise ConnectionError(f"WebSocket connection failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected WebSocket error: {e}")
    
    async def _handle_message(self, message: str):
        """Обработка WebSocket сообщения."""
        try:
            self._stats['messages_received'] += 1
            self._stats['last_message_time'] = time.time()
            
            # Парсим JSON
            data = orjson.loads(message)
            
            # Проверяем что это kline данные
            if 'data' not in data or 'k' not in data['data']:
                return
            
            kline = data['data']['k']
            
            # Обрабатываем только закрытые свечи
            if not kline.get('x', False):
                return
            
            # Формируем данные свечи
            candle_data = {
                'symbol': kline['s'],
                'interval': kline['i'],
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c']),
                'volume': float(kline['v']),
                'is_closed': kline['x']
            }
            
            # Передаем в обработчик
            await self.message_callback(candle_data)
            
        except orjson.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            self._stats['errors'] += 1
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Data parsing error: {e}")
            self._stats['errors'] += 1
        except Exception as e:
            logger.error(f"Message handling error: {e}")
            self._stats['errors'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        stats = self._stats.copy()
        stats.update({
            'running': self._running,
            'active_connections': len([t for t in self._connection_tasks if not t.done()]),
            'total_streams': len(self._current_streams),
            'session_active': self._session is not None
        })
        return stats
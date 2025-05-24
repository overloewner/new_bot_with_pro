# shared/database/manager.py
"""Улучшенный менеджер базы данных для модульной архитектуры."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool
from sqlalchemy import text  # ДОБАВЛЕНО: для правильного SQL
import logging

from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер базы данных с пулом соединений."""
    
    def __init__(self, database_url: str):
        """Инициализация менеджера БД."""
        self.database_url = self._prepare_url(database_url)
        
        # Создаем движок с настройками для модульной архитектуры
        self.engine = create_async_engine(
            self.database_url,
            pool_size=20,           # Увеличиваем пул для множественных модулей
            max_overflow=30,        # Больше соединений для пиковой нагрузки
            pool_pre_ping=True,     # Проверка соединений
            pool_recycle=3600,      # Пересоздание соединений каждый час
            echo=False,             # Установите True для отладки SQL
            # Для модульной архитектуры важно правильно настроить пул
            connect_args={
                "server_settings": {
                    "client_encoding": "utf8",
                    "application_name": "crypto_bot_modular"
                },
                "command_timeout": 60
            }
        )
        
        # Создаем фабрику сессий
        self.async_session = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
        
        # Статистика соединений
        self._connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0
        }
    
    def _prepare_url(self, url: str) -> str:
        """Подготовка URL для asyncpg."""
        clean_url = url.split('?')[0]
        
        if clean_url.startswith('postgresql://'):
            return clean_url.replace('postgresql://', 'postgresql+asyncpg://')
        elif clean_url.startswith('postgres://'):
            return clean_url.replace('postgres://', 'postgresql+asyncpg://')
        
        return clean_url
    
    async def initialize(self) -> None:
        """Инициализация базы данных."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database initialized successfully")
        except SQLAlchemyError as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Контекстный менеджер для получения сессии БД."""
        session = self.async_session()
        self._connection_stats["active_connections"] += 1
        self._connection_stats["total_connections"] += 1
        
        try:
            yield session
        except SQLAlchemyError as e:
            await session.rollback()
            self._connection_stats["failed_connections"] += 1
            logger.error(f"Database session error: {e}")
            raise
        except Exception as e:
            await session.rollback()
            self._connection_stats["failed_connections"] += 1
            logger.error(f"Unexpected session error: {e}")
            raise
        finally:
            await session.close()
            self._connection_stats["active_connections"] -= 1
    
    async def health_check(self) -> bool:
        """Проверка здоровья соединения с БД."""
        try:
            async with self.get_session() as session:
                # ИСПРАВЛЕНО: Используем text() для SQL запроса
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Закрытие соединений с базой данных."""
        try:
            await self.engine.dispose()
            logger.info("📊 Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики базы данных."""
        pool = self.engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid(),
            "connection_stats": self._connection_stats.copy()
        }
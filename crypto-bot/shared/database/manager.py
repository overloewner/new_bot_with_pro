# core/database/manager.py
"""Упрощенный менеджер базы данных."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import logging

from .models import Base

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных."""
    
    def __init__(self, database_url: str):
        """Инициализация менеджера БД."""
        self.database_url = self._prepare_url(database_url)
        
        # Создаем движок
        self.engine = create_async_engine(
            self.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
            connect_args={
                "server_settings": {
                    "client_encoding": "utf8",
                    "application_name": "crypto_bot"
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
        
        try:
            yield session
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Unexpected session error: {e}")
            raise
        finally:
            await session.close()
    
    async def health_check(self) -> bool:
        """Проверка здоровья соединения с БД."""
        try:
            async with self.get_session() as session:
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
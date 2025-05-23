"""SQLAlchemy модели для базы данных."""

from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class User(Base):
    """Модель пользователя."""
    __tablename__ = 'users'
    
    user_id = Column(BigInteger, primary_key=True, index=True)
    is_running = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Статистика
    total_alerts_sent = Column(Integer, default=0)
    last_activity = Column(DateTime(timezone=True))
    
    def __repr__(self):
        return f"<User(user_id={self.user_id}, is_running={self.is_running})>"


class Preset(Base):
    """Модель пресета."""
    __tablename__ = 'presets'
    
    preset_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    preset_name = Column(String(100), nullable=False)
    pairs = Column(JSONB, nullable=False)  # Список торговых пар
    interval = Column(String(10), nullable=False)  # Таймфрейм
    percent = Column(Float, nullable=False)  # Процент изменения
    is_active = Column(Boolean, nullable=False, default=False)
    
    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Статистика
    alerts_triggered = Column(Integer, default=0)
    last_alert = Column(DateTime(timezone=True))
    
    def __repr__(self):
        return f"<Preset(preset_id={self.preset_id}, name={self.preset_name}, active={self.is_active})>"


class AlertLog(Base):
    """Лог отправленных алертов."""
    __tablename__ = 'alert_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    preset_id = Column(UUID(as_uuid=True), ForeignKey('presets.preset_id', ondelete='CASCADE'), nullable=True)
    
    symbol = Column(String(20), nullable=False)
    interval = Column(String(10), nullable=False)
    price_change = Column(Float, nullable=False)
    open_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    
    message_text = Column(Text)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    def __repr__(self):
        return f"<AlertLog(symbol={self.symbol}, change={self.price_change}%)>"


class SystemStats(Base):
    """Системная статистика."""
    __tablename__ = 'system_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Статистика пользователей
    total_users = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    
    # Статистика пресетов
    total_presets = Column(Integer, default=0)
    active_presets = Column(Integer, default=0)
    
    # Статистика сообщений
    alerts_sent_hour = Column(Integer, default=0)
    alerts_sent_day = Column(Integer, default=0)
    
    # Статистика WebSocket
    ws_connections = Column(Integer, default=0)
    ws_streams = Column(Integer, default=0)
    
    # Статистика очередей
    candle_queue_size = Column(Integer, default=0)
    alert_queue_size = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<SystemStats(timestamp={self.timestamp}, users={self.active_users})>"


class TokenCache(Base):
    """Кеш информации о токенах."""
    __tablename__ = 'token_cache'
    
    symbol = Column(String(20), primary_key=True)
    quote_volume = Column(Float, nullable=False)
    price_change_percent = Column(Float)
    last_price = Column(Float)
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<TokenCache(symbol={self.symbol}, volume={self.quote_volume})>"
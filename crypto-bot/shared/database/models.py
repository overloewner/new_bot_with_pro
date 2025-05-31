# core/database/models.py
"""Модели базы данных для всех модулей."""

from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class User(Base):
    """Базовая модель пользователя."""
    __tablename__ = 'users'
    
    user_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Общие настройки
    notification_enabled = Column(Boolean, nullable=False, default=True)
    language_code = Column(String(10), nullable=False, default='ru')
    
    # Статистика
    total_alerts_received = Column(Integer, default=0)
    last_activity = Column(DateTime(timezone=True))
    
    def __repr__(self):
        return f"<User(user_id={self.user_id}, username={self.username})>"

class PricePreset(Base):
    """Модель пресета ценовых алертов."""
    __tablename__ = 'price_presets'
    
    preset_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    preset_name = Column(String(100), nullable=False)
    pairs = Column(JSONB, nullable=False)
    interval = Column(String(10), nullable=False)
    percent = Column(Float, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Статистика
    alerts_triggered = Column(Integer, default=0)
    last_alert = Column(DateTime(timezone=True))
    
    __table_args__ = (
        Index('idx_price_presets_user_active', 'user_id', 'is_active'),
        Index('idx_price_presets_active', 'is_active'),
        {'extend_existing': True}
    )

class GasAlert(Base):
    """Модель алерта газа."""
    __tablename__ = 'gas_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    threshold_gwei = Column(Float, nullable=False)
    alert_type = Column(String(20), nullable=False, default='below')
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_triggered = Column(DateTime(timezone=True))
    times_triggered = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_gas_alerts_user_active', 'user_id', 'is_active'),
        {'extend_existing': True}
    )

class WhaleAlert(Base):
    """Модель алерта китов."""
    __tablename__ = 'whale_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    threshold_usd = Column(Float, nullable=True)
    threshold_btc = Column(Float, nullable=True)
    token_filter = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_triggered = Column(DateTime(timezone=True))
    times_triggered = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_whale_alerts_user_active', 'user_id', 'is_active'),
        {'extend_existing': True}
    )

class WalletAlert(Base):
    """Модель алерта кошелька."""
    __tablename__ = 'wallet_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    wallet_address = Column(String(42), nullable=False, index=True)
    min_value_eth = Column(BigInteger, nullable=True)
    track_incoming = Column(Boolean, nullable=False, default=True)
    track_outgoing = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_checked_block = Column(BigInteger, nullable=True)
    last_triggered = Column(DateTime(timezone=True))
    times_triggered = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_wallet_alerts_user_active', 'user_id', 'is_active'),
        Index('idx_wallet_alerts_address', 'wallet_address'),
        {'extend_existing': True}
    )

class AlertLog(Base):
    """Общий лог всех алертов."""
    __tablename__ = 'alert_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    module_name = Column(String(50), nullable=False)
    alert_type = Column(String(50), nullable=False)
    alert_data = Column(JSONB, nullable=True)
    message_text = Column(Text, nullable=True)
    
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    delivery_status = Column(String(20), nullable=False, default='sent')
    
    __table_args__ = (
        Index('idx_alert_logs_user_module', 'user_id', 'module_name'),
        Index('idx_alert_logs_sent_at', 'sent_at'),
        {'extend_existing': True}
    )
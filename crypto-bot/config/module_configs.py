# config/module_configs.py  
"""Конфигурации для отдельных модулей."""

from dataclasses import dataclass


@dataclass
class GasTrackerConfig:
    """Конфигурация Gas Tracker."""
    update_interval: int = 30  # секунд
    max_alerts_per_user: int = 5
    cooldown_minutes: int = 5


@dataclass 
class WhaleTrackerConfig:
    """Конфигурация Whale Tracker."""
    min_transaction_eth: float = 100.0
    update_interval: int = 30  # секунд
    max_alerts_per_user: int = 10
    api_rate_limit: int = 5  # запросов в секунду


@dataclass
class WalletTrackerConfig:
    """Конфигурация Wallet Tracker."""
    max_wallets_per_user: int = 5
    check_interval: int = 180  # секунд (3 минуты)
    cooldown_minutes: int = 5
    
    
@dataclass
class PriceAlertsConfig:
    """Конфигурация Price Alerts."""
    max_presets_per_user: int = 20
    max_pairs_per_preset: int = 500
    websocket_reconnect_delay: int = 5
    batch_size: int = 500
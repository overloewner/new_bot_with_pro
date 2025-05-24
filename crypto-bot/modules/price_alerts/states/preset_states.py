# modules/price_alerts/states/preset_states.py
"""Состояния для создания пресетов."""

from aiogram.fsm.state import State, StatesGroup


class PresetStates(StatesGroup):
    """Состояния для создания пресетов."""
    waiting_preset_name = State()
    waiting_pairs = State()
    waiting_volume_input = State()
    waiting_interval = State()
    waiting_percent = State()
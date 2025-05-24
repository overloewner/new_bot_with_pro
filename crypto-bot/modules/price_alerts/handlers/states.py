# modules/price_alerts/handlers/states.py
"""FSM состояния для price_alerts."""

from aiogram.fsm.state import State, StatesGroup


class PresetStates(StatesGroup):
    """Состояния для создания пресета."""
    waiting_name = State()
    waiting_pairs = State()
    waiting_interval = State()
    waiting_percent = State()
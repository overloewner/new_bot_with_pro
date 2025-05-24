# modules/gas_tracker/handlers/gas_handlers.py
"""Обработчики команд для газ трекера."""

from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED


class GasStates(StatesGroup):
    """Состояния для настройки газ алертов."""
    waiting_threshold = State()
    waiting_alert_type = State()


class GasHandlers:
    """Обработчики команд газ трекера."""
    
    def __init__(self, gas_service):
        self.gas_service = gas_service
    
    async def show_gas_menu(self, callback: types.CallbackQuery):
        """Показ меню газ трекера."""
        current_gas = self.gas_service.get_current_gas_price()
        user_alerts = self.gas_service.get_user_alerts(callback.from_user.id)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Текущие цены", callback_data="gas_current")
        builder.button(text="🔔 Мои алерты", callback_data="gas_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        text = "⛽ Газ Трекер\n\n"
        
        if current_gas:
            text += (
                f"Текущие цены:\n"
                f"🟢 Безопасный: {current_gas['safe']:.1f} gwei\n"
                f"🟡 Стандартный: {current_gas['standard']:.1f} gwei\n"
                f"🟠 Быстрый: {current_gas['fast']:.1f} gwei\n"
                f"🔴 Мгновенный: {current_gas['instant']:.1f} gwei\n\n"
            )
        else:
            text += "❌ Данные о газе недоступны\n\n"
        
        text += f"Активных алертов: {len([a for a in user_alerts if a['is_active']])}"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def show_current_gas(self, callback: types.CallbackQuery):
        """Показ текущих цен на газ."""
        current_gas = self.gas_service.get_current_gas_price()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="gas_current")
        builder.button(text="◀️ Назад", callback_data="gas_menu")
        builder.adjust(1)
        
        if current_gas:
            from datetime import datetime
            updated = datetime.fromisoformat(current_gas['timestamp'])
            
            text = (
                f"⛽ Текущие цены на газ\n\n"
                f"🟢 Безопасный: {current_gas['safe']:.1f} gwei\n"
                f"🟡 Стандартный: {current_gas['standard']:.1f} gwei\n"
                f"🟠 Быстрый: {current_gas['fast']:.1f} gwei\n"
                f"🔴 Мгновенный: {current_gas['instant']:.1f} gwei\n\n"
                f"🕐 Обновлено: {updated.strftime('%H:%M:%S')}"
            )
        else:
            text = "❌ Данные о газе недоступны"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def add_gas_alert_start(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало добавления газ алерта."""
        await state.set_state(GasStates.waiting_threshold)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="gas_menu")
        
        await callback.message.edit_text(
            "🔔 Добавление газ алерта\n\n"
            "Введите пороговое значение в gwei (1-500):\n"
            "Например: 20",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    
    async def process_gas_threshold(self, message: types.Message, state: FSMContext):
        """Обработка порогового значения."""
        try:
            threshold = float(message.text.strip())
            
            if threshold <= 0 or threshold > 500:
                await message.answer("❌ Введите значение от 1 до 500 gwei")
                return
            
            await state.update_data(threshold=threshold)
            await state.set_state(GasStates.waiting_alert_type)
            
            builder = InlineKeyboardBuilder()
            builder.button(text="⬇️ Ниже порога", callback_data="gas_type_below")
            builder.button(text="⬆️ Выше порога", callback_data="gas_type_above")
            builder.button(text="❌ Отмена", callback_data="gas_menu")
            builder.adjust(1)
            
            await message.answer(
                f"Порог установлен: {threshold:.1f} gwei\n\n"
                "Когда отправлять алерт?",
                reply_markup=builder.as_markup()
            )
            
        except ValueError:
            await message.answer("❌ Введите корректное число")
    
    async def process_alert_type(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка типа алерта."""
        alert_type = callback.data.split("_")[-1]  # below или above
        data = await state.get_data()
        threshold = data.get("threshold")
        
        success = await self.gas_service.add_user_alert(
            callback.from_user.id,
            threshold,
            alert_type
        )
        
        if success:
            direction = "ниже" if alert_type == "below" else "выше"
            text = f"✅ Алерт добавлен!\nУведомление при цене {direction} {threshold:.1f} gwei"
        else:
            text = "❌ Ошибка при добавлении алерта"
        
        await state.clear()
        
        # Возвращаемся в меню газа
        await self.show_gas_menu(callback)
        
        # Отправляем уведомление
        await callback.message.answer(text)

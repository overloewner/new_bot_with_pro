"""Обработчики команд для отслеживания китов."""

from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED


class WhaleStates(StatesGroup):
    """Состояния для настройки алертов китов."""
    waiting_threshold_type = State()
    waiting_threshold_value = State()


class WhaleHandlers:
    """Обработчики команд отслеживания китов."""
    
    def __init__(self, whale_service):
        self.whale_service = whale_service
    
    async def show_whale_menu(self, callback: types.CallbackQuery):
        """Показ меню отслеживания китов."""
        user_alerts = self.whale_service.get_user_alerts(callback.from_user.id)
        limitations = self.whale_service.get_limitations_info()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="ℹ️ Ограничения", callback_data="whale_limitations")
        builder.button(text="🔔 Мои алерты", callback_data="whale_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="whale_add_alert")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        text = (
            "🐋 Whale Tracker (Ограниченная версия)\n\n"
            f"Активных алертов: {len([a for a in user_alerts if a['is_active']])}\n\n"
            "⚠️ Использует только бесплатные API\n"
            "Нажмите 'Ограничения' для подробностей"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def show_limitations(self, callback: types.CallbackQuery):
        """Показ ограничений сервиса."""
        limitations = self.whale_service.get_limitations_info()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="whale_menu")
        
        text = f"⚠️ {limitations['title']}\n\n"
        
        text += "🚫 Текущие ограничения:\n"
        for limit in limitations['limitations']:
            text += f"{limit}\n"
        
        text += "\n✅ Что работает:\n"
        for work in limitations['what_works']:
            text += f"{work}\n"
        
        text += "\n💰 Для полного функционала нужны:\n"
        for req in limitations['for_full_functionality']:
            text += f"{req}\n"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def add_whale_alert_start(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало добавления алерта китов."""
        await state.set_state(WhaleStates.waiting_threshold_type)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💵 В долларах USD", callback_data="whale_threshold_usd")
        builder.button(text="₿ В биткоинах BTC", callback_data="whale_threshold_btc")
        builder.button(text="❌ Отмена", callback_data="whale_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "🐋 Добавление алерта китов\n\n"
            "В какой валюте установить порог?",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    
    async def process_threshold_type(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка типа порога."""
        threshold_type = callback.data.split("_")[-1]  # usd или btc
        await state.update_data(threshold_type=threshold_type)
        await state.set_state(WhaleStates.waiting_threshold_value)
        
        if threshold_type == "usd":
            text = (
                "💵 Порог в долларах\n\n"
                "Введите минимальную сумму в USD:\n"
                "Например: 1000000 (для транзакций > $1M)\n"
                "Диапазон: $1,000 - $100,000,000"
            )
        else:
            text = (
                "₿ Порог в биткоинах\n\n"
                "Введите минимальную сумму в BTC:\n"
                "Например: 10 (для транзакций > 10 BTC)\n"
                "Диапазон: 0.1 - 10,000 BTC"
            )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="whale_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def process_threshold_value(self, message: types.Message, state: FSMContext):
        """Обработка значения порога."""
        try:
            data = await state.get_data()
            threshold_type = data.get("threshold_type")
            threshold_value = float(message.text.strip())
            
            # Валидация
            if threshold_type == "usd":
                if threshold_value < 1000 or threshold_value > 100000000:
                    await message.answer("❌ Введите значение от $1,000 до $100,000,000")
                    return
                
                success = await self.whale_service.add_user_alert(
                    message.from_user.id,
                    threshold_usd=threshold_value
                )
                
                if success:
                    text = f"✅ Алерт добавлен!\nУведомления о транзакциях > ${threshold_value:,.0f}"
                else:
                    text = "❌ Ошибка при добавлении алерта"
                    
            else:  # btc
                if threshold_value < 0.1 or threshold_value > 10000:
                    await message.answer("❌ Введите значение от 0.1 до 10,000 BTC")
                    return
                
                success = await self.whale_service.add_user_alert(
                    message.from_user.id,
                    threshold_btc=threshold_value
                )
                
                if success:
                    text = f"✅ Алерт добавлен!\nУведомления о транзакциях > {threshold_value} BTC"
                else:
                    text = "❌ Ошибка при добавлении алерта"
            
            await state.clear()
            await message.answer(text)
            
        except ValueError:
            await message.answer("❌ Введите корректное число")


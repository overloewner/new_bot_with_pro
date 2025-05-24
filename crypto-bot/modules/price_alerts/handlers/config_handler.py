# modules/price_alerts/handlers/config_handler.py
"""Обработчик настроек ценовых алертов."""

from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from shared.events import event_bus, Event


class ConfigHandler:
    """Обработчик настроек пресетов и конфигурации."""
    
    def register_handlers(self, router):
        """Регистрация обработчиков."""
        router.message(F.text == "Настройка конфигов")(self.config_menu)
        router.callback_query(F.data == "active_presets")(self.show_active_presets)
        router.callback_query(F.data == "inactive_presets")(self.show_inactive_presets)
        router.callback_query(F.data == "back_to_config")(self.back_to_config)
        router.callback_query(F.data == "back_to_main")(self.back_to_main)
    
    async def config_menu(self, message: types.Message):
        """Главное меню настроек."""
        try:
            # Запрашиваем данные пользователя через события
            await event_bus.publish(Event(
                type="price_alerts.get_user_data",
                data={"user_id": message.from_user.id},
                source_module="telegram"
            ))
            
            # TODO: Ждем ответ и показываем меню
            await self._send_config_menu(message)
            
        except Exception as e:
            await message.answer("❌ Ошибка при загрузке настроек")
    
    async def show_active_presets(self, callback: types.CallbackQuery):
        """Показ активных пресетов."""
        try:
            await event_bus.publish(Event(
                type="price_alerts.get_active_presets",
                data={"user_id": callback.from_user.id},
                source_module="telegram"
            ))
            
            # TODO: Ждем ответ и показываем список
            
            builder = InlineKeyboardBuilder()
            builder.button(text="◀️ Назад", callback_data="back_to_config")
            
            await callback.message.edit_text(
                "🟢 Активные пресеты:\n\nЗагрузка...",
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            
        except Exception as e:
            await callback.answer("Ошибка при загрузке пресетов")
    
    async def show_inactive_presets(self, callback: types.CallbackQuery):
        """Показ неактивных пресетов."""
        try:
            await event_bus.publish(Event(
                type="price_alerts.get_inactive_presets",
                data={"user_id": callback.from_user.id},
                source_module="telegram"
            ))
            
            builder = InlineKeyboardBuilder()
            builder.button(text="◀️ Назад", callback_data="back_to_config")
            
            await callback.message.edit_text(
                "🔴 Неактивные пресеты:\n\nЗагрузка...",
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            
        except Exception as e:
            await callback.answer("Ошибка при загрузке пресетов")
    
    async def back_to_config(self, callback: types.CallbackQuery):
        """Возврат к меню настроек."""
        try:
            await self._send_config_menu_edit(callback)
        except Exception as e:
            await callback.answer("Ошибка")
    
    async def back_to_main(self, callback: types.CallbackQuery):
        """Возврат к главному меню."""
        try:
            await callback.message.delete()
            
            await event_bus.publish(Event(
                type="telegram.show_main_menu",
                data={"user_id": callback.from_user.id},
                source_module="price_alerts"
            ))
            
            await callback.answer()
            
        except Exception as e:
            await callback.answer("Ошибка")
    
    async def _send_config_menu(self, message: types.Message):
        """Отправка меню настроек."""
        builder = InlineKeyboardBuilder()
        builder.button(text="🟢 Активные пресеты", callback_data="active_presets")
        builder.button(text="🔴 Неактивные пресеты", callback_data="inactive_presets")
        builder.button(text="➕ Добавить пресет", callback_data="add_preset")
        builder.button(text="◀️ Назад", callback_data="back_to_main")
        builder.adjust(1)
        
        await message.answer(
            "⚙️ Настройка ценовых алертов:\n\n"
            "Выберите действие для управления пресетами:",
            reply_markup=builder.as_markup()
        )
    
    async def _send_config_menu_edit(self, callback: types.CallbackQuery):
        """Редактирование сообщения с меню настроек."""
        builder = InlineKeyboardBuilder()
        builder.button(text="🟢 Активные пресеты", callback_data="active_presets")
        builder.button(text="🔴 Неактивные пресеты", callback_data="inactive_presets")
        builder.button(text="➕ Добавить пресет", callback_data="add_preset")
        builder.button(text="◀️ Назад", callback_data="back_to_main")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "⚙️ Настройка ценовых алертов:\n\n"
            "Выберите действие для управления пресетами:",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
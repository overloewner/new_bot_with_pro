"""Обработчик настроек и конфигурации."""

from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.base import BaseHandler
from bot.core.exceptions import DatabaseError


class ConfigHandler(BaseHandler):
    """Обработчик настроек пресетов и конфигурации."""
    
    def _setup_handlers(self):
        """Настройка обработчиков."""
        self.router.message(F.text == "Настройка конфигов")(self.config_menu)
        self.router.callback_query(F.data == "active_presets")(self.show_active_presets)
        self.router.callback_query(F.data == "inactive_presets")(self.show_inactive_presets)
        self.router.callback_query(F.data == "back_to_config")(self.back_to_config)
        self.router.callback_query(F.data == "back_to_main")(self.back_to_main)
        self.router.callback_query(F.data == "back_to_presets")(self.back_to_presets)
    
    async def config_menu(self, message: types.Message):
        """Главное меню настроек."""
        try:
            user_data = await self.storage.get_user_data(message.from_user.id)
            
            if user_data.get("is_running", False):
                await message.answer("❌ Настройки недоступны, пока бот запущен")
                return
            
            await self._send_config_menu(message)
            
        except DatabaseError as e:
            await self._handle_error(e, "config menu")
            await self._send_error_message(message)
        except Exception as e:
            await self._handle_error(e, "config menu")
            await self._send_error_message(message)
    
    async def show_active_presets(self, callback: types.CallbackQuery):
        """Показ активных пресетов."""
        try:
            user_data = await self.storage.get_user_data(callback.from_user.id)
            active_presets = user_data.get("active_presets", set())
            
            builder = InlineKeyboardBuilder()
            
            if not active_presets:
                builder.button(text="◀️ Назад", callback_data="back_to_config")
                await callback.message.edit_text(
                    "📋 У вас нет активных пресетов",
                    reply_markup=builder.as_markup()
                )
                await callback.answer()
                return
            
            # Добавляем кнопки для каждого активного пресета
            for preset_id in active_presets:
                preset = user_data["presets"].get(preset_id)
                if preset:
                    builder.button(
                        text=f"🟢 {preset['preset_name']}",
                        callback_data=f"view_active_{preset_id}"
                    )
            
            builder.button(text="◀️ Назад", callback_data="back_to_config")
            builder.adjust(1)
            
            await callback.message.edit_text(
                f"🟢 Активные пресеты ({len(active_presets)}):",
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            
        except DatabaseError as e:
            await self._handle_error(e, "show active presets")
            await callback.answer("Ошибка при загрузке пресетов")
        except Exception as e:
            await self._handle_error(e, "show active presets")
            await callback.answer("Ошибка")
    
    async def show_inactive_presets(self, callback: types.CallbackQuery):
        """Показ неактивных пресетов."""
        try:
            user_data = await self.storage.get_user_data(callback.from_user.id)
            all_presets = set(user_data.get("presets", {}).keys())
            active_presets = user_data.get("active_presets", set())
            inactive_presets = all_presets - active_presets
            
            builder = InlineKeyboardBuilder()
            
            if not inactive_presets:
                builder.button(text="◀️ Назад", callback_data="back_to_config")
                await callback.message.edit_text(
                    "📋 У вас нет неактивных пресетов",
                    reply_markup=builder.as_markup()
                )
                await callback.answer()
                return
            
            # Добавляем кнопки для каждого неактивного пресета
            for preset_id in inactive_presets:
                preset = user_data["presets"].get(preset_id)
                if preset:
                    builder.button(
                        text=f"🔴 {preset['preset_name']}",
                        callback_data=f"view_inactive_{preset_id}"
                    )
            
            builder.button(text="◀️ Назад", callback_data="back_to_config")
            builder.adjust(1)
            
            await callback.message.edit_text(
                f"🔴 Неактивные пресеты ({len(inactive_presets)}):",
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            
        except DatabaseError as e:
            await self._handle_error(e, "show inactive presets")
            await callback.answer("Ошибка при загрузке пресетов")
        except Exception as e:
            await self._handle_error(e, "show inactive presets")
            await callback.answer("Ошибка")
    
    async def back_to_config(self, callback: types.CallbackQuery):
        """Возврат к меню настроек."""
        try:
            await self._send_config_menu_edit(callback)
        except Exception as e:
            await self._handle_error(e, "back to config")
            await callback.answer("Ошибка")
    
    async def back_to_main(self, callback: types.CallbackQuery):
        """Возврат к главному меню."""
        try:
            await callback.message.delete()
            
            # Импортируем здесь, чтобы избежать циклического импорта
            from bot.handlers.start_handler import StartHandler
            start_handler = StartHandler(self.storage)
            
            # Создаем фиктивное сообщение для вызова start
            class FakeMessage:
                def __init__(self, user_id, answer_func):
                    self.from_user = types.User(id=user_id, is_bot=False, first_name="User")
                    self.answer = answer_func
            
            fake_message = FakeMessage(callback.from_user.id, callback.message.answer)
            await start_handler.cmd_start(fake_message)
            
            await callback.answer()
            
        except Exception as e:
            await self._handle_error(e, "back to main")
            await callback.answer("Ошибка")
    
    async def back_to_presets(self, callback: types.CallbackQuery):
        """Возврат к списку пресетов."""
        try:
            # Определяем, откуда пришел пользователь по тексту сообщения
            message_text = callback.message.text or ""
            
            if "Активные пресеты" in message_text:
                await self.show_active_presets(callback)
            elif "Неактивные пресеты" in message_text:
                await self.show_inactive_presets(callback)
            else:
                await self._send_config_menu_edit(callback)
                
        except Exception as e:
            await self._handle_error(e, "back to presets")
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
            "⚙️ Настройка конфигов:\n\n"
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
            "⚙️ Настройка конфигов:\n\n"
            "Выберите действие для управления пресетами:",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
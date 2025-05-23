"""Обработчик стартовых команд."""

from aiogram import types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.handlers.base import BaseHandler
from bot.core.exceptions import DatabaseError


class StartHandler(BaseHandler):
    """Обработчик команды /start и основного меню."""
    
    def _setup_handlers(self):
        """Настройка обработчиков."""
        self.router.message(Command("start"))(self.cmd_start)
        self.router.message(F.text == "Запустить")(self.start_bot)
        self.router.message(F.text == "Приостановить")(self.pause_bot)
    
    async def cmd_start(self, message: types.Message):
        """Обработка команды /start."""
        try:
            user_data = await self.storage.get_user_data(message.from_user.id)
            await self._send_main_menu(message, user_data)
        except DatabaseError as e:
            await self._handle_error(e, "start command")
            await self._send_error_message(message)
        except Exception as e:
            await self._handle_error(e, "start command")
            await self._send_error_message(message)
    
    async def start_bot(self, message: types.Message):
        """Запуск бота для пользователя."""
        try:
            user_id = message.from_user.id
            user_data = await self.storage.get_user_data(user_id)
            
            if not user_data["active_presets"]:
                await message.answer("❌ Нет активных пресетов для запуска")
                return
            
            # Удаляем старые подписки
            await self.storage.remove_user_subscriptions(user_id)
            
            # Добавляем новые подписки
            added = await self._add_user_subscriptions(user_id, user_data)
            
            # Обновляем статус
            await self.storage.update_user_running_status(user_id, True)
            
            await message.answer(f"✅ Бот запущен! Добавлено {added} подписок.")
            
            # Обновляем меню
            user_data = await self.storage.get_user_data(user_id)
            await self._send_main_menu(message, user_data)
            
        except DatabaseError as e:
            await self._handle_error(e, "start bot")
            await self._send_error_message(message, "Ошибка при запуске бота")
        except Exception as e:
            await self._handle_error(e, "start bot")
            await self._send_error_message(message)
    
    async def pause_bot(self, message: types.Message):
        """Приостановка бота для пользователя."""
        try:
            user_id = message.from_user.id
            
            # Удаляем подписки
            removed = await self.storage.remove_user_subscriptions(user_id)
            
            # Обновляем статус
            await self.storage.update_user_running_status(user_id, False)
            
            await message.answer(f"⏸️ Бот приостановлен! Удалено {removed} подписок.")
            
            # Обновляем меню
            user_data = await self.storage.get_user_data(user_id)
            await self._send_main_menu(message, user_data)
            
        except DatabaseError as e:
            await self._handle_error(e, "pause bot")
            await self._send_error_message(message, "Ошибка при приостановке бота")
        except Exception as e:
            await self._handle_error(e, "pause bot")
            await self._send_error_message(message)
    
    async def _send_main_menu(self, message: types.Message, user_data: dict):
        """Отправка главного меню."""
        builder = ReplyKeyboardBuilder()
        
        if user_data.get("is_running", False):
            builder.button(text="Настройка конфигов (недоступно)")
            builder.button(text="Приостановить")
        else:
            builder.button(text="Настройка конфигов")
            builder.button(text="Запустить")
        
        builder.adjust(2)
        
        status = "🟢 Запущен" if user_data.get("is_running") else "🔴 Остановлен"
        active_presets = len(user_data.get("active_presets", set()))
        total_presets = len(user_data.get("presets", {}))
        
        text = (
            f"🤖 Крипто Алерт Бот\n\n"
            f"Статус: {status}\n"
            f"Активных пресетов: {active_presets}/{total_presets}\n\n"
            f"Выберите действие:"
        )
        
        await message.answer(
            text,
            reply_markup=builder.as_markup(resize_keyboard=True)
        )
    
    async def _add_user_subscriptions(self, user_id: int, user_data: dict) -> int:
        """Добавление подписок пользователя."""
        added_count = 0
        
        for preset_id in user_data["active_presets"]:
            preset = user_data["presets"].get(preset_id)
            if not preset:
                continue
            
            for pair in preset["pairs"]:
                key = f"{pair.lower()}@kline_{preset['interval']}"
                await self.storage.add_subscription(key, user_id, preset_id)
                added_count += 1
        
        return added_count
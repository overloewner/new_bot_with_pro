"""Обработчик управления пресетами."""

import uuid
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.base import BaseHandler
from bot.storage import PresetStates
from bot.core.exceptions import DatabaseError, ValidationError
from bot.utils.validators import PresetValidator, VolumeValidator


class PresetHandler(BaseHandler):
    """Обработчик создания и управления пресетами."""
    
    def _setup_handlers(self):
        """Настройка обработчиков."""
        # Callback обработчики
        self.router.callback_query(F.data == "add_preset")(self.add_preset)
        self.router.callback_query(F.data == "select_all_pairs")(self.select_all_pairs)
        self.router.callback_query(F.data == "select_by_volume")(self.select_by_volume)
        self.router.callback_query(F.data == "enter_manually")(self.enter_manually)
        self.router.callback_query(F.data.startswith("interval_"))(self.process_interval_callback)
        self.router.callback_query(F.data.startswith("activate_"))(self.activate_preset)
        self.router.callback_query(F.data.startswith("deactivate_"))(self.deactivate_preset)
        self.router.callback_query(F.data.startswith("delete_"))(self.delete_preset)
        self.router.callback_query(F.data.startswith("view_active_"))(self.view_active_preset)
        self.router.callback_query(F.data.startswith("view_inactive_"))(self.view_inactive_preset)
        
        # State обработчики
        self.router.message(PresetStates.waiting_preset_name)(self.process_preset_name)
        self.router.message(PresetStates.waiting_pairs)(self.process_pairs)
        self.router.message(PresetStates.waiting_volume_input)(self.process_volume_input)
        self.router.message(PresetStates.waiting_percent)(self.process_percent)
    
    async def add_preset(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало создания пресета."""
        try:
            await state.set_state(PresetStates.waiting_preset_name)
            await callback.message.edit_text(
                "📝 Введите название пресета:",
                reply_markup=None
            )
            await callback.answer()
        except Exception as e:
            await self._handle_error(e, "add preset")
            await callback.answer("Ошибка при создании пресета")
    
    async def process_preset_name(self, message: types.Message, state: FSMContext):
        """Обработка имени пресета."""
        try:
            # Валидируем имя
            preset_name = PresetValidator.validate_preset_name(message.text)
            
            await state.update_data(preset_name=preset_name)
            await state.set_state(PresetStates.waiting_pairs)
            
            builder = InlineKeyboardBuilder()
            builder.button(text="Выбрать все пары", callback_data="select_all_pairs")
            builder.button(text="Выбрать по объему", callback_data="select_by_volume")
            builder.button(text="Ввести названия пар вручную", callback_data="enter_manually")
            builder.adjust(1)
            
            await message.answer(
                "💰 Как вы хотите выбрать торговые пары?",
                reply_markup=builder.as_markup()
            )
            
        except ValidationError as e:
            await message.answer(f"❌ {str(e)}")
        except Exception as e:
            await self._handle_error(e, "process preset name")
            await self._send_error_message(message)
    
    async def select_all_pairs(self, callback: types.CallbackQuery, state: FSMContext):
        """Выбор всех доступных пар."""
        try:
            all_tokens = self.storage.get_all_tokens()
            await state.update_data(pairs=all_tokens)
            await self._show_interval_selection(callback, state)
            await callback.answer(f"Выбрано {len(all_tokens)} пар")
        except Exception as e:
            await self._handle_error(e, "select all pairs")
            await callback.answer("Ошибка при выборе пар")
    
    async def select_by_volume(self, callback: types.CallbackQuery, state: FSMContext):
        """Выбор пар по объему торгов."""
        try:
            await callback.message.answer(
                "📊 Введите минимальный объем торгов за 24ч (в USDT):\n"
                "Например: 1000000 - для пар с объемом > $1M"
            )
            await state.set_state(PresetStates.waiting_volume_input)
            await callback.answer()
        except Exception as e:
            await self._handle_error(e, "select by volume")
            await callback.answer("Ошибка")
    
    async def process_volume_input(self, message: types.Message, state: FSMContext):
        """Обработка ввода минимального объема."""
        try:
            # Валидируем объем
            min_volume = VolumeValidator.validate_volume(message.text)
            
            # Получаем пары по объему
            selected_pairs = await self.storage.get_tokens_by_volume(min_volume)
            
            if not selected_pairs:
                await message.answer(
                    f"❌ Нет пар с объемом выше {min_volume:,.0f} USDT. "
                    "Попробуйте ввести меньшее значение:"
                )
                return
            
            await state.update_data(pairs=selected_pairs)
            await message.answer(
                f"✅ Выбрано {len(selected_pairs)} пар с объемом > {min_volume:,.0f} USDT"
            )
            await self._show_interval_selection_message(message, state)
            
        except ValidationError as e:
            await message.answer(f"❌ {str(e)}")
        except Exception as e:
            await self._handle_error(e, "process volume input")
            await self._send_error_message(message)
    
    async def enter_manually(self, callback: types.CallbackQuery, state: FSMContext):
        """Ручной ввод торговых пар."""
        try:
            await callback.message.answer(
                "✏️ Введите торговые пары через запятую:\n"
                "Например: BTCUSDT, ETHUSDT, ADAUSDT"
            )
            await state.set_state(PresetStates.waiting_pairs)
            await callback.answer()
        except Exception as e:
            await self._handle_error(e, "enter manually")
            await callback.answer("Ошибка")
    
    async def process_pairs(self, message: types.Message, state: FSMContext):
        """Обработка ручного ввода пар."""
        try:
            # Парсим и валидируем пары
            pairs_input = [p.strip().upper() for p in message.text.split(",")]
            pairs = PresetValidator.validate_pairs(pairs_input)
            
            # Проверяем валидность пар
            invalid_pairs = []
            for pair in pairs:
                if not await self.storage.is_valid_token(pair):
                    invalid_pairs.append(pair)
            
            if invalid_pairs:
                await message.answer(
                    f"❌ Следующие пары не найдены: {', '.join(invalid_pairs)}\n"
                    "Пожалуйста, введите корректные пары:"
                )
                return
            
            await state.update_data(pairs=pairs)
            await message.answer(f"✅ Выбрано {len(pairs)} пар")
            await self._show_interval_selection_message(message, state)
            
        except ValidationError as e:
            await message.answer(f"❌ {str(e)}")
        except Exception as e:
            await self._handle_error(e, "process pairs")
            await self._send_error_message(message)
    
    async def _show_interval_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Показ выбора интервала через callback."""
        await state.set_state(PresetStates.waiting_interval)
        
        builder = InlineKeyboardBuilder()
        for tf in self.storage.get_all_timeframes():
            builder.button(text=tf, callback_data=f"interval_{tf}")
        builder.adjust(3)
        
        await callback.message.answer(
            "⏰ Выберите интервал свечи:",
            reply_markup=builder.as_markup()
        )
    
    async def _show_interval_selection_message(self, message: types.Message, state: FSMContext):
        """Показ выбора интервала через сообщение."""
        await state.set_state(PresetStates.waiting_interval)
        
        builder = InlineKeyboardBuilder()
        for tf in self.storage.get_all_timeframes():
            builder.button(text=tf, callback_data=f"interval_{tf}")
        builder.adjust(3)
        
        await message.answer(
            "⏰ Выберите интервал свечи:",
            reply_markup=builder.as_markup()
        )
    
    async def process_interval_callback(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора интервала."""
        try:
            interval = callback.data.split("_")[1]
            
            # Валидируем интервал
            interval = PresetValidator.validate_interval(interval)
            
            await state.update_data(interval=interval)
            await state.set_state(PresetStates.waiting_percent)
            
            await callback.message.answer(
                "📈 Введите процент изменения цены для алертов:\n"
                "Например: 5 (для алертов при изменении > 5%)\n"
                "Диапазон: 0.01% - 1000%"
            )
            await callback.answer(f"Выбран интервал: {interval}")
            
        except ValidationError as e:
            await callback.answer(f"Ошибка: {str(e)}")
        except Exception as e:
            await self._handle_error(e, "process interval")
            await callback.answer("Ошибка при выборе интервала")
    
    async def process_percent(self, message: types.Message, state: FSMContext):
        """Обработка ввода процента."""
        try:
            # Парсим и валидируем процент
            percent_text = message.text.strip().replace('%', '').replace(',', '.')
            percent = PresetValidator.validate_percent(float(percent_text))
            
            # Получаем данные из состояния
            data = await state.get_data()
            required_fields = ['preset_name', 'pairs', 'interval']
            
            if not all(k in data for k in required_fields):
                await message.answer("⚠️ Ошибка данных. Начните создание пресета заново.")
                await state.clear()
                return
            
            # Создаем пресет
            preset_id = str(uuid.uuid4())
            preset_data = {
                'preset_name': data['preset_name'],
                'pairs': data['pairs'],
                'interval': data['interval'],
                'percent': percent
            }
            
            await self.storage.add_preset(
                user_id=message.from_user.id,
                preset_id=preset_id,
                preset_data=preset_data
            )
            
            await message.answer(
                f"✅ Пресет '{preset_data['preset_name']}' создан!\n"
                f"🔧 Пар: {len(preset_data['pairs'])}\n"
                f"⏰ Интервал: {preset_data['interval']}\n"
                f"📈 Процент: {preset_data['percent']}%",
                reply_markup=types.ReplyKeyboardRemove()
            )
            
        except ValidationError as e:
            await message.answer(f"❌ {str(e)}")
        except ValueError:
            await message.answer("❌ Введите корректное число (например: 5 или 0.5)")
        except DatabaseError as e:
            await self._handle_error(e, "create preset")
            await self._send_error_message(message, "Ошибка при создании пресета")
        except Exception as e:
            await self._handle_error(e, "create preset")
            await self._send_error_message(message)
        finally:
            await state.clear()
            # Возвращаемся к главному меню
            from bot.handlers.start_handler import StartHandler
            start_handler = StartHandler(self.storage)
            await start_handler.cmd_start(message)
    
    async def view_active_preset(self, callback: types.CallbackQuery):
        """Просмотр активного пресета."""
        try:
            preset_id = callback.data.split("_")[2]
            await self._show_preset_details(callback, preset_id, is_active=True)
        except Exception as e:
            await self._handle_error(e, "view active preset")
            await callback.answer("Ошибка при просмотре пресета")
    
    async def view_inactive_preset(self, callback: types.CallbackQuery):
        """Просмотр неактивного пресета."""
        try:
            preset_id = callback.data.split("_")[2]
            await self._show_preset_details(callback, preset_id, is_active=False)
        except Exception as e:
            await self._handle_error(e, "view inactive preset")
            await callback.answer("Ошибка при просмотре пресета")
    
    async def _show_preset_details(self, callback: types.CallbackQuery, preset_id: str, is_active: bool):
        """Показ деталей пресета."""
        user_data = await self.storage.get_user_data(callback.from_user.id)
        preset = user_data["presets"].get(preset_id)
        
        if not preset:
            await callback.answer("Пресет не найден")
            return
        
        builder = InlineKeyboardBuilder()
        if is_active:
            builder.button(text="⏸️ Деактивировать", callback_data=f"deactivate_{preset_id}")
        else:
            builder.button(text="▶️ Активировать", callback_data=f"activate_{preset_id}")
        
        builder.button(text="🗑️ Удалить", callback_data=f"delete_{preset_id}")
        builder.button(text="◀️ Назад", callback_data="back_to_presets")
        builder.adjust(2)
        
        pairs_text = (
            f"{len(preset['pairs'])} пар" 
            if len(preset['pairs']) > 10 
            else ', '.join(preset['pairs'][:10])
        )
        
        status = "🟢 АКТИВЕН" if is_active else "🔴 НЕАКТИВЕН"
        
        text = (
            f"📋 Пресет: {preset['preset_name']}\n"
            f"💰 Пары: {pairs_text}\n"
            f"⏰ Интервал: {preset['interval']}\n"
            f"📈 Процент: {preset['percent']}%\n"
            f"🔄 Статус: {status}"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def activate_preset(self, callback: types.CallbackQuery):
        """Активация пресета."""
        try:
            user_id = callback.from_user.id
            preset_id = callback.data.split("_")[1]
            
            await self.storage.activate_preset(user_id, preset_id)
            await callback.answer("✅ Пресет активирован")
            
            # Обновляем отображение
            await self._show_preset_details(callback, preset_id, is_active=True)
            
        except DatabaseError as e:
            await self._handle_error(e, "activate preset")
            await callback.answer("Ошибка при активации пресета")
        except Exception as e:
            await self._handle_error(e, "activate preset")
            await callback.answer("Ошибка")
    
    async def deactivate_preset(self, callback: types.CallbackQuery):
        """Деактивация пресета."""
        try:
            user_id = callback.from_user.id
            preset_id = callback.data.split("_")[1]
            
            await self.storage.deactivate_preset(user_id, preset_id)
            await callback.answer("✅ Пресет деактивирован")
            
            # Обновляем отображение
            await self._show_preset_details(callback, preset_id, is_active=False)
            
        except DatabaseError as e:
            await self._handle_error(e, "deactivate preset")
            await callback.answer("Ошибка при деактивации пресета")
        except Exception as e:
            await self._handle_error(e, "deactivate preset")
            await callback.answer("Ошибка")
    
    async def delete_preset(self, callback: types.CallbackQuery):
        """Удаление пресета."""
        try:
            user_id = callback.from_user.id
            preset_id = callback.data.split("_")[1]
            
            # Получаем информацию о пресете перед удалением
            user_data = await self.storage.get_user_data(user_id)
            preset_name = user_data["presets"].get(preset_id, {}).get("preset_name", "Неизвестный")
            
            # Удаляем пресет
            await self.storage.delete_preset(user_id, preset_id)
            
            # Удаляем сообщение с деталями
            await callback.message.delete()
            
            # Отправляем уведомление и меню настроек
            builder = InlineKeyboardBuilder()
            builder.button(text="🟢 Активные пресеты", callback_data="active_presets")
            builder.button(text="🔴 Неактивные пресеты", callback_data="inactive_presets")
            builder.button(text="➕ Добавить пресет", callback_data="add_preset")
            builder.button(text="◀️ Назад", callback_data="back_to_main")
            builder.adjust(1)
            
            await callback.message.answer(
                f"🗑️ Пресет '{preset_name}' удален!\n\n"
                "⚙️ Настройка конфигов:",
                reply_markup=builder.as_markup()
            )
            
            await callback.answer("Пресет удален")
            
        except DatabaseError as e:
            await self._handle_error(e, "delete preset")
            await callback.answer("Ошибка при удалении пресета")
        except Exception as e:
            await self._handle_error(e, "delete preset")
            await callback.answer("Ошибка")
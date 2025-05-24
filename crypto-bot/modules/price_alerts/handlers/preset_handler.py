# modules/price_alerts/handlers/preset_handler.py
"""Обработчик пресетов (адаптация существующего кода)."""

import uuid
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event
from shared.utils.validators import PriceAlertsValidator, ValidationError
from ..states.preset_states import PresetStates


class PresetHandler:
    """Обработчик создания и управления пресетами."""
    
    def __init__(self):
        # Подписываемся на ответы от price_alerts сервиса
        event_bus.subscribe("price_alerts.preset_created", self._handle_preset_created)
        event_bus.subscribe("price_alerts.preset_activated", self._handle_preset_activated)
    
    def register_handlers(self, router):
        """Регистрация обработчиков."""
        # Callback обработчики
        router.callback_query(F.data == "add_preset")(self.add_preset)
        router.callback_query(F.data == "select_all_pairs")(self.select_all_pairs)
        router.callback_query(F.data == "select_by_volume")(self.select_by_volume)
        router.callback_query(F.data == "enter_manually")(self.enter_manually)
        router.callback_query(F.data.startswith("interval_"))(self.process_interval_callback)
        router.callback_query(F.data.startswith("activate_"))(self.activate_preset)
        router.callback_query(F.data.startswith("deactivate_"))(self.deactivate_preset)
        router.callback_query(F.data.startswith("delete_"))(self.delete_preset)
        
        # State обработчики
        router.message(PresetStates.waiting_preset_name)(self.process_preset_name)
        router.message(PresetStates.waiting_pairs)(self.process_pairs)
        router.message(PresetStates.waiting_volume_input)(self.process_volume_input)
        router.message(PresetStates.waiting_percent)(self.process_percent)
    
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
            await callback.answer("Ошибка при создании пресета")
    
    async def process_preset_name(self, message: types.Message, state: FSMContext):
        """Обработка имени пресета."""
        try:
            preset_name = PriceAlertsValidator.validate_preset_name(message.text)
            
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
    
    async def select_all_pairs(self, callback: types.CallbackQuery, state: FSMContext):
        """Выбор всех доступных пар."""
        try:
            # Запрашиваем токены через события
            await event_bus.publish(Event(
                type="price_alerts.get_all_tokens",
                data={"callback_id": callback.id},
                source_module="telegram"
            ))
            
            # TODO: Ждем ответ и обрабатываем
            # Пока заглушка
            all_tokens = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]  # Заглушка
            
            await state.update_data(pairs=all_tokens)
            await self._show_interval_selection(callback, state)
            await callback.answer(f"Выбрано {len(all_tokens)} пар")
        except Exception as e:
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
            await callback.answer("Ошибка")
    
    async def process_volume_input(self, message: types.Message, state: FSMContext):
        """Обработка ввода минимального объема."""
        try:
            from shared.utils.validators import BaseValidator
            min_volume = BaseValidator.validate_number(message.text, min_value=0)
            
            # Запрашиваем токены по объему через события
            await event_bus.publish(Event(
                type="price_alerts.get_tokens_by_volume",
                data={"min_volume": min_volume, "user_id": message.from_user.id},
                source_module="telegram"
            ))
            
            # TODO: Ждем ответ
            # Пока заглушка
            selected_pairs = ["BTCUSDT", "ETHUSDT"]
            
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
            await callback.answer("Ошибка")
    
    async def process_pairs(self, message: types.Message, state: FSMContext):
        """Обработка ручного ввода пар."""
        try:
            pairs_input = [p.strip().upper() for p in message.text.split(",")]
            pairs = PriceAlertsValidator.validate_pairs(pairs_input)
            
            # TODO: Проверить валидность через события
            
            await state.update_data(pairs=pairs)
            await message.answer(f"✅ Выбрано {len(pairs)} пар")
            await self._show_interval_selection_message(message, state)
            
        except ValidationError as e:
            await message.answer(f"❌ {str(e)}")
    
    async def _show_interval_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Показ выбора интервала через callback."""
        await state.set_state(PresetStates.waiting_interval)
        
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]  # TODO: Получать через события
        
        builder = InlineKeyboardBuilder()
        for tf in timeframes:
            builder.button(text=tf, callback_data=f"interval_{tf}")
        builder.adjust(3)
        
        await callback.message.answer(
            "⏰ Выберите интервал свечи:",
            reply_markup=builder.as_markup()
        )
    
    async def _show_interval_selection_message(self, message: types.Message, state: FSMContext):
        """Показ выбора интервала через сообщение."""
        await state.set_state(PresetStates.waiting_interval)
        
        timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
        builder = InlineKeyboardBuilder()
        for tf in timeframes:
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
            interval = PriceAlertsValidator.validate_interval(interval)
            
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
    
    async def process_percent(self, message: types.Message, state: FSMContext):
        """Обработка ввода процента."""
        try:
            percent_text = message.text.strip().replace('%', '').replace(',', '.')
            percent = PriceAlertsValidator.validate_percent(float(percent_text))
            
            # Получаем данные из состояния
            data = await state.get_data()
            required_fields = ['preset_name', 'pairs', 'interval']
            
            if not all(k in data for k in required_fields):
                await message.answer("⚠️ Ошибка данных. Начните создание пресета заново.")
                await state.clear()
                return
            
            # Создаем пресет через события
            preset_data = {
                'preset_name': data['preset_name'],
                'pairs': data['pairs'],
                'interval': data['interval'],
                'percent': percent
            }
            
            await event_bus.publish(Event(
                type="price_alerts.create_preset",
                data={
                    "user_id": message.from_user.id,
                    "preset_data": preset_data
                },
                source_module="telegram"
            ))
            
            await message.answer(
                f"✅ Пресет '{preset_data['preset_name']}' создается...\n"
                f"🔧 Пар: {len(preset_data['pairs'])}\n"
                f"⏰ Интервал: {preset_data['interval']}\n"
                f"📈 Процент: {preset_data['percent']}%"
            )
            
        except ValidationError as e:
            await message.answer(f"❌ {str(e)}")
        except ValueError:
            await message.answer("❌ Введите корректное число (например: 5 или 0.5)")
        finally:
            await state.clear()
    
    async def activate_preset(self, callback: types.CallbackQuery):
        """Активация пресета."""
        try:
            preset_id = callback.data.split("_")[1]
            
            await event_bus.publish(Event(
                type="price_alerts.activate_preset",
                data={
                    "user_id": callback.from_user.id,
                    "preset_id": preset_id
                },
                source_module="telegram"
            ))
            
            await callback.answer("✅ Пресет активируется...")
            
        except Exception as e:
            await callback.answer("Ошибка при активации пресета")
    
    async def deactivate_preset(self, callback: types.CallbackQuery):
        """Деактивация пресета."""
        try:
            preset_id = callback.data.split("_")[1]
            
            await event_bus.publish(Event(
                type="price_alerts.deactivate_preset",
                data={
                    "user_id": callback.from_user.id,
                    "preset_id": preset_id
                },
                source_module="telegram"
            ))
            
            await callback.answer("✅ Пресет деактивируется...")
            
        except Exception as e:
            await callback.answer("Ошибка при деактивации пресета")
    
    async def delete_preset(self, callback: types.CallbackQuery):
        """Удаление пресета."""
        try:
            preset_id = callback.data.split("_")[1]
            
            await event_bus.publish(Event(
                type="price_alerts.delete_preset",
                data={
                    "user_id": callback.from_user.id,
                    "preset_id": preset_id
                },
                source_module="telegram"
            ))
            
            await callback.answer("🗑️ Пресет удаляется...")
            
        except Exception as e:
            await callback.answer("Ошибка при удалении пресета")
    
    async def _handle_preset_created(self, event: Event):
        """Обработка события создания пресета."""
        # TODO: Уведомить пользователя о результате
        pass
    
    async def _handle_preset_activated(self, event: Event):
        """Обработка события активации пресета."""
        # TODO: Уведомить пользователя о результате
        pass
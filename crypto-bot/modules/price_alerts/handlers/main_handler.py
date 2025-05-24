# modules/price_alerts/handlers/main_handler.py
"""Основной обработчик команд price_alerts."""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event
from shared.utils.logger import get_module_logger
from .states import PresetStates

logger = get_module_logger("price_alerts_handler")


class PriceAlertsHandler:
    """Обработчик команд ценовых алертов."""
    
    def __init__(self):
        self.router = Router()
        
        # Подписываемся на ответы от сервиса
        event_bus.subscribe("price_alerts.preset_created", self._handle_preset_created)
        event_bus.subscribe("price_alerts.preset_activated", self._handle_preset_activated)
        event_bus.subscribe("price_alerts.user_presets_response", self._handle_user_presets_response)
        event_bus.subscribe("price_alerts.tokens_response", self._handle_tokens_response)
        
        # Кеш для временного хранения ответов
        self._response_cache = {}
    
    def register_handlers(self, dp):
        """Регистрация обработчиков."""
        # Основные команды
        self.router.callback_query(F.data == "price_alerts")(self.show_main_menu)
        self.router.callback_query(F.data == "price_create_preset")(self.start_create_preset)
        self.router.callback_query(F.data == "price_my_presets")(self.show_user_presets)
        self.router.callback_query(F.data == "price_start_monitoring")(self.start_monitoring)
        self.router.callback_query(F.data == "price_stop_monitoring")(self.stop_monitoring)
        
        # Создание пресета
        self.router.message(PresetStates.waiting_name)(self.process_preset_name)
        self.router.callback_query(F.data.startswith("pairs_"))(self.process_pairs_selection)
        self.router.message(PresetStates.waiting_pairs)(self.process_manual_pairs)
        self.router.callback_query(F.data.startswith("interval_"))(self.process_interval)
        self.router.message(PresetStates.waiting_percent)(self.process_percent)
        
        # Управление пресетами
        self.router.callback_query(F.data.startswith("activate_"))(self.activate_preset)
        self.router.callback_query(F.data.startswith("deactivate_"))(self.deactivate_preset)
        
        dp.include_router(self.router)
    
    async def show_main_menu(self, callback: types.CallbackQuery):
        """Показ главного меню price alerts."""
        text = (
            "📈 <b>Price Alerts</b>\n\n"
            "Система мониторинга цен криптовалют в реальном времени\n\n"
            "🔧 <b>Возможности:</b>\n"
            "• Создание пресетов для групп пар\n"
            "• Настройка процентного изменения\n"
            "• Множественные таймфреймы\n"
            "• Фильтрация по объему\n"
            "• Группировка уведомлений\n\n"
            "📊 <b>Статистика:</b>\n"
            "• Активных пресетов: 0\n"
            "• Мониторинг: Остановлен"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="📋 Мои пресеты", callback_data="price_my_presets")
        builder.button(text="🚀 Запустить мониторинг", callback_data="price_start_monitoring")
        builder.button(text="⏹️ Остановить мониторинг", callback_data="price_stop_monitoring")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def start_create_preset(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало создания пресета."""
        await state.set_state(PresetStates.waiting_name)
        
        text = (
            "📝 <b>Создание пресета</b>\n\n"
            "Шаг 1/4: Введите название пресета\n\n"
            "Примеры:\n"
            "• \"Топ криптовалюты 2%\"\n"
            "• \"Альткоины 5%\"\n"
            "• \"DeFi токены\""
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="price_alerts")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_preset_name(self, message: types.Message, state: FSMContext):
        """Обработка названия пресета."""
        try:
            preset_name = message.text.strip()
            
            if len(preset_name) < 3:
                await message.answer("❌ Название слишком короткое (минимум 3 символа)")
                return
            
            if len(preset_name) > 50:
                await message.answer("❌ Название слишком длинное (максимум 50 символов)")
                return
            
            await state.update_data(preset_name=preset_name)
            await state.set_state(PresetStates.waiting_pairs)
            
            text = (
                f"✅ Название: <b>{preset_name}</b>\n\n"
                "📊 Шаг 2/4: Выберите торговые пары\n\n"
                "Как выбрать пары?"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🔝 Топ 10 пар", callback_data="pairs_top10")
            builder.button(text="📈 Топ 50 пар", callback_data="pairs_top50")
            builder.button(text="💰 По объему торгов", callback_data="pairs_volume")
            builder.button(text="✏️ Ввести вручную", callback_data="pairs_manual")
            builder.button(text="❌ Отмена", callback_data="price_alerts")
            builder.adjust(1)
            
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Error processing preset name: {e}")
            await message.answer("❌ Ошибка обработки названия")
    
    async def process_pairs_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора пар."""
        selection = callback.data.split("_")[1]
        
        # Запрашиваем токены у сервиса
        await event_bus.publish(Event(
            type="price_alerts.get_all_tokens",
            data={"selection": selection, "user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        # Показываем загрузку
        await callback.message.edit_text("🔄 Загружаю список токенов...")
        await callback.answer()
        
        # Сохраняем контекст для обработки ответа
        self._response_cache[callback.from_user.id] = {
            "type": "pairs_selection",
            "selection": selection,
            "state": state,
            "message": callback.message
        }
    
    async def process_manual_pairs(self, message: types.Message, state: FSMContext):
        """Обработка ручного ввода пар."""
        try:
            pairs_text = message.text.strip().upper()
            pairs = [pair.strip() for pair in pairs_text.split(",")]
            
            # Базовая валидация
            valid_pairs = []
            for pair in pairs:
                if pair.endswith("USDT") and len(pair) > 4:
                    valid_pairs.append(pair)
            
            if not valid_pairs:
                await message.answer("❌ Не найдено валидных USDT пар. Попробуйте еще раз:")
                return
            
            if len(valid_pairs) > 100:
                await message.answer("❌ Слишком много пар (максимум 100). Попробуйте еще раз:")
                return
            
            await state.update_data(pairs=valid_pairs)
            await self._show_interval_selection(message, state, len(valid_pairs))
            
        except Exception as e:
            logger.error(f"Error processing manual pairs: {e}")
            await message.answer("❌ Ошибка обработки пар")
    
    async def process_interval(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора интервала."""
        interval = callback.data.split("_")[1]
        await state.update_data(interval=interval)
        await state.set_state(PresetStates.waiting_percent)
        
        data = await state.get_data()
        pairs_count = len(data.get('pairs', []))
        
        text = (
            f"✅ Интервал: <b>{interval}</b>\n\n"
            "📈 Шаг 4/4: Процент изменения\n\n"
            "Введите минимальный процент изменения цены для получения уведомлений:\n\n"
            "Примеры: 1, 2.5, 5, 10"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="1%", callback_data="percent_1")
        builder.button(text="2%", callback_data="percent_2")
        builder.button(text="5%", callback_data="percent_5")
        builder.button(text="❌ Отмена", callback_data="price_alerts")
        builder.adjust(3)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_percent(self, message: types.Message, state: FSMContext):
        """Обработка процента изменения."""
        try:
            percent_text = message.text.strip().replace('%', '').replace(',', '.')
            percent = float(percent_text)
            
            if percent <= 0 or percent > 100:
                await message.answer("❌ Процент должен быть от 0.1% до 100%")
                return
            
            # Получаем все данные
            data = await state.get_data()
            preset_data = {
                'preset_name': data['preset_name'],
                'pairs': data['pairs'],
                'interval': data['interval'],
                'percent': percent
            }
            
            # Создаем пресет через сервис
            await event_bus.publish(Event(
                type="price_alerts.create_preset",
                data={
                    "user_id": message.from_user.id,
                    "preset_data": preset_data
                },
                source_module="telegram"
            ))
            
            # Показываем подтверждение
            text = (
                "✅ <b>Пресет создается...</b>\n\n"
                f"📝 Название: {preset_data['preset_name']}\n"
                f"📊 Пар: {len(preset_data['pairs'])}\n"
                f"⏰ Интервал: {preset_data['interval']}\n"
                f"📈 Процент: {preset_data['percent']}%"
            )
            
            await message.answer(text, parse_mode="HTML")
            await state.clear()
            
        except ValueError:
            await message.answer("❌ Введите корректное число")
        except Exception as e:
            logger.error(f"Error processing percent: {e}")
            await message.answer("❌ Ошибка создания пресета")
    
    async def show_user_presets(self, callback: types.CallbackQuery):
        """Показ пресетов пользователя."""
        # Запрашиваем пресеты у сервиса
        await event_bus.publish(Event(
            type="price_alerts.get_user_presets",
            data={"user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        await callback.message.edit_text("🔄 Загружаю ваши пресеты...")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[callback.from_user.id] = {
            "type": "user_presets",
            "message": callback.message
        }
    
    async def start_monitoring(self, callback: types.CallbackQuery):
        """Запуск мониторинга."""
        await event_bus.publish(Event(
            type="price_alerts.start_monitoring",
            data={"user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        await callback.answer("🚀 Мониторинг запущен!")
    
    async def stop_monitoring(self, callback: types.CallbackQuery):
        """Остановка мониторинга."""
        await event_bus.publish(Event(
            type="price_alerts.stop_monitoring",
            data={"user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        await callback.answer("⏹️ Мониторинг остановлен!")
    
    async def activate_preset(self, callback: types.CallbackQuery):
        """Активация пресета."""
        preset_id = callback.data.split("_", 1)[1]
        
        await event_bus.publish(Event(
            type="price_alerts.activate_preset",
            data={"user_id": callback.from_user.id, "preset_id": preset_id},
            source_module="telegram"
        ))
        
        await callback.answer("✅ Пресет активируется...")
    
    async def deactivate_preset(self, callback: types.CallbackQuery):
        """Деактивация пресета."""
        preset_id = callback.data.split("_", 1)[1]
        
        await event_bus.publish(Event(
            type="price_alerts.deactivate_preset",
            data={"user_id": callback.from_user.id, "preset_id": preset_id},
            source_module="telegram"
        ))
        
        await callback.answer("⏹️ Пресет деактивируется...")
    
    async def _show_interval_selection(self, message: types.Message, state: FSMContext, pairs_count: int):
        """Показ выбора интервала."""
        await state.set_state(PresetStates.waiting_interval)
        
        text = (
            f"✅ Выбрано пар: <b>{pairs_count}</b>\n\n"
            "⏰ Шаг 3/4: Выберите интервал свечи\n\n"
            "Чем меньше интервал, тем чаще уведомления:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="1m", callback_data="interval_1m")
        builder.button(text="5m", callback_data="interval_5m")
        builder.button(text="15m", callback_data="interval_15m")
        builder.button(text="1h", callback_data="interval_1h")
        builder.button(text="4h", callback_data="interval_4h")
        builder.button(text="1d", callback_data="interval_1d")
        builder.button(text="❌ Отмена", callback_data="price_alerts")
        builder.adjust(3, 3, 1)
        
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    # Обработчики ответов от сервиса
    async def _handle_preset_created(self, event: Event):
        """Обработка создания пресета."""
        # TODO: Уведомить пользователя о результате
        pass
    
    async def _handle_preset_activated(self, event: Event):
        """Обработка активации пресета."""
        # TODO: Обновить интерфейс
        pass
    
    async def _handle_user_presets_response(self, event: Event):
        """Обработка ответа с пресетами пользователя."""
        user_id = event.data.get("user_id")
        presets = event.data.get("presets", {})
        
        if user_id in self._response_cache:
            context = self._response_cache[user_id]
            
            if context["type"] == "user_presets":
                await self._show_presets_list(context["message"], presets)
                del self._response_cache[user_id]
    
    async def _handle_tokens_response(self, event: Event):
        """Обработка ответа со списком токенов."""
        tokens = event.data.get("tokens", [])
        
        # Найти пользователя в кеше и обработать
        for user_id, context in list(self._response_cache.items()):
            if context["type"] == "pairs_selection":
                selection = context["selection"]
                
                if selection == "top10":
                    selected_pairs = tokens[:10]
                elif selection == "top50":
                    selected_pairs = tokens[:50]
                else:
                    selected_pairs = tokens[:10]  # fallback
                
                await context["state"].update_data(pairs=selected_pairs)
                await self._show_interval_selection(context["message"], context["state"], len(selected_pairs))
                
                del self._response_cache[user_id]
                break
    
    async def _show_presets_list(self, message: types.Message, presets: dict):
        """Показ списка пресетов."""
        if not presets:
            text = "📋 У вас пока нет созданных пресетов"
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Создать первый пресет", callback_data="price_create_preset")
            builder.button(text="◀️ Назад", callback_data="price_alerts")
        else:
            text = f"📋 <b>Ваши пресеты ({len(presets)}):</b>\n\n"
            
            builder = InlineKeyboardBuilder()
            
            for preset_id, preset in presets.items():
                status = "🟢" if preset.get('is_active', False) else "🔴"
                text += f"{status} <b>{preset['preset_name']}</b>\n"
                text += f"   📊 {len(preset['pairs'])} пар, {preset['interval']}, {preset['percent']}%\n\n"
                
                if preset.get('is_active', False):
                    builder.button(
                        text=f"⏹️ {preset['preset_name'][:20]}",
                        callback_data=f"deactivate_{preset_id}"
                    )
                else:
                    builder.button(
                        text=f"▶️ {preset['preset_name'][:20]}",
                        callback_data=f"activate_{preset_id}"
                    )
            
            builder.button(text="◀️ Назад", callback_data="price_alerts")
            builder.adjust(1)
        
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
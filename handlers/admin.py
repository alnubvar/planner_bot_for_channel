from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
    InputMediaAnimation,
)

from keyboards.main_menu import admin_menu
from keyboards.calendar_kb import build_date_choice_kb, build_calendar
from keyboards.inline_admin import build_posts_list_kb

from datetime import datetime, timedelta
from asyncio import create_task, sleep
import pytz
import json

from utils.db import save_post, get_pending_posts_page
from utils.scheduler import schedule_post
from config import CHANNEL_ID

router = Router()

print("ADMIN ROUTER LOADED")

ADMIN_ID = [8120213148, 882428172]
PAGE_SIZE = 5
LA = pytz.timezone("America/New_York")


# ============================================================
#                    FSM
# ============================================================


class AddPost(StatesGroup):
    waiting_for_content = State()
    waiting_for_action = State()
    waiting_for_date = State()
    waiting_for_time = State()


def register_admin_handlers(dp):
    dp.include_router(router)


# ============================================================
#                    ВСПОМОГАТЕЛЬНЫЕ
# ============================================================


def build_publish_or_schedule_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Опубликовать сейчас", callback_data="post_action:now"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Запланировать", callback_data="post_action:schedule"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data="post_action:cancel"
                )
            ],
        ]
    )


async def publish_now_to_channel(bot: Bot, content_type: str, raw_content: str):
    chat_id = CHANNEL_ID

    # --- TEXT ---
    if content_type == "text":
        await bot.send_message(chat_id, raw_content)
        return

    # --- ALBUM ---
    if content_type == "media_group":
        album = json.loads(raw_content)
        media = []

        caption = album.get("caption")
        items = album["items"]

        for idx, item in enumerate(items[:10]):
            cap = caption if idx == 0 else None
            if item["type"] == "photo":
                media.append(InputMediaPhoto(item["file_id"], caption=cap))
            elif item["type"] == "video":
                media.append(InputMediaVideo(item["file_id"], caption=cap))
            elif item["type"] == "document":
                media.append(InputMediaDocument(item["file_id"], caption=cap))
            elif item["type"] == "animation":
                media.append(InputMediaAnimation(item["file_id"], caption=cap))

        await bot.send_media_group(chat_id, media)
        return

    # --- SINGLE MEDIA ---
    data = json.loads(raw_content)
    file_id = data["file_id"]
    caption = data.get("caption")

    if content_type == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption)
    elif content_type == "video":
        await bot.send_video(chat_id, file_id, caption=caption)
    elif content_type == "document":
        await bot.send_document(chat_id, file_id, caption=caption)
    elif content_type == "voice":
        await bot.send_voice(chat_id, file_id, caption=caption)
    elif content_type == "audio":
        await bot.send_audio(chat_id, file_id, caption=caption)
    elif content_type == "animation":
        await bot.send_animation(chat_id, file_id, caption=caption)
    elif content_type == "video_note":
        await bot.send_video_note(chat_id, file_id)


# ============================================================
#                    1. ДОБАВИТЬ ПОСТ
# ============================================================


@router.message(F.text == "📝 Добавить пост")
async def add_post(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID:
        return

    await state.set_state(AddPost.waiting_for_content)
    await state.update_data(album=None)

    await message.answer(
        "Отправь мне пост, который нужно опубликовать.\n\n"
        "Поддерживается:\n"
        "— текст\n"
        "— фото / видео + текст\n"
        "— документы\n"
        "— голосовые, аудио, GIF\n"
        "— альбомы (2–10 медиа подряд)"
    )


# ============================================================
#                    2. СПИСОК ПОСТОВ
# ============================================================


@router.message(F.text == "📋 Мои запланированные")
async def list_my_posts(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return

    page = 1
    posts = await get_pending_posts_page(PAGE_SIZE, 0)

    if not posts:
        await message.answer("У тебя нет запланированных постов 💤")
        return

    kb = build_posts_list_kb(posts, page, PAGE_SIZE)
    await message.answer("Вот твои запланированные посты:", reply_markup=kb)


# ============================================================
#         3. ПРИНЯТИЕ КОНТЕНТА + АЛЬБОМЫ
# ============================================================


@router.message(AddPost.waiting_for_content)
async def process_content(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # ----------------------------------------------------------
    # Альбом (media_group)
    # ----------------------------------------------------------
    if message.media_group_id:
        album = data.get("album")

        if not album:
            album = {
                "media_group_id": message.media_group_id,
                "items": [],
                "caption": None,
            }

        if message.caption and not album["caption"]:
            album["caption"] = message.caption

        if message.photo:
            album["items"].append(
                {"type": "photo", "file_id": message.photo[-1].file_id}
            )
        elif message.video:
            album["items"].append({"type": "video", "file_id": message.video.file_id})
        elif message.document:
            album["items"].append(
                {"type": "document", "file_id": message.document.file_id}
            )
        elif message.animation:
            album["items"].append(
                {"type": "animation", "file_id": message.animation.file_id}
            )
        else:
            await message.answer(
                "В альбом можно добавлять только фото, видео, GIF и документы."
            )
            return

        album["items"] = album["items"][:10]
        await state.update_data(album=album)

        async def finish(group_id):
            await sleep(0.7)
            d = await state.get_data()
            last = d.get("album")

            if not last or last["media_group_id"] != group_id:
                return

            await state.update_data(
                content_type="media_group",
                content=json.dumps(
                    {"items": last["items"], "caption": last["caption"]},
                    ensure_ascii=False,
                ),
                album=None,
            )

            await state.set_state(AddPost.waiting_for_action)
            await message.answer(
                "Альбом принят! Как публикуем?",
                reply_markup=build_publish_or_schedule_kb(),
            )

        create_task(finish(message.media_group_id))
        return

    # ----------------------------------------------------------
    # Альбом завершён, приходит новое сообщение
    # ----------------------------------------------------------
    if data.get("album"):
        album = data["album"]
        await state.update_data(
            content_type="media_group",
            content=json.dumps(
                {"items": album["items"], "caption": album["caption"]},
                ensure_ascii=False,
            ),
            album=None,
        )

        await state.set_state(AddPost.waiting_for_action)
        await message.answer(
            "Альбом принят! Как публикуем?", reply_markup=build_publish_or_schedule_kb()
        )
        return

    # ----------------------------------------------------------
    # Одиночные медиа / текст
    # ----------------------------------------------------------
    if message.text:
        await state.update_data(content_type="text", content=message.text)

    elif message.photo:
        await state.update_data(
            content_type="photo",
            content=json.dumps(
                {"file_id": message.photo[-1].file_id, "caption": message.caption},
                ensure_ascii=False,
            ),
        )

    elif message.video:
        await state.update_data(
            content_type="video",
            content=json.dumps(
                {"file_id": message.video.file_id, "caption": message.caption},
                ensure_ascii=False,
            ),
        )

    elif message.document:
        await state.update_data(
            content_type="document",
            content=json.dumps(
                {"file_id": message.document.file_id, "caption": message.caption},
                ensure_ascii=False,
            ),
        )

    elif message.voice:
        await state.update_data(
            content_type="voice",
            content=json.dumps(
                {"file_id": message.voice.file_id, "caption": message.caption},
                ensure_ascii=False,
            ),
        )

    elif message.audio:
        await state.update_data(
            content_type="audio",
            content=json.dumps(
                {"file_id": message.audio.file_id, "caption": message.caption},
                ensure_ascii=False,
            ),
        )

    elif message.video_note:
        await state.update_data(
            content_type="video_note",
            content=json.dumps({"file_id": message.video_note.file_id}),
        )

    elif message.animation:
        await state.update_data(
            content_type="animation",
            content=json.dumps(
                {"file_id": message.animation.file_id, "caption": message.caption},
                ensure_ascii=False,
            ),
        )

    else:
        await message.answer("Этот тип контента пока не поддерживается.")
        return

    # Показываем выбор действия
    await state.set_state(AddPost.waiting_for_action)
    await message.answer(
        "Пост получен! Как публикуем?", reply_markup=build_publish_or_schedule_kb()
    )


# ============================================================
#               3.1 ВЫБОР ДЕЙСТВИЯ
# ============================================================


@router.callback_query(AddPost.waiting_for_action, F.data == "post_action:cancel")
async def cancel_post(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Пост отменён ❌")
    await callback.answer()


@router.callback_query(AddPost.waiting_for_action, F.data == "post_action:now")
async def publish_now(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    await publish_now_to_channel(
        callback.message.bot,
        data["content_type"],
        data["content"],
    )

    await state.clear()
    await callback.message.edit_text("Пост опубликован прямо сейчас ✅")
    await callback.message.answer("Что дальше?", reply_markup=admin_menu())


@router.callback_query(AddPost.waiting_for_action, F.data == "post_action:schedule")
async def choose_schedule(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddPost.waiting_for_date)

    await callback.message.edit_text(
        "Выбери дату публикации:", reply_markup=build_date_choice_kb()
    )
    await callback.answer()


# ============================================================
#                4. БЫСТРЫЕ ДАТЫ + КАЛЕНДАРЬ
# ============================================================


@router.callback_query(AddPost.waiting_for_date, F.data.startswith("pick_date:"))
async def pick_quick_date(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split(":")[1]
    today = datetime.now(LA).date()

    if data == "today":
        chosen = today
    elif data == "tomorrow":
        chosen = today + timedelta(days=1)
    elif data == "after2":
        chosen = today + timedelta(days=2)
    else:
        chosen = datetime.strptime(data, "%Y-%m-%d").date()

    await state.update_data(chosen_date=str(chosen))
    await state.set_state(AddPost.waiting_for_time)

    await callback.message.answer(
        "Теперь введи время в формате: ЧЧ ММ (например 14 30)"
    )
    await callback.answer()


# ------------- Открыть календарь -------------
@router.callback_query(F.data == "open_calendar")
async def open_calendar(callback: types.CallbackQuery):
    now = datetime.now(LA)
    kb = build_calendar(now.year, now.month)

    await callback.message.edit_text("Выбери дату:", reply_markup=kb)
    await callback.answer()


# ------------- Переключение месяцев -------------
@router.callback_query(F.data.startswith("calendar_prev:"))
async def prev_month(callback: types.CallbackQuery):
    _, year, month = callback.data.split(":")
    year = int(year)
    month = int(month) - 1

    if month == 0:
        month = 12
        year -= 1

    kb = build_calendar(year, month)
    await callback.message.edit_text("Выбери дату:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("calendar_next:"))
async def next_month(callback: types.CallbackQuery):
    _, year, month = callback.data.split(":")
    year = int(year)
    month = int(month) + 1

    if month == 13:
        month = 1
        year += 1

    kb = build_calendar(year, month)
    await callback.message.edit_text("Выбери дату:", reply_markup=kb)
    await callback.answer()


# ------------- Закрыть календарь -------------
@router.callback_query(F.data == "calendar_close")
async def close_calendar(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выбери дату публикации (New York):", reply_markup=build_date_choice_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("calendar_pick:"))
async def pick_quick_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    await state.update_data(chosen_date=date_str)

    await state.set_state(AddPost.waiting_for_time)
    await callback.message.edit_text(
        "Теперь введи время публикации.\nФормат: ЧЧ ММ (например 14 30)"
    )
    await callback.answer()


# ============================================================
#                5. ВВОД ВРЕМЕНИ → СОХРАНЕНИЕ
# ============================================================


@router.message(AddPost.waiting_for_time)
async def choose_time(message: types.Message, state: FSMContext):
    try:
        hour, minute = map(int, message.text.split())
        if hour > 23 or minute > 59:
            raise ValueError
    except:
        await message.answer("Неверный формат. Пример: 14 30")
        return

    data = await state.get_data()
    chosen_date = datetime.fromisoformat(data["chosen_date"])

    publish_dt = LA.localize(
        datetime(chosen_date.year, chosen_date.month, chosen_date.day, hour, minute)
    )

    content = data["content"]
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)

    post_id = await save_post(
        data["content_type"], content, CHANNEL_ID, publish_dt.isoformat()
    )

    schedule_post(message.bot, post_id, publish_dt)

    await message.answer(
        f"Готово! 🎉\nПост запланирован на {publish_dt.strftime('%Y-%m-%d %H:%M')} New York.",
        reply_markup=admin_menu(),
    )

    await state.clear()


# ============================================================
#                 6. ПАГИНАЦИЯ СПИСКА
# ============================================================


@router.callback_query(F.data.startswith("posts_page:"))
async def paginate_posts(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_ID:
        return await callback.answer()

    _, page_str = callback.data.split(":")
    page = int(page_str)
    offset = (page - 1) * PAGE_SIZE

    posts = await get_pending_posts_page(PAGE_SIZE, offset)

    if not posts:
        await callback.message.edit_text("Нет постов 💤")
        return

    kb = build_posts_list_kb(posts, page, PAGE_SIZE)
    await callback.message.edit_text("Вот твои запланированные посты:", reply_markup=kb)
    await callback.answer()

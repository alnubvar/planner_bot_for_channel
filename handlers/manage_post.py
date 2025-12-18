from aiogram import Router, F, types, Bot
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

import json
from datetime import datetime
import pytz

from utils.db import (
    get_scheduled_posts,
    update_post,
    delete_post,
    get_pending_posts_page,
)
from utils.scheduler import reschedule_post, remove_scheduled_post
from keyboards.inline_admin import build_posts_list_kb

router = Router()
LA = pytz.timezone("America/New_York")
PAGE_SIZE = 5  # такой же, как в admin.py


# ============= FSM STATES =============


class EditText(StatesGroup):
    waiting_new_text = State()


class EditMedia(StatesGroup):
    waiting_new_media = State()


class EditDate(StatesGroup):
    waiting_new_date = State()


class EditTime(StatesGroup):
    waiting_new_time = State()


def register_manage_post_handlers(dp):
    dp.include_router(router)


# ============= КЛАВИАТУРА ПОД ПОСТОМ =============


def manage_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать текст",
                    callback_data=f"edit_text:{post_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖼 Редактировать медиа",
                    callback_data=f"edit_media:{post_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Дата", callback_data=f"edit_date:{post_id}"
                ),
                InlineKeyboardButton(
                    text="⏰ Время", callback_data=f"edit_time:{post_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить пост", callback_data=f"delete_post:{post_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к списку", callback_data="back_to_list"
                )
            ],
        ]
    )


# ============= PREVIEW =============


async def send_post_preview(bot: Bot, admin_id: int, post: dict):
    """
    Отправляем превью поста администратору + inline-меню управления.
    """

    post_type = post["type"]
    raw = post["content"]

    # ---------- TEXT ----------
    if post_type == "text":
        await bot.send_message(admin_id, raw, reply_markup=manage_keyboard(post["id"]))
        return

    # ---------- MEDIA GROUP (ALBUM) ----------
    if post_type == "media_group":
        try:
            album = json.loads(raw)  # {"items": [...], "caption": "..."}
        except Exception:
            await bot.send_message(admin_id, "Ошибка: повреждён media_group JSON")
            return

        items = album.get("items", [])
        caption = album.get("caption")

        media = []
        for idx, item in enumerate(items[:10]):
            itype = item["type"]
            file_id = item["file_id"]
            cap = caption if idx == 0 else None

            if itype == "photo":
                media.append(InputMediaPhoto(media=file_id, caption=cap))
            elif itype == "video":
                media.append(InputMediaVideo(media=file_id, caption=cap))
            elif itype == "document":
                media.append(InputMediaDocument(media=file_id, caption=cap))
            elif itype == "animation":
                media.append(InputMediaAnimation(media=file_id, caption=cap))

        if media:
            await bot.send_media_group(admin_id, media)

        # отдельно сообщение с клавиатурой
        await bot.send_message(
            admin_id,
            f"Управление альбомом #{post['id']}:",
            reply_markup=manage_keyboard(post["id"]),
        )
        return

    # ---------- SINGLE MEDIA ----------
    try:
        data = json.loads(raw)
    except Exception:
        await bot.send_message(admin_id, "Ошибка: повреждён JSON контента")
        return

    file_id = data.get("file_id")
    caption = data.get("caption")

    if post_type == "photo":
        await bot.send_photo(
            admin_id, file_id, caption=caption, reply_markup=manage_keyboard(post["id"])
        )
    elif post_type == "video":
        await bot.send_video(
            admin_id, file_id, caption=caption, reply_markup=manage_keyboard(post["id"])
        )
    elif post_type == "document":
        await bot.send_document(
            admin_id, file_id, caption=caption, reply_markup=manage_keyboard(post["id"])
        )
    elif post_type == "audio":
        await bot.send_audio(
            admin_id, file_id, caption=caption, reply_markup=manage_keyboard(post["id"])
        )
    elif post_type == "voice":
        await bot.send_voice(
            admin_id, file_id, caption=caption, reply_markup=manage_keyboard(post["id"])
        )
    elif post_type == "animation":
        await bot.send_animation(
            admin_id, file_id, caption=caption, reply_markup=manage_keyboard(post["id"])
        )


# ============= ОТКРЫТЬ ПОСТ ИЗ СПИСКА =============


@router.callback_query(F.data.startswith("post_open:"))
async def open_post(callback: types.CallbackQuery):
    _, post_id_str, _page_str = callback.data.split(":")
    post_id = int(post_id_str)

    post = await get_scheduled_posts(post_id)
    if not post:
        await callback.answer("Пост не найден 😕", show_alert=True)
        return

    await send_post_preview(callback.message.bot, callback.from_user.id, post)
    await callback.answer()


# ============= EDIT TEXT =============


@router.callback_query(F.data.startswith("edit_text:"))
async def start_edit_text(callback: types.CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    await state.update_data(edit_post_id=post_id)

    await callback.message.answer("Отправь новый текст поста:")
    await state.set_state(EditText.waiting_new_text)
    await callback.answer()


@router.message(EditText.waiting_new_text)
async def save_new_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data["edit_post_id"]

    post = await get_scheduled_posts(post_id)
    if not post:
        await message.answer("Пост не найден 😕")
        await state.clear()
        return

    if post["type"] == "text":
        new_content = message.text

    elif post["type"] == "media_group":
        album = json.loads(post["content"])
        album["caption"] = message.text
        new_content = json.dumps(album, ensure_ascii=False)

    else:
        raw = json.loads(post["content"])
        raw["caption"] = message.text
        new_content = json.dumps(raw, ensure_ascii=False)

    await update_post(post_id, new_content)

    await message.answer("Текст обновлён ✅")
    await send_post_preview(
        message.bot, message.from_user.id, await get_scheduled_posts(post_id)
    )

    await state.clear()


# ============= EDIT MEDIA =============


@router.callback_query(F.data.startswith("edit_media:"))
async def start_edit_media(callback: types.CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    await state.update_data(edit_post_id=post_id)

    await callback.message.answer(
        "Пришли новое медиа (фото/видео/документ и т.д.).\n"
        "Для альбомов: можно менять только текст, "
        "если нужно полностью другой альбом — удали пост и создай заново."
    )
    await state.set_state(EditMedia.waiting_new_media)
    await callback.answer()


@router.message(EditMedia.waiting_new_media)
async def save_new_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data["edit_post_id"]

    post = await get_scheduled_posts(post_id)
    if not post:
        await message.answer("Пост не найден 😕")
        await state.clear()
        return

    # если это альбом — не трогаем медиа, только текст (см. сообщение выше)
    if post["type"] == "media_group":
        await message.answer(
            "Медиа альбома нельзя менять, только текст.\n"
            "Если нужно другой набор картинок — удали пост и создай заново."
        )
        await state.clear()
        return

    # одиночное медиа
    if message.photo:
        t = "photo"
        payload = {"file_id": message.photo[-1].file_id, "caption": message.caption}
    elif message.video:
        t = "video"
        payload = {"file_id": message.video.file_id, "caption": message.caption}
    elif message.document:
        t = "document"
        payload = {"file_id": message.document.file_id, "caption": message.caption}
    elif message.animation:
        t = "animation"
        payload = {"file_id": message.animation.file_id, "caption": message.caption}
    elif message.audio:
        t = "audio"
        payload = {"file_id": message.audio.file_id, "caption": message.caption}
    elif message.voice:
        t = "voice"
        payload = {"file_id": message.voice.file_id, "caption": message.caption}
    else:
        await message.answer("Этот тип медиа не поддерживается.")
        return

    await update_post(post_id, json.dumps(payload, ensure_ascii=False), t)

    await message.answer("Медиа обновлено ✅")
    await send_post_preview(
        message.bot, message.from_user.id, await get_scheduled_posts(post_id)
    )

    await state.clear()


# ============= EDIT DATE =============


@router.callback_query(F.data.startswith("edit_date:"))
async def start_edit_date(callback: types.CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    await state.update_data(edit_post_id=post_id)

    await callback.message.answer("Введи новую дату (формат YYYY-MM-DD):")
    await state.set_state(EditDate.waiting_new_date)
    await callback.answer()


@router.message(EditDate.waiting_new_date)
async def save_new_date(message: types.Message, state: FSMContext):
    try:
        new_date = datetime.strptime(message.text, "%Y-%m-%d").date()
    except Exception:
        await message.answer("Неверный формат. Пример: 2025-12-05")
        return

    data = await state.get_data()
    post_id = data["edit_post_id"]

    post = await get_scheduled_posts(post_id)
    if not post:
        await message.answer("Пост не найден 😕")
        await state.clear()
        return

    old_dt = datetime.fromisoformat(post["publish_time"])

    new_dt = LA.localize(
        datetime(
            new_date.year,
            new_date.month,
            new_date.day,
            old_dt.hour,
            old_dt.minute,
        )
    )

    await update_post(post_id, None, None, new_dt.isoformat())
    reschedule_post(post_id, new_dt)

    await message.answer("Дата обновлена ✅")
    await send_post_preview(
        message.bot, message.from_user.id, await get_scheduled_posts(post_id)
    )

    await state.clear()


# ============= EDIT TIME =============


@router.callback_query(F.data.startswith("edit_time:"))
async def start_edit_time(callback: types.CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    await state.update_data(edit_post_id=post_id)

    await callback.message.answer("Введи новое время (формат ЧЧ ММ):")
    await state.set_state(EditTime.waiting_new_time)
    await callback.answer()


@router.message(EditTime.waiting_new_time)
async def save_new_time(message: types.Message, state: FSMContext):
    try:
        hour, minute = map(int, message.text.split())
    except Exception:
        await message.answer("Неверный формат. Пример: 14 30")
        return

    data = await state.get_data()
    post_id = data["edit_post_id"]

    post = await get_scheduled_posts(post_id)
    if not post:
        await message.answer("Пост не найден 😕")
        await state.clear()
        return

    old_dt = datetime.fromisoformat(post["publish_time"])

    new_dt = LA.localize(datetime(old_dt.year, old_dt.month, old_dt.day, hour, minute))

    await update_post(post_id, None, None, new_dt.isoformat())
    reschedule_post(post_id, new_dt)

    await message.answer("Время обновлено ✅")
    await send_post_preview(
        message.bot, message.from_user.id, await get_scheduled_posts(post_id)
    )

    await state.clear()


# ============= DELETE POST =============


@router.callback_query(F.data.startswith("delete_post:"))
async def delete_post_handler(callback: types.CallbackQuery):
    post_id = int(callback.data.split(":")[1])

    await delete_post(post_id)
    remove_scheduled_post(post_id)

    await callback.message.answer("Пост удалён ✅")
    await callback.answer()


# ============= BACK TO LIST =============


@router.callback_query(F.data == "back_to_list")
async def back_to_list(callback: types.CallbackQuery):
    """
    Возвращаемся к первой странице списка запланированных постов.
    """
    offset = 0
    posts = await get_pending_posts_page(PAGE_SIZE, offset)

    if not posts:
        await callback.message.answer("У тебя нет запланированных постов 💤")
        await callback.answer()
        return

    kb = build_posts_list_kb(posts, page=1, page_size=PAGE_SIZE)
    await callback.message.answer("Вот твои запланированные посты:", reply_markup=kb)
    await callback.answer()

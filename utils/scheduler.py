import pytz
import json
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from utils.db import get_scheduled_posts, mark_post_as_sent

LA_TZ = pytz.timezone("America/New_York")

scheduler = AsyncIOScheduler(timezone=LA_TZ)


# ==========================================
#            PUBLISH POST
# ==========================================


async def publish_post(bot: Bot, post_id: int):
    post = await get_scheduled_posts(post_id)

    if not post:
        return

    chat_id = post["channel_id"]
    post_type = post["type"]
    raw = post["content"]

    # ---------- TEXT ----------
    if post_type == "text":
        await bot.send_message(chat_id, raw)
        await mark_post_as_sent(post_id)
        return

    # ---------- MEDIA GROUP (ALBUM) ----------
    if post_type == "media_group":
        from aiogram.types import (
            InputMediaPhoto,
            InputMediaVideo,
            InputMediaDocument,
            InputMediaAnimation,
        )

        try:
            album = json.loads(raw)  # {"items": [...], "caption": "..."}
        except Exception:
            # не валидный JSON — просто помечаем как отправленный и выходим
            await mark_post_as_sent(post_id)
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
            await bot.send_media_group(chat_id, media)

        await mark_post_as_sent(post_id)
        return

    # ---------- SINGLE MEDIA ----------
    try:
        data = json.loads(raw)
    except Exception:
        await mark_post_as_sent(post_id)
        return

    file_id = data.get("file_id")
    caption = data.get("caption")

    if post_type == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption)
    elif post_type == "video":
        await bot.send_video(chat_id, file_id, caption=caption)
    elif post_type == "document":
        await bot.send_document(chat_id, file_id, caption=caption)
    elif post_type == "audio":
        await bot.send_audio(chat_id, file_id, caption=caption)
    elif post_type == "voice":
        await bot.send_voice(chat_id, file_id, caption=caption)
    elif post_type == "animation":
        await bot.send_animation(chat_id, file_id, caption=caption)
    elif post_type == "video_note":
        await bot.send_video_note(chat_id, file_id)

    await mark_post_as_sent(post_id)


# ==========================================
#          SCHEDULE POST
# ==========================================


def schedule_post(bot: Bot, post_id: int, dt: datetime):
    scheduler.add_job(
        publish_post,
        "date",
        args=[bot, post_id],
        run_date=dt,
        id=f"post_{post_id}",
        misfire_grace_time=3600,  # 1 hour
    )


# ==========================================
#       RESCHEDULE (CHANGE TIME)
# ==========================================


def reschedule_post(post_id: int, new_dt: datetime):
    job_id = f"post_{post_id}"
    try:
        scheduler.reschedule_job(job_id, trigger="date", run_date=new_dt)
    except Exception:
        # если задачи не было — просто игнорируем
        pass


# ==========================================
#         REMOVE SCHEDULED POST
# ==========================================


def remove_scheduled_post(post_id: int):
    job_id = f"post_{post_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

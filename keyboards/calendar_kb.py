from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date, datetime
import calendar
import pytz

LA = pytz.timezone("America/New_York")

HOLIDAYS = {
    "01-01": "🎉",
    "02-14": "❤️",
    "03-08": "🌸",
    "07-04": "🗽",
    "10-31": "🎃",
    "12-25": "🎄",
}

TODAY_EMOJI = "🔵"
WEEKEND_EMOJI = "🟢"


def build_date_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Сегодня", callback_data="pick_date:today")],
            [
                InlineKeyboardButton(
                    text="📆 Завтра", callback_data="pick_date:tomorrow"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Через 2 дня", callback_data="pick_date:after2"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📖 Открыть календарь", callback_data="open_calendar"
                )
            ],
        ]
    )


def build_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    today = datetime.now(LA).date()
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # HEADER
    kb.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="«", callback_data=f"calendar_prev:{year}:{month}"
            ),
            InlineKeyboardButton(
                text=f"{calendar.month_name[month]} {year}", callback_data="ignore"
            ),
            InlineKeyboardButton(
                text="»", callback_data=f"calendar_next:{year}:{month}"
            ),
        ]
    )

    kb.inline_keyboard.append(
        [
            InlineKeyboardButton(text="Пн", callback_data="ignore"),
            InlineKeyboardButton(text="Вт", callback_data="ignore"),
            InlineKeyboardButton(text="Ср", callback_data="ignore"),
            InlineKeyboardButton(text="Чт", callback_data="ignore"),
            InlineKeyboardButton(text="Пт", callback_data="ignore"),
            InlineKeyboardButton(text="Сб", callback_data="ignore"),
            InlineKeyboardButton(text="Вс", callback_data="ignore"),
        ]
    )

    # DAYS
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
                continue

            d = date(year, month, day)
            mmdd = d.strftime("%m-%d")

            # disable past
            if d < today:
                row.append(
                    InlineKeyboardButton(text=f"·{day}·", callback_data="ignore")
                )
                continue

            # emoji
            emoji = ""
            if d == today:
                emoji = TODAY_EMOJI
            elif mmdd in HOLIDAYS:
                emoji = HOLIDAYS[mmdd]
            elif d.weekday() >= 5:
                emoji = WEEKEND_EMOJI

            row.append(
                InlineKeyboardButton(
                    text=f"{emoji} {day}",
                    callback_data=f"calendar_pick:{d.strftime('%Y-%m-%d')}",
                )
            )

        kb.inline_keyboard.append(row)

    # FOOTER
    kb.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅ Назад", callback_data="calendar_close")]
    )

    return kb

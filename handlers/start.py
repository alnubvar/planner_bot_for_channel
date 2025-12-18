from aiogram import Router, types
from aiogram.filters import Command
from keyboards.main_menu import admin_menu

router = Router()

ADMIN_ID = [8120213148, 882428172]  # теперь список, но имя то же!


def register_start_handlers(dp):
    dp.include_router(router)


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id in ADMIN_ID:  # <<< вот это единственное важное изменение
        await message.answer(
            "Приветствую, Ирина! 😊\nВыбери действие:", reply_markup=admin_menu()
        )
    else:
        await message.answer("Привет! Это бот-планировщик постов Ирины.")

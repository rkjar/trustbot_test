from aiogram import types
from aiogram.dispatcher.storage import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import ADMIN
from filters import IsNotBanned
from database import User
from loader import bot, dp
from keyboards.default import main_kbd
from keyboards.inline import request_kbd, back_to_main_kbd, skip_back_kbd
from database import requests
from states import UserLeaveRequestState
from utils import fio_format_editor, phone_format_editor


# TODO mediagroup handler, caption length

@dp.callback_query_handler(text='request_skip', state=UserLeaveRequestState.address)
async def skip_address(call: types.CallbackQuery, state: FSMContext):
    await call.message.delete()
    text = '<i><b>Шаг 2/3</b></i>. 🖼Прикрепите фотографию или видео к своей заявке или пропустите этот пункт:'
    await call.message.answer(text=text, reply_markup=skip_back_kbd(skip=True, back=True))
    await UserLeaveRequestState.media.set()
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.message_handler(state=UserLeaveRequestState.address)
async def request_address(message: types.Message, state: FSMContext):
    if len(message.text) > 4000:
        text = '📛 Длина сообщения более 4000 символов, что не допустимо! Попробуйте еще раз:'
        return await message.reply(text=text)
    async with state.proxy() as data:
        data['address'] = message.text
    text = '<i><b>Шаг 2/3</b></i>. 🖼Прикрепите фотографию или видео к своей заявке или пропустите этот пункт:'
    await message.answer(text=text, reply_markup=skip_back_kbd(skip=True, back=True))
    await UserLeaveRequestState.media.set()


@dp.callback_query_handler(text='request_skip', state=UserLeaveRequestState.media)
async def skip_media(call: types.CallbackQuery):
    await call.message.delete()
    text = '<i><b>Шаг 3/3.</b></i> 📛Напишите причину обращения в подробностях:'
    await call.message.answer(text=text, reply_markup=skip_back_kbd(back=True))
    await UserLeaveRequestState.reason.set()
    await bot.answer_callback_query(callback_query_id=call.id)


@dp.message_handler(content_types=types.ContentTypes.ANY, state=UserLeaveRequestState.media)
async def request_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.content_type not in ['photo', 'video']:
        text = f'⛔️📛 В данном пункте нужно обязательно отправить <b>фотографию</b> или <b>видео</b> ' \
               f'в виде медиа-сообщения. <i><b>Попробуйте еще раз</b>:</i>'
        await message.answer(text=text)
        await bot.delete_message(
            chat_id=message.from_user.id,
            message_id=message.message_id
        )
    else:
        if len(message.caption) > 1000:
            text = '📛 Длина подписи файла более 1000 символов, что не допустимо! Попробуйте еще раз:'
            return await message.reply(text=text)
        if message.photo:
            media = f'photo {message.photo[-1].file_id}'
        elif message.video:
            media = f'video {message.video.file_id}'
        async with state.proxy() as data:
            data['media'] = media
        text = '<i><b>Шаг 3/3.</b></i> 📛Напишите причину обращения в подробностях:'
        await message.answer(text=text, reply_markup=skip_back_kbd(back=True))
        await UserLeaveRequestState.reason.set()


@dp.message_handler(state=UserLeaveRequestState.reason)
async def request_reason(message: types.Message, session: AsyncSession, state: FSMContext):
    if len(message.text) > 4000:
        text = '📛 Длина сообщения более 4000 символов, что не допустимо! Попробуйте еще раз:'
        return await message.reply(text=text)
    async with state.proxy() as data:
        data['reason'] = message.text
    user: User = await requests.get_user(user_id=message.from_user.id, session=session)
    username = user.username if user.username else 'Пользователь'
    data = await state.get_data()
    text = '✅<b>Жалоба отправлена администрации.</b> <i>Спасибо за Ваше обращение!</i>'
    await message.answer(text=text)
    await state.finish()

    text_admin = f'<b>⛔Поступила новая жалоба</b>\n<a href="tg://user?id={user.telegram_id}">{username}</a>\n' \
                 f'<i><b>Имя и Фамилия:</b></i> {user.fio}\n' \
                 f'<i><b>Номер телефона:</b></i> {user.phone_number}\n' \
                 f'<i><b>Адрес:</b></i> {data.get("address", "Не указан")}\n' \
                 f'<i><b>Содержание:</b></i> {data.get("reason", "Не указано")}'

    if data.get('media'):
        media, file_id = data['media'].split()
        if media == 'photo':
            await bot.send_photo(chat_id=ADMIN, photo=file_id, caption=text_admin)
        elif media == 'video':
            await bot.send_video(chat_id=ADMIN, video=file_id, caption=text_admin)
    else:
        await bot.send_message(chat_id=ADMIN, text=text_admin)


@dp.callback_query_handler(text='request_back', state='*')
async def request_back(call: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state == UserLeaveRequestState.media.state:
        await call.message.delete()
        text = '<i><b>Шаг 1/3</b></i>. 📓 Напишите адрес или ориентир проблемы (улицу, номер дома, ' \
               'подъезд, этаж и квартиру) или пропустите этот пункт:'
        kbd = skip_back_kbd(skip=True, to_main=True)
        await call.message.answer(text=text, reply_markup=kbd)
        await UserLeaveRequestState.address.set()
    elif current_state == UserLeaveRequestState.reason.state:
        await skip_address(call=call, state=state)
    await bot.answer_callback_query(callback_query_id=call.id)

import logging
import sys
import os
import json
import requests
import requests_random_user_agent
from bs4 import BeautifulSoup

import asyncio

from aiohttp import web

from aiogram import Bot, Dispatcher, Router, types
from aiogram import F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold, hcode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from antiflood_middleware import AntiFloodMiddleware


# Bot token
TOKEN = '6423151141:AAGlh-YWeeHnGVZcwqZVid7vAs-5z7-hTOo'

# Webserver settings
WEB_SERVER_HOST = '0.0.0.0'
# Port for incoming requests
WEB_SERVER_PORT = 80

# Path to webhook route
WEBHOOK_PATH = '/webhook'
# Secret key to validate requests from Telegram
WEBHOOK_SECRET = 'cat3pillar7'
# Base URL for webhook will be used to generate webhook URL for Telegram
BASE_WEBHOOK_URL = 'https://one-d0ce.onrender.com'

PARTS_WEBSITE_URL = 'https://offroadeq.com/parts-search/{}/'
# EXCHANGE_RATE = 101.0
# COEFFICIENT_1 = 1.2
# COEFFICIENT_2 = 1.04
# COEFFICIENT_3 = 1.27

# SKU examples
# 1063969
# 1R0751
# 346-6687

PARAMS_VALUES_FILE = 'data/config.json'

router = Router()
router.message.middleware(AntiFloodMiddleware())


def get_price(sku: str) -> tuple[int, str, str]:
    sku = sku.lower()
    try:
        resp = requests.get(PARTS_WEBSITE_URL.format(sku))
    except Exception as e:
        return 1, str(e), ''
    if resp.status_code != 200:
        return 1, str(resp.status_code), ''
    html = resp.text
    with open('log.html', 'w') as f:
        f.write(html)
    soup = BeautifulSoup(html, 'lxml')
    result = soup.find('part-result').find('section')
    title = result.find('h2').text
    if 'UNKNOWN' in title:
        return 0, 'UNKNOWN',''
    part = result.find('part-items-app')
    price = str(part.get('price')).strip()
    return 2, title, price


def calculate_price(summ: str) -> float:
    with open(PARAMS_VALUES_FILE) as f:
        params = json.loads(f.read())
        EXCHANGE_RATE = float(params['EXCHANGE_RATE'])
        COEFFICIENT_1 = float(params['COEFFICIENT_1'])
        COEFFICIENT_2 = float(params['COEFFICIENT_2'])
        COEFFICIENT_3 = float(params['COEFFICIENT_3'])
    return round(float(summ) * EXCHANGE_RATE * COEFFICIENT_1 * COEFFICIENT_2 * COEFFICIENT_3, 2)


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    full_name = hbold(message.from_user.full_name)
    msg_text = f'Добро пожаловать, {full_name}!\nЭтот бот поможет найти вам нужные запчасти и цены.\nДля начала работы - отправьте в чат нужный вам артикул.'
    await message.answer(msg_text)


@router.message(F.text.startswith('!@#'))
async def params_edit(message: Message) -> None:
    with open(PARAMS_VALUES_FILE) as f:
        params = json.loads(f.read())
    msg = ''
    cmd = str(message.text).strip()
    if cmd.lower() == '!@#R'.lower():
        # Reading params from file
        msg += 'Значения переменных\n'
        for p in params.keys():
            msg += f'Параметр: {hbold(p)} Значение: {hbold(params[p])}\n'
        msg += '\n Для изменения значений переменных, введите комманду, указанную ниже\n!@#W [параметр] [значение]\nНапример:\n!@#W EXCHANGE_RATE 108.30'
    if cmd.lower().startswith('!@#W'.lower()):
        # Writing params into json file
        try:
            _, name, value = cmd.strip().split(' ')
        except Exception as e:
            msg = 'Неверный формат команды.'
            return await message.answer(msg)
        if name in params:
            try:
                params[name] = str(round(float(value), 2))
                with open(PARAMS_VALUES_FILE, 'w') as f:
                    f.write(json.dumps(params))
            except Exception as e:
                msg = 'Указано некорректное значение.'
            else:
                msg = f'Параметр {hbold(name)} успешно изменен.'
        else:
            msg = 'Параметр не найден либо указано некорректное значение.'
    await message.answer(msg)


@router.message(F.content_type.in_({'text',}))
async def search_part(message: Message) -> None:
    sku = str(message.text).strip()
    status, title, price = get_price(sku)
    if title.startswith(sku):
        title = ' '.join(title.split(sku + ' - ')[1:])
    if status == 0:
        msg = f'Запчасть с артикулом: {hbold(sku)} не найдена.'
    elif status == 1:
        msg = 'Ошибка выполнения запроса. Попробуйте другой артикул.'
    elif status == 2:
        end_price = str(calculate_price(price))
        end_price = f'{end_price} руб.'
        msg = f'{hbold("Результат поиска")}\n\n{hbold("SKU")}: {hcode(sku)}\n{hbold("Название")}: {hcode(title)}\n{hbold("Цена")}: {hcode(end_price)}'
    await message.answer(msg)


async def on_startup(bot: Bot) -> None:
    await bot.set_webhook(f'{BASE_WEBHOOK_URL}{WEBHOOK_PATH}', secret_token=WEBHOOK_SECRET)


def main() -> None:
    # Initialize Bot instance with a default parse mode
    # Remove webhooks first
    try:
        requests.get('https://api.telegram.org/bot{}/deleteWebhook'.format(TOKEN))
    except Exception as e:
        logging.error('Failed to make reset webhook request')
        exit()

    bot = Bot(TOKEN, parse_mode=ParseMode.HTML)

    # Dispatcher is a root router
    dp = Dispatcher()
    # All other routers should be attached to Dispatcher
    dp.include_router(router)

    if 'AMVERA' not in os.environ:
        print('POLLING mode.')
        asyncio.run(dp.start_polling(bot))

    else:
        print('WEBHOOK mode.')
        # Register startup hook to initialize webhook
        dp.startup.register(on_startup)

        # Create aiohttp.web.Application instance
        app = web.Application()

        # Create an instance of request handler,
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=WEBHOOK_SECRET,
        )
        # Register webhook handler on application
        webhook_requests_handler.register(app, path=WEBHOOK_PATH)

        # Mount dispatcher startup and shutdown hooks to aiohttp application
        setup_application(app, dp, bot=bot)

        # Start webserver
        web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()


import datetime
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

FLOOD_RATE = 8
ALERT_MESSAGE = 'Подозрение на спам.\nПовторите отправку через {} сек.'

class AntiFloodMiddleware(BaseMiddleware):
    time_updates: dict[int, datetime.datetime] = {}
    timedelta_limiter: datetime.timedelta = datetime.timedelta(seconds=FLOOD_RATE)

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id
            if user_id in self.time_updates.keys():
                if (datetime.datetime.now() - self.time_updates[user_id]) > self.timedelta_limiter:
                    self.time_updates[user_id] = datetime.datetime.now()
                    return await handler(event, data)
                else:
                    seconds = FLOOD_RATE - int((datetime.datetime.now() - self.time_updates[user_id]).seconds)
                    return await event.answer(ALERT_MESSAGE.format(str(seconds)))
            else:
                self.time_updates[user_id] = datetime.datetime.now()
                return await handler(event, data)

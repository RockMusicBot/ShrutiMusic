import asyncio
import importlib

from pyrogram import idle
from pytgcalls.exceptions import GroupCallNotFoundError

import config
from ShrutiMusic import LOGGER, app, userbot
from ShrutiMusic.core.call import Aviax
from ShrutiMusic.misc import sudo
from ShrutiMusic.plugins import ALL_MODULES
from ShrutiMusic.utils.database import get_banned_users, get_gbanned
from config import BANNED_USERS


async def init():
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error("Assistant client variables not defined, exiting...")
        exit()

    await sudo()

    try:
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)
        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
    except Exception as e:
        LOGGER("ShrutiMusic").warning(f"Error fetching banned users: {e}")

    await app.start()

    for all_module in ALL_MODULES:
        importlib.import_module("ShrutiMusic.plugins" + all_module)
    LOGGER("ShrutiMusic.plugins").info("Successfully Imported Modules...")

    await userbot.start()
    await Aviax.start()

    try:
        await Aviax.stream_call("https://te.legra.ph/file/29f784eb49d230ab62e9e.mp4")
    except GroupCallNotFoundError:
        LOGGER("ShrutiMusic").error(
            "Please start the video chat in your log group/channel first.\n\nStopping Bot..."
        )
        exit()
    except Exception as e:
        LOGGER("ShrutiMusic").error(f"Stream failed: {e}")
        exit()

    await Aviax.decorators()
    LOGGER("ShrutiMusic").info(
        "Shruti Music Started Successfully with PyTgCalls 2.x!\nVisit @ShrutiBots"
    )

    await idle()

    await app.stop()
    await userbot.stop()
    LOGGER("ShrutiMusic").info("Stopping Shruti Music Bot...")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(init())

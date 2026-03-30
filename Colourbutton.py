from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import enums

# 🔑 Apni details yaha daalo
API_ID = 123456
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

app = Client("color_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@app.on_message(filters.command("start"))
async def start(client, message):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔵 Blue (Primary)",
                    callback_data="blue",
                    style=enums.ButtonStyle.PRIMARY,
                )
            ],
            [
                InlineKeyboardButton(
                    "⚪ Grey (Secondary)",
                    callback_data="grey",
                    style=enums.ButtonStyle.SECONDARY,
                )
            ],
            [
                InlineKeyboardButton(
                    "🟢 Green (Success)",
                    callback_data="green",
                    style=enums.ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    "🔴 Red (Danger)",
                    callback_data="red",
                    style=enums.ButtonStyle.DANGER,
                )
            ],
        ]
    )

    await message.reply_text(
        "👋 Hello sir!\n\nYaha 4 colored buttons hai 👇",
        reply_markup=keyboard
    )


@app.on_callback_query()
async def callbacks(client, query):
    await query.answer(f"You clicked {query.data} button!")


app.run()

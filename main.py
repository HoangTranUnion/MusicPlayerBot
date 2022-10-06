import discord, asyncio
from pathlib import Path
from constants import BOT_PREFIX, TOKEN, REMINE_ID
from discord.ext.commands import Bot, is_owner

intents = discord.Intents.default()
intents.message_content = True

bot = Bot(command_prefix=BOT_PREFIX, intents = intents)
client = discord.Client(intents = intents)

extensions = [f"src.cogs.{path.stem}" for path in Path('src/cogs').glob('*.py')]


@bot.event
async def on_ready():
    print("The bot is live~")


@bot.command()
@is_owner()
async def load(ctx, extension):
    if ctx.author.id == REMINE_ID:
        try:
            await bot.load_extension(extension)
            print(f"Loaded {extension}")
            await ctx.send(f"Loaded {extension}")
        except Exception as e:
            print('{} cannot be loaded.[{}]'.format(extension, e))
            await ctx.send('{} cannot be loaded.'.format(extension))
    else:
        await ctx.send("You are not authorized to use this command")


@bot.command()
@is_owner()
async def unload(ctx, extension):
    if ctx.author.id == REMINE_ID:
        try:
            await bot.unload_extension(extension)
            print(f"Unloaded {extension}")
            await ctx.send(f"Unloaded {extension}")
        except Exception as e:
            print(f'{extension} cannot be unloaded.[{e}]')
            await ctx.send(f'{extension} cannot be unloaded.')
    else:
        await ctx.send("You are not authorized to use this command")


@bot.command()
@is_owner()
async def reload(ctx, extension):
    if ctx.author.id == REMINE_ID:
        try:
            await bot.reload_extension(extension)
            print(f"Reloaded {extension}")
            await ctx.send(f"Reloaded {extension}")
        except Exception as e:
            print(f'{extension} cannot be reloaded.[{e}]')
            await ctx.send(f'{extension} cannot be reloaded.[{e}]')
    else:
        await ctx.send("You are not authorized to use this command")


if __name__ =='__main__':
    for extension in extensions:
        try:
            asyncio.run(bot.load_extension(extension))
            print(f"Loaded {extension}")
        except Exception as e:
            print(f"{extension} cannot be loaded: {e}")
    bot.run(TOKEN)
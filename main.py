import discord, asyncio
from pathlib import Path
from constants import BOT_PREFIX, TOKEN, MUSIC_STORAGE
from discord.ext.commands import Bot, is_owner

intents = discord.Intents.default()
intents.message_content = True

bot = Bot(command_prefix=BOT_PREFIX, intents = intents)
bot.remove_command('help')
client = discord.Client(intents = intents)

extensions = [f"src.cogs.{path.stem}" for path in Path('src/cogs').glob('*.py')]


@bot.event
async def on_ready():
    print("The bot is live~")


@bot.command()
@is_owner()
async def load(ctx, extension):
    try:
        await bot.load_extension(extension)
        print(f"Loaded {extension}")
        await ctx.send(f"Loaded {extension}")
    except Exception as e:
        print('{} cannot be loaded.[{}]'.format(extension, e))
        await ctx.send('{} cannot be loaded.'.format(extension))
    


@bot.command()
@is_owner()
async def unload(ctx, extension):
    try:
        await bot.unload_extension(extension)
        print(f"Unloaded {extension}")
        await ctx.send(f"Unloaded {extension}")
    except Exception as e:
        print(f'{extension} cannot be unloaded.[{e}]')
        await ctx.send(f'{extension} cannot be unloaded.')
    

@bot.command()
@is_owner()
async def reload(ctx, extension):
    try:
        await bot.reload_extension(extension)
        print(f"Reloaded {extension}")
        await ctx.send(f"Reloaded {extension}")
    except Exception as e:
        print(f'{extension} cannot be reloaded.[{e}]')
        await ctx.send(f'{extension} cannot be reloaded.[{e}]')
    

@load.error
@unload.error
@reload.error
async def error_msg(ctx, extension):
    await ctx.send("You are not authorized to use this command")


if __name__ =='__main__':
    import glob, os, os.path

    filelist = glob.glob(os.path.join(MUSIC_STORAGE, "*.mp3"))
    for f in filelist:
        os.remove(f)

    try:
        os.makedirs(MUSIC_STORAGE, mode=0o777)
    except FileExistsError:
        pass

    for extension in extensions:
        try:
            asyncio.run(bot.load_extension(extension))
            print(f"Loaded {extension}")
        except Exception as e:
            print(f"{extension} cannot be loaded: {e}")
    bot.run(TOKEN)
import discord
from discord.ext import commands


class Core(commands.Cog):
    def __init__(self, bot:commands.Bot):
        self._bot = bot

    @commands.command(name = "help", aliases = ['h'])
    async def help(self, ctx):
        embed = discord.Embed(title = "Help!",
                              description= "Command prefix: >3",
                              color = discord.Color.blue())
        embed.add_field(
            name = ">3play <url/query>",
            value = "Play the audio from the given url, or play a song chosen/auto-picked from the query.",
            inline = False
        )

        embed.add_field(
            name = ">3pause",
            value = "Pauses the current media",
            inline = False
        )

        embed.add_field(
            name = ">3resume",
            value = "Resumes the current media",
            inline = False
        )

        embed.add_field(
            name = ">3queue/q/playlist",
            value = "Checks the current queue",
            inline = False
        )

        embed.add_field(
            name = ">3skip",
            value = "Skips the current song. The current song will be repeated if loop is set for the song.",
            inline = False
        )

        embed.add_field(
            name = ">3fskip/forceskip/force_skip",
            value = "Skips the current song regardless of loop status. Next song will not be looped using this command.",
            inline = False
        )

        embed.add_field(
            name = ">3loop <optional: number of times to loop>",
            value = "Loops the curent media. If a number of times is specified, the song will be looped for that number of times.",
            inline = False
        )

        embed.add_field(
            name=">3shuffle",
            value="Shuffles the queue",
            inline=False
        )

        embed.add_field(
            name = ">3clear",
            value = "Clears the current queue",
            inline = False
        )

        embed.add_field(
            name = ">3set_state",
            value = "Sets either the bot to select the first song found immediately or allow the user to select on input being a query. Requires admin.",
            inline = False
        )

        await ctx.send(embed = embed)


async def setup(bot):
    await bot.add_cog(Core(bot))

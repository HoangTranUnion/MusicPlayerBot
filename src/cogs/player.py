from discord.ext import commands, tasks
import discord
import asyncio
import os
from copy import deepcopy
from src.player.youtube.verify_link import is_valid_link
from src.player.youtube.search import SearchVideos
from src.player.youtube.media_metadata import MediaMetadata
from src.player.youtube.load_url import LoadURL
from src.player.youtube.download_media import Downloader, NoVideoInQueueError, isExist, SingleDownloader
from typing import List, Dict, Union
from datetime import timedelta
from collections import defaultdict
import random
from constants import MUSIC_STORAGE, MAX_MSG_EMBED_SIZE
from yt_dlp import YoutubeDL
import functools
from timeit import default_timer

YOUTUBEDL_PARAMS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': os.path.join(MUSIC_STORAGE, '%(id)s.%(ext)s')
}

MAX_QUEUE_SIZE = 50  # not implemented - basically max queue size possible supported.


class Player(commands.Cog):
    _NO_LOOP = 0
    _LOOP = 1

    _AUTO_PICK_FIRST_VIDEO = 0
    _SELECT_VIDEO = 1

    _NEW_PLAYER = 1
    _REFRESH_PLAYER = 0

    _FFMPEG_OPTIONS = {
        'options': '-vn',
    }

    def __init__(self, bot):
        self._bot = bot
        self._queue: Dict[int, List[MediaMetadata]] = defaultdict(list)
        self._loop: Dict[int] = defaultdict(lambda: self._NO_LOOP)
        self._select_video: Dict[int] = defaultdict(lambda: self._SELECT_VIDEO)
        self._cur_song: Dict[int, Union[MediaMetadata, None]] = defaultdict(lambda: None)
        self._previous_song: Dict[int, Union[MediaMetadata, None]] = defaultdict(lambda: None)
        self._players: Dict[int, discord.FFmpegPCMAudio] = {}

    @staticmethod
    def _delete_files(song_metadata: MediaMetadata):
        fp = os.path.join(MUSIC_STORAGE, f"{song_metadata.id}.mp3")
        try:
            if os.path.isfile(fp) or os.path.islink(fp):
                os.unlink(fp)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (fp, e))

    def get_players(self, ctx, job=_NEW_PLAYER):
        guild_id = ctx.guild.id
        if guild_id in self._players and job:
            return self._players[guild_id]
        else:
            player = discord.FFmpegPCMAudio(os.path.join(MUSIC_STORAGE, f"{self._cur_song[guild_id].id}.mp3"),
                                            **self._FFMPEG_OPTIONS)
            self._players[guild_id] = player
            return player

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        # add cases where ALL users left the VC and the bot is left idle for some time.

        if member.bot and member.id == self._bot.user.id:
            if before.channel and not after.channel:
                guild_id = member.guild.id
                bogus_queue = deepcopy(self._queue[guild_id])
                for item in bogus_queue:
                    self._delete_files(item)
                self._queue[guild_id].clear()
                self._cur_song[guild_id] = None
                try:
                    del self._players[guild_id]
                except KeyError:
                    pass
                self._loop[guild_id] = self._NO_LOOP

                print(f"cleared in guild id {guild_id}")

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def play(self, ctx, *, url_: str):
        """
        Allows the bot to play audio in the voice channel.
        Subsequent calls from users in the same channel will add more media entries to the queue.
        At the moment, the bot only supports YouTube and Bilibili links.
        :param ctx:
        :param url_:
        :return:
        """

        guild_id = ctx.guild.id

        def check_valid_input(m):
            return m.author == ctx.author and m.channel == ctx.channel

        async def run_blocker(client, func, *args, **kwargs):
            func_ = functools.partial(func, *args, **kwargs)
            return await client.loop.run_in_executor(None, func_)

        if is_valid_link(url_):
            load_sesh = LoadURL(url_)
            data = await run_blocker(self._bot, load_sesh.load_info)
        elif self._select_video[guild_id]:
            sv_obj = SearchVideos()
            result: List[MediaMetadata] = await run_blocker(self._bot, sv_obj.search, url_)
            results_embed = discord.Embed(
                color=discord.Color.blue()
            )
            r_link = ""
            for res_ind, res in enumerate(result):
                if res_ind != len(result) - 1:
                    r_link += f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({self._time_split(res.duration)})\n"
                else:
                    r_link += f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({self._time_split(res.duration)})\n"

            results_embed.add_field(
                name="Select a video.",
                value=r_link,
                inline=False
            )
            results_embed.set_footer(text="Timeout in 30s")
            await ctx.send(embed=results_embed)

            q_msg = await self._bot.wait_for('message', check=check_valid_input, timeout=30)

            if q_msg.content.isdigit() and 1 <= int(q_msg.content) <= 5:
                data = [result[int(q_msg.content)]]
            else:
                return await ctx.send("Illegal input. Terminated search session.")
        else:
            sv_obj = SearchVideos(limit=1)
            data: List[MediaMetadata] = await run_blocker(self._bot, sv_obj.search, url_)
        if data is not None:
            data_l = len(data)
            if data_l == 1:
                msg = f"Added {data[0].title} to the queue."
            else:
                msg = f"Added {data_l} songs to the queue."
            try:
                voiceChannel = discord.utils.get(
                    ctx.message.guild.voice_channels,
                    name=ctx.author.guild.get_member(ctx.author.id).voice.channel.name
                )
            except AttributeError:
                return await ctx.send('You need to be in a voice channel to use this command')

            self._queue[guild_id].extend(data)
            await ctx.send(msg)
            with YoutubeDL(YOUTUBEDL_PARAMS) as ydl:
                try:
                    obj = Downloader(data, ydl)
                    await run_blocker(self._bot, obj.first_download)
                except NoVideoInQueueError:
                    return await ctx.send("No items are currently in queue")

            if data_l > 1:
                self._bg_download_check.start(ctx)

            if not self._is_connected(ctx):
                await self.peek_vc(ctx)
                await voiceChannel.connect()
                # await ctx.send(data)

            voice = ctx.voice_client
            await self.play_song(ctx, voice)

    @play.error
    async def play_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("Slow down a bit, I am processing the previous request.")

    @tasks.loop(minutes=1)
    async def _bg_download_check(self, ctx):
        async def run_blocker(client, func, *args, **kwargs):
            func_ = functools.partial(func, *args, **kwargs)
            return await client.loop.run_in_executor(None, func_)

        guild_id = ctx.guild.id

        for item in self._queue[guild_id]:
            if not isExist(item):
                with YoutubeDL(YOUTUBEDL_PARAMS) as ydl_sesh:
                    down_sesh = SingleDownloader(item, ydl_sesh)
                    await run_blocker(self._bot, down_sesh.download)

    async def play_song(self, ctx, voice):
        guild_id = ctx.guild.id

        def repeat(guild, voice_, audio):
            voice_.play(audio, after=lambda e: repeat(guild, voice, audio))
            voice_.is_playing()

        if self._loop[guild_id]:
            player = self.get_players(ctx, job = self._REFRESH_PLAYER)
            ctx.voice_client.play(
                player,
                after=lambda e:
                print('Player error: %s' % e) if e else repeat(ctx.guild, ctx.voice_client, player)
            )
        else:
            if not voice.is_playing():
                async with ctx.typing():
                    try:
                        self._cur_song[guild_id] = self._queue[guild_id].pop(0)
                    except IndexError:
                        self._cur_song[guild_id] = None
                    if self._cur_song[guild_id] is None:
                        await voice.disconnect()
                        return

                    player = self.get_players(ctx)
                    voice.play(
                        player,
                        after=lambda e:
                        print('Player error: %s' % e) if e else self.play_next(ctx)
                    )
                await ctx.send('**Now playing:** {}'.format(self._cur_song[guild_id].title), delete_after=20)
            else:
                await asyncio.sleep(1)

    def play_next(self, ctx):
        guild_id = ctx.guild.id

        def repeat(guild, voice, audio):
            voice.play(audio, after=lambda e: repeat(guild, voice, audio))
            voice.is_playing()

        vc = discord.utils.get(self._bot.voice_clients, guild=ctx.guild)

        if self._loop[guild_id]:
            player = self.get_players(ctx, self._REFRESH_PLAYER)
            ctx.voice_client.play(
                player,
                after=lambda e:
                print('Player error: %s' % e) if e else repeat(ctx.guild, ctx.voice_client, player)
            )
        else:
            if len(self._queue[guild_id]) >= 1:
                try:
                    self._previous_song[guild_id] = self._cur_song[guild_id]
                    self._cur_song[guild_id] = self._queue[guild_id].pop(0)
                    if not isExist(self._cur_song[guild_id]):
                        self._queue[guild_id].insert(0, self._cur_song[guild_id])
                        self._cur_song[guild_id] = self._previous_song[guild_id]
                        self._previous_song[guild_id] = None
                        raise IOError("File not exist just yet")
                except IndexError:
                    self._cur_song[guild_id] = None
                if self._cur_song[guild_id] is None:
                    asyncio.run_coroutine_threadsafe(ctx.send("Finished playing"), ctx.bot.loop)
                    asyncio.run_coroutine_threadsafe(ctx.voice_client.disconnect(), ctx.bot.loop)
                    return

                vc.play(self.get_players(ctx, job=self._REFRESH_PLAYER), after=lambda e: self.play_next(ctx))
                asyncio.run_coroutine_threadsafe(ctx.send(
                    f'**Now playing:** {self._cur_song[guild_id].title}',
                    delete_after=20
                ), ctx.bot.loop)
            else:
                if not vc.is_playing():
                    asyncio.run_coroutine_threadsafe(vc.disconnect(), self._bot.loop)
                asyncio.run_coroutine_threadsafe(ctx.send("Finished playing!"), ctx.bot.loop)

    @staticmethod
    def _time_split(time: int):
        return str(timedelta(seconds=time))

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx):
        guild_id = ctx.guild.id
        await ctx.send(self._queue[guild_id])
        if self._cur_song[guild_id] is not None:
            await ctx.send(self._cur_song[guild_id])
        else:
            await ctx.send("Currently no song is playing")

        await ctx.send(self._queue)
        await ctx.send(self._cur_song)

    @commands.command(name='stop')
    async def stop_(self, ctx):
        """Stops and disconnects the bot from voice"""
        guild_id = ctx.guild.id
        await self.peek_vc(ctx)

        if self._is_connected(ctx):
            await ctx.voice_client.disconnect()
        else:
            await ctx.send("I am not in any voice chat right now")
        self._queue[guild_id].clear()

    @commands.command(name="skip")
    async def skip_(self, ctx):
        """
        Skips to next song in queue
        """
        await self.peek_vc(ctx)

        if self._is_connected(ctx):
            ctx.voice_client.pause()
            try:
                self.play_next(ctx)
            except IOError:
                ctx.voice_client.resume()
                return await ctx.send("The next media file is not ready to be played just yet - please be patient.")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name="pause")
    async def pause(self, ctx):
        await self.peek_vc(ctx)

        if self._is_connected(ctx):
            ctx.voice_client.pause()
            await ctx.send("Paused!")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name='resume')
    async def resume(self, ctx):
        await self.peek_vc(ctx)

        if self._is_connected(ctx):
            ctx.voice_client.resume()
            await ctx.send("Resumed!")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name="queue", aliases=["q", "playlist"])
    async def queue_(self, ctx):
        await self.peek_vc(ctx)

        guild_id = ctx.guild.id

        if self._is_connected(ctx):
            cur_playing_embed = discord.Embed(
                color=discord.Color.blue()
            )

            cur_playing_embed.add_field(
                name="Currently playing",
                value=f"**[{self._cur_song[guild_id].title}]({self._cur_song[guild_id].original_url})** ({self._time_split(self._cur_song[guild_id].duration)})\n"
            )

            await ctx.send(embed=cur_playing_embed)

            all_additional_embeds_created = False
            all_embeds = []
            cur_index = 0
            if self._queue[guild_id]:
                while not all_additional_embeds_created:
                    next_playing_embed = discord.Embed(
                        color=discord.Color.blue()
                    )

                    r_link = ""
                    max_reached = False
                    while not max_reached and cur_index < len(self._queue[guild_id]):
                        res_ind = cur_index
                        res = self._queue[guild_id][res_ind]
                        string = f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({self._time_split(res.duration)})\n"
                        if len(r_link) <= MAX_MSG_EMBED_SIZE - len(string):
                            r_link += string
                            cur_index += 1
                        else:
                            max_reached = True
                    if cur_index == len(self._queue[guild_id]):
                        all_additional_embeds_created = True
                    if r_link != "":
                        next_playing_embed.add_field(
                            name="Next songs",
                            value=r_link,
                            inline=False
                        )
                    all_embeds.append(next_playing_embed)
            for e_ind, embed in enumerate(all_embeds):
                embed.set_footer(text=f"Page {e_ind + 1}/{len(all_embeds)}")
                await ctx.send(embed=embed)
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name='clear')
    async def clear_(self, ctx):
        guild_id = ctx.guild.id
        await self.peek_vc(ctx)

        self._queue[guild_id].clear()
        await ctx.send("Queue cleared!")

    @commands.command(name='loop')
    async def loop(self, ctx):
        await self.peek_vc(ctx)
        guild_id = ctx.guild.id

        if self._loop[guild_id]:
            self._loop[guild_id] = self._NO_LOOP
            await ctx.send("No longer looping current song.")
        else:
            self._loop[guild_id] = self._LOOP
            await ctx.send("Looping current song.")

    @commands.command(name='shuffle')
    async def shuffle(self, ctx):
        await self.peek_vc(ctx)

        guild_id = ctx.guild.id
        if self._queue[guild_id]:
            random.shuffle(self._queue[guild_id])
            await ctx.send("Queue is shuffled. To check current queue, please use >3queue, or >3q")
        else:
            await ctx.send("There is nothing to be shuffled.")

    @commands.command(name='set_song_choosing_state', aliases=['set_state'])
    @commands.has_permissions(administrator=True)
    async def set_state(self, ctx):
        """
        Changes from either selecting songs or just pick the first one while searching.
        Requires admin privilege in the server or the bot would just be abused back and forth.
        """
        guild_id = ctx.guild.id
        if self._select_video[guild_id]:
            self._select_video[guild_id] = self._AUTO_PICK_FIRST_VIDEO
            await ctx.send("Changed to auto select the first one on search.")
        else:
            self._select_video[guild_id] = self._SELECT_VIDEO
            await ctx.send("Changed to manually select video from search.")

    @set_state.error
    async def set_state_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            msg = f"You don't have the privilege to set this {ctx.message.author.mention}."
            await ctx.send(msg)

    @staticmethod
    async def peek_vc(ctx):
        """
        Checks to see if the author is in any vc or not.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            # Exiting if the user is not in a voice channel
            return await ctx.send('You need to be in a voice channel to use this command')

    @staticmethod
    async def idle_wait(ctx, ori_time):
        elapsed = default_timer() - ori_time
        if elapsed > 5:
            await ctx.send("This will take a while to load, please be patient")
        elif elapsed > 60:
            await ctx.send("This is taking longer than expected, please be patient...")

    def _is_connected(self, ctx):
        return discord.utils.get(self._bot.voice_clients, guild=ctx.guild)


async def setup(bot):
    await bot.add_cog(Player(bot))

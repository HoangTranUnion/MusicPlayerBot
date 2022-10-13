from discord.ext import commands, tasks
import discord
import asyncio
import os
from copy import deepcopy
from typing import Union
from datetime import timedelta
import random
import inspect
from yt_dlp import YoutubeDL
import functools
from timeit import default_timer
from constants import MUSIC_STORAGE, MAX_MSG_EMBED_SIZE, CONFIG_FILE_LOC
from src.player.youtube.verify_link import is_valid_link
from src.player.youtube.search import SearchVideos
from src.player.youtube.media_metadata import MediaMetadata
from src.player.youtube.load_url import LoadURL
from src.player.youtube.download_media import Downloader, NoVideoInQueueError, isExist, SingleDownloader
from src.player.observers import *
from src.data_transfer import *
from src.configs import Config


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


async def run_blocker(client, func, *args, **kwargs):
    func_ = functools.partial(func, *args, **kwargs)
    return await client.loop.run_in_executor(None, func_)


def _time_split(time: int):
    return str(timedelta(seconds=time))


class Job:
    def __init__(self, job_name: str, work: str):
        self.job = job_name  # accepts either "search" or "access"
        self.work = work


YT_DLP_SESH = YoutubeDL(YOUTUBEDL_PARAMS)


class RequestQueue(DownloaderObservers):
    def __init__(self, observer = DownloaderObservable()):
        super().__init__(observer)
        self.priority: Union[Job, None] = None
        self.on_hold: List[Job] = []
        self._completed_priority = False
        self._ongoing_process = False
    
    def add_new_request(self, job: Job):
        if self.priority is None and not self.on_hold:
            self.priority = job
        elif self.priority is None:
            self.priority = self.on_hold.pop(0)
            self.on_hold.append(job)
        else:
            self.on_hold.append(job)

    def update(self):
        if inspect.stack()[1][3] == "notify_observers":
            self._completed_priority = True

    async def process_requests(self, client, ctx: commands.Context, vault: Vault, selector_choice):
        """
        Projected solution:
            - If self.priority is not None, proceed to download the file(s) in the playlist given in self.priority
            - Other than that, pop one from on_hold and let the process continues
            - If priority is None, and the on_hold list is empty, nothing needs to be done at all. We done!

            - If the download process is completed for one list, continue with the next one.
        """
        def check_valid_input(m):
            return m.author == ctx.author and m.channel == ctx.channel

        if self.priority is not None and self._ongoing_process:
            while not self._completed_priority:
                await asyncio.sleep(1)
            self._completed_priority = False
            self._ongoing_process = False
            await self.process_requests(client, ctx, vault, selector_choice)
        elif self.priority is not None and not self._completed_priority:
            self._ongoing_process = True
            guild_id = ctx.guild.id
            new_sender = Sender(guild_id, vault)

            url_ = self.priority.work
            if self.priority.job == "search":
                if not selector_choice:
                    sv_obj = SearchVideos()
                    sv_obj.subscribe(self)
                    result: List[MediaMetadata] = await run_blocker(client, sv_obj.search, url_)
                    results_embed = discord.Embed(
                        color=discord.Color.blue()
                    )
                    r_link = ""
                    for res_ind, res in enumerate(result):
                        if res_ind != len(result) - 1:
                            r_link += f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({_time_split(res.duration)})\n"
                        else:
                            r_link += f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({_time_split(res.duration)})\n"

                    results_embed.add_field(
                        name="Select a video.",
                        value=r_link,
                        inline=False
                    )
                    results_embed.set_footer(text="Timeout in 30s")
                    await ctx.send(embed=results_embed)

                    try:
                        q_msg = await client.wait_for('message', check=check_valid_input, timeout=30)
                    except asyncio.TimeoutError:
                        self.priority = None
                        return await ctx.send(f"Timeout! Search session for query {url_} terminated.")
                    sv_obj.unsubscribe(self)
                    if q_msg.content.isdigit() and 1 <= int(q_msg.content) <= 5:
                        data = [result[int(q_msg.content) - 1]]
                    else:
                        self.priority = None  # reset. This session no longer exists
                        return await ctx.send("Illegal input. Terminated search session.")
                else:
                    sv_obj = SearchVideos(limit=1)
                    sv_obj.subscribe(self)
                    data: List[MediaMetadata] = await run_blocker(client, sv_obj.search, url_)
                    sv_obj.unsubscribe(self) # avoid the bot to store far too many unnecessary observants.
            else:
                load_sesh = LoadURL(url_)
                load_sesh.subscribe(self)
                data = await run_blocker(client, load_sesh.load_info)
                load_sesh.unsubscribe(self)

            new_sender.send(data)
            self.priority = None
        elif self.priority is None and self.on_hold:
            self.priority = self.on_hold.pop(0)
            await self.process_requests(client, ctx, vault, selector_choice)
    

class Player(commands.Cog):
    _NO_LOOP = 0
    _LOOP = 1

    # _AUTO_PICK_FIRST_VIDEO = 0
    # _SELECT_VIDEO = 1

    _NEW_PLAYER = 1
    _REFRESH_PLAYER = 0

    _FFMPEG_OPTIONS = {
        'options': '-vn',
    }

    _ACCESS_JOB = "access"
    _SEARCH_JOB = "search"

    def __init__(self, bot):
        self._bot = bot
        self._queue: Dict[int, List[MediaMetadata]] = defaultdict(list)
        self._request_queue: Dict[int, RequestQueue] = defaultdict(lambda: RequestQueue())
        self._loop: Dict[int] = defaultdict(lambda: self._NO_LOOP)
        # self._select_video: Dict[int] = defaultdict(lambda: self._SELECT_VIDEO)
        self._cur_song: Dict[int, Union[MediaMetadata, None]] = defaultdict(lambda: None)
        self._previous_song: Dict[int, Union[MediaMetadata, None]] = defaultdict(lambda: None)
        self._players: Dict[int, discord.FFmpegPCMAudio] = {}
        self._vault = Vault()
        self._cur_processing: Dict[int, bool] = defaultdict(lambda: False)
        self._pre_play_processing: Dict[int, bool] = defaultdict(lambda: False)
        self._bot_config = Config(CONFIG_FILE_LOC)

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
    async def play(self, ctx, *, url_: str):
        """
        Allows the bot to play audio in the voice channel.
        Subsequent calls from users in the same channel will add more media entries to the queue.
        At the moment, the bot only supports YouTube links.
        :param ctx:
        :param url_:
        :return:
        """
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        if not url_.strip():
            return await ctx.send("No input has been given")
        guild_id = ctx.guild.id

        if is_valid_link(url_):
            cmd_job = self._ACCESS_JOB
        else:
            cmd_job = self._SEARCH_JOB
        self._request_queue[guild_id].add_new_request(Job(cmd_job, url_))
        if not self._cur_processing[guild_id]:
            self._cur_processing[guild_id] = True
            self._bot.loop.create_task(self.bg_process_rq(ctx))

        while self._vault.isEmpty(guild_id):
            await asyncio.sleep(1)

        # both runs at the same time from here.
        data = self._vault.get_data(guild_id)

        if data is not None:
            data_l = len(data)
            if data_l == 1:
                msg = f"Added {data[0].title} to the queue."
            else:
                msg = f"Added {data_l} songs to the queue."

            self._queue[guild_id].extend(data)
            await ctx.send(msg)

            try:
                voiceChannel = discord.utils.get(
                    ctx.message.guild.voice_channels,
                    name=ctx.author.guild.get_member(ctx.author.id).voice.channel.name
                )
            except AttributeError:
                return await ctx.send('You need to be in a voice channel to use this command')

            await self.pre_play_process(ctx, data,voiceChannel)

    async def pre_play_process(self, ctx, data, voiceChannel):
        """
        Processes the data before playing the songs in the voice channel.

        Args:
            ctx (commands.Context): Context of the command
            data (List[MediaMetadata]): The data to be processed
            voiceChannel (_type_): The voice channel to connect to

        """
        guild_id = ctx.guild.id
        if self._pre_play_processing[guild_id]:
            await asyncio.sleep(1)
            await self.pre_play_process(ctx, data, voiceChannel)
        else:
            try:
                obj = Downloader(data, YT_DLP_SESH)
                await run_blocker(self._bot, obj.first_download)
            except NoVideoInQueueError:
                return await ctx.send("No items are currently in queue")

            if len(data) > 1:
                self.bg_download_check.start(ctx)

            if not self._is_connected(ctx):
                await voiceChannel.connect()

            voice = ctx.voice_client
            self._pre_play_processing[guild_id] = False
            try:
                await self.play_song(ctx, voice)
            except discord.errors.ClientException:
                pass

    async def bg_process_rq(self, ctx):
        """ Processes the requests in the background

        Args:
            ctx (commands.Context): Context of the command
        """
        guild_id = ctx.guild.id
        while True:
            if self._request_queue[guild_id].on_hold or self._request_queue[guild_id].priority is not None:
                await self._request_queue[guild_id].process_requests(self._bot, ctx, self._vault, self._bot_config.isAutoPick(guild_id))
            else:
                self._cur_processing[guild_id] = False
                break

    @tasks.loop(seconds = 20)
    async def bg_download_check(self, ctx):
        guild_id = ctx.guild.id

        for item in self._queue[guild_id]:
            if not isExist(item):
                down_sesh = SingleDownloader(item, YT_DLP_SESH)
                await run_blocker(self._bot, down_sesh.download)

    async def play_song(self, ctx, voice):
        guild_id = ctx.guild.id

        def repeat(guild, voice_, audio):
            voice_.play(audio, after=lambda e: repeat(guild, voice, audio))
            voice_.is_playing()

        if self._loop[guild_id]:
            player = self.get_players(ctx, job=self._REFRESH_PLAYER)
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
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

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
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

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
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        if self._is_connected(ctx):
            ctx.voice_client.pause()
            await ctx.send("Paused!")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name='resume')
    async def resume(self, ctx):
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        if self._is_connected(ctx):
            ctx.voice_client.resume()
            await ctx.send("Resumed!")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name="queue", aliases=["q", "playlist"])
    async def queue_(self, ctx):
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        guild_id = ctx.guild.id

        if self._is_connected(ctx):
            cur_playing_embed = discord.Embed(
                color=discord.Color.blue()
            )

            cur_playing_embed.add_field(
                name="Currently playing",
                value=f"**[{self._cur_song[guild_id].title}]({self._cur_song[guild_id].original_url})** ({_time_split(self._cur_song[guild_id].duration)})\n"
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
                        string = f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({_time_split(res.duration)})\n"
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
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        self._queue[guild_id].clear()
        await ctx.send("Queue cleared!")

    @commands.command(name='loop')
    async def loop(self, ctx):
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")
        guild_id = ctx.guild.id

        if self._loop[guild_id]:
            self._loop[guild_id] = self._NO_LOOP
            await ctx.send("No longer looping current song.")
        else:
            self._loop[guild_id] = self._LOOP
            await ctx.send("Looping current song.")

    @commands.command(name='shuffle')
    async def shuffle(self, ctx):
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

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
        self._bot_config.set_state(guild_id)
        if self._bot_config.isAutoPick(guild_id):
            await ctx.send("Changed to auto select the first one on search.")
        else:
            await ctx.send("Changed to manually select video from search.")

    @set_state.error
    async def set_state_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            msg = f"You don't have the privilege to set this {ctx.message.author.mention}."
            await ctx.send(msg)

    @staticmethod
    def peek_vc(ctx):
        """
        Checks to see if the author is in any vc or not.
        """
        voice_state = ctx.author.voice

        if voice_state is None:
            # Exiting if the user is not in a voice channel
            return False

        return True

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

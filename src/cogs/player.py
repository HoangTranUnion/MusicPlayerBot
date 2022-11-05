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
from constants import MUSIC_STORAGE, MAX_MSG_EMBED_SIZE, CONFIG_FILE_LOC, BOT_PREFIX
from src.player.youtube.verify_link import is_valid_link
from src.player.youtube.search import SearchVideos
from src.player.youtube.media_metadata import MediaMetadata
from src.player.youtube.load_url import LoadURL
from src.player.youtube.download_media import Downloader, NoVideoInQueueError, isExist, SingleDownloader
from src.player.observers import *
from src.player.load_options import LoopOption, PlayerOption, FFMPEGOption, JobOption
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
    'outtmpl': os.path.join(MUSIC_STORAGE, '%(id)s.%(ext)s'),
}

async def run_blocker(client, func, *args, **kwargs):
    func_ = functools.partial(func, *args, **kwargs)
    return await client.loop.run_in_executor(None, func_)


def _time_split(time: int):
    return str(timedelta(seconds=time))


class Job:
    def __init__(self, job_name: str, work: str):
        """
        Defines a job for the bot to do.

        Args:
            job_name (str): The name of the job. Accepts either 'search' or 'access'.
            work (str): The workload required for the job.
        """
        self.job = job_name  # accepts either "search" or "access"
        self.work = work


YT_DLP_SESH = YoutubeDL(YOUTUBEDL_PARAMS)


class RequestQueue(DownloaderObservers):
    def __init__(self, observer = DownloaderObservable()):
        """Initialize a queue for processing the urls and queries.

        Args:
            observer (DownloaderObservable, optional): A DownloaderObservable object.
        """
        super().__init__(observer)
        self.priority: Union[Job, None] = None
        self.on_hold: List[Job] = []
        self._completed_priority = False
        self._ongoing_process = False
    
    def add_new_request(self, job: Job):
        """Adds a new request to the queue

        Args:
            job (Job): A job for the queue to handle.
        """
        if self.priority is None and not self.on_hold:
            self.priority = job
        elif self.priority is None:
            self.priority = self.on_hold.pop(0)
            self.on_hold.append(job)
        else:
            self.on_hold.append(job)

    def update(self):
        """
        Overrides the original update function in DownloaderObservers
        """
        if inspect.stack()[1][3] == "notify_observers":
            self._completed_priority = True

    async def process_requests(self, client, ctx: commands.Context, vault: Vault, selector_choice):
        """Processes the requests sequentially.

        Args:
            client (_type_): A Discord Bot Client.
            ctx (commands.Context): Context of the command
            vault (Vault): A vault to store values for other classes
            selector_choice (int): Whether the guild wants the search to yield an immediate result or not.
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
    

class GuildSession:
    def __init__(self):
        self.queue: List[MediaMetadata] = list()
        self.request_queue: RequestQueue = RequestQueue()
        self.loop: int = LoopOption.NO_LOOP
        
        self.loop_count: Union[Dict[MediaMetadata, int], None] = None
        self.loop_counter: int = lambda: 0

        self.cur_song: Union[MediaMetadata, None] = None
        self.previous_song: Union[MediaMetadata, None] = None
        self.player: Union[discord.FFmpegPCMAudio, None] = None
        
        self.cur_processing: bool = False
        self.retry_count: int = 0

        self.requires_download: List[MediaMetadata] = list()

    @staticmethod
    def _delete_files(song_metadata: MediaMetadata):
        """ Deletes the files of a song, given the metadata.

        Args:
            song_metadata (MediaMetadata): The metadata of the song.
        """
        fp = os.path.join(MUSIC_STORAGE, f"{song_metadata.id}.mp3")
        try:
            if os.path.isfile(fp) or os.path.islink(fp):
                os.unlink(fp)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (fp, e))

    def reset(self):
        bogus_queue = deepcopy(self.queue) # safe delete
        for item in bogus_queue:
            self._delete_files(item)
        self.queue.clear()
        self.cur_song = None
        self.player = None
        self.loop = LoopOption.NO_LOOP


class Player(commands.Cog):
    _MAX_RETRY_COUNT = 3

    _MAX_AUDIO_ALLOWED_TIME = 21600
    
    # issue found at https://gist.github.com/vbe0201/ade9b80f2d3b64643d854938d40a0a2d?permalink_comment_id=4140046#gistcomment-4140046
    # basically, if the playlist is set to be played for 6 hrs, the latter links will expire.
    # though, this should only matter to streaming music, right?

    def __init__(self, bot):
        """Initializes the Player

        Args:
            bot: A Discord Bot object
        """
        
        self._bot = bot
        self._sessions: Dict[int, GuildSession] = defaultdict(lambda: GuildSession())
        self._vault = Vault()
        self._bot_config = Config(CONFIG_FILE_LOC)

    def get_players(self, ctx, job= PlayerOption.NEW_PLAYER):
        """Gets the player for the bot in a voice channel in a guild

        Args:
            ctx (commands.Context): Context of the command
            job (str, optional): The job of this getter, which either gets a new player or refreshes the current one. Defaults to getting a new one.

        Returns:
            discord.FFmegPCMAudio: The player for the bot to play audio.
        """
        guild_sesh = self._get_guild_sesh()

        if guild_sesh.player is not None and job:
            return guild_sesh.player
        else:
            if guild_sesh.cur_song not in guild_sesh.requires_download:
                player = discord.FFmpegPCMAudio(guild_sesh.cur_song.url, **FFMPEGOption.FFMPEG_STREAM_OPTIONS)
            else:
                player = discord.FFmpegPCMAudio(os.path.join(MUSIC_STORAGE, f"{guild_sesh.cur_song.id}.mp3"),
                                            **FFMPEGOption.FFMPEG_PLAY_OPTIONS)
            guild_sesh.player = player
            return player

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        # add cases where ALL users left the VC and the bot is left idle for some time.

        if member.bot and member.id == self._bot.user.id:
            if before.channel and not after.channel:
                guild_id = member.guild.id
                self._sessions[guild_id].reset()
                print(f"cleared in guild id {guild_id}")
            
    @commands.command()
    async def play(self, ctx: commands.Context, *, url_: str):
        """
        Allows the bot to play audio in the voice channel.
        Subsequent calls from users in the same channel will add more media entries to the queue.
        At the moment, the bot only supports YouTube links and queries.
        :param ctx: Context of the command
        :param url_: The url, or the query, that is associated with the command
        :return:
        """
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        if not url_:
            return await ctx.send("No input has been given")
        guild_sesh = self._get_guild_sesh()
        if is_valid_link(url_):
            cmd_job = JobOption.ACCESS_JOB
        else:
            cmd_job = JobOption.SEARCH_JOB
        guild_sesh.request_queue.add_new_request(Job(cmd_job, url_))
        if not guild_sesh.cur_processing:
            guild_sesh.cur_processing = True
            self._bot.loop.create_task(self.bg_process_rq(ctx))

        while self._vault.isEmpty(ctx.guild.id):
            await asyncio.sleep(1)

        # both runs at the same time from here.
        data = self._vault.get_data(ctx.guild.id)
        if data is not None:
            data_l = len(data)
            if data_l == 1:
                msg = f"Added {data[0].title} to the queue."
            else:
                msg = f"Added {data_l} songs to the queue."

            # checking for entries that requires downloading
            # These entries are some but not limited to:
            #  - Entries that are more than 6 hours in play time.
            #  - Entries that make the playlist plays longer than 6 hours 
            # All of this is mainly to preserve the items in the playlist.

            queue_total_play_time = sum([int(i.duration) for i in guild_sesh.queue]) if guild_sesh.queue else 0
            for item_ind, item in enumerate(data):
                if item.duration >= self._MAX_AUDIO_ALLOWED_TIME: # for now, for safety, that is removed
                    await ctx.send(f"Video {item.title} is too long! Current max length allowed is 6 hours! Removed from queue")
                    data.remove(item)
                elif queue_total_play_time + item.duration >= self._MAX_AUDIO_ALLOWED_TIME:
                    guild_sesh.requires_download.extend(data[item_ind:])
                    break
            
            if data:
                guild_sesh.queue.extend(data)
                await ctx.send(msg)

                try:
                    voiceChannel = discord.utils.get(
                        ctx.message.guild.voice_channels,
                        name=ctx.author.guild.get_member(ctx.author.id).voice.channel.name
                    )
                except AttributeError:
                    return await ctx.send('You need to be in a voice channel to use this command')

                await self.pre_play_process(ctx, voiceChannel)

    async def pre_play_process(self, ctx, voiceChannel):
        """
        Processes the data before playing the songs in the voice channel.

        Args:
            ctx (commands.Context): Context of the command
            data (List[MediaMetadata]): The data to be processed
            voiceChannel (_type_): The voice channel to connect to

        """
        guild_sesh = self._get_guild_sesh()
            # try:
            #     obj = Downloader(data, YT_DLP_SESH)
            #     await run_blocker(self._bot, obj.first_download)
            # except NoVideoInQueueError:
            #     return await ctx.send("No items are currently in queue")

            # if len(data) > 1:
        try:
            if guild_sesh.requires_download:
                try:
                    obj = Downloader(guild_sesh.requires_download[0], YT_DLP_SESH)
                    await run_blocker(self._bot, obj.first_download)
                except NoVideoInQueueError:
                    return await ctx.send("No items are currently in queue")
                if len(guild_sesh.requires_download) > 1:
                    self.bg_download_check.start(ctx)
        except RuntimeError:
            pass

        if not self._is_connected(ctx):
            await voiceChannel.connect()

        voice = ctx.voice_client
        try:
            await self.play_song(ctx, voice)
        except discord.errors.ClientException:
            pass

    async def bg_process_rq(self, ctx):
        """ Processes the requests in the background

        Args:
            ctx (commands.Context): Context of the command
        """
        guild_sesh = self._get_guild_sesh()
        while True:
            if guild_sesh.request_queue.on_hold or guild_sesh.request_queue.priority is not None:
                await guild_sesh.request_queue.process_requests(self._bot, ctx, self._vault, self._bot_config.isAutoPick(ctx.guild.id))
            else:
                guild_sesh.cur_processing = False
                break

    @tasks.loop(seconds = 20)
    async def bg_download_check(self, ctx):
        """

        Processes the download in the background.

        Args:
            ctx (_type_): _description_
        """
        guild_sesh = self._get_guild_sesh()
        for item in guild_sesh.requires_download:
            if not isExist(item):
                down_sesh = SingleDownloader(item, YT_DLP_SESH)
                await run_blocker(self._bot, down_sesh.download)

    async def play_song(self, ctx, voice, refresh = False):
        """Plays the audio.

        Args:
            ctx (commands.Context): Context of the command,
            voice (discord.VoiceClient): The current voice client that the command issuer is being in.
            refresh (bool, optional): Whether the player should be refreshed a lot. Defaults to False.
        """
        guild_sesh = self._get_guild_sesh()

        if not voice.is_playing():
            async with ctx.typing():
                try:
                    guild_sesh.cur_song = guild_sesh.queue.pop(0)
                except IndexError:
                    guild_sesh.cur_song = None
            if guild_sesh.cur_song is None:
                await voice.disconnect()
                return

            player = self.get_players(ctx, PlayerOption._REFRESH_PLAYER) if refresh else self.get_players(ctx)
            voice.play(
                player,
                after=lambda e:
                self.retry_play(ctx, voice, e) if e else self.play_next(ctx)
                    )
            await ctx.send('**Now playing:** {}'.format(guild_sesh.cur_song.title), delete_after=20)
        else:
            await asyncio.sleep(1)
    
    def retry_play(self, ctx, voice, e):
        """Retries playing the audio.
        """
        guild_sesh = self._get_guild_sesh()
        if guild_sesh.retry_count < self._MAX_RETRY_COUNT:
            guild_sesh.retry_count += 1
            guild_sesh.queue.insert(0, guild_sesh.cur_song)
            guild_sesh.cur_song = None
            asyncio.run_coroutine_threadsafe(self.play_song(ctx, voice, True), ctx.bot.loop)
        else:
            print("Player error: %s", e)

    def play_next(self, ctx):
        """Plays the next audio in queue.
        """
        guild_sesh = self._get_guild_sesh()

        vc = discord.utils.get(self._bot.voice_clients, guild=ctx.guild)

        if guild_sesh.loop:
            if guild_sesh.loop_count is not None:
                if guild_sesh.loop_counter < list(guild_sesh.loop_count.values())[0]:
                    guild_sesh.loop_counter += 1
                else:
                    guild_sesh.loop = LoopOption.NO_LOOP
                    guild_sesh.loop_count = None
                    guild_sesh.loop_counter = 0
                    self.play_next(ctx)
            
            player = self.get_players(ctx, self._REFRESH_PLAYER)
            ctx.voice_client.play(
                player,
                after=lambda e:
                print('Player error: %s' % e) if e else self.play_next(ctx)
            )
            
        elif len(guild_sesh.queue) >= 1:
            try:
                guild_sesh.previous_song = guild_sesh.cur_song
                guild_sesh.cur_song = guild_sesh.queue.pop(0)
                if guild_sesh.cur_song in guild_sesh.requires_download and not isExist(guild_sesh.cur_song):
                    guild_sesh.queue.insert(0, guild_sesh.cur_song)
                    guild_sesh.cur_song = guild_sesh.previous_song
                    guild_sesh.previous_song = None
                    raise IOError("File not exist just yet")
            except IndexError:
                guild_sesh.cur_song = None
            if guild_sesh.cur_song is None:
                asyncio.run_coroutine_threadsafe(ctx.send("Finished playing"), ctx.bot.loop)
                asyncio.run_coroutine_threadsafe(ctx.voice_client.disconnect(), ctx.bot.loop)
                return

            ctx.voice_client.play(self.get_players(ctx, job=self._REFRESH_PLAYER), after=lambda e: self.play_next(ctx))
            asyncio.run_coroutine_threadsafe(ctx.send(
                    f'**Now playing:** {guild_sesh.cur_song.title}',
                    delete_after=20
                ), ctx.bot.loop)
        elif not ctx.voice_client.is_playing():
            asyncio.run_coroutine_threadsafe(vc.disconnect(), self._bot.loop)
            asyncio.run_coroutine_threadsafe(ctx.send("Finished playing!"), ctx.bot.loop)

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx):
        """Debugs a section of the code. Only the owner can use this.

        Args:
            ctx (commands.Context()): context of the message
        """
        guild_sesh = self._get_guild_sesh()
        await ctx.send(guild_sesh.queue)
        if guild_sesh.cur_song is not None:
            await ctx.send(guild_sesh.cur_song)
        else:
            await ctx.send("Currently no song is playing")

        await ctx.send([(k, v.queue) for k, v in self._sessions])
        await ctx.send([(k, v.cur_song) for k, v in self._sessions])

    @commands.command(name='stop')
    async def stop_(self, ctx):
        """Stops and disconnects the bot from voice"""
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        if self._is_connected(ctx):
            await ctx.voice_client.disconnect()
        else:
            await ctx.send("I am not in any voice chat right now")

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
                ctx.voice_client.stop()
            except IOError:
                ctx.voice_client.resume()
                return await ctx.send("The next media file is not ready to be played just yet - please be patient.")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name= 'fskip', aliases = ['forceskip', 'force_skip'])
    async def force_skip(self, ctx):
        """
        Skips to next song in queue, but forces the skip -- the loop will be ignored.
        """
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        guild_sesh = self._get_guild_sesh()

        if self._is_connected(ctx):
            ctx.voice_client.pause()
            try:
                guild_sesh.loop = LoopOption.NO_LOOP # next song is set to NOT loop - which should be what people want anyway.
                self.play_next(ctx)
            except IOError:
                ctx.voice_client.resume()
                return await ctx.send("The next media file is not ready to be played just yet - please be patient.")
        else:
            await ctx.send("I am not in any voice chat right now")

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pauses the player
        """
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
        """Resumes the player
        """
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
        """Checks the current playlist
        """
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        guild_sesh = self._get_guild_sesh()

        if self._is_connected(ctx):
            cur_playing_embed = discord.Embed(
                color=discord.Color.blue()
            )

            cur_playing_embed.add_field(
                name="Currently playing",
                value=f"**[{guild_sesh.cur_song.title}]({guild_sesh.cur_song.original_url})** ({_time_split(guild_sesh.cur_song.duration)})\n"
            )

            await ctx.send(embed=cur_playing_embed)

            all_additional_embeds_created = False
            all_embeds = []
            cur_index = 0
            if guild_sesh.queue:
                while not all_additional_embeds_created:
                    next_playing_embed = discord.Embed(
                        color=discord.Color.blue()
                    )

                    r_link = ""
                    max_reached = False
                    while not max_reached and cur_index < len(guild_sesh.queue):
                        res_ind = cur_index
                        res = guild_sesh.queue[res_ind]
                        string = f"**{res_ind + 1}. [{res.title}]({res.original_url})** ({_time_split(res.duration)})\n"
                        if len(r_link) <= MAX_MSG_EMBED_SIZE - len(string):
                            r_link += string
                            cur_index += 1
                        else:
                            max_reached = True
                    if cur_index == len(guild_sesh.queue):
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
        """Clears the queue
        """
        guild_id = ctx.guild.id
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        self._queue[guild_id].clear()
        self._requires_download[guild_id].clear()
        await ctx.send("Queue cleared!")

    @commands.command(name='loop')
    async def loop(self, ctx, loop_amount = None):
        """Loops indefinitely the audio or loop it a finite amount of times.
        Use the command again to end looping.
        """
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")
        guild_sesh = self._get_guild_sesh()

        if guild_sesh.loop:
            if loop_amount is not None:
                return await ctx.send(f"Already looping a couple of times - please type {BOT_PREFIX}loop to end loop.")
            guild_sesh.loop = LoopOption.NO_LOOP
            if guild_sesh.loop_count is not None:
                guild_sesh.loop_count = None
            await ctx.send("No longer looping current song.")
        else:
            if loop_amount is not None:
                if not loop_amount.isdigit():
                    return await ctx.send("Please enter a number if you want to loop the current song a number of times.")
                else:
                    guild_sesh.loop_count = {
                        guild_sesh.cur_song : int(loop_amount)
                        }
                    await ctx.send(f"Looping current song for {loop_amount} more times.")
            else:
                await ctx.send("Looping current song.")
            guild_sesh.loop = LoopOption.LOOP
            

    @commands.command(name='shuffle')
    async def shuffle(self, ctx):
        """Shuffles the playlist
        """
        can_join_vc = self.peek_vc(ctx)
        if not can_join_vc:
            return await ctx.send("You need to be in a voice channel to use this command.")

        guild_sesh = self._get_guild_sesh()
        if guild_sesh.queue:
            random.shuffle(guild_sesh.queue)
            await ctx.send(f"Queue is shuffled. To check current queue, please use {BOT_PREFIX}queue, or {BOT_PREFIX}q")
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

    @set_state.error
    async def set_state_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            msg = f"You don't have the privilege to set this {ctx.message.author.mention}."
            await ctx.send(msg)

    def _is_connected(self, ctx):
        return discord.utils.get(self._bot.voice_clients, guild=ctx.guild)

    def _get_guild_sesh(self, ctx):
        return self._session[ctx.guild.id]

async def setup(bot):
    await bot.add_cog(Player(bot))

from yt_dlp import YoutubeDL
from typing import List
import os
import asyncio

from constants import MUSIC_STORAGE
from src.player.youtube.media_metadata import MediaMetadata
from src.player.alter_title import alter_title


class NoVideoInQueueError(Exception):
    """Error when there is no video in queue
    """
    pass


class SingleDownloader:
    """Downloads the audio from a single YouTube video.
    """
    def __init__(self, data:MediaMetadata, ydl_session:YoutubeDL):
        self._data = data
        self._ydl = ydl_session

    def download(self):
        if self._data is not None and not isExist(self._data):
            self._ydl.download([self._data.original_url])


class Downloader:
    """Downloads the audio from a list of YouTube videos.
    """
    def __init__(self, data:List[MediaMetadata], ydl_sesh:YoutubeDL):
        self._data = data
        self._ydl = ydl_sesh
        self.playable = False

    def first_download(self):
        try:
            SingleDownloader(self._data[0], self._ydl).download()
            self.playable = True
        except IndexError:
            raise NoVideoInQueueError("There is no video currently in queue")

    async def _async_range_ft(self, from_point, to_point):
        for i in range(from_point, to_point):
            yield i
            await asyncio.sleep(0.0)

    def continue_download(self):
        if len(self._data) > 1:
            for sin_ind in range(1, len(self._data)):
                SingleDownloader(self._data[sin_ind], self._ydl).download()


def isExist(info_dict: MediaMetadata) -> bool:
    try:
        return os.path.isfile(os.path.join(MUSIC_STORAGE,'{}.mp3'.format(alter_title(info_dict.id))))
    except AttributeError:
        return False
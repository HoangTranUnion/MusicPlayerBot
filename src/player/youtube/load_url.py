from yt_dlp import YoutubeDL
from typing import Dict
from src.player.youtube.media_metadata import MediaMetadata


class LoadURL:
    def __init__(self, url):
        self._url = url
        if "list" in self._url:
            self._url_type = "playlist"
        else:
            self._url_type = "video"
        self.inst = YoutubeDL(
            {
                'format':'bestaudio',
                'ignoreerrors':'only_download'
            }
        )

        self.load_sesh_completed = False

    def load_info(self):
        obtained_data : Dict = self.inst.extract_info(self._url, download = False)
        self.load_sesh_completed = True
        if self._url_type == 'video':
            if obtained_data is not None:
                return [MediaMetadata(obtained_data)]
            else:
                return []
        else:
            return [MediaMetadata(i) for i in obtained_data['entries'] if i is not None]


from yt_dlp import YoutubeDL
from src.player.youtube.media_metadata import MediaMetadata


class SearchVideos:
    _SITE_MAPPING = {
        "YouTube":'ytsearch',
        "Bilibili":'bilisearch'
    }

    def __init__(self, chosen_site = "YouTube", limit = 5):
        self._search_key = self._SITE_MAPPING[chosen_site]
        self._limit = limit
        self.search_sesh_completed = False

    def search(self, query):
        ydl = YoutubeDL({
            'format': 'bestaudio',
            'ignoreerrors': 'only_download'
        })
        search_res = ydl.extract_info(f"{self._search_key}{self._limit}:{query}", download=False)['entries']
        self.search_sesh_completed = True
        return [MediaMetadata(i) for i in search_res]
class MediaMetadata:
    __slots__ = ('_full_info',
                 'id',
                 'title',
                 'formats',
                 'thumbnails',
                 'description',
                 'upload_date',
                 'uploader',
                 'uploader_id',
                 'uploader_url',
                 'channel_id',
                 'channel_url',
                 'duration',
                 'view_count',
                 'average_rating',
                 'age_limit',
                 'webpage_url',
                 'categories',
                 'tags',
                 'playable_in_embed',
                 'is_live',
                 'was_live',
                 'live_status',
                 'release_timestamp',
                 'automatic_captions',
                 'subtitles',
                 'chapters',
                 'like_count',
                 'dislike_count',
                 'channel',
                 'track',
                 'artist',
                 'album',
                 'creator',
                 'alt_title',
                 'availability',
                 'original_url',
                 'webpage_url_basename',
                 'extractor',
                 'extractor_key',
                 'playlist',
                 'playlist_index',
                 'thumbnail',
                 'display_id',
                 'requested_subtitles',
                 '__has_drm',
                 'requested_formats',
                 'format',
                 'format_id',
                 'ext',
                 'width',
                 'height',
                 'resolution',
                 'fps',
                 'vcodec',
                 'vbr',
                 'stretched_ratio',
                 'acodec',
                 'abr',
                 'url'
                 )

    def __init__(self, info_dict: dict):
        '''
        Keeps track of the metadata of a YouTube video
        All necessary keys:
        'id', 'title', 'formats', 'thumbnails', 'description', 'upload_date', 'uploader', 'uploader_id', 'uploader_url',
         'channel_id', 'channel_url', 'duration', 'view_count', 'average_rating', 'age_limit', 'webpage_url',
         'categories', 'tags', 'playable_in_embed', 'is_live', 'was_live', 'live_status', 'release_timestamp',
         'automatic_captions', 'subtitles', 'chapters', 'like_count', 'dislike_count', 'channel', 'track', 'artist',
         'album', 'creator', 'alt_title', 'availability', 'original_url', 'webpage_url_basename', 'extractor',
         'extractor_key', 'playlist', 'playlist_index', 'thumbnail', 'display_id', 'requested_subtitles', '__has_drm',
         'requested_formats', 'format', 'format_id', 'ext', 'width', 'height', 'resolution', 'fps', 'vcodec', 'vbr',
         'stretched_ratio', 'acodec', 'abr', 'url'
        :param info_dict: The dictionary containing the metadata of the video
        '''
        self._full_info = info_dict
        self.id = self._setup_variable('id')
        self.title = self._setup_variable('title')
        self.formats = self._setup_variable('formats')
        self.thumbnails = self._setup_variable('thumbnails')
        self.description = self._setup_variable('description')
        self.upload_date = self._setup_variable('upload_date')
        self.uploader = self._setup_variable('uploader')
        self.uploader_id = self._setup_variable('uploader_id')
        self.uploader_url = self._setup_variable('uploader_url')
        self.channel_id = self._setup_variable('channel_id')
        self.channel_url = self._setup_variable('channel_url')
        self.duration = self._setup_variable('duration')
        self.view_count = self._setup_variable('view_count')
        self.average_rating = self._setup_variable('average_rating')
        self.age_limit = self._setup_variable('age_limit')
        self.webpage_url = self._setup_variable('webpage_url')
        self.categories = self._setup_variable('categories')
        self.tags = self._setup_variable('tags')
        self.playable_in_embed = self._setup_variable('playable_in_embed')
        self.is_live = self._setup_variable('is_live')
        self.was_live = self._setup_variable('was_live')
        self.live_status = self._setup_variable('live_status')
        self.release_timestamp = self._setup_variable('release_timestamp')
        self.automatic_captions = self._setup_variable('automatic_captions')
        self.subtitles = self._setup_variable('subtitles')
        self.chapters = self._setup_variable('chapters')
        self.like_count = self._setup_variable('like_count')
        self.dislike_count = self._setup_variable('dislike_count')
        self.channel = self._setup_variable('channel')
        self.track = self._setup_variable('track')
        self.artist = self._setup_variable('artist')
        self.album = self._setup_variable('album')
        self.creator = self._setup_variable('creator')
        self.alt_title = self._setup_variable('alt_title')
        self.availability = self._setup_variable('availability')
        self.original_url = self._setup_variable('original_url')
        self.webpage_url_basename = self._setup_variable('webpage_url_basename')
        self.extractor = self._setup_variable('extractor')
        self.extractor_key = self._setup_variable('extractor_key')
        self.playlist = self._setup_variable('playlist')
        self.playlist_index = self._setup_variable('playlist_index')
        self.thumbnail = self._setup_variable('thumbnail')
        self.display_id = self._setup_variable('display_id')
        self.requested_subtitles = self._setup_variable('requested_subtitles')
        self.__has_drm = self._setup_variable('__has_drm')
        self.requested_formats = self._setup_variable('requested_formats')
        self.format = self._setup_variable('format')
        self.format_id = self._setup_variable('format_id')
        self.ext = self._setup_variable('ext')
        self.width = self._setup_variable('width')
        self.height = self._setup_variable('height')
        self.resolution = self._setup_variable('resolution')
        self.fps = self._setup_variable('fps')
        self.vcodec = self._setup_variable('vcodec')
        self.vbr = self._setup_variable('vbr')
        self.stretched_ratio = self._setup_variable('stretched_ratio')
        self.acodec = self._setup_variable('acodec')
        self.abr = self._setup_variable('abr')
        self.url = self._setup_variable('url')

    def _setup_variable(self, key):
        try:
            return self._full_info[key]
        except KeyError:
            return None
        except TypeError:
            return None

    def __str__(self):
        try:
            return str(self.to_simple_dict())
        except TypeError:
            return "None"

    def __repr__(self):
        try:
            return str(self.to_simple_dict())
        except TypeError:
            return "None"

    def __eq__(self, o):
        if isinstance(o, MediaMetadata):
            if self.id == o.id:
                return True
            else:
                return False
        else:
            return False

    def to_dict(self):
        return self._full_info

    def to_simple_dict(self):
        return {
            'title': self.title,
            'duration': self.duration,
            'url': self.original_url
        }

    def __key(self):
        return (self.id, self.title)       

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        if isinstance(other, MediaMetadata):
            if self.id == other.id and self.title == other.title:
                return True
        return False
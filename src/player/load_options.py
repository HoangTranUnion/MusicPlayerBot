from enum import Enum, unique

@unique
class LoopOption(Enum):
    NO_LOOP = 0
    LOOP = 1

@unique
class PlayerOption(Enum):
    NEW_PLAYER = 1
    REFRESH_PLAYER = 0

@unique
class FFMPEGOption(Enum):
    FFMPEG_STREAM_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    FFMPEG_PLAY_OPTIONS = {
        'options': '-vn',
    }

@unique
class JobOption(Enum):
    ACCESS_JOB = "access"
    SEARCH_JOB = "search"
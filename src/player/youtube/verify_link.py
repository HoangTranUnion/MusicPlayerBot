import re

_YOUTUBE_VALID_LINK_REGEX = r'^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$'
# _BILIBILI_VALID_LINK_REGEX = r'''(?x)
#                     https?://
#                         (?:(?:www|bangumi)\.)?
#                         bilibili\.(?:tv|com)/
#                         (?:
#                             (?:
#                                 video/[aA][vV]|
#                                 anime/(?P<anime_id>\d+)/play\#
#                             )(?P<id>\d+)|
#                             (s/)?video/[bB][vV](?P<id_bv>[^/?#&]+)
#                         )
#                         (?:/?\?p=(?P<page>\d+))?
#                     '''
SUPPORTED_SITES = ["youtube"]


def is_valid_link(link:str):
    return bool(re.search(_YOUTUBE_VALID_LINK_REGEX, link)) or bool(re.search(_BILIBILI_VALID_LINK_REGEX, link))
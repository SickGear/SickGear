# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import os

from . import generic, xbmc_12plus
from .. import helpers
import sickbeard
# noinspection PyPep8Naming
import encodingKludge as ek

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional


class XBMCMetadata(xbmc_12plus.XBMC12PlusMetadata):
    """
    Metadata generation class for XBMC (legacy).

    The following file structure is used:

    show_root/tvshow.nfo              (show metadata)
    show_root/fanart.jpg              (fanart)
    show_root/folder.jpg              (poster)
    show_root/folder.jpg              (banner)
    show_root/Season ##/filename.ext  (*)
    show_root/Season ##/filename.nfo  (episode metadata)
    show_root/Season ##/filename.tbn  (episode thumb)
    show_root/season##.tbn            (season posters)
    show_root/season-all.tbn          (season all poster)
    """

    def __init__(self,
                 show_metadata=False,  # type: bool
                 episode_metadata=False,  # type: bool
                 use_fanart=False,  # type: bool
                 use_poster=False,  # type: bool
                 use_banner=False,  # type: bool
                 episode_thumbnails=False,  # type: bool
                 season_posters=False,  # type: bool
                 season_banners=False,  # type: bool
                 season_all_poster=False,  # type: bool
                 season_all_banner=False  # type: bool
                 ):

        generic.GenericMetadata.__init__(self,
                                         show_metadata,
                                         episode_metadata,
                                         use_fanart,
                                         use_poster,
                                         use_banner,
                                         episode_thumbnails,
                                         season_posters,
                                         season_banners,
                                         season_all_poster,
                                         season_all_banner)

        self.name = 'XBMC'  # type: AnyStr

        self.poster_name = self.banner_name = "folder.jpg"  # type: AnyStr
        self.season_all_poster_name = "season-all.tbn"  # type: AnyStr

        # web-ui metadata template
        self.eg_show_metadata = "tvshow.nfo"  # type: AnyStr
        self.eg_episode_metadata = "Season##\\<i>filename</i>.nfo"  # type: AnyStr
        self.eg_fanart = "fanart.jpg"  # type: AnyStr
        self.eg_poster = "folder.jpg"  # type: AnyStr
        self.eg_banner = "folder.jpg"  # type: AnyStr
        self.eg_episode_thumbnails = "Season##\\<i>filename</i>.tbn"  # type: AnyStr
        self.eg_season_posters = "season##.tbn"  # type: AnyStr
        self.eg_season_banners = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_all_poster = "season-all.tbn"  # type: AnyStr
        self.eg_season_all_banner = "<i>not supported</i>"  # type: AnyStr

    # Override with empty methods for unsupported features
    def create_season_banners(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> None
        pass

    def create_season_all_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def get_episode_thumb_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[AnyStr]
        """
        Returns the path where the episode thumbnail should be stored. Defaults to
        the same path as the episode file but with a .tbn extension.

        ep_obj: a TVEpisode instance for which to create the thumbnail
        """
        if ek.ek(os.path.isfile, ep_obj.location):
            tbn_filename = helpers.replace_extension(ep_obj.location, 'tbn')
        else:
            return None

        return tbn_filename

    def get_season_poster_path(self, show_obj, season):
        # type: (sickbeard.tv.TVShow, int) -> AnyStr
        """
        Returns the full path to the file for a given season poster.

        show_obj: a TVShow instance for which to generate the path
        season: a season number to be used for the path. Note that season 0
                means specials.
        """

        # Our specials thumbnail is, well, special
        if 0 == season:
            season_poster_filename = 'season-specials'
        else:
            season_poster_filename = 'season' + str(season).zfill(2)

        return ek.ek(os.path.join, show_obj.location, season_poster_filename + '.tbn')


# present a standard "interface" from the module
metadata_class = XBMCMetadata

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

from . import generic
# noinspection PyPep8Naming
import encodingKludge as ek
import sickbeard

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple


class PS3Metadata(generic.GenericMetadata):
    """
    Metadata generation class for Sony PS3.

    The following file structure is used:

    show_root/cover.jpg                         (poster)
    show_root/Season ##/filename.ext            (*)
    show_root/Season ##/filename.ext.cover.jpg  (episode thumb)
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

        self.name = "Sony PS3"  # type: AnyStr

        self.poster_name = "cover.jpg"  # type: AnyStr

        # web-ui metadata template
        self.eg_show_metadata = "<i>not supported</i>"  # type: AnyStr
        self.eg_episode_metadata = "<i>not supported</i>"  # type: AnyStr
        self.eg_fanart = "<i>not supported</i>"  # type: AnyStr
        self.eg_poster = "cover.jpg"  # type: AnyStr
        self.eg_banner = "<i>not supported</i>"  # type: AnyStr
        self.eg_episode_thumbnails = "Season##\\<i>filename</i>.ext.cover.jpg"  # type: AnyStr
        self.eg_season_posters = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_banners = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_all_poster = "<i>not supported</i>"  # type: AnyStr
        self.eg_season_all_banner = "<i>not supported</i>"  # type: AnyStr

    # Override with empty methods for unsupported features
    def retrieveShowMetadata(self, folder):
        # type: (AnyStr) -> Tuple[None, None, None]
        # no show metadata generated, we abort this lookup function
        return None, None, None

    def create_show_metadata(self, show_obj, force=False):
        # type: (sickbeard.tv.TVShow, bool) -> None
        pass

    def update_show_indexer_metadata(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def get_show_file_path(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_episode_metadata(self, ep_obj, force=False):
        # type: (sickbeard.tv.TVEpisode, bool) -> None
        pass

    def create_fanart(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_posters(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_banners(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> None
        pass

    def create_season_all_poster(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def create_season_all_banner(self, show_obj):
        # type: (sickbeard.tv.TVShow) -> None
        pass

    def get_episode_thumb_path(self, ep_obj):
        # type: (sickbeard.tv.TVEpisode) -> Optional[AnyStr]
        """
        Returns the path where the episode thumbnail should be stored. Defaults to
        the same path as the episode file but with a .cover.jpg extension.

        ep_obj: a TVEpisode instance for which to create the thumbnail
        """
        if ek.ek(os.path.isfile, ep_obj.location):
            tbn_filename = ep_obj.location + ".cover.jpg"
        else:
            return None

        return tbn_filename


# present a standard "interface" from the module
metadata_class = PS3Metadata

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

import datetime
import glob
import os.path
import re
import zlib

import exceptions_helper
from exceptions_helper import ex
import sickgear
import sg_helpers
from . import db, logger
from .metadata.generic import GenericMetadata
from .sgdatetime import SGDatetime
from .indexers.indexer_config import TVINFO_TVDB, TVINFO_TVMAZE, TVINFO_TMDB, TVINFO_IMDB

from six import itervalues, iteritems

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Tuple, Union
    from .tv import TVShow, Person, Character
    from six import integer_types
    from .metadata.generic import ShowInfosDict

from lib.hachoir.parser import createParser, guessParser
from lib.hachoir.metadata import extractMetadata
from lib.hachoir.metadata.metadata_item import QUALITY_BEST
from lib.hachoir.stream import StringInputStream

cache_img_base = {'tvmaze': TVINFO_TVMAZE, 'themoviedb': TVINFO_TMDB, 'thetvdb': TVINFO_TVDB, 'imdb': TVINFO_IMDB}
cache_img_src = {TVINFO_TMDB: 'tmdb', TVINFO_TVDB: 'tvdb', TVINFO_TVMAZE: 'tvmaze', TVINFO_IMDB: 'imdb'}


class ImageCache(object):
    base_dir = None  # type: AnyStr or None
    shows_dir = None  # type: AnyStr or None
    persons_dir = None  # type: Optional[AnyStr]
    characters_dir = None  # type: Optional[AnyStr]

    def __init__(self):
        if None is ImageCache.base_dir and os.path.exists(sickgear.CACHE_DIR):
            ImageCache.base_dir = os.path.abspath(os.path.join(sickgear.CACHE_DIR, 'images'))
            ImageCache.shows_dir = os.path.abspath(os.path.join(self.base_dir, 'shows'))
            ImageCache.persons_dir = self._persons_dir()
            ImageCache.characters_dir = self._characters_dir()

    def __del__(self):
        pass

    # @staticmethod
    # def _cache_dir():
    #     """
    #     Builds up the full path to the image cache directory
    #     """
    #     return os.path.abspath(os.path.join(sickgear.CACHE_DIR, 'images'))

    @staticmethod
    def _persons_dir():
        # type: (...) -> AnyStr
        return os.path.join(sickgear.CACHE_DIR, 'images', 'person')

    @staticmethod
    def _characters_dir():
        # type: (...) -> AnyStr
        return os.path.join(sickgear.CACHE_DIR, 'images', 'characters')

    def _fanart_dir(self, tvid=None, prodid=None):
        # type: (int, int) -> AnyStr
        """
        Builds up the full path to the fanart image cache directory

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :return: path
        :rtype: AnyStr or None
        """
        if None not in (tvid, prodid):
            return os.path.abspath(os.path.join(self.shows_dir, '%s-%s' % (tvid, prodid), 'fanart'))

    def _thumbnails_dir(self, tvid, prodid):
        # type: (int, int) -> AnyStr
        """
        Builds up the full path to the thumbnails image cache directory

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :return: path
        :rtype: AnyStr
        """
        return os.path.abspath(os.path.join(self.shows_dir, '%s-%s' % (tvid, prodid), 'thumbnails'))

    @staticmethod
    def _person_base_name(person_obj):
        # type: (Person) -> AnyStr
        base_id = next((v for k, v in iteritems(cache_img_base)
                        if k in (person_obj.image_url or '') or person_obj.thumb_url), 0)
        return '%s-%s' % (cache_img_src.get(base_id, base_id), person_obj.ids.get(base_id)
                          or sg_helpers.sanitize_filename(person_obj.name))

    @staticmethod
    def _character_base_name(character_obj, show_obj, tvid=None, proid=None):
        # type: (Character, TVShow, integer_types, integer_types) -> AnyStr
        return '%s-%s' % (cache_img_src.get(tvid or show_obj.tvid, tvid or show_obj.tvid),
                          character_obj.ids.get(tvid or show_obj.tvid)
                          or sg_helpers.sanitize_filename(character_obj.name))

    def person_path(self, person_obj, base_path=None):
        # type: (Optional[Person], AnyStr) -> AnyStr
        """
        return image filename
        :param person_obj:
        :param base_path:
        """
        filename = '%s.jpg' % base_path or self._person_base_name(person_obj)
        return os.path.join(self.persons_dir, filename)

    def person_thumb_path(self, person_obj, base_path=None):
        # type: (Optional[Person], AnyStr) -> AnyStr
        """
        return thumb image filename
        :param person_obj:
        :param base_path:
        """
        filename = '%s_thumb.jpg' % base_path or self._person_base_name(person_obj)
        return os.path.join(self.persons_dir, filename)

    def person_both_paths(self, person_obj):
        # type: (Person) -> Tuple[AnyStr, AnyStr]
        """
        return tuple image, thumb filenames
        :param person_obj:
        """
        base_path = self._person_base_name(person_obj)
        return self.person_path(None, base_path=base_path), self.person_thumb_path(None, base_path=base_path)

    def character_path(self, character_obj, show_obj, base_path=None):
        # type: (Optional[Character], Optional[TVShow], AnyStr) -> AnyStr
        """
        return image filename
        :param character_obj:
        :param show_obj:
        :param base_path:
        """
        filename = '%s.jpg' % base_path or self._character_base_name(character_obj, show_obj)
        return os.path.join(self.characters_dir, filename)

    def character_thumb_path(self, character_obj, show_obj, base_path=None):
        # type: (Optional[Character], Optional[TVShow], AnyStr) -> AnyStr
        """
        return thumb image filename
        :param character_obj:
        :param show_obj:
        :param base_path:
        """
        filename = '%s_thumb.jpg' % base_path or self._character_base_name(character_obj, show_obj)
        return os.path.join(self.characters_dir, filename)

    def character_both_path(self, character_obj, show_obj=None, tvid=None, proid=None, person_obj=None):
        # type: (Character, TVShow, integer_types, integer_types, Person) -> Tuple[AnyStr, AnyStr]
        """
        returns tuple image, thumb image
        :param character_obj:
        :param show_obj:
        :param tvid:
        :param proid:
        :param person_obj:
        """
        base_path = self._character_base_name(character_obj, show_obj=show_obj, tvid=tvid, proid=proid)
        from .tv import Person
        if isinstance(person_obj, Person):
            person_base = self._person_base_name(person_obj)
            if person_base:
                base_path = '%s-%s' % (base_path, person_base)
        return self.character_path(None, None, base_path=base_path), \
            self.character_thumb_path(None, None, base_path=base_path)

    def poster_path(self, tvid, prodid):
        # type: (int, int) -> AnyStr
        """
        Builds up the path to a poster cache for a given tvid prodid

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :return: a full path to the cached poster file for the given tvid prodid
        :rtype: AnyStr
        """
        return os.path.join(self.shows_dir, '%s-%s' % (tvid, prodid), 'poster.jpg')

    def banner_path(self, tvid, prodid):
        # type: (int, int) -> AnyStr
        """
        Builds up the path to a banner cache for a given tvid prodid

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :return: a full path to the cached banner file for the given tvid prodid
        :rtype: AnyStr
        """
        return os.path.join(self.shows_dir, '%s-%s' % (tvid, prodid), 'banner.jpg')

    def fanart_path(self, tvid, prodid, prefix=''):
        # type: (int, int, Optional[AnyStr]) -> AnyStr
        """
        Builds up the path to a fanart cache for a given tvid prodid

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :param prefix: String to insert at the start of a filename (e.g. '001.')
        :type prefix: AnyStr
        :return: a full path to the cached fanart file for the given tvid prodid
        :rtype: AnyStr
        """
        return os.path.join(self._fanart_dir(tvid, prodid), '%s%s' % (prefix, 'fanart.jpg'))

    def poster_thumb_path(self, tvid, prodid):
        # type: (int, int) -> AnyStr
        """
        Builds up the path to a poster cache for a given tvid prodid

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :return: a full path to the cached poster file for the given tvid prodid
        :rtype: AnyStr
        """
        return os.path.join(self._thumbnails_dir(tvid, prodid), 'poster.jpg')

    def banner_thumb_path(self, tvid, prodid):
        # type: (int, int) -> AnyStr
        """
        Builds up the path to a poster cache for a given tvid prodid

        :param tvid: TV info source ID to use in the file name
        :type tvid: int
        :param prodid: Show ID to use in the file name
        :type prodid: int or long
        :return: a full path to the cached poster file for the given tvid prodid
        :rtype: AnyStr
        """
        return os.path.join(self._thumbnails_dir(tvid, prodid), 'banner.jpg')

    @staticmethod
    def has_file(image_file):
        # type: (AnyStr) -> bool
        """
        :param image_file: image file
        :type image_file: AnyStr
        :return: true if an image_file exists
        :rtype: bool
        """
        result = []
        for filename in glob.glob(image_file):
            result.append(os.path.isfile(filename) and filename)
            logger.debug(f'Found cached {filename}')

        not any(result) and logger.debug(f'No cache for {image_file}')
        return any(result)

    def has_poster(self, tvid, prodid):
        # type: (int, int) -> bool
        """
        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :return: true if a cached poster exists for the given tvid prodid
        :rtype: bool
        """
        return self.has_file(self.poster_path(tvid, prodid))

    def has_banner(self, tvid, prodid):
        # type: (int, int) -> bool
        """
        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :return: true if a cached banner exists for the given tvid prodid
        :rtype: bool
        """
        return self.has_file(self.banner_path(tvid, prodid))

    def has_fanart(self, tvid, prodid):
        # type: (int, int) -> bool
        """
        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :return: true if a cached fanart exists for the given tvid prodid
        :rtype: bool
        """
        return self.has_file(self.fanart_path(tvid, prodid).replace('fanart.jpg', '001.*.fanart.jpg'))

    def has_poster_thumbnail(self, tvid, prodid):
        # type: (int, int) -> bool
        """
        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :return: true if a cached poster thumbnail exists for the given tvid prodid
        :rtype: bool
        """
        return self.has_file(self.poster_thumb_path(tvid, prodid))

    def has_banner_thumbnail(self, tvid, prodid):
        # type: (int, int) -> bool
        """
        :param tvid: tvid
        :type tvid: int
        :param prodid: prodid
        :type prodid: int or long
        :return: true if a cached banner exists for the given tvid prodid
        :rtype: bool
        """
        return self.has_file(self.banner_thumb_path(tvid, prodid))

    BANNER = 1
    POSTER = 2
    BANNER_THUMB = 3
    POSTER_THUMB = 4
    FANART = 5

    # img_type_str = {
    #     1: 'Banner',
    #     2: 'Poster',
    #     3: 'Banner thumb',
    #     4: 'Poster thumb',
    #     5: 'Fanart'
    # }

    @staticmethod
    def get_img_dimensions(image, is_binary=False):
        # type: (AnyStr, bool) -> Optional[Tuple[integer_types, integer_types, float]]
        """
        get image dimensions: width, height, ratio
        :param image: image file or data
        :param is_binary: is data instead of path
        """
        if not is_binary and not os.path.isfile(image):
            logger.warning(f'File not found to determine image type of {image}')
            return
        if not image:
            logger.warning('No Image Data to determinate image type')
            return

        try:
            if is_binary:
                img_parser = guessParser(StringInputStream(image))
            else:
                img_parser = createParser(image)
            img_parser.parse_comments = False
            img_parser.parse_exif = False
            img_parser.parse_photoshop_content = False
            img_metadata = extractMetadata(img_parser, quality=QUALITY_BEST)
        except (BaseException, Exception) as e:
            logger.debug(f'Unable to extract metadata from {image}, not using file. Error: {ex(e)}')
            return

        if not img_metadata:
            if is_binary:
                msg = 'Image Data'
            else:
                msg = image
            logger.debug(f'Unable to extract metadata from {msg}, not using file')
            return

        width = img_metadata.get('width')
        height = img_metadata.get('height')
        img_ratio = float(width) / float(height)

        if not is_binary:
            # noinspection PyProtectedMember
            img_parser.stream._input.close()

        return width, height, img_ratio

    def which_type(self, image, is_binary=False):
        # type: (AnyStr, bool) -> Optional[int]
        """
        Analyzes the image provided and attempts to determine whether it is a poster, banner or fanart.

        :param image: full path to the image or image data
        :param is_binary: is binary data instead path to image
        :return: BANNER, POSTER, FANART or None if image type is not detected or doesn't exist
        :rtype: int
        """

        result = self.get_img_dimensions(image, is_binary)
        if not result:
            return

        img_width, img_height, img_ratio = result

        if is_binary:
            msg_data = '<Image Data>'
        else:
            msg_data = image.replace('%', '%%')
        msg_success = 'Treating image as %s' \
                      + ' with extracted aspect ratio from %s' % msg_data
        # most posters are around 0.68 width/height ratio (eg. 680/1000)
        if 0.55 <= img_ratio <= 0.8:
            logger.debug(msg_success % 'poster')
            return self.POSTER

        # most banners are around 5.4 width/height ratio (eg. 758/140)
        if 5 <= img_ratio <= 6:
            logger.debug(msg_success % 'banner')
            return self.BANNER

        # most fan art are around 1.7 width/height ratio (eg. 1280/720 or 1920/1080)
        if 1.7 <= img_ratio <= 1.8:
            if 500 < img_width:
                logger.debug(msg_success % 'fanart')
                return self.FANART

            logger.warning('Skipped image with fanart aspect ratio but less than 500 pixels wide')
        else:
            logger.warning(f'Skipped image with useless ratio {img_ratio}')

    def should_refresh(self, image_type=None, provider='local'):
        # type: (int, Optional[AnyStr]) -> bool
        """

        :param image_type: image type
        :type image_type: int
        :param provider: provider name
        :type provider: AnyStr
        :return:
        :rtype: bool
        """
        my_db = db.DBConnection('cache.db', row_type='dict')

        sql_result = my_db.select('SELECT time FROM lastUpdate WHERE provider = ?',
                                  ['imsg_%s_%s' % ((image_type, self.FANART)[None is image_type], provider)])

        if sql_result:
            minutes_iv = 60 * 3
            # daily_interval = 60 * 60 * 23
            iv = minutes_iv
            now_stamp = SGDatetime.timestamp_near()
            the_time = int(sql_result[0]['time'])
            return now_stamp - the_time > iv

        return True

    def set_last_refresh(self, image_type=None, provider='local'):
        # type: (int, Optional[AnyStr]) -> None
        """

        :param image_type: image type
        :type image_type: int or None
        :param provider: provider name
        :type provider: AnyStr
        """
        my_db = db.DBConnection('cache.db')
        my_db.upsert('lastUpdate',
                     {'time': SGDatetime.timestamp_near()},
                     {'provider': 'imsg_%s_%s' % ((image_type, self.FANART)[None is image_type], provider)})

    def _cache_image_from_file(self, image_path, img_type, tvid, prodid, prefix='', move_file=False):
        # type: (AnyStr, int, int, int, Optional[AnyStr], Optional[bool]) -> Union[AnyStr, bool]
        """
        Takes the image provided and copies or moves it to the cache folder

        :param image_path: path to the image to cache
        :type image_path: AnyStr
        :param img_type: BANNER, POSTER, or FANART
        :type img_type: int
        :param tvid: id of the TV info source this image belongs to
        :type tvid: int
        :param prodid: id of the show this image belongs to
        :type prodid: int or long
        :param prefix: string to use at the start of a filename (e.g. '001.')
        :type prefix: AnyStr
        :param move_file: True if action is to move the file else file should be copied
        :type move_file: bool
        :return: full path to cached file or None
        :rtype: AnyStr
        """

        # generate the path based on the type, tvid and prodid
        fanart_dir = []
        id_args = (tvid, prodid)
        if self.POSTER == img_type:
            dest_path = self.poster_path(*id_args)
            dest_thumb_path = self.poster_thumb_path(*id_args)
        elif self.BANNER == img_type:
            dest_path = self.banner_path(*id_args)
            dest_thumb_path = self.banner_thumb_path(*id_args)
        elif self.FANART == img_type:
            dest_thumb_path = None
            with open(image_path, mode='rb') as resource:
                crc = '%05X' % (zlib.crc32(resource.read()) & 0xFFFFFFFF)
            dest_path = self.fanart_path(*id_args + (prefix,)).replace('.fanart.jpg', '.%s.fanart.jpg' % crc)
            fanart_dir = [self._fanart_dir(*id_args)]
        else:
            logger.error(f'Invalid cache image type: {img_type}')
            return False

        for cache_dir in [self.shows_dir, self._thumbnails_dir(*id_args)] + fanart_dir:
            sg_helpers.make_path(cache_dir)

        logger.log(f'{("Copy", "Mov")[move_file]}ing from {image_path} to {dest_path}')
        # copy poster, banner as thumb, even if moved we need to duplicate the images
        if img_type in (self.POSTER, self.BANNER) and dest_thumb_path:
            sg_helpers.copy_file(image_path, dest_thumb_path)
        if move_file:
            sg_helpers.move_file(image_path, dest_path)
        else:
            sg_helpers.copy_file(image_path, dest_path)

        return os.path.isfile(dest_path) and dest_path or None

    def _cache_info_source_images(self, show_obj, img_type, num_files=0, max_files=500, force=False, show_infos=None):
        # type: (TVShow, int, int, int, bool, ShowInfosDict) -> bool
        """
        Retrieves an image of the type specified from TV info source and saves it to the cache folder

        :param show_obj: TVShow object to cache an image for
        :param img_type:  BANNER, POSTER, or FANART
        :param num_files:
        :param max_files:
        :param force:
        :param show_infos: dict of showinfo objects to use
        :return: bool representing success
        """

        # generate the path based on the type, tvid and prodid
        arg_tvid_prodid = (show_obj.tvid, show_obj.prodid)
        dest_thumb_path = None
        if self.POSTER == img_type:
            img_type_name = 'poster'
            dest_path = self.poster_path(*arg_tvid_prodid)
            dest_thumb_path = self.poster_thumb_path(*arg_tvid_prodid)
        elif self.BANNER == img_type:
            img_type_name = 'banner'
            dest_path = self.banner_path(*arg_tvid_prodid)
            dest_thumb_path = self.banner_thumb_path(*arg_tvid_prodid)
        elif self.FANART == img_type:
            img_type_name = 'fanart_all'
            dest_path = self.fanart_path(*arg_tvid_prodid).replace('fanart.jpg', '*')
        elif self.POSTER_THUMB == img_type:
            img_type_name = 'poster_thumb'
            dest_path = self.poster_thumb_path(*arg_tvid_prodid)
        elif self.BANNER_THUMB == img_type:
            img_type_name = 'banner_thumb'
            dest_path = self.banner_thumb_path(*arg_tvid_prodid)
        else:
            logger.error(f'Invalid cache image type: {img_type}')
            return False

        # retrieve the image from TV info source using the generic metadata class
        metadata_generator = GenericMetadata()
        if self.FANART == img_type:
            image_urls = metadata_generator.retrieve_show_image(img_type_name, show_obj, show_infos=show_infos)
            if None is image_urls:
                return False

            crcs = []
            for cache_file_name in glob.glob(dest_path):
                with open(cache_file_name, mode='rb') as resource:
                    crc = '%05X' % (zlib.crc32(resource.read()) & 0xFFFFFFFF)
                if crc not in crcs:
                    crcs += [crc]

            success = 0
            sources = []
            sickgear.MEMCACHE.setdefault('cookies', {})
            for image_url in image_urls or []:
                img_data = sg_helpers.get_url(image_url, nocache=True, as_binary=True,
                                              url_solver=sickgear.FLARESOLVERR_HOST,
                                              memcache_cookies=sickgear.MEMCACHE['cookies'])
                if None is img_data or self.FANART != self.which_type(img_data, is_binary=True):
                    continue

                crc = '%05X' % (zlib.crc32(img_data) & 0xFFFFFFFF)
                if crc in crcs:
                    continue
                crcs += [crc]
                img_source = ((((('', 'tvdb')['thetvdb.com' in image_url],
                                'tvrage')['tvrage.com' in image_url],
                               'fatv')['fanart.tv' in image_url],
                              'tmdb')['tmdb' in image_url],
                              'tvmaze')['tvmaze.com' in image_url]
                img_xtra = ''
                if 'tmdb' == img_source:
                    match = re.search(r'(?:.*\?(\d+$))?', image_url, re.I | re.M)
                    if match and None is not match.group(1):
                        img_xtra = match.group(1)
                file_desc = '%03d%s.%s.' % (num_files, ('.%s%s' % (img_source, img_xtra), '')['' == img_source], crc)
                cur_file_path = self.fanart_path(show_obj.tvid, show_obj.prodid, file_desc)
                result = metadata_generator.write_image(img_data, cur_file_path)
                if img_source:
                    sources += [img_source]
                num_files += (0, 1)[result]
                success += (0, 1)[result]
                if num_files > max_files:
                    break
            total = len(glob.glob(dest_path))
            logger.log(f'Saved {success} fanart images'
                       f'{("", " from " + ", ".join([x for x in list(set(sources))]))[0 < len(sources)]}.'
                       f' Cached {total} of max {sickgear.FANART_LIMIT} fanart file{sg_helpers.maybe_plural(total)}')
            return bool(success)

        image_urls = metadata_generator.retrieve_show_image(img_type_name, show_obj, return_links=True,
                                                            show_infos=show_infos)
        if None is image_urls:
            return False

        result = None
        for image_url in image_urls or []:
            if isinstance(image_url, tuple) and img_type in (self.BANNER, self.POSTER):
                img_url, thumb_url = image_url
            else:
                img_url, thumb_url = image_url, None
            img_data = sg_helpers.get_url(img_url, nocache=True, as_binary=True)
            if None is img_data or img_type != self.which_type(img_data, is_binary=True):
                continue
            result = metadata_generator.write_image(img_data, dest_path, force=force)
            if img_type in (self.BANNER, self.POSTER) and dest_thumb_path:
                thumb_img_data = sg_helpers.get_url(img_url, nocache=True, as_binary=True)
                thumb_result = None
                if thumb_img_data:
                    thumb_result = metadata_generator.write_image(thumb_img_data, dest_thumb_path, force=True)
                if not thumb_result:
                    metadata_generator.write_image(img_data, dest_thumb_path, force=True)
            break

        if result:
            logger.log(f'Saved image type {img_type_name}')
        return result

    def fill_cache(self, show_obj, force=False):
        # type: (TVShow, Optional[bool]) -> Optional[bool]
        """
        Caches all images for the given show. Copies them from the show dir if possible, or
        downloads them from TV info source if they aren't in the show dir.

        :param show_obj: TVShow object to cache images for
        :type show_obj: sickgear.tv.TVShow
        :param force:
        :type force: bool
        """

        arg_tvid_prodid = (show_obj.tvid, show_obj.prodid)
        # check if any images are cached
        need_images = {self.POSTER: not self.has_poster(*arg_tvid_prodid) or force,
                       self.BANNER: not self.has_banner(*arg_tvid_prodid) or force,
                       self.FANART: 0 < sickgear.FANART_LIMIT and (
                               force or not self.has_fanart(*arg_tvid_prodid)),
                       # use limit? shows less than a limit of say 50 would fail to fulfill images every day
                       # '%03d.*' % sickgear.FANART_LIMIT
                       self.POSTER_THUMB: not self.has_poster_thumbnail(*arg_tvid_prodid) or force,
                       self.BANNER_THUMB: not self.has_banner_thumbnail(*arg_tvid_prodid) or force}

        if not any(itervalues(need_images)):
            logger.log(f'{show_obj.tvid_prodid}: No new cache images needed. Done.')
            return

        show_infos = GenericMetadata.gen_show_infos_dict(show_obj)

        void = False
        if not void and need_images[self.FANART]:
            cache_path = self.fanart_path(*arg_tvid_prodid).replace('fanart.jpg', '')
            # num_images = len(fnmatch.filter(os.listdir(cache_path), '*.jpg'))

            for cache_dir in glob.glob(cache_path):
                if show_obj.tvid_prodid in sickgear.FANART_RATINGS:
                    del (sickgear.FANART_RATINGS[show_obj.tvid_prodid])
                result = sg_helpers.remove_file(cache_dir, tree=True)
                if result:
                    logger.debug(f'{result} cache file {cache_dir}')

        try:
            checked_files = []
            crcs = []

            for cur_provider in itervalues(sickgear.metadata_provider_dict):
                # check the show dir for poster or banner images and use them
                needed = []
                if any([need_images[self.POSTER], need_images[self.BANNER]]):
                    poster_path = cur_provider.get_poster_path(show_obj)
                    if poster_path not in checked_files and os.path.isfile(poster_path):
                        needed += [[False, poster_path]]
                if need_images[self.FANART]:
                    fanart_path = cur_provider.get_fanart_path(show_obj)
                    if fanart_path not in checked_files and os.path.isfile(fanart_path):
                        needed += [[True, fanart_path]]
                if 0 == len(needed):
                    break

                logger.debug(f'Checking for images from optional {cur_provider.name} metadata')

                for all_meta_provs, path_file in needed:
                    checked_files += [path_file]
                    cache_file_name = os.path.abspath(path_file)

                    with open(cache_file_name, mode='rb') as resource:
                        crc = '%05X' % (zlib.crc32(resource.read()) & 0xFFFFFFFF)
                    if crc in crcs:
                        continue
                    crcs += [crc]

                    cur_file_type = self.which_type(cache_file_name)

                    if None is cur_file_type:
                        continue

                    logger.debug(f'Checking if image {cache_file_name} '
                                 f'(type {str(cur_file_type)}'
                                 f' needs metadata: {("No", "Yes")[True is need_images[cur_file_type]]}'
                                 f')')

                    if need_images.get(cur_file_type):
                        need_images[cur_file_type] = (
                            (need_images[cur_file_type] + 1, 1)[isinstance(need_images[cur_file_type], bool)],
                            False)[not all_meta_provs]
                        if self.FANART == cur_file_type and \
                                (not sickgear.FANART_LIMIT or sickgear.FANART_LIMIT < need_images[cur_file_type]):
                            continue
                        logger.debug(f'Caching image found in the show directory to the image cache: {cache_file_name},'
                                     f' type {cur_file_type}')

                        self._cache_image_from_file(
                            cache_file_name, cur_file_type,
                            *arg_tvid_prodid + (('%03d.' % need_images[cur_file_type], '')[
                                                    isinstance(need_images[cur_file_type], bool)],))

        except exceptions_helper.ShowDirNotFoundException:
            logger.warning('Unable to search for images in show directory because it doesn\'t exist')

        # download images from TV info sources
        for image_type, name_type in [[self.POSTER, 'Poster'], [self.BANNER, 'Banner'], [self.FANART, 'Fanart']]:
            max_files = (500, sickgear.FANART_LIMIT)[self.FANART == image_type]
            if not max_files or max_files < need_images[image_type]:
                continue

            logger.debug(f'Seeing if we still need an image of type {name_type}:'
                         f' {("No", "Yes")[True is need_images[image_type]]}')
            if need_images[image_type]:
                file_num = (need_images[image_type] + 1, 1)[isinstance(need_images[image_type], bool)]
                if file_num <= max_files:
                    self._cache_info_source_images(show_obj, image_type, file_num, max_files, force=force,
                                                   show_infos=show_infos)

        logger.log('Done cache check')

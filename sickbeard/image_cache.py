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

import datetime
import glob
import os.path
import re
import time
import zlib

# noinspection PyPep8Naming
import encodingKludge as ek
import exceptions_helper
from exceptions_helper import ex
import sickbeard
from . import db, helpers, logger
from .metadata.generic import GenericMetadata

from six import itervalues

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Union
    from .tv import TVShow

from lib.hachoir.parser import createParser
from lib.hachoir.metadata import extractMetadata


class ImageCache(object):
    base_dir = None  # type: AnyStr or None
    shows_dir = None  # type: AnyStr or None

    def __init__(self):
        if None is ImageCache.base_dir and ek.ek(os.path.exists, sickbeard.CACHE_DIR):
            ImageCache.base_dir = ek.ek(os.path.abspath, ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images'))
            ImageCache.shows_dir = ek.ek(os.path.abspath, ek.ek(os.path.join, self.base_dir, 'shows'))

    def __del__(self):
        pass

    # @staticmethod
    # def _cache_dir():
    #     """
    #     Builds up the full path to the image cache directory
    #     """
    #     return ek.ek(os.path.abspath, ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images'))

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
            return ek.ek(os.path.abspath, ek.ek(os.path.join, self.shows_dir, '%s-%s' % (tvid, prodid), 'fanart'))

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
        return ek.ek(os.path.abspath, ek.ek(os.path.join, self.shows_dir, '%s-%s' % (tvid, prodid), 'thumbnails'))

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
        return ek.ek(os.path.join, self.shows_dir, '%s-%s' % (tvid, prodid), 'poster.jpg')

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
        return ek.ek(os.path.join, self.shows_dir, '%s-%s' % (tvid, prodid), 'banner.jpg')

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
        return ek.ek(os.path.join, self._fanart_dir(tvid, prodid), '%s%s' % (prefix, 'fanart.jpg'))

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
        return ek.ek(os.path.join, self._thumbnails_dir(tvid, prodid), 'poster.jpg')

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
        return ek.ek(os.path.join, self._thumbnails_dir(tvid, prodid), 'banner.jpg')

    @staticmethod
    def has_file(image_file):
        # type: (AnyStr) -> bool
        """
        :param image_file: image file
        :type image_file: AnyStr
        :return: true if a image_file exists
        :rtype: bool
        """
        result = []
        for filename in ek.ek(glob.glob, image_file):
            result.append(ek.ek(os.path.isfile, filename) and filename)
            logger.log(u'Found cached %s' % filename, logger.DEBUG)

        not any(result) and logger.log(u'No cache for %s' % image_file, logger.DEBUG)
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

    def which_type(self, path):
        # type: (AnyStr) -> Optional[int]
        """
        Analyzes the image provided and attempts to determine whether it is a poster, banner or fanart.

        :param path: full path to the image
        :type path: AnyStr
        :return: BANNER, POSTER, FANART or None if image type is not detected or doesn't exist
        :rtype: int
        """

        if not ek.ek(os.path.isfile, path):
            logger.log(u'File does not exist to determine image type of %s' % path, logger.WARNING)
            return None

        # use hachoir to parse the image for us
        try:
            img_parser = createParser(path)
            img_parser.parse_exif = False
            img_parser.parse_photoshop_content = False
            img_parser.parse_comments = False
            img_metadata = extractMetadata(img_parser)
        except (BaseException, Exception) as e:
            logger.log('Unable to extract metadata from %s, not using existing image. Error: %s' % (path, ex(e)),
                       logger.DEBUG)
            return None

        if not img_metadata:
            logger.log(u'Unable to extract metadata from %s, not using existing image' % path, logger.DEBUG)
            return None

        img_ratio = float(img_metadata.get('width')) / float(img_metadata.get('height'))

        # noinspection PyProtectedMember
        img_parser.stream._input.close()

        msg_success = u'Treating image as %s' \
                      + u' with extracted aspect ratio from %s' % path.replace('%', '%%')
        # most posters are around 0.68 width/height ratio (eg. 680/1000)
        if 0.55 < img_ratio < 0.8:
            logger.log(msg_success % 'poster', logger.DEBUG)
            return self.POSTER

        # most banners are around 5.4 width/height ratio (eg. 758/140)
        elif 5 < img_ratio < 6:
            logger.log(msg_success % 'banner', logger.DEBUG)
            return self.BANNER

        # most fanart are around 1.7 width/height ratio (eg. 1280/720 or 1920/1080)
        elif 1.7 < img_ratio < 1.8:
            if 500 < img_metadata.get('width'):
                logger.log(msg_success % 'fanart', logger.DEBUG)
                return self.FANART

            logger.log(u'Image found with fanart aspect ratio but less than 500 pixels wide, skipped', logger.WARNING)
            return None

        logger.log(u'Image not useful with size ratio %s, skipping' % img_ratio, logger.WARNING)

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
            minutes_freq = 60 * 3
            # daily_freq = 60 * 60 * 23
            freq = minutes_freq
            now_stamp = int(time.mktime(datetime.datetime.today().timetuple()))
            the_time = int(sql_result[0]['time'])
            return now_stamp - the_time > freq

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
                     {'time': int(time.mktime(datetime.datetime.today().timetuple()))},
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
        elif self.BANNER == img_type:
            dest_path = self.banner_path(*id_args)
        elif self.FANART == img_type:
            with open(image_path, mode='rb') as resource:
                crc = '%05X' % (zlib.crc32(resource.read()) & 0xFFFFFFFF)
            dest_path = self.fanart_path(*id_args + (prefix,)).replace('.fanart.jpg', '.%s.fanart.jpg' % crc)
            fanart_dir = [self._fanart_dir(*id_args)]
        else:
            logger.log(u'Invalid cache image type: ' + str(img_type), logger.ERROR)
            return False

        for cache_dir in [self.shows_dir, self._thumbnails_dir(*id_args)] + fanart_dir:
            helpers.make_dirs(cache_dir)

        logger.log(u'%sing from %s to %s' % (('Copy', 'Mov')[move_file], image_path, dest_path))
        if move_file:
            helpers.move_file(image_path, dest_path)
        else:
            helpers.copy_file(image_path, dest_path)

        return ek.ek(os.path.isfile, dest_path) and dest_path or None

    def _cache_info_source_images(self, show_obj, img_type, num_files=0, max_files=500, force=False):
        # type: (TVShow, int, int, int, Optional[bool]) -> bool
        """
        Retrieves an image of the type specified from TV info source and saves it to the cache folder

        :param show_obj: TVShow object to cache an image for
        :type show_obj: sickbeard.tv.TVShow
        :param img_type:  BANNER, POSTER, or FANART
        :type img_type: int
        :param num_files:
        :type num_files: int or long
        :param max_files:
        :type max_files: int or long
        :param force:
        :type force: bool
        :return: bool representing success
        :rtype: bool
        """

        # generate the path based on the type, tvid and prodid
        arg_tvid_prodid = (show_obj.tvid, show_obj.prodid)
        if self.POSTER == img_type:
            img_type_name = 'poster'
            dest_path = self.poster_path(*arg_tvid_prodid)
        elif self.BANNER == img_type:
            img_type_name = 'banner'
            dest_path = self.banner_path(*arg_tvid_prodid)
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
            logger.log(u'Invalid cache image type: ' + str(img_type), logger.ERROR)
            return False

        # retrieve the image from TV info source using the generic metadata class
        metadata_generator = GenericMetadata()
        if self.FANART == img_type:
            image_urls = metadata_generator.retrieve_show_image(img_type_name, show_obj)
            if None is image_urls:
                return False

            crcs = []
            for cache_file_name in ek.ek(glob.glob, dest_path):
                with open(cache_file_name, mode='rb') as resource:
                    crc = '%05X' % (zlib.crc32(resource.read()) & 0xFFFFFFFF)
                if crc not in crcs:
                    crcs += [crc]

            success = 0
            count_urls = len(image_urls)
            sources = []
            for image_url in image_urls or []:
                img_data = helpers.get_url(image_url, nocache=True, as_binary=True)
                if None is img_data:
                    continue
                crc = '%05X' % (zlib.crc32(img_data) & 0xFFFFFFFF)
                if crc in crcs:
                    count_urls -= 1
                    continue
                crcs += [crc]
                img_source = (((('', 'tvdb')['thetvdb.com' in image_url],
                                'tvrage')['tvrage.com' in image_url],
                               'fatv')['fanart.tv' in image_url],
                              'tmdb')['tmdb' in image_url]
                img_xtra = ''
                if 'tmdb' == img_source:
                    match = re.search(r'(?:.*\?(\d+$))?', image_url, re.I | re.M)
                    if match and None is not match.group(1):
                        img_xtra = match.group(1)
                file_desc = '%03d%s.%s.' % (num_files, ('.%s%s' % (img_source, img_xtra), '')['' == img_source], crc)
                cur_file_path = self.fanart_path(show_obj.tvid, show_obj.prodid, file_desc)
                result = metadata_generator.write_image(img_data, cur_file_path)
                if result and self.FANART != self.which_type(cur_file_path):
                    try:
                        ek.ek(os.remove, cur_file_path)
                    except OSError as e:
                        logger.log(u'Unable to remove %s: %s / %s' % (cur_file_path, repr(e), ex(e)), logger.WARNING)
                    continue
                if img_source:
                    sources += [img_source]
                num_files += (0, 1)[result]
                success += (0, 1)[result]
                if num_files > max_files:
                    break
            if count_urls:
                total = len(ek.ek(glob.glob, dest_path))
                logger.log(u'Saved %s of %s fanart images%s. Cached %s of max %s fanart file%s'
                           % (success, count_urls,
                              ('', ' from ' + ', '.join([x for x in list(set(sources))]))[0 < len(sources)],
                              total, sickbeard.FANART_LIMIT, helpers.maybe_plural(total)))
            return bool(count_urls) and not bool(count_urls - success)

        img_data = metadata_generator.retrieve_show_image(img_type_name, show_obj)
        if None is img_data:
            return False
        result = metadata_generator.write_image(img_data, dest_path, force=force)
        if result:
            logger.log(u'Saved image type %s' % img_type_name)
        return result

    def fill_cache(self, show_obj, force=False):
        # type: (TVShow, Optional[bool]) -> Optional[bool]
        """
        Caches all images for the given show. Copies them from the show dir if possible, or
        downloads them from TV info source if they aren't in the show dir.

        :param show_obj: TVShow object to cache images for
        :type show_obj: sickbeard.tv.TVShow
        :param force:
        :type force: bool
        """

        arg_tvid_prodid = (show_obj.tvid, show_obj.prodid)
        # check if any images are cached
        need_images = {self.POSTER: not self.has_poster(*arg_tvid_prodid) or force,
                       self.BANNER: not self.has_banner(*arg_tvid_prodid) or force,
                       self.FANART: 0 < sickbeard.FANART_LIMIT and (
                               force or not self.has_fanart(*arg_tvid_prodid)),
                       # use limit? shows less than a limit of say 50 would fail to fulfill images every day
                       # '%03d.*' % sickbeard.FANART_LIMIT
                       self.POSTER_THUMB: not self.has_poster_thumbnail(*arg_tvid_prodid) or force,
                       self.BANNER_THUMB: not self.has_banner_thumbnail(*arg_tvid_prodid) or force}

        if not any(itervalues(need_images)):
            logger.log(u'%s: No new cache images needed. Done.' % show_obj.tvid_prodid)
            return

        void = False
        if not void and need_images[self.FANART]:
            cache_path = self.fanart_path(*arg_tvid_prodid).replace('fanart.jpg', '')
            # num_images = len(fnmatch.filter(os.listdir(cache_path), '*.jpg'))

            for cache_dir in ek.ek(glob.glob, cache_path):
                if show_obj.tvid_prodid in sickbeard.FANART_RATINGS:
                    del (sickbeard.FANART_RATINGS[show_obj.tvid_prodid])
                result = helpers.remove_file(cache_dir, tree=True)
                if result:
                    logger.log(u'%s cache file %s' % (result, cache_dir), logger.DEBUG)

        try:
            checked_files = []
            crcs = []

            for cur_provider in itervalues(sickbeard.metadata_provider_dict):
                # check the show dir for poster or banner images and use them
                needed = []
                if any([need_images[self.POSTER], need_images[self.BANNER]]):
                    poster_path = cur_provider.get_poster_path(show_obj)
                    if poster_path not in checked_files and ek.ek(os.path.isfile, poster_path):
                        needed += [[False, poster_path]]
                if need_images[self.FANART]:
                    fanart_path = cur_provider.get_fanart_path(show_obj)
                    if fanart_path not in checked_files and ek.ek(os.path.isfile, fanart_path):
                        needed += [[True, fanart_path]]
                if 0 == len(needed):
                    break

                logger.log(u'Checking for images from optional %s metadata' % cur_provider.name, logger.DEBUG)

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

                    logger.log(u'Checking if image %s (type %s needs metadata: %s)'
                               % (cache_file_name, str(cur_file_type),
                                  ('No', 'Yes')[True is need_images[cur_file_type]]), logger.DEBUG)

                    if need_images.get(cur_file_type):
                        need_images[cur_file_type] = (
                            (need_images[cur_file_type] + 1, 1)[isinstance(need_images[cur_file_type], bool)],
                            False)[not all_meta_provs]
                        if self.FANART == cur_file_type and \
                                (not sickbeard.FANART_LIMIT or sickbeard.FANART_LIMIT < need_images[cur_file_type]):
                            continue
                        logger.log(u'Caching image found in the show directory to the image cache: %s, type %s'
                                   % (cache_file_name, cur_file_type), logger.DEBUG)

                        self._cache_image_from_file(
                            cache_file_name, cur_file_type,
                            *arg_tvid_prodid + (('%03d.' % need_images[cur_file_type], '')[
                                                    isinstance(need_images[cur_file_type], bool)],))

        except exceptions_helper.ShowDirNotFoundException:
            logger.log(u'Unable to search for images in show directory because it doesn\'t exist', logger.WARNING)

        # download images from TV info sources
        for image_type, name_type in [[self.POSTER, 'Poster'], [self.BANNER, 'Banner'], [self.FANART, 'Fanart'],
                                      [self.POSTER_THUMB, 'Poster Thumb'], [self.BANNER_THUMB, 'Banner Thumb']]:
            max_files = (500, sickbeard.FANART_LIMIT)[self.FANART == image_type]
            if not max_files or max_files < need_images[image_type]:
                continue

            logger.log(u'Seeing if we still need an image of type %s: %s'
                       % (name_type, ('No', 'Yes')[True is need_images[image_type]]), logger.DEBUG)
            if need_images[image_type]:
                file_num = (need_images[image_type] + 1, 1)[isinstance(need_images[image_type], bool)]
                if file_num <= max_files:
                    self._cache_info_source_images(show_obj, image_type, file_num, max_files, force=force)

        logger.log(u'Done cache check')

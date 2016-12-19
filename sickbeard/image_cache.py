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
import fnmatch
import glob
import os.path
import re
import shutil
import time

import sickbeard
from sickbeard import helpers, logger, exceptions
from sickbeard import encodingKludge as ek
from sickbeard import db

from sickbeard.metadata.generic import GenericMetadata

from lib.hachoir_parser import createParser
from lib.hachoir_metadata import extractMetadata
from lib.send2trash import send2trash
try:
    import zlib
except:
    pass


class ImageCache:
    def __init__(self):
        pass

    def __del__(self):
        pass

    @staticmethod
    def _cache_dir():
        """
        Builds up the full path to the image cache directory
        """
        return ek.ek(os.path.abspath, ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images'))

    def _fanart_dir(self, indexer_id=None):
        """
        Builds up the full path to the fanart image cache directory
        """
        args = [os.path.join, self._cache_dir(), 'fanart'] + \
            (None is not indexer_id and [str(indexer_id).split('.')[0]] or [])
        return ek.ek(os.path.abspath, ek.ek(*args))

    def _thumbnails_dir(self):
        """
        Builds up the full path to the thumbnails image cache directory
        """
        return ek.ek(os.path.abspath, ek.ek(os.path.join, self._cache_dir(), 'thumbnails'))

    def poster_path(self, indexer_id):
        """
        Builds up the path to a poster cache for a given Indexer ID

        returns: a full path to the cached poster file for the given Indexer ID

        indexer_id: ID of the show to use in the file name
        """
        return ek.ek(os.path.join, self._cache_dir(), '%s.poster.jpg' % indexer_id)

    def banner_path(self, indexer_id):
        """
        Builds up the path to a banner cache for a given Indexer ID

        returns: a full path to the cached banner file for the given Indexer ID

        indexer_id: ID of the show to use in the file name
        """
        return ek.ek(os.path.join, self._cache_dir(), '%s.banner.jpg' % indexer_id)

    def fanart_path(self, indexer_id):
        """
        Builds up the path to a fanart cache for a given Indexer ID

        returns: a full path to the cached fanart file for the given Indexer ID

        indexer_id: ID of the show to use in the file name
        """
        return ek.ek(os.path.join, self._fanart_dir(indexer_id), '%s.fanart.jpg' % indexer_id)

    def poster_thumb_path(self, indexer_id):
        """
        Builds up the path to a poster cache for a given Indexer ID

        returns: a full path to the cached poster file for the given Indexer ID

        indexer_id: ID of the show to use in the file name
        """
        return ek.ek(os.path.join, self._thumbnails_dir(), '%s.poster.jpg' % indexer_id)

    def banner_thumb_path(self, indexer_id):
        """
        Builds up the path to a poster cache for a given Indexer ID

        returns: a full path to the cached poster file for the given Indexer ID

        indexer_id: ID of the show to use in the file name
        """
        return ek.ek(os.path.join, self._thumbnails_dir(), '%s.banner.jpg' % indexer_id)

    @staticmethod
    def has_file(image_file):
        """
        Returns true if a image_file exists
        """
        result = []
        for filename in ek.ek(glob.glob, image_file):
            result.append(ek.ek(os.path.isfile, filename) and filename)
            logger.log(u'Found cached %s' % filename, logger.DEBUG)

        not any(result) and logger.log(u'No cache for %s' % image_file, logger.DEBUG)
        return any(result)

    def has_poster(self, indexer_id):
        """
        Returns true if a cached poster exists for the given Indexer ID
        """
        return self.has_file(self.poster_path(indexer_id))

    def has_banner(self, indexer_id):
        """
        Returns true if a cached banner exists for the given Indexer ID
        """
        return self.has_file(self.banner_path(indexer_id))

    def has_fanart(self, indexer_id):
        """
        Returns true if a cached fanart exists for the given Indexer ID
        """
        return self.has_file(self.fanart_path(indexer_id))

    def has_poster_thumbnail(self, indexer_id):
        """
        Returns true if a cached poster thumbnail exists for the given Indexer ID
        """
        return self.has_file(self.poster_thumb_path(indexer_id))

    def has_banner_thumbnail(self, indexer_id):
        """
        Returns true if a cached banner exists for the given Indexer ID
        """
        return self.has_file(self.banner_thumb_path(indexer_id))

    BANNER = 1
    POSTER = 2
    BANNER_THUMB = 3
    POSTER_THUMB = 4
    FANART = 5

    def which_type(self, path):
        """
        Analyzes the image provided and attempts to determine whether it is a poster, banner or fanart.

        returns: BANNER, POSTER, FANART or None if image type is not detected or doesn't exist

        path: full path to the image
        """

        if not ek.ek(os.path.isfile, path):
            logger.log(u'File does not exist to determine image type of %s' % path, logger.WARNING)
            return None

        # use hachoir to parse the image for us
        img_parser = createParser(path)
        img_metadata = extractMetadata(img_parser)

        if not img_metadata:
            logger.log(u'Unable to extract metadata from %s, not using existing image' % path, logger.DEBUG)
            return None

        img_ratio = float(img_metadata.get('width')) / float(img_metadata.get('height'))

        img_parser.stream._input.close()

        msg_success = u'Treating image as %s'\
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
        else:
            logger.log(u'Image not useful with size ratio %s, skipping' % img_ratio, logger.WARNING)
            return None

    def should_refresh(self, image_type=None, provider='local'):
        my_db = db.DBConnection('cache.db', row_type='dict')

        sql_results = my_db.select('SELECT time FROM lastUpdate WHERE provider = ?',
                                   ['imsg_%s_%s' % ((image_type, self.FANART)[None is image_type], provider)])

        if sql_results:
            minutes_freq = 60 * 3
            # daily_freq = 60 * 60 * 23
            freq = minutes_freq
            now_stamp = int(time.mktime(datetime.datetime.today().timetuple()))
            the_time = int(sql_results[0]['time'])
            return now_stamp - the_time > freq

        return True

    def set_last_refresh(self, image_type=None, provider='local'):
        my_db = db.DBConnection('cache.db')
        my_db.upsert('lastUpdate',
                     {'time': int(time.mktime(datetime.datetime.today().timetuple()))},
                     {'provider': 'imsg_%s_%s' % ((image_type, self.FANART)[None is image_type], provider)})

    def _cache_image_from_file(self, image_path, img_type, indexer_id, move_file=False):
        """
        Takes the image provided and copies or moves it to the cache folder

        returns: full path to cached file or None

        image_path: path to the image to cache
        img_type: BANNER, POSTER, or FANART
        indexer_id: id of the show this image belongs to
        move_file: True if action is to move the file else file should be copied
        """

        # generate the path based on the type & indexer_id
        fanart_subdir = []
        if img_type == self.POSTER:
            dest_path = self.poster_path(indexer_id)
        elif img_type == self.BANNER:
            dest_path = self.banner_path(indexer_id)
        elif img_type == self.FANART:
            with open(image_path, mode='rb') as resource:
                crc = '%05X' % (zlib.crc32(resource.read()) & 0xFFFFFFFF)
            fanart_subdir = [self._fanart_dir(indexer_id)]
            dest_path = self.fanart_path(indexer_id).replace('.fanart.jpg', '.%s.fanart.jpg' % crc)
        else:
            logger.log(u'Invalid cache image type: ' + str(img_type), logger.ERROR)
            return False

        for cache_dir in [self._cache_dir(), self._thumbnails_dir(), self._fanart_dir()] + fanart_subdir:
            helpers.make_dirs(cache_dir)

        logger.log(u'%sing from %s to %s' % (('Copy', 'Mov')[move_file], image_path, dest_path))
        if move_file:
            helpers.moveFile(image_path, dest_path)
        else:
            helpers.copyFile(image_path, dest_path)

        return ek.ek(os.path.isfile, dest_path) and dest_path or None

    def _cache_image_from_indexer(self, show_obj, img_type, num_files=0, max_files=500):
        """
        Retrieves an image of the type specified from indexer and saves it to the cache folder

        returns: bool representing success

        show_obj: TVShow object that we want to cache an image for
        img_type: BANNER, POSTER, or FANART
        """

        # generate the path based on the type & indexer_id
        if img_type == self.POSTER:
            img_type_name = 'poster'
            dest_path = self.poster_path(show_obj.indexerid)
        elif img_type == self.BANNER:
            img_type_name = 'banner'
            dest_path = self.banner_path(show_obj.indexerid)
        elif img_type == self.FANART:
            img_type_name = 'fanart_all'
            dest_path = self.fanart_path(show_obj.indexerid).replace('fanart.jpg', '*')
        elif img_type == self.POSTER_THUMB:
            img_type_name = 'poster_thumb'
            dest_path = self.poster_thumb_path(show_obj.indexerid)
        elif img_type == self.BANNER_THUMB:
            img_type_name = 'banner_thumb'
            dest_path = self.banner_thumb_path(show_obj.indexerid)
        else:
            logger.log(u'Invalid cache image type: ' + str(img_type), logger.ERROR)
            return False

        # retrieve the image from indexer using the generic metadata class
        metadata_generator = GenericMetadata()
        if img_type == self.FANART:
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
                img_data = helpers.getURL(image_url, nocache=True)
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
                file_desc = '%s.%03d%s.%s' % (
                    show_obj.indexerid, num_files, ('.%s%s' % (img_source, img_xtra), '')['' == img_source], crc)
                cur_file_path = self.fanart_path(file_desc)
                result = metadata_generator.write_image(img_data, cur_file_path)
                if result and self.FANART != self.which_type(cur_file_path):
                    try:
                        ek.ek(os.remove, cur_file_path)
                    except OSError as e:
                        logger.log(u'Unable to remove %s: %s / %s' % (cur_file_path, repr(e), str(e)), logger.WARNING)
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
        result = metadata_generator.write_image(img_data, dest_path)
        if result:
            logger.log(u'Saved image type %s' % img_type_name)
        return result

    def clean_fanart(self):
        ratings_found = False
        fanarts = ek.ek(glob.glob, '%s.jpg' % self._fanart_dir('*'))
        if fanarts:
            logger.log(u'Reorganising fanart cache files', logger.DEBUG)

            for image_path in fanarts:
                image_path_parts = ek.ek(os.path.basename, image_path).split('.')
                dest_path = self._cache_image_from_file(image_path, self.FANART, '.'.join(image_path_parts[0:-2]), True)
                if None is not dest_path:
                    src_file_id = '.'.join(image_path_parts[1:-2])
                    rating = sickbeard.FANART_RATINGS.get(image_path_parts[0], {}).get(src_file_id, None)
                    if None is not rating:
                        ratings_found = True
                        dest_file_id = str('.'.join(ek.ek(os.path.basename, dest_path).split('.')[1:-2]))
                        sickbeard.FANART_RATINGS[image_path_parts[0]][dest_file_id] = rating
                        del (sickbeard.FANART_RATINGS[image_path_parts[0]][src_file_id])
        return ratings_found

    def fill_cache(self, show_obj, force=False):
        """
        Caches all images for the given show. Copies them from the show dir if possible, or
        downloads them from indexer if they aren't in the show dir.

        show_obj: TVShow object to cache images for
        """

        show_id = '%s' % show_obj.indexerid

        # check if any images are cached
        need_images = {self.POSTER: not self.has_poster(show_id),
                       self.BANNER: not self.has_banner(show_id),
                       self.FANART: 0 < sickbeard.FANART_LIMIT and (force or not self.has_fanart(show_id + '.001.*')),
                       # use limit? shows less than a limit of say 50 would fail to fulfill images every day
                       # '.%03d.*' % sickbeard.FANART_LIMIT
                       self.POSTER_THUMB: not self.has_poster_thumbnail(show_id),
                       self.BANNER_THUMB: not self.has_banner_thumbnail(show_id)}

        if not any(need_images.values()):
            logger.log(u'%s: No new cache images needed. Done.' % show_id)
            return

        void = False
        if not void and need_images[self.FANART]:
            action = ('delete', 'trash')[sickbeard.TRASH_REMOVE_SHOW]

            cache_path = self.fanart_path(show_id).replace('%s.fanart.jpg' % show_id, '')
            # num_images = len(fnmatch.filter(os.listdir(cache_path), '*.jpg'))

            for cache_dir in ek.ek(glob.glob, cache_path):
                if show_id in sickbeard.FANART_RATINGS:
                    del (sickbeard.FANART_RATINGS[show_id])
                logger.log(u'Attempt to %s purge cache file %s' % (action, cache_dir), logger.DEBUG)
                try:
                    if sickbeard.TRASH_REMOVE_SHOW:
                        send2trash(cache_dir)
                    else:
                        shutil.rmtree(cache_dir)

                except OSError as e:
                    logger.log(u'Unable to %s %s: %s / %s' % (action, cache_dir, repr(e), str(e)), logger.WARNING)

        try:
            checked_files = []
            crcs = []

            for cur_provider in sickbeard.metadata_provider_dict.values():
                # check the show dir for poster or banner images and use them
                needed = []
                if any([need_images[self.POSTER], need_images[self.BANNER]]):
                    needed += [[False, cur_provider.get_poster_path(show_obj)]]
                if need_images[self.FANART]:
                    needed += [[True, cur_provider.get_fanart_path(show_obj)]]
                if 0 == len(needed):
                    break

                logger.log(u'Checking for images from optional %s metadata' % cur_provider.name, logger.DEBUG)

                for all_meta_provs, path_file in needed:
                    if path_file in checked_files:
                        continue
                    checked_files += [path_file]
                    if ek.ek(os.path.isfile, path_file):
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

                            self._cache_image_from_file(cache_file_name, cur_file_type, '%s%s' % (
                                show_id, ('.%03d' % need_images[cur_file_type], '')[
                                    isinstance(need_images[cur_file_type], bool)]))

        except exceptions.ShowDirNotFoundException:
            logger.log(u'Unable to search for images in show directory because it doesn\'t exist', logger.WARNING)

        # download missing ones from indexer
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
                    self._cache_image_from_indexer(show_obj, image_type, file_num, max_files)

        logger.log(u'Done cache check')

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

from .. import logger
import sg_helpers

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional


def get_show_image(url, img_num=None, show_name=None, supress_log=False):
    # type: (AnyStr, Optional[int], Optional[AnyStr], bool) -> Optional[bytes]
    """

    :param url: url
    :param img_num:
    :param show_name:
    :param supress_log:
    :type show_name: AnyStr or None
    """
    # fix for undocumented type change from str to dict
    if isinstance(url, dict):
        url = url.get('original', url.get('medium'))

    if None is url:
        return None

    # if they provided a fanart number try to use it instead
    temp_url = url if None is img_num else url.split('-')[0] + '-' + str(img_num) + '.jpg'

    logger.debug(f'Fetching image from {temp_url}')

    from sickgear import FLARESOLVERR_HOST, MEMCACHE
    MEMCACHE.setdefault('cookies', {})
    image_data = sg_helpers.get_url(temp_url, as_binary=True,
                                    url_solver=FLARESOLVERR_HOST, memcache_cookies=MEMCACHE['cookies'])
    if None is image_data:
        if supress_log:
            return
        logger.warning(f'There was an error trying to retrieve the image'
                       f'{("", " for show: %s" % show_name)[None is not show_name]}, aborting')
        return

    return image_data

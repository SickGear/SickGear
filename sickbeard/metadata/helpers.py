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

from .. import helpers, logger

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional


def getShowImage(url, img_num=None, show_name=None, supress_log=False):
    # type: (AnyStr, Optional[int], Optional[AnyStr], bool) -> Optional[bytes]
    """

    :param url: url
    :param img_num:
    :param show_name:
    :param supress_log:
    :type show_name: AnyStr or None
    """
    if None is url:
        return None

    # if they provided a fanart number try to use it instead
    temp_url = url if None is img_num else url.split('-')[0] + '-' + str(img_num) + '.jpg'

    logger.log(u'Fetching image from ' + temp_url, logger.DEBUG)

    image_data = helpers.get_url(temp_url, as_binary=True)
    if None is image_data:
        if supress_log:
            return
        logger.log('There was an error trying to retrieve the image%s, aborting' %
                   ('', ' for show: %s' % show_name)[None is not show_name], logger.WARNING)
        return

    return image_data

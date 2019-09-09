# Author: Tyler Fenby <tylerfenby@gmail.com>
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

from __future__ import with_statement

import exceptions_helper

import sickbeard
from . import logger, search_queue, show_name_helpers
from ._legacy_classes import LegacyFailedProcessor
from .name_parser.parser import NameParser, InvalidNameException, InvalidShowException

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr


class FailedProcessor(LegacyFailedProcessor):
    """Take appropriate action when a download fails to complete"""

    def __init__(self, dir_name, nzb_name, show_obj=None):
        """
        :param dir_name: Full path to the folder of the failed download
        :type dir_name: AnyStr
        :param nzb_name: Full name of the nzb file that failed
        :type nzb_name: AnyStr or None
        :param show_obj: show object
        :type show_obj: sickbeard.tv.TVShow or None
        """
        self.dir_name = dir_name  # type: AnyStr
        self.nzb_name = nzb_name  # type: AnyStr or None
        self._show_obj = show_obj  # type: sickbeard.tv.TVShow or None

        self.log = ''  # type: AnyStr

    @property
    def show_obj(self):
        """
        :rtype: sickbeard.tv.TVShow or None
        """
        return self._show_obj

    @show_obj.setter
    def show_obj(self, val):
        """
        :param val: show object or None
        :type val: sickbeard.tv.TVShow or None
        """
        self._show_obj = val

    def process(self):
        """

        :return: success
        :type: bool or None
        """
        self._log(u'Failed download detected: (%s, %s)' % (self.nzb_name, self.dir_name))

        releaseName = show_name_helpers.determineReleaseName(self.dir_name, self.nzb_name)
        if None is releaseName:
            self._log(u'Warning: unable to find a valid release name.', logger.WARNING)
            raise exceptions_helper.FailedProcessingFailed()

        try:
            parser = NameParser(False, show_obj=self.show_obj, convert=True)
            parsed = parser.parse(releaseName)
        except InvalidNameException:
            self._log(u'Error: release name is invalid: ' + releaseName, logger.DEBUG)
            raise exceptions_helper.FailedProcessingFailed()
        except InvalidShowException:
            self._log(u'Error: unable to parse release name %s into a valid show' % releaseName, logger.DEBUG)
            raise exceptions_helper.FailedProcessingFailed()

        logger.log(u"name_parser info: ", logger.DEBUG)
        logger.log(u" - " + str(parsed.series_name), logger.DEBUG)
        logger.log(u" - " + str(parsed.season_number), logger.DEBUG)
        logger.log(u" - " + str(parsed.episode_numbers), logger.DEBUG)
        logger.log(u" - " + str(parsed.extra_info), logger.DEBUG)
        logger.log(u" - " + str(parsed.release_group), logger.DEBUG)
        logger.log(u" - " + str(parsed.air_date), logger.DEBUG)

        for episode in parsed.episode_numbers:
            segment = parsed.show_obj.get_episode(parsed.season_number, episode)

            cur_failed_queue_item = search_queue.FailedQueueItem(parsed.show_obj, [segment])
            sickbeard.searchQueueScheduler.action.add_item(cur_failed_queue_item)

        return True

    def _log(self, message, level=logger.MESSAGE):
        """Log to regular logfile and save for return for PP script log
        :param message: message
        :type message: AnyStr
        :param level: logging level
        :type level: int
        """
        logger.log(message, level)
        self.log += message + '\n'

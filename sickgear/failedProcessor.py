# Author: Tyler Fenby <tylerfenby@gmail.com>
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

import exceptions_helper

import sickgear
from . import logger, failed_history, history, search_queue, show_name_helpers
from ._legacy_classes import LegacyFailedProcessor
from .name_parser.parser import NameParser, InvalidNameException, InvalidShowException

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, Optional, Union
    from .tv import TVShow


class FailedProcessor(LegacyFailedProcessor):
    """Take appropriate action when a download fails to complete"""

    def __init__(self, dir_name, nzb_name, show_obj=None, client=None, client_uid=None, puid=None):
        # type: (str, str, TVShow, int, Union[int, str], str) -> None
        """
        :param dir_name: Full path to the folder of the failed download
        :param nzb_name: Full name of the nzb file that failed
        :param show_obj: show object
        :param client: client
        :param client_uid: client uid
        :param puid: puid
        """
        self.dir_name = dir_name  # type: str
        self.nzb_name = nzb_name  # type: Optional[str]
        self._show_obj = show_obj  # type: Optional[TVShow]
        self.client = client  # type: Optional[int]
        self.client_uid = client_uid  # type: Union[int, str]
        self.puid = puid  # type: Optional[str]

        self.log = ''  # type: str

    @property
    def show_obj(self):
        """
        :rtype: sickgear.tv.TVShow or None
        """
        return self._show_obj

    @show_obj.setter
    def show_obj(self, val):
        """
        :param val: show object or None
        :type val: sickgear.tv.TVShow or None
        """
        self._show_obj = val

    def process(self):
        """

        :return: success
        :type: bool or None
        """
        self._log(f'Failed download detected: ({self.nzb_name}, {self.dir_name})')

        sql_result, release_name = None, None
        if self.puid:
            sql_result = history.find_data_by_puidstr(self.puid)
            if sql_result:
                release_name = sql_result['resource']
        if not release_name:
            release_name = show_name_helpers.determine_release_name(self.dir_name, self.nzb_name)
        if None is release_name:
            self._log('Warning: unable to find a valid release name.', logger.WARNING)
            raise exceptions_helper.FailedProcessingFailed()

        if failed_history.has_failed(release_name, puid=self.puid, client=self.client, client_uid=self.client_uid):
            self._log('Warning: release was already failed processed.', logger.WARNING)
            raise exceptions_helper.FailedProcessingFailed()

        try:
            parser = NameParser(False, show_obj=self.show_obj, convert=True)
            parsed = parser.parse(release_name)
        except InvalidNameException:
            self._log(f'Error: release name is invalid: {release_name}', logger.DEBUG)
            raise exceptions_helper.FailedProcessingFailed()
        except InvalidShowException:
            self._log(f'Error: unable to parse release name {release_name} into a valid show', logger.DEBUG)
            raise exceptions_helper.FailedProcessingFailed()

        for cur_msg in (
                'name_parser info: ',
                f' - {parsed.series_name}',
                f' - {parsed.season_number}',
                f' - {parsed.episode_numbers}',
                f' - {parsed.extra_info}',
                f' - {parsed.release_group}',
                f' - {parsed.air_date}'
        ):
            logger.debug(cur_msg)

        for episode in parsed.episode_numbers:
            segment = parsed.show_obj.get_episode(parsed.season_number, episode)

            cur_failed_queue_item = search_queue.FailedQueueItem(parsed.show_obj, [segment],
                                                                 client=self.client, client_uid=self.client_uid,
                                                                 puid=self.puid)
            sickgear.search_queue_scheduler.action.add_item(cur_failed_queue_item)

        return True

    def _log(self, message, level=logger.MESSAGE):
        """Log to regular logfile and save for return for PP script log
        :param message: message
        :type message: AnyStr
        :param level: logging level
        :type level: int
        """
        logger.log(message, level)
        self.log += f'{message}\n'

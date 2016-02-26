# Author: Nyaran <nyayukko@gmail.com>, based on Antoine Bertin <diaoulael@gmail.com> work
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import datetime
from sickbeard.common import *
from sickbeard import logger
from sickbeard import helpers
from sickbeard import encodingKludge as ek
from sickbeard import db
from sickbeard.scheduler import Job
from lib import subliminal

SINGLE = 'und'


def sorted_service_list():

    services_mapping = dict([(i.lower(), i) for i in subliminal.core.SERVICES])

    new_list = []

    # add all services in the priority list, in order
    index = 0
    for curService in sickbeard.SUBTITLES_SERVICES_LIST:
        if curService in services_mapping:
            cur_service = {'id': curService, 'image': '%s.png' % curService,
                           'name': services_mapping[curService],
                           'enabled': 1 == sickbeard.SUBTITLES_SERVICES_ENABLED[index],
                           'api_based': __import__('lib.subliminal.services.%s' % curService, globals=globals(),
                                                   locals=locals(), fromlist=['Service'], level=-1).Service.api_based,
                           'url': __import__('lib.subliminal.services.%s' % curService, globals=globals(),
                                             locals=locals(), fromlist=['Service'], level=-1).Service.site_url}
            new_list.append(cur_service)
        index += 1

    # add any services that are missing from that list
    for curService in services_mapping.keys():
        if curService not in [i['id'] for i in new_list]:
            cur_service = {'id': curService, 'image': '%s.png' % curService,
                           'name': services_mapping[curService],
                           'enabled': False,
                           'api_based': __import__('lib.subliminal.services.' + curService, globals=globals(),
                                                   locals=locals(), fromlist=['Service'], level=-1).Service.api_based,
                           'url': __import__('lib.subliminal.services.' + curService, globals=globals(),
                                             locals=locals(), fromlist=['Service'], level=-1).Service.site_url}
            new_list.append(cur_service)

    return new_list


def get_enabled_service_list():

    return [i['name'] for i in sorted_service_list() if i['enabled']]


def is_valid_language(language):

    return subliminal.language.language_list(language)


def get_language_name(select_lang):

    return subliminal.language.Language(select_lang).name


def wanted_languages(sql_like=False):
    languages = sorted(sickbeard.SUBTITLES_LANGUAGES)
    if sql_like:
        return '%%%s%%' % ','.join(languages)

    return languages


def subtitles_languages(video_path):
    """Return a list detected subtitles for the given video file"""
    video = subliminal.videos.Video.from_path(video_path)
    subtitles = video.scan()
    languages = set()
    for subtitle in subtitles:
        if subtitle.language:
            languages.add(subtitle.language.alpha2)
        else:
            languages.add(SINGLE)

    return list(languages)


# Return a list with languages that have alpha2 code
def subtitle_language_filter():

    return [language for language in subliminal.language.LANGUAGES if '' != language[2]]


class SubtitlesFinder(Job):
    """
    The SubtitlesFinder will be executed every hour but will not necessarly search
    and download subtitles. Only if the defined rule is true
    """

    def __init__(self):
        super(SubtitlesFinder, self).__init__(self.main_task, kwargs={}, thread_lock=True)

    def main_task(self):
        if 1 > len(sickbeard.subtitles.get_enabled_service_list()):
            logger.log(u'Not enough services selected. At least 1 service is required to search subtitles in the background', logger.ERROR)
            return

        logger.log(u'Checking for subtitles', logger.MESSAGE)

        # get episodes on which we want subtitles
        # criteria is:
        #  - show subtitles = 1
        #  - episode subtitles != config wanted languages or SINGLE (depends on config multi)
        #  - search count < 2 and diff(airdate, now) > 1 week : now -> 1d
        #  - search count < 7 and diff(airdate, now) <= 1 week : now -> 4h -> 8h -> 16h -> 1d -> 1d -> 1d

        today = datetime.date.today().toordinal()

        # you have 5 minutes to understand that one. Good luck
        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT s.show_name, e.showid, e.season, e.episode, e.status, e.subtitles, e.subtitles_searchcount AS searchcount, e.subtitles_lastsearch AS lastsearch, e.location, (? - e.airdate) AS airdate_daydiff FROM tv_episodes AS e INNER JOIN tv_shows AS s ON (e.showid = s.indexer_id) WHERE s.subtitles = 1 AND e.subtitles NOT LIKE (?) AND ((e.subtitles_searchcount <= 2 AND (? - e.airdate) > 7) OR (e.subtitles_searchcount <= 7 AND (? - e.airdate) <= 7)) AND (e.status IN ('+','.join([str(x) for x in Quality.DOWNLOADED])+') OR (e.status IN ('+','.join([str(x) for x in Quality.SNATCHED + Quality.SNATCHED_PROPER])+') AND e.location != ""))', [today, wanted_languages(True), today, today])
        if 0 == len(sql_results):
            logger.log('No subtitles to download', logger.MESSAGE)
            return

        rules = self._get_rules()
        now = datetime.datetime.now()
        for epToSub in sql_results:

            if not ek.ek(os.path.isfile, epToSub['location']):
                logger.log('Episode file does not exist, cannot download subtitles for episode %dx%d of show %s' % (epToSub['season'], epToSub['episode'], epToSub['show_name']), logger.DEBUG)
                continue

            # Old shows rule
            void = datetime.datetime.strptime('20110101', '%Y%m%d')
            if ((epToSub['airdate_daydiff'] > 7 and epToSub['searchcount'] < 2 and now - datetime.datetime.strptime(epToSub['lastsearch'], '%Y-%m-%d %H:%M:%S') > datetime.timedelta(hours=rules['old'][epToSub['searchcount']])) or
                    # Recent shows rule
                    (epToSub['airdate_daydiff'] <= 7 and epToSub['searchcount'] < 7 and now - datetime.datetime.strptime(epToSub['lastsearch'], '%Y-%m-%d %H:%M:%S') > datetime.timedelta(hours=rules['new'][epToSub['searchcount']]))):
                logger.log('Downloading subtitles for episode %dx%d of show %s' % (epToSub['season'], epToSub['episode'], epToSub['show_name']), logger.DEBUG)

                show_obj = helpers.findCertainShow(sickbeard.showList, int(epToSub['showid']))
                if not show_obj:
                    logger.log(u'Show not found', logger.DEBUG)
                    return

                ep_obj = show_obj.getEpisode(int(epToSub["season"]), int(epToSub["episode"]))
                if isinstance(ep_obj, str):
                    logger.log(u'Episode not found', logger.DEBUG)
                    return

                try:
                    ep_obj.downloadSubtitles()
                except:
                    logger.log(u'Unable to find subtitles', logger.DEBUG)
                    return

    @staticmethod
    def _get_rules():
        """
        Define the hours to wait between 2 subtitles search depending on:
        - the episode: new or old
        - the number of searches done so far (searchcount), represented by the index of the list
        """
        return {'old': [0, 24], 'new': [0, 4, 8, 4, 16, 24, 24]}

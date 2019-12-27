#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty    of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from collections import OrderedDict
from time import sleep
import datetime
import os
import re
import traceback

# noinspection PyPep8Naming
import encodingKludge as ek
import sickbeard
from . import db, logger
from .helpers import get_url, try_int
from .indexers.indexer_config import TVINFO_TVDB, TVINFO_IMDB, TVINFO_TVMAZE, TVINFO_TVRAGE, TVINFO_TMDB, TVINFO_TRAKT

import requests
# noinspection PyPep8Naming
from lib import tmdbsimple as TMDB
from lib.dateutil.parser import parse
from lib.imdbpie import Imdb
from libtrakt import TraktAPI
from libtrakt.exceptions import TraktAuthException, TraktException

from _23 import unidecode, urlencode
from six import iteritems, iterkeys, string_types, PY2

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import AnyStr, Dict, List, Optional

tv_maze_retry_wait = 10
defunct_indexer = []
indexer_list = []
tmdb_ids = {TVINFO_TVDB: 'tvdb_id', TVINFO_IMDB: 'imdb_id', TVINFO_TVRAGE: 'tvrage_id'}


class NewIdDict(dict):
    def __init__(self, *args, **kwargs):
        super(NewIdDict, self).__init__(*args, **kwargs)

    @staticmethod
    def set_value(value, old_value=None):
        if old_value is MapStatus.MISMATCH or (0 < value and old_value not in [None, value] and 0 < old_value):
            return MapStatus.MISMATCH
        return value

    @staticmethod
    def get_value(value):
        if value in [None, 0]:
            return MapStatus.NOT_FOUND
        return value

    def __getitem__(self, key):
        return self.get_value(super(NewIdDict, self).get(key))

    def get(self, key, default=None):
        return self.get_value(super(NewIdDict, self).get(key, default))

    def __setitem__(self, key, value):
        super(NewIdDict, self).__setitem__(key, self.set_value(value, self.get(key)))

    def update(self, other=None, **kwargs):
        if isinstance(other, dict):
            other = {o: self.set_value(v, self.get(o)) for o, v in iteritems(other)}
        super(NewIdDict, self).update(other, **kwargs)


class TvmazeDict(OrderedDict):
    tvmaze_ids = {TVINFO_TVDB: 'thetvdb', TVINFO_IMDB: 'imdb', TVINFO_TVRAGE: 'tvrage'}

    def __init__(self, *args, **kwds):
        super(TvmazeDict, self).__init__(*args, **kwds)

    def get_url(self, key):
        if TVINFO_TVMAZE == key:
            return '%sshows/%s' % (sickbeard.TVInfoAPI(TVINFO_TVMAZE).config['base_url'], self.tvmaze_ids[key])
        return '%slookup/shows?%s=%s%s' % (sickbeard.TVInfoAPI(TVINFO_TVMAZE).config['base_url'],
                                           self.tvmaze_ids[key], ('', 'tt')[key == TVINFO_IMDB],
                                           (self[key], '%07d' % self[key])[key == TVINFO_IMDB])


class TraktDict(OrderedDict):
    trakt_ids = {TVINFO_TVDB: 'tvdb', TVINFO_IMDB: 'imdb', TVINFO_TVRAGE: 'tvrage'}

    def __init__(self, *args, **kwds):
        super(TraktDict, self).__init__(*args, **kwds)

    def get_url(self, key):
        return 'search/%s/%s%s?type=show' % (self.trakt_ids[key], ('', 'tt')[key == TVINFO_IMDB],
                                             (self[key], '%07d' % self[key])[key == TVINFO_IMDB])


# noinspection PyUnusedLocal
def tvmaze_record_hook(r, *args, **kwargs):
    r.hook_called = True
    if 301 == r.status_code and isinstance(r.headers.get('Location'), string_types) \
            and r.headers.get('Location').startswith('http://api.tvmaze'):
        r.headers['Location'] = r.headers['Location'].replace('http://', 'https://')
    return r


def get_tvmaze_data(count=0, *args, **kwargs):
    res = None
    count += 1
    kwargs['hooks'] = {'response': tvmaze_record_hook}
    if 3 >= count:
        try:
            res = get_url(*args, **kwargs)
        except requests.HTTPError as e:
            # rate limit
            if 429 == e.response.status_code:
                sleep(tv_maze_retry_wait)
                return get_tvmaze_data(*args, count=count, **kwargs)
        except (BaseException, Exception):
            pass
    return res


def get_tvmaze_ids(url_tvmaze):
    """

    :param url_tvmaze: tvmaze url
    :type url_tvmaze: TvmazeDict
    :return:
    :rtype: Dict
    """
    ids = {}
    for url_key in iterkeys(url_tvmaze):
        try:
            res = get_tvmaze_data(url=url_tvmaze.get_url(url_key), parse_json=True, raise_status_code=True, timeout=120)
            if res and 'externals' in res:
                ids[TVINFO_TVRAGE] = res['externals'].get('tvrage', 0)
                ids[TVINFO_TVDB] = res['externals'].get('thetvdb', 0)
                ids[TVINFO_IMDB] = try_int(str(res['externals'].get('imdb')).replace('tt', ''))
                ids[TVINFO_TVMAZE] = res.get('id', 0)
                break
        except (BaseException, Exception):
            pass
    return {k: v for k, v in iteritems(ids) if v not in (None, '', 0)}


def get_premieredate(show_obj):
    """

    :param show_obj: show object
    :type show_obj: sickbeard.tv.TVShow
    :return:
    :rtype: datetime.date or None
    """
    try:
        ep_obj = show_obj.get_episode(season=1, episode=1)
        if ep_obj and ep_obj.airdate:
            return ep_obj.airdate
    except (BaseException, Exception):
        pass
    return None


def clean_show_name(showname):
    """

    :param showname: show name
    :type showname: AnyStr
    :return:
    :rtype: AnyStr
    """
    if not PY2:
        return re.sub(r'[(\s]*(?:19|20)\d\d[)\s]*$', '', showname)
    return re.sub(r'[(\s]*(?:19|20)\d\d[)\s]*$', '', unidecode(showname))


def get_tvmaze_by_name(showname, premiere_date):
    """

    :param showname: show name
    :type showname: AnyStr
    :param premiere_date: premiere date
    :type premiere_date: datetime.date
    :return:
    :rtype: Dict
    """
    ids = {}
    try:
        url = '%ssearch/shows?%s' % (sickbeard.TVInfoAPI(TVINFO_TVMAZE).config['base_url'],
                                     urlencode({'q': clean_show_name(showname)}))
        res = get_tvmaze_data(url=url, parse_json=True, raise_status_code=True, timeout=120)
        if res:
            for r in res:
                if 'show' in r and 'premiered' in r['show'] and 'externals' in r['show']:
                    premiered = parse(r['show']['premiered'], fuzzy=True)
                    if abs(premiere_date - premiered.date()) < datetime.timedelta(days=2):
                        ids[TVINFO_TVRAGE] = r['show']['externals'].get('tvrage', 0)
                        ids[TVINFO_TVDB] = r['show']['externals'].get('thetvdb', 0)
                        ids[TVINFO_IMDB] = try_int(str(r['show']['externals'].get('imdb')).replace('tt', ''))
                        ids[TVINFO_TVMAZE] = r['show'].get('id', 0)
                        break
    except (BaseException, Exception):
        pass
    return {k: v for k, v in iteritems(ids) if v not in (None, '', 0)}


def get_trakt_ids(url_trakt):
    """

    :param url_trakt: trakt url
    :type url_trakt: TraktDict
    :return:
    :rtype: Dict
    """
    ids = {}
    for url_key in iterkeys(url_trakt):
        try:
            res = TraktAPI().trakt_request(url_trakt.get_url(url_key))
            if res:
                found = False
                for r in res:
                    if 'show' == r.get('type', '') and 'show' in r and 'ids' in r['show']:
                        ids[TVINFO_TVDB] = try_int(r['show']['ids'].get('tvdb', 0))
                        ids[TVINFO_TVRAGE] = try_int(r['show']['ids'].get('tvrage', 0))
                        ids[TVINFO_IMDB] = try_int(str(r['show']['ids'].get('imdb')).replace('tt', ''))
                        ids[TVINFO_TRAKT] = try_int(r['show']['ids'].get('trakt', 0))
                        ids[TVINFO_TMDB] = try_int(r['show']['ids'].get('tmdb', 0))
                        found = True
                        break
                if found:
                    break
        except (TraktAuthException, TraktException, IndexError, KeyError):
            pass
    return {k: v for k, v in iteritems(ids) if v not in (None, '', 0)}


def get_imdbid_by_name(name, startyear):
    """

    :param name: name
    :type name: AnyStr
    :param startyear: start year
    :type startyear: int or AnyStr
    :return:
    :rtype: Dict
    """
    ids = {}
    try:
        res = Imdb(exclude_episodes=True,
                   cachedir=ek.ek(os.path.join, sickbeard.CACHE_DIR, 'imdb-pie')).search_for_title(title=name)
        for r in res:
            if isinstance(r.get('type'), string_types) and 'tv series' == r.get('type').lower() \
                    and str(startyear) == str(r.get('year')):
                ids[TVINFO_IMDB] = try_int(re.sub(r'[^0-9]*', '', r.get('imdb_id')))
                break
    except (BaseException, Exception):
        pass
    return {k: v for k, v in iteritems(ids) if v not in (None, '', 0)}


def check_missing_trakt_id(n_ids, show_obj, url_trakt):
    """

    :param n_ids:
    :type n_ids: NewIdDict
    :param show_obj: show objects
    :type show_obj: sickbeard.tv.TVShow
    :param url_trakt: trakt url
    :type url_trakt: TraktDict
    :return:
    :rtype: NewIdDict
    """
    if TVINFO_TRAKT not in n_ids:
        new_url_trakt = TraktDict()
        for k, v in iteritems(n_ids):
            if k != show_obj.tvid and k in [TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_IMDB] and 0 < v \
                    and k not in url_trakt:
                new_url_trakt[k] = v

        if 0 < len(new_url_trakt):
            n_ids.update(get_trakt_ids(new_url_trakt))

    return n_ids


def map_indexers_to_show(show_obj, update=False, force=False, recheck=False):
    """

    :param show_obj: TVShow Object
    :type show_obj: sickbeard.tv.TVShow
    :param update: add missing + previously not found ids
    :type update: bool
    :param force: search for and replace all mapped/missing ids (excluding NO_AUTOMATIC_CHANGE flagged)
    :type force: bool
    :param recheck: load all ids, don't remove existing
    :type recheck: bool
    :return: mapped ids
    :rtype: Dict
    """
    mapped = {}

    # init mapped tvids object
    for tvid in indexer_list:
        mapped[tvid] = {'id': (0, show_obj.prodid)[int(tvid) == int(show_obj.tvid)],
                        'status': (MapStatus.NONE, MapStatus.SOURCE)[int(tvid) == int(show_obj.tvid)],
                        'date': datetime.date.fromordinal(1)}

    my_db = db.DBConnection()
    sql_result = my_db.select('SELECT *'
                              ' FROM indexer_mapping'
                              ' WHERE indexer = ? AND indexer_id = ?',
                              [show_obj.tvid, show_obj.prodid])

    # for each mapped entry
    for cur_result in sql_result:
        date = try_int(cur_result['date'])
        mapped[int(cur_result['mindexer'])] = {'status': int(cur_result['status']),
                                               'id': int(cur_result['mindexer_id']),
                                               'date': datetime.date.fromordinal(date if 0 < date else 1)}

    # get list of needed ids
    mis_map = [k for k, v in iteritems(mapped) if (v['status'] not in [
        MapStatus.NO_AUTOMATIC_CHANGE, MapStatus.SOURCE])
               and ((0 == v['id'] and MapStatus.NONE == v['status'])
                    or force or recheck or (update and 0 == v['id'] and k not in defunct_indexer))]
    if mis_map:
        url_tvmaze = TvmazeDict()
        url_trakt = TraktDict()
        if show_obj.tvid in (TVINFO_TVDB, TVINFO_TVRAGE):
            url_tvmaze[show_obj.tvid] = show_obj.prodid
            url_trakt[show_obj.tvid] = show_obj.prodid
        elif show_obj.tvid == TVINFO_TVMAZE:
            url_tvmaze[TVINFO_TVMAZE] = show_obj.tvid
        if show_obj.imdbid and re.search(r'\d+$', show_obj.imdbid):
            url_tvmaze[TVINFO_IMDB] = try_int(re.search(r'(?:tt)?(\d+)', show_obj.imdbid).group(1))
            url_trakt[TVINFO_IMDB] = try_int(re.search(r'(?:tt)?(\d+)', show_obj.imdbid).group(1))
        for m, v in iteritems(mapped):
            if m != show_obj.tvid and m in [TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_TVRAGE, TVINFO_IMDB] and \
                            0 < v.get('id', 0):
                url_tvmaze[m] = v['id']

        new_ids = NewIdDict()

        if isinstance(show_obj.imdbid, string_types) and re.search(r'\d+$', show_obj.imdbid):
            try:
                new_ids[TVINFO_IMDB] = try_int(re.search(r'(?:tt)?(\d+)', show_obj.imdbid).group(1))
            except (BaseException, Exception):
                pass

        if 0 < len(url_tvmaze):
            new_ids.update(get_tvmaze_ids(url_tvmaze))

        for m, v in iteritems(new_ids):
            if m != show_obj.tvid and m in [TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_TVRAGE, TVINFO_IMDB] and 0 < v:
                url_trakt[m] = v

        if url_trakt:
            new_ids.update(get_trakt_ids(url_trakt))

        if TVINFO_TVMAZE not in new_ids:
            new_url_tvmaze = TvmazeDict()
            for k, v in iteritems(new_ids):
                if k != show_obj.tvid and k in [TVINFO_TVDB, TVINFO_TVRAGE, TVINFO_TVRAGE, TVINFO_IMDB] \
                        and 0 < v and k not in url_tvmaze:
                    new_url_tvmaze[k] = v

            if 0 < len(new_url_tvmaze):
                new_ids.update(get_tvmaze_ids(new_url_tvmaze))

        if TVINFO_TVMAZE not in new_ids:
            f_date = get_premieredate(show_obj)
            if f_date and f_date != datetime.date.fromordinal(1):
                tvids = {k: v for k, v in iteritems(get_tvmaze_by_name(show_obj.name, f_date)) if k == TVINFO_TVMAZE
                         or k not in new_ids or new_ids.get(k) in (None, 0, '', MapStatus.NOT_FOUND)}
                new_ids.update(tvids)

        new_ids = check_missing_trakt_id(new_ids, show_obj, url_trakt)

        if TVINFO_IMDB not in new_ids:
            new_ids.update(get_imdbid_by_name(show_obj.name, show_obj.startyear))
            new_ids = check_missing_trakt_id(new_ids, show_obj, url_trakt)

        if TVINFO_TMDB in mis_map \
                and (None is new_ids.get(TVINFO_TMDB) or MapStatus.NOT_FOUND == new_ids.get(TVINFO_TMDB)) \
                and (0 < mapped.get(TVINFO_TVDB, {'id': 0}).get('id', 0) or 0 < new_ids.get(TVINFO_TVDB, 0)
                     or 0 < mapped.get(TVINFO_IMDB, {'id': 0}).get('id', 0) or 0 < new_ids.get(TVINFO_TMDB, 0)
                     or 0 < mapped.get(TVINFO_TVRAGE, {'id': 0}).get('id', 0) or 0 < new_ids.get(TVINFO_TVRAGE, 0)):
            try:
                TMDB.API_KEY = sickbeard.TMDB_API_KEY
                for d in [TVINFO_TVDB, TVINFO_IMDB, TVINFO_TVRAGE]:
                    c = (new_ids.get(d), mapped.get(d, {'id': 0}).get('id'))[0 < mapped.get(d, {'id': 0}).get('id', 0)]
                    if 0 >= c:
                        continue
                    if None is not c and 0 < c:
                        if TVINFO_IMDB == d:
                            c = 'tt%07d' % c
                        tmdb_data = TMDB.Find(c).info(**{'external_source': tmdb_ids[d]})
                        if isinstance(tmdb_data, dict) \
                                and 'tv_results' in tmdb_data and 0 < len(tmdb_data['tv_results']) \
                                and 'id' in tmdb_data['tv_results'][0] \
                                and 0 < try_int(tmdb_data['tv_results'][0]['id']):
                            new_ids[TVINFO_TMDB] = try_int(tmdb_data['tv_results'][0]['id'])
                            break
            except (BaseException, Exception):
                pass

            if TVINFO_TMDB not in new_ids:
                try:
                    TMDB.API_KEY = sickbeard.TMDB_API_KEY
                    tmdb_data = TMDB.Search().tv(**{'query': clean_show_name(show_obj.name),
                                                    'first_air_date_year': show_obj.startyear})
                    for s in tmdb_data.get('results'):
                        if clean_show_name(s['name']) == clean_show_name(show_obj.name):
                            new_ids[TVINFO_TMDB] = try_int(s['id'])
                            break
                except (BaseException, Exception):
                    pass

        for i in indexer_list:
            if i != show_obj.tvid and i in mis_map and 0 != new_ids.get(i, 0):
                if 0 > new_ids[i]:
                    mapped[i] = {'status': new_ids[i], 'id': 0}
                elif force or not recheck or 0 >= mapped.get(i, {'id': 0}).get('id', 0):
                    mapped[i] = {'status': MapStatus.NONE, 'id': new_ids[i]}

        if [k for k in mis_map if 0 != mapped.get(k, {'id': 0, 'status': 0})['id'] or
                mapped.get(k, {'id': 0, 'status': 0})['status'] not in [MapStatus.NONE, MapStatus.SOURCE]]:
            sql_l = []
            today = datetime.date.today()
            date = today.toordinal()
            for tvid in indexer_list:

                if show_obj.tvid == tvid or tvid not in mis_map:
                    continue

                if 0 != mapped[tvid]['id'] or MapStatus.NONE != mapped[tvid]['status']:
                    mapped[tvid]['date'] = today
                    sql_l.append([
                        'INSERT OR REPLACE INTO indexer_mapping (' +
                        'indexer_id, indexer, mindexer_id, mindexer, date, status) VALUES (?,?,?,?,?,?)',
                        [show_obj.prodid, show_obj.tvid, mapped[tvid]['id'],
                         tvid, date, mapped[tvid]['status']]])
                else:
                    sql_l.append([
                        'DELETE FROM indexer_mapping'
                        ' WHERE indexer = ? AND indexer_id = ?'
                        ' AND mindexer = ?',
                        [show_obj.tvid, show_obj.prodid, tvid]])

            if 0 < len(sql_l):
                logger.log('Adding TV info mapping to DB for show: %s' % show_obj.name, logger.DEBUG)
                my_db = db.DBConnection()
                my_db.mass_action(sql_l)

    show_obj.ids = mapped
    return mapped


def save_mapping(show_obj, save_map=None):
    # type: (sickbeard.tv.TVShow, Optional[List[int]]) -> None
    """

    :param show_obj: show object
    :param save_map: list of tvid ints
    """
    sql_l = []
    today = datetime.date.today()
    date = today.toordinal()
    for tvid in indexer_list:

        if show_obj.tvid == tvid or (isinstance(save_map, list) and tvid not in save_map):
            continue

        if 0 != show_obj.ids[tvid]['id'] or MapStatus.NONE != show_obj.ids[tvid]['status']:
            show_obj.ids[tvid]['date'] = today
            sql_l.append([
                'INSERT OR REPLACE INTO indexer_mapping'
                ' (indexer_id, indexer, mindexer_id, mindexer, date, status) VALUES (?,?,?,?,?,?)',
                [show_obj.prodid, show_obj.tvid, show_obj.ids[tvid]['id'],
                 tvid, date, show_obj.ids[tvid]['status']]])
        else:
            sql_l.append([
                'DELETE FROM indexer_mapping'
                ' WHERE indexer = ? AND indexer_id = ?'
                ' AND mindexer = ?',
                [show_obj.tvid, show_obj.prodid, tvid]])

    if 0 < len(sql_l):
        logger.log('Saving TV info mapping to DB for show: %s' % show_obj.name, logger.DEBUG)
        my_db = db.DBConnection()
        my_db.mass_action(sql_l)


def del_mapping(tvid, prodid):
    """

    :param tvid: tvid
    :type tvid: int
    :param prodid: prodid
    :type prodid: int or long
    """
    my_db = db.DBConnection()
    my_db.action('DELETE FROM indexer_mapping'
                 ' WHERE indexer = ? AND indexer_id = ?',
                 [tvid, prodid])


def should_recheck_update_ids(show_obj):
    """

    :param show_obj: show object
    :type show_obj: sickbeard.tv.TVShow
    :return:
    :rtype: bool
    """
    try:
        today = datetime.date.today()
        ids_updated = min([v.get('date') for k, v in iteritems(show_obj.ids) if k != show_obj.tvid and
                           k not in defunct_indexer] or [datetime.date.fromtimestamp(1)])
        if today - ids_updated >= datetime.timedelta(days=365):
            return True
        ep_obj = show_obj.get_episode(season=1, episode=1)
        if ep_obj and ep_obj.airdate and ep_obj.airdate > datetime.date.fromtimestamp(1):
            show_age = (today - ep_obj.airdate).days
            # noinspection PyTypeChecker
            for d in [365, 270, 180, 135, 90, 60, 30, 16, 9] + range(4, -4, -1):
                if d <= show_age:
                    return ids_updated < (ep_obj.airdate + datetime.timedelta(days=d))
    except (BaseException, Exception):
        pass
    return False


def load_mapped_ids(**kwargs):
    logger.log('Start loading TV info mappings...')
    for cur_show_obj in sickbeard.showList:
        with cur_show_obj.lock:
            n_kargs = kwargs.copy()
            if 'update' in kwargs and should_recheck_update_ids(cur_show_obj):
                n_kargs['recheck'] = True
            try:
                cur_show_obj.ids = sickbeard.indexermapper.map_indexers_to_show(cur_show_obj, **n_kargs)
            except (BaseException, Exception):
                logger.log('Error loading mapped id\'s for show: %s' % cur_show_obj.name, logger.ERROR)
                logger.log('Traceback: %s' % traceback.format_exc(), logger.ERROR)
    logger.log('TV info mappings loaded')


class MapStatus(object):
    def __init__(self):
        pass

    SOURCE = 1
    NONE = 0
    NOT_FOUND = -1
    MISMATCH = -2
    NO_AUTOMATIC_CHANGE = -100

    allstatus = [SOURCE, NONE, NOT_FOUND, MISMATCH, NO_AUTOMATIC_CHANGE]

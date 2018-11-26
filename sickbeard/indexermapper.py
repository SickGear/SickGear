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

import datetime
import re
import traceback

import requests
import sickbeard
from collections import OrderedDict
from urllib import urlencode
from lib.dateutil.parser import parse
from lib.unidecode import unidecode
from libtrakt import TraktAPI
from libtrakt.exceptions import TraktAuthException, TraktException
from sickbeard import db, logger
from sickbeard.helpers import tryInt, getURL
from sickbeard.indexers.indexer_config import (INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_TVMAZE,
                                               INDEXER_IMDB, INDEXER_TRAKT, INDEXER_TMDB)
from lib.tmdb_api import TMDB
from lib.imdbpie import Imdb
from time import sleep

tv_maze_retry_wait = 10
defunct_indexer = []
indexer_list = []
tmdb_ids = {INDEXER_TVDB: 'tvdb_id', INDEXER_IMDB: 'imdb_id', INDEXER_TVRAGE: 'tvrage_id'}


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
            other = {o: self.set_value(v, self.get(o)) for o, v in other.iteritems()}
        super(NewIdDict, self).update(other, **kwargs)


class TvmazeDict(OrderedDict):
    tvmaze_ids = {INDEXER_TVDB: 'thetvdb', INDEXER_IMDB: 'imdb', INDEXER_TVRAGE: 'tvrage'}

    def __init__(self, *args, **kwds):
        super(TvmazeDict, self).__init__(*args, **kwds)

    def get_url(self, key):
        if INDEXER_TVMAZE == key:
            return '%sshows/%s' % (sickbeard.indexerApi(INDEXER_TVMAZE).config['base_url'], self.tvmaze_ids[key])
        return '%slookup/shows?%s=%s%s' % (sickbeard.indexerApi(INDEXER_TVMAZE).config['base_url'],
                                           self.tvmaze_ids[key], ('', 'tt')[key == INDEXER_IMDB],
                                           (self[key], '%07d' % self[key])[key == INDEXER_IMDB])


class TraktDict(OrderedDict):
    trakt_ids = {INDEXER_TVDB: 'tvdb', INDEXER_IMDB: 'imdb', INDEXER_TVRAGE: 'tvrage'}

    def __init__(self, *args, **kwds):
        super(TraktDict, self).__init__(*args, **kwds)

    def get_url(self, key):
        return 'search/%s/%s%s?type=show' % (self.trakt_ids[key], ('', 'tt')[key == INDEXER_IMDB],
                                             (self[key], '%07d' % self[key])[key == INDEXER_IMDB])


def tvmaze_record_hook(r, *args, **kwargs):
    r.hook_called = True
    if 301 == r.status_code and isinstance(r.headers.get('Location'), basestring) \
            and r.headers.get('Location').startswith('http://api.tvmaze'):
        r.headers['Location'] = r.headers['Location'].replace('http://', 'https://')
    return r


def get_tvmaze_data(count=0, *args, **kwargs):
    res = None
    count += 1
    kwargs['hooks'] = {'response': tvmaze_record_hook}
    if 3 >= count:
        try:
            res = getURL(*args, **kwargs)
        except requests.HTTPError as e:
            # rate limit
            if 429 == e.response.status_code:
                sleep(tv_maze_retry_wait)
                return get_tvmaze_data(*args, count=count, **kwargs)
        except (StandardError, Exception):
            pass
    return res


def get_tvmaze_ids(url_tvmaze):
    ids = {}
    for url_key in url_tvmaze.iterkeys():
        try:
            res = get_tvmaze_data(url=url_tvmaze.get_url(url_key), json=True, raise_status_code=True, timeout=120)
            if res and 'externals' in res:
                ids[INDEXER_TVRAGE] = res['externals'].get('tvrage', 0)
                ids[INDEXER_TVDB] = res['externals'].get('thetvdb', 0)
                ids[INDEXER_IMDB] = tryInt(str(res['externals'].get('imdb')).replace('tt', ''))
                ids[INDEXER_TVMAZE] = res.get('id', 0)
                break
        except (StandardError, Exception):
            pass
    return {k: v for k, v in ids.iteritems() if v not in (None, '', 0)}


def get_premieredate(show):
    try:
        first_ep = show.getEpisode(season=1, episode=1)
        if first_ep and first_ep.airdate:
            return first_ep.airdate
    except (StandardError, Exception):
        pass
    return None


def clean_show_name(showname):
    return re.sub(r'[(\s]*(?:19|20)\d\d[)\s]*$', '', isinstance(showname, unicode) and unidecode(showname) or showname)


def get_tvmaze_by_name(showname, premiere_date):
    ids = {}
    try:
        url = '%ssearch/shows?%s' % (sickbeard.indexerApi(INDEXER_TVMAZE).config['base_url'],
                                     urlencode({'q': clean_show_name(showname)}))
        res = get_tvmaze_data(url=url, json=True, raise_status_code=True, timeout=120)
        if res:
            for r in res:
                if 'show' in r and 'premiered' in r['show'] and 'externals' in r['show']:
                    premiered = parse(r['show']['premiered'], fuzzy=True)
                    if abs(premiere_date - premiered.date()) < datetime.timedelta(days=2):
                        ids[INDEXER_TVRAGE] = r['show']['externals'].get('tvrage', 0)
                        ids[INDEXER_TVDB] = r['show']['externals'].get('thetvdb', 0)
                        ids[INDEXER_IMDB] = tryInt(str(r['show']['externals'].get('imdb')).replace('tt', ''))
                        ids[INDEXER_TVMAZE] = r['show'].get('id', 0)
                        break
    except (StandardError, Exception):
        pass
    return {k: v for k, v in ids.iteritems() if v not in (None, '', 0)}


def get_trakt_ids(url_trakt):
    ids = {}
    for url_key in url_trakt.iterkeys():
        try:
            res = TraktAPI().trakt_request(url_trakt.get_url(url_key))
            if res:
                found = False
                for r in res:
                    if r.get('type', '') == 'show' and 'show' in r and 'ids' in r['show']:
                        ids[INDEXER_TVDB] = tryInt(r['show']['ids'].get('tvdb', 0))
                        ids[INDEXER_TVRAGE] = tryInt(r['show']['ids'].get('tvrage', 0))
                        ids[INDEXER_IMDB] = tryInt(str(r['show']['ids'].get('imdb')).replace('tt', ''))
                        ids[INDEXER_TRAKT] = tryInt(r['show']['ids'].get('trakt', 0))
                        ids[INDEXER_TMDB] = tryInt(r['show']['ids'].get('tmdb', 0))
                        found = True
                        break
                if found:
                    break
        except (TraktAuthException, TraktException, IndexError, KeyError):
            pass
    return {k: v for k, v in ids.iteritems() if v not in (None, '', 0)}


def get_imdbid_by_name(name, startyear):
    ids = {}
    try:
        res = Imdb(exclude_episodes=True).search_for_title(title=name)
        for r in res:
            if isinstance(r.get('type'), basestring) and 'tv series' == r.get('type').lower() \
                    and str(startyear) == str(r.get('year')):
                ids[INDEXER_IMDB] = tryInt(re.sub(r'[^0-9]*', '', r.get('imdb_id')))
                break
    except (StandardError, Exception):
        pass
    return {k: v for k, v in ids.iteritems() if v not in (None, '', 0)}


def check_missing_trakt_id(n_ids, show_obj, url_trakt):
    if INDEXER_TRAKT not in n_ids:
        new_url_trakt = TraktDict()
        for k, v in n_ids.iteritems():
            if k != show_obj.indexer and k in [INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_IMDB] and 0 < v \
                    and k not in url_trakt:
                new_url_trakt[k] = v

        if 0 < len(new_url_trakt):
            n_ids.update(get_trakt_ids(new_url_trakt))

    return n_ids


def map_indexers_to_show(show_obj, update=False, force=False, recheck=False):
    """

    :return: mapped ids
    :rtype: dict
    :param show_obj: TVShow Object
    :param update: add missing + previously not found ids
    :param force: search for and replace all mapped/missing ids (excluding NO_AUTOMATIC_CHANGE flagged)
    :param recheck: load all ids, don't remove existing
    """
    mapped = {}

    # init mapped indexers object
    for indexer in indexer_list:
        mapped[indexer] = {'id': (0, show_obj.indexerid)[int(indexer) == int(show_obj.indexer)],
                           'status': (MapStatus.NONE, MapStatus.SOURCE)[int(indexer) == int(show_obj.indexer)],
                           'date': datetime.date.fromordinal(1)}

    my_db = db.DBConnection()
    sql_results = my_db.select('SELECT' + ' * FROM indexer_mapping WHERE indexer_id = ? AND indexer = ?',
                               [show_obj.indexerid, show_obj.indexer])

    # for each mapped entry
    for curResult in sql_results:
        date = tryInt(curResult['date'])
        mapped[int(curResult['mindexer'])] = {'status': int(curResult['status']),
                                              'id': int(curResult['mindexer_id']),
                                              'date': datetime.date.fromordinal(date if 0 < date else 1)}

    # get list of needed ids
    mis_map = [k for k, v in mapped.iteritems() if (v['status'] not in [
        MapStatus.NO_AUTOMATIC_CHANGE, MapStatus.SOURCE])
               and ((0 == v['id'] and MapStatus.NONE == v['status'])
                    or force or recheck or (update and 0 == v['id'] and k not in defunct_indexer))]
    if mis_map:
        url_tvmaze = TvmazeDict()
        url_trakt = TraktDict()
        if show_obj.indexer == INDEXER_TVDB or show_obj.indexer == INDEXER_TVRAGE:
            url_tvmaze[show_obj.indexer] = show_obj.indexerid
            url_trakt[show_obj.indexer] = show_obj.indexerid
        elif show_obj.indexer == INDEXER_TVMAZE:
            url_tvmaze[INDEXER_TVMAZE] = show_obj.indexer
        if show_obj.imdbid and re.search(r'\d+$', show_obj.imdbid):
            url_tvmaze[INDEXER_IMDB] = tryInt(re.search(r'(?:tt)?(\d+)', show_obj.imdbid).group(1))
            url_trakt[INDEXER_IMDB] = tryInt(re.search(r'(?:tt)?(\d+)', show_obj.imdbid).group(1))
        for m, v in mapped.iteritems():
            if m != show_obj.indexer and m in [INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_TVRAGE, INDEXER_IMDB] and \
                            0 < v.get('id', 0):
                url_tvmaze[m] = v['id']

        new_ids = NewIdDict()

        if isinstance(show_obj.imdbid, basestring) and re.search(r'\d+$', show_obj.imdbid):
            new_ids[INDEXER_IMDB] = tryInt(re.search(r'(?:tt)?(\d+)', show_obj.imdbid))

        if 0 < len(url_tvmaze):
            new_ids.update(get_tvmaze_ids(url_tvmaze))

        for m, v in new_ids.iteritems():
            if m != show_obj.indexer and m in [INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_TVRAGE, INDEXER_IMDB] and 0 < v:
                url_trakt[m] = v

        if url_trakt:
            new_ids.update(get_trakt_ids(url_trakt))

        if INDEXER_TVMAZE not in new_ids:
            new_url_tvmaze = TvmazeDict()
            for k, v in new_ids.iteritems():
                if k != show_obj.indexer and k in [INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_TVRAGE, INDEXER_IMDB] \
                        and 0 < v and k not in url_tvmaze:
                    new_url_tvmaze[k] = v

            if 0 < len(new_url_tvmaze):
                new_ids.update(get_tvmaze_ids(new_url_tvmaze))

        if INDEXER_TVMAZE not in new_ids:
            f_date = get_premieredate(show_obj)
            if f_date and f_date is not datetime.date.fromordinal(1):
                tvids = {k: v for k, v in get_tvmaze_by_name(show_obj.name, f_date).iteritems() if k == INDEXER_TVMAZE
                         or k not in new_ids or new_ids.get(k) in (None, 0, '', MapStatus.NOT_FOUND)}
                new_ids.update(tvids)

        new_ids = check_missing_trakt_id(new_ids, show_obj, url_trakt)

        if INDEXER_IMDB not in new_ids:
            new_ids.update(get_imdbid_by_name(show_obj.name, show_obj.startyear))
            new_ids = check_missing_trakt_id(new_ids, show_obj, url_trakt)

        if INDEXER_TMDB in mis_map \
                and (None is new_ids.get(INDEXER_TMDB) or MapStatus.NOT_FOUND == new_ids.get(INDEXER_TMDB)) \
                and (0 < mapped.get(INDEXER_TVDB, {'id': 0}).get('id', 0) or 0 < new_ids.get(INDEXER_TVDB, 0)
                     or 0 < mapped.get(INDEXER_IMDB, {'id': 0}).get('id', 0) or 0 < new_ids.get(INDEXER_TMDB, 0)
                     or 0 < mapped.get(INDEXER_TVRAGE, {'id': 0}).get('id', 0) or 0 < new_ids.get(INDEXER_TVRAGE, 0)):
            try:
                tmdb = TMDB(sickbeard.TMDB_API_KEY)
                for d in [INDEXER_TVDB, INDEXER_IMDB, INDEXER_TVRAGE]:
                    c = (new_ids.get(d), mapped.get(d, {'id': 0}).get('id'))[0 < mapped.get(d, {'id': 0}).get('id', 0)]
                    if 0 >= c:
                        continue
                    if INDEXER_IMDB == d:
                        c = 'tt%07d' % c
                    if None is not c and 0 < c:
                        tmdb_data = tmdb.Find(c).info({'external_source': tmdb_ids[d]})
                        if isinstance(tmdb_data, dict) \
                                and 'tv_results' in tmdb_data and 0 < len(tmdb_data['tv_results']) \
                                and 'id' in tmdb_data['tv_results'][0] and 0 < tryInt(tmdb_data['tv_results'][0]['id']):
                            new_ids[INDEXER_TMDB] = tryInt(tmdb_data['tv_results'][0]['id'])
                            break
            except (StandardError, Exception):
                pass

            if INDEXER_TMDB not in new_ids:
                try:
                    tmdb = TMDB(sickbeard.TMDB_API_KEY)
                    tmdb_data = tmdb.Search().tv(params={'query': clean_show_name(show_obj.name),
                                                         'first_air_date_year': show_obj.startyear})
                    for s in tmdb_data.get('results'):
                        if clean_show_name(s['name']) == clean_show_name(show_obj.name):
                            new_ids[INDEXER_TMDB] = tryInt(s['id'])
                            break
                except (StandardError, Exception):
                    pass

        for i in indexer_list:
            if i != show_obj.indexer and i in mis_map and 0 != new_ids.get(i, 0):
                if 0 > new_ids[i]:
                    mapped[i] = {'status': new_ids[i], 'id': 0}
                elif force or not recheck or 0 >= mapped.get(i, {'id': 0}).get('id', 0):
                    mapped[i] = {'status': MapStatus.NONE, 'id': new_ids[i]}

        if [k for k in mis_map if 0 != mapped.get(k, {'id': 0, 'status': 0})['id'] or
                mapped.get(k, {'id': 0, 'status': 0})['status'] not in [MapStatus.NONE, MapStatus.SOURCE]]:
            sql_l = []
            today = datetime.date.today()
            date = today.toordinal()
            for indexer in indexer_list:

                if show_obj.indexer == indexer or indexer not in mis_map:
                    continue

                if 0 != mapped[indexer]['id'] or MapStatus.NONE != mapped[indexer]['status']:
                    mapped[indexer]['date'] = today
                    sql_l.append([
                        'INSERT OR REPLACE INTO indexer_mapping (' +
                        'indexer_id, indexer, mindexer_id, mindexer, date, status) VALUES (?,?,?,?,?,?)',
                        [show_obj.indexerid, show_obj.indexer, mapped[indexer]['id'],
                         indexer, date, mapped[indexer]['status']]])
                else:
                    sql_l.append([
                        'DELETE' + ' FROM indexer_mapping WHERE indexer_id = ? AND indexer = ? AND mindexer = ?',
                        [show_obj.indexerid, show_obj.indexer, indexer]])

            if 0 < len(sql_l):
                logger.log('Adding indexer mapping to DB for show: %s' % show_obj.name, logger.DEBUG)
                my_db = db.DBConnection()
                my_db.mass_action(sql_l)

    show_obj.ids = mapped
    return mapped


def save_mapping(show_obj, save_map=None):
    sql_l = []
    today = datetime.date.today()
    date = today.toordinal()
    for indexer in indexer_list:

        if show_obj.indexer == indexer or (isinstance(save_map, list) and indexer not in save_map):
            continue

        if 0 != show_obj.ids[indexer]['id'] or MapStatus.NONE != show_obj.ids[indexer]['status']:
            show_obj.ids[indexer]['date'] = today
            sql_l.append([
                'INSERT OR REPLACE INTO indexer_mapping (' +
                'indexer_id, indexer, mindexer_id, mindexer, date, status) VALUES (?,?,?,?,?,?)',
                [show_obj.indexerid, show_obj.indexer, show_obj.ids[indexer]['id'],
                 indexer, date, show_obj.ids[indexer]['status']]])
        else:
            sql_l.append([
                'DELETE' + ' FROM indexer_mapping WHERE indexer_id = ? AND indexer = ? AND mindexer = ?',
                [show_obj.indexerid, show_obj.indexer, indexer]])

    if 0 < len(sql_l):
        logger.log('Saving indexer mapping to DB for show: %s' % show_obj.name, logger.DEBUG)
        my_db = db.DBConnection()
        my_db.mass_action(sql_l)


def del_mapping(indexer, indexerid):
    my_db = db.DBConnection()
    my_db.action('DELETE' + ' FROM indexer_mapping WHERE indexer_id = ? AND indexer = ?', [indexerid, indexer])


def should_recheck_update_ids(show):
    try:
        today = datetime.date.today()
        ids_updated = min([v.get('date') for k, v in show.ids.iteritems() if k != show.indexer and
                           k not in defunct_indexer] or [datetime.date.fromtimestamp(1)])
        if today - ids_updated >= datetime.timedelta(days=365):
            return True
        first_ep = show.getEpisode(season=1, episode=1)
        if first_ep and first_ep.airdate and first_ep.airdate > datetime.date.fromtimestamp(1):
            show_age = (today - first_ep.airdate).days
            for d in [365, 270, 180, 135, 90, 60, 30, 16, 9] + range(4, -4, -1):
                if d <= show_age:
                    return ids_updated < (first_ep.airdate + datetime.timedelta(days=d))
    except (StandardError, Exception):
        pass
    return False


def load_mapped_ids(**kwargs):
    logger.log('Start loading Indexer mappings...')
    for s in sickbeard.showList:
        with s.lock:
            n_kargs = kwargs.copy()
            if 'update' in kwargs and should_recheck_update_ids(s):
                n_kargs['recheck'] = True
            try:
                s.ids = sickbeard.indexermapper.map_indexers_to_show(s, **n_kargs)
            except (StandardError, Exception):
                logger.log('Error loading mapped id\'s for show: %s' % s.name, logger.ERROR)
                logger.log('Traceback: %s' % traceback.format_exc(), logger.ERROR)
    logger.log('Indexer mappings loaded')


class MapStatus:
    def __init__(self):
        pass

    SOURCE = 1
    NONE = 0
    NOT_FOUND = -1
    MISMATCH = -2
    NO_AUTOMATIC_CHANGE = -100

    allstatus = [SOURCE, NONE, NOT_FOUND, MISMATCH, NO_AUTOMATIC_CHANGE]

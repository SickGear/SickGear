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
import re
import traceback

from . import classes, db, logger
from .helpers import try_int
from .indexers.indexer_config import TVINFO_IMDB, TVINFO_TMDB, TVINFO_TRAKT, TVINFO_TVDB, TVINFO_TVMAZE

import sickgear

from lib.dateutil.parser import parse

from _23 import unidecode
from six import iteritems, moves, string_types, PY2

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, List, Optional, Tuple, Union
    from six import integer_types
    from sickgear.tv import TVShow

tv_maze_retry_wait = 10
defunct_indexer = []
indexer_list = []


class NewIdDict(dict):
    def __init__(self, *args, **kwargs):
        tv_src = kwargs.pop('tv_src')
        super(NewIdDict, self).__init__(*args, **kwargs)
        self.verified = {s: (False, True)[s == tv_src] for s in indexer_list}

    def set_value(self, value, old_value=None, tv_src=None, key=None):
        # type: (Any, Any, int, int) -> Any
        if (None is tv_src or tv_src != key) and old_value is MapStatus.MISMATCH or (
                0 < value and old_value not in [None, value] and 0 < old_value):
            return MapStatus.MISMATCH
        if value and tv_src and tv_src == key:
            self.verified[tv_src] = True
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

    def update(self, other=None, tv_src=None, **kwargs):
        # type: (Dict[int, Any], int, Any) -> None
        """
        updates dict with new ids
        set MapStatus.MISMATCH if values mismatch, except if it's tv_src (this will be treated as verified source id)

        :param other: new data dict
        :param tv_src: verified tv src id
        :param kwargs:
        """
        if isinstance(other, dict):
            other = {o: self.set_value(v, self.get(o), tv_src, o) for o, v in iteritems(other)}
        super(NewIdDict, self).update(other, **kwargs)


def get_missing_ids(show_ids, show_obj, tv_src):
    # type: (Dict[int, integer_types], TVShow, int) -> Dict[int, integer_types]
    """

    :param show_ids:
    :param show_obj:
    :param tv_src:
    :return:
    """
    try:
        tvinfo_config = sickgear.TVInfoAPI(tv_src).api_params.copy()
        tvinfo_config['cache_search'] = True
        tvinfo_config['custom_ui'] = classes.AllShowInfosNoFilterListUI
        t = sickgear.TVInfoAPI(tv_src).setup(**tvinfo_config)
        show_name, f_date = None, None
        if any(1 for k, v in iteritems(show_ids) if v and k in t.supported_id_searches):
            try:
                found_shows = t.search_show(ids=show_ids)
                res_count = len(found_shows or [])
                if 1 < res_count:
                    show_name, f_date = get_show_name_date(show_obj)
                for show in found_shows or []:
                    if 1 == res_count or confirm_show(f_date, show['firstaired'], show_name,
                                                      clean_show_name(show['seriesname'])):
                        return combine_new_ids(show_ids, show['ids'], tv_src)
            except (BaseException, Exception):
                pass
        found_shows = t.search_show(name=clean_show_name(show_obj.name))
        if not show_name:
            show_name, f_date = get_show_name_date(show_obj)
        for show in found_shows or []:
            if confirm_show(f_date, show['firstaired'], show_name, clean_show_name(show['seriesname'])):
                if any(v for k, v in iteritems(show['ids']) if tv_src != k and v):
                    f_show = [show]
                else:
                    f_show = t.search_show(ids={tv_src: show['id']})
                if f_show and 1 == len(f_show):
                    return combine_new_ids(show_ids, f_show[0]['ids'], tv_src)
    except (BaseException, Exception):
        pass
    return {}


def confirm_show(premiere_date, shows_premiere, expected_name, show_name):
    # type: (Optional[datetime.date], Optional[Union[AnyStr, datetime.date]], AnyStr, AnyStr) -> bool
    """
    confirm show possible confirmations:
    1. premiere dates are less then 2 days apart
    2. show name is the same and premiere year is 1 year or less apart

    :param premiere_date: expected show premiere date
    :param shows_premiere: compare date
    :param expected_name:
    :param show_name:
    """
    if any(t is None for t in (premiere_date, shows_premiere)):
        return False
    if isinstance(shows_premiere, string_types):
        try:
            shows_premiere = parse(shows_premiere).date()
        except (BaseException, Exception):
            return False
    start_year = (shows_premiere and shows_premiere.year) or 0
    return abs(premiere_date - shows_premiere) < datetime.timedelta(days=2) or (
            expected_name == show_name and abs(premiere_date.year - start_year) <= 1)


def get_premieredate(show_obj):
    """

    :param show_obj: show object
    :type show_obj: sickgear.tv.TVShow
    :return:
    :rtype: datetime.date or None
    """
    try:
        ep_obj = show_obj.first_aired_regular_episode
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


def get_show_name_date(show_obj):
    # type: (TVShow) -> Tuple[Optional[AnyStr], Optional[datetime.date]]
    return clean_show_name(show_obj.name), get_premieredate(show_obj)


def combine_mapped_new_dict(mapped, new_ids):
    # type: (Dict[int, Dict], Dict[int, integer_types]) -> Dict[int, integer_types]
    return {n: m for d in ({k: v['id'] for k, v in iteritems(mapped) if v['id']}, new_ids) for n, m in iteritems(d)}


def combine_new_ids(cur_ids, new_ids, src_id):
    # type: (Dict[int, integer_types], Dict[int, integer_types], int) -> Dict[int, integer_types]
    """
    combine cur_ids with new_ids, priority has cur_ids with exception of src_id key

    :param cur_ids:
    :param new_ids:
    :param src_id:
    """
    return {k: v for d in (cur_ids, new_ids) for k, v in iteritems(d)
            if v and (k == src_id or not cur_ids.get(k) or v == cur_ids.get(k, ''))}


def map_indexers_to_show(show_obj, update=False, force=False, recheck=False, im_sql_result=None):
    # type: (sickgear.tv.TVShow, Optional[bool], Optional[bool], Optional[bool], Optional[list]) -> dict
    """

    :param show_obj: TVShow Object
    :param update: add missing + previously not found ids
    :param force: search for and replace all mapped/missing ids (excluding NO_AUTOMATIC_CHANGE flagged)
    :param recheck: load all ids, don't remove existing
    :param im_sql_result:
    :return: mapped ids
    """
    mapped = {}

    # init mapped tvids object
    for tvid in indexer_list:
        mapped[tvid] = {'id': (0, show_obj.prodid)[int(tvid) == int(show_obj.tvid)],
                        'status': (MapStatus.NONE, MapStatus.SOURCE)[int(tvid) == int(show_obj.tvid)],
                        'date': datetime.date.fromordinal(1)}

    sql_result = []
    for cur_row in im_sql_result or []:
        if show_obj.prodid == cur_row['indexer_id'] and show_obj.tvid == cur_row['indexer']:
            sql_result.append(cur_row)

    if not sql_result:
        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT * FROM indexer_mapping WHERE indexer = ? AND indexer_id = ?', [show_obj.tvid, show_obj.prodid])

    # for each mapped entry
    for cur_row in sql_result or []:
        date = try_int(cur_row['date'])
        mapped[int(cur_row['mindexer'])] = {'status': int(cur_row['status']),
                                            'id': int(cur_row['mindexer_id']),
                                            'date': datetime.date.fromordinal(date if 0 < date else 1)}

    # get list of needed ids
    mis_map = [k for k, v in iteritems(mapped) if (v['status'] not in [
        MapStatus.NO_AUTOMATIC_CHANGE, MapStatus.SOURCE])
               and ((0 == v['id'] and MapStatus.NONE == v['status'])
                    or force or recheck or (update and 0 == v['id'] and k not in defunct_indexer))]
    if mis_map:
        src_tv_id = show_obj._tvid
        new_ids = NewIdDict(tv_src=src_tv_id)  # type: NewIdDict
        if show_obj.imdbid and re.search(r'\d+$', show_obj.imdbid):
            new_ids[TVINFO_IMDB] = try_int(re.search(r'(?:tt)?(\d+)', show_obj.imdbid).group(1))
        all_ids_srcs = [src_tv_id] + [s for s in (TVINFO_TRAKT, TVINFO_TMDB, TVINFO_TVMAZE, TVINFO_TVDB, TVINFO_IMDB)
                                      if s != src_tv_id]
        searched, confirmed = {}, False
        for r in moves.range(len(all_ids_srcs)):
            search_done = False
            for i in all_ids_srcs:
                if new_ids.verified.get(i):
                    continue
                search_ids = {k: v for k, v in iteritems(combine_mapped_new_dict(mapped, new_ids))
                              if k not in searched.setdefault(i, {})}
                if search_ids:
                    search_done = True
                    searched[i].update(search_ids)
                    new_ids.update(get_missing_ids(search_ids, show_obj, tv_src=i), tv_src=i)
                    if new_ids.get(i) and 0 < new_ids.get(i):
                        searched[i].update({i: new_ids[i]})
                confirmed = all(v for k, v in iteritems(new_ids.verified) if k not in defunct_indexer)
                if confirmed:
                    break
            if confirmed or not search_done:
                break

        for i in indexer_list:
            if i != show_obj.tvid and ((i in mis_map and 0 != new_ids.get(i, 0)) or
                                       (new_ids.verified.get(i) and 0 < new_ids.get(i, 0))):
                if i not in new_ids:
                    mapped[i] = {'status': MapStatus.NOT_FOUND, 'id': 0}
                    continue
                if new_ids.verified.get(i) and 0 < new_ids[i] and mapped.get(i, {'id': 0})['id'] != new_ids[i]:
                    if i not in mis_map:
                        mis_map.append(i)
                    mapped[i] = {'status': MapStatus.NONE, 'id': new_ids[i]}
                    continue
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
                        'REPLACE INTO indexer_mapping (indexer_id, indexer, mindexer_id, mindexer, date, status)'
                        ' VALUES (?,?,?,?,?,?)',
                        [show_obj.prodid, show_obj.tvid, mapped[tvid]['id'], tvid, date, mapped[tvid]['status']]])
                else:
                    sql_l.append([
                        'DELETE FROM indexer_mapping'
                        ' WHERE indexer = ? AND indexer_id = ? AND mindexer = ?',
                        [show_obj.tvid, show_obj.prodid, tvid]])

            if 0 < len(sql_l):
                logger.debug('Adding TV info mapping to DB for show: %s' % show_obj.unique_name)
                my_db = db.DBConnection()
                my_db.mass_action(sql_l)

    show_obj.ids = mapped
    return mapped


def save_mapping(show_obj, save_map=None):
    # type: (sickgear.tv.TVShow, Optional[List[int]]) -> None
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
                'REPLACE INTO indexer_mapping'
                ' (indexer_id, indexer, mindexer_id, mindexer, date, status) VALUES (?,?,?,?,?,?)',
                [show_obj.prodid, show_obj.tvid, show_obj.ids[tvid]['id'],
                 tvid, date, show_obj.ids[tvid]['status']]])
        else:
            sql_l.append([
                'DELETE FROM indexer_mapping WHERE indexer = ? AND indexer_id = ? AND mindexer = ?',
                [show_obj.tvid, show_obj.prodid, tvid]])

    if 0 < len(sql_l):
        logger.debug('Saving TV info mapping to DB for show: %s' % show_obj.unique_name)
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
    my_db.action('DELETE FROM indexer_mapping WHERE indexer = ? AND indexer_id = ?', [tvid, prodid])


def should_recheck_update_ids(show_obj):
    """

    :param show_obj: show object
    :type show_obj: sickgear.tv.TVShow
    :return:
    :rtype: bool
    """
    try:
        today = datetime.date.today()
        ids_updated = min([v.get('date') for k, v in iteritems(show_obj.ids) if k != show_obj.tvid and
                           k not in defunct_indexer] or [datetime.date.fromtimestamp(1)])
        if today - ids_updated >= datetime.timedelta(days=365):
            return True
        ep_obj = show_obj.first_aired_regular_episode
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
    if 'load_all' in kwargs:
        del kwargs['load_all']
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT * FROM indexer_mapping ORDER BY indexer, indexer_id')
    else:
        sql_result = None
    for cur_show_obj in sickgear.showList:
        with cur_show_obj.lock:
            n_kargs = kwargs.copy()
            if 'update' in kwargs and should_recheck_update_ids(cur_show_obj):
                n_kargs['recheck'] = True
            if sql_result:
                n_kargs['im_sql_result'] = sql_result
            try:
                cur_show_obj.ids = sickgear.indexermapper.map_indexers_to_show(cur_show_obj, **n_kargs)
            except (BaseException, Exception):
                logger.debug('Error loading mapped id\'s for show: %s' % cur_show_obj.unique_name)
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

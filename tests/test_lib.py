# coding=UTF-8
# Author: Dennis Lutter <lad1337@gmail.com>
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
import gc
import glob
import locale
import os.path
import re
import random
import shutil
import sys
import xml.etree.ElementTree as ET
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

import sickgear
from sickgear import db, providers, tvcache
from sickgear.common import Quality, VideoCodec
from sickgear.databases import cache_db, failed_db, mainDB
from sg_helpers import try_int
from sickgear.providers.newznab import NewznabConstants

# noinspection PyUnreachableCode
if False:
    from typing import Union

# =================
# test globals
# =================
TESTDIR = os.path.abspath('.')
TESTDBNAME = 'sickbeard.db'
TESTCACHEDBNAME = 'cache.db'
TESTFAILEDDBNAME = 'failed.db'

SHOWNAME = 'show name'
SEASON = 4
EPISODE = 2
FILENAME = f'show name - s0{SEASON}e0{EPISODE}.mkv'
FILEDIR = os.path.join(TESTDIR, SHOWNAME)
FILEPATH = os.path.join(FILEDIR, FILENAME)

SHOWDIR = os.path.join(TESTDIR, f'{SHOWNAME} final')

# sickgear.logger.sb_log_instance = sickgear.logger.SBRotatingLogHandler(
#     os.path.join(TESTDIR, 'sickgear.log'), sickgear.logger.NUM_LOGS, sickgear.logger.LOG_SIZE)
sickgear.logger.SBRotatingLogHandler.log_file = os.path.join(os.path.join(TESTDIR, 'Logs'), 'test_sickgear.log')

# English day and month names for dates in mock data, 'C' is a locale of every platform
locale.setlocale(locale.LC_TIME, 'C')

# =================
# prepare env functions
# =================
def create_test_log_folder():
    if not os.path.isdir(sickgear.LOG_DIR):
        os.mkdir(sickgear.LOG_DIR)


def create_test_cache_folder():
    if not os.path.isdir(sickgear.CACHE_DIR):
        os.mkdir(sickgear.CACHE_DIR)


def remove_test_cache_folder():
    if os.path.isdir(sickgear.CACHE_DIR):
        shutil.rmtree(sickgear.CACHE_DIR, ignore_errors=True)


# call env functions at appropriate time during sickgear var setup

# =================
# sickgear globals
# =================
sickgear.SYS_ENCODING = 'UTF-8'
sickgear.showList = []
sickgear.showDict = {}
sickgear.QUALITY_DEFAULT = 4  # hdtv
sickgear.FLATTEN_FOLDERS_DEFAULT = 0

sickgear.NAMING_PATTERN = ''
sickgear.NAMING_ABD_PATTERN = ''
sickgear.NAMING_SPORTS_PATTERN = ''
sickgear.NAMING_MULTI_EP = 1

sickgear.PROVIDER_ORDER = []
sickgear.newznab_providers = providers.newznab_source_list('')
sickgear.provider_list = providers.provider_modules()

sickgear.PROG_DIR = os.path.abspath('..')
# sickgear.DATA_DIR = os.path.join(sickgear.PROG_DIR, 'tests')
sickgear.DATA_DIR = os.path.join(TESTDIR, 'data')
sickgear.LOG_DIR = os.path.join(TESTDIR, 'Logs')
create_test_log_folder()
sickgear.logger.sb_log_instance.init_logging(False)

sickgear.CACHE_DIR = os.path.join(TESTDIR, 'cache')
sickgear.ZONEINFO_DIR = os.path.join(TESTDIR, 'cache', 'zoneinfo')
create_test_cache_folder()
sickgear.GUI_NAME = 'slick'
sickgear.MEMCACHE = {'history_tab_limit': 10, 'history_tab': []}


# =================
# dummy functions
# =================
def _dummy_save_config():
    return True


# this overrides the save_config which gets called during a db upgrade
# this might be considered a hack
mainDB.sickgear.save_config = _dummy_save_config


# the real one tries to contact tvdb just stop it from getting more info on the ep
# noinspection PyUnusedLocal
def _fake_specify_ep(self, season, episode, show_sql=None, existing_only=False, **kwargs):
    pass


org_specify_episode = sickgear.tv.TVEpisode.specify_episode
sickgear.tv.TVEpisode.specify_episode = _fake_specify_ep


# =================
# test classes
# =================
class SickbeardTestDBCase(unittest.TestCase):
    def setUp(self):
        create_test_cache_folder()
        sickgear.showList = []
        sickgear.showDict = {}
        setup_test_db()
        setup_test_episode_file()
        setup_test_show_dir()

    def tearDown(self):
        remove_test_cache_folder()
        sickgear.showList = []
        sickgear.showDict = {}
        teardown_test_db()
        teardown_test_episode_file()
        teardown_test_show_dir()


class TestDBConnection(db.DBConnection, object):

    def __init__(self, db_file_name=TESTDBNAME, row_type=None):
        db_file_name = os.path.join(TESTDIR, db_file_name)
        super(TestDBConnection, self).__init__(db_file_name, row_type=row_type)


class TestCacheDBConnection(TestDBConnection, object):

    def __init__(self):  #, provider_name):
        db.DBConnection.__init__(self, os.path.join(TESTDIR, TESTCACHEDBNAME))

        # Create the table if it's not already there
        try:
            if not self.has_table('lastUpdate'):
                self.action('CREATE TABLE lastUpdate (provider TEXT, time NUMERIC)')
        except (BaseException, Exception) as e:
            if str(e) != 'table lastUpdate already exists':
                raise e
        # Create the table if it's not already there
        # try:
        #     sql = 'CREATE TABLE ' + provider_name + \
        #           ' (name TEXT, season NUMERIC, episodes TEXT,' \
        #           ' indexerid NUMERIC, url TEXT, time NUMERIC, quality TEXT);'
        #     self.connection.execute(sql)
        #     self.connection.commit()
        # except sqlite3.OperationalError as e:
        #     if 'table %s already exists' % provider_name != str(e):
        #         raise
        #
        # Create the table if it's not already there
        # try:
        #     sql = 'CREATE TABLE lastUpdate (provider TEXT, time NUMERIC);'
        #     self.connection.execute(sql)
        #     self.connection.commit()
        # except sqlite3.OperationalError as e:
        #     if 'table lastUpdate already exists' != str(e):
        #         raise



# this will override the normal db connection
sickgear.db.DBConnection = TestDBConnection
sickgear.tvcache.CacheDBConnection = TestCacheDBConnection


# =================
# test functions
# =================
def setup_test_db():
    """upgrades the db to the latest version
    """
    # upgrading the db
    with db.DBConnection() as sg_db:
        db.migration_code(sg_db)

        # fix up any db problems
        db.sanity_check_db(sg_db, mainDB.MainSanityCheck)

    with db.DBConnection('cache.db') as sg_db:
        # and for cachedb too
        db.upgrade_database(sg_db, cache_db.InitialSchema)

    with db.DBConnection('failed.db') as sg_db:
        # and for faileddb too
        db.upgrade_database(sg_db, failed_db.InitialSchema)


def teardown_test_db():
    """Deletes the test db
        although this seems not to work on my system it leaves me with an zero kb file
    """
    # uncomment next line so leave the db intact between test and at the end
    # return False
    try:
        sickgear.db.DBConnection().close()
    except (BaseException, Exception):
        pass
    try:
        sickgear.tvcache.CacheDBConnection().close()
    except (BaseException, Exception):
        pass

    # force python to garbage collect all db connections, so that the file can be deleted
    try:
        gc.collect(2)
    except (BaseException, Exception):
        pass

    for filename in glob.glob(f'{os.path.join(TESTDIR, TESTDBNAME)}*'):
        try:
            os.remove(filename)
        except (BaseException, Exception):
            pass
    for filename in glob.glob(f'{os.path.join(TESTDIR, TESTCACHEDBNAME)}*'):
        try:
            os.remove(filename)
        except (BaseException, Exception):
            pass
    for filename in glob.glob(f'{os.path.join(TESTDIR, TESTFAILEDDBNAME)}*'):
        try:
            os.remove(filename)
        except (BaseException, Exception):
            pass


def setup_test_episode_file():
    if not os.path.exists(FILEDIR):
        os.makedirs(FILEDIR)

    try:
        with open(FILEPATH, 'w') as f:
            f.write('foo bar')
    except EnvironmentError:
        print('Unable to set up test episode')
        raise


def teardown_test_episode_file():
    if os.path.exists(FILEDIR):
        shutil.rmtree(FILEDIR)


def setup_test_show_dir():
    if not os.path.exists(SHOWDIR):
        os.makedirs(SHOWDIR)


def teardown_test_show_dir():
    if os.path.exists(SHOWDIR):
        shutil.rmtree(SHOWDIR)


teardown_test_db()

# =======================
# test dummy newznab responses
# =======================

tvinfo_src_ids = ['tvdbid', 'tvmazeid', 'imdbid', 'tmdbid', 'traktid']

sample_show_names = [
    'The Shwo',
    'A Example',
    'Another thing',
    'Something',
    'Random Name',
    'Sample',
    'Test Series',
    'Show',
    'Real Show',
    '45678',
    'Whatever'
]

quality_str = {
    5030: ['480p'],
    5040: ['720p','720p hdtv','720p webrip','720p webdl','720p bluray',
           '1080p', '1080p hdtv', '1080p webrip', '1080p webdl', '1080p bluray'],
    5045: ['2160p','2160p webrip','2160p webdl','2160p bluray'],
}

quality_nb = {
    '480p': 5030,
    '720p': 5040,
    '1080p': 5040,
    '216p': 5045
}

quality_regex_nb = {re.compile(f'\\b{k}\\b', flags=re.I): v for k, v in quality_nb.items()}

quality_int = {
    Quality.SDTV: 5030,
    Quality.SDDVD: 5030,
    Quality.HDTV: 5040,
    Quality.RAWHDTV: 5040,
    Quality.FULLHDTV: 5040,
    Quality.HDWEBDL: 5040,
    Quality.FULLHDWEBDL: 5040,
    Quality.HDBLURAY: 5040,
    Quality.FULLHDBLURAY: 5040,
    # Quality.UHD4KTV: 5045,
    Quality.UHD4KWEB: 5045,
    Quality.UHD4KBLURAY: 5045
}

quality_int_str = {
    Quality.SDTV: '480p',
    Quality.SDDVD: '480p DVDRip',
    Quality.HDTV: '720p hdtv',
    Quality.RAWHDTV: '1080i hdtv',
    Quality.FULLHDTV: '1080p',
    Quality.HDWEBDL: '720p webdl',
    Quality.FULLHDWEBDL: '1080p webdl',
    Quality.HDBLURAY: '720p bluray',
    Quality.FULLHDBLURAY: '1080p bluray',
    # Quality.UHD4KTV: '2160p',
    Quality.UHD4KWEB: '2160p webdl',
    Quality.UHD4KBLURAY: '2160p bluray'
}

codec_str = [
    'mpeg2',
    'xvid',
    'divx',
    'h264',
    'x264',
    'h265',
    'x264',
    'vp9',
    'av1',
]

codec_int_str = {
    VideoCodec.VC_UNKNOWN: '',
    VideoCodec.VC_MPEG1: 'MPEG1',
    VideoCodec.VC_MPEG2: 'MPEG2',
    VideoCodec.VC_DivXvid: 'xvid',
    VideoCodec.VC_VC1: 'VC1',
    VideoCodec.VC_264: 'x264',
    VideoCodec.VC_VP9: 'VP9',
    VideoCodec.VC_265: 'x265',
    VideoCodec.VC_AV1: 'AV1',
    VideoCodec.VC_VVC: 'VVC',
    VideoCodec.VC_AV2: 'AV2'
}


def get_cat_nb_from_release_name(release_name):
    for k, v in quality_regex_nb.items():
        if k.search(release_name):
            return v


space_replace_regex = re.compile(' +')
newznab_pubdate = '%a, %d %b %Y %H:%M:%S %z'
tzinfo_newznab = datetime.timezone(datetime.timedelta(0), 'GMT')


def generate_release_name(use_dots=True, show_name=None, season=None, episodes=None, quality=None, codec=None,
                          group=None, p_types=None, random_proper=False, must_be_proper=False, cat=5030, data_set=None):
    # type (bool, str, Union[int,str], str, str, str, list, bool, int, set) -> str
    """
    generate random release name (incorporates given values)

    :param use_dots: use dots instead of spaces as seperators
    :param show_name: show name
    :param season: season number
    :param episodes: episode number(s)
    :param quality: quality string
    :param codec: codec string
    :param group: group name
    :param p_types: list of requested proper types (proper, repack, real)
    :param random_proper: add p_types randomly including one
    :param must_be_proper: at least 1 proper word must be used
    :param cat: cat to use
    :param data_set: alternatively to above individual options, dict with all fields
    """
    if not isinstance(data_set, dict):
        data_set = {}
    if 'quality' in data_set and data_set['quality'] in quality_int:
        cat = quality_int[data_set['quality']]
    if cat not in quality_str:
        cat = 5030
    show_name = data_set.get('show_name') or show_name
    if not show_name:
        nb = random.randint(0, len(sample_show_names) - 1)
        show_name = sample_show_names[nb]
    episode = None
    episode_end = ''
    if 'episode' in data_set:
        episode = data_set['episode']
        if isinstance(data_set.get("episode_end", None), int):
            episode_end = f'E{data_set["episode_end"]:02d}'
    if isinstance(episodes, str) and '-' in episodes:
        episodes = episodes.split('-')
        episode = int(episodes[0])
        episode_end = f'E{int(episodes[1]):02d}'
    elif None is not episodes:
        episode_end = ''
        episode = episodes
    elif None is episodes:
        episode_end = ''
        episode = ''
    if None is season and 'season' in data_set:
        season = data_set['season']
    elif not isinstance(season, int):
        season = random.randint(1, 50)
    if None is episode:
        episode = random.randint(1, 50)
    ep_str = ''
    if '' != episode:
        ep_str = f'E{episode:02d}{episode_end}'
    ep_nb_str = f'S{season:02d}{ep_str}'
    if 'ep_title' in data_set:
        ep_title_text = data_set['ep_title']
    else:
        ep_title_text = ('', 'some tile')[random.randint(0, 1)]
    if 'quality' in data_set:
        quality = quality_int_str.get(data_set['quality'])
    if None is quality:
        quality = quality_str[cat][random.randint(0, len(quality_str[cat]) - 1)]
    if 'codec' in data_set:
        codec = codec_int_str.get(data_set['codec'], '')
    if None is codec:
        codec = codec_str[random.randint(0, len(codec_str) - 1)]
    if 'group' in data_set:
        group = data_set['group']
    if None is group:
        group = 'grp'
    proper_str = ''
    if 'proper' in data_set:
        proper_str = data_set['proper']
    if p_types:
        if must_be_proper:
            p_l = [p_types[random.randint(0, len(p_types)-1)]]
            o_p = p_types.copy()
            o_p.remove(p_l[0])
            p_l.extend([p for p in o_p if not random_proper or random.randint(0, 1)])
            proper_str = ' '.join(p_l)
        else:
            proper_str = ' '.join(p for p in p_types or [] if not random_proper or (random_proper and random.randint(0, 1)))
    s_n = f'{show_name} {ep_nb_str} {proper_str} {ep_title_text} {quality} {codec}-{group}'
    s_n = space_replace_regex.sub((' ', '.')[use_dots], s_n)
    return s_n


def generate_random_date(start_d, end_d):
    # type: (float, float) -> datetime.datetime
    """
    generates a random date between given 2 timestamps

    :param start_d: start timestomp
    :param end_d: end timestamp
    :return: random datetime.datetime
    """
    return datetime.datetime.fromtimestamp(start_d + ((end_d - start_d) * random.random()), tz=tzinfo_newznab)


def guid_generator():
    """
    generates a random 32 char guid
    """
    return '%030x' % random.randrange(16**32)


def _randint_exclude(start, stop, exclude_list):
    # type: (int, int, list) -> int
    while True:
        r = random.randint(start, stop)
        if r not in exclude_list or []:
            return r


def generate_item_list(count=100, start_pub=None, end_pub=None, base_data=None, p_types=None, cats=None,
                       exclude_src_ids=None):
    # type: (int, datetime.datetime, datetime.datetime, list, list, list, dict) -> list
    """
    generates a list of result items

    :param count: count of results
    :param start_pub: start datetime for pubdate
    :param end_pub: end datetime for pubdate
    :param base_data: base items to include in list
    :param p_types: list of requested proper types (proper, repack, real)
    :param cats: list of wanted cats
    :param exclude_src_ids: tvinfo src ids to exclude
    """
    if None is start_pub:
        start_pub = datetime.datetime.now(tz=tzinfo_newznab) - datetime.timedelta(minutes=30)
    if None is end_pub:
        end_pub = datetime.datetime.now(tz=tzinfo_newznab)
    start_pub = start_pub.timestamp()
    end_pub = end_pub.timestamp()

    # collect all base src_ids
    for _b in base_data:
        for _src_id in tvinfo_src_ids:
            if _src_id in _b:
                exclude_src_ids.setdefault(_src_id, set()).add(_b[_src_id])

    random_dates = [generate_random_date(start_pub, end_pub) for _i in range(0, count)]
    random_dates.sort()
    guid_list = set()
    for _i in base_data:
        guid_list.add(_i['guid'])
    while True:
        guid_list.add(guid_generator())
        if count <= len(guid_list):
            break
    for _i in base_data:
        guid_list.remove(_i['guid'])
    l = []
    for bd in base_data or []:
        entry = bd.copy()
        for src_id in tvinfo_src_ids:
            if src_id in bd:
                entry[src_id] = bd[src_id]
        l.append(entry)
    # add random fill items
    while True:
        cat = cats[random.randint(0, len(cats)-1)]
        entry = {
            'release_name': generate_release_name(p_types=p_types, random_proper=True, cat=cat),
            'item_category': 'TV > HD',
            'category_id': 5000,
            'category_sub_id': cat,
            'size': random.randint(0, 1024**3*50),
        }
        for src_id in tvinfo_src_ids:
            if random.randint(0, 1):
                entry[src_id] = _randint_exclude(1, 1000000, exclude_src_ids.get(src_id, []))
        entry['guid'] = guid_list.pop()
        l.append(entry)
        if count <= len(l):
            break
    # randomize base_data items and random generated items
    random.shuffle(l)
    # add pubDate in descending order
    for _n, _i in enumerate(l):
        _i['pubDate'] = random_dates[_n]
    return l


# basic categories list for caps
categories_list = [
    {'id': '1000',
     'name': 'Console',
     'subcats': [{'id': '1010', 'name': 'NDS', 'description': 'Console'},
                 {'id': '1020', 'name': 'PSP', 'description': 'Console'},
                 {'id': '1030', 'name': 'Wii', 'description': 'Console'},
                 {'id': '1035', 'name': 'Switch', 'description': 'Console'},
                 {'id': '1040', 'name': 'Xbox', 'description': 'Console'},
                 {'id': '1050', 'name': 'Xbox 360', 'description': 'Console'},
                 {'id': '1060', 'name': 'WiiWare/VC', 'description': 'Console'},
                 {'id': '1070', 'name': 'XBOX 360 DLC', 'description': 'Console'},
                 {'id': '1080', 'name': 'PS3', 'description': 'Console'},
                 {'id': '1090', 'name': 'Xbox One', 'description': 'Console'},
                 {'id': '1100', 'name': 'PS4', 'description': 'Console'},
                 {'id': '1110', 'name': 'NSW', 'description': 'Console'},
                 ]
     },
    {'id': '2000',
     'name': 'Movies',
     'subcats': [{'id': '2010', 'name': 'Foreign', 'description': 'Movies'},
                 {'id': '2020', 'name': 'Other', 'description': 'Movies'},
                 {'id': '2030', 'name': 'SD', 'description': 'Movies'},
                 {'id': '2040', 'name': 'HD', 'description': 'Movies'},
                 {'id': '2045', 'name': 'UHD', 'description': 'Movies'},
                 {'id': '2050', 'name': 'BluRay', 'description': 'Movies'},
                 {'id': '2060', 'name': '3D', 'description': 'Movies'},
                 ]
     },
    {'id': '3000',
     'name': 'Audio',
     'subcats': [{'id': '3010', 'name': 'MP3', 'description': 'Audio'},
                 {'id': '3020', 'name': 'Video', 'description': 'Audio'},
                 {'id': '3030', 'name': 'Audiobook', 'description': 'Audio'},
                 {'id': '3040', 'name': 'Lossless', 'description': 'Audio'},
                 ]
     },
    {'id': '4000',
     'name': 'PC',
     'subcats': [{'id': '4010', 'name': '0day', 'description': 'PC'},
                 {'id': '4020', 'name': 'ISO', 'description': 'PC'},
                 {'id': '4030', 'name': 'Mac', 'description': 'PC'},
                 {'id': '4040', 'name': 'Mobile-Other', 'description': 'PC'},
                 {'id': '4050', 'name': 'Games', 'description': 'PC'},
                 {'id': '4060', 'name': 'Mobile-iOS', 'description': 'PC'},
                 {'id': '4070', 'name': 'Mobile-Android', 'description': 'PC'},
                 ]
     },
    {'id': '5000',
     'name': 'TV',
     'subcats': [{'id': '5020', 'name': 'Foreign', 'description': 'TV'},
                 {'id': '5030', 'name': 'SD', 'description': 'TV'},
                 {'id': '5040', 'name': 'HD', 'description': 'TV'},
                 {'id': '5045', 'name': 'UHD', 'description': 'TV'},
                 {'id': '5050', 'name': 'Other', 'description': 'TV'},
                 {'id': '5060', 'name': 'Sport', 'description': 'TV'},
                 {'id': '5070', 'name': 'Anime', 'description': 'TV'},
                 {'id': '5080', 'name': 'Documentary', 'description': 'TV'},
                 ]
     },
    {'id': '7000',
     'name': 'Books',
     'subcats': [{'id': '7010', 'name': 'Mags', 'description': 'Books'},
                 {'id': '7020', 'name': 'Ebook', 'description': 'Books'},
                 {'id': '7030', 'name': 'Comics', 'description': 'Books'},
                 ]
     },
]


def generate_newznab_caps(domain='api.example.com'):
    # type: (str) -> str
    """
    generates a standard newznab caps result

    :param domain: domain name without http prefix
    """
    root = ET.Element("caps")
    ET.SubElement(root, "server",
                  attrib={
                        'appversion': '1.0.0',
                        'version': '0.1',
                        'title': 'random indexer',
                        'strapline': '',
                        'email': f'info@{domain}',
                        'url': f'{domain}',
                        'image': f'{domain}',
                  })
    ET.SubElement(root, 'limits', attrib={'max': '100', 'default': '100'})
    ET.SubElement(root, 'registration', attrib={'available': 'no', 'open': 'no'})
    searching = ET.SubElement(root, 'searching')
    ET.SubElement(searching, 'search', attrib={'available': 'yes', 'supportedParams': 'q,group'})
    ET.SubElement(searching, 'tv-search', attrib={
        'available': 'yes',
        'supportedParams': 'q,rid,tvdbid,tmdbid,imdbid,tvmazeid,imedid,traktid,season,ep'})
    ET.SubElement(searching, 'movie-search', attrib={'available': 'yes', 'supportedParams': 'q,imdbid,genre'})
    ET.SubElement(searching, 'audio-search', attrib={'available': 'yes', 'supportedParams': 'q'})

    categories = ET.SubElement(root, 'categories')
    for cl in categories_list:
        category = ET.SubElement(categories, 'category', attrib={'id': cl['id'], 'name': cl['name']})
        for sc in cl['subcats']:
            ET.SubElement(category, 'subcat', attrib={'id': sc['id'], 'name': sc['name'],
                                                      'description': sc['description']})

    groups = ET.SubElement(root, 'groups')
    ET.SubElement(groups, 'group', attrib={'id': '1', 'name': 'alt.binaries.usenet',
                                           'description': 'Usenet', 'lastupdate': 'Tue, 14 Jan 2025 19:06:52 0'})
    genres = ET.SubElement(root, 'genres')
    for gid, genre_id in enumerate((1000, 2000, 3000, 4000, 5000, 7000), 1):
        ET.SubElement(genres, 'genre', attrib={'id': f'{gid}', 'categoryid': f'{genre_id}', 'name': 'All'})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t", level=0)
    return ET.tostring(tree.getroot(), encoding='utf8').decode('utf8')


def generate_newznab_feed(data, domain='api.example.com', category='', offset=0, limit=100, attrs=None, extended=False):
    # type: (list, str, str, int, int, list, bool) -> str
    """
    generates a standard newznab result feed

    :param data: list of result items
    :param domain: domain without http prefix
    :param category: base category (optional)
    :param offset: start offset in data items list
    :param limit: limit of returned items
    :param attrs: list of all wanted attrs
    :param extended: want all attrs
    """
    if not isinstance(attrs, list):
        attrs = []
    total = len(data)
    api_key = '123ff5'
    root = ET.Element("rss", attrib={'version': "2.0", 'xmlns:atom': "http://www.w3.org/2005/Atom",
                                     'xmlns:newznab': "http://www.newznab.com/DTD/2010/feeds/attributes/"})
    doc = ET.SubElement(root, "channel")

    ET.SubElement(doc, "atom:link", attrib={'href': f'{domain}', 'rel': 'self', 'type': 'application/rss+xml'})
    ET.SubElement(doc, "title").text = f"{domain}"
    ET.SubElement(doc, "description").text = "example API"
    ET.SubElement(doc, "link").text = f"{domain}"
    ET.SubElement(doc, "language").text = "en-gb"
    ET.SubElement(doc, "webMaster").text = f"info@{domain}"
    ET.SubElement(doc, "category").text = category
    ET.SubElement(doc, "image")   # .text = ''
    ET.SubElement(doc, "newznab:response", attrib={'offset': f"{offset}", 'total': f"{total}"})

    locale.setlocale(locale.LC_TIME, 'C')
    for i in data[offset:offset+limit]:
        title = i['release_name']
        guid = i['guid']
        pubDate = i['pubDate'].strftime(newznab_pubdate)
        item_category = i['item_category']
        category_id = i['category_id']
        category_sub_id = i['category_sub_id']
        size = i['size']
        download_url = f'http://{domain}/api?t=get&amp;id={guid}&amp;apikey={api_key}'

        item = ET.SubElement(doc, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "guid", attrib={'isPermaLink': 'true'}).text = f'{domain}/search?guid={guid}'
        ET.SubElement(item, "link").text = download_url
        ET.SubElement(item, "pubDate").text = pubDate
        ET.SubElement(item, "category").text = item_category
        ET.SubElement(item, "description").text = title
        ET.SubElement(item, "enclosure", attrib={'url': download_url, 'length': f'{size}',
                                                 'type': 'application/x-nzb'})
        ET.SubElement(item, "newznab:attr", attrib={'name': 'category', 'value': f'{category_id}'})
        ET.SubElement(item, "newznab:attr", attrib={'name': 'category', 'value': f'{category_sub_id}'})
        ET.SubElement(item, "newznab:attr", attrib={'name': 'size', 'value': f'{size}'})
        ET.SubElement(item, "newznab:attr", attrib={'name': 'guid', 'value': f'{guid}'})
        for src_id in tvinfo_src_ids:
            if src_id in i and (extended or src_id in attrs):
                ET.SubElement(item, "newznab:attr", attrib={'name': src_id, 'value': f'{i[src_id]}'})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t", level=0)
    return ET.tostring(tree.getroot(), encoding='utf8').decode('utf8')


def generate_recent_items(base_data=None, count=100, cats=None, exclude_src_ids=None):
    # type: (list, int, list, dict) -> list
    """
    generate a recent search items list

    :param base_data: items list to include
    :param count: count of returned items
    :param cats: list of wanted cats
    :param exclude_src_ids: tvinfo src ids to exclude
    """
    return generate_item_list(base_data=base_data, count=count, cats=cats, exclude_src_ids=exclude_src_ids)


def generate_proper_items(base_data=None, count=100, p_types=None, cats=None, exclude_src_ids=None):
    # type: (list, int, list, list, dict) -> list
    """
    generate a proper search items list

    :param base_data: items list to include
    :param count: count of returned items
    :param p_types: list of requested proper types (proper, repack, real)
    :param cats: list of wanted cats
    :param exclude_src_ids: tvinfo ids to exclude
    """
    return generate_item_list(base_data=base_data, count=count, p_types=p_types, cats=cats,
                              exclude_src_ids=exclude_src_ids)


def generate_normal_search_items(base_data=None, count=100, pub_start=None, pub_end=None, cats=None, parsed_q=None,
                                 exclude_src_ids=None):
    # type: (list, int, datetime.datetime, datetime.datetime, list, dict, dict) -> list
    """
    generate items list of any standard search

    :param base_data: items to include
    :param count: count of items to return
    :param pub_start: start of pubdates
    :param pub_end: end of pubdates
    :param cats: list of wanted cats
    :param parsed_q: parsed query from url call
    :param exclude_src_ids: dict of excluded tvinfo src ids
    """
    # filter results for given search string (simulate indexer search)
    if 'q' in parsed_q:
        search_str = parsed_q['q'][0].replace('*', '.*').replace(' ', '.+')
        q_regex = re.compile(search_str, flags=re.I)
        base_data = [b for b in base_data if q_regex.search(b['release_name'])]
    # filter for requested ids
    if any(si in parsed_q for si in tvinfo_src_ids):
        new_base = []
        for b in base_data:
            if any(0 < try_int(parsed_q[src_id][0], -1) == b.get(src_id, -2) for src_id in tvinfo_src_ids):
                new_base.append(b)
        base_data = new_base
    st = pub_start or datetime.datetime.now()
    et = pub_end or datetime.datetime(2005, 12, 31)
    return generate_item_list(base_data=base_data, start_pub=st, end_pub=et, count=count, cats=cats,
                              exclude_src_ids=exclude_src_ids)


def generate_newznab_responce(self, domain, url, parsed_q, **kwargs):
    if 't' in parsed_q:
        offset = try_int(parsed_q.get('offset', [0])[0], 0)
        limit = min(100, try_int(parsed_q.get('limit', [100])[0], 100))
        cats = [try_int(c, 0) for c in parsed_q.get('cat', [''])[0].split(',')]
        attrs = parsed_q.get('attrs', [''])[0].split(',')
        extended = bool(try_int(parsed_q.get('extended', ['0'])[0], 0))
        items = [c for c in self.cur_items if get_cat_nb_from_release_name(c['release_name']) in cats]
        # generate tvinfo src ids exclude lists
        exclude_src_ids = {}
        for _src_id in tvinfo_src_ids:
            _tvi_src = NewznabConstants.providerToIndexerMapping.get(_src_id)
            if self.show_obj.ids.get(_tvi_src, {'id': None})['id']:
                exclude_src_ids.setdefault(_src_id, set()).add(self.show_obj.ids[_tvi_src]['id'])
        if any('caps' == v for v in parsed_q['t']):
            return generate_newznab_caps()
        elif any('tvsearch' == v for v in parsed_q['t']):
            if 0 == offset:
                if not any(si in parsed_q for si in ['q'] + tvinfo_src_ids):
                    self._item_data = generate_recent_items(base_data=items, cats=cats, exclude_src_ids=exclude_src_ids)
                else:
                    self._item_data = generate_normal_search_items(base_data=items, count=self.count,
                                                                   cats=cats, parsed_q=parsed_q,
                                                                   exclude_src_ids=exclude_src_ids)
            return generate_newznab_feed(self._item_data, domain=domain, offset=offset, limit=limit,
                                         attrs=attrs, extended=extended)
        elif any('search' == v for v in parsed_q['t']) and 'q' in parsed_q:
            p_types = []
            for p in parsed_q['q']:
                if 'proper' in p:
                    p_types.append('proper')
                if 'repack' in p:
                    p_types.append('repack')
                if 'real' in p:
                    p_types.append('real')
            if p_types:
                if 0 == offset:
                    self._item_data = generate_proper_items(
                        base_data=[i for i in items if any(_p in i['release_name'].lower() for _p in p_types)],
                        count=self.count, p_types=p_types, cats=cats, exclude_src_ids=exclude_src_ids)
                return generate_newznab_feed(self._item_data, domain=domain, offset=offset, limit=limit,
                                                  attrs=attrs, extended=extended)
    if 'savename' in kwargs:
        savename = kwargs['savename']
        self.result_data.append({'url': url, 'filename': os.path.basename(savename)})
        return True

# nzbget mock helper
class MockServerProxy():

    def __init__(self, process_method, *args, **kwargs):
        super().__init__()
        self._process_method = process_method

    def __call__(self, url, *args, **kwargs):
        self.url = url
        return self

    def writelog(self, *args, **kwargs):
        return True

    def version(self):
        return self._process_method('version')

    def append(self, nzbname, result_url, category, priority, addtotop, addpaused, dupekey, dupescore, dupemode,
               autocat, ppparameters=None):
        # nzbid
        return self._process_method('append', nzbname, result_url, category, priority, addtotop, addpaused, dupekey, dupescore, dupemode,
               autocat, ppparameters)


if '__main__' == __name__:
    print('=========================')
    print('Dont call this directly')
    print('=========================')
    print('you might want to call')

    dirList = os.listdir(TESTDIR)
    for fname in dirList:
        if (0 < fname.find('_test')) and (0 > fname.find('pyc')):
            print(f'- {fname}')

    print('=========================')
    print('or just call all_tests.py')

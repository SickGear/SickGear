# coding=utf-8
from __future__ import print_function
import warnings
warnings.filterwarnings('ignore', module=r'.*fuz.*', message='.*Sequence.*')
warnings.filterwarnings('ignore', module=r'.*dateutil.*', message='.*Unicode.*')

import datetime
import os.path
import random
import sys
import test_lib as test
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

try:
    from lxml import etree
except ImportError:
    try:
        import xml.etree.cElementTree as etree
    except ImportError:
        import xml.etree.ElementTree as etree

from lib.dateutil import parser
from sickbeard.indexers.indexer_config import *
from sickbeard.network_timezones import sb_timezone
from sickbeard.providers import newznab

import sickbeard

sickbeard.SYS_ENCODING = 'UTF-8'

DEBUG = VERBOSE = False

item_parse_test_cases = [
    (('Show.Name.S02E01.720p.HDTV.x264-GROUP', 'https://test.h/test/hhhh'),
     ('Show.Name.S02E01.720p.HDTV.x264-GROUP', 'https://test.h/test/hhhh')),
    (('Show.Name.S02E02.720p.HDTV.x264-GROUP-JUNK', 'https://test.h/test/hhhh'),
     ('Show.Name.S02E02.720p.HDTV.x264-GROUP', 'https://test.h/test/hhhh')),
    (('Show.Name.S02E03.720p.HDTV.x264-GROUP[JUNK]', 'https://test.h'),
     ('Show.Name.S02E03.720p.HDTV.x264-GROUP', 'https://test.h')),
    (('Show.Name.S02E04.720p.HDTV.x264-GROUP-JUNK-JUNK', 'https://test.h'),
     ('Show.Name.S02E04.720p.HDTV.x264-GROUP', 'https://test.h')),
    (('Show.Name.S02E05.720p.HDTV.x264-GROUP-JUNK[JUNK]', 'https://test.h'),
     ('Show.Name.S02E05.720p.HDTV.x264-GROUP', 'https://test.h')),
    ((u'Show.Name.S02E06.720p.HDTV.x264-GROUP-JUNK[JUNK帝]', 'https://test.h'),
     (u'Show.Name.S02E06.720p.HDTV.x264-GROUP', 'https://test.h')),
    ((u'Show.Name.S02E07-EpName帝.720p.HDTV.x264-GROUP帝-JUNK[JUNK帝]', 'https://test.h'),
     (u'Show.Name.S02E07-EpName帝.720p.HDTV.x264-GROUP帝', 'https://test.h')),
    ((u'[grp 帝] Show Name - 11 [1024x576 h264 AAC ger-sub][123456].mp4', 'https://test.h'),
     (u'[grp.帝].Show.Name.-.11.[1024x576.h264.AAC.ger-sub][123456]', 'https://test.h')),
]

size_test_cases = [
    ((1000, 'ad87987dadf7987987'), (1000, 'ad87987dadf7987987')),
    ((1254105454, 'ffdds7766dgdzhghdzghdgg'), (1254105454, 'ffdds7766dgdzhghdzghdgg')),
    ((-1, ''), (-1, None))
]

pubdate_test_cases = [
    'Sat, 28 Jul 2018 07:33:06 +0000',
    'Sun, 10 Sep 2017 23:11:09 +0200'
]

caps_test_cases = [
    {
        'name': 'newznab',
        'data_files': {'caps': 'newznab_caps.xml'},
        'caps': {
            INDEXER_TVDB: 'tvdbid', INDEXER_TVRAGE: 'rid', INDEXER_TVMAZE: 'tvmazeid',
            newznab.NewznabConstants.SEARCH_EPISODE: 'ep', newznab.NewznabConstants.SEARCH_SEASON: 'season',
            newznab.NewznabConstants.SEARCH_TEXT: 'q'
        },
        'cats': {
            newznab.NewznabConstants.CAT_SD: ['5030'], newznab.NewznabConstants.CAT_SPORT: ['5060'],
            newznab.NewznabConstants.CAT_ANIME: ['5070'], newznab.NewznabConstants.CAT_UHD: ['5045'],
            newznab.NewznabConstants.CAT_HD: ['5040']
        },
        'all_cats': [
            {'id': '5070', 'name': 'Anime'}, {'id': '5185', 'name': 'Docu HD'},
            {'id': '5180', 'name': 'Docu SD'}, {'id': '5020', 'name': 'Foreign'},
            {'id': '5040', 'name': 'HD'}, {'id': '5200', 'name': 'HEVC'},
            {'id': '5050', 'name': 'Other'}, {'id': '5030', 'name': 'SD'},
            {'id': '5060', 'name': 'Sport'}, {'id': '5045', 'name': 'UHD'}
        ],
        'limits': 100,
        'server_type': newznab.NewznabConstants.SERVER_DEFAULT
    }, {
        'name': 'nzedb',
        'data_files': {'caps': 'nzedb_caps.xml'},
        'caps': {
            INDEXER_TVDB: 'tvdbid', INDEXER_TVRAGE: 'rid', INDEXER_TVMAZE: 'tvmazeid', INDEXER_TRAKT: 'traktid',
            INDEXER_IMDB: 'imdbid', INDEXER_TMDB: 'tmdbid',
            newznab.NewznabConstants.SEARCH_EPISODE: 'ep', newznab.NewznabConstants.SEARCH_SEASON: 'season',
            newznab.NewznabConstants.SEARCH_TEXT: 'q'
        },
        'cats': {
            newznab.NewznabConstants.CAT_SD: ['5030'], newznab.NewznabConstants.CAT_SPORT: ['5060'],
            newznab.NewznabConstants.CAT_ANIME: ['5070'], newznab.NewznabConstants.CAT_UHD: ['5045'],
            newznab.NewznabConstants.CAT_HD: ['5040'], newznab.NewznabConstants.CAT_WEBDL: ['5010']
        },
        'all_cats': [
            {'id': '5070', 'name': 'Anime'}, {'id': '5080', 'name': 'Documentary'},
            {'id': '5020', 'name': 'Foreign'}, {'id': '5040', 'name': 'HD'},
            {'id': '5999', 'name': 'Other'}, {'id': '5030', 'name': 'SD'},
            {'id': '5060', 'name': 'Sport'}, {'id': '5045', 'name': 'UHD'},
            {'id': '5010', 'name': 'WEB-DL'}
        ],
        'limits': 100,
        'server_type': newznab.NewznabConstants.SERVER_DEFAULT
    }, {
        'name': 'nntmux',
        'data_files': {'caps': 'nntmux_caps.xml'},
        'caps': {
            INDEXER_TVDB: 'tvdbid', INDEXER_TVRAGE: 'rid', INDEXER_TVMAZE: 'tvmazeid', INDEXER_TRAKT: 'traktid',
            INDEXER_IMDB: 'imdbid', INDEXER_TMDB: 'tmdbid',
            newznab.NewznabConstants.SEARCH_EPISODE: 'ep', newznab.NewznabConstants.SEARCH_SEASON: 'season',
            newznab.NewznabConstants.SEARCH_TEXT: 'q'
        },
        'cats': {
            newznab.NewznabConstants.CAT_SD: ['5030'], newznab.NewznabConstants.CAT_SPORT: ['5060'],
            newznab.NewznabConstants.CAT_ANIME: ['5070'], newznab.NewznabConstants.CAT_UHD: ['5045'],
            newznab.NewznabConstants.CAT_HD: ['5040'], newznab.NewznabConstants.CAT_WEBDL: ['5010']
        },
        'all_cats': [
            {'id': '5070', 'name': 'Anime'}, {'id': '5080', 'name': 'Documentary'},
            {'id': '5020', 'name': 'Foreign'}, {'id': '5040', 'name': 'HD'}, {'id': '5999', 'name': 'Other'},
            {'id': '5030', 'name': 'SD'}, {'id': '5060', 'name': 'Sport'}, {'id': '5045', 'name': 'UHD'},
            {'id': '5010', 'name': 'WEB-DL'}, {'id': '5090', 'name': 'X265'}
        ],
        'limits': 100,
        'server_type': newznab.NewznabConstants.SERVER_DEFAULT
    }, {
        'name': 'spotweb',
        'data_files': {'caps': 'spotweb_caps.xml'},
        'caps': {
            INDEXER_TVRAGE: 'rid', INDEXER_TVMAZE: 'tvmazeid',
            newznab.NewznabConstants.SEARCH_EPISODE: 'ep', newznab.NewznabConstants.SEARCH_SEASON: 'season',
            newznab.NewznabConstants.SEARCH_TEXT: 'q'
        },
        'cats': {
            newznab.NewznabConstants.CAT_SD: ['5030'], newznab.NewznabConstants.CAT_SPORT: ['5060'],
            newznab.NewznabConstants.CAT_ANIME: ['5070'], newznab.NewznabConstants.CAT_HD: ['5040']
        },
        'all_cats': [
            {'id': '5020', 'name': 'Foreign'}, {'id': '5030', 'name': 'SD'}, {'id': '5040', 'name': 'HD'},
            {'id': '5050', 'name': 'Other'}, {'id': '5060', 'name': 'Sport'}, {'id': '5070', 'name': 'Anime'}
        ],
        'limits': 500,
        'server_type': newznab.NewznabConstants.SERVER_SPOTWEB
    }, {
        'name': 'NZBHydra',
        'data_files': {'caps': 'hydra1_caps.xml'},
        'caps': {
            INDEXER_TVDB: 'tvdbid', INDEXER_TVRAGE: 'rid',
            newznab.NewznabConstants.SEARCH_EPISODE: 'ep', newznab.NewznabConstants.SEARCH_SEASON: 'season',
            newznab.NewznabConstants.SEARCH_TEXT: 'q'
        },
        'cats': {
            newznab.NewznabConstants.CAT_SD: ['5030'], newznab.NewznabConstants.CAT_SPORT: ['5060'],
            newznab.NewznabConstants.CAT_ANIME: ['5070'], newznab.NewznabConstants.CAT_HD: ['5040']
        },
        'all_cats': [
            {'id': '5020', 'name': 'Foreign'}, {'id': '5030', 'name': 'SD'}, {'id': '5040', 'name': 'HD'},
            {'id': '5050', 'name': 'Other'}, {'id': '5060', 'name': 'Sport'}, {'id': '5070', 'name': 'Anime'},
            {'id': '5080', 'name': 'Documentary'}
        ],
        'limits': 100,
        'server_type': newznab.NewznabConstants.SERVER_HYDRA1
    }, {
        'name': 'NZBHydra 2',
        'data_files': {'caps': 'hydra2_caps.xml'},
        'caps': {
            INDEXER_TVDB: 'tvdbid', INDEXER_TVRAGE: 'rid', INDEXER_TVMAZE: 'tvmazeid', INDEXER_TRAKT: 'traktid',
            newznab.NewznabConstants.SEARCH_EPISODE: 'ep', newznab.NewznabConstants.SEARCH_SEASON: 'season',
            newznab.NewznabConstants.SEARCH_TEXT: 'q'
        },
        'cats': {
            newznab.NewznabConstants.CAT_SD: ['5030'], newznab.NewznabConstants.CAT_SPORT: ['5060'],
            newznab.NewznabConstants.CAT_ANIME: ['5070'], newznab.NewznabConstants.CAT_HD: ['5040']
        },
        'all_cats': [
            {'id': '5070', 'name': 'Anime'},  {'id': '5040', 'name': 'TV HD'},  {'id': '5030', 'name': 'TV SD'}
        ],
        'limits': 100,
        'server_type': newznab.NewznabConstants.SERVER_HYDRA2
    },
]


class FakeNewznabProvider(newznab.NewznabProvider):

    def __init__(self, *args, **kwargs):
        self.FILEDIR = os.path.join(test.TESTDIR, 'newznab_data')
        self._data_files_dict = ({}, kwargs['data_files_dict'])[isinstance(kwargs.get('data_files_dict'), dict)]
        if 'data_files_dict' in kwargs:
            del kwargs['data_files_dict']
        super(FakeNewznabProvider, self).__init__(*args, **kwargs)

    def _read_data(self, filename):
        try:
            f = os.path.join(self.FILEDIR, filename)
            if os.path.isfile(f):
                with open(f, 'r') as d:
                    return d.read().decode('UTF-8')
        except (StandardError, Exception):
            return

    # simulate Data from provider
    def get_url(self, url, skip_auth=False, use_tmr_limit=True, *args, **kwargs):
        data = None
        if '/api?' in url:
            api_parameter = url[url.find('/api?') + 5:]
            if 't=caps' in api_parameter and 'caps' in self._data_files_dict:
                data = self._read_data(self._data_files_dict['caps'])
        return data


class BasicTests(test.SickbeardTestDBCase):

    ns = {'newznab': 'http://www.newznab.com/DTD/2010/feeds/attributes/', 'atom': 'http://www.w3.org/2005/Atom'}
    ns_parsed = dict((k, '{%s}' % v) for (k, v) in ns.items())

    @staticmethod
    def _create_item(title, link, size=-1, uuid='', ids=None, pubdate=None):
        item = etree.Element('item', nsmap=BasicTests.ns)
        title_item = etree.Element('title')
        title_item.text = title
        link_item = etree.Element('link')
        link_item.text = link
        item.append(title_item)
        item.append(link_item)
        if -1 != size:
            size_item = etree.Element('{%s}attr' % BasicTests.ns['newznab'], nsmap=BasicTests.ns)
            size_item.set('name', 'size')
            size_item.set('value', '%s' % size)
            item.append(size_item)
        if uuid:
            uuid_item = etree.Element('{%s}attr' % BasicTests.ns['newznab'], nsmap=BasicTests.ns)
            uuid_item.set('name', 'guid')
            uuid_item.set('value', '%s' % uuid)
            item.append(uuid_item)
        if ids:
            for a, b in ids.iteritems():
                ids_item = etree.Element('{%s}attr' % BasicTests.ns['newznab'], nsmap=BasicTests.ns)
                ids_item.set('name', a)
                ids_item.set('value', '%s' % b)
                item.append(ids_item)
        if pubdate:
            pubdate_item = etree.Element('pubDate')
            pubdate_item.text = pubdate
            item.append(pubdate_item)
        return item

    def test_title_and_url(self):

        if VERBOSE:
            print('Running tests')

        newznab_provider = newznab.NewznabProvider('test', '')

        for cur_test, cur_expected in item_parse_test_cases:
            item = self._create_item(cur_test[0], cur_test[1])
            result = newznab_provider._title_and_url(item)
            self.assertEqual(cur_expected, result)

    def test_get_size_uid(self):

        newznab_provider = newznab.NewznabProvider('test', '')

        for cur_test, cur_expected in size_test_cases:
            item = self._create_item('Show.Name.S01E01.x264-Group', 'http://test.h', cur_test[0], cur_test[1])
            result = newznab_provider.get_size_uid(item, name_space=BasicTests.ns_parsed)
            self.assertEqual(cur_expected, result)

    def test_parse_ids(self):
        ids_test_cases = []
        for k in newznab.NewznabConstants.providerToIndexerMapping.iterkeys():
            rand_id = random.randrange(1, 99999999)
            ids_test_cases.append(({k: rand_id}, {newznab.NewznabConstants.providerToIndexerMapping[k]: rand_id}))

        all_case = {}
        all_case_ex = {}
        for k in newznab.NewznabConstants.providerToIndexerMapping.iterkeys():
            rand_id = random.randrange(1, 99999999)
            all_case.update({k: rand_id})
            all_case_ex.update({newznab.NewznabConstants.providerToIndexerMapping[k]: rand_id})

        ids_test_cases.append((all_case, all_case_ex))

        newznab_provider = newznab.NewznabProvider('test', '')

        for cur_test, cur_expected in ids_test_cases:
            item = self._create_item('Show.Name.S01E01.x264-Group', 'https://test.h', ids=cur_test)
            result = newznab_provider.cache.parse_ids(item, BasicTests.ns_parsed)
            self.assertEqual(cur_expected, result)

    @staticmethod
    def _parse_pub_date(date_str):
        parsed_date = None
        try:
            if date_str:
                p = parser.parse(date_str, fuzzy=True)
                try:
                    p = p.astimezone(sb_timezone)
                except (StandardError, Exception):
                    pass
                if isinstance(p, datetime.datetime):
                    parsed_date = p.replace(tzinfo=None)
        except (StandardError, Exception):
            pass

        return parsed_date

    def test_parse_pub_date(self):
        newznab_provider = newznab.NewznabProvider('test', '')

        for cur_test in pubdate_test_cases:
            item = self._create_item('Show.Name.S01E01.x264-Group', 'https://test.h', pubdate=cur_test)
            result = newznab_provider._parse_pub_date(item)
            cur_expected = self._parse_pub_date(cur_test)
            self.assertEqual(cur_expected, result)


class FakeProviderTests(test.SickbeardTestDBCase):

    def test_caps(self):
        self.longMessage = True
        for cur_test in caps_test_cases:
            newznab_provider = FakeNewznabProvider('test', 'https://fake.fake/', data_files_dict=cur_test['data_files'])
            newznab_provider.enabled = True
            newznab_provider.get_caps()
            msg = 'Test case: %s' % cur_test['name']
            self.assertEqual(cur_test['server_type'], newznab_provider.server_type, msg=msg)
            self.assertEqual(cur_test['limits'], newznab_provider.limits, msg=msg)
            self.assertEqual(cur_test['caps'], newznab_provider.caps, msg=msg)
            self.assertEqual(cur_test['cats'], newznab_provider.cats, msg=msg)
            self.assertEqual(cur_test['all_cats'], newznab_provider.all_cats, msg=msg)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        suite = unittest.TestLoader().loadTestsFromName('newznab_tests.BasicTests.test_' + sys.argv[1])
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(BasicTests)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase(FakeProviderTests)
    unittest.TextTestRunner(verbosity=2).run(FakeNewznabProvider)

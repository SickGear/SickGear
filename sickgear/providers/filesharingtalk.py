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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear. If not, see <http://www.gnu.org/licenses/>.

from datetime import datetime, timedelta
import difflib
import re
import time
import traceback

import sickgear
from . import generic
from .. import classes, logger, show_name_helpers, tvcache
from ..classes import NZBDataSearchResult
from ..common import NeededQualities
from ..tv import TVEpisode

from bs4_parser import BS4Parser

from six import iteritems

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional


class FSTProvider(generic.NZBProvider):

    def __init__(self):
        generic.NZBProvider.__init__(self, 'FileSharingTalk')

        self.url_base = 'https://filesharingtalk.com/'  # type: AnyStr
        self.urls = {'config_provider_home_uri': self.url_base,
                     'cache': self.url_base + 'nzbs/tv/%s?sort=age&order=desc',
                     'search_init': self.url_base + 'search.php?search_type=1#ads=15',
                     'search': self.url_base + 'search.php?do=process'}  # type: Dict[AnyStr, AnyStr]
        self.url = self.urls['config_provider_home_uri']

        self.digest = None
        self.cache = FSTCache(self)

    cat_sd = ['dvdr', 'xvid', 'x264sd', 'misc']
    cat_hd = ['x264720', 'x2641080', 'webdl720', 'misc']

    @staticmethod
    def _get_cats(needed):
        """

        :param needed: needed class
        :type needed: NeededQualities
        :return:
        :rtype: List
        """
        cats = []
        if needed.need_sd:
            cats.extend(FSTProvider.cat_sd)
        if needed.need_hd:
            cats.extend(FSTProvider.cat_hd)
        return list(set(cats))

    def _init_cookies(self):
        # type: (...) -> Optional[bool]
        """
        :return: False if success with no issues, or None if failure to init
        """
        if not self.should_skip():
            self.cookies = self.digest
            success, msg = self._check_cookie()
            if success:
                return False
            logger.warning(u'%s: %s' % (msg, self.cookies))

        self.cookies = None
        return None

    def _search_provider(self, search, search_mode='eponly', needed=NeededQualities(need_all=True), **kwargs):
        # type: (AnyStr, AnyStr, NeededQualities, Any) -> List
        """
        :param search:
        :param search_mode:
        :param needed:needed class
        :param kwargs:
        """
        self._init_cookies()
        results = []
        if None is getattr(self, 'cookies', None):
            return results

        cats = self._get_cats(needed=needed)
        if not cats:
            return results

        rc = dict((k, re.compile('(?i)' + v)) for (k, v) in iteritems(dict(
            cat='(?:%s)' % '|'.join(cats), results='(?:collections|searchbits)')))
        mode = ('search', 'cache')['' == search]
        post_data = None
        if 'cache' == mode:
            pages = ['', 'page2']
        else:
            html = self.get_url(self.urls['search_init'])
            try:
                token = re.findall(r'(?i)token["\s]+[^"]+"([0-9a-f-]+)"', html)[0]
            except(BaseException, Exception):
                token = None
            if not token:
                logger.warning('Failed to parse an initial search token')
                pages = []
            else:
                post_data = {'ngsubcategory[]': [16, 17, 53, 22, 23, 51, 49, 24]}
                post_data.update(dict(
                    query='%s' % search, securitytoken='%s' % token, dosearch='Search+Now', saveprefs=0, searchdate=0,
                    searchuser='', s='', sortby='dateline', order='descending', beforeafter='after', overridesearch=1,
                    searchfromtype='fstNZB:Collection', contenttypeid='', do='process'))
                pages = ['']

        for cur_page in pages:
            cnt = len(results)
            search_url = self.urls[mode]
            if 'cache' == mode:
                search_url = search_url % cur_page

            html = self.get_url(search_url, post_data=post_data)
            if self.should_skip():
                return results

            try:
                if not html:
                    raise generic.HaltParseException

                with BS4Parser(html, parse_only={'ol': {'id': rc['results']}}) as soup:  # 'collections'
                    tbl_rows = [] if not soup else soup.find_all('li', class_='collectionbit')

                    if 1 > len(tbl_rows):
                        raise generic.HaltParseException

                    for tr in tbl_rows:
                        try:
                            if tr.find('img', class_=rc['cat']):
                                title = tr['data-title'].strip()
                                age = tr.find(class_='binaryage').find('dd').get_text(strip=True).lower()
                                age_value, age_dim = age.split()
                                rls_dt = None
                                age_arg = 'hours' if 'hour' in age_dim else 'days' if 'day' in age_dim else None
                                if age_arg:
                                    rls_dt = datetime.utcnow() - timedelta(**{age_arg: float(age_value)})
                                info_url = self._link(tr['data-url'].strip())
                        except (AttributeError, TypeError, ValueError):
                            continue

                        if title and info_url and rls_dt:
                            results.append({'title': title, 'link': info_url, 'release_dt': rls_dt})

            except generic.HaltParseException:
                time.sleep(1.1)
                pass
            except (BaseException, Exception):
                logger.error(u'Failed to parse. Traceback: %s' % traceback.format_exc())

            self._log_search((mode, search_mode)['Propers' == search_mode], len(results) - cnt, search_url)
        return results

    def find_propers(self, **kwargs):
        """

        :param kwargs:
        :return:
        :rtype: List[classes.Proper]
        """
        results = []
        if not self.should_skip():

            search_terms = ['.PROPER.', '.REPACK.', '.REAL.']
            for term in search_terms:
                for item in self._search_provider(term, search_mode='Propers'):
                    title, url = self._title_and_url(item)
                    results.append(classes.Proper(title, url, item['release_dt'], self.show_obj))

        return results

    @staticmethod
    def common_string(files):
        # type: (List) -> Optional[AnyStr]
        """ find a string common to many strings
        e.g 1) 123.rar 2) 123.par2 3) 123.nfo returns `123`

        :param files: list of strings
        :return: string common to those in list or None
        """

        result = None

        def __matcher(_s1, _s2):
            sequencer = difflib.SequenceMatcher(None, _s1, _s2)
            pos_a, pos_b, size = max(sequencer.get_matching_blocks(), key=lambda _x: _x[2])
            # noinspection PyUnresolvedReferences
            return sequencer.a[pos_a:pos_a + size]

        base_names = set()
        # 1st pass, get candidates of common part of name
        s1 = files[0]
        for s2 in files[1:]:
            s1 = __matcher(s1, s2)
            base_names.add(s1)

        # 2nd pass, finds base name
        files2nd = sorted(list(base_names), key=len)
        s1 = files2nd[0]
        for s2 in files2nd[1:]:
            s1 = __matcher(s1, s2)
            if '.' == s1[-1]:
                result = s1[0:-1]
                break

        return result

    def get_data(self, url):
        """
        :param url: url
        :type url: AnyStr
        :return:
        :rtype:
        """
        result = None
        if url and False is self._init_cookies():
            html = self.get_url(url, timeout=90)
            if not self.should_skip() and html:
                try:
                    collection = int(url.rpartition('/')[-1].split('-')[0])
                except(BaseException, Exception):
                    collection = None

                if collection:
                    with BS4Parser(html, parse_only={'div': {'id': 'binaryeditor'}}) as soup:
                        nzb_rows = [] if not soup else soup.find_all('li', {'data-collectionid': '%s' % collection})
                        try:
                            files = sorted([_x.find(class_='subject').find('dd').get_text(strip=True)
                                            for _x in nzb_rows], key=len, reverse=True)
                        except(BaseException, Exception):
                            files = []

                    if len(files):
                        base_name = self.common_string(files)
                        if base_name:
                            base_url = 'https://nzbindex.nl/'
                            # uncomment the following into use if required.
                            # init_url = base_url + 'search/?q=%s' % base_name
                            # html = self.get_url(init_url)
                            # try:
                            #     action = re.findall(r'action="([^"]+)"', html)[0].lstrip('/')
                            # except(BaseException, Exception):
                            #     action = None
                            # if action:
                            #     # get a session disclaimer cookie
                            #     self.get_url(base_url + action, post_data={'_method': 'POST'})
                            #
                            # if 'disclaimer' in self.session.cookies:
                            # all the following to be indented +1 if above is uncommented into use
                            json = self.get_url(base_url + 'search/json?q=%s' % base_name, parse_json=True,
                                                params=dict(max=100, minage=0, maxage=0, sort='agedesc',
                                                            hidespam=1, hidepassword=0, minsize=0, maxsize=0,
                                                            complete=0, hidecross=0, hasNFO=0, poster='', p=0))

                            ids = []
                            idx_eq_fst = True
                            fn_reg = re.compile(r'[^"]+"([^"]+).*')
                            for cur_result in json['results']:
                                ids += [cur_result['id']]
                                # check indexer files match FST files
                                idx_eq_fst = idx_eq_fst and fn_reg.sub(r'\1', cur_result['name']) in files

                            if idx_eq_fst:
                                nzb = '%s.nzb' % base_name
                                response = self.get_url(base_url + 'download/' + nzb, post_data={'n': nzb, 'r[]': ids})

                                if '</nzb>' not in response:
                                    logger.debug('Failed nzb data response: %s' % response)
                                else:
                                    result = response
        return result

    def get_result(self, ep_obj_list, url):
        # type: (List[TVEpisode], AnyStr) -> Optional[NZBDataSearchResult]
        """

        :param ep_obj_list: list of episode objects
        :param url: url
        """
        result = classes.NZBDataSearchResult(ep_obj_list)
        result.get_data_func = self.get_data
        result.url = url
        result.provider = self
        return result

    def _season_strings(self, ep_obj):
        """

        :param ep_obj: episode object
        :type ep_obj: sickgear.tv.TVEpisode
        :return: list of search strings
        :rtype: List[AnyStr]
        """
        return [x for x in show_name_helpers.make_scene_season_search_string(self.show_obj, ep_obj)]

    def _episode_strings(self, ep_obj):
        """

        :param ep_obj: episode object
        :type ep_obj: sickgear.tv.TVEpisode
        :return: list of search strings
        :rtype: List[AnyStr]
        """
        return [x for x in show_name_helpers.make_scene_search_string(self.show_obj, ep_obj)]

    @staticmethod
    def ui_string(key=None):
        return 'filesharingtalk_digest' == key and 'use... \'bb_userid=xx; bb_password=yy\'' or ''


class FSTCache(tvcache.TVCache):
    def __init__(self, this_provider):
        tvcache.TVCache.__init__(self, this_provider)

    def _cache_data(self, **kwargs):
        # noinspection PyProtectedMember
        return self.provider._search_provider('', **kwargs)


provider = FSTProvider()

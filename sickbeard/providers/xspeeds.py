# coding=utf-8
#
# Author: SickGear
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

import re
import traceback

from . import generic
from .. import logger
from ..helpers import has_anime, try_int
from bs4_parser import BS4Parser

from _23 import unidecode
from six import iteritems


class XspeedsProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, 'Xspeeds')

        self.url_base = 'https://www.xspeeds.eu/'
        self.urls = {'config_provider_home_uri': self.url_base,
                     'login_action': self.url_base + 'login.php',
                     'edit': self.url_base + 'usercp.php?act=edit_details',
                     'search': self.url_base + 'browse.php'}

        self.categories = {'Season': [94, 21], 'Episode': [91, 74, 54, 20, 47, 16], 'anime': [70]}
        self.categories['Cache'] = self.categories['Season'] + self.categories['Episode']

        self.url = self.urls['config_provider_home_uri']

        self.username, self.password, self.freeleech, self.minseed, self.minleech = 5 * [None]

    def _authorised(self, **kwargs):

        return super(XspeedsProvider, self)._authorised(
            logged_in=(lambda y=None: self.has_all_cookies(pre='c_secure_')), post_params={'form_tmpl': True})

    def _search_provider(self, search_params, **kwargs):

        results = []
        if not self._authorised():
            return results

        items = {'Cache': [], 'Season': [], 'Episode': [], 'Propers': []}

        rc = dict([(k, re.compile('(?i)' + v)) for (k, v) in
                   iteritems({'info': 'detail', 'get': 'download', 'fl': 'free'})])
        for mode in search_params:
            save_url, restore = self._set_categories(mode)
            if self.should_skip():
                return results
            for search_string in search_params[mode]:
                search_string = search_string.replace(u'£', '%')
                search_string = re.sub(r'[\s.]+', '%', search_string)
                search_string = unidecode(search_string)

                kwargs = dict(post_data={'keywords': search_string, 'do': 'quick_sort', 'page': '0',
                                         'category': '0', 'search_type': 't_name', 'sort': 'added',
                                         'order': 'desc', 'daysprune': '-1'})

                html = self.get_url(self.urls['search'], **kwargs)
                if self.should_skip():
                    return results

                cnt = len(items[mode])
                try:
                    if not html or self._has_no_results(html):
                        raise generic.HaltParseException

                    parse_only = dict(table={'id': (lambda at: at and 'sortabletable' in at)})
                    with BS4Parser(html, parse_only=parse_only) as tbl:
                        tbl_rows = [] if not tbl else tbl.find_all('tr')
                        get_detail = True

                        if 2 > len(tbl_rows):
                            raise generic.HaltParseException

                        head = None
                        for tr in tbl_rows[1:]:
                            cells = tr.find_all('td')
                            if 6 > len(cells):
                                continue
                            try:
                                head = head if None is not head else self._header_row(tr)
                                seeders, leechers, size = [try_int(n, n) for n in [
                                    cells[head[x]].get_text().strip() for x in ('seed', 'leech', 'size')]]
                                if self._reject_item(seeders, leechers, self.freeleech and (
                                        None is cells[1].find('img', title=rc['fl']))):
                                    continue

                                info = tr.find('a', href=rc['info'])
                                title = (tr.find('div', class_='tooltip-content').get_text() or info.get_text()).strip()
                                title = re.findall('(?m)(^[^\r\n]+)', title)[0]
                                download_url = self._link(tr.find('a', href=rc['get'])['href'])
                            except (BaseException, Exception):
                                continue

                            if get_detail and title.endswith('...'):
                                try:
                                    with BS4Parser(self.get_url('%s%s' % (
                                            self.urls['config_provider_home_uri'], info['href'].lstrip('/').replace(
                                                self.urls['config_provider_home_uri'], '')))) as soup_detail:
                                        title = soup_detail.find(
                                            'td', class_='thead', attrs={'colspan': '3'}).get_text().strip()
                                        title = re.findall('(?m)(^[^\r\n]+)', title)[0]
                                except IndexError:
                                    continue
                                except (BaseException, Exception):
                                    get_detail = False

                            title = self.regulate_title(title)
                            if download_url and title:
                                items[mode].append((title, download_url, seeders, self._bytesizer(size)))

                except generic.HaltParseException:
                    pass
                except (BaseException, Exception):
                    logger.log(u'Failed to parse. Traceback: %s' % traceback.format_exc(), logger.ERROR)

                self._log_search(mode, len(items[mode]) - cnt,
                                 ('search string: ' + search_string.replace('%', '%%'), self.name)['Cache' == mode])

                if mode in 'Season' and len(items[mode]):
                    break

            if save_url:
                self.get_url(save_url, post_data=restore)

            results = self._sort_seeding(mode, results + items[mode])

        return results

    def _set_categories(self, mode):
        # set up categories
        html = self.get_url(self.urls['edit'])
        if self.should_skip():
            return None, None
        try:
            form = re.findall('(?is).*(<form.*?save.*?</form>)', html)[0]
            save_url = self._link(re.findall('(?i)action="([^"]+?)"', form)[0])
            tags = re.findall(r'(?is)(<input[^>]*?name=[\'"][^\'"]+[^>]*)', form)
        except (BaseException, Exception):
            return None, None

        cats, params = [], {}
        attrs = [[(re.findall(r'(?is)%s=[\'"]([^\'"]+)' % attr, c) or [''])[0]
                  for attr in ['type', 'name', 'value', 'checked']] for c in tags]
        for itype, name, value, checked in attrs:
            if 'cat' == name[0:3] and 'checkbox' == itype.lower():
                if any(checked):
                    try:
                        cats += [re.findall(r'(\d+)[^\d]*$', name)[0]]
                    except IndexError:
                        pass
            elif 'hidden' == itype.lower() or 'nothing' in name or \
                    (itype.lower() in ['checkbox', 'radio'] and any(checked)):
                params[name] = value
        selects = re.findall('(?is)(<select.*?</select>)', form)
        for select in selects:
            name, values, index = None, None, 0
            try:
                name = re.findall(r'(?is)<select\sname="([^"]+)"', select)[0]
                values = re.findall('(?is)value="([^"]+)"[^"]+("selected"|</option)', select)
                index = ['"selected"' in x[1] for x in values].index(True)
            except ValueError:
                pass
            except IndexError:
                continue
            params[name] = values[index][0]

        restore = params.copy()
        restore.update(dict([('cat%s' % c, 'yes') for c in cats]))
        params.update(dict([('cat%s' % c, 'yes') for c in (
            self.categories[(mode, 'Episode')['Propers' == mode]] +
            ([], self.categories['anime'])[
                (re.search('(Ca|Pr)', mode) and has_anime()) or
                all([re.search('(Se|Ep)', mode) and self.show_obj and self.show_obj.is_anime])])]))
        params['torrentsperpage'] = 40
        self.get_url(save_url, post_data=params)
        if self.should_skip():
            return None, None

        return save_url, restore

    @staticmethod
    def regulate_title(title):

        if re.search(r'(?i)\.web.?(rip)?$', title):
            title = '%s.x264' % title

        return title


provider = XspeedsProvider()

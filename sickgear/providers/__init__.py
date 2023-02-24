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

import importlib
import sys

from . import generic, newznab
from .newznab import NewznabConstants
from .. import logger
import sickgear

from six import iteritems, itervalues

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, List, Union
    from .generic import GenericProvider, NZBProvider, TorrentProvider

# noinspection PyUnresolvedReferences
__all__ = [
    # usenet
    'filesharingtalk',
    'omgwtfnzbs',
    # torrent
    'alpharatio', 'bithdtv', 'blutopia', 'btn',
    'custom01', 'custom11', 'eztv', 'fano', 'filelist', 'funfile',
    'hdbits', 'hdspace', 'hdtorrents',
    'immortalseed', 'iptorrents', 'limetorrents', 'magnetdl', 'milkie', 'morethan', 'nebulance', 'ncore', 'nyaa',
    'pretome', 'privatehd', 'ptf',
    'rarbg', 'revtt', 'scenehd', 'scenetime', 'shazbat', 'showrss', 'snowfl', 'speedapp', 'speedcd',
    'thepiratebay', 'torlock', 'torrentday', 'torrenting', 'torrentleech',  'tvchaosuk',
    'xspeeds',
    # anime
    'tokyotoshokan',
    ]
for module in __all__:
    try:
        m = importlib.import_module('.' + module, 'sickgear.providers')
        globals().update({n: getattr(m, n) for n in m.__all__} if hasattr(m, '__all__')
                         else dict(filter(lambda t: '_' != t[0][0], iteritems(m.__dict__))))
    except ImportError as e:
        if 'custom' != module[0:6]:
            raise e


def sorted_sources():
    # type: (...) -> List[Union[GenericProvider, NZBProvider, TorrentProvider]]
    """
    return sorted provider list

    :return: sorted list of providers
    """
    initial_list = sickgear.provider_list + sickgear.newznab_providers + sickgear.torrent_rss_providers
    provider_dict = dict(zip([x.get_id() for x in initial_list], initial_list))

    new_list = []

    # add all modules in the priority list, in order
    for curModule in sickgear.PROVIDER_ORDER:
        if curModule in provider_dict:
            new_list.append(provider_dict[curModule])

    if not sickgear.PROVIDER_ORDER:
        nzb = list(filter(lambda p: p.providerType == generic.GenericProvider.NZB, itervalues(provider_dict)))
        tor = list(filter(lambda p: p.providerType != generic.GenericProvider.NZB, itervalues(provider_dict)))
        new_list = sorted(filter(lambda p: not p.anime_only, nzb), key=lambda v: v.get_id()) + \
            sorted(filter(lambda p: not p.anime_only, tor), key=lambda v: v.get_id()) + \
            sorted(filter(lambda p: p.anime_only, nzb), key=lambda v: v.get_id()) + \
            sorted(filter(lambda p: p.anime_only, tor), key=lambda v: v.get_id())

    # add any modules that are missing from that list
    for curModule in provider_dict:
        if provider_dict[curModule] not in new_list:
            new_list.append(provider_dict[curModule])

    return new_list


def provider_modules():
    return [x.provider for x in [_get_module_by_name(y) for y in __all__] if x]


def generic_provider_name(n):
    # type: (AnyStr) -> AnyStr
    return n.strip().lower()


def generic_provider_url(u):
    # type: (AnyStr) -> AnyStr
    return u.strip().strip('/').lower().replace('https', 'http')


def _make_unique_list(p_list, d_list=None):
    # type: (List, List) -> List
    """
    remove provider duplicates
    duplicates: same name or api url

    :param p_list: provider list
    :param d_list: provider default list
    :return: unique provider list
    """
    names = set()
    urls = set()
    new_p_list = []

    default_names = [d.name for d in d_list or []]

    p_list = filter(lambda _x: _x.get_id() not in ['sick_beard_index'], p_list)
    for cur_p in p_list:
        g_name = generic_provider_name(cur_p.name)
        g_url = generic_provider_url(cur_p.url)
        if g_name in names or g_url in urls:
            # default entries have priority so remove the non default provider and add the default
            if cur_p.name in default_names:
                new_p_list = [n for n in new_p_list if generic_provider_name(n.name) != g_name and
                              generic_provider_url(n.url) != g_url]
            else:
                continue
        new_p_list.append(cur_p)
        names.add(g_name)
        urls.add(g_url)
    return new_p_list


def newznab_source_list(data):
    # type: (AnyStr) -> List
    default_list = [_create_newznab_source(x) for x in _default_newznab_sources().split('!!!')]
    provider_list = _make_unique_list(list(filter(
        lambda _x: _x, [_create_newznab_source(x) for x in data.split('!!!')])), default_list)

    provider_dict = dict(zip([x.name for x in provider_list], provider_list))

    for curDefault in default_list:
        if not curDefault:
            continue

        if curDefault.name not in provider_dict:
            curDefault.default = True
            provider_list.append(curDefault)
        else:
            provider_dict[curDefault.name].default = True
            for k in ('name', 'url', 'needs_auth', 'search_mode', 'search_fallback',
                      'enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog',
                      'server_type'):
                setattr(provider_dict[curDefault.name], k, getattr(curDefault, k))

    return list(filter(lambda _x: _x, provider_list))


def _create_newznab_source(config_string):
    if not config_string:
        return None

    values = config_string.split('|')
    if 5 <= len(values):
        name, url, enabled = values.pop(0), values.pop(0), values.pop(4-2)
        params = dict()
        for k, d in (('key', ''), ('cat_ids', ''), ('search_mode', 'eponly'), ('search_fallback', 0),
                     ('enable_recentsearch', 0), ('enable_backlog', 0), ('enable_scheduled_backlog', 1),
                     ('server_type', NewznabConstants.SERVER_DEFAULT)):
            try:
                params.update({k: values.pop(0)})
            except IndexError:
                params.update({k: d})
    else:
        logger.log(u'Skipping Newznab provider string: \'%s\', incorrect format' % config_string, logger.ERROR)
        return None

    newznab_module = sys.modules['sickgear.providers.newznab']

    new_provider = newznab_module.NewznabProvider(name, url, **params)
    new_provider.enabled = '1' == enabled

    return new_provider


def torrent_rss_source_list(data):
    provider_list = list(filter(lambda _x: _x, [_create_torrent_rss_source(x) for x in data.split('!!!')]))

    return list(filter(lambda _x: _x, provider_list))


def _create_torrent_rss_source(config_string):
    if not config_string:
        return None

    cookies = None
    search_mode = 'eponly'
    search_fallback = 0
    enable_recentsearch = 0
    enable_backlog = 0

    try:
        values = config_string.split('|')[0:8]  # deprecated: enable_scheduled_backlog by using `[0:8]`
        if 8 == len(values):
            name, url, cookies, enabled, search_mode, search_fallback, enable_recentsearch, enable_backlog = values
        else:
            name = values[0]
            url = values[1]
            enabled = values[3]
    except ValueError:
        logger.log(u"Skipping RSS Torrent provider string: '" + config_string + "', incorrect format",
                   logger.ERROR)
        return None

    try:
        torrent_rss = sys.modules['sickgear.providers.rsstorrent']
    except (BaseException, Exception):
        return

    new_provider = torrent_rss.TorrentRssProvider(name, url, cookies, search_mode, search_fallback, enable_recentsearch,
                                                  enable_backlog)
    new_provider.enabled = '1' == enabled

    return new_provider


def _default_newznab_sources():
    return '!!!'.join([
        '|'.join(_src) for _src in
        (['NZBgeek', 'https://api.nzbgeek.info/', '', '5030,5040', '0', 'eponly', '0', '0', '0'],
         ['DrunkenSlug', 'https://api.drunkenslug.com/', '', '5030,5040', '0', 'eponly', '0', '0', '0'],
         ['NinjaCentral', 'https://ninjacentral.co.za/', '', '5030,5040', '0', 'eponly', '0', '0', '0'],
         )])


def _get_module_by_name(name):
    prefix, cprov, name = 'sickgear.providers.', 'motsuc'[::-1], name.lower()
    if name in __all__ and prefix + name in sys.modules:
        return sys.modules[prefix + name]
    elif cprov in name:
        return None
    raise Exception('Can\'t find %s%s in providers' % (prefix, name))


def get_by_id(provider_id):
    provider_match = [x for x in
                      sickgear.provider_list + sickgear.newznab_providers + sickgear.torrent_rss_providers if
                      provider_id == x.get_id()]

    if 1 != len(provider_match):
        return None
    return provider_match[0]

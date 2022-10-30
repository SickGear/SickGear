# Author: Nic Wolfe <nic@wolfeden.ca>
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
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

import importlib
import sys

from . import generic, newznab
from .newznab import NewznabConstants
from .. import logger
import sickbeard

from _23 import filter_list, filter_iter
from six import iteritems, itervalues

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr, List, Union
    from .generic import GenericProvider, NZBProvider, TorrentProvider

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
        m = importlib.import_module('.' + module, 'sickbeard.providers')
        globals().update({n: getattr(m, n) for n in m.__all__} if hasattr(m, '__all__')
                         else dict(filter_iter(lambda t: '_' != t[0][0], iteritems(m.__dict__))))
    except ImportError as e:
        if 'custom' != module[0:6]:
            raise e


def sortedProviderList():
    # type: (...) -> List[Union[GenericProvider, NZBProvider, TorrentProvider]]
    """
    return sorted provider list

    :return: sorted list of providers
    """
    initialList = sickbeard.providerList + sickbeard.newznabProviderList + sickbeard.torrentRssProviderList
    providerDict = dict(zip([x.get_id() for x in initialList], initialList))

    newList = []

    # add all modules in the priority list, in order
    for curModule in sickbeard.PROVIDER_ORDER:
        if curModule in providerDict:
            newList.append(providerDict[curModule])

    if not sickbeard.PROVIDER_ORDER:
        nzb = filter_list(lambda p: p.providerType == generic.GenericProvider.NZB, itervalues(providerDict))
        tor = filter_list(lambda p: p.providerType != generic.GenericProvider.NZB, itervalues(providerDict))
        newList = sorted(filter_iter(lambda p: not p.anime_only, nzb), key=lambda v: v.get_id()) + \
            sorted(filter_iter(lambda p: not p.anime_only, tor), key=lambda v: v.get_id()) + \
            sorted(filter_iter(lambda p: p.anime_only, nzb), key=lambda v: v.get_id()) + \
            sorted(filter_iter(lambda p: p.anime_only, tor), key=lambda v: v.get_id())

    # add any modules that are missing from that list
    for curModule in providerDict:
        if providerDict[curModule] not in newList:
            newList.append(providerDict[curModule])

    return newList


def makeProviderList():
    return [x.provider for x in [getProviderModule(y) for y in __all__] if x]


def generic_provider_name(n):
    # type: (AnyStr) -> AnyStr
    return n.strip().lower()


def generic_provider_url(u):
    # type: (AnyStr) -> AnyStr
    return u.strip().strip('/').lower().replace('https', 'http')


def make_unique_list(p_list, d_list=None):
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


def getNewznabProviderList(data):
    # type: (AnyStr) -> List
    defaultList = [makeNewznabProvider(x) for x in getDefaultNewznabProviders().split('!!!')]
    providerList = make_unique_list(filter_list(lambda _x: _x, [makeNewznabProvider(x) for x in data.split('!!!')]),
                                    defaultList)

    providerDict = dict(zip([x.name for x in providerList], providerList))

    for curDefault in defaultList:
        if not curDefault:
            continue

        if curDefault.name not in providerDict:
            curDefault.default = True
            providerList.append(curDefault)
        else:
            providerDict[curDefault.name].default = True
            for k in ('name', 'url', 'needs_auth', 'search_mode', 'search_fallback',
                      'enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog',
                      'server_type'):
                setattr(providerDict[curDefault.name], k, getattr(curDefault, k))

    return filter_list(lambda _x: _x, providerList)


def makeNewznabProvider(config_string):
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

    newznab_module = sys.modules['sickbeard.providers.newznab']

    newProvider = newznab_module.NewznabProvider(name, url, **params)
    newProvider.enabled = '1' == enabled

    return newProvider


def getTorrentRssProviderList(data):
    providerList = filter_list(lambda _x: _x, [makeTorrentRssProvider(x) for x in data.split('!!!')])

    return filter_list(lambda _x: _x, providerList)


def makeTorrentRssProvider(config_string):
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
        torrentRss = sys.modules['sickbeard.providers.rsstorrent']
    except (BaseException, Exception):
        return

    newProvider = torrentRss.TorrentRssProvider(name, url, cookies, search_mode, search_fallback, enable_recentsearch,
                                                enable_backlog)
    newProvider.enabled = '1' == enabled

    return newProvider


def getDefaultNewznabProviders():
    return '!!!'.join(['Sick Beard Index|https://lolo.sickbeard.com/|0|5030,5040|0|eponly|0|0|0',
                       'NZBgeek|https://api.nzbgeek.info/||5030,5040|0|eponly|0|0|0',
                       'DrunkenSlug|https://api.drunkenslug.com/||5030,5040|0|eponly|0|0|0',
                       'NinjaCentral|https://ninjacentral.co.za/||5030,5040|0|eponly|0|0|0',
                       ])


def getProviderModule(name):
    prefix, cprov, name = 'sickbeard.providers.', 'motsuc'[::-1], name.lower()
    if name in __all__ and prefix + name in sys.modules:
        return sys.modules[prefix + name]
    elif cprov in name:
        return None
    raise Exception('Can\'t find %s%s in providers' % (prefix, name))


def getProviderClass(provider_id):
    providerMatch = [x for x in
                     sickbeard.providerList + sickbeard.newznabProviderList + sickbeard.torrentRssProviderList if
                     provider_id == x.get_id()]

    if 1 != len(providerMatch):
        return None
    return providerMatch[0]

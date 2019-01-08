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

from os import sys
import importlib

import os.path
import sickbeard

from . import generic, newznab
from .newznab import NewznabConstants
from sickbeard import logger, encodingKludge as ek

__all__ = [
    # usenet
    'omgwtfnzbs',
    # torrent
    'alpharatio', 'bb', 'beyondhd', 'bithdtv', 'blutopia', 'btn',
    'custom01', 'custom11', 'dh', 'ettv', 'eztv', 'fano', 'filelist', 'funfile', 'grabtheinfo',
    'hdbits', 'hdme', 'hdspace', 'hdtorrents', 'horriblesubs',
    'immortalseed', 'iptorrents', 'limetorrents', 'magnetdl', 'milkie', 'morethan', 'nebulance', 'ncore', 'nyaa',
    'pisexy', 'potuk', 'pretome', 'privatehd', 'ptf',
    'rarbg', 'revtt', 'scenehd', 'scenetime', 'shazbat', 'showrss', 'skytorrents', 'snowfl', 'speedcd',
    'thepiratebay', 'torlock', 'torrentday', 'torrenting', 'torrentleech',  'tvchaosuk',
    'wop', 'xspeeds', 'zooqle',
    # anime
    'anizb', 'tokyotoshokan',
    ]
for module in __all__:
    try:
        m = importlib.import_module('.' + module, 'sickbeard.providers')
        globals().update({n: getattr(m, n) for n in m.__all__} if hasattr(m, '__all__')
                         else dict(filter(lambda t: '_' != t[0][0], m.__dict__.items())))
    except ImportError as e:
        if 'custom' != module[0:6]:
            raise e


def sortedProviderList():
    initialList = sickbeard.providerList + sickbeard.newznabProviderList + sickbeard.torrentRssProviderList
    providerDict = dict(zip([x.get_id() for x in initialList], initialList))

    newList = []

    # add all modules in the priority list, in order
    for curModule in sickbeard.PROVIDER_ORDER:
        if curModule in providerDict:
            newList.append(providerDict[curModule])

    if not sickbeard.PROVIDER_ORDER:
        nzb = filter(lambda p: p.providerType == generic.GenericProvider.NZB, providerDict.values())
        tor = filter(lambda p: p.providerType != generic.GenericProvider.NZB, providerDict.values())
        newList = sorted(filter(lambda p: not p.anime_only, nzb), key=lambda v: v.get_id()) + \
            sorted(filter(lambda p: not p.anime_only, tor), key=lambda v: v.get_id()) + \
            sorted(filter(lambda p: p.anime_only, nzb), key=lambda v: v.get_id()) + \
            sorted(filter(lambda p: p.anime_only, tor), key=lambda v: v.get_id())

    # add any modules that are missing from that list
    for curModule in providerDict:
        if providerDict[curModule] not in newList:
            newList.append(providerDict[curModule])

    return newList


def makeProviderList():
    providers = [x.provider for x in [getProviderModule(y) for y in __all__] if x]
    import browser_ua, zlib
    headers = [1449593765, 1597250020]
    for p in providers:
        if abs(zlib.crc32(p.name)) + 40000400 in headers:
            p.headers.update({'User-Agent': browser_ua.get_ua()})
    return providers


def getNewznabProviderList(data):
    defaultList = [makeNewznabProvider(x) for x in getDefaultNewznabProviders().split('!!!')]
    providerList = filter(lambda x: x, [makeNewznabProvider(x) for x in data.split('!!!')])

    seen_values = set()
    providerListDeduped = []
    for d in providerList:
        value = d.name
        if value not in seen_values:
            providerListDeduped.append(d)
            seen_values.add(value)

    providerList = providerListDeduped
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

    return filter(lambda x: x, providerList)


def makeNewznabProvider(configString):
    if not configString:
        return None

    values = configString.split('|')
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
        logger.log(u'Skipping Newznab provider string: \'%s\', incorrect format' % configString, logger.ERROR)
        return None

    newznab = sys.modules['sickbeard.providers.newznab']

    newProvider = newznab.NewznabProvider(name, url, **params)
    newProvider.enabled = enabled == '1'

    return newProvider


def getTorrentRssProviderList(data):
    providerList = filter(lambda x: x, [makeTorrentRssProvider(x) for x in data.split('!!!')])

    seen_values = set()
    providerListDeduped = []
    for d in providerList:
        value = d.name
        if value not in seen_values:
            providerListDeduped.append(d)
            seen_values.add(value)

    return filter(lambda x: x, providerList)


def makeTorrentRssProvider(configString):
    if not configString:
        return None

    cookies = None
    search_mode = 'eponly'
    search_fallback = 0
    enable_recentsearch = 0
    enable_backlog = 0
    enable_scheduled_backlog = 1

    try:
        values = configString.split('|')
        if len(values) == 9:
            name, url, cookies, enabled, search_mode, search_fallback, enable_recentsearch, enable_backlog, \
            enable_scheduled_backlog = values
        elif len(values) == 8:
            name, url, cookies, enabled, search_mode, search_fallback, enable_recentsearch, enable_backlog = values
        else:
            name = values[0]
            url = values[1]
            enabled = values[3]
    except ValueError:
        logger.log(u"Skipping RSS Torrent provider string: '" + configString + "', incorrect format",
                   logger.ERROR)
        return None

    try:
        torrentRss = sys.modules['sickbeard.providers.rsstorrent']
    except:
        return

    newProvider = torrentRss.TorrentRssProvider(name, url, cookies, search_mode, search_fallback, enable_recentsearch,
                                                enable_backlog, enable_scheduled_backlog)
    newProvider.enabled = enabled == '1'

    return newProvider


def getDefaultNewznabProviders():
    return '!!!'.join(['Sick Beard Index|https://lolo.sickbeard.com/|0|5030,5040|0|eponly|0|0|0',
                       'NZBgeek|https://api.nzbgeek.info/||5030,5040|0|eponly|0|0|0',
                       'NZBs.org|https://nzbs.org/||5030,5040|0|eponly|0|0|0',
                       'DrunkenSlug|https://api.drunkenslug.com/||5030,5040|0|eponly|0|0|0',
                       ])


def getProviderModule(name):
    prefix, cprov, name = 'sickbeard.providers.', 'motsuc'[::-1], name.lower()
    if name in __all__ and prefix + name in sys.modules:
        return sys.modules[prefix + name]
    elif cprov in name:
        return None
    raise Exception('Can\'t find %s%s in providers' % (prefix, name))


def getProviderClass(id):
    providerMatch = [x for x in
                     sickbeard.providerList + sickbeard.newznabProviderList + sickbeard.torrentRssProviderList if
                     x.get_id() == id]

    if len(providerMatch) != 1:
        return None
    else:
        return providerMatch[0]

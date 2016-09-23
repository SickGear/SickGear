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

import os.path
import sickbeard

from . import generic
from sickbeard import logger, encodingKludge as ek
# usenet
from . import newznab, omgwtfnzbs, womble
# torrent
from . import alpharatio, beyondhd, bithdtv, bitmetv, btn, btscene, dh, extratorrent, \
    fano, filelist, freshontv, funfile, gftracker, grabtheinfo, hd4free, hdbits, hdspace, \
    ilt, iptorrents, limetorrents, morethan, ncore, pisexy, pretome, privatehd, ptf, \
    rarbg, revtt, scc, scenetime, shazbat, speedcd, \
    thepiratebay, torlock, torrentbytes, torrentday, torrenting, torrentleech, \
    torrentshack, torrentz2, transmithe_net, tvchaosuk, zooqle
# anime
from . import anizb, nyaatorrents, tokyotoshokan
# custom
try:
    from . import custom01
except:
    pass

__all__ = ['omgwtfnzbs',
           'womble',
           'alpharatio',
           'anizb',
           'beyondhd',
           'bithdtv',
           'bitmetv',
           'btn',
           'btscene',
           'custom01',
           'dh',
           'extratorrent',
           'fano',
           'filelist',
           'freshontv',
           'funfile',
           'gftracker',
           'grabtheinfo',
           'hd4free',
           'hdbits',
           'hdspace',
           'ilt',
           'iptorrents',
           'limetorrents',
           'morethan',
           'ncore',
           'pisexy',
           'pretome',
           'privatehd',
           'ptf',
           'rarbg',
           'revtt',
           'scc',
           'scenetime',
           'shazbat',
           'speedcd',
           'thepiratebay',
           'torlock',
           'torrentbytes',
           'torrentday',
           'torrenting',
           'torrentleech',
           'torrentshack',
           'torrentz2',
           'transmithe_net',
           'tvchaosuk',
           'zooqle',
           'nyaatorrents',
           'tokyotoshokan',
           ]


def sortedProviderList():
    initialList = sickbeard.providerList + sickbeard.newznabProviderList + sickbeard.torrentRssProviderList
    providerDict = dict(zip([x.get_id() for x in initialList], initialList))

    newList = []

    # add all modules in the priority list, in order
    for curModule in sickbeard.PROVIDER_ORDER:
        if curModule in providerDict:
            newList.append(providerDict[curModule])

    # add any modules that are missing from that list
    for curModule in providerDict:
        if providerDict[curModule] not in newList:
            newList.append(providerDict[curModule])

    return newList


def makeProviderList():
    return [x.provider for x in [getProviderModule(y) for y in __all__] if x]


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
            providerDict[curDefault.name].name = curDefault.name
            providerDict[curDefault.name].url = curDefault.url
            providerDict[curDefault.name].needs_auth = curDefault.needs_auth
            providerDict[curDefault.name].search_mode = curDefault.search_mode
            providerDict[curDefault.name].search_fallback = curDefault.search_fallback
            providerDict[curDefault.name].enable_recentsearch = curDefault.enable_recentsearch
            providerDict[curDefault.name].enable_backlog = curDefault.enable_backlog

    return filter(lambda x: x, providerList)


def makeNewznabProvider(configString):
    if not configString:
        return None

    search_mode = 'eponly'
    search_fallback = 0
    enable_recentsearch = 0
    enable_backlog = 0

    try:
        values = configString.split('|')
        if len(values) == 9:
            name, url, key, cat_ids, enabled, search_mode, search_fallback, enable_recentsearch, enable_backlog = values
        else:
            name = values[0]
            url = values[1]
            key = values[2]
            cat_ids = values[3]
            enabled = values[4]
    except ValueError:
        logger.log(u"Skipping Newznab provider string: '" + configString + "', incorrect format", logger.ERROR)
        return None

    newznab = sys.modules['sickbeard.providers.newznab']

    newProvider = newznab.NewznabProvider(name, url, key=key, cat_ids=cat_ids, search_mode=search_mode,
                                          search_fallback=search_fallback, enable_recentsearch=enable_recentsearch,
                                          enable_backlog=enable_backlog)
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

    try:
        values = configString.split('|')
        if len(values) == 8:
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
                                                enable_backlog)
    newProvider.enabled = enabled == '1'

    return newProvider


def getDefaultNewznabProviders():
    return '!!!'.join(['Sick Beard Index|http://lolo.sickbeard.com/|0|5030,5040|0|eponly|0|0|0',
                       'NZBgeek|https://api.nzbgeek.info/||5030,5040|0|eponly|0|0|0',
                       'NZBs.org|https://nzbs.org/||5030,5040|0|eponly|0|0|0',
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

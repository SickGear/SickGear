# coding=utf-8
from __future__ import print_function
from __future__ import with_statement
from six import iteritems

# import datetime
import os.path
import re
import sys
import urllib2
import unittest

sys.path.insert(1, os.path.abspath('..'))
sys.path.insert(1, os.path.abspath('../lib'))

from lib.dateutil import parser
import sickbeard
import sickbeard.sbdatetime
from sickbeard import encodingKludge as ek
sickbeard.SYS_ENCODING = 'UTF-8'


def test_plex():
    # try:
    #     username = sickbeard.PLEX_USERNAME
    #     password = sickbeard.PLEX_PASSWORD
    #     hosts = sickbeard.PLEX_SERVER_HOST
    #     rd = sickbeard.ROOT_DIRS
    # except NameError:
    #     pass
    from plex import Plex

    # Test data
    # rd = '1|V:\\VideoDraft\\tv_draft|V:\\Video\\tv|D:\\_Video\\tv|D:\\_Video\\tv_draft' # win
    rd = '1|/media/ota|/media/tv'  # doms set up
    username = password = ''
    # hosts = '10.10.0.200:32400, 10.10.0.198:32400' # win
    hosts = 'https://destiny.slackadelic.com:32400'
    ##########

    plex = Plex({
        'token': 'JYaNBxsanDWEtnhN7Sg7'
        #'username': SickGeard.PLEX_USER_NAME
        #'password': SickGeard.PLEX_PASSWORD
        #, 'default_home_users': 'all'
    })
    # plex.username = username
    # plex.password = password
    plex.section_filter_path = '1|/media/ota|/media/tv'.split('|')[1:]

    for cur_host in [x.strip().lower() for x in hosts.split(',')]:
        parts = urllib2.splitport(cur_host)
        states = {}
        if parts[0]:
            plex.plex_host = parts[0]
            if None is not parts[1]:
                plex.plex_port = parts[1]

            # plex.fetch_show_states(True)  # Fetch all
            plex.fetch_show_states()  # Fetch recent

            for (k, v) in iteritems(plex.show_states):
                if 0 < v.get('played') or 0:
                    states[k] = v
                    print(v['path_file'])

            print(plex.file_count)
            print(len(states))
            print('####################################')
            print('####################################')
            print('####################################')


def test_emby():
    #
    # API help calls pulled from cross referencing web app calls with ...
    # https://github.com/MediaBrowser/Emby.ApiClient.Javascript/blob/master/apiclient.js
    #
    # Test data
    username = password = ''
    apikeys = '3b0c6fa161524d0e9f8c39339659681e'
    hosts = '10.10.0.200:8096'

    ##########

    import sickbeard.notifiers.emby as emby

    client = emby.EmbyNotifier()
    hosts, keys, message = client.check_config(hosts, apikeys)
    if not hosts:
        return False, message

    success = True
    message = []

    rd = '1|V:\\VideoDraft\\tv_draft|V:\\Video\\tv|D:\\_Video\\tv|D:\\_Video\\tv_draft'.split('|')[1:]
    rootpaths = sorted(['%s%s' % (os.path.splitdrive(x)[1], os.path.sep) for x in rd], key=len, reverse=True)
    rootdirs = sorted([x for x in rd], key=len, reverse=True)
    headers = {'Content-type': 'application/json'}
    states = {}
    idx = 0

    for i, cur_host in enumerate(hosts):
        headers.update({'X-MediaBrowser-Token': keys[i]})

        users = sickbeard.helpers.getURL(
            'http://%s/emby/Users' % cur_host,
            headers=headers, params=dict(format='json'), timeout=10, json=True)
        if not users:
            continue

        folders = sickbeard.helpers.getURL(
            'http://%s/emby/Library/VirtualFolders' % cur_host,
            headers=headers, params=dict(format='json'), timeout=10, json=True)
        if not folders:
            continue

        for user in users:
            for folder in filter(lambda r: 'tvshows' in r.get('CollectionType'), folders):
                items = sickbeard.helpers.getURL(
                    'http://%s/emby/Users/%s/Items' % (cur_host, user.get('Id')),
                    headers=headers,
                    params=dict(itemId=folder['ItemId'],
                                SortBy='DatePlayed,SeriesSortName,SortName',
                                SortOrder='Descending',
                                IncludeItemTypes='Episode',
                                Recursive='true',
                                Fields='Path,UserData',
                                StartIndex='0', Limit='100',
                                format='json'),
                    timeout=10, json=True)
                for d in filter(lambda x: 'Episode' == x.get('Type', ''), items.get('Items')):
                    try:
                        root_dir_found = False
                        path_file = d.get('Path')
                        if not path_file:
                            continue
                        for index, p in enumerate(rootpaths):
                            if p in path_file:
                                path_file = ek.ek(os.path.join, rootdirs[index],
                                                  re.sub('.*?%s' % re.escape(p), '', path_file))
                                root_dir_found = True
                                break
                        if not root_dir_found:
                            continue
                        states[idx] = dict(
                            path_file=path_file,
                            media_id=d['Id'],
                            played=100 * (d.get('UserData', {}).get('PlayCount') or 0),
                            label='%s%s{Emby}' % (user.get('Name', ''), bool(user.get('Name')) and ' ' or ''),
                            date_watched=sickbeard.sbdatetime.sbdatetime.totimestamp(
                                parser.parse(d.get('UserData', {}).get('LastPlayedDate'))))
                    except(StandardError, Exception):
                        continue
                    idx += 1
    return success, message


test_plex()
# test_emby()

# coding=utf-8
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

from __future__ import with_statement

import base64
import datetime
import dateutil.parser
import itertools
import os
import random
import re
import sys
import time
import traceback
import urllib
import threading

from mimetypes import MimeTypes
from Cheetah.Template import Template
from six import iteritems

import sickbeard
from sickbeard import config, sab, nzbget, clients, history, notifiers, processTV, ui, logger, helpers, exceptions,\
    classes,  db, search_queue, image_cache, naming, scene_exceptions, search_propers, subtitles, network_timezones,\
    sbdatetime
from sickbeard import encodingKludge as ek
from sickbeard.providers import newznab, rsstorrent
from sickbeard.common import Quality, Overview, statusStrings, qualityPresetStrings
from sickbeard.common import SNATCHED, UNAIRED, IGNORED, ARCHIVED, WANTED, FAILED, SKIPPED, DOWNLOADED, SNATCHED_BEST, SNATCHED_PROPER
from sickbeard.common import SD, HD720p, HD1080p
from sickbeard.exceptions import ex
from sickbeard.helpers import has_image_ext, remove_article, starify
from sickbeard.indexers.indexer_config import INDEXER_TVDB, INDEXER_TVRAGE
from sickbeard.scene_numbering import get_scene_numbering, set_scene_numbering, get_scene_numbering_for_show, \
    get_xem_numbering_for_show, get_scene_absolute_numbering_for_show, get_xem_absolute_numbering_for_show, \
    get_scene_absolute_numbering
from sickbeard.name_cache import buildNameCache
from sickbeard.browser import foldersAtPath
from sickbeard.blackandwhitelist import BlackAndWhiteList, short_group_names
from sickbeard.search_backlog import FORCED_BACKLOG
from sickbeard.indexermapper import MapStatus, save_mapping, map_indexers_to_show
from tornado import gen
from tornado.web import RequestHandler, StaticFileHandler, authenticated
from lib import adba
from lib import subliminal
from lib.dateutil import tz
import lib.rarfile.rarfile as rarfile

from lib.libtrakt import TraktAPI
from lib.libtrakt.exceptions import TraktException, TraktAuthException
from trakt_helpers import build_config, trakt_collection_remove_account
from sickbeard.bs4_parser import BS4Parser
from lib.tmdb_api import TMDB

try:
    import json
except ImportError:
    from lib import simplejson as json


class PageTemplate(Template):
    def __init__(self, headers, *args, **KWs):
        KWs['file'] = os.path.join(sickbeard.PROG_DIR, 'gui/' + sickbeard.GUI_NAME + '/interfaces/default/',
                                   KWs['file'])
        super(PageTemplate, self).__init__(*args, **KWs)

        self.sbRoot = sickbeard.WEB_ROOT
        self.sbHttpPort = sickbeard.WEB_PORT
        self.sbHttpsPort = sickbeard.WEB_PORT
        self.sbHttpsEnabled = sickbeard.ENABLE_HTTPS
        self.sbHandleReverseProxy = sickbeard.HANDLE_REVERSE_PROXY
        self.sbThemeName = sickbeard.THEME_NAME

        if headers['Host'][0] == '[':
            self.sbHost = re.match('^\[.*\]', headers['Host'], re.X | re.M | re.S).group(0)
        else:
            self.sbHost = re.match('^[^:]+', headers['Host'], re.X | re.M | re.S).group(0)

        if 'X-Forwarded-Host' in headers:
            self.sbHost = headers['X-Forwarded-Host']
        if 'X-Forwarded-Port' in headers:
            sbHttpPort = headers['X-Forwarded-Port']
            self.sbHttpsPort = sbHttpPort
        if 'X-Forwarded-Proto' in headers:
            self.sbHttpsEnabled = True if headers['X-Forwarded-Proto'] == 'https' else False

        logPageTitle = 'Logs &amp; Errors'
        if len(classes.ErrorViewer.errors):
            logPageTitle += ' (' + str(len(classes.ErrorViewer.errors)) + ')'
        self.logPageTitle = logPageTitle
        self.sbPID = str(sickbeard.PID)
        self.menu = [
            {'title': 'Home', 'key': 'home'},
            {'title': 'Episodes', 'key': 'episodeView'},
            {'title': 'History', 'key': 'history'},
            {'title': 'Manage', 'key': 'manage'},
            {'title': 'Config', 'key': 'config'},
            {'title': logPageTitle, 'key': 'errorlogs'},
        ]

    def compile(self, *args, **kwargs):
        if not os.path.exists(os.path.join(sickbeard.CACHE_DIR, 'cheetah')):
            os.mkdir(os.path.join(sickbeard.CACHE_DIR, 'cheetah'))

        kwargs['cacheModuleFilesForTracebacks'] = True
        kwargs['cacheDirForModuleFiles'] = os.path.join(sickbeard.CACHE_DIR, 'cheetah')
        return super(PageTemplate, self).compile(*args, **kwargs)


class BaseStaticFileHandler(StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')


class BaseHandler(RequestHandler):
    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')

    def redirect(self, url, permanent=False, status=None):
        if not url.startswith(sickbeard.WEB_ROOT):
            url = sickbeard.WEB_ROOT + url

        super(BaseHandler, self).redirect(url, permanent, status)

    def get_current_user(self, *args, **kwargs):
        if sickbeard.WEB_USERNAME or sickbeard.WEB_PASSWORD:
            return self.get_secure_cookie('sickgear-session')
        else:
            return True

    def showPoster(self, show=None, which=None, api=None):
        # Redirect initial poster/banner thumb to default images
        if which[0:6] == 'poster':
            default_image_name = 'poster.png'
        else:
            default_image_name = 'banner.png'

        static_image_path = os.path.join('/images', default_image_name)
        if show and sickbeard.helpers.findCertainShow(sickbeard.showList, int(show)):
            cache_obj = image_cache.ImageCache()

            image_file_name = None
            if which == 'poster':
                image_file_name = cache_obj.poster_path(show)
            if which == 'poster_thumb':
                image_file_name = cache_obj.poster_thumb_path(show)
            if which == 'banner':
                image_file_name = cache_obj.banner_path(show)
            if which == 'banner_thumb':
                image_file_name = cache_obj.banner_thumb_path(show)

            if ek.ek(os.path.isfile, image_file_name):
                static_image_path = image_file_name

        if api:
            mime_type, encoding = MimeTypes().guess_type(static_image_path)
            self.set_header('Content-Type', mime_type)
            with open(static_image_path, 'rb') as img:
                return img.read()
        else:
            static_image_path = os.path.normpath(static_image_path.replace(sickbeard.CACHE_DIR, '/cache'))
            static_image_path = static_image_path.replace('\\', '/')
            self.redirect(static_image_path)


class LoginHandler(BaseHandler):
    def get(self, *args, **kwargs):
        if self.get_current_user():
            self.redirect(self.get_argument('next', '/home/'))
        else:
            t = PageTemplate(headers=self.request.headers, file='login.tmpl')
            t.resp = self.get_argument('resp', '')
            self.set_status(401)
            self.finish(t.respond())

    def post(self, *args, **kwargs):
        username = sickbeard.WEB_USERNAME
        password = sickbeard.WEB_PASSWORD

        if (self.get_argument('username') == username) and (self.get_argument('password') == password):
            remember_me = int(self.get_argument('remember_me', default=0) or 0)
            self.set_secure_cookie('sickgear-session', sickbeard.COOKIE_SECRET, expires_days=30 if remember_me > 0 else None)
            self.redirect(self.get_argument('next', '/home/'))
        else:
            next_arg = '&next=' + self.get_argument('next', '/home/')
            self.redirect('/login?resp=authfailed' + next_arg)


class LogoutHandler(BaseHandler):
    def get(self, *args, **kwargs):
        self.clear_cookie('sickgear-session')
        self.redirect('/login/')


class CalendarHandler(BaseHandler):
    def get(self, *args, **kwargs):
        if sickbeard.CALENDAR_UNPROTECTED or self.get_current_user():
            self.write(self.calendar())
        else:
            self.set_status(401)
            self.write('User authentication required')

    def calendar(self, *args, **kwargs):
        """ iCalendar (iCal) - Standard RFC 5545 <http://tools.ietf.org/html/rfc5546>
        Works with iCloud, Google Calendar and Outlook.
        Provides a subscribeable URL for iCal subscriptions """

        logger.log(u'Receiving iCal request from %s' % self.request.remote_ip)

        # Limit dates
        past_date = (datetime.date.today() + datetime.timedelta(weeks=-52)).toordinal()
        future_date = (datetime.date.today() + datetime.timedelta(weeks=52)).toordinal()
        utc = tz.gettz('GMT')

        # Get all the shows that are not paused and are currently on air
        myDB = db.DBConnection()
        show_list = myDB.select(
            'SELECT show_name, indexer_id, network, airs, runtime FROM tv_shows WHERE ( status = "Continuing" OR status = "Returning Series" ) AND paused != "1"')

        nl = '\\n\\n'
        crlf = '\r\n'

        # Create iCal header
        appname = 'SickGear'
        ical = 'BEGIN:VCALENDAR%sVERSION:2.0%sX-WR-CALNAME:%s%sX-WR-CALDESC:%s%sPRODID://%s Upcoming Episodes//%s'\
               % (crlf, crlf, appname, crlf, appname, crlf, appname, crlf)

        for show in show_list:
            # Get all episodes of this show airing between today and next month
            episode_list = myDB.select(
                'SELECT indexerid, name, season, episode, description, airdate FROM tv_episodes WHERE airdate >= ? AND airdate < ? AND showid = ?',
                (past_date, future_date, int(show['indexer_id'])))

            for episode in episode_list:

                air_date_time = network_timezones.parse_date_time(episode['airdate'], show['airs'],
                                                                  show['network']).astimezone(utc)
                air_date_time_end = air_date_time + datetime.timedelta(
                    minutes=helpers.tryInt(show['runtime'], 60))

                # Create event for episode
                ical += 'BEGIN:VEVENT%s' % crlf\
                    + 'DTSTART:%sT%sZ%s' % (air_date_time.strftime('%Y%m%d'), air_date_time.strftime('%H%M%S'), crlf)\
                    + 'DTEND:%sT%sZ%s' % (air_date_time_end.strftime('%Y%m%d'), air_date_time_end.strftime('%H%M%S'), crlf)\
                    + 'SUMMARY:%s - %sx%s - %s%s' % (show['show_name'], str(episode['season']), str(episode['episode']), episode['name'], crlf)\
                    + 'UID:%s-%s-%s-E%sS%s%s' % (appname, str(datetime.date.today().isoformat()), show['show_name'].replace(' ', '-'), str(episode['episode']), str(episode['season']), crlf)\
                    + 'DESCRIPTION:%s on %s' % ((show['airs'] or '(Unknown airs)'), (show['network'] or 'Unknown network'))\
                    + ('' if not episode['description'] else '%s%s' % (nl, episode['description'].splitlines()[0]))\
                    + '%sEND:VEVENT%s' % (crlf, crlf)

        # Ending the iCal
        return ical + 'END:VCALENDAR'


class IsAliveHandler(BaseHandler):
    def get(self, *args, **kwargs):
        kwargs = self.request.arguments
        if 'callback' in kwargs and '_' in kwargs:
            callback, _ = kwargs['callback'][0], kwargs['_']
        else:
            return 'Error: Unsupported Request. Send jsonp request with callback variable in the query string.'

        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')
        self.set_header('Content-Type', 'text/javascript')
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Headers', 'x-requested-with')

        if sickbeard.started:
            results = callback + '(' + json.dumps(
                {'msg': str(sickbeard.PID)}) + ');'
        else:
            results = callback + '(' + json.dumps({'msg': 'nope'}) + ');'

        self.write(results)


class WebHandler(BaseHandler):
    def __init__(self, *arg, **kwargs):
        super(BaseHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    def page_not_found(self):
        self.set_status(404)
        t = PageTemplate(headers=self.request.headers, file='404.tmpl')
        return t.respond()

    @authenticated
    @gen.coroutine
    def get(self, route, *args, **kwargs):
        route = route.strip('/') or 'index'
        try:
            method = getattr(self, route)
        except:
            self.finish(self.page_not_found())
        else:
            kwargss = self.request.arguments
            for arg, value in kwargss.items():
                if len(value) == 1:
                    kwargss[arg] = value[0]
            result = method(**kwargss)
            if result:
                self.finish(result)

    def send_message(self, message):
        with self.lock:
            self.write(message)
            self.flush()

    post = get


class MainHandler(WebHandler):
    def index(self):
        self.redirect('/home/')

    def http_error_401_handler(self):
        """ Custom handler for 401 error """
        return r'''<!DOCTYPE html>
    <html>
        <head>
            <title>%s</title>
        </head>
        <body>
            <br/>
            <font color="#0000FF">Error %s: You need to provide a valid username and password.</font>
        </body>
    </html>
    ''' % ('Access denied', 401)

    def write_error(self, status_code, **kwargs):
        if status_code == 401:
            self.finish(self.http_error_401_handler())
        elif status_code == 404:
            self.redirect(sickbeard.WEB_ROOT + '/home/')
        elif self.settings.get('debug') and 'exc_info' in kwargs:
            exc_info = kwargs['exc_info']
            trace_info = ''.join(['%s<br/>' % line for line in traceback.format_exception(*exc_info)])
            request_info = ''.join(['<strong>%s</strong>: %s<br/>' % (k, self.request.__dict__[k] ) for k in
                                    self.request.__dict__.keys()])
            error = exc_info[1]

            self.set_header('Content-Type', 'text/html')
            self.finish('''<html>
                                 <title>%s</title>
                                 <body>
                                    <h2>Error</h2>
                                    <p>%s</p>
                                    <h2>Traceback</h2>
                                    <p>%s</p>
                                    <h2>Request Info</h2>
                                    <p>%s</p>
                                 </body>
                               </html>''' % (error, error,
                                             trace_info, request_info))

    def robots_txt(self, *args, **kwargs):
        """ Keep web crawlers out """
        self.set_header('Content-Type', 'text/plain')
        return 'User-agent: *\nDisallow: /'

    def setHomeLayout(self, layout):

        if layout not in ('poster', 'small', 'banner', 'simple'):
            layout = 'poster'

        sickbeard.HOME_LAYOUT = layout

        self.redirect('/home/showlistView/')

    def setPosterSortBy(self, sort):

        if sort not in ('name', 'date', 'network', 'progress', 'quality'):
            sort = 'name'

        sickbeard.POSTER_SORTBY = sort
        sickbeard.save_config()

    def setPosterSortDir(self, direction):

        sickbeard.POSTER_SORTDIR = int(direction)
        sickbeard.save_config()

    def setHistoryLayout(self, layout):

        if layout not in ('compact', 'detailed'):
            layout = 'detailed'

        sickbeard.HISTORY_LAYOUT = layout

        self.redirect('/history/')

    def toggleDisplayShowSpecials(self, show):

        sickbeard.DISPLAY_SHOW_SPECIALS = not sickbeard.DISPLAY_SHOW_SPECIALS

        self.redirect('/home/displayShow?show=' + show)

    def setEpisodeViewLayout(self, layout):
        if layout not in ('poster', 'banner', 'list', 'daybyday'):
            layout = 'banner'

        if 'daybyday' == layout:
            sickbeard.EPISODE_VIEW_SORT = 'time'

        sickbeard.EPISODE_VIEW_LAYOUT = layout

        sickbeard.save_config()

        self.redirect('/episodeView/')

    def toggleEpisodeViewDisplayPaused(self, *args, **kwargs):

        sickbeard.EPISODE_VIEW_DISPLAY_PAUSED = not sickbeard.EPISODE_VIEW_DISPLAY_PAUSED

        sickbeard.save_config()

        self.redirect('/episodeView/')

    def setEpisodeViewSort(self, sort, redir=1):
        if sort not in ('time', 'network', 'show'):
            sort = 'time'

        sickbeard.EPISODE_VIEW_SORT = sort

        sickbeard.save_config()

        if int(redir):
            self.redirect('/episodeView/')

    def episodeView(self, layout='None'):
        """ display the episodes """
        today_dt = datetime.date.today()
        #today = today_dt.toordinal()
        yesterday_dt = today_dt - datetime.timedelta(days=1)
        yesterday = yesterday_dt.toordinal()
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).toordinal()
        next_week_dt = (datetime.date.today() + datetime.timedelta(days=7))
        next_week = (next_week_dt + datetime.timedelta(days=1)).toordinal()
        recently = (yesterday_dt - datetime.timedelta(days=sickbeard.EPISODE_VIEW_MISSED_RANGE)).toordinal()

        done_show_list = []
        qualities = Quality.DOWNLOADED + Quality.SNATCHED + [ARCHIVED, IGNORED]

        myDB = db.DBConnection()
        sql_results = myDB.select(
            'SELECT *, tv_shows.status as show_status FROM tv_episodes, tv_shows WHERE season != 0 AND airdate >= ? AND airdate <= ? AND tv_shows.indexer_id = tv_episodes.showid AND tv_episodes.status NOT IN (%s)'
            % ','.join(['?'] * len(qualities)),
            [yesterday, next_week] + qualities)

        for cur_result in sql_results:
            done_show_list.append(int(cur_result['showid']))

        sql_results += myDB.select(
            'SELECT *, tv_shows.status as show_status FROM tv_episodes outer_eps, tv_shows WHERE season != 0 AND showid NOT IN (%s)'
            % ','.join(['?'] * len(done_show_list))
            + ' AND tv_shows.indexer_id = outer_eps.showid AND airdate = (SELECT airdate FROM tv_episodes inner_eps WHERE inner_eps.season != 0 AND inner_eps.showid = outer_eps.showid AND inner_eps.airdate >= ? ORDER BY inner_eps.airdate ASC LIMIT 1) AND outer_eps.status NOT IN (%s)'
            % ','.join(['?'] * len(Quality.DOWNLOADED + Quality.SNATCHED)),
            done_show_list + [next_week] + Quality.DOWNLOADED + Quality.SNATCHED)

        sql_results += myDB.select(
            'SELECT *, tv_shows.status as show_status FROM tv_episodes, tv_shows WHERE season != 0 AND tv_shows.indexer_id = tv_episodes.showid AND airdate <= ? AND airdate >= ? AND tv_episodes.status = ? AND tv_episodes.status NOT IN (%s)'
            % ','.join(['?'] * len(qualities)),
            [tomorrow, recently, WANTED] + qualities)

        sql_results = list(set(sql_results))

        # make a dict out of the sql results
        sql_results = [dict(row) for row in sql_results
                       if Quality.splitCompositeStatus(helpers.tryInt(row['status']))[0] not in
                       [DOWNLOADED, SNATCHED, SNATCHED_PROPER, SNATCHED_BEST, ARCHIVED, IGNORED]]

        # multi dimension sort
        sorts = {
            'network': (lambda a, b: cmp(
                (a['data_network'], a['localtime'], a['data_show_name'], a['season'], a['episode']),
                (b['data_network'], b['localtime'], b['data_show_name'], b['season'], b['episode']))),
            'show': (lambda a, b: cmp(
                (a['data_show_name'], a['localtime'], a['season'], a['episode']),
                (b['data_show_name'], b['localtime'], b['season'], b['episode']))),
            'time': (lambda a, b: cmp(
                (a['localtime'], a['data_show_name'], a['season'], a['episode']),
                (b['localtime'], b['data_show_name'], b['season'], b['episode'])))
        }

        def value_maybe_article(value=None):
            if None is value:
                return ''
            return (remove_article(value.lower()), value.lower())[sickbeard.SORT_ARTICLE]

        # add localtime to the dict
        for index, item in enumerate(sql_results):
            sql_results[index]['localtime'] = sbdatetime.sbdatetime.convert_to_setting(network_timezones.parse_date_time(item['airdate'],
                                                                                       item['airs'], item['network']))
            sql_results[index]['data_show_name'] = value_maybe_article(item['show_name'])
            sql_results[index]['data_network'] = value_maybe_article(item['network'])

        sql_results.sort(sorts[sickbeard.EPISODE_VIEW_SORT])

        t = PageTemplate(headers=self.request.headers, file='episodeView.tmpl')
        t.next_week = datetime.datetime.combine(next_week_dt, datetime.time(tzinfo=network_timezones.sb_timezone))
        t.today = datetime.datetime.now(network_timezones.sb_timezone)
        t.sql_results = sql_results

        # Allow local overriding of layout parameter
        if layout and layout in ('banner', 'daybyday', 'list', 'poster'):
            t.layout = layout
        else:
            t.layout = sickbeard.EPISODE_VIEW_LAYOUT

        return t.respond()

    def _genericMessage(self, subject, message):
        t = PageTemplate(headers=self.request.headers, file='genericMessage.tmpl')
        t.submenu = self.HomeMenu()
        t.subject = subject
        t.message = message
        return t.respond()


class Home(MainHandler):
    def HomeMenu(self):
        return [
            {'title': 'Add Shows', 'path': 'home/addShows/', },
            {'title': 'Manual Post-Processing', 'path': 'home/postprocess/'},
            {'title': 'Update Emby', 'path': 'home/updateEMBY/', 'requires': self.haveEMBY},
            {'title': 'Update Kodi', 'path': 'home/updateKODI/', 'requires': self.haveKODI},
            {'title': 'Update XBMC', 'path': 'home/updateXBMC/', 'requires': self.haveXBMC},
            {'title': 'Update Plex', 'path': 'home/updatePLEX/', 'requires': self.havePLEX},
            {'title': 'Restart', 'path': 'home/restart/?pid=' + str(sickbeard.PID), 'confirm': True},
            {'title': 'Shutdown', 'path': 'home/shutdown/?pid=' + str(sickbeard.PID), 'confirm': True},
        ]

    @staticmethod
    def haveEMBY():
        return sickbeard.USE_EMBY

    @staticmethod
    def haveKODI():
        return sickbeard.USE_KODI

    @staticmethod
    def haveXBMC():
        return sickbeard.USE_XBMC and sickbeard.XBMC_UPDATE_LIBRARY

    @staticmethod
    def havePLEX():
        return sickbeard.USE_PLEX and sickbeard.PLEX_UPDATE_LIBRARY

    @staticmethod
    def _getEpisode(show, season=None, episode=None, absolute=None):
        if show is None:
            return 'Invalid show parameters'

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            return 'Invalid show paramaters'

        if absolute:
            epObj = showObj.getEpisode(absolute_number=int(absolute))
        elif None is not season and None is not episode:
            epObj = showObj.getEpisode(int(season), int(episode))
        else:
            return 'Invalid paramaters'

        if epObj is None:
            return "Episode couldn't be retrieved"

        return epObj

    def index(self, *args, **kwargs):
        if 'episodes' == sickbeard.DEFAULT_HOME:
            self.redirect('/episodeView/')
        elif 'history' == sickbeard.DEFAULT_HOME:
            self.redirect('/history/')
        else:
            self.redirect('/home/showlistView/')

    def showlistView(self):
        t = PageTemplate(headers=self.request.headers, file='home.tmpl')
        t.showlists = []
        index = 0
        if sickbeard.SHOWLIST_TAGVIEW == 'custom':
            for name in sickbeard.SHOW_TAGS:
                results = filter(lambda x: x.tag == name, sickbeard.showList)
                if results:
                    t.showlists.append(['container%s' % index, name, results])
                index += 1
        elif sickbeard.SHOWLIST_TAGVIEW == 'anime':
            show_results = filter(lambda x: not x.anime, sickbeard.showList)
            anime_results = filter(lambda x: x.anime, sickbeard.showList)
            if show_results:
                t.showlists.append(['container%s' % index, 'Show List', show_results])
                index += 1
            if anime_results:
                t.showlists.append(['container%s' % index, 'Anime List', anime_results])

        if 0 == len(t.showlists):
            t.showlists.append(['container0', 'Show List', sickbeard.showList])

        if 'simple' != sickbeard.HOME_LAYOUT:
            t.network_images = {}
            networks = {}
            images_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', 'network')
            for item in sickbeard.showList:
                network_name = 'nonetwork' if None is item.network else item.network.replace(u'\u00C9', 'e').lower()
                if network_name not in networks:
                    filename = u'%s.png' % network_name
                    if not ek.ek(os.path.isfile, ek.ek(os.path.join, images_path, filename)):
                        filename = u'%s.png' % re.sub(r'(?m)(.*)\s+\(\w{2}\)$', r'\1', network_name)
                        if not ek.ek(os.path.isfile, ek.ek(os.path.join, images_path, filename)):
                            filename = u'nonetwork.png'
                    networks.setdefault(network_name, filename)
                t.network_images.setdefault(item.indexerid, networks[network_name])

        t.submenu = self.HomeMenu()
        t.layout = sickbeard.HOME_LAYOUT

        # Get all show snatched / downloaded / next air date stats
        myDB = db.DBConnection()
        today = datetime.date.today().toordinal()
        status_quality = ','.join([str(x) for x in Quality.SNATCHED + Quality.SNATCHED_PROPER])
        status_download = ','.join([str(x) for x in Quality.DOWNLOADED + [ARCHIVED]])
        status_total = '%s, %s, %s' % (SKIPPED, WANTED, FAILED)

        sql_statement = 'SELECT showid, '
        sql_statement += '(SELECT COUNT(*) FROM tv_episodes WHERE showid=tv_eps.showid AND season > 0 AND episode > 0 AND airdate > 1 AND status IN (%s)) AS ep_snatched, '
        sql_statement += '(SELECT COUNT(*) FROM tv_episodes WHERE showid=tv_eps.showid AND season > 0 AND episode > 0 AND airdate > 1 AND status IN (%s)) AS ep_downloaded, '
        sql_statement += '(SELECT COUNT(*) FROM tv_episodes WHERE showid=tv_eps.showid AND season > 0 AND episode > 0 AND airdate > 1 AND ((airdate <= %s AND (status IN (%s))) OR (status IN (%s)) OR (status IN (%s)))) AS ep_total, '
        sql_statement += '(SELECT airdate FROM tv_episodes WHERE showid=tv_eps.showid AND airdate >= %s AND (status = %s  OR status = %s) ORDER BY airdate ASC LIMIT 1) AS ep_airs_next '
        sql_statement += ' FROM tv_episodes tv_eps GROUP BY showid'
        sql_result = myDB.select(sql_statement % (status_quality, status_download, today, status_total, status_quality, status_download, today, UNAIRED, WANTED))

        t.show_stat = {}

        for cur_result in sql_result:
            t.show_stat[cur_result['showid']] = cur_result

        return t.respond()

    def test_sabnzbd(self, host=None, username=None, password=None, apikey=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_url(host)
        connection, access_msg = sab.access_method(host)
        if connection:
            if None is not password and set('*') == set(password):
                password = sickbeard.SAB_PASSWORD
            if None is not apikey and starify(apikey, True):
                apikey = sickbeard.SAB_APIKEY

            authed, auth_msg = sab.test_authentication(host, username, password, apikey)
            if authed:
                return u'Success. Connected %s authentication' % \
                       ('using %s' % access_msg, 'with no')['None' == auth_msg.lower()]
            return u'Authentication failed. %s' % auth_msg
        return u'Unable to connect to host'

    def test_nzbget(self, host=None, use_https=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_url(host)
        if None is not password and set('*') == set(password):
            password = sickbeard.NZBGET_PASSWORD

        authed, auth_msg, void = nzbget.test_nzbget(host, bool(config.checkbox_to_value(use_https)), username, password)
        return auth_msg

    def test_torrent(self, torrent_method=None, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_url(host)
        if None is not password and set('*') == set(password):
            password = sickbeard.TORRENT_PASSWORD

        client = clients.get_client_instance(torrent_method)

        connection, accesMsg = client(host, username, password).test_authentication()

        return accesMsg

    def testGrowl(self, host=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host, default_port=23053)
        if None is not password and set('*') == set(password):
            password = sickbeard.GROWL_PASSWORD

        result = notifiers.growl_notifier.test_notify(host, password)
        if password is None or password == '':
            pw_append = ''
        else:
            pw_append = ' with password: ' + password

        if result:
            return 'Registered and Tested growl successfully ' + urllib.unquote_plus(host) + pw_append
        else:
            return 'Registration and Testing of growl failed ' + urllib.unquote_plus(host) + pw_append

    def testProwl(self, prowl_api=None, prowl_priority=0):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not prowl_api and starify(prowl_api, True):
            prowl_api = sickbeard.PROWL_API

        result = notifiers.prowl_notifier.test_notify(prowl_api, prowl_priority)
        if result:
            return 'Test prowl notice sent successfully'
        else:
            return 'Test prowl notice failed'

    def testBoxcar2(self, accesstoken=None, sound=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not accesstoken and starify(accesstoken, True):
            accesstoken = sickbeard.BOXCAR2_ACCESSTOKEN

        result = notifiers.boxcar2_notifier.test_notify(accesstoken, sound)
        if result:
            return 'Boxcar2 notification succeeded. Check your Boxcar2 clients to make sure it worked'
        else:
            return 'Error sending Boxcar2 notification'

    def testPushover(self, userKey=None, apiKey=None, priority=None, device=None, sound=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not userKey and starify(userKey, True):
            userKey = sickbeard.PUSHOVER_USERKEY

        if None is not apiKey and starify(apiKey, True):
            apiKey = sickbeard.PUSHOVER_APIKEY

        result = notifiers.pushover_notifier.test_notify(userKey, apiKey, priority, device, sound)
        if result:
            return 'Pushover notification succeeded. Check your Pushover clients to make sure it worked'
        else:
            return 'Error sending Pushover notification'

    def getPushoverDevices(self, userKey=None, apiKey=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not userKey and starify(userKey, True):
            userKey = sickbeard.PUSHOVER_USERKEY

        if None is not apiKey and starify(apiKey, True):
            apiKey = sickbeard.PUSHOVER_APIKEY

        result = notifiers.pushover_notifier.get_devices(userKey, apiKey)
        if result:
            return result
        else:
            return "{}"

    def twitterStep1(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.twitter_notifier._get_authorization()

    def twitterStep2(self, key):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        result = notifiers.twitter_notifier._get_credentials(key)
        logger.log(u'result: ' + str(result))
        if result:
            return 'Key verification successful'
        else:
            return 'Unable to verify key'

    def testTwitter(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        result = notifiers.twitter_notifier.test_notify()
        if result:
            return 'Tweet successful, check your twitter to make sure it worked'
        else:
            return 'Error sending tweet'

    @staticmethod
    def discover_emby():
        return notifiers.emby_notifier.discover_server()

    def testEMBY(self, host=None, apikey=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host)
        if not hosts:
            return 'Fail: At least one invalid host'

        total_success, cur_message = notifiers.emby_notifier.test_notify(hosts, apikey)
        return (cur_message, u'Success. All Emby hosts tested.')[total_success]

    def testKODI(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host)
        if not hosts:
            return 'Fail: At least one invalid host'

        if None is not password and set('*') == set(password):
            password = sickbeard.KODI_PASSWORD

        total_success, cur_message = notifiers.kodi_notifier.test_notify(hosts, username, password)
        return (cur_message, u'Success. All Kodi hosts tested.')[total_success]

    def testXBMC(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_hosts(host)
        if None is not password and set('*') == set(password):
            password = sickbeard.XBMC_PASSWORD

        finalResult = ''
        for curHost in [x.strip() for x in host.split(',')]:
            curResult = notifiers.xbmc_notifier.test_notify(urllib.unquote_plus(curHost), username, password)
            if len(curResult.split(':')) > 2 and 'OK' in curResult.split(':')[2]:
                finalResult += 'Test XBMC notice sent successfully to ' + urllib.unquote_plus(curHost)
            else:
                finalResult += 'Test XBMC notice failed to ' + urllib.unquote_plus(curHost)
            finalResult += "<br />\n"

        return finalResult

    def testPMC(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not password and set('*') == set(password):
            password = sickbeard.PLEX_PASSWORD

        finalResult = ''
        for curHost in [x.strip() for x in host.split(',')]:
            curResult = notifiers.plex_notifier.test_notify(urllib.unquote_plus(curHost), username, password)
            if len(curResult.split(':')) > 2 and 'OK' in curResult.split(':')[2]:
                finalResult += 'Successful test notice sent to Plex client ... ' + urllib.unquote_plus(curHost)
            else:
                finalResult += 'Test failed for Plex client ... ' + urllib.unquote_plus(curHost)
            finalResult += '<br />' + '\n'

        ui.notifications.message('Tested Plex client(s): ', urllib.unquote_plus(host.replace(',', ', ')))

        return finalResult

    def testPMS(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not password and set('*') == set(password):
            password = sickbeard.PLEX_PASSWORD

        cur_result = notifiers.plex_notifier.test_notify(urllib.unquote_plus(host), username, password, server=True)
        final_result = (('Test result for', 'Successful test of')['Fail' not in cur_result]
                        + ' Plex server(s) ... %s<br />\n' % cur_result)

        ui.notifications.message('Tested Plex Media Server host(s): ', urllib.unquote_plus(host.replace(',', ', ')))

        return final_result

    def testLibnotify(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if notifiers.libnotify_notifier.test_notify():
            return 'Tried sending desktop notification via libnotify'
        else:
            return notifiers.libnotify.diagnose()

    def testNMJ(self, host=None, database=None, mount=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        result = notifiers.nmj_notifier.test_notify(urllib.unquote_plus(host), database, mount)
        if result:
            return 'Successfully started the scan update'
        else:
            return 'Test failed to start the scan update'

    def settingsNMJ(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        result = notifiers.nmj_notifier.notify_settings(urllib.unquote_plus(host))
        if result:
            return '{"message": "Got settings from %(host)s", "database": "%(database)s", "mount": "%(mount)s"}' % {
                "host": host, "database": sickbeard.NMJ_DATABASE, "mount": sickbeard.NMJ_MOUNT}
        else:
            return '{"message": "Failed! Make sure your Popcorn is on and NMJ is running. (see Log & Errors -> Debug for detailed info)", "database": "", "mount": ""}'

    def testNMJv2(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        result = notifiers.nmjv2_notifier.test_notify(urllib.unquote_plus(host))
        if result:
            return 'Test notice sent successfully to ' + urllib.unquote_plus(host)
        else:
            return 'Test notice failed to ' + urllib.unquote_plus(host)

    def settingsNMJv2(self, host=None, dbloc=None, instance=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        result = notifiers.nmjv2_notifier.notify_settings(urllib.unquote_plus(host), dbloc, instance)
        if result:
            return '{"message": "NMJ Database found at: %(host)s", "database": "%(database)s"}' % {"host": host,
                                                                                                   "database": sickbeard.NMJv2_DATABASE}
        else:
            return '{"message": "Unable to find NMJ Database at location: %(dbloc)s. Is the right location selected and PCH running?", "database": ""}' % {
                "dbloc": dbloc}

    def trakt_authenticate(self, pin=None, account=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is pin:
            return json.dumps({'result': 'Fail', 'error_message': 'Trakt PIN required for authentication'})

        if account and 'new' == account:
            account = None

        acc = None
        if account:
            acc = sickbeard.helpers.tryInt(account, -1)
            if 0 < acc and acc not in sickbeard.TRAKT_ACCOUNTS:
                return json.dumps({'result': 'Fail', 'error_message': 'Fail: cannot update non-existing account'})

        json_fail_auth = json.dumps({'result': 'Fail', 'error_message': 'Trakt NOT authenticated'})
        try:
            resp = TraktAPI().trakt_token(pin, account=acc)
        except TraktAuthException:
            return json_fail_auth
        if not account and isinstance(resp, bool) and not resp:
            return json_fail_auth

        if not sickbeard.USE_TRAKT:
            sickbeard.USE_TRAKT = True
            sickbeard.save_config()
        pick = resp if not account else acc
        return json.dumps({'result': 'Success',
                           'account_id': sickbeard.TRAKT_ACCOUNTS[pick].account_id,
                           'account_name': sickbeard.TRAKT_ACCOUNTS[pick].name})

    def trakt_delete(self, accountid=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if accountid:
            aid = sickbeard.helpers.tryInt(accountid, None)
            if None is not aid:
                if aid in sickbeard.TRAKT_ACCOUNTS:
                    account = {'result': 'Success',
                               'account_id': sickbeard.TRAKT_ACCOUNTS[aid].account_id,
                               'account_name': sickbeard.TRAKT_ACCOUNTS[aid].name}
                    if TraktAPI.delete_account(aid):
                        trakt_collection_remove_account(aid)
                        account['num_accounts'] = len(sickbeard.TRAKT_ACCOUNTS)
                        return json.dumps(account)

                return json.dumps({'result': 'Not found: Account to delete'})
        return json.dumps({'result': 'Not found: Invalid account id'})

    def loadShowNotifyLists(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        my_db = db.DBConnection()
        rows = my_db.select('SELECT indexer_id, indexer, notify_list FROM tv_shows ' +
                            'WHERE notify_list NOTNULL and notify_list != ""')
        notify_lists = {}
        for r in filter(lambda x: x['notify_list'].strip(), rows):
            notify_lists['%s_%s' % (r['indexer'], r['indexer_id'])] = r['notify_list']

        sorted_show_lists = self.sorted_show_lists()
        response = []
        for current_group in sorted_show_lists:
            data = []
            for current_show in current_group[1]:
                uid = '%s_%s' % (current_show.indexer, current_show.indexerid)
                data.append({'id': uid, 'name': current_show.name,
                             'list': '' if uid not in notify_lists else notify_lists[uid]})
            if data:
                response.append({current_group[0]: data})

        return json.dumps(response)

    @staticmethod
    def save_show_email(show=None, emails=None):
        # self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        my_db = db.DBConnection()
        success = False
        parse = show.split('_')
        if 1 < len(parse) and \
                my_db.action('UPDATE tv_shows SET notify_list = ? WHERE indexer = ? AND indexer_id = ?',
                             [emails, parse[0], parse[1]]):
            success = True
        return json.dumps({'id': show, 'success': success})

    def testEmail(self, host=None, port=None, smtp_from=None, use_tls=None, user=None, pwd=None, to=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not pwd and set('*') == set(pwd):
            pwd = sickbeard.EMAIL_PASSWORD
        host = config.clean_host(host)

        if notifiers.email_notifier.test_notify(host, port, smtp_from, use_tls, user, pwd, to):
            return 'Success. Test email sent. Check inbox.'
        return 'ERROR: %s' % notifiers.email_notifier.last_err

    def testNMA(self, nma_api=None, nma_priority=0):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not nma_api and starify(nma_api, True):
            nma_api = sickbeard.NMA_API

        result = notifiers.nma_notifier.test_notify(nma_api, nma_priority)
        if result:
            return 'Test NMA notice sent successfully'
        else:
            return 'Test NMA notice failed'

    def testPushalot(self, authorizationToken=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not authorizationToken and starify(authorizationToken, True):
            authorizationToken = sickbeard.PUSHALOT_AUTHORIZATIONTOKEN

        result = notifiers.pushalot_notifier.test_notify(authorizationToken)
        if result:
            return 'Pushalot notification succeeded. Check your Pushalot clients to make sure it worked'
        else:
            return 'Error sending Pushalot notification'

    def testPushbullet(self, accessToken=None, device_iden=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not accessToken and starify(accessToken, True):
            accessToken = sickbeard.PUSHBULLET_ACCESS_TOKEN

        return notifiers.pushbullet_notifier.test_notify(accessToken, device_iden)

    def getPushbulletDevices(self, accessToken=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not accessToken and starify(accessToken, True):
            accessToken = sickbeard.PUSHBULLET_ACCESS_TOKEN

        return notifiers.pushbullet_notifier.get_devices(accessToken)

    def viewchanges(self):

        t = PageTemplate(headers=self.request.headers, file='viewchanges.tmpl')

        t.changelist = [{'type': 'rel', 'ver': '', 'date': 'Nothing to display at this time'}]
        url = 'https://raw.githubusercontent.com/wiki/SickGear/SickGear/sickgear/CHANGES.md'
        response = helpers.getURL(url)
        if not response:
            return t.respond()

        data = response.replace('\xef\xbb\xbf', '').splitlines()

        output, change, max_rel = [], {}, 5
        for line in data:
            if not line.strip():
                continue
            if line.startswith('  '):
                change_parts = re.findall('^[\W]+(.*)$', line)
                change['text'] += change_parts and (' %s' % change_parts[0].strip()) or ''
            else:
                if change:
                    output.append(change)
                    change = None
                if line.startswith('* '):
                    change_parts = re.findall(r'^[\*\W]+(Add|Change|Fix|Port|Remove|Update)\W(.*)', line)
                    change = change_parts and {'type': change_parts[0][0], 'text': change_parts[0][1].strip()} or {}
                elif not max_rel:
                    break
                elif line.startswith('### '):
                    rel_data = re.findall(r'(?im)^###\W*([^\s]+)\W\(([^\)]+)\)', line)
                    rel_data and output.append({'type': 'rel', 'ver': rel_data[0][0], 'date': rel_data[0][1]})
                    max_rel -= 1
                elif line.startswith('# '):
                    max_data = re.findall(r'^#\W*([\d]+)\W*$', line)
                    max_rel = max_data and helpers.tryInt(max_data[0], None) or 5
        if change:
            output.append(change)

        t.changelist = output
        return t.respond()

    def shutdown(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        sickbeard.events.put(sickbeard.events.SystemEvent.SHUTDOWN)

        title = 'Shutting down'
        message = 'SickGear is shutting down...'

        return self._genericMessage(title, message)

    def restart(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        t = PageTemplate(headers=self.request.headers, file='restart.tmpl')
        t.submenu = self.HomeMenu()

        # restart
        sickbeard.events.put(sickbeard.events.SystemEvent.RESTART)

        return t.respond()

    def update(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        updated = sickbeard.versionCheckScheduler.action.update()  # @UndefinedVariable
        if updated:
            # do a hard restart
            sickbeard.events.put(sickbeard.events.SystemEvent.RESTART)

            t = PageTemplate(headers=self.request.headers, file='restart_bare.tmpl')
            return t.respond()
        else:
            return self._genericMessage('Update Failed',
                                        "Update wasn't successful, not restarting. Check your log for more information.")

    def branchCheckout(self, branch):
        sickbeard.BRANCH = branch
        ui.notifications.message('Checking out branch: ', branch)
        return self.update(sickbeard.PID)

    def pullRequestCheckout(self, branch):
        pull_request = branch
        branch = branch.split(':')[1]
        fetched = sickbeard.versionCheckScheduler.action.fetch(pull_request)
        if fetched:
            sickbeard.BRANCH = branch
            ui.notifications.message('Checking out branch: ', branch)
            return self.update(sickbeard.PID)
        else:
            self.redirect('/home/')

    def displayShow(self, show=None):

        if show is None:
            return self._genericMessage('Error', 'Invalid show ID')
        else:
            showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

            if showObj is None:
                return self._genericMessage('Error', 'Show not in show list')

        myDB = db.DBConnection()
        seasonResults = myDB.select(
            'SELECT DISTINCT season FROM tv_episodes WHERE showid = ? ORDER BY season desc',
            [showObj.indexerid]
        )

        sqlResults = myDB.select(
            'SELECT * FROM tv_episodes WHERE showid = ? ORDER BY season DESC, episode DESC',
            [showObj.indexerid]
        )

        t = PageTemplate(headers=self.request.headers, file='displayShow.tmpl')
        t.submenu = [{'title': 'Edit', 'path': 'home/editShow?show=%d' % showObj.indexerid}]

        try:
            t.showLoc = (showObj.location, True)
        except sickbeard.exceptions.ShowDirNotFoundException:
            t.showLoc = (showObj._location, False)

        show_message = ''

        if sickbeard.showQueueScheduler.action.isBeingAdded(showObj):  # @UndefinedVariable
            show_message = 'This show is in the process of being downloaded - the info below is incomplete.'

        elif sickbeard.showQueueScheduler.action.isBeingUpdated(showObj):  # @UndefinedVariable
            show_message = 'The information on this page is in the process of being updated.'

        elif sickbeard.showQueueScheduler.action.isBeingRefreshed(showObj):  # @UndefinedVariable
            show_message = 'The episodes below are currently being refreshed from disk'

        elif sickbeard.showQueueScheduler.action.isBeingSubtitled(showObj):  # @UndefinedVariable
            show_message = 'Currently downloading subtitles for this show'

        elif sickbeard.showQueueScheduler.action.isInRefreshQueue(showObj):  # @UndefinedVariable
            show_message = 'This show is queued to be refreshed.'

        elif sickbeard.showQueueScheduler.action.isInUpdateQueue(showObj):  # @UndefinedVariable
            show_message = 'This show is queued and awaiting an update.'

        elif sickbeard.showQueueScheduler.action.isInSubtitleQueue(showObj):  # @UndefinedVariable
            show_message = 'This show is queued and awaiting subtitles download.'

        if not sickbeard.showQueueScheduler.action.isBeingAdded(showObj):  # @UndefinedVariable
            if not sickbeard.showQueueScheduler.action.isBeingUpdated(showObj):  # @UndefinedVariable
                t.submenu.append(
                    {'title': 'Remove', 'path': 'home/deleteShow?show=%d' % showObj.indexerid, 'confirm': True})
                t.submenu.append({'title': 'Re-scan files', 'path': 'home/refreshShow?show=%d' % showObj.indexerid})
                t.submenu.append(
                    {'title': 'Force Full Update', 'path': 'home/updateShow?show=%d&amp;force=1&amp;web=1' % showObj.indexerid})
                t.submenu.append({'title': 'Update show in Emby',
                                  'path': 'home/updateEMBY%s' %
                                          (INDEXER_TVDB == showObj.indexer and ('?show=%s' % showObj.indexerid) or '/'),
                                  'requires': self.haveEMBY})
                t.submenu.append({'title': 'Update show in Kodi',
                                  'path': 'home/updateKODI?showName=%s' % urllib.quote_plus(
                                  showObj.name.encode('utf-8')), 'requires': self.haveKODI})
                t.submenu.append({'title': 'Update show in XBMC',
                                  'path': 'home/updateXBMC?showName=%s' % urllib.quote_plus(
                                  showObj.name.encode('utf-8')), 'requires': self.haveXBMC})
                t.submenu.append({'title': 'Media Renamer', 'path': 'home/testRename?show=%d' % showObj.indexerid})
                if sickbeard.USE_SUBTITLES and not sickbeard.showQueueScheduler.action.isBeingSubtitled(
                        showObj) and showObj.subtitles:
                    t.submenu.append(
                        {'title': 'Download Subtitles', 'path': 'home/subtitleShow?show=%d' % showObj.indexerid})

        t.show = showObj
        t.sqlResults = sqlResults
        t.seasonResults = seasonResults
        t.show_message = show_message

        epCounts = {}
        epCats = {}
        epCounts[Overview.SKIPPED] = 0
        epCounts[Overview.WANTED] = 0
        epCounts[Overview.QUAL] = 0
        epCounts[Overview.GOOD] = 0
        epCounts[Overview.UNAIRED] = 0
        epCounts[Overview.SNATCHED] = 0
        epCounts['videos'] = {}
        epCounts['archived'] = {}
        epCounts['totals'] = {}
        highest_season = 0
        latest_season = 0

        for curResult in sqlResults:
            curEpCat = showObj.getOverview(int(curResult['status']))
            if curEpCat:
                epCats[str(curResult['season']) + 'x' + str(curResult['episode'])] = curEpCat
                epCounts[curEpCat] += 1
            if '' != curResult['location']:
                if curResult['season'] not in epCounts['videos']:
                    epCounts['videos'][curResult['season']] = 1
                else:
                    epCounts['videos'][curResult['season']] += 1
            if curResult['season'] not in epCounts['totals']:
                epCounts['totals'][curResult['season']] = 1
            else:
                epCounts['totals'][curResult['season']] += 1
            if ARCHIVED == curResult['status']:
                if curResult['season'] not in epCounts['archived']:
                    epCounts['archived'][curResult['season']] = 1
                else:
                    epCounts['archived'][curResult['season']] += 1
            if highest_season < curResult['season'] and 1000 < curResult['airdate'] and UNAIRED < curResult['status']:
                highest_season = curResult['season']

        if 0 < len(epCounts['totals']):
            latest_season = int(sorted(epCounts['totals'])[-1::][0])

        display_seasons = []
        if 1 < highest_season:
            display_seasons += [1]
        display_seasons += [highest_season]

        t.sortedShowLists = self.sorted_show_lists()

        tvshows = []
        tvshow_names = []
        cur_sel = None
        for tvshow_types in t.sortedShowLists:
            for tvshow in tvshow_types[1]:
                tvshows.append(tvshow.indexerid)
                tvshow_names.append(tvshow.name)
                if showObj.indexerid == tvshow.indexerid:
                    cur_sel = len(tvshow_names)
        t.tvshow_id_csv = ','.join(str(x) for x in tvshows)

        last_item = len(tvshow_names)
        t.prev_title = ''
        t.next_title = ''
        if cur_sel:
            t.prev_title = 'Prev show, %s' % tvshow_names[(cur_sel - 2, last_item - 1)[1 == cur_sel]]
            t.next_title = 'Next show, %s' % tvshow_names[(cur_sel, 0)[last_item == cur_sel]]

        t.bwl = None
        if showObj.is_anime:
            t.bwl = showObj.release_groups

        t.epCounts = epCounts
        t.epCats = epCats
        t.display_seasons = display_seasons
        t.latest_season = latest_season

        showObj.exceptions = scene_exceptions.get_scene_exceptions(showObj.indexerid)

        indexerid = int(showObj.indexerid)
        indexer = int(showObj.indexer)
        t.all_scene_exceptions = showObj.exceptions
        t.scene_numbering = get_scene_numbering_for_show(indexerid, indexer)
        t.xem_numbering = get_xem_numbering_for_show(indexerid, indexer)
        t.scene_absolute_numbering = get_scene_absolute_numbering_for_show(indexerid, indexer)
        t.xem_absolute_numbering = get_xem_absolute_numbering_for_show(indexerid, indexer)

        return t.respond()

    @staticmethod
    def sorted_show_lists():

        def titler(x):
            return (remove_article(x), x)[not x or sickbeard.SORT_ARTICLE]

        if 'custom' == sickbeard.SHOWLIST_TAGVIEW:
            sorted_show_lists = []
            for tag in sickbeard.SHOW_TAGS:
                results = filter(lambda x: x.tag == tag, sickbeard.showList)
                if results:
                    sorted_show_lists.append([tag, sorted(results, lambda x, y: cmp(titler(x.name), titler(y.name)))])
        elif 'anime' == sickbeard.SHOWLIST_TAGVIEW:
            shows = []
            anime = []
            for show in sickbeard.showList:
                if show.is_anime:
                    anime.append(show)
                else:
                    shows.append(show)
            sorted_show_lists = [['Shows', sorted(shows, lambda x, y: cmp(titler(x.name), titler(y.name)))],
                                 ['Anime', sorted(anime, lambda x, y: cmp(titler(x.name), titler(y.name)))]]

        else:
            sorted_show_lists = [
                ['Show List', sorted(sickbeard.showList, lambda x, y: cmp(titler(x.name), titler(y.name)))]]

        return sorted_show_lists

    def plotDetails(self, show, season, episode):
        myDB = db.DBConnection()
        result = myDB.select(
            'SELECT description FROM tv_episodes WHERE showid = ? AND season = ? AND episode = ?',
            (int(show), int(season), int(episode)))
        return result[0]['description'] if result else 'Episode not found.'

    def sceneExceptions(self, show):
        exceptionsList = sickbeard.scene_exceptions.get_all_scene_exceptions(show)
        if not exceptionsList:
            return 'No scene exceptions'

        out = []
        for season, names in iter(sorted(iteritems(exceptionsList))):
            if season == -1:
                season = '*'
            out.append('S' + str(season) + ': ' + ', '.join(names))
        return '<br/>'.join(out)

    def switchIndexer(self, indexerid, indexer, mindexerid, mindexer, set_pause=False, mark_wanted=False):
        indexer = helpers.tryInt(indexer)
        indexerid = helpers.tryInt(indexerid)
        mindexer = helpers.tryInt(mindexer)
        mindexerid = helpers.tryInt(mindexerid)
        show_obj = sickbeard.helpers.find_show_by_id(
            sickbeard.showList, {indexer: indexerid}, no_mapped_ids=True)
        try:
            m_show_obj = sickbeard.helpers.find_show_by_id(
                sickbeard.showList, {mindexer: mindexerid}, no_mapped_ids=False)
        except exceptions.MultipleShowObjectsException:
            msg = 'Duplicate shows in DB'
            ui.notifications.message('Indexer Switch', 'Error: ' + msg)
            return {'Error': msg}
        if not show_obj or (m_show_obj and show_obj is not m_show_obj):
            msg = 'Unable to find the specified show'
            ui.notifications.message('Indexer Switch', 'Error: ' + msg)
            return {'Error': msg}

        with show_obj.lock:
            show_obj.indexer = mindexer
            show_obj.indexerid = mindexerid
            pausestatus_after = None
            if not set_pause:
                show_obj.paused = False
                if not mark_wanted:
                    show_obj.paused = True
                    pausestatus_after = False
            elif not show_obj.paused:
                show_obj.paused = True

        show_obj.switchIndexer(indexer, indexerid, pausestatus_after=pausestatus_after)

        ui.notifications.message('Indexer Switch', 'Finished after updating the show')
        return {'Success': 'Switched to new TV info source'}

    def saveMapping(self, show, **kwargs):
        show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))
        response = {}
        if not show_obj:
            return json.dumps(response)
        new_ids = {}
        save_map = []
        with show_obj.lock:
            for k, v in kwargs.iteritems():
                t = re.search(r'mid-(\d+)', k)
                if t:
                    i = helpers.tryInt(v, None)
                    if None is not i:
                        new_ids.setdefault(helpers.tryInt(t.group(1)), {'id': 0, 'status': MapStatus.NONE,
                                                                        'date': datetime.date.fromordinal(1)})['id'] = i
                else:
                    t = re.search(r'lockid-(\d+)', k)
                    if t:
                        new_ids.setdefault(helpers.tryInt(t.group(1)), {'id': 0, 'status': MapStatus.NONE, 'date':
                            datetime.date.fromordinal(1)})['status'] = (MapStatus.NONE, MapStatus.NO_AUTOMATIC_CHANGE)[
                            'true' == v]
            if new_ids:
                for k, v in new_ids.iteritems():
                    if None is v.get('id') or None is v.get('status'):
                        continue
                    if (show_obj.ids.get(k, {'id': 0}).get('id') != v.get('id') or
                            (MapStatus.NO_AUTOMATIC_CHANGE == v.get('status') and
                             MapStatus.NO_AUTOMATIC_CHANGE != show_obj.ids.get(
                                 k, {'status': MapStatus.NONE}).get('status')) or
                            (MapStatus.NO_AUTOMATIC_CHANGE != v.get('status') and
                             MapStatus.NO_AUTOMATIC_CHANGE == show_obj.ids.get(
                                 k, {'status': MapStatus.NONE}).get('status'))):
                        show_obj.ids[k]['id'] = (0, v['id'])[v['id'] >= 0]
                        show_obj.ids[k]['status'] = (MapStatus.NOT_FOUND, v['status'])[v['id'] != 0]
                        save_map.append(k)
            if len(save_map):
                save_mapping(show_obj, save_map=save_map)
                ui.notifications.message('Mappings saved')
            else:
                ui.notifications.message('Mappings unchanged, not saving.')

        master_ids = [show] + [kwargs.get(x) for x in 'indexer', 'mindexerid', 'mindexer']
        if all([helpers.tryInt(x) > 0 for x in master_ids]):
            master_ids += [bool(helpers.tryInt(kwargs.get(x))) for x in 'paused', 'markwanted']
            response = {'switch': self.switchIndexer(*master_ids), 'mid': kwargs['mindexerid']}

        response.update({
            'map': {k: {r: w for r, w in v.iteritems() if r != 'date'} for k, v in show_obj.ids.iteritems()}
        })
        return json.dumps(response)

    def forceMapping(self, show, **kwargs):
        show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))
        if not show_obj:
            return json.dumps({})
        save_map = []
        with show_obj.lock:
            for k, v in kwargs.iteritems():
                t = re.search(r'lockid-(\d+)', k)
                if t:
                    new_status = (MapStatus.NONE, MapStatus.NO_AUTOMATIC_CHANGE)['true' == v]
                    old_status = show_obj.ids.get(helpers.tryInt(t.group(1)), {'status': MapStatus.NONE})['status']
                    if ((MapStatus.NO_AUTOMATIC_CHANGE == new_status and
                         MapStatus.NO_AUTOMATIC_CHANGE != old_status) or
                        (MapStatus.NO_AUTOMATIC_CHANGE != new_status and
                         MapStatus.NO_AUTOMATIC_CHANGE == old_status)):
                        i = helpers.tryInt(t.group(1))
                        if 'mid-%s' % i in kwargs:
                            l = helpers.tryInt(kwargs['mid-%s' % i], None)
                            if None is not id and id >= 0:
                                show_obj.ids.setdefault(i, {'id': 0, 'status': MapStatus.NONE, 'date':
                                    datetime.date.fromordinal(1)})['id'] = l
                        show_obj.ids.setdefault(i, {'id': 0, 'status': MapStatus.NONE, 'date':
                            datetime.date.fromordinal(1)})['status'] = new_status
                        save_map.append(i)
            if len(save_map):
                save_mapping(show_obj, save_map=save_map)
            map_indexers_to_show(show_obj, force=True)
            ui.notifications.message('Mapping Reloaded')
        return json.dumps({k: {r: w for r, w in v.iteritems() if 'date' != r} for k, v in show_obj.ids.iteritems()})

    def editShow(self, show=None, location=None, anyQualities=[], bestQualities=[], exceptions_list=[],
                 flatten_folders=None, paused=None, directCall=False, air_by_date=None, sports=None, dvdorder=None,
                 indexerLang=None, subtitles=None, archive_firstmatch=None, rls_ignore_words=None,
                 rls_require_words=None, anime=None, blacklist=None, whitelist=None,
                 scene=None, tag=None, quality_preset=None, **kwargs):

        if show is None:
            errString = 'Invalid show ID: ' + str(show)
            if directCall:
                return [errString]
            else:
                return self._genericMessage('Error', errString)

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if not showObj:
            errString = 'Unable to find the specified show: ' + str(show)
            if directCall:
                return [errString]
            else:
                return self._genericMessage('Error', errString)

        showObj.exceptions = scene_exceptions.get_all_scene_exceptions(showObj.indexerid)

        if None is not quality_preset and int(quality_preset):
            bestQualities = []

        if not location and not anyQualities and not bestQualities and not flatten_folders:
            t = PageTemplate(headers=self.request.headers, file='editShow.tmpl')
            t.submenu = self.HomeMenu()

            myDB = db.DBConnection()
            t.seasonResults = myDB.select(
                'SELECT DISTINCT season FROM tv_episodes WHERE showid = ? ORDER BY season asc', [showObj.indexerid])

            if showObj.is_anime:
                if not showObj.release_groups:
                    showObj.release_groups = BlackAndWhiteList(showObj.indexerid)
                t.whitelist = showObj.release_groups.whitelist
                t.blacklist = showObj.release_groups.blacklist

                t.groups = []
                if helpers.set_up_anidb_connection():
                    try:
                        anime = adba.Anime(sickbeard.ADBA_CONNECTION, name=showObj.name)
                        t.groups = anime.get_groups()
                    except Exception as e:
                        t.groups.append(dict([('name', 'Fail:AniDB connect. Restart sg else check debug log'), ('rating', ''), ('range', '')]))
                else:
                    t.groups.append(dict([('name', 'Did not initialise AniDB. Check debug log if reqd.'), ('rating', ''), ('range', '')]))

            with showObj.lock:
                t.show = showObj
                t.show_has_scene_map = showObj.indexerid in sickbeard.scene_exceptions.xem_ids_list[showObj.indexer]

            return t.respond()

        flatten_folders = config.checkbox_to_value(flatten_folders)
        dvdorder = config.checkbox_to_value(dvdorder)
        archive_firstmatch = config.checkbox_to_value(archive_firstmatch)
        paused = config.checkbox_to_value(paused)
        air_by_date = config.checkbox_to_value(air_by_date)
        scene = config.checkbox_to_value(scene)
        sports = config.checkbox_to_value(sports)
        anime = config.checkbox_to_value(anime)
        subtitles = config.checkbox_to_value(subtitles)

        if indexerLang and indexerLang in sickbeard.indexerApi(showObj.indexer).indexer().config['valid_languages']:
            indexer_lang = indexerLang
        else:
            indexer_lang = showObj.lang

        # if we changed the language then kick off an update
        if indexer_lang == showObj.lang:
            do_update = False
        else:
            do_update = True

        if scene == showObj.scene and anime == showObj.anime:
            do_update_scene_numbering = False
        else:
            do_update_scene_numbering = True

        if type(anyQualities) != list:
            anyQualities = [anyQualities]

        if type(bestQualities) != list:
            bestQualities = [bestQualities]

        if type(exceptions_list) != list:
            exceptions_list = [exceptions_list]

        # If directCall from mass_edit_update no scene exceptions handling or blackandwhite list handling or tags
        if directCall:
            do_update_exceptions = False
        else:
            do_update_exceptions = True  # TODO make this smarter and only update on changes

            with showObj.lock:
                if anime:
                    if not showObj.release_groups:
                        showObj.release_groups = BlackAndWhiteList(showObj.indexerid)
                    if whitelist:
                        shortwhitelist = short_group_names(whitelist)
                        showObj.release_groups.set_white_keywords(shortwhitelist)
                    else:
                        showObj.release_groups.set_white_keywords([])

                    if blacklist:
                        shortblacklist = short_group_names(blacklist)
                        showObj.release_groups.set_black_keywords(shortblacklist)
                    else:
                        showObj.release_groups.set_black_keywords([])

        errors = []
        with showObj.lock:
            newQuality = Quality.combineQualities(map(int, anyQualities), map(int, bestQualities))
            showObj.quality = newQuality
            showObj.archive_firstmatch = archive_firstmatch

            # reversed for now
            if bool(showObj.flatten_folders) != bool(flatten_folders):
                showObj.flatten_folders = flatten_folders
                try:
                    sickbeard.showQueueScheduler.action.refreshShow(showObj)  # @UndefinedVariable
                except exceptions.CantRefreshException as e:
                    errors.append('Unable to refresh this show: ' + ex(e))

            showObj.paused = paused
            showObj.scene = scene
            showObj.anime = anime
            showObj.sports = sports
            showObj.subtitles = subtitles
            showObj.air_by_date = air_by_date
            showObj.tag = tag

            if not directCall:
                showObj.lang = indexer_lang
                showObj.dvdorder = dvdorder
                showObj.rls_ignore_words = rls_ignore_words.strip()
                showObj.rls_require_words = rls_require_words.strip()

            # if we change location clear the db of episodes, change it, write to db, and rescan
            if os.path.normpath(showObj._location) != os.path.normpath(location):
                logger.log(os.path.normpath(showObj._location) + ' != ' + os.path.normpath(location), logger.DEBUG)
                if not ek.ek(os.path.isdir, location) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
                    errors.append('New location <tt>%s</tt> does not exist' % location)

                # don't bother if we're going to update anyway
                elif not do_update:
                    # change it
                    try:
                        showObj.location = location
                        try:
                            sickbeard.showQueueScheduler.action.refreshShow(showObj)  # @UndefinedVariable
                        except exceptions.CantRefreshException as e:
                            errors.append('Unable to refresh this show:' + ex(e))
                            # grab updated info from TVDB
                            # showObj.loadEpisodesFromIndexer()
                            # rescan the episodes in the new folder
                    except exceptions.NoNFOException:
                        errors.append(
                            "The folder at <tt>%s</tt> doesn't contain a tvshow.nfo - copy your files to that folder before you change the directory in SickGear." % location)

            # save it to the DB
            showObj.saveToDB()

        # force the update
        if do_update:
            try:
                sickbeard.showQueueScheduler.action.updateShow(showObj, True)  # @UndefinedVariable
                helpers.cpu_sleep()
            except exceptions.CantUpdateException as e:
                errors.append('Unable to force an update on the show.')

        if do_update_exceptions:
            try:
                scene_exceptions.update_scene_exceptions(showObj.indexerid, exceptions_list)  # @UndefinedVdexerid)
                buildNameCache(showObj)
                helpers.cpu_sleep()
            except exceptions.CantUpdateException as e:
                errors.append('Unable to force an update on scene exceptions of the show.')

        if do_update_scene_numbering:
            try:
                sickbeard.scene_numbering.xem_refresh(showObj.indexerid, showObj.indexer)  # @UndefinedVariable
                helpers.cpu_sleep()
            except exceptions.CantUpdateException as e:
                errors.append('Unable to force an update on scene numbering of the show.')

        if directCall:
            return errors

        if len(errors) > 0:
            ui.notifications.error('%d error%s while saving changes:' % (len(errors), '' if len(errors) == 1 else 's'),
                                   '<ul>' + '\n'.join(['<li>%s</li>' % error for error in errors]) + '</ul>')

        self.redirect('/home/displayShow?show=' + show)

    def deleteShow(self, show=None, full=0):

        if show is None:
            return self._genericMessage('Error', 'Invalid show ID')

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            return self._genericMessage('Error', 'Unable to find the specified show')

        if sickbeard.showQueueScheduler.action.isBeingAdded(
                showObj) or sickbeard.showQueueScheduler.action.isBeingUpdated(showObj):  # @UndefinedVariable
            return self._genericMessage("Error", "Shows can't be deleted while they're being added or updated.")

        # if sickbeard.USE_TRAKT and sickbeard.TRAKT_SYNC:
        #     # remove show from trakt.tv library
        #     sickbeard.traktCheckerScheduler.action.removeShowFromTraktLibrary(showObj)

        showObj.deleteShow(bool(full))

        ui.notifications.message('%s with %s' % (('Deleting', 'Trashing')[sickbeard.TRASH_REMOVE_SHOW],
                                                 ('media left untouched', 'all related media')[bool(full)]),
                                 '<b>%s</b>' % showObj.name)
        self.redirect('/home/')

    def refreshShow(self, show=None):

        if show is None:
            return self._genericMessage('Error', 'Invalid show ID')

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            return self._genericMessage('Error', 'Unable to find the specified show')

        # force the update from the DB
        try:
            sickbeard.showQueueScheduler.action.refreshShow(showObj)  # @UndefinedVariable
        except exceptions.CantRefreshException as e:
            ui.notifications.error('Unable to refresh this show.',
                                   ex(e))

        helpers.cpu_sleep()

        self.redirect('/home/displayShow?show=' + str(showObj.indexerid))

    def updateShow(self, show=None, force=0, web=0):

        if show is None:
            return self._genericMessage('Error', 'Invalid show ID')

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            return self._genericMessage('Error', 'Unable to find the specified show')

        # force the update
        try:
            sickbeard.showQueueScheduler.action.updateShow(showObj, bool(force), bool(web))
        except exceptions.CantUpdateException as e:
            ui.notifications.error('Unable to update this show.',
                                   ex(e))

        helpers.cpu_sleep()

        self.redirect('/home/displayShow?show=' + str(showObj.indexerid))

    def subtitleShow(self, show=None, force=0):

        if show is None:
            return self._genericMessage('Error', 'Invalid show ID')

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            return self._genericMessage('Error', 'Unable to find the specified show')

        # search and download subtitles
        sickbeard.showQueueScheduler.action.downloadSubtitles(showObj, bool(force))  # @UndefinedVariable

        helpers.cpu_sleep()

        self.redirect('/home/displayShow?show=' + str(showObj.indexerid))

    def updateEMBY(self, show=None):

        if notifiers.emby_notifier.update_library(
                sickbeard.helpers.findCertainShow(sickbeard.showList,helpers.tryInt(show, None)), force=True):
            ui.notifications.message('Library update command sent to Emby host(s): ' + sickbeard.EMBY_HOST)
        else:
            ui.notifications.error('Unable to contact one or more Emby host(s): ' + sickbeard.EMBY_HOST)
        self.redirect('/home/')

    def updateKODI(self, showName=None):

        # only send update to first host in the list -- workaround for kodi sql backend users
        if sickbeard.KODI_UPDATE_ONLYFIRST:
            # only send update to first host in the list -- workaround for kodi sql backend users
            host = sickbeard.KODI_HOST.split(',')[0].strip()
        else:
            host = sickbeard.KODI_HOST

        if notifiers.kodi_notifier.update_library(showName=showName, force=True):
            ui.notifications.message('Library update command sent to Kodi host(s): ' + host)
        else:
            ui.notifications.error('Unable to contact one or more Kodi host(s): ' + host)
        self.redirect('/home/')

    def updateXBMC(self, showName=None):

        # only send update to first host in the list -- workaround for xbmc sql backend users
        if sickbeard.XBMC_UPDATE_ONLYFIRST:
            # only send update to first host in the list -- workaround for xbmc sql backend users
            host = sickbeard.XBMC_HOST.split(',')[0].strip()
        else:
            host = sickbeard.XBMC_HOST

        if notifiers.xbmc_notifier.update_library(showName=showName):
            ui.notifications.message('Library update command sent to XBMC host(s): ' + host)
        else:
            ui.notifications.error('Unable to contact one or more XBMC host(s): ' + host)
        self.redirect('/home/')

    def updatePLEX(self, *args, **kwargs):
        result = notifiers.plex_notifier.update_library()
        if 'Fail' not in result:
            ui.notifications.message(
                'Library update command sent to', 'Plex Media Server host(s): ' + sickbeard.PLEX_SERVER_HOST.replace(',', ', '))
        else:
            ui.notifications.error('Unable to contact', 'Plex Media Server host(s): ' + result)
        self.redirect('/home/')

    def setStatus(self, show=None, eps=None, status=None, direct=False):

        if show is None or eps is None or status is None:
            errMsg = 'You must specify a show and at least one episode'
            if direct:
                ui.notifications.error('Error', errMsg)
                return json.dumps({'result': 'error'})
            else:
                return self._genericMessage('Error', errMsg)

        if not statusStrings.has_key(int(status)):
            errMsg = 'Invalid status'
            if direct:
                ui.notifications.error('Error', errMsg)
                return json.dumps({'result': 'error'})
            else:
                return self._genericMessage('Error', errMsg)

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            errMsg = 'Error', 'Show not in show list'
            if direct:
                ui.notifications.error('Error', errMsg)
                return json.dumps({'result': 'error'})
            else:
                return self._genericMessage('Error', errMsg)

        segments = {}
        if eps is not None:

            sql_l = []
            for curEp in eps.split('|'):

                logger.log(u'Attempting to set status on episode %s to %s' % (curEp, status), logger.DEBUG)

                epInfo = curEp.split('x')

                epObj = showObj.getEpisode(int(epInfo[0]), int(epInfo[1]))

                if epObj is None:
                    return self._genericMessage("Error", "Episode couldn't be retrieved")

                if int(status) in [WANTED, FAILED]:
                    # figure out what episodes are wanted so we can backlog them
                    if epObj.season in segments:
                        segments[epObj.season].append(epObj)
                    else:
                        segments[epObj.season] = [epObj]

                with epObj.lock:
                    # don't let them mess up UNAIRED episodes
                    if epObj.status == UNAIRED:
                        logger.log(u'Refusing to change status of ' + curEp + ' because it is UNAIRED', logger.ERROR)
                        continue

                    if int(
                            status) in Quality.DOWNLOADED and epObj.status not in Quality.SNATCHED + Quality.SNATCHED_PROPER + Quality.SNATCHED_BEST + Quality.DOWNLOADED + [
                        IGNORED, SKIPPED] and not ek.ek(os.path.isfile, epObj.location):
                        logger.log(
                            u'Refusing to change status of ' + curEp + " to DOWNLOADED because it's not SNATCHED/DOWNLOADED",
                            logger.ERROR)
                        continue

                    if int(
                            status) == FAILED and epObj.status not in Quality.SNATCHED + Quality.SNATCHED_PROPER + Quality.SNATCHED_BEST + Quality.DOWNLOADED:
                        logger.log(
                            u'Refusing to change status of ' + curEp + " to FAILED because it's not SNATCHED/DOWNLOADED",
                            logger.ERROR)
                        continue

                    epObj.status = int(status)

                    # mass add to database
                    result = epObj.get_sql()
                    if None is not result:
                        sql_l.append(result)

            if 0 < len(sql_l):
                myDB = db.DBConnection()
                myDB.mass_action(sql_l)

        if WANTED == int(status):
            season_list = ''
            season_wanted = []
            for season, segment in segments.items():
                if not showObj.paused:
                    cur_backlog_queue_item = search_queue.BacklogQueueItem(showObj, segment)
                    sickbeard.searchQueueScheduler.action.add_item(cur_backlog_queue_item)  # @UndefinedVariable

                if season not in season_wanted:
                    season_wanted += [season]
                    season_list += u'<li>Season %s</li>' % season
                    logger.log((u'Not adding wanted eps to backlog search for %s season %s because show is paused',
                               u'Starting backlog search for %s season %s because eps were set to wanted')[
                        not showObj.paused] % (showObj.name, season))

            (title, msg) = (('Not starting backlog', u'Paused show prevented backlog search'),
                            ('Backlog started', u'Backlog search started'))[not showObj.paused]

            if segments:
                ui.notifications.message(title,
                                         u'%s for the following seasons of <b>%s</b>:<br /><ul>%s</ul>'
                                         % (msg, showObj.name, season_list))

        elif FAILED == int(status):
            msg = 'Retrying Search was automatically started for the following season of <b>' + showObj.name + '</b>:<br />'
            msg += '<ul>'

            for season, segment in segments.items():
                cur_failed_queue_item = search_queue.FailedQueueItem(showObj, segment)
                sickbeard.searchQueueScheduler.action.add_item(cur_failed_queue_item)  # @UndefinedVariable

                msg += '<li>Season ' + str(season) + '</li>'
                logger.log(u'Retrying Search for ' + showObj.name + ' season ' + str(
                    season) + ' because some eps were set to failed')

            msg += '</ul>'

            if segments:
                ui.notifications.message('Retry Search started', msg)

        if direct:
            return json.dumps({'result': 'success'})
        else:
            self.redirect('/home/displayShow?show=' + show)

    def testRename(self, show=None):

        if show is None:
            return self._genericMessage('Error', 'You must specify a show')

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            return self._genericMessage('Error', 'Show not in show list')

        try:
            show_loc = showObj.location  # @UnusedVariable
        except exceptions.ShowDirNotFoundException:
            return self._genericMessage('Error', "Can't rename episodes when the show dir is missing.")

        ep_obj_rename_list = []

        ep_obj_list = showObj.getAllEpisodes(has_location=True)

        for cur_ep_obj in ep_obj_list:
            # Only want to rename if we have a location
            if cur_ep_obj.location:
                if cur_ep_obj.relatedEps:
                    # do we have one of multi-episodes in the rename list already
                    have_already = False
                    for cur_related_ep in cur_ep_obj.relatedEps + [cur_ep_obj]:
                        if cur_related_ep in ep_obj_rename_list:
                            have_already = True
                            break
                        if not have_already:
                            ep_obj_rename_list.append(cur_ep_obj)
                else:
                    ep_obj_rename_list.append(cur_ep_obj)

        if ep_obj_rename_list:
            # present season DESC episode DESC on screen
            ep_obj_rename_list.reverse()

        t = PageTemplate(headers=self.request.headers, file='testRename.tmpl')
        t.submenu = [{'title': 'Edit', 'path': 'home/editShow?show=%d' % showObj.indexerid}]
        t.ep_obj_list = ep_obj_rename_list
        t.show = showObj

        return t.respond()

    def doRename(self, show=None, eps=None):

        if show is None or eps is None:
            errMsg = 'You must specify a show and at least one episode'
            return self._genericMessage('Error', errMsg)

        show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if show_obj is None:
            errMsg = 'Error', 'Show not in show list'
            return self._genericMessage('Error', errMsg)

        try:
            show_loc = show_obj.location  # @UnusedVariable
        except exceptions.ShowDirNotFoundException:
            return self._genericMessage('Error', "Can't rename episodes when the show dir is missing.")

        if eps is None:
            return self.redirect('/home/displayShow?show=' + show)

        myDB = db.DBConnection()
        for curEp in eps.split('|'):

            epInfo = curEp.split('x')

            # this is probably the worst possible way to deal with double eps but I've kinda painted myself into a corner here with this stupid database
            ep_result = myDB.select(
                'SELECT * FROM tv_episodes WHERE showid = ? AND season = ? AND episode = ? AND 5=5',
                [show, epInfo[0], epInfo[1]])
            if not ep_result:
                logger.log(u'Unable to find an episode for ' + curEp + ', skipping', logger.WARNING)
                continue
            related_eps_result = myDB.select('SELECT * FROM tv_episodes WHERE location = ? AND episode != ?',
                                             [ep_result[0]['location'], epInfo[1]])

            root_ep_obj = show_obj.getEpisode(int(epInfo[0]), int(epInfo[1]))
            root_ep_obj.relatedEps = []

            for cur_related_ep in related_eps_result:
                related_ep_obj = show_obj.getEpisode(int(cur_related_ep['season']), int(cur_related_ep['episode']))
                if related_ep_obj not in root_ep_obj.relatedEps:
                    root_ep_obj.relatedEps.append(related_ep_obj)

            root_ep_obj.rename()

        self.redirect('/home/displayShow?show=' + show)

    def searchEpisode(self, show=None, season=None, episode=None):

        # retrieve the episode object and fail if we can't get one
        ep_obj = self._getEpisode(show, season, episode)
        if isinstance(ep_obj, str):
            return json.dumps({'result': 'failure'})

        # make a queue item for it and put it on the queue
        ep_queue_item = search_queue.ManualSearchQueueItem(ep_obj.show, ep_obj)

        sickbeard.searchQueueScheduler.action.add_item(ep_queue_item)  # @UndefinedVariable

        if ep_queue_item.success:
            return returnManualSearchResult(ep_queue_item)
        if not ep_queue_item.started and ep_queue_item.success is None:
            return json.dumps({'result': 'success'}) #I Actually want to call it queued, because the search hasnt been started yet!
        if ep_queue_item.started and ep_queue_item.success is None:
            return json.dumps({'result': 'success'})
        else:
            return json.dumps({'result': 'failure'})

    ### Returns the current ep_queue_item status for the current viewed show.
    # Possible status: Downloaded, Snatched, etc...
    # Returns {'show': 279530, 'episodes' : ['episode' : 6, 'season' : 1, 'searchstatus' : 'queued', 'status' : 'running', 'quality': '4013']
    def getManualSearchStatus(self, show=None, season=None):

        episodes = []
        currentManualSearchThreadsQueued = []
        currentManualSearchThreadActive = []
        finishedManualSearchThreadItems= []

        # Queued Searches
        currentManualSearchThreadsQueued = sickbeard.searchQueueScheduler.action.get_all_ep_from_queue(show)
        # Running Searches
        if (sickbeard.searchQueueScheduler.action.is_manualsearch_in_progress()):
            currentManualSearchThreadActive = sickbeard.searchQueueScheduler.action.currentItem

        # Finished Searches
        finishedManualSearchThreadItems =  sickbeard.search_queue.MANUAL_SEARCH_HISTORY

        if currentManualSearchThreadsQueued:
            for searchThread in currentManualSearchThreadsQueued:
                searchstatus = 'queued'
                if isinstance(searchThread, sickbeard.search_queue.ManualSearchQueueItem):
                    episodes.append({'episode': searchThread.segment.episode,
                                     'episodeindexid': searchThread.segment.indexerid,
                                     'season' : searchThread.segment.season,
                                     'searchstatus' : searchstatus,
                                     'status' : statusStrings[searchThread.segment.status],
                                     'quality': self.getQualityClass(searchThread.segment)})
                elif hasattr(searchThread, 'segment'):
                    for epObj in searchThread.segment:
                        episodes.append({'episode': epObj.episode,
                             'episodeindexid': epObj.indexerid,
                             'season' : epObj.season,
                             'searchstatus' : searchstatus,
                             'status' : statusStrings[epObj.status],
                             'quality': self.getQualityClass(epObj)})

        if currentManualSearchThreadActive:
            searchThread = currentManualSearchThreadActive
            searchstatus = 'searching'
            if searchThread.success:
                searchstatus = 'finished'
            else:
                searchstatus = 'searching'
            if isinstance(searchThread, sickbeard.search_queue.ManualSearchQueueItem):
                episodes.append({'episode': searchThread.segment.episode,
                                 'episodeindexid': searchThread.segment.indexerid,
                                 'season' : searchThread.segment.season,
                                 'searchstatus' : searchstatus,
                                 'status' : statusStrings[searchThread.segment.status],
                                 'quality': self.getQualityClass(searchThread.segment)})
            elif hasattr(searchThread, 'segment'):
                for epObj in searchThread.segment:
                    episodes.append({'episode': epObj.episode,
                                     'episodeindexid': epObj.indexerid,
                                     'season' : epObj.season,
                                     'searchstatus' : searchstatus,
                                     'status' : statusStrings[epObj.status],
                                     'quality': self.getQualityClass(epObj)})

        if finishedManualSearchThreadItems:
            for searchThread in finishedManualSearchThreadItems:
                if isinstance(searchThread, sickbeard.search_queue.ManualSearchQueueItem):
                    if str(searchThread.show.indexerid) == show and not [x for x in episodes if x['episodeindexid'] == searchThread.segment.indexerid]:
                        searchstatus = 'finished'
                        episodes.append({'episode': searchThread.segment.episode,
                                         'episodeindexid': searchThread.segment.indexerid,
                                 'season' : searchThread.segment.season,
                                 'searchstatus' : searchstatus,
                                 'status' : statusStrings[searchThread.segment.status],
                                 'quality': self.getQualityClass(searchThread.segment)})
                ### These are only Failed Downloads/Retry SearchThreadItems.. lets loop through the segement/episodes
                elif hasattr(searchThread, 'segment') and str(searchThread.show.indexerid) == show:
                    for epObj in searchThread.segment:
                        if not [x for x in episodes if x['episodeindexid'] == epObj.indexerid]:
                            searchstatus = 'finished'
                            episodes.append({'episode': epObj.episode,
                                             'episodeindexid': epObj.indexerid,
                                     'season' : epObj.season,
                                     'searchstatus' : searchstatus,
                                     'status' : statusStrings[epObj.status],
                                     'quality': self.getQualityClass(epObj)})

        return json.dumps({'show': show, 'episodes' : episodes})

        #return json.dumps()

    def getQualityClass(self, ep_obj):
        # return the correct json value

        # Find the quality class for the episode
        quality_class = Quality.qualityStrings[Quality.UNKNOWN]
        ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
        for x in (SD, HD720p, HD1080p):
            if ep_quality in Quality.splitQuality(x)[0]:
                quality_class = qualityPresetStrings[x]
                break

        return quality_class

    def searchEpisodeSubtitles(self, show=None, season=None, episode=None):
        # retrieve the episode object and fail if we can't get one
        ep_obj = self._getEpisode(show, season, episode)
        if isinstance(ep_obj, str):
            return json.dumps({'result': 'failure'})

        # try do download subtitles for that episode
        previous_subtitles = set(subliminal.language.Language(x) for x in ep_obj.subtitles)
        try:
            ep_obj.subtitles = set(x.language for x in ep_obj.downloadSubtitles().values()[0])
        except:
            return json.dumps({'result': 'failure'})

        # return the correct json value
        if previous_subtitles != ep_obj.subtitles:
            status = 'New subtitles downloaded: %s' % ' '.join([
                "<img src='" + sickbeard.WEB_ROOT + "/images/flags/" + x.alpha2 +
                ".png' alt='" + x.name + "'/>" for x in
                sorted(list(ep_obj.subtitles.difference(previous_subtitles)))])
        else:
            status = 'No subtitles downloaded'
        ui.notifications.message('Subtitles Search', status)
        return json.dumps({'result': status, 'subtitles': ','.join(sorted([x.alpha2 for x in
                                                                    ep_obj.subtitles.union(previous_subtitles)]))})

    def setSceneNumbering(self, show, indexer, forSeason=None, forEpisode=None, forAbsolute=None, sceneSeason=None,
                          sceneEpisode=None, sceneAbsolute=None):

        # sanitize:
        show = None if show in [None, 'null', ''] else int(show)
        indexer = None if indexer in [None, 'null', ''] else int(indexer)

        show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, show)

        if not show_obj.is_anime:
            for_season = None if forSeason in [None, 'null', ''] else int(forSeason)
            for_episode = None if forEpisode in [None, 'null', ''] else int(forEpisode)
            scene_season = None if sceneSeason in [None, 'null', ''] else int(sceneSeason)
            scene_episode = None if sceneEpisode in [None, 'null', ''] else int(sceneEpisode)
            action_log = u'Set episode scene numbering to %sx%s for episode %sx%s of "%s"'\
                         % (scene_season, scene_episode, for_season, for_episode, show_obj.name)
            ep_args = {'show': show, 'season': for_season, 'episode': for_episode}
            scene_args = {'indexer_id': show, 'indexer': indexer, 'season': for_season, 'episode': for_episode,
                          'sceneSeason': scene_season, 'sceneEpisode': scene_episode}
            result = {'forSeason': for_season, 'forEpisode': for_episode, 'sceneSeason': None, 'sceneEpisode': None}
        else:
            for_absolute = None if forAbsolute in [None, 'null', ''] else int(forAbsolute)
            scene_absolute = None if sceneAbsolute in [None, 'null', ''] else int(sceneAbsolute)
            action_log = u'Set absolute scene numbering to %s for episode %s of "%s"'\
                         % (scene_absolute, for_absolute, show_obj.name)
            ep_args = {'show': show, 'absolute': for_absolute}
            scene_args = {'indexer_id': show, 'indexer': indexer, 'absolute_number': for_absolute,
                          'sceneAbsolute': scene_absolute}
            result = {'forAbsolute': for_absolute, 'sceneAbsolute': None}

        ep_obj = self._getEpisode(**ep_args)
        result['success'] = not isinstance(ep_obj, str)
        if result['success']:
            logger.log(action_log, logger.DEBUG)
            set_scene_numbering(**scene_args)
            show_obj.flushEpisodes()
        else:
            result['errorMessage'] = ep_obj

        if not show_obj.is_anime:
            scene_numbering = get_scene_numbering(show, indexer, for_season, for_episode)
            if scene_numbering:
                (result['sceneSeason'], result['sceneEpisode']) = scene_numbering
        else:
            scene_numbering = get_scene_absolute_numbering(show, indexer, for_absolute)
            if scene_numbering:
                result['sceneAbsolute'] = scene_numbering

        return json.dumps(result)

    def retryEpisode(self, show, season, episode):

        # retrieve the episode object and fail if we can't get one
        ep_obj = self._getEpisode(show, season, episode)
        if isinstance(ep_obj, str):
            return json.dumps({'result': 'failure'})

        # make a queue item for it and put it on the queue
        ep_queue_item = search_queue.FailedQueueItem(ep_obj.show, [ep_obj])
        sickbeard.searchQueueScheduler.action.add_item(ep_queue_item)  # @UndefinedVariable

        if ep_queue_item.success:
            return returnManualSearchResult(ep_queue_item)
        if not ep_queue_item.started and ep_queue_item.success is None:
            return json.dumps({'result': 'success'}) #I Actually want to call it queued, because the search hasnt been started yet!
        if ep_queue_item.started and ep_queue_item.success is None:
            return json.dumps({'result': 'success'})
        else:
            return json.dumps({'result': 'failure'})

    @staticmethod
    def fetch_releasegroups(show_name):

        if helpers.set_up_anidb_connection():
            try:
                anime = adba.Anime(sickbeard.ADBA_CONNECTION, name=show_name)
                groups = anime.get_groups()
            except Exception as e:
                logger.log(u'exception msg: ' + str(e), logger.DEBUG)
                return json.dumps({'result': 'fail', 'resp': 'connect'})

            return json.dumps({'result': 'success', 'groups': groups})

        return json.dumps({'result': 'fail', 'resp': 'init'})


class HomePostProcess(Home):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='home_postprocess.tmpl')
        t.submenu = self.HomeMenu()
        return t.respond()

    def processEpisode(self, dir=None, nzbName=None, jobName=None, quiet=None, process_method=None, force=None,
                       force_replace=None, failed='0', type='auto', stream='0', dupekey=None, **kwargs):

        if not dir and ('0' == failed or not nzbName):
            self.redirect('/home/postprocess/')
        else:
            showIdRegex = re.compile(r'^SickGear-([A-Za-z]*)(\d+)-')
            indexer = 0
            showObj = None
            if dupekey and showIdRegex.search(dupekey):
                m = showIdRegex.match(dupekey)
                istr = m.group(1)
                for i in sickbeard.indexerApi().indexers:
                    if istr == sickbeard.indexerApi(i).config.get('dupekey'):
                        indexer = i
                        break
                showObj = helpers.find_show_by_id(sickbeard.showList, {indexer: int(m.group(2))},
                                               no_mapped_ids=True)
            result = processTV.processDir(dir.decode('utf-8') if dir else None, nzbName.decode('utf-8') if nzbName else None,
                                          process_method=process_method, type=type,
                                          cleanup='cleanup' in kwargs and kwargs['cleanup'] in ['on', '1'],
                                          force=force in ['on', '1'],
                                          force_replace=force_replace in ['on', '1'],
                                          failed='0' != failed,
                                          webhandler=self.send_message if stream != '0' else None,
                                          showObj=showObj)

            if '0' != stream:
                return
            result = re.sub(r'(?i)<br(?:[\s/]+)>', '\n', result)
            if None is not quiet and 1 == int(quiet):
                return u'%s' % re.sub('(?i)<a[^>]+>([^<]+)<[/]a>', r'\1', result)

            return self._genericMessage('Postprocessing results', u'<pre>%s</pre>' % result)


class NewHomeAddShows(Home):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='home_addShows.tmpl')
        t.submenu = self.HomeMenu()
        return t.respond()

    def getIndexerLanguages(self, *args, **kwargs):
        result = sickbeard.indexerApi().config['valid_languages']

        # Make sure list is sorted alphabetically but 'en' is in front
        if 'en' in result:
            del result[result.index('en')]
        result.sort()
        result.insert(0, 'en')

        return json.dumps({'results': result})

    def sanitizeFileName(self, name):
        return helpers.sanitizeFileName(name)

    def searchIndexersForShowName(self, search_term, lang='en', indexer=None):
        if not lang or lang == 'null':
            lang = 'en'

        search_term = search_term.strip().encode('utf-8')

        results = {}
        final_results = []

        search_id, indexer_id = '', None
        search_id = ''
        try:
            search_id = re.search(r'(?m)((?:tt\d{4,})|^\d{4,}$)', search_term).group(1)
            resp = [r for r in self.getTrakt('/search/%s/%s?type=show&extended=full' % (
                ('tvdb', 'imdb')['tt' in search_id], search_id)) if 'show' == r['type']][0]
            search_term = resp['show']['title']
            indexer_id = resp['show']['ids']['tvdb']
        except:
            search_term = (search_term, '')['tt' in search_id]

        # Query Indexers for each search term and build the list of results
        for indexer in sickbeard.indexerApi().indexers if not int(indexer) else [int(indexer)]:
            lINDEXER_API_PARMS = sickbeard.indexerApi(indexer).api_params.copy()
            lINDEXER_API_PARMS['language'] = lang
            lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsListUI
            t = sickbeard.indexerApi(indexer).indexer(**lINDEXER_API_PARMS)

            try:
                # add search results
                if bool(indexer_id):
                    logger.log('Fetching show using id: %s (%s) from tv datasource %s' % (
                        search_id, search_term, sickbeard.indexerApi(indexer).name), logger.DEBUG)
                    results.setdefault('tt' in search_id and 3 or indexer, []).extend(
                        [{'id': indexer_id, 'seriesname': t[indexer_id, False]['seriesname'],
                          'firstaired': t[indexer_id, False]['firstaired'], 'network': t[indexer_id, False]['network'],
                          'overview': t[indexer_id, False]['overview'],
                          'genres': '' if not t[indexer_id, False]['genre'] else
                            t[indexer_id, False]['genre'].lower().strip('|').replace('|', ', '),
                          }])
                    break
                else:
                    logger.log('Searching for shows using search term: %s from tv datasource %s' % (
                        search_term, sickbeard.indexerApi(indexer).name), logger.DEBUG)
                    results.setdefault(indexer, []).extend(t[search_term])
            except Exception as e:
                pass

            # Query trakt for tvdb ids
            try:
                logger.log('Searching for show using search term: %s from tv datasource Trakt' % search_term, logger.DEBUG)
                resp = self.getTrakt('/search/show?query=%s&extended=full' % search_term)
                tvdb_ids = []
                results_trakt = []
                for item in resp:
                    show = item['show']
                    if 'tvdb' in show['ids'] and show['ids']['tvdb'] and show['ids']['tvdb'] not in tvdb_ids:
                        results_trakt.append({
                            'id': show['ids']['tvdb'], 'seriesname': show['title'],
                            'firstaired': (show['first_aired'] and re.sub(r'T.*$', '', str(show['first_aired'])) or show['year']),
                            'network': show['network'], 'overview': show['overview'],
                            'genres': ', '.join(['%s' % v.lower() for v in show.get('genres', {}) or []])})
                        tvdb_ids.append(show['ids']['tvdb'])
                results.update({3: results_trakt})
                if INDEXER_TVDB in results:
                    tvdb_filtered = []
                    for tvdb_item in results[INDEXER_TVDB]:
                        if int(tvdb_item['id']) not in tvdb_ids:
                            tvdb_filtered.append(tvdb_item)
                    if tvdb_filtered:
                        results[INDEXER_TVDB] = tvdb_filtered
                    else:
                        del(results[INDEXER_TVDB])
            except:
                pass

        id_names = [None, sickbeard.indexerApi(INDEXER_TVDB).name, sickbeard.indexerApi(INDEXER_TVRAGE).name,
                    '%s via Trakt' % sickbeard.indexerApi(INDEXER_TVDB).name]
        map(final_results.extend,
            ([['%s%s' % (id_names[id], helpers.findCertainShow(sickbeard.showList, int(show['id'])) and ' - <span class="exists-db">exists in db</span>' or ''),
               (id, INDEXER_TVDB)[id == 3], sickbeard.indexerApi((id, INDEXER_TVDB)[id == 3]).config['show_url'], int(show['id']),
               show['seriesname'], self.encode_html(show['seriesname']), show['firstaired'],
               show.get('network', '') or '', show.get('genres', '') or '',
               re.sub(r'([,\.!][^,\.!]*?)$', '...',
                      re.sub(r'([!\?\.])(?=\w)', r'\1 ',
                             self.encode_html((show.get('overview', '') or '')[:250:].strip())))
               ] for show in shows] for id, shows in results.items()))

        lang_id = sickbeard.indexerApi().config['langabbv_to_id'][lang]
        return json.dumps({
            'results': sorted(final_results, reverse=True, key=lambda x: dateutil.parser.parse(
                re.match('^(?:19|20)\d\d$', str(x[6])) and ('%s-12-31' % str(x[6])) or (x[6] and str(x[6])) or '1900')),
            'langid': lang_id})

    def getTrakt(self, url, *args, **kwargs):

        filtered = []
        try:
            resp = TraktAPI().trakt_request(url)
            if len(resp):
                filtered = resp
        except TraktException as e:
            logger.log(u'Could not connect to Trakt service: %s' % ex(e), logger.WARNING)

        return filtered

    def massAddTable(self, rootDir=None, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='home_massAddTable.tmpl')
        t.submenu = self.HomeMenu()
        t.kwargs = kwargs

        if not rootDir:
            return 'No folders selected.'
        elif type(rootDir) != list:
            root_dirs = [rootDir]
        else:
            root_dirs = rootDir

        root_dirs = [urllib.unquote_plus(x) for x in root_dirs]

        if sickbeard.ROOT_DIRS:
            default_index = int(sickbeard.ROOT_DIRS.split('|')[0])
        else:
            default_index = 0

        if len(root_dirs) > default_index:
            tmp = root_dirs[default_index]
            if tmp in root_dirs:
                root_dirs.remove(tmp)
                root_dirs = [tmp] + root_dirs

        dir_list = []

        display_one_dir = file_list = None
        if kwargs.get('hash_dir'):
            try:
                for root_dir in sickbeard.ROOT_DIRS.split('|')[1:]:
                    try:
                        file_list = ek.ek(os.listdir, root_dir)
                    except:
                        continue

                    for cur_file in file_list:

                        cur_path = ek.ek(os.path.normpath, ek.ek(os.path.join, root_dir, cur_file))
                        if not ek.ek(os.path.isdir, cur_path):
                            continue

                        display_one_dir = kwargs.get('hash_dir') == str(abs(hash(cur_path)))
                        if display_one_dir:
                            raise ValueError('hash matched')
            except ValueError:
                pass

        myDB = db.DBConnection()
        for root_dir in root_dirs:
            if not file_list:
                try:
                    file_list = ek.ek(os.listdir, root_dir)
                except:
                    continue

            for cur_file in file_list:

                cur_path = ek.ek(os.path.normpath, ek.ek(os.path.join, root_dir, cur_file))
                if not ek.ek(os.path.isdir, cur_path):
                    continue

                highlight = kwargs.get('hash_dir') == str(abs(hash(cur_path)))
                if display_one_dir and not highlight:
                    continue
                cur_dir = {
                    'dir': cur_path,
                    'highlight': highlight,
                    'name': ek.ek(os.path.basename, cur_path),
                    'path': '%s%s' % (ek.ek(os.path.dirname, cur_path), os.sep)
                }

                # see if the folder is in XBMC already
                dirResults = myDB.select('SELECT * FROM tv_shows WHERE location = ?', [cur_path])

                if dirResults:
                    cur_dir['added_already'] = True
                else:
                    cur_dir['added_already'] = False

                dir_list.append(cur_dir)

                indexer_id = show_name = indexer = None
                for cur_provider in sickbeard.metadata_provider_dict.values():
                    if indexer_id and show_name:
                        continue

                    (indexer_id, show_name, indexer) = cur_provider.retrieveShowMetadata(cur_path)

                    # default to TVDB if indexer was not detected
                    if show_name and (not indexer or not indexer_id):
                        (sn, idx, id) = helpers.searchIndexerForShowID(show_name, indexer, indexer_id)

                        # set indexer and indexer_id from found info
                        if idx and id:
                            indexer = idx
                            indexer_id = id
                            show_name = sn

                # in case we don't have both indexer + indexer_id, set both to None
                if not indexer or not indexer_id:
                    indexer = indexer_id = None

                cur_dir['existing_info'] = (indexer_id, show_name, indexer)

                if indexer_id and helpers.findCertainShow(sickbeard.showList, indexer_id):
                    cur_dir['added_already'] = True

            file_list = None

        t.dirList = dir_list

        return t.respond()

    def new_show(self, show_to_add=None, other_shows=None, use_show_name=None, **kwargs):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to addNewShow
        """
        self.set_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Expires', '0')

        t = PageTemplate(headers=self.request.headers, file='home_newShow.tmpl')
        t.submenu = self.HomeMenu()
        t.enable_anime_options = True
        t.enable_default_wanted = True
        t.kwargs = kwargs

        indexer, show_dir, indexer_id, show_name = self.split_extra_show(show_to_add)

        # use the given show_dir for the indexer search if available
        if use_show_name:
            t.default_show_name = show_name
        elif not show_dir:
            t.default_show_name = ''
        elif not show_name:
            t.default_show_name = ek.ek(os.path.basename, ek.ek(os.path.normpath, show_dir)).replace('.', ' ')
        else:
            t.default_show_name = show_name

        # carry a list of other dirs if given
        if not other_shows:
            other_shows = []
        elif type(other_shows) != list:
            other_shows = [other_shows]

        # tell the template whether we're giving it show name & Indexer ID
        t.use_provided_info = bool(indexer_id and indexer and show_name)
        if t.use_provided_info:
            t.provided_indexer_id = int(indexer_id or 0)
            t.provided_indexer_name = show_name

        t.provided_show_dir = show_dir
        t.other_shows = other_shows
        t.provided_indexer = int(indexer or sickbeard.INDEXER_DEFAULT)
        t.indexers = dict([(i, sickbeard.indexerApi().indexers[i]) for i in sickbeard.indexerApi().indexers
                           if sickbeard.indexerApi(i).config['active']])
        t.whitelist = []
        t.blacklist = []
        t.groups = []

        t.show_scene_maps = list(itertools.chain(*sickbeard.scene_exceptions.xem_ids_list.values()))

        return t.respond()

    def randomhot_anidb(self, *args, **kwargs):

        try:
            import xml.etree.cElementTree as etree
        except ImportError:
            import elementtree.ElementTree as etree

        browse_type = 'AniDB'
        filtered = []

        xref_src = 'https://raw.githubusercontent.com/ScudLee/anime-lists/master/anime-list.xml'
        xml_data = helpers.getURL(xref_src)
        xref_root = xml_data and etree.fromstring(xml_data) or None

        url = 'http://api.anidb.net:9001/httpapi?client=sickgear&clientver=1&protover=1&request=main'
        response = helpers.getURL(url)
        if response and xref_root:
            oldest, newest = None, None
            try:
                anime_root = etree.fromstring(response)
                hot_anime, random_rec = [anime_root.find(node) for node in ['hotanime', 'randomrecommendation']]
                random_rec = [item.find('./anime') for item in random_rec]
                oldest_dt, newest_dt = 9999999, 0
                for list_type, items in [('hot', hot_anime.getchildren()), ('recommended', random_rec)]:
                    for anime in items:
                        ids = dict(anidb=config.to_int(anime.get('id'), None))
                        xref_node = xref_root.find('./anime[@anidbid="%s"]' % ids['anidb'])
                        if not xref_node:
                            continue
                        tvdbid = config.to_int(xref_node.get('tvdbid'), None)
                        if None is tvdbid:
                            continue
                        ids.update(dict(tvdb=tvdbid))
                        first_aired, title, image = [None is not y and y.text or y for y in [
                            anime.find(node) for node in ['startdate', 'title', 'picture']]]

                        dt = dateutil.parser.parse(first_aired)
                        dt_ordinal = dt.toordinal()
                        dt_string = sbdatetime.sbdatetime.sbfdate(dt)
                        if dt_ordinal < oldest_dt:
                            oldest_dt = dt_ordinal
                            oldest = dt_string
                        if dt_ordinal > newest_dt:
                            newest_dt = dt_ordinal
                            newest = dt_string

                        img_uri = 'http://img7.anidb.net/pics/anime/%s' % image
                        images = dict(poster=dict(thumb='imagecache?path=anidb&source=%s' % img_uri))
                        sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)

                        votes = rating = 0
                        counts = anime.find('./ratings/permanent')
                        if isinstance(counts, object):
                            votes = counts.get('count')
                            rated = float(counts.text)
                            rating = 100 < rated and rated / 10 or 10 > rated and 10 * rated or rated

                        filtered.append(dict(
                            type=list_type,
                            ids=ids,
                            premiered=dt_ordinal,
                            premiered_str=dt_string,
                            when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not poss. 16.11.2015
                            title=title.strip(),
                            images=images,
                            url_src_db='http://anidb.net/perl-bin/animedb.pl?show=anime&aid=%s' % ids['anidb'],
                            url_tvdb='%s%s' % (sickbeard.indexerApi(INDEXER_TVDB).config['show_url'], ids['tvdb']),
                            votes=votes, rating=rating,
                            genres='', overview=''
                        ))
            except:
                pass

            kwargs.update(dict(oldest=oldest, newest=newest))

        return self.browse_shows(browse_type, 'Random and Hot at AniDB', filtered, **kwargs)

    def anime_default(self):

        return self.redirect('/home/addShows/randomhot_anidb')

    def addAniDBShow(self, indexer_id, showName):

        if helpers.findCertainShow(sickbeard.showList, config.to_int(indexer_id, '')):
            return
        return self.new_show('|'.join(['', '', '', indexer_id or showName]), use_show_name=True, is_anime=True)

    @staticmethod
    def watchlist_config(**kwargs):

        if not isinstance(sickbeard.IMDB_ACCOUNTS, type([])):
            sickbeard.IMDB_ACCOUNTS = list(sickbeard.IMDB_ACCOUNTS)
        accounts = dict(map(None, *[iter(sickbeard.IMDB_ACCOUNTS)] * 2))

        if 'enable' == kwargs.get('action'):
            account_id = re.findall('\d{6,32}', kwargs.get('input', ''))
            if not account_id:
                return json.dumps({'result': 'Fail: Invalid IMDb ID'})
            acc_id = account_id[0]

            url = 'http://www.imdb.com/user/ur%s/watchlist' % acc_id + \
                  '/_ajax?sort=date_added,desc&mode=detail&page=1&title_type=tvSeries%2CtvEpisode&ref_=wl_vm_dtl'
            html = helpers.getURL(url, nocache=True)

            try:
                list_name = re.findall('(?i)<h1[^>]+>(.*)\s+Watchlist</h1>', html)[0].replace('\'s', '')
                accounts[acc_id] = list_name or 'noname'
            except:
                return json.dumps({'result': 'Fail: No list found with id: %s' % acc_id})

        else:
            acc_id = kwargs.get('select', '')
            if acc_id not in accounts:
                return json.dumps({'result': 'Fail: Unknown IMDb ID'})

            if 'disable' == kwargs.get('action'):
                accounts[acc_id] = '(Off) %s' % accounts[acc_id].replace('(Off) ', '')
            else:
                del accounts[acc_id]

        gears = [[k, v] for k, v in accounts.iteritems() if 'sickgear' in v.lower()]
        if gears:
            del accounts[gears[0][0]]
        yours = [[k, v] for k, v in accounts.iteritems() if 'your' == v.replace('(Off) ', '').lower()]
        if yours:
            del accounts[yours[0][0]]
        sickbeard.IMDB_ACCOUNTS = [x for tup in sorted(list(accounts.items()), key=lambda t: t[1]) for x in tup]
        if gears:
            sickbeard.IMDB_ACCOUNTS.insert(0, gears[0][1])
            sickbeard.IMDB_ACCOUNTS.insert(0, gears[0][0])
        if yours:
            sickbeard.IMDB_ACCOUNTS.insert(0, yours[0][1])
            sickbeard.IMDB_ACCOUNTS.insert(0, yours[0][0])
        sickbeard.save_config()

        return json.dumps({'result': 'Success', 'accounts': sickbeard.IMDB_ACCOUNTS})

    @staticmethod
    def parse_imdb_overview(tag):
        paragraphs = tag.select('.lister-item-content p')
        filtered = []
        for item in paragraphs:
            if not (item.select('span.certificate') or item.select('span.genre') or
                    item.select('span.runtime') or item.select('span.ghost')):
                filtered.append(item.get_text().strip())
        split_lines = [element.split('\n') for element in filtered]
        filtered = []
        least_lines = 10
        for item_lines in split_lines:
            if len(item_lines) < least_lines:
                least_lines = len(item_lines)
                filtered = [item_lines]
            elif len(item_lines) == least_lines:
                filtered.append(item_lines)
        overview = None
        for item_lines in filtered:
            text = ' '.join([item_lines.strip() for item_lines in item_lines]).strip()
            if len(text) and (not overview or (len(text) > len(overview))):
                overview = text
        return overview

    def parse_imdb_html(self, html, filtered, kwargs):

        img_size = re.compile(r'(?im)(V1[^XY]+([XY]))(\d+)([^\d]+)(\d+)([^\d]+)(\d+)([^\d]+)(\d+)([^\d]+)(\d+)(.*?)$')
        imdb_id = re.compile(r'(?i).*(tt\d+).*')

        with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
            show_list = soup.select('.lister-list')
            shows = [] if not show_list else show_list[0].select('.lister-item')
            oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0

            for row in shows:
                try:
                    title = row.select('.lister-item-header a[href*=title]')[0]
                    url_path = title['href'].strip('/')
                    ids = dict(imdb=imdb_id.sub(r'\1', url_path))
                    year, ended = 2*[None]
                    first_aired = row.select('.lister-item-header .lister-item-year')
                    if len(first_aired):
                        years = re.findall(r'.*?(\d{4})(?:.*?(\d{4}))?.*', first_aired[0].get_text())
                        year, ended = years and years[0] or 2*[None]
                    dt_ordinal = 0
                    if year:
                        dt = dateutil.parser.parse('01-01-%s' % year)
                        dt_ordinal = dt.toordinal()
                        if dt_ordinal < oldest_dt:
                            oldest_dt = dt_ordinal
                            oldest = year
                        if dt_ordinal > newest_dt:
                            newest_dt = dt_ordinal
                            newest = year

                    genres = row.select('.genre')
                    images = {}
                    img = row.select('.lister-item-image img')
                    overview = self.parse_imdb_overview(row)
                    rating = row.find('meta', attrs={'itemprop': 'ratingValue'})
                    rating = None is not rating and rating.get('content') or ''
                    voting = row.find('meta', attrs={'itemprop': 'ratingCount'})
                    voting = None is not voting and voting.get('content') or ''
                    img_uri = None
                    if len(img):
                        img_uri = img[0].get('loadlate')
                        match = img_size.search(img_uri)
                        if match and 'tv_series.gif' not in img_uri and 'nopicture' not in img_uri:
                            scale = lambda low1, high1: int((float(450) / high1) * low1)
                            high = int(max([match.group(9), match.group(11)]))
                            scaled = [scale(x, high) for x in
                                      [(int(match.group(n)), high)[high == int(match.group(n))] for n in
                                       3, 5, 7, 9, 11]]
                            parts = [match.group(1), match.group(4), match.group(6), match.group(8), match.group(10),
                                     match.group(12)]
                            img_uri = img_uri.replace(match.group(), ''.join(
                                [str(y) for x in map(None, parts, scaled) for y in x if y is not None]))
                            images = dict(poster=dict(thumb='imagecache?path=imdb&source=%s' % img_uri))
                            sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)

                    filtered.append(dict(
                        premiered=dt_ordinal,
                        premiered_str=year or 'No year',
                        ended_str=ended or '',
                        when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not poss. 16.11.2015
                        genres=('No genre yet' if not len(genres) else
                                genres[0].get_text().strip().lower().replace(' |', ',')),
                        ids=ids,
                        images='' if not img_uri else images,
                        overview='No overview yet' if not overview else self.encode_html(overview[:250:]),
                        rating=0 if not len(rating) else int(helpers.tryFloat(rating) * 10),
                        title=title.get_text().strip(),
                        url_src_db='http://www.imdb.com/%s/' % url_path.strip('/'),
                        votes=0 if not len(voting) else helpers.tryInt(voting, 'TBA')))

                    show = filter(lambda x: x.imdbid == ids['imdb'], sickbeard.showList)[0]
                    src = ((None, 'tvrage')[INDEXER_TVRAGE == show.indexer], 'tvdb')[INDEXER_TVDB == show.indexer]
                    if src:
                        filtered[-1]['ids'][src] = show.indexerid
                        filtered[-1]['url_' + src] = '%s%s' % (
                            sickbeard.indexerApi(show.indexer).config['show_url'], show.indexerid)
                except (AttributeError, TypeError, KeyError, IndexError):
                    continue

            kwargs.update(dict(oldest=oldest, newest=newest))

        return show_list and True or None

    def watchlist_imdb(self, *args, **kwargs):

        if 'add' == kwargs.get('action'):
            return self.redirect('/config/general/#core-component-group2')

        if kwargs.get('action') in ('delete', 'enable', 'disable'):
            return self.watchlist_config(**kwargs)

        browse_type = 'IMDb'

        filtered = []
        footnote = None
        start_year, end_year = (datetime.date.today().year - 10, datetime.date.today().year + 1)
        periods = [(start_year, end_year)] + [(x-10, x) for x in range(start_year, start_year-40, -10)]

        accounts = dict(map(None, *[iter(sickbeard.IMDB_ACCOUNTS)]*2))
        acc_id, list_name = (sickbeard.IMDB_DEFAULT_LIST_ID, sickbeard.IMDB_DEFAULT_LIST_NAME) if \
            0 == sickbeard.helpers.tryInt(kwargs.get('account')) or \
            kwargs.get('account') not in accounts.keys() or \
            accounts.get(kwargs.get('account'), '').startswith('(Off) ') else \
            (kwargs.get('account'), accounts.get(kwargs.get('account')))

        list_name += ('\'s', '')['your' == list_name.replace('(Off) ', '').lower()]

        url = 'http://www.imdb.com/user/ur%s/watchlist' % acc_id
        url_data = '/_ajax?sort=date_added,desc&mode=detail&page=1&title_type=tvSeries%2CtvEpisode&ref_=wl_vm_dtl'
        url_ui = '?mode=detail&page=1&sort=date_added,desc&title_type=tvSeries%2CtvEpisode&ref_=wl_ref_typ'

        html = helpers.getURL(url + url_data, headers={'Accept-Language': 'en-US'})
        if html:
            show_list_found = self.parse_imdb_html(html, filtered, kwargs)
            kwargs.update(dict(start_year=start_year))

            if len(filtered):
                footnote = ('Note; Some images on this page may be cropped at source: ' +
                            '<a target="_blank" href="%s">%s watchlist at IMDb</a>' % (
                                helpers.anon_url(url + url_ui), list_name))
            elif None is not show_list_found:
                kwargs['show_header'] = True
                kwargs['error_msg'] = 'No TV titles in the <a target="_blank" href="%s">%s watchlist at IMDb</a>' % (
                    helpers.anon_url(url + url_ui), list_name)

        kwargs.update(dict(footnote=footnote, mode='watchlist-%s' % acc_id, periods=periods))
        return self.browse_shows(browse_type, '%s IMDb Watchlist' % list_name, filtered, **kwargs)

    def popular_imdb(self, *args, **kwargs):

        browse_type = 'IMDb'

        filtered = []
        footnote = None
        start_year, end_year = (datetime.date.today().year - 10, datetime.date.today().year + 1)
        periods = [(start_year, end_year)] + [(x-10, x) for x in range(start_year, start_year-40, -10)]

        start_year_in, end_year_in = [helpers.tryInt(x) for x in (('0,0', kwargs.get('period'))[
                                                              ',' in kwargs.get('period', '')]).split(',')]
        if 1900 < start_year_in < 2050 and 2050 > end_year_in > 1900:
            start_year, end_year = (start_year_in, end_year_in)

        mode = 'popular-%s,%s' % (start_year, end_year)

        url = 'http://www.imdb.com/search/title?at=0&sort=moviemeter&title_type=tv_series&year=%s,%s' % (start_year, end_year)
        html = helpers.getURL(url, headers={'Accept-Language': 'en-US'})
        if html:
            self.parse_imdb_html(html, filtered, kwargs)
            kwargs.update(dict(mode=mode, periods=periods))

            if len(filtered):
                footnote = ('Note; Some images on this page may be cropped at source: ' +
                            '<a target="_blank" href="%s">IMDb</a>' % helpers.anon_url(url))

        kwargs.update(dict(footnote=footnote))
        return self.browse_shows(browse_type, 'Most Popular IMDb TV', filtered, **kwargs)

    def imdb_default(self):

        return self.redirect('/home/addShows/popular_imdb')

    def addIMDbShow(self, indexer_id, showName):
        return self.new_show('|'.join(['', '', '', re.search('(?i)tt\d+$', indexer_id) and indexer_id or showName]),
                            use_show_name=True)

    def trakt_anticipated(self, *args, **kwargs):

        return self.browse_trakt('shows/anticipated?limit=%s&' % 100, 'Anticipated at Trakt', mode='anticipated')

    def trakt_newseasons(self, *args, **kwargs):

        return self.browse_trakt(
                '/calendars/all/shows/premieres/%s/%s?' % (sbdatetime.sbdatetime.sbfdate(
                        dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
                'Season premieres at Trakt',
                mode='newseasons', footnote='Note; Expect default placeholder images in this list')

    def trakt_newshows(self, *args, **kwargs):

        return self.browse_trakt(
                '/calendars/all/shows/new/%s/%s?' % (sbdatetime.sbdatetime.sbfdate(
                        dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
                'Brand-new shows at Trakt',
                mode='newshows', footnote='Note; Expect default placeholder images in this list')

    def trakt_popular(self, *args, **kwargs):

        return self.browse_trakt('shows/popular?limit=%s&' % 100, 'Popular at Trakt', mode='popular')

    def trakt_trending(self, *args, **kwargs):

        return self.browse_trakt('shows/trending?limit=%s&' % 100, 'Trending at Trakt', mode='trending',
                                 footnote='Tip: For more Trakt, use "Show" near the top of this view')

    def trakt_watched(self, *args, **kwargs):

        return self.trakt_action('watch', args, **kwargs)

    def trakt_played(self, *args, **kwargs):

        return self.trakt_action('play', args, **kwargs)

    def trakt_collected(self, *args, **kwargs):

        return self.trakt_action('collect', args, **kwargs)

    def trakt_action(self, action, *args, **kwargs):

        cycle, desc, ext = (('month', 'month', ''), ('year', '12 months', '-year'))['year' == kwargs.get('period', '')]
        return self.browse_trakt('shows/%sed/%sly?limit=%s&' % (action, cycle, 100),
                                 'Most %sed at Trakt during the last %s' % (action, desc),
                                 mode='%sed%s' % (action, ext))

    def trakt_recommended(self, *args, **kwargs):

        if 'add' == kwargs.get('action'):
            return self.redirect('/config/notifications/#tabs-3')

        account = sickbeard.helpers.tryInt(kwargs.get('account'), None)
        try:
            name = sickbeard.TRAKT_ACCOUNTS[account].name
        except KeyError:
            return self.trakt_default()
        return self.browse_trakt(
                'recommendations/shows?limit=%s&' % 100, 'Recommended for <b class="grey-text">%s</b> by Trakt' % name,
                mode='recommended-%s' % account, send_oauth=account)

    def trakt_default(self):

        return self.redirect('/home/addShows/%s' % ('trakt_trending', sickbeard.TRAKT_MRU)[any(sickbeard.TRAKT_MRU)])

    def browse_trakt(self, url_path, browse_title, *args, **kwargs):

        browse_type = 'Trakt'
        normalised, filtered = ([], [])

        if not sickbeard.USE_TRAKT and 'recommended' in kwargs.get('mode', ''):
            error_msg = 'To browse personal recommendations, enable Trakt.tv in Config/Notifications/Social'
            return self.browse_shows(browse_type, browse_title, filtered, error_msg=error_msg, show_header=1, **kwargs)

        error_msg = None
        try:
            account = kwargs.get('send_oauth', None)
            if account:
                account = sickbeard.helpers.tryInt(account)
            resp = TraktAPI().trakt_request('%sextended=full,images' % url_path, send_oauth=account)
            if resp:
                if 'show' in resp[0]:
                    if 'first_aired' in resp[0]:
                        for item in resp:
                            item['show']['first_aired'] = item['first_aired']
                            del item['first_aired']
                    normalised = resp
                else:
                    for item in resp:
                        normalised.append({u'show': item})
                del resp
        except TraktAuthException as e:
            logger.log(u'Pin authorisation needed to connect to Trakt service: %s' % ex(e), logger.WARNING)
            error_msg = 'Unauthorized: Get another pin in the Notifications Trakt settings'
        except TraktException as e:
            logger.log(u'Could not connect to Trakt service: %s' % ex(e), logger.WARNING)
        except (IndexError, KeyError):
            pass

        oldest_dt = 9999999
        newest_dt = 0
        oldest = None
        newest = None
        for item in normalised:
            ignore = '''
            ((bbc|channel\s*?5.*?|itv)\s*?(drama|documentaries))|bbc\s*?(comedy|music)|music\s*?specials|tedtalks
            '''
            if re.search(ignore, item['show']['title'].strip(), re.I | re.X):
                continue
            try:
                dt = dateutil.parser.parse(item['show']['first_aired'])
                dt_ordinal = dt.toordinal()
                dt_string = sbdatetime.sbdatetime.sbfdate(dt)
                if dt_ordinal < oldest_dt:
                    oldest_dt = dt_ordinal
                    oldest = dt_string
                if dt_ordinal > newest_dt:
                    newest_dt = dt_ordinal
                    newest = dt_string

                tmdbid = item.get('show', {}).get('ids', {}).get('tmdb', 0)
                tvdbid = item.get('show', {}).get('ids', {}).get('tvdb', 0)
                traktid = item.get('show', {}).get('ids', {}).get('trakt', 0)
                images = dict(poster=dict(thumb='imagecache?path=trakt/poster/thumb&filename=%s&tmdbid=%s&tvdbid=%s' %
                                                ('%s.jpg' % traktid, tmdbid, tvdbid)))

                filtered.append(dict(
                    premiered=dt_ordinal,
                    premiered_str=dt_string,
                    when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not yet available 16.11.2015
                    episode_number='' if 'episode' not in item else item['episode']['number'] or 1,
                    episode_overview=('' if 'episode' not in item else
                                      self.encode_html(item['episode']['overview'][:250:].strip()) or ''),
                    episode_season='' if 'episode' not in item else item['episode']['season'] or 1,
                    genres=('' if 'genres' not in item['show'] else
                            ', '.join(['%s' % v for v in item['show']['genres']])),
                    ids=item['show']['ids'],
                    images=images,
                    overview=('' if 'overview' not in item['show'] or None is item['show']['overview'] else
                              self.encode_html(item['show']['overview'][:250:].strip())),
                    rating=0 < item['show'].get('rating', 0) and
                           ('%.2f' % (item['show'].get('rating') * 10)).replace('.00', '') or 0,
                    title=item['show']['title'].strip(),
                    url_src_db='https://trakt.tv/shows/%s' % item['show']['ids']['slug'],
                    url_tvdb=('', '%s%s' % (sickbeard.indexerApi(INDEXER_TVDB).config['show_url'],
                                            item['show']['ids']['tvdb']))[isinstance(item['show']['ids']['tvdb'], (int, long))
                                                                          and 0 < item['show']['ids']['tvdb']],
                    votes='0' if 'votes' not in item['show'] else item['show']['votes']))
            except:
                pass

        kwargs.update(dict(oldest=oldest, newest=newest, error_msg=error_msg))

        if 'recommended' not in kwargs.get('mode', ''):
            mode = kwargs.get('mode', '').split('-')
            if mode:
                func = 'trakt_%s' % mode[0]
                if callable(getattr(self, func, None)):
                    param = '' if 1 == len(mode) or mode[1] not in ['year', 'month', 'week', 'all'] else \
                        '?period=' + mode[1]
                    sickbeard.TRAKT_MRU = '%s%s' % (func, param)
                    sickbeard.save_config()
        return self.browse_shows(browse_type, browse_title, filtered, **kwargs)

    @staticmethod
    def encode_html(text):

        return re.sub(r'\r?\n', '<br />', text.replace('"', '&quot;').replace("'", '&#39;').replace('&', '&amp;')
                      .replace('<', '&lt;').replace('>', '&gt;'))

    def addTraktShow(self, indexer_id, showName):

        if not helpers.findCertainShow(sickbeard.showList, config.to_int(indexer_id, '')):
            return self.new_show('|'.join(['', '', '', config.to_int(indexer_id, None) and indexer_id or showName]),
                                use_show_name=True)

    def browse_shows(self, browse_type, browse_title, shows, *args, **kwargs):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to addNewShow
        """
        t = PageTemplate(headers=self.request.headers, file='home_browseShows.tmpl')
        t.submenu = self.HomeMenu()
        t.browse_type = browse_type
        t.browse_title = browse_title
        t.all_shows = []
        t.kwargs = kwargs
        dedupe = []

        t.all_shows_inlibrary = 0
        for item in shows:
            item['show_id'] = ''
            for index, tvdb in enumerate(['tvdb', 'tvrage']):
                try:
                    item['show_id'] = str(item['ids'][tvdb])
                    tvshow = helpers.findCertainShow(sickbeard.showList, item['show_id'])
                except:
                    continue
                # check tvshow indexer is not using the same id from another indexer
                if tvshow and (index + 1) == tvshow.indexer:
                    item['show_id'] = u'%s:%s' % (tvshow.indexer, tvshow.indexerid)
                    t.all_shows_inlibrary += 1
                    break

                if None is not config.to_int(item['show_id'], None):
                    break

            if not item['show_id'] and 'tt' in item['ids'].get('imdb', ''):
                item['show_id'] = item['ids']['imdb']

            if item['show_id'] not in dedupe:
                dedupe.append(item['show_id'])
                t.all_shows.append(item)

        return t.respond()

    def existing_shows(self, *args, **kwargs):
        """
        Prints out the page to add existing shows from a root dir
        """
        t = PageTemplate(headers=self.request.headers, file='home_addExistingShow.tmpl')
        t.submenu = self.HomeMenu()
        t.enable_anime_options = False
        t.kwargs = kwargs
        t.multi_parents = helpers.maybe_plural(len(sickbeard.ROOT_DIRS.split('|')[1:])) and 's are' or ' is'

        return t.respond()

    def addNewShow(self, whichSeries=None, indexerLang='en', rootDir=None, defaultStatus=None,
                   quality_preset=None, anyQualities=None, bestQualities=None, flatten_folders=None, subtitles=None,
                   fullShowPath=None, other_shows=None, skipShow=None, providedIndexer=None, anime=None,
                   scene=None, blacklist=None, whitelist=None, wanted_begin=None, wanted_latest=None, tag=None):
        """
        Receive tvdb id, dir, and other options and create a show from them. If extra show dirs are
        provided then it forwards back to new_show, if not it goes to /home.
        """

        # grab our list of other dirs if given
        if not other_shows:
            other_shows = []
        elif type(other_shows) != list:
            other_shows = [other_shows]

        def finishAddShow():
            # if there are no extra shows then go home
            if not other_shows:
                return self.redirect('/home/')

            # peel off the next one
            next_show_dir = other_shows[0]
            rest_of_show_dirs = other_shows[1:]

            # go to add the next show
            return self.new_show(next_show_dir, rest_of_show_dirs)

        # if we're skipping then behave accordingly
        if skipShow:
            return finishAddShow()

        # sanity check on our inputs
        if (not rootDir and not fullShowPath) or not whichSeries:
            return 'Missing params, no Indexer ID or folder:' + repr(whichSeries) + ' and ' + repr(
                rootDir) + '/' + repr(fullShowPath)

        # figure out what show we're adding and where
        series_pieces = whichSeries.split('|')
        if (whichSeries and rootDir) or (whichSeries and fullShowPath and len(series_pieces) > 1):
            if len(series_pieces) < 4:
                logger.log('Unable to add show due to show selection. Not enough arguments: %s' % (repr(series_pieces)),
                           logger.ERROR)
                ui.notifications.error('Unknown error. Unable to add show due to problem with show selection.')
                return self.redirect('/home/addShows/existing_shows/')

            indexer = int(series_pieces[0])
            indexer_id = int(series_pieces[2])
            show_name = series_pieces[3]
        else:
            # if no indexer was provided use the default indexer set in General settings
            if not providedIndexer:
                providedIndexer = sickbeard.INDEXER_DEFAULT

            indexer = int(providedIndexer)
            indexer_id = int(whichSeries)
            show_name = os.path.basename(os.path.normpath(fullShowPath))

        # use the whole path if it's given, or else append the show name to the root dir to get the full show path
        if fullShowPath:
            show_dir = ek.ek(os.path.normpath, fullShowPath)
        else:
            show_dir = ek.ek(os.path.join, rootDir, helpers.sanitizeFileName(show_name))

        # blanket policy - if the dir exists you should have used 'add existing show' numbnuts
        if ek.ek(os.path.isdir, show_dir) and not fullShowPath:
            ui.notifications.error('Unable to add show', u'Found existing folder: ' + show_dir)
            return self.redirect('/home/addShows/existing_shows?sid=%s&hash_dir=%s' % (indexer_id, abs(hash(show_dir))))

        # don't create show dir if config says not to
        if sickbeard.ADD_SHOWS_WO_DIR:
            logger.log(u'Skipping initial creation due to config.ini setting (add_shows_wo_dir)')
        else:
            dir_exists = helpers.makeDir(show_dir)
            if not dir_exists:
                logger.log(u'Unable to add show because can\'t create folder: ' + show_dir, logger.ERROR)
                ui.notifications.error('Unable to add show', u'Can\'t create folder: ' + show_dir)
                return self.redirect('/home/')

            else:
                helpers.chmodAsParent(show_dir)

        # prepare the inputs for passing along
        scene = config.checkbox_to_value(scene)
        anime = config.checkbox_to_value(anime)
        flatten_folders = config.checkbox_to_value(flatten_folders)
        subtitles = config.checkbox_to_value(subtitles)

        if whitelist:
            whitelist = short_group_names(whitelist)
        if blacklist:
            blacklist = short_group_names(blacklist)

        if not anyQualities:
            anyQualities = []
        if not bestQualities or int(quality_preset):
            bestQualities = []
        if type(anyQualities) != list:
            anyQualities = [anyQualities]
        if type(bestQualities) != list:
            bestQualities = [bestQualities]
        newQuality = Quality.combineQualities(map(int, anyQualities), map(int, bestQualities))

        wanted_begin = config.minimax(wanted_begin, 0, -1, 10)
        wanted_latest = config.minimax(wanted_latest, 0, -1, 10)

        # add the show
        sickbeard.showQueueScheduler.action.addShow(indexer, indexer_id, show_dir, int(defaultStatus), newQuality,
                                                    flatten_folders, indexerLang, subtitles, anime,
                                                    scene, None, blacklist, whitelist,
                                                    wanted_begin, wanted_latest, tag)  # @UndefinedVariable
        # ui.notifications.message('Show added', 'Adding the specified show into ' + show_dir)

        return finishAddShow()

    def split_extra_show(self, extra_show):
        if not extra_show:
            return (None, None, None, None)
        split_vals = extra_show.split('|')
        indexer = helpers.tryInt(split_vals[0], 1)
        show_dir = split_vals[1]
        if len(split_vals) < 4:
            return indexer, show_dir, None, None
        indexer_id = split_vals[2]
        show_name = '|'.join(split_vals[3:])

        return indexer, show_dir, indexer_id, show_name

    def addExistingShows(self, shows_to_add=None, promptForSettings=None, **kwargs):
        """
        Receives a dir list and add them. Adds the ones with given TVDB IDs first, then forwards
        along to the new_show page.
        """

        if kwargs.get('sid', None):
            return self.redirect('/home/addShows/new_show?show_to_add=%s&use_show_name=True' %
                                 '|'.join(['', '', '', kwargs.get('sid', '')]))

        # grab a list of other shows to add, if provided
        if not shows_to_add:
            shows_to_add = []
        elif type(shows_to_add) != list:
            shows_to_add = [shows_to_add]

        promptForSettings = config.checkbox_to_value(promptForSettings)

        indexer_id_given = []
        dirs_only = []
        # separate all the ones with Indexer IDs
        for cur_dir in shows_to_add:
            if '|' in cur_dir:
                split_vals = cur_dir.split('|')
                if len(split_vals) < 3:
                    dirs_only.append(cur_dir)
            if '|' not in cur_dir:
                dirs_only.append(cur_dir)
            else:
                indexer, show_dir, indexer_id, show_name = self.split_extra_show(cur_dir)

                if not show_dir or not indexer_id or not show_name:
                    continue

                indexer_id_given.append((indexer, show_dir, int(indexer_id), show_name))

        # if they want me to prompt for settings then I will just carry on to the new_show page
        if promptForSettings and shows_to_add:
            return self.new_show(shows_to_add[0], shows_to_add[1:])

        # if they don't want me to prompt for settings then I can just add all the nfo shows now
        num_added = 0
        for cur_show in indexer_id_given:
            indexer, show_dir, indexer_id, show_name = cur_show

            if indexer is not None and indexer_id is not None:
                # add the show
                sickbeard.showQueueScheduler.action.addShow(indexer, indexer_id, show_dir,
                                                            default_status=sickbeard.STATUS_DEFAULT,
                                                            quality=sickbeard.QUALITY_DEFAULT,
                                                            flatten_folders=sickbeard.FLATTEN_FOLDERS_DEFAULT,
                                                            subtitles=sickbeard.SUBTITLES_DEFAULT,
                                                            anime=sickbeard.ANIME_DEFAULT,
                                                            scene=sickbeard.SCENE_DEFAULT)
                num_added += 1

        if num_added:
            ui.notifications.message('Shows Added',
                                     'Automatically added ' + str(num_added) + ' from their existing metadata files')

        # if we're done then go home
        if not dirs_only:
            return self.redirect('/home/')

        # for the remaining shows we need to prompt for each one, so forward this on to the new_show page
        return self.new_show(dirs_only[0], dirs_only[1:])


class Manage(MainHandler):
    def ManageMenu(self):
        manageMenu = [
            {'title': 'Backlog Overview', 'path': 'manage/backlogOverview/'},
            {'title': 'Manage Searches', 'path': 'manage/manageSearches/'},
            {'title': 'Show Queue Overview', 'path': 'manage/showQueueOverview/'},
            {'title': 'Episode Status Management', 'path': 'manage/episodeStatuses/'}, ]

        if sickbeard.USE_SUBTITLES:
            manageMenu.append({'title': 'Missed Subtitle Management', 'path': 'manage/subtitleMissed/'})

        if sickbeard.USE_FAILED_DOWNLOADS:
            manageMenu.append({'title': 'Failed Downloads', 'path': 'manage/failedDownloads/'})

        return manageMenu

    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='manage.tmpl')
        t.submenu = self.ManageMenu()
        return t.respond()

    def showEpisodeStatuses(self, indexer_id, whichStatus):
        status_list = [int(whichStatus)]
        if status_list[0] == SNATCHED:
            status_list = Quality.SNATCHED + Quality.SNATCHED_PROPER

        myDB = db.DBConnection()
        cur_show_results = myDB.select(
            'SELECT season, episode, name, airdate FROM tv_episodes WHERE showid = ? AND season != 0 AND status IN (' + ','.join(
                ['?'] * len(status_list)) + ')', [int(indexer_id)] + status_list)

        result = {}
        for cur_result in cur_show_results:
            if not sickbeard.SEARCH_UNAIRED and 1000 > cur_result['airdate']:
                continue
            cur_season = int(cur_result['season'])
            cur_episode = int(cur_result['episode'])

            if cur_season not in result:
                result[cur_season] = {}

            result[cur_season][cur_episode] = {'name': cur_result['name'], 'airdate_never': 1000 > int(cur_result['airdate'])}

        return json.dumps(result)

    def episodeStatuses(self, whichStatus=None):

        if whichStatus:
            whichStatus = int(whichStatus)
            status_list = [whichStatus]
            if status_list[0] == SNATCHED:
                status_list = Quality.SNATCHED + Quality.SNATCHED_PROPER
        else:
            status_list = []

        t = PageTemplate(headers=self.request.headers, file='manage_episodeStatuses.tmpl')
        t.submenu = self.ManageMenu()
        t.whichStatus = whichStatus

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT COUNT(*) AS snatched FROM [tv_episodes] WHERE season > 0 AND episode > 0 AND airdate > 1 AND ' +
            'status IN (%s)' % ','.join([str(quality) for quality in Quality.SNATCHED + Quality.SNATCHED_PROPER]))
        t.default_manage = sql_result and sql_result[0]['snatched'] and SNATCHED or WANTED

        # if we have no status then this is as far as we need to go
        if not status_list:
            return t.respond()

        status_results = my_db.select(
            'SELECT show_name, tv_shows.indexer_id as indexer_id, airdate FROM tv_episodes, tv_shows WHERE tv_episodes.status IN (' + ','.join(
                ['?'] * len(
                    status_list)) + ') AND season != 0 AND tv_episodes.showid = tv_shows.indexer_id ORDER BY show_name',
            status_list)

        ep_counts = {}
        ep_count = 0
        never_counts = {}
        show_names = {}
        sorted_show_ids = []
        for cur_status_result in status_results:
            if not sickbeard.SEARCH_UNAIRED and 1000 > cur_status_result['airdate']:
                continue
            cur_indexer_id = int(cur_status_result['indexer_id'])
            if cur_indexer_id not in ep_counts:
                ep_counts[cur_indexer_id] = 1
            else:
                ep_counts[cur_indexer_id] += 1
            ep_count += 1
            if cur_indexer_id not in never_counts:
                never_counts[cur_indexer_id] = 0
            if 1000 > int(cur_status_result['airdate']):
                never_counts[cur_indexer_id] += 1

            show_names[cur_indexer_id] = cur_status_result['show_name']
            if cur_indexer_id not in sorted_show_ids:
                sorted_show_ids.append(cur_indexer_id)

        t.show_names = show_names
        t.ep_counts = ep_counts
        t.ep_count = ep_count
        t.never_counts = never_counts
        t.sorted_show_ids = sorted_show_ids
        return t.respond()

    def changeEpisodeStatuses(self, oldStatus, newStatus, wantedStatus=sickbeard.common.UNKNOWN, *args, **kwargs):
        status_list = [int(oldStatus)]
        if status_list[0] == SNATCHED:
            status_list = Quality.SNATCHED + Quality.SNATCHED_PROPER

        to_change = {}

        # make a list of all shows and their associated args
        for arg in kwargs:
            # we don't care about unchecked checkboxes
            if kwargs[arg] != 'on':
                continue

            indexer_id, what = arg.split('-')

            if indexer_id not in to_change:
                to_change[indexer_id] = []

            to_change[indexer_id].append(what)

        if sickbeard.common.WANTED == int(wantedStatus):
            newStatus = sickbeard.common.WANTED

        myDB = db.DBConnection()
        for cur_indexer_id in to_change:

            # get a list of all the eps we want to change if they just said 'all'
            if 'all' in to_change[cur_indexer_id]:
                all_eps_results = myDB.select(
                    'SELECT season, episode FROM tv_episodes WHERE status IN (' + ','.join(
                        ['?'] * len(status_list)) + ') AND season != 0 AND showid = ?',
                    status_list + [cur_indexer_id])
                all_eps = [str(x['season']) + 'x' + str(x['episode']) for x in all_eps_results]
                to_change[cur_indexer_id] = all_eps

            Home(self.application, self.request).setStatus(cur_indexer_id, '|'.join(to_change[cur_indexer_id]),
                                                           newStatus, direct=True)

        self.redirect('/manage/episodeStatuses/')

    def showSubtitleMissed(self, indexer_id, whichSubs):
        myDB = db.DBConnection()
        cur_show_results = myDB.select(
            "SELECT season, episode, name, subtitles FROM tv_episodes WHERE showid = ? AND season != 0 AND status LIKE '%4'",
            [int(indexer_id)])

        result = {}
        for cur_result in cur_show_results:
            if whichSubs == 'all':
                if len(set(cur_result['subtitles'].split(',')).intersection(set(subtitles.wantedLanguages()))) >= len(
                        subtitles.wantedLanguages()):
                    continue
            elif whichSubs in cur_result['subtitles'].split(','):
                continue

            cur_season = int(cur_result['season'])
            cur_episode = int(cur_result['episode'])

            if cur_season not in result:
                result[cur_season] = {}

            if cur_episode not in result[cur_season]:
                result[cur_season][cur_episode] = {}

            result[cur_season][cur_episode]['name'] = cur_result['name']

            result[cur_season][cur_episode]['subtitles'] = ','.join(
                subliminal.language.Language(subtitle).alpha2 for subtitle in cur_result['subtitles'].split(',')) if not \
                cur_result['subtitles'] == '' else ''

        return json.dumps(result)

    def subtitleMissed(self, whichSubs=None):

        t = PageTemplate(headers=self.request.headers, file='manage_subtitleMissed.tmpl')
        t.submenu = self.ManageMenu()
        t.whichSubs = whichSubs

        if not whichSubs:
            return t.respond()

        myDB = db.DBConnection()
        status_results = myDB.select(
            "SELECT show_name, tv_shows.indexer_id as indexer_id, tv_episodes.subtitles subtitles FROM tv_episodes, tv_shows WHERE tv_shows.subtitles = 1 AND tv_episodes.status LIKE '%4' AND tv_episodes.season != 0 AND tv_episodes.showid = tv_shows.indexer_id ORDER BY show_name")

        ep_counts = {}
        show_names = {}
        sorted_show_ids = []
        for cur_status_result in status_results:
            if whichSubs == 'all':
                if len(set(cur_status_result['subtitles'].split(',')).intersection(
                        set(subtitles.wantedLanguages()))) >= len(subtitles.wantedLanguages()):
                    continue
            elif whichSubs in cur_status_result['subtitles'].split(','):
                continue

            cur_indexer_id = int(cur_status_result['indexer_id'])
            if cur_indexer_id not in ep_counts:
                ep_counts[cur_indexer_id] = 1
            else:
                ep_counts[cur_indexer_id] += 1

            show_names[cur_indexer_id] = cur_status_result['show_name']
            if cur_indexer_id not in sorted_show_ids:
                sorted_show_ids.append(cur_indexer_id)

        t.show_names = show_names
        t.ep_counts = ep_counts
        t.sorted_show_ids = sorted_show_ids
        return t.respond()

    def downloadSubtitleMissed(self, *args, **kwargs):

        to_download = {}

        # make a list of all shows and their associated args
        for arg in kwargs:
            indexer_id, what = arg.split('-')

            # we don't care about unchecked checkboxes
            if kwargs[arg] != 'on':
                continue

            if indexer_id not in to_download:
                to_download[indexer_id] = []

            to_download[indexer_id].append(what)

        for cur_indexer_id in to_download:
            # get a list of all the eps we want to download subtitles if they just said 'all'
            if 'all' in to_download[cur_indexer_id]:
                myDB = db.DBConnection()
                all_eps_results = myDB.select(
                    "SELECT season, episode FROM tv_episodes WHERE status LIKE '%4' AND season != 0 AND showid = ?",
                    [cur_indexer_id])
                to_download[cur_indexer_id] = [str(x['season']) + 'x' + str(x['episode']) for x in all_eps_results]

            for epResult in to_download[cur_indexer_id]:
                season, episode = epResult.split('x')

                show = sickbeard.helpers.findCertainShow(sickbeard.showList, int(cur_indexer_id))
                subtitles = show.getEpisode(int(season), int(episode)).downloadSubtitles()

        self.redirect('/manage/subtitleMissed/')

    def backlogShow(self, indexer_id):

        show_obj = helpers.findCertainShow(sickbeard.showList, int(indexer_id))

        if show_obj:
            sickbeard.backlogSearchScheduler.action.search_backlog([show_obj])  # @UndefinedVariable

        self.redirect('/manage/backlogOverview/')

    def backlogOverview(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='manage_backlogOverview.tmpl')
        t.submenu = self.ManageMenu()

        showCounts = {}
        showCats = {}
        showSQLResults = {}

        myDB = db.DBConnection()
        for curShow in sickbeard.showList:

            epCounts = {}
            epCats = {}
            epCounts[Overview.SKIPPED] = 0
            epCounts[Overview.WANTED] = 0
            epCounts[Overview.QUAL] = 0
            epCounts[Overview.GOOD] = 0
            epCounts[Overview.UNAIRED] = 0
            epCounts[Overview.SNATCHED] = 0

            sqlResults = myDB.select(
                'SELECT * FROM tv_episodes WHERE showid = ? ORDER BY season DESC, episode DESC',
                [curShow.indexerid])

            for curResult in sqlResults:
                if not sickbeard.SEARCH_UNAIRED and 1 == curResult['airdate']:
                    continue
                curEpCat = curShow.getOverview(int(curResult['status']))
                if curEpCat:
                    epCats[str(curResult['season']) + 'x' + str(curResult['episode'])] = curEpCat
                    epCounts[curEpCat] += 1

            showCounts[curShow.indexerid] = epCounts
            showCats[curShow.indexerid] = epCats
            showSQLResults[curShow.indexerid] = sqlResults

        t.showCounts = showCounts
        t.showCats = showCats
        t.showSQLResults = showSQLResults

        return t.respond()

    def massEdit(self, toEdit=None):

        t = PageTemplate(headers=self.request.headers, file='manage_massEdit.tmpl')
        t.submenu = self.ManageMenu()

        if not toEdit:
            return self.redirect('/manage/')

        showIDs = toEdit.split('|')
        showList = []
        for curID in showIDs:
            curID = int(curID)
            showObj = helpers.findCertainShow(sickbeard.showList, curID)
            if showObj:
                showList.append(showObj)

        archive_firstmatch_all_same = True
        last_archive_firstmatch = None

        flatten_folders_all_same = True
        last_flatten_folders = None

        paused_all_same = True
        last_paused = None

        tag_all_same = True
        last_tag = None

        anime_all_same = True
        last_anime = None

        sports_all_same = True
        last_sports = None

        quality_all_same = True
        last_quality = None

        subtitles_all_same = True
        last_subtitles = None

        scene_all_same = True
        last_scene = None

        air_by_date_all_same = True
        last_air_by_date = None

        root_dir_list = []

        for curShow in showList:

            cur_root_dir = ek.ek(os.path.dirname, curShow._location)
            if cur_root_dir not in root_dir_list:
                root_dir_list.append(cur_root_dir)

            if archive_firstmatch_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_archive_firstmatch not in (None, curShow.archive_firstmatch):
                    archive_firstmatch_all_same = False
                else:
                    last_archive_firstmatch = curShow.archive_firstmatch

            # if we know they're not all the same then no point even bothering
            if paused_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_paused not in (None, curShow.paused):
                    paused_all_same = False
                else:
                    last_paused = curShow.paused

            if tag_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_tag not in (None, curShow.tag):
                    tag_all_same = False
                else:
                    last_tag = curShow.tag

            if anime_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_anime not in (None, curShow.is_anime):
                    anime_all_same = False
                else:
                    last_anime = curShow.anime

            if flatten_folders_all_same:
                if last_flatten_folders not in (None, curShow.flatten_folders):
                    flatten_folders_all_same = False
                else:
                    last_flatten_folders = curShow.flatten_folders

            if quality_all_same:
                if last_quality not in (None, curShow.quality):
                    quality_all_same = False
                else:
                    last_quality = curShow.quality

            if subtitles_all_same:
                if last_subtitles not in (None, curShow.subtitles):
                    subtitles_all_same = False
                else:
                    last_subtitles = curShow.subtitles

            if scene_all_same:
                if last_scene not in (None, curShow.scene):
                    scene_all_same = False
                else:
                    last_scene = curShow.scene

            if sports_all_same:
                if last_sports not in (None, curShow.sports):
                    sports_all_same = False
                else:
                    last_sports = curShow.sports

            if air_by_date_all_same:
                if last_air_by_date not in (None, curShow.air_by_date):
                    air_by_date_all_same = False
                else:
                    last_air_by_date = curShow.air_by_date

        t.showList = toEdit
        t.archive_firstmatch_value = last_archive_firstmatch if archive_firstmatch_all_same else None
        t.paused_value = last_paused if paused_all_same else None
        t.tag_value = last_tag if tag_all_same else None
        t.anime_value = last_anime if anime_all_same else None
        t.flatten_folders_value = last_flatten_folders if flatten_folders_all_same else None
        t.quality_value = last_quality if quality_all_same else None
        t.subtitles_value = last_subtitles if subtitles_all_same else None
        t.scene_value = last_scene if scene_all_same else None
        t.sports_value = last_sports if sports_all_same else None
        t.air_by_date_value = last_air_by_date if air_by_date_all_same else None
        t.root_dir_list = root_dir_list

        return t.respond()

    def massEditSubmit(self, archive_firstmatch=None, paused=None, anime=None, sports=None, scene=None,
                       flatten_folders=None, quality_preset=False, subtitles=None, air_by_date=None, anyQualities=[],
                       bestQualities=[], toEdit=None, tag=None, *args, **kwargs):

        dir_map = {}
        for cur_arg in kwargs:
            if not cur_arg.startswith('orig_root_dir_'):
                continue
            which_index = cur_arg.replace('orig_root_dir_', '')
            end_dir = kwargs['new_root_dir_' + which_index]
            dir_map[kwargs[cur_arg]] = end_dir

        showIDs = toEdit.split('|')
        errors = []
        for curShow in showIDs:
            curErrors = []
            showObj = helpers.findCertainShow(sickbeard.showList, int(curShow))
            if not showObj:
                continue

            cur_root_dir = ek.ek(os.path.dirname, showObj._location)
            cur_show_dir = ek.ek(os.path.basename, showObj._location)
            if cur_root_dir in dir_map and cur_root_dir != dir_map[cur_root_dir]:
                new_show_dir = ek.ek(os.path.join, dir_map[cur_root_dir], cur_show_dir)
                if 'nt' != os.name and ':\\' in cur_show_dir:
                    cur_show_dir = showObj._location.split('\\')[-1]
                    try:
                        base_dir = dir_map[cur_root_dir].rsplit(cur_show_dir)[0].rstrip('/')
                    except IndexError:
                        base_dir = dir_map[cur_root_dir]
                    new_show_dir = ek.ek(os.path.join, base_dir, cur_show_dir)
                logger.log(
                    u'For show ' + showObj.name + ' changing dir from ' + showObj._location + ' to ' + new_show_dir)
            else:
                new_show_dir = showObj._location

            if archive_firstmatch == 'keep':
                new_archive_firstmatch = showObj.archive_firstmatch
            else:
                new_archive_firstmatch = True if archive_firstmatch == 'enable' else False
            new_archive_firstmatch = 'on' if new_archive_firstmatch else 'off'

            if paused == 'keep':
                new_paused = showObj.paused
            else:
                new_paused = True if paused == 'enable' else False
            new_paused = 'on' if new_paused else 'off'

            if tag == 'keep':
                new_tag = showObj.tag
            else:
                new_tag = tag

            if anime == 'keep':
                new_anime = showObj.anime
            else:
                new_anime = True if anime == 'enable' else False
            new_anime = 'on' if new_anime else 'off'

            if sports == 'keep':
                new_sports = showObj.sports
            else:
                new_sports = True if sports == 'enable' else False
            new_sports = 'on' if new_sports else 'off'

            if scene == 'keep':
                new_scene = showObj.is_scene
            else:
                new_scene = True if scene == 'enable' else False
            new_scene = 'on' if new_scene else 'off'

            if air_by_date == 'keep':
                new_air_by_date = showObj.air_by_date
            else:
                new_air_by_date = True if air_by_date == 'enable' else False
            new_air_by_date = 'on' if new_air_by_date else 'off'

            if flatten_folders == 'keep':
                new_flatten_folders = showObj.flatten_folders
            else:
                new_flatten_folders = True if flatten_folders == 'enable' else False
            new_flatten_folders = 'on' if new_flatten_folders else 'off'

            if subtitles == 'keep':
                new_subtitles = showObj.subtitles
            else:
                new_subtitles = True if subtitles == 'enable' else False

            new_subtitles = 'on' if new_subtitles else 'off'

            if quality_preset == 'keep':
                anyQualities, bestQualities = Quality.splitQuality(showObj.quality)
            elif int(quality_preset):
                 bestQualities = []

            exceptions_list = []

            curErrors += Home(self.application, self.request).editShow(curShow, new_show_dir, anyQualities,
                                                                       bestQualities, exceptions_list,
                                                                       archive_firstmatch=new_archive_firstmatch,
                                                                       flatten_folders=new_flatten_folders,
                                                                       paused=new_paused, sports=new_sports,
                                                                       subtitles=new_subtitles, anime=new_anime,
                                                                       scene=new_scene, air_by_date=new_air_by_date,
                                                                       tag=new_tag, directCall=True)

            if curErrors:
                logger.log(u'Errors: ' + str(curErrors), logger.ERROR)
                errors.append('<b>%s:</b>\n<ul>' % showObj.name + ' '.join(
                    ['<li>%s</li>' % error for error in curErrors]) + '</ul>')

        if len(errors) > 0:
            ui.notifications.error('%d error%s while saving changes:' % (len(errors), '' if len(errors) == 1 else 's'),
                                   ' '.join(errors))

        self.redirect('/manage/')

    def massUpdate(self, toUpdate=None, toRefresh=None, toRename=None, toDelete=None, toRemove=None, toMetadata=None, toSubtitle=None):

        if toUpdate is not None:
            toUpdate = toUpdate.split('|')
        else:
            toUpdate = []

        if toRefresh is not None:
            toRefresh = toRefresh.split('|')
        else:
            toRefresh = []

        if toRename is not None:
            toRename = toRename.split('|')
        else:
            toRename = []

        if toSubtitle is not None:
            toSubtitle = toSubtitle.split('|')
        else:
            toSubtitle = []

        if toDelete is not None:
            toDelete = toDelete.split('|')
        else:
            toDelete = []

        if toRemove is not None:
            toRemove = toRemove.split('|')
        else:
            toRemove = []

        if toMetadata is not None:
            toMetadata = toMetadata.split('|')
        else:
            toMetadata = []

        errors = []
        refreshes = []
        updates = []
        renames = []
        subtitles = []

        for curShowID in set(toUpdate + toRefresh + toRename + toSubtitle + toDelete + toRemove + toMetadata):

            if curShowID == '':
                continue

            showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(curShowID))

            if showObj is None:
                continue

            if curShowID in toDelete:
                showObj.deleteShow(True)
                # don't do anything else if it's being deleted
                continue

            if curShowID in toRemove:
                showObj.deleteShow()
                # don't do anything else if it's being remove
                continue

            if curShowID in toUpdate:
                try:
                    sickbeard.showQueueScheduler.action.updateShow(showObj, True, True)  # @UndefinedVariable
                    updates.append(showObj.name)
                except exceptions.CantUpdateException as e:
                    errors.append('Unable to update show ' + showObj.name + ': ' + ex(e))

            # don't bother refreshing shows that were updated anyway
            if curShowID in toRefresh and curShowID not in toUpdate:
                try:
                    sickbeard.showQueueScheduler.action.refreshShow(showObj)  # @UndefinedVariable
                    refreshes.append(showObj.name)
                except exceptions.CantRefreshException as e:
                    errors.append('Unable to refresh show ' + showObj.name + ': ' + ex(e))

            if curShowID in toRename:
                sickbeard.showQueueScheduler.action.renameShowEpisodes(showObj)  # @UndefinedVariable
                renames.append(showObj.name)

            if curShowID in toSubtitle:
                sickbeard.showQueueScheduler.action.downloadSubtitles(showObj)  # @UndefinedVariable
                subtitles.append(showObj.name)

        if len(errors) > 0:
            ui.notifications.error('Errors encountered',
                                   '<br >\n'.join(errors))

        messageDetail = ''

        if len(updates) > 0:
            messageDetail += '<br /><b>Updates</b><br /><ul><li>'
            messageDetail += '</li><li>'.join(updates)
            messageDetail += '</li></ul>'

        if len(refreshes) > 0:
            messageDetail += '<br /><b>Refreshes</b><br /><ul><li>'
            messageDetail += '</li><li>'.join(refreshes)
            messageDetail += '</li></ul>'

        if len(renames) > 0:
            messageDetail += '<br /><b>Renames</b><br /><ul><li>'
            messageDetail += '</li><li>'.join(renames)
            messageDetail += '</li></ul>'

        if len(subtitles) > 0:
            messageDetail += '<br /><b>Subtitles</b><br /><ul><li>'
            messageDetail += '</li><li>'.join(subtitles)
            messageDetail += '</li></ul>'

        if len(updates + refreshes + renames + subtitles) > 0:
            ui.notifications.message('The following actions were queued:',
                                     messageDetail)

        self.redirect('/manage/')

    def failedDownloads(self, limit=100, toRemove=None):

        myDB = db.DBConnection('failed.db')

        sql = 'SELECT * FROM failed ORDER BY ROWID DESC'
        limit = helpers.tryInt(limit, 100)
        if not limit:
            sql_results = myDB.select(sql)
        else:
            sql_results = myDB.select(sql + ' LIMIT ?', [limit + 1])

        toRemove = toRemove.split('|') if toRemove is not None else []

        for release in toRemove:
            item = re.sub('_{3,}', '%', release)
            myDB.action('DELETE FROM failed WHERE release like ?', [item])

        if toRemove:
            return self.redirect('/manage/failedDownloads/')

        t = PageTemplate(headers=self.request.headers, file='manage_failedDownloads.tmpl')
        t.over_limit = limit and len(sql_results) > limit
        t.failedResults = t.over_limit and sql_results[0:-1] or sql_results
        t.limit = str(limit)
        t.submenu = self.ManageMenu()

        return t.respond()


class ManageSearches(Manage):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='manage_manageSearches.tmpl')
        # t.backlogPI = sickbeard.backlogSearchScheduler.action.get_progress_indicator()
        t.backlogPaused = sickbeard.searchQueueScheduler.action.is_backlog_paused()
        t.backlogRunning = sickbeard.searchQueueScheduler.action.is_backlog_in_progress()
        t.backlogIsActive = sickbeard.backlogSearchScheduler.action.am_running()
        t.standardBacklogRunning = sickbeard.searchQueueScheduler.action.is_standard_backlog_in_progress()
        t.backlogRunningType = sickbeard.searchQueueScheduler.action.type_of_backlog_in_progress()
        t.recentSearchStatus = sickbeard.searchQueueScheduler.action.is_recentsearch_in_progress()
        t.findPropersStatus = sickbeard.searchQueueScheduler.action.is_propersearch_in_progress()
        t.queueLength = sickbeard.searchQueueScheduler.action.queue_length()

        t.submenu = self.ManageMenu()

        return t.respond()

    def forceVersionCheck(self, *args, **kwargs):
        # force a check to see if there is a new version
        if sickbeard.versionCheckScheduler.action.check_for_new_version(force=True):
            logger.log(u'Forcing version check')

        self.redirect('/home/')

    def forceBacklog(self, *args, **kwargs):
        # force it to run the next time it looks
        if not sickbeard.searchQueueScheduler.action.is_standard_backlog_in_progress():
            sickbeard.backlogSearchScheduler.force_search(force_type=FORCED_BACKLOG)
            logger.log(u'Backlog search forced')
            ui.notifications.message('Backlog search started')

            time.sleep(5)
            self.redirect('/manage/manageSearches/')

    def forceSearch(self, *args, **kwargs):

        # force it to run the next time it looks
        if not sickbeard.searchQueueScheduler.action.is_recentsearch_in_progress():
            result = sickbeard.recentSearchScheduler.forceRun()
            if result:
                logger.log(u'Recent search forced')
                ui.notifications.message('Recent search started')

        time.sleep(5)
        self.redirect('/manage/manageSearches/')

    def forceFindPropers(self, *args, **kwargs):

        # force it to run the next time it looks
        result = sickbeard.properFinderScheduler.forceRun()
        if result:
            logger.log(u'Find propers search forced')
            ui.notifications.message('Find propers search started')

        time.sleep(5)
        self.redirect('/manage/manageSearches/')

    def pauseBacklog(self, paused=None):
        if paused == '1':
            sickbeard.searchQueueScheduler.action.pause_backlog()  # @UndefinedVariable
        else:
            sickbeard.searchQueueScheduler.action.unpause_backlog()  # @UndefinedVariable

        time.sleep(5)
        self.redirect('/manage/manageSearches/')

class showQueueOverview(Manage):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='manage_showQueueOverview.tmpl')
        t.queueLength = sickbeard.showQueueScheduler.action.queue_length()
        t.showList = sickbeard.showList
        t.ShowUpdateRunning = sickbeard.showQueueScheduler.action.isShowUpdateRunning() or sickbeard.showUpdateScheduler.action.amActive

        t.submenu = self.ManageMenu()

        return t.respond()

    def forceShowUpdate(self, *args, **kwargs):

        result = sickbeard.showUpdateScheduler.forceRun()
        if result:
            logger.log(u'Show Update forced')
            ui.notifications.message('Forced Show Update started')

        time.sleep(5)
        self.redirect('/manage/showQueueOverview/')

class History(MainHandler):
    def index(self, limit=100):

        # sqlResults = myDB.select('SELECT h.*, show_name, name FROM history h, tv_shows s, tv_episodes e WHERE h.showid=s.indexer_id AND h.showid=e.showid AND h.season=e.season AND h.episode=e.episode ORDER BY date DESC LIMIT '+str(numPerPage*(p-1))+', '+str(numPerPage))
        myDB = db.DBConnection()
        if limit == '0':
            sqlResults = myDB.select(
                'SELECT h.*, show_name FROM history h, tv_shows s WHERE h.showid=s.indexer_id ORDER BY date DESC')
        else:
            sqlResults = myDB.select(
                'SELECT h.*, show_name FROM history h, tv_shows s WHERE h.showid=s.indexer_id ORDER BY date DESC LIMIT ?',
                [limit])

        history = {'show_id': 0, 'season': 0, 'episode': 0, 'quality': 0,
                   'actions': [{'time': '', 'action': '', 'provider': ''}]}
        compact = []

        for sql_result in sqlResults:

            if not any((history['show_id'] == sql_result['showid']
                        and history['season'] == sql_result['season']
                        and history['episode'] == sql_result['episode']
                        and history['quality'] == sql_result['quality'])
                       for history in compact):

                history = {}
                history['show_id'] = sql_result['showid']
                history['season'] = sql_result['season']
                history['episode'] = sql_result['episode']
                history['quality'] = sql_result['quality']
                history['show_name'] = sql_result['show_name']
                history['resource'] = sql_result['resource']

                action = {}
                history['actions'] = []

                action['time'] = sql_result['date']
                action['action'] = sql_result['action']
                action['provider'] = sql_result['provider']
                action['resource'] = sql_result['resource']
                history['actions'].append(action)
                history['actions'].sort(key=lambda x: x['time'])
                compact.append(history)
            else:
                index = [i for i, dict in enumerate(compact) \
                         if dict['show_id'] == sql_result['showid'] \
                         and dict['season'] == sql_result['season'] \
                         and dict['episode'] == sql_result['episode']
                         and dict['quality'] == sql_result['quality']][0]

                action = {}
                history = compact[index]

                action['time'] = sql_result['date']
                action['action'] = sql_result['action']
                action['provider'] = sql_result['provider']
                action['resource'] = sql_result['resource']
                history['actions'].append(action)
                history['actions'].sort(key=lambda x: x['time'], reverse=True)

        t = PageTemplate(headers=self.request.headers, file='history.tmpl')
        t.historyResults = sqlResults
        t.compactResults = compact
        t.limit = limit
        t.submenu = [
            {'title': 'Clear History', 'path': 'history/clearHistory'},
            {'title': 'Trim History', 'path': 'history/trimHistory'},
        ]

        return t.respond()

    def clearHistory(self, *args, **kwargs):

        myDB = db.DBConnection()
        myDB.action('DELETE FROM history WHERE 1=1')

        ui.notifications.message('History cleared')
        self.redirect('/history/')

    def trimHistory(self, *args, **kwargs):

        myDB = db.DBConnection()
        myDB.action('DELETE FROM history WHERE date < ' + str(
            (datetime.datetime.today() - datetime.timedelta(days=30)).strftime(history.dateFormat)))

        ui.notifications.message('Removed history entries greater than 30 days old')
        self.redirect('/history/')


class Config(MainHandler):
    @staticmethod
    def ConfigMenu():
        return [
            {'title': 'General', 'path': 'config/general/'},
            {'title': 'Search Settings', 'path': 'config/search/'},
            {'title': 'Search Providers', 'path': 'config/providers/'},
            {'title': 'Subtitles Settings', 'path': 'config/subtitles/'},
            {'title': 'Post Processing', 'path': 'config/postProcessing/'},
            {'title': 'Notifications', 'path': 'config/notifications/'},
            {'title': 'Anime', 'path': 'config/anime/'},
        ]

    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='config.tmpl')
        t.submenu = self.ConfigMenu

        return t.respond()


class ConfigGeneral(Config):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='config_general.tmpl')
        t.submenu = self.ConfigMenu
        t.show_tags = ', '.join(sickbeard.SHOW_TAGS)
        t.indexers = dict([(i, sickbeard.indexerApi().indexers[i]) for i in sickbeard.indexerApi().indexers
                           if sickbeard.indexerApi(i).config['active']])
        return t.respond()

    def saveRootDirs(self, rootDirString=None):
        sickbeard.ROOT_DIRS = rootDirString

    def saveAddShowDefaults(self, default_status, any_qualities='', best_qualities='', default_wanted_begin=None,
                            default_wanted_latest=None, default_flatten_folders=False, default_scene=False,
                            default_subtitles=False, default_anime=False, default_tag=''):

        any_qualities = ([], any_qualities.split(','))[any(any_qualities)]
        best_qualities = ([], best_qualities.split(','))[any(best_qualities)]

        sickbeard.STATUS_DEFAULT = int(default_status)
        sickbeard.QUALITY_DEFAULT = int(Quality.combineQualities(map(int, any_qualities), map(int, best_qualities)))
        sickbeard.WANTED_BEGIN_DEFAULT = config.minimax(default_wanted_begin, 0, -1, 10)
        sickbeard.WANTED_LATEST_DEFAULT = config.minimax(default_wanted_latest, 0, -1, 10)
        sickbeard.FLATTEN_FOLDERS_DEFAULT = config.checkbox_to_value(default_flatten_folders)
        sickbeard.SCENE_DEFAULT = config.checkbox_to_value(default_scene)
        sickbeard.SUBTITLES_DEFAULT = config.checkbox_to_value(default_subtitles)
        sickbeard.ANIME_DEFAULT = config.checkbox_to_value(default_anime)
        sickbeard.DEFAULT_SHOW_TAG = default_tag

        sickbeard.save_config()

    def generateKey(self, *args, **kwargs):
        """ Return a new randomized API_KEY
        """

        try:
            from hashlib import md5
        except ImportError:
            from md5 import md5

        # Create some values to seed md5
        t = str(time.time())
        r = str(random.random())

        # Create the md5 instance and give it the current time
        m = md5(t)

        # Update the md5 instance with the random variable
        m.update(r)

        # Return a hex digest of the md5, eg 49f68a5c8493ec2c0bf489821c21fc3b
        logger.log(u'New API generated')
        return m.hexdigest()

    def saveGeneral(self, log_dir=None, web_port=None, web_log=None, encryption_version=None, web_ipv6=None,
                    update_shows_on_start=None, show_update_hour=None,
                    trash_remove_show=None, trash_rotate_logs=None, update_frequency=None, launch_browser=None, web_username=None,
                    use_api=None, api_key=None, indexer_default=None, timezone_display=None, cpu_preset=None, file_logging_preset=None,
                    web_password=None, version_notify=None, enable_https=None, https_cert=None, https_key=None,
                    handle_reverse_proxy=None, home_search_focus=None, sort_article=None, auto_update=None, notify_on_update=None,
                    proxy_setting=None, proxy_indexers=None, anon_redirect=None, git_path=None, git_remote=None, calendar_unprotected=None,
                    fuzzy_dating=None, trim_zero=None, date_preset=None, date_preset_na=None, time_preset=None,
                    indexer_timeout=None, rootDir=None, theme_name=None, default_home=None, use_imdb_info=None,
                    display_background=None, display_background_transparent=None, display_all_seasons=None,
                    show_tags=None, showlist_tagview=None):

        results = []

        # Misc
        sickbeard.LAUNCH_BROWSER = config.checkbox_to_value(launch_browser)
        config.change_VERSION_NOTIFY(config.checkbox_to_value(version_notify))
        sickbeard.AUTO_UPDATE = config.checkbox_to_value(auto_update)
        sickbeard.NOTIFY_ON_UPDATE = config.checkbox_to_value(notify_on_update)
        # sickbeard.LOG_DIR is set in config.change_LOG_DIR()

        sickbeard.UPDATE_SHOWS_ON_START = config.checkbox_to_value(update_shows_on_start)
        sickbeard.SHOW_UPDATE_HOUR = config.minimax(show_update_hour, 3, 0, 23)
        sickbeard.TRASH_REMOVE_SHOW = config.checkbox_to_value(trash_remove_show)
        sickbeard.TRASH_ROTATE_LOGS = config.checkbox_to_value(trash_rotate_logs)
        config.change_UPDATE_FREQUENCY(update_frequency)
        sickbeard.LAUNCH_BROWSER = config.checkbox_to_value(launch_browser)
        sickbeard.HOME_SEARCH_FOCUS = config.checkbox_to_value(home_search_focus)
        sickbeard.USE_IMDB_INFO = config.checkbox_to_value(use_imdb_info)
        sickbeard.DISPLAY_BACKGROUND = config.checkbox_to_value(display_background)
        sickbeard.DISPLAY_BACKGROUND_TRANSPARENT = display_background_transparent
        sickbeard.DISPLAY_ALL_SEASONS = config.checkbox_to_value(display_all_seasons)
        sickbeard.SORT_ARTICLE = config.checkbox_to_value(sort_article)
        sickbeard.CPU_PRESET = cpu_preset
        sickbeard.FILE_LOGGING_PRESET = file_logging_preset
        sickbeard.SHOWLIST_TAGVIEW = showlist_tagview

        # 'Show List' is the must have default fallback. Tags in use that are removed from config ui are restored, not deleted.
        # Deduped list order preservation is key to feature function.
        myDB = db.DBConnection()
        sql_results = myDB.select('SELECT DISTINCT tag FROM tv_shows')
        new_names = [u'' + v.strip() for v in (show_tags.split(u','), [])[None is show_tags] if v.strip()]
        orphans = [item for item in [v['tag'] for v in sql_results or []] if item not in new_names]
        cleanser = []
        if 0 < len(orphans):
            cleanser = [item for item in sickbeard.SHOW_TAGS if item in orphans or item in new_names]
            results += [u'An attempt was prevented to remove a show list group name still in use']
        dedupe = {}
        sickbeard.SHOW_TAGS = [dedupe.setdefault(item, item) for item in (cleanser + new_names + [u'Show List'])
                               if item not in dedupe]

        logger.log_set_level()

        sickbeard.ANON_REDIRECT = anon_redirect
        sickbeard.PROXY_SETTING = proxy_setting
        sickbeard.PROXY_INDEXERS = config.checkbox_to_value(proxy_indexers)
        sickbeard.GIT_PATH = git_path
        sickbeard.GIT_REMOTE = git_remote
        sickbeard.CALENDAR_UNPROTECTED = config.checkbox_to_value(calendar_unprotected)
        # sickbeard.LOG_DIR is set in config.change_LOG_DIR()

        sickbeard.WEB_PORT = config.to_int(web_port)
        sickbeard.WEB_IPV6 = config.checkbox_to_value(web_ipv6)
        # sickbeard.WEB_LOG is set in config.change_LOG_DIR()
        sickbeard.ENCRYPTION_VERSION = config.checkbox_to_value(encryption_version)

        reload_page = False

        if sickbeard.WEB_USERNAME != web_username:
            sickbeard.WEB_USERNAME = web_username
            reload_page = True

        if set('*') != set(web_password):
            sickbeard.WEB_PASSWORD = web_password
            reload_page = True

        sickbeard.FUZZY_DATING = config.checkbox_to_value(fuzzy_dating)
        sickbeard.TRIM_ZERO = config.checkbox_to_value(trim_zero)

        if date_preset:
            sickbeard.DATE_PRESET = date_preset

        if indexer_default:
            sickbeard.INDEXER_DEFAULT = config.to_int(indexer_default)
            if not sickbeard.indexerApi(sickbeard.INDEXER_DEFAULT).config['active']:
                sickbeard.INDEXER_DEFAULT = INDEXER_TVDB

        if indexer_timeout:
            sickbeard.INDEXER_TIMEOUT = config.to_int(indexer_timeout)

        if time_preset:
            sickbeard.TIME_PRESET_W_SECONDS = time_preset
            sickbeard.TIME_PRESET = sickbeard.TIME_PRESET_W_SECONDS.replace(u':%S', u'')

        sickbeard.TIMEZONE_DISPLAY = timezone_display

        if not config.change_LOG_DIR(log_dir, web_log):
            results += ['Unable to create directory ' + os.path.normpath(log_dir) + ', log directory not changed.']

        sickbeard.USE_API = config.checkbox_to_value(use_api)
        sickbeard.API_KEY = api_key

        sickbeard.ENABLE_HTTPS = config.checkbox_to_value(enable_https)

        if not config.change_HTTPS_CERT(https_cert):
            results += [
                'Unable to create directory ' + os.path.normpath(https_cert) + ', https cert directory not changed.']

        if not config.change_HTTPS_KEY(https_key):
            results += [
                'Unable to create directory ' + os.path.normpath(https_key) + ', https key directory not changed.']

        sickbeard.HANDLE_REVERSE_PROXY = config.checkbox_to_value(handle_reverse_proxy)

        sickbeard.THEME_NAME = theme_name
        sickbeard.DEFAULT_HOME = default_home

        sickbeard.save_config()

        if len(results) > 0:
            for v in results:
                logger.log(v, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        if reload_page:
            self.clear_cookie('sickgear-session')
            self.write('reload')

    @staticmethod
    def fetch_pullrequests():
        if sickbeard.BRANCH == 'master':
            return json.dumps({'result': 'success', 'pulls': []})
        else:
            try:
                pulls = sickbeard.versionCheckScheduler.action.list_remote_pulls()
                return json.dumps({'result': 'success', 'pulls': pulls})
            except Exception as e:
                logger.log(u'exception msg: ' + str(e), logger.DEBUG)
                return json.dumps({'result': 'fail'})

    @staticmethod
    def fetch_branches():
        try:
            branches = sickbeard.versionCheckScheduler.action.list_remote_branches()
            return json.dumps({'result': 'success', 'branches': branches, 'current': sickbeard.BRANCH or 'master'})
        except Exception as e:
            logger.log(u'exception msg: ' + str(e), logger.DEBUG)
            return json.dumps({'result': 'fail'})


class ConfigSearch(Config):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='config_search.tmpl')
        t.submenu = self.ConfigMenu
        t.using_rls_ignore_words = [(show.indexerid, show.name)
                                    for show in sickbeard.showList if show.rls_ignore_words and
                                    show.rls_ignore_words.strip()]
        t.using_rls_ignore_words.sort(lambda x, y: cmp(x[1], y[1]), reverse=False)
        t.using_rls_require_words = [(show.indexerid, show.name)
                                     for show in sickbeard.showList if show.rls_require_words and
                                     show.rls_require_words.strip()]
        t.using_rls_require_words.sort(lambda x, y: cmp(x[1], y[1]), reverse=False)
        t.propers_intervals = search_propers.ProperSearcher().search_intervals
        return t.respond()

    def saveSearch(self, use_nzbs=None, use_torrents=None, nzb_dir=None, sab_username=None, sab_password=None,
                   sab_apikey=None, sab_category=None, sab_host=None, nzbget_username=None, nzbget_password=None,
                   nzbget_category=None, nzbget_priority=None, nzbget_host=None, nzbget_use_https=None,
                   backlog_days=None, backlog_frequency=None, search_unaired=None, unaired_recent_search_only=None,
                   recentsearch_frequency=None, nzb_method=None, torrent_method=None, usenet_retention=None,
                   download_propers=None, check_propers_interval=None, allow_high_priority=None,
                   torrent_dir=None, torrent_username=None, torrent_password=None, torrent_host=None,
                   torrent_label=None, torrent_path=None, torrent_verify_cert=None,
                   torrent_seed_time=None, torrent_paused=None, torrent_high_bandwidth=None, ignore_words=None, require_words=None):

        results = []

        if not config.change_NZB_DIR(nzb_dir):
            results += ['Unable to create directory ' + os.path.normpath(nzb_dir) + ', dir not changed.']

        if not config.change_TORRENT_DIR(torrent_dir):
            results += ['Unable to create directory ' + os.path.normpath(torrent_dir) + ', dir not changed.']

        config.change_RECENTSEARCH_FREQUENCY(recentsearch_frequency)

        old_backlog_frequency = sickbeard.BACKLOG_FREQUENCY
        config.change_BACKLOG_FREQUENCY(backlog_frequency)
        sickbeard.search_backlog.BacklogSearcher.change_backlog_parts(old_backlog_frequency, sickbeard.BACKLOG_FREQUENCY)
        sickbeard.BACKLOG_DAYS = config.to_int(backlog_days, default=7)

        sickbeard.USE_NZBS = config.checkbox_to_value(use_nzbs)
        sickbeard.USE_TORRENTS = config.checkbox_to_value(use_torrents)

        sickbeard.NZB_METHOD = nzb_method
        sickbeard.TORRENT_METHOD = torrent_method
        sickbeard.USENET_RETENTION = config.to_int(usenet_retention, default=500)

        sickbeard.IGNORE_WORDS = ignore_words if ignore_words else ''
        sickbeard.REQUIRE_WORDS = require_words if require_words else ''

        sickbeard.DOWNLOAD_PROPERS = config.checkbox_to_value(download_propers)
        if sickbeard.CHECK_PROPERS_INTERVAL != check_propers_interval:
            sickbeard.CHECK_PROPERS_INTERVAL = check_propers_interval

            if sickbeard.DOWNLOAD_PROPERS:
                proper_sch = sickbeard.properFinderScheduler
                item = [(k, n, v) for (k, n, v) in proper_sch.action.search_intervals if k == check_propers_interval]
                if item and None is proper_sch.start_time:
                    interval = datetime.timedelta(minutes=item[0][2])
                    run_in = proper_sch.lastRun + interval - datetime.datetime.now()
                    proper_sch.cycleTime = interval

                    run_at = 'imminent'
                    if datetime.timedelta() < run_in:
                        hours, remainder = divmod(run_in.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        run_at = u'in approx. ' + ('%dh, %dm' % (hours, minutes) if 0 < hours else
                                                   '%dm, %ds' % (minutes, seconds))
                    logger.log(u'Change search PROPERS interval, next check %s' % run_at)

        sickbeard.SEARCH_UNAIRED = bool(config.checkbox_to_value(search_unaired))
        sickbeard.UNAIRED_RECENT_SEARCH_ONLY = bool(config.checkbox_to_value(unaired_recent_search_only, value_off=1, value_on=0))

        sickbeard.ALLOW_HIGH_PRIORITY = config.checkbox_to_value(allow_high_priority)

        sickbeard.SAB_USERNAME = sab_username
        if set('*') != set(sab_password):
            sickbeard.SAB_PASSWORD = sab_password
        key = sab_apikey.strip()
        if not starify(key, True):
            sickbeard.SAB_APIKEY = key
        sickbeard.SAB_CATEGORY = sab_category
        sickbeard.SAB_HOST = config.clean_url(sab_host)

        sickbeard.NZBGET_USERNAME = nzbget_username
        if set('*') != set(nzbget_password):
            sickbeard.NZBGET_PASSWORD = nzbget_password
        sickbeard.NZBGET_CATEGORY = nzbget_category
        sickbeard.NZBGET_HOST = config.clean_host(nzbget_host)
        sickbeard.NZBGET_USE_HTTPS = config.checkbox_to_value(nzbget_use_https)
        sickbeard.NZBGET_PRIORITY = config.to_int(nzbget_priority, default=100)

        sickbeard.TORRENT_USERNAME = torrent_username
        if set('*') != set(torrent_password):
            sickbeard.TORRENT_PASSWORD = torrent_password
        sickbeard.TORRENT_LABEL = torrent_label
        sickbeard.TORRENT_VERIFY_CERT = config.checkbox_to_value(torrent_verify_cert)
        sickbeard.TORRENT_PATH = torrent_path
        sickbeard.TORRENT_SEED_TIME = config.to_int(torrent_seed_time, 0)
        sickbeard.TORRENT_PAUSED = config.checkbox_to_value(torrent_paused)
        sickbeard.TORRENT_HIGH_BANDWIDTH = config.checkbox_to_value(torrent_high_bandwidth)
        sickbeard.TORRENT_HOST = config.clean_url(torrent_host)

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/search/')


class ConfigPostProcessing(Config):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='config_postProcessing.tmpl')
        t.submenu = self.ConfigMenu
        return t.respond()

    def savePostProcessing(self, naming_pattern=None, naming_multi_ep=None,
                           xbmc_data=None, xbmc_12plus_data=None, mediabrowser_data=None, sony_ps3_data=None,
                           wdtv_data=None, tivo_data=None, mede8er_data=None, kodi_data=None,
                           keep_processed_dir=None, process_method=None, process_automatically=None,
                           rename_episodes=None, airdate_episodes=None, unpack=None,
                           move_associated_files=None, postpone_if_sync_files=None, nfo_rename=None, tv_download_dir=None, naming_custom_abd=None,
                           naming_anime=None,
                           naming_abd_pattern=None, naming_strip_year=None, use_failed_downloads=None,
                           delete_failed=None, extra_scripts=None, skip_removed_files=None,
                           naming_custom_sports=None, naming_sports_pattern=None,
                           naming_custom_anime=None, naming_anime_pattern=None, naming_anime_multi_ep=None,
                           autopostprocesser_frequency=None):

        results = []

        if not config.change_TV_DOWNLOAD_DIR(tv_download_dir):
            results += ['Unable to create directory ' + os.path.normpath(tv_download_dir) + ', dir not changed.']

        new_val = config.checkbox_to_value(process_automatically)
        if new_val != sickbeard.PROCESS_AUTOMATICALLY:
            if not sickbeard.PROCESS_AUTOMATICALLY and not sickbeard.autoPostProcesserScheduler.ident:
                try:
                    sickbeard.autoPostProcesserScheduler.start()
                except:
                    pass
            sickbeard.PROCESS_AUTOMATICALLY = new_val

        config.change_AUTOPOSTPROCESSER_FREQUENCY(autopostprocesser_frequency)

        if sickbeard.PROCESS_AUTOMATICALLY:
            sickbeard.autoPostProcesserScheduler.silent = False
        else:
            sickbeard.autoPostProcesserScheduler.silent = True

        if unpack:
            if self.isRarSupported() != 'not supported':
                sickbeard.UNPACK = config.checkbox_to_value(unpack)
            else:
                sickbeard.UNPACK = 0
                results.append('Unpacking Not Supported, disabling unpack setting')
        else:
            sickbeard.UNPACK = config.checkbox_to_value(unpack)

        sickbeard.KEEP_PROCESSED_DIR = config.checkbox_to_value(keep_processed_dir)
        sickbeard.PROCESS_METHOD = process_method
        sickbeard.EXTRA_SCRIPTS = [x.strip() for x in extra_scripts.split('|') if x.strip()]
        sickbeard.RENAME_EPISODES = config.checkbox_to_value(rename_episodes)
        sickbeard.AIRDATE_EPISODES = config.checkbox_to_value(airdate_episodes)
        sickbeard.MOVE_ASSOCIATED_FILES = config.checkbox_to_value(move_associated_files)
        sickbeard.POSTPONE_IF_SYNC_FILES = config.checkbox_to_value(postpone_if_sync_files)
        sickbeard.NAMING_CUSTOM_ABD = config.checkbox_to_value(naming_custom_abd)
        sickbeard.NAMING_CUSTOM_SPORTS = config.checkbox_to_value(naming_custom_sports)
        sickbeard.NAMING_CUSTOM_ANIME = config.checkbox_to_value(naming_custom_anime)
        sickbeard.NAMING_STRIP_YEAR = config.checkbox_to_value(naming_strip_year)
        sickbeard.USE_FAILED_DOWNLOADS = config.checkbox_to_value(use_failed_downloads)
        sickbeard.DELETE_FAILED = config.checkbox_to_value(delete_failed)
        sickbeard.SKIP_REMOVED_FILES = config.minimax(skip_removed_files, IGNORED, 1, IGNORED)
        sickbeard.NFO_RENAME = config.checkbox_to_value(nfo_rename)

        sickbeard.METADATA_XBMC = xbmc_data
        sickbeard.METADATA_XBMC_12PLUS = xbmc_12plus_data
        sickbeard.METADATA_MEDIABROWSER = mediabrowser_data
        sickbeard.METADATA_PS3 = sony_ps3_data
        sickbeard.METADATA_WDTV = wdtv_data
        sickbeard.METADATA_TIVO = tivo_data
        sickbeard.METADATA_MEDE8ER = mede8er_data
        sickbeard.METADATA_KODI = kodi_data

        sickbeard.metadata_provider_dict['XBMC'].set_config(sickbeard.METADATA_XBMC)
        sickbeard.metadata_provider_dict['XBMC 12+'].set_config(sickbeard.METADATA_XBMC_12PLUS)
        sickbeard.metadata_provider_dict['MediaBrowser'].set_config(sickbeard.METADATA_MEDIABROWSER)
        sickbeard.metadata_provider_dict['Sony PS3'].set_config(sickbeard.METADATA_PS3)
        sickbeard.metadata_provider_dict['WDTV'].set_config(sickbeard.METADATA_WDTV)
        sickbeard.metadata_provider_dict['TIVO'].set_config(sickbeard.METADATA_TIVO)
        sickbeard.metadata_provider_dict['Mede8er'].set_config(sickbeard.METADATA_MEDE8ER)
        sickbeard.metadata_provider_dict['Kodi'].set_config(sickbeard.METADATA_KODI)

        if self.isNamingValid(naming_pattern, naming_multi_ep, anime_type=naming_anime) != 'invalid':
            sickbeard.NAMING_PATTERN = naming_pattern
            sickbeard.NAMING_MULTI_EP = int(naming_multi_ep)
            sickbeard.NAMING_ANIME = int(naming_anime)
            sickbeard.NAMING_FORCE_FOLDERS = naming.check_force_season_folders()
        else:
            if int(naming_anime) in [1, 2]:
                results.append('You tried saving an invalid anime naming config, not saving your naming settings')
            else:
                results.append('You tried saving an invalid naming config, not saving your naming settings')

        if self.isNamingValid(naming_anime_pattern, naming_anime_multi_ep, anime_type=naming_anime) != 'invalid':
            sickbeard.NAMING_ANIME_PATTERN = naming_anime_pattern
            sickbeard.NAMING_ANIME_MULTI_EP = int(naming_anime_multi_ep)
            sickbeard.NAMING_ANIME = int(naming_anime)
            sickbeard.NAMING_FORCE_FOLDERS = naming.check_force_season_folders()
        else:
            if int(naming_anime) in [1, 2]:
                results.append('You tried saving an invalid anime naming config, not saving your naming settings')
            else:
                results.append('You tried saving an invalid naming config, not saving your naming settings')

        if self.isNamingValid(naming_abd_pattern, None, abd=True) != 'invalid':
            sickbeard.NAMING_ABD_PATTERN = naming_abd_pattern
        else:
            results.append(
                'You tried saving an invalid air-by-date naming config, not saving your air-by-date settings')

        if self.isNamingValid(naming_sports_pattern, None, sports=True) != 'invalid':
            sickbeard.NAMING_SPORTS_PATTERN = naming_sports_pattern
        else:
            results.append(
                'You tried saving an invalid sports naming config, not saving your sports settings')

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/postProcessing/')

    def testNaming(self, pattern=None, multi=None, abd=False, sports=False, anime=False, anime_type=None):

        if multi is not None:
            multi = int(multi)

        if anime_type is not None:
            anime_type = int(anime_type)

        result = naming.test_name(pattern, multi, abd, sports, anime, anime_type)

        result = ek.ek(os.path.join, result['dir'], result['name'])

        return result

    def isNamingValid(self, pattern=None, multi=None, abd=False, sports=False, anime=False, anime_type=None):
        if pattern is None:
            return 'invalid'

        if multi is not None:
            multi = int(multi)

        if anime_type is not None:
            anime_type = int(anime_type)

        # air by date shows just need one check, we don't need to worry about season folders
        if abd:
            is_valid = naming.check_valid_abd_naming(pattern)
            require_season_folders = False

        # sport shows just need one check, we don't need to worry about season folders
        elif sports:
            is_valid = naming.check_valid_sports_naming(pattern)
            require_season_folders = False

        else:
            # check validity of single and multi ep cases for the whole path
            is_valid = naming.check_valid_naming(pattern, multi, anime_type)

            # check validity of single and multi ep cases for only the file name
            require_season_folders = naming.check_force_season_folders(pattern, multi, anime_type)

        if is_valid and not require_season_folders:
            return 'valid'
        elif is_valid and require_season_folders:
            return 'seasonfolders'
        else:
            return 'invalid'

    def isRarSupported(self, *args, **kwargs):
        """
        Test Packing Support:
        """

        try:
            if 'win32' == sys.platform:
                rarfile.UNRAR_TOOL = ek.ek(os.path.join, sickbeard.PROG_DIR, 'lib', 'rarfile', 'UnRAR.exe')
            rar_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'lib', 'rarfile', 'test.rar')
            if 'This is only a test.' == rarfile.RarFile(rar_path).read(r'test\test.txt'):
                return 'supported'
            msg = 'Could not read test file content'
        except Exception as e:
            msg = ex(e)

        logger.log(u'Rar Not Supported: %s' % msg, logger.ERROR)
        return 'not supported'


class ConfigProviders(Config):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='config_providers.tmpl')
        t.submenu = self.ConfigMenu
        return t.respond()

    def canAddNewznabProvider(self, name):

        if not name:
            return json.dumps({'error': 'No Provider Name specified'})

        providerDict = dict(zip([x.get_id() for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))

        tempProvider = newznab.NewznabProvider(name, '')

        if tempProvider.get_id() in providerDict:
            return json.dumps({'error': 'Provider Name already exists as ' + providerDict[tempProvider.get_id()].name})
        else:
            return json.dumps({'success': tempProvider.get_id()})

    def saveNewznabProvider(self, name, url, key=''):

        if not name or not url:
            return '0'

        providerDict = dict(zip([x.name for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))

        if name in providerDict:
            if not providerDict[name].default:
                providerDict[name].name = name
                providerDict[name].url = config.clean_url(url)

            providerDict[name].key = key
            # a 0 in the key spot indicates that no key is needed
            providerDict[name].needs_auth = '0' != key

            return providerDict[name].get_id() + '|' + providerDict[name].config_str()

        else:
            newProvider = newznab.NewznabProvider(name, url, key=key)
            sickbeard.newznabProviderList.append(newProvider)
            return newProvider.get_id() + '|' + newProvider.config_str()

    def getNewznabCategories(self, name, url, key):
        """
        Retrieves a list of possible categories with category id's
        Using the default url/api?cat
        http://yournewznaburl.com/api?t=caps&apikey=yourapikey
        """

        error = not name and 'Name' or not url and 'Url' or not key and 'Apikey' or ''
        if error:
            error = '\nNo provider %s specified' % error
            return json.dumps({'success': False, 'error': error})

        if name in [n.name for n in sickbeard.newznabProviderList if n.url == url]:
            tv_categories = newznab.NewznabProvider.clean_newznab_categories([n for n in sickbeard.newznabProviderList if n.name == name][0].all_cats)
        else:
            providers = dict(zip([x.get_id() for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))
            temp_provider = newznab.NewznabProvider(name, url, key)
            if None is not key and starify(key, True):
                temp_provider.key = providers[temp_provider.get_id()].key

            tv_categories = newznab.NewznabProvider.clean_newznab_categories(temp_provider.all_cats)

        return json.dumps({'success': True, 'tv_categories': tv_categories, 'error': ''})

    def deleteNewznabProvider(self, nnid):

        providerDict = dict(zip([x.get_id() for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))

        if nnid not in providerDict or providerDict[nnid].default:
            return '0'

        # delete it from the list
        sickbeard.newznabProviderList.remove(providerDict[nnid])

        if nnid in sickbeard.PROVIDER_ORDER:
            sickbeard.PROVIDER_ORDER.remove(nnid)

        return '1'

    def canAddTorrentRssProvider(self, name, url, cookies):

        if not name:
            return json.dumps({'error': 'Invalid name specified'})

        providerDict = dict(
            zip([x.get_id() for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        tempProvider = rsstorrent.TorrentRssProvider(name, url, cookies)

        if tempProvider.get_id() in providerDict:
            return json.dumps({'error': 'A provider exists as [%s]' % providerDict[tempProvider.get_id()].name})
        else:
            (succ, errMsg) = tempProvider.validate_feed()
            if succ:
                return json.dumps({'success': tempProvider.get_id()})
            else:
                return json.dumps({'error': errMsg})

    def saveTorrentRssProvider(self, name, url, cookies):

        if not name or not url:
            return '0'

        providerDict = dict(zip([x.name for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        if name in providerDict:
            providerDict[name].name = name
            providerDict[name].url = config.clean_url(url)
            providerDict[name].cookies = cookies

            return providerDict[name].get_id() + '|' + providerDict[name].config_str()

        else:
            newProvider = rsstorrent.TorrentRssProvider(name, url, cookies)
            sickbeard.torrentRssProviderList.append(newProvider)
            return newProvider.get_id() + '|' + newProvider.config_str()

    def deleteTorrentRssProvider(self, id):

        providerDict = dict(
            zip([x.get_id() for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        if id not in providerDict:
            return '0'

        # delete it from the list
        sickbeard.torrentRssProviderList.remove(providerDict[id])

        if id in sickbeard.PROVIDER_ORDER:
            sickbeard.PROVIDER_ORDER.remove(id)

        return '1'

    def saveProviders(self, newznab_string='', torrentrss_string='', provider_order=None, **kwargs):

        results = []
        provider_list = []

        # add all the newznab info we have into our list
        newznab_sources = dict(zip([x.get_id() for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))
        active_ids = []
        if newznab_string:
            for curNewznabProviderStr in newznab_string.split('!!!'):

                if not curNewznabProviderStr:
                    continue

                cur_name, cur_url, cur_key, cur_cat = curNewznabProviderStr.split('|')
                cur_url = config.clean_url(cur_url)

                if starify(cur_key, True):
                    cur_key = ''

                new_provider = newznab.NewznabProvider(cur_name, cur_url, key=cur_key)

                cur_id = new_provider.get_id()

                # if it already exists then update it
                if cur_id in newznab_sources:
                    nzb_src = newznab_sources[cur_id]

                    nzb_src.name, nzb_src.url, nzb_src.cat_ids = cur_name, cur_url, cur_cat

                    if cur_key:
                        nzb_src.key = cur_key

                    # a 0 in the key spot indicates that no key is needed
                    nzb_src.needs_auth = '0' != cur_key

                    attr = 'search_mode'
                    if cur_id + '_' + attr in kwargs:
                        setattr(nzb_src, attr, str(kwargs.get(cur_id + '_' + attr)).strip())

                    for attr in ['search_fallback', 'enable_recentsearch', 'enable_backlog']:
                        setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(cur_id + '_' + attr)))

                else:
                    sickbeard.newznabProviderList.append(new_provider)

                active_ids.append(cur_id)

        # delete anything that is missing
        for source in [x for x in sickbeard.newznabProviderList if x.get_id() not in active_ids]:
            sickbeard.newznabProviderList.remove(source)

        # add all the torrent RSS info we have into our list
        torrent_rss_sources = dict(zip([x.get_id() for x in sickbeard.torrentRssProviderList],
                                       sickbeard.torrentRssProviderList))
        active_ids = []
        if torrentrss_string:
            for curTorrentRssProviderStr in torrentrss_string.split('!!!'):

                if not curTorrentRssProviderStr:
                    continue

                cur_name, cur_url, cur_cookies = curTorrentRssProviderStr.split('|')
                cur_url = config.clean_url(cur_url, False)

                if starify(cur_cookies, True):
                    cur_cookies = ''

                new_provider = rsstorrent.TorrentRssProvider(cur_name, cur_url, cur_cookies)

                cur_id = new_provider.get_id()

                # if it already exists then update it
                if cur_id in torrent_rss_sources:
                    torrent_rss_sources[cur_id].name = cur_name
                    torrent_rss_sources[cur_id].url = cur_url
                    if cur_cookies:
                        torrent_rss_sources[cur_id].cookies = cur_cookies
                else:
                    sickbeard.torrentRssProviderList.append(new_provider)

                active_ids.append(cur_id)

        # delete anything that is missing
        for source in [x for x in sickbeard.torrentRssProviderList if x.get_id() not in active_ids]:
            sickbeard.torrentRssProviderList.remove(source)

        # enable/disable states of source providers
        provider_str_list = provider_order.split()
        sources = dict(zip([x.get_id() for x in sickbeard.providers.sortedProviderList()],
                           sickbeard.providers.sortedProviderList()))
        for cur_src_str in provider_str_list:
            src_name, src_enabled = cur_src_str.split(':')

            provider_list.append(src_name)
            src_enabled = bool(config.to_int(src_enabled))

            if src_name in sources and hasattr(sources[src_name], 'enabled'):
                sources[src_name].enabled = src_enabled

            if src_name in newznab_sources:
                newznab_sources[src_name].enabled = src_enabled
            elif src_name in torrent_rss_sources:
                torrent_rss_sources[src_name].enabled = src_enabled

        # update torrent source settings
        for torrent_src in [src for src in sickbeard.providers.sortedProviderList()
                            if sickbeard.GenericProvider.TORRENT == src.providerType]:
            src_id_prefix = torrent_src.get_id() + '_'

            attr = 'url_edit'
            if getattr(torrent_src, attr, None):
                url_edit = ','.join(set(['%s' % url.strip() for url in kwargs.get(
                    src_id_prefix + attr, '').split(',')]))
                torrent_src.url_home = ([url_edit], [])[not url_edit]

            for attr in [x for x in ['username', 'uid'] if hasattr(torrent_src, x)]:
                setattr(torrent_src, attr, str(kwargs.get(src_id_prefix + attr, '')).strip())

            for attr in [x for x in ['password', 'api_key', 'passkey', 'digest', 'hash'] if hasattr(torrent_src, x)]:
                key = str(kwargs.get(src_id_prefix + attr, '')).strip()
                if 'password' == attr:
                    set('*') != set(key) and setattr(torrent_src, attr, key)
                elif not starify(key, True):
                    setattr(torrent_src, attr, key)

            attr = 'ratio'
            if hasattr(torrent_src, '_seed_' + attr) and src_id_prefix + attr in kwargs:
                setattr(torrent_src, '_seed_' + attr, kwargs.get(src_id_prefix + attr, '').strip() or None)

            for attr in [x for x in ['minseed', 'minleech'] if hasattr(torrent_src, x)]:
                setattr(torrent_src, attr, config.to_int(str(kwargs.get(src_id_prefix + attr)).strip()))

            for attr in [x for x in ['confirmed', 'freeleech', 'reject_m2ts', 'enable_recentsearch',
                                     'enable_backlog', 'search_fallback']
                         if hasattr(torrent_src, x) and src_id_prefix + attr in kwargs]:
                setattr(torrent_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)))

            attr = 'seed_time'
            if hasattr(torrent_src, attr) and src_id_prefix + attr in kwargs:
                setattr(torrent_src, attr, config.to_int(str(kwargs.get(src_id_prefix + attr)).strip()))

            attr = 'search_mode'
            if hasattr(torrent_src, attr):
                setattr(torrent_src, attr, str(kwargs.get(src_id_prefix + attr, '')).strip() or 'eponly')

            attr = 'filter'
            if hasattr(torrent_src, attr):
                setattr(torrent_src, attr,
                        [k for k in torrent_src.may_filter.keys()
                         if config.checkbox_to_value(kwargs.get('%sfilter_%s' % (src_id_prefix, k)))])

        # update nzb source settings
        for nzb_src in [src for src in sickbeard.providers.sortedProviderList() if
                        sickbeard.GenericProvider.NZB == src.providerType]:
            src_id_prefix = nzb_src.get_id() + '_'

            attr = 'api_key'
            if hasattr(nzb_src, attr):
                key = str(kwargs.get(src_id_prefix + attr, '')).strip()
                if not starify(key, True):
                    setattr(nzb_src, attr, key)

            attr = 'username'
            if hasattr(nzb_src, attr):
                setattr(nzb_src, attr, str(kwargs.get(src_id_prefix + attr, '')).strip() or None)

            attr = 'search_mode'
            if hasattr(nzb_src, attr):
                setattr(nzb_src, attr, str(kwargs.get(src_id_prefix + attr, '')).strip() or 'eponly')

            attr = 'enable_recentsearch'
            if hasattr(nzb_src, attr):
                setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)) or
                        not getattr(nzb_src, 'supports_backlog', True))

            for attr in [x for x in ['search_fallback', 'enable_backlog'] if hasattr(nzb_src, x)]:
                setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)))

        sickbeard.NEWZNAB_DATA = '!!!'.join([x.config_str() for x in sickbeard.newznabProviderList])
        sickbeard.PROVIDER_ORDER = provider_list

        helpers.clear_unused_providers()

        sickbeard.save_config()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration', '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/providers/')


class ConfigNotifications(Config):

    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='config_notifications.tmpl')
        t.submenu = self.ConfigMenu
        t.root_dirs = []
        if sickbeard.ROOT_DIRS:
            root_pieces = sickbeard.ROOT_DIRS.split('|')
            root_default = helpers.tryInt(root_pieces[0], None)
            for i, location in enumerate(root_pieces[1:]):
                t.root_dirs.append({'root_def': root_default and i == root_default,
                                    'loc': location,
                                    'b64': base64.urlsafe_b64encode(location)})
        return t.respond()

    def saveNotifications(self,
                          use_emby=None, emby_update_library=None, emby_host=None, emby_apikey=None,
                          use_kodi=None, kodi_always_on=None, kodi_notify_onsnatch=None, kodi_notify_ondownload=None,
                          kodi_notify_onsubtitledownload=None, kodi_update_onlyfirst=None,
                          kodi_update_library=None, kodi_update_full=None,
                          kodi_host=None, kodi_username=None, kodi_password=None,
                          use_xbmc=None, xbmc_always_on=None, xbmc_notify_onsnatch=None, xbmc_notify_ondownload=None,
                          xbmc_notify_onsubtitledownload=None, xbmc_update_onlyfirst=None,
                          xbmc_update_library=None, xbmc_update_full=None,
                          xbmc_host=None, xbmc_username=None, xbmc_password=None,
                          use_plex=None, plex_notify_onsnatch=None, plex_notify_ondownload=None,
                          plex_notify_onsubtitledownload=None, plex_update_library=None,
                          plex_server_host=None, plex_host=None, plex_username=None, plex_password=None,
                          use_growl=None, growl_notify_onsnatch=None, growl_notify_ondownload=None,
                          growl_notify_onsubtitledownload=None, growl_host=None, growl_password=None,
                          use_prowl=None, prowl_notify_onsnatch=None, prowl_notify_ondownload=None,
                          prowl_notify_onsubtitledownload=None, prowl_api=None, prowl_priority=0,
                          use_twitter=None, twitter_notify_onsnatch=None, twitter_notify_ondownload=None,
                          twitter_notify_onsubtitledownload=None,
                          use_boxcar2=None, boxcar2_notify_onsnatch=None, boxcar2_notify_ondownload=None,
                          boxcar2_notify_onsubtitledownload=None, boxcar2_accesstoken=None, boxcar2_sound=None,
                          use_pushover=None, pushover_notify_onsnatch=None, pushover_notify_ondownload=None,
                          pushover_notify_onsubtitledownload=None, pushover_userkey=None, pushover_apikey=None,
                          pushover_priority=None, pushover_device=None, pushover_sound=None, pushover_device_list=None,
                          use_libnotify=None, libnotify_notify_onsnatch=None, libnotify_notify_ondownload=None,
                          libnotify_notify_onsubtitledownload=None,
                          use_nmj=None, nmj_host=None, nmj_database=None, nmj_mount=None, use_synoindex=None,
                          use_nmjv2=None, nmjv2_host=None, nmjv2_dbloc=None, nmjv2_database=None,
                          use_trakt=None, trakt_pin=None,
                          trakt_remove_watchlist=None, trakt_use_watchlist=None, trakt_method_add=None,
                          trakt_start_paused=None, trakt_sync=None,
                          trakt_default_indexer=None, trakt_remove_serieslist=None, trakt_collection=None, trakt_accounts=None,
                          use_synologynotifier=None, synologynotifier_notify_onsnatch=None,
                          synologynotifier_notify_ondownload=None, synologynotifier_notify_onsubtitledownload=None,
                          use_pytivo=None, pytivo_notify_onsnatch=None, pytivo_notify_ondownload=None,
                          pytivo_notify_onsubtitledownload=None, pytivo_update_library=None,
                          pytivo_host=None, pytivo_share_name=None, pytivo_tivo_name=None,
                          use_nma=None, nma_notify_onsnatch=None, nma_notify_ondownload=None,
                          nma_notify_onsubtitledownload=None, nma_api=None, nma_priority=0,
                          use_pushalot=None, pushalot_notify_onsnatch=None, pushalot_notify_ondownload=None,
                          pushalot_notify_onsubtitledownload=None, pushalot_authorizationtoken=None,
                          use_pushbullet=None, pushbullet_notify_onsnatch=None, pushbullet_notify_ondownload=None,
                          pushbullet_notify_onsubtitledownload=None, pushbullet_access_token=None,
                          pushbullet_device_iden=None, pushbullet_device_list=None,
                          use_email=None, email_notify_onsnatch=None, email_notify_ondownload=None,
                          email_notify_onsubtitledownload=None, email_host=None, email_port=25, email_from=None,
                          email_tls=None, email_user=None, email_password=None, email_list=None, email_show_list=None,
                          email_show=None, **kwargs):

        results = []

        sickbeard.USE_EMBY = config.checkbox_to_value(use_emby)
        sickbeard.EMBY_UPDATE_LIBRARY = config.checkbox_to_value(emby_update_library)
        sickbeard.EMBY_HOST = config.clean_hosts(emby_host)
        keys_changed = False
        all_keys = []
        old_keys = [x.strip() for x in sickbeard.EMBY_APIKEY.split(',') if x.strip()]
        new_keys = [x.strip() for x in emby_apikey.split(',') if x.strip()]
        for key in new_keys:
            if not starify(key, True):
                keys_changed = True
                all_keys += [key]
                continue
            for x in old_keys:
                if key.startswith(x[0:3]) and key.endswith(x[-4:]):
                    all_keys += [x]
                    break
        if keys_changed or (len(all_keys) != len(old_keys)):
            sickbeard.EMBY_APIKEY = ','.join(all_keys)

        sickbeard.USE_KODI = config.checkbox_to_value(use_kodi)
        sickbeard.KODI_ALWAYS_ON = config.checkbox_to_value(kodi_always_on)
        sickbeard.KODI_NOTIFY_ONSNATCH = config.checkbox_to_value(kodi_notify_onsnatch)
        sickbeard.KODI_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(kodi_notify_ondownload)
        sickbeard.KODI_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(kodi_notify_onsubtitledownload)
        sickbeard.KODI_UPDATE_LIBRARY = config.checkbox_to_value(kodi_update_library)
        sickbeard.KODI_UPDATE_FULL = config.checkbox_to_value(kodi_update_full)
        sickbeard.KODI_UPDATE_ONLYFIRST = config.checkbox_to_value(kodi_update_onlyfirst)
        sickbeard.KODI_HOST = config.clean_hosts(kodi_host)
        sickbeard.KODI_USERNAME = kodi_username
        if set('*') != set(kodi_password):
            sickbeard.KODI_PASSWORD = kodi_password

        sickbeard.USE_XBMC = config.checkbox_to_value(use_xbmc)
        sickbeard.XBMC_ALWAYS_ON = config.checkbox_to_value(xbmc_always_on)
        sickbeard.XBMC_NOTIFY_ONSNATCH = config.checkbox_to_value(xbmc_notify_onsnatch)
        sickbeard.XBMC_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(xbmc_notify_ondownload)
        sickbeard.XBMC_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(xbmc_notify_onsubtitledownload)
        sickbeard.XBMC_UPDATE_LIBRARY = config.checkbox_to_value(xbmc_update_library)
        sickbeard.XBMC_UPDATE_FULL = config.checkbox_to_value(xbmc_update_full)
        sickbeard.XBMC_UPDATE_ONLYFIRST = config.checkbox_to_value(xbmc_update_onlyfirst)
        sickbeard.XBMC_HOST = config.clean_hosts(xbmc_host)
        sickbeard.XBMC_USERNAME = xbmc_username
        if set('*') != set(xbmc_password):
            sickbeard.XBMC_PASSWORD = xbmc_password

        sickbeard.USE_PLEX = config.checkbox_to_value(use_plex)
        sickbeard.PLEX_NOTIFY_ONSNATCH = config.checkbox_to_value(plex_notify_onsnatch)
        sickbeard.PLEX_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(plex_notify_ondownload)
        sickbeard.PLEX_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(plex_notify_onsubtitledownload)
        sickbeard.PLEX_UPDATE_LIBRARY = config.checkbox_to_value(plex_update_library)
        sickbeard.PLEX_HOST = config.clean_hosts(plex_host)
        sickbeard.PLEX_SERVER_HOST = config.clean_hosts(plex_server_host)
        sickbeard.PLEX_USERNAME = plex_username
        if set('*') != set(plex_password):
            sickbeard.PLEX_PASSWORD = plex_password

        sickbeard.USE_GROWL = config.checkbox_to_value(use_growl)
        sickbeard.GROWL_NOTIFY_ONSNATCH = config.checkbox_to_value(growl_notify_onsnatch)
        sickbeard.GROWL_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(growl_notify_ondownload)
        sickbeard.GROWL_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(growl_notify_onsubtitledownload)
        sickbeard.GROWL_HOST = config.clean_host(growl_host, default_port=23053)
        if set('*') != set(growl_password):
            sickbeard.GROWL_PASSWORD = growl_password

        sickbeard.USE_PROWL = config.checkbox_to_value(use_prowl)
        sickbeard.PROWL_NOTIFY_ONSNATCH = config.checkbox_to_value(prowl_notify_onsnatch)
        sickbeard.PROWL_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(prowl_notify_ondownload)
        sickbeard.PROWL_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(prowl_notify_onsubtitledownload)
        key = prowl_api.strip()
        if not starify(key, True):
            sickbeard.PROWL_API = key
        sickbeard.PROWL_PRIORITY = prowl_priority

        sickbeard.USE_TWITTER = config.checkbox_to_value(use_twitter)
        sickbeard.TWITTER_NOTIFY_ONSNATCH = config.checkbox_to_value(twitter_notify_onsnatch)
        sickbeard.TWITTER_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(twitter_notify_ondownload)
        sickbeard.TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(twitter_notify_onsubtitledownload)

        sickbeard.USE_BOXCAR2 = config.checkbox_to_value(use_boxcar2)
        sickbeard.BOXCAR2_NOTIFY_ONSNATCH = config.checkbox_to_value(boxcar2_notify_onsnatch)
        sickbeard.BOXCAR2_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(boxcar2_notify_ondownload)
        sickbeard.BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(boxcar2_notify_onsubtitledownload)
        key = boxcar2_accesstoken.strip()
        if not starify(key, True):
            sickbeard.BOXCAR2_ACCESSTOKEN = key
        sickbeard.BOXCAR2_SOUND = boxcar2_sound

        sickbeard.USE_PUSHOVER = config.checkbox_to_value(use_pushover)
        sickbeard.PUSHOVER_NOTIFY_ONSNATCH = config.checkbox_to_value(pushover_notify_onsnatch)
        sickbeard.PUSHOVER_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(pushover_notify_ondownload)
        sickbeard.PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(pushover_notify_onsubtitledownload)
        key = pushover_userkey.strip()
        if not starify(key, True):
            sickbeard.PUSHOVER_USERKEY = key
        key = pushover_apikey.strip()
        if not starify(key, True):
            sickbeard.PUSHOVER_APIKEY = key
        sickbeard.PUSHOVER_PRIORITY = pushover_priority
        sickbeard.PUSHOVER_DEVICE = pushover_device
        sickbeard.PUSHOVER_SOUND = pushover_sound

        sickbeard.USE_LIBNOTIFY = config.checkbox_to_value(use_libnotify)
        sickbeard.LIBNOTIFY_NOTIFY_ONSNATCH = config.checkbox_to_value(libnotify_notify_onsnatch)
        sickbeard.LIBNOTIFY_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(libnotify_notify_ondownload)
        sickbeard.LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(libnotify_notify_onsubtitledownload)

        sickbeard.USE_NMJ = config.checkbox_to_value(use_nmj)
        sickbeard.NMJ_HOST = config.clean_host(nmj_host)
        sickbeard.NMJ_DATABASE = nmj_database
        sickbeard.NMJ_MOUNT = nmj_mount

        sickbeard.USE_NMJv2 = config.checkbox_to_value(use_nmjv2)
        sickbeard.NMJv2_HOST = config.clean_host(nmjv2_host)
        sickbeard.NMJv2_DATABASE = nmjv2_database
        sickbeard.NMJv2_DBLOC = nmjv2_dbloc

        sickbeard.USE_SYNOINDEX = config.checkbox_to_value(use_synoindex)

        sickbeard.USE_SYNOLOGYNOTIFIER = config.checkbox_to_value(use_synologynotifier)
        sickbeard.SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH = config.checkbox_to_value(synologynotifier_notify_onsnatch)
        sickbeard.SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(synologynotifier_notify_ondownload)
        sickbeard.SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(
            synologynotifier_notify_onsubtitledownload)

        sickbeard.USE_TRAKT = config.checkbox_to_value(use_trakt)
        # sickbeard.traktCheckerScheduler.silent = not sickbeard.USE_TRAKT
        sickbeard.TRAKT_UPDATE_COLLECTION = build_config(**kwargs)
        # sickbeard.TRAKT_DEFAULT_INDEXER = int(trakt_default_indexer)
        # sickbeard.TRAKT_SYNC = config.checkbox_to_value(trakt_sync)
        # sickbeard.TRAKT_USE_WATCHLIST = config.checkbox_to_value(trakt_use_watchlist)
        # sickbeard.TRAKT_METHOD_ADD = int(trakt_method_add)
        # sickbeard.TRAKT_REMOVE_WATCHLIST = config.checkbox_to_value(trakt_remove_watchlist)
        # sickbeard.TRAKT_REMOVE_SERIESLIST = config.checkbox_to_value(trakt_remove_serieslist)
        # sickbeard.TRAKT_START_PAUSED = config.checkbox_to_value(trakt_start_paused)

        sickbeard.USE_EMAIL = config.checkbox_to_value(use_email)
        sickbeard.EMAIL_NOTIFY_ONSNATCH = config.checkbox_to_value(email_notify_onsnatch)
        sickbeard.EMAIL_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(email_notify_ondownload)
        sickbeard.EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(email_notify_onsubtitledownload)
        sickbeard.EMAIL_HOST = config.clean_host(email_host)
        sickbeard.EMAIL_PORT = config.to_int(email_port, default=25)
        sickbeard.EMAIL_FROM = email_from
        sickbeard.EMAIL_TLS = config.checkbox_to_value(email_tls)
        sickbeard.EMAIL_USER = email_user
        if set('*') != set(email_password):
            sickbeard.EMAIL_PASSWORD = email_password
        sickbeard.EMAIL_LIST = email_list

        sickbeard.USE_PYTIVO = config.checkbox_to_value(use_pytivo)
        sickbeard.PYTIVO_NOTIFY_ONSNATCH = config.checkbox_to_value(pytivo_notify_onsnatch)
        sickbeard.PYTIVO_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(pytivo_notify_ondownload)
        sickbeard.PYTIVO_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(pytivo_notify_onsubtitledownload)
        sickbeard.PYTIVO_UPDATE_LIBRARY = config.checkbox_to_value(pytivo_update_library)
        sickbeard.PYTIVO_HOST = config.clean_host(pytivo_host)
        sickbeard.PYTIVO_SHARE_NAME = pytivo_share_name
        sickbeard.PYTIVO_TIVO_NAME = pytivo_tivo_name

        sickbeard.USE_NMA = config.checkbox_to_value(use_nma)
        sickbeard.NMA_NOTIFY_ONSNATCH = config.checkbox_to_value(nma_notify_onsnatch)
        sickbeard.NMA_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(nma_notify_ondownload)
        sickbeard.NMA_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(nma_notify_onsubtitledownload)
        key = nma_api.strip()
        if not starify(key, True):
            sickbeard.NMA_API = key
        sickbeard.NMA_PRIORITY = nma_priority

        sickbeard.USE_PUSHALOT = config.checkbox_to_value(use_pushalot)
        sickbeard.PUSHALOT_NOTIFY_ONSNATCH = config.checkbox_to_value(pushalot_notify_onsnatch)
        sickbeard.PUSHALOT_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(pushalot_notify_ondownload)
        sickbeard.PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(pushalot_notify_onsubtitledownload)
        key = pushalot_authorizationtoken.strip()
        if not starify(key, True):
            sickbeard.PUSHALOT_AUTHORIZATIONTOKEN = key

        sickbeard.USE_PUSHBULLET = config.checkbox_to_value(use_pushbullet)
        sickbeard.PUSHBULLET_NOTIFY_ONSNATCH = config.checkbox_to_value(pushbullet_notify_onsnatch)
        sickbeard.PUSHBULLET_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(pushbullet_notify_ondownload)
        sickbeard.PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(pushbullet_notify_onsubtitledownload)
        key = pushbullet_access_token.strip()
        if not starify(key, True):
            sickbeard.PUSHBULLET_ACCESS_TOKEN = key
        sickbeard.PUSHBULLET_DEVICE_IDEN = pushbullet_device_iden

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/notifications/')


class ConfigSubtitles(Config):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file='config_subtitles.tmpl')
        t.submenu = self.ConfigMenu
        return t.respond()

    def saveSubtitles(self, use_subtitles=None, subtitles_plugins=None, subtitles_languages=None, subtitles_dir=None,
                      service_order=None, subtitles_history=None, subtitles_finder_frequency=None):
        results = []

        if subtitles_finder_frequency == '' or subtitles_finder_frequency is None:
            subtitles_finder_frequency = 1

        if use_subtitles == 'on' and not sickbeard.subtitlesFinderScheduler.isAlive():
            sickbeard.subtitlesFinderScheduler.silent = False
            sickbeard.subtitlesFinderScheduler.start()
        else:
            sickbeard.subtitlesFinderScheduler.stop.set()
            sickbeard.subtitlesFinderScheduler.silent = True
            logger.log(u'Waiting for the SUBTITLESFINDER thread to exit')
            try:
                sickbeard.subtitlesFinderScheduler.join(5)
            except:
                pass

        sickbeard.USE_SUBTITLES = config.checkbox_to_value(use_subtitles)
        sickbeard.SUBTITLES_LANGUAGES = [lang.alpha2 for lang in subtitles.isValidLanguage(
            subtitles_languages.replace(' ', '').split(','))] if subtitles_languages != '' else ''
        sickbeard.SUBTITLES_DIR = subtitles_dir
        sickbeard.SUBTITLES_HISTORY = config.checkbox_to_value(subtitles_history)
        sickbeard.SUBTITLES_FINDER_FREQUENCY = config.to_int(subtitles_finder_frequency, default=1)

        # Subtitles services
        services_str_list = service_order.split()
        subtitles_services_list = []
        subtitles_services_enabled = []
        for curServiceStr in services_str_list:
            curService, curEnabled = curServiceStr.split(':')
            subtitles_services_list.append(curService)
            subtitles_services_enabled.append(int(curEnabled))

        sickbeard.SUBTITLES_SERVICES_LIST = subtitles_services_list
        sickbeard.SUBTITLES_SERVICES_ENABLED = subtitles_services_enabled

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/subtitles/')


class ConfigAnime(Config):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='config_anime.tmpl')
        t.submenu = self.ConfigMenu
        return t.respond()

    def saveAnime(self, use_anidb=None, anidb_username=None, anidb_password=None, anidb_use_mylist=None,
                  anime_treat_as_hdtv=None):

        results = []

        sickbeard.USE_ANIDB = config.checkbox_to_value(use_anidb)
        sickbeard.ANIDB_USERNAME = anidb_username
        if set('*') != set(anidb_password):
            sickbeard.ANIDB_PASSWORD = anidb_password
        sickbeard.ANIDB_USE_MYLIST = config.checkbox_to_value(anidb_use_mylist)
        sickbeard.ANIME_TREAT_AS_HDTV = config.checkbox_to_value(anime_treat_as_hdtv)

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/anime/')


class UI(MainHandler):
    def add_message(self):
        ui.notifications.message('Test 1', 'This is test number 1')
        ui.notifications.error('Test 2', 'This is test number 2')

        return 'ok'

    def get_messages(self):
        messages = {}
        cur_notification_num = 1
        for cur_notification in ui.notifications.get_notifications(self.request.remote_ip):
            messages['notification-' + str(cur_notification_num)] = {'title': cur_notification.title,
                                                                     'message': cur_notification.message,
                                                                     'type': cur_notification.type}
            cur_notification_num += 1

        return json.dumps(messages)


class ErrorLogs(MainHandler):
    @staticmethod
    def ErrorLogsMenu():
        return [{'title': 'Clear Errors', 'path': 'errorlogs/clearerrors/'},]

    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file='errorlogs.tmpl')
        t.submenu = self.ErrorLogsMenu

        return t.respond()

    def clearerrors(self, *args, **kwargs):
        classes.ErrorViewer.clear()
        self.redirect('/errorlogs/')

    def viewlog(self, minLevel=logger.MESSAGE, maxLines=500):

        t = PageTemplate(headers=self.request.headers, file='viewlogs.tmpl')
        t.submenu = self.ErrorLogsMenu

        minLevel = int(minLevel)

        data = []
        if os.path.isfile(logger.sb_log_instance.log_file_path):
            with ek.ek(open, logger.sb_log_instance.log_file_path) as f:
                data = f.readlines()

        regex = '^(\d\d\d\d)\-(\d\d)\-(\d\d)\s*(\d\d)\:(\d\d):(\d\d)\s*([A-Z]+)\s*(.+?)\s*\:\:\s*(.*)$'

        finalData = []

        numLines = 0
        lastLine = False
        numToShow = min(maxLines, len(data))

        for x in reversed(data):

            x = x.decode('utf-8', 'replace')
            match = re.match(regex, x)

            if match:
                level = match.group(7)
                if level not in logger.reverseNames:
                    lastLine = False
                    continue

                if logger.reverseNames[level] >= minLevel:
                    lastLine = True
                    finalData.append(x)
                else:
                    lastLine = False
                    continue

            elif lastLine:
                finalData.append('AA' + x)

            numLines += 1

            if numLines >= numToShow:
                break

        result = ''.join(finalData)

        t.logLines = result
        t.minLevel = minLevel

        return t.respond()


class WebFileBrowser(MainHandler):
    def index(self, path='', includeFiles=False, *args, **kwargs):
        self.set_header('Content-Type', 'application/json')
        return json.dumps(foldersAtPath(path, True, bool(int(includeFiles))))

    def complete(self, term, includeFiles=0):
        self.set_header('Content-Type', 'application/json')
        paths = [entry['path'] for entry in foldersAtPath(os.path.dirname(term), includeFiles=bool(int(includeFiles))) if 'path' in entry]
        return json.dumps(paths)


class ApiBuilder(MainHandler):
    def index(self):
        """ expose the api-builder template """
        t = PageTemplate(headers=self.request.headers, file='apiBuilder.tmpl')

        def titler(x):
            return (remove_article(x), x)[not x or sickbeard.SORT_ARTICLE]

        t.sortedShowList = sorted(sickbeard.showList, lambda x, y: cmp(titler(x.name), titler(y.name)))

        seasonSQLResults = {}
        episodeSQLResults = {}

        myDB = db.DBConnection(row_type='dict')
        for curShow in t.sortedShowList:
            seasonSQLResults[curShow.indexerid] = myDB.select(
                'SELECT DISTINCT season FROM tv_episodes WHERE showid = ? ORDER BY season DESC', [curShow.indexerid])

        for curShow in t.sortedShowList:
            episodeSQLResults[curShow.indexerid] = myDB.select(
                'SELECT DISTINCT season,episode FROM tv_episodes WHERE showid = ? ORDER BY season DESC, episode DESC',
                [curShow.indexerid])

        t.seasonSQLResults = seasonSQLResults
        t.episodeSQLResults = episodeSQLResults

        if len(sickbeard.API_KEY) == 32:
            t.apikey = sickbeard.API_KEY
        else:
            t.apikey = 'api key not generated'

        return t.respond()


class Cache(MainHandler):
    def index(self):
        myDB = db.DBConnection('cache.db')
        sql_results = myDB.select('SELECT * FROM provider_cache')
        if not sql_results:
            sql_results = []

        t = PageTemplate(headers=self.request.headers, file='cache.tmpl')
        t.cacheResults = sql_results

        return t.respond()


class CachedImages(MainHandler):
    @staticmethod
    def should_try_image(filename, source, days=1, minutes=0):
        try:
            dummy_file = '%s.%s.dummy' % (ek.ek(os.path.splitext, filename)[0], source)
            if ek.ek(os.path.isfile, dummy_file):
                if ek.ek(os.stat, dummy_file).st_mtime < time.mktime((datetime.datetime.now() - datetime.timedelta(days=days, minutes=minutes)).timetuple()):
                    CachedImages.delete_dummy_image(dummy_file)
                    return True
                return False
        except:
            pass
        return True

    @staticmethod
    def create_dummy_image(filename, source):
        dummy_file = '%s.%s.dummy' % (ek.ek(os.path.splitext, filename)[0], source)
        CachedImages.delete_dummy_image(dummy_file)
        try:
            with open(dummy_file, 'w'):
                pass
        except:
            pass

    @staticmethod
    def delete_dummy_image(dummy_file):
        try:
            if ek.ek(os.path.isfile, dummy_file):
                ek.ek(os.remove, dummy_file)
        except:
            pass

    @staticmethod
    def delete_all_dummy_images(filename):
        for f in ['tmdb', 'tvdb']:
            CachedImages.delete_dummy_image('%s.%s.dummy' % (ek.ek(os.path.splitext, filename)[0], f))

    def index(self, path='', source=None, filename=None, tmdbid=None, tvdbid=None, *args, **kwargs):

        path = path.strip('/')
        file_name = ''
        if None is not source:
            file_name = ek.ek(os.path.basename, source)
        elif filename not in [None, 0, '0']:
            file_name = filename
        static_image_path = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', path, file_name)
        static_image_path = ek.ek(os.path.abspath, static_image_path.replace('\\', '/'))
        if not ek.ek(os.path.isfile, static_image_path) and has_image_ext(file_name):
            basepath = ek.ek(os.path.dirname, static_image_path)
            helpers.make_dirs(basepath)
            s = ''
            tmdbimage = False
            if source is not None and source in sickbeard.CACHE_IMAGE_URL_LIST:
                s = source
            if source is None and tmdbid not in [None, 0, '0'] and self.should_try_image(static_image_path, 'tmdb'):
                tmdbimage = True
                try:
                    tmdbapi = TMDB(sickbeard.TMDB_API_KEY)
                    tmdbconfig = tmdbapi.Configuration().info()
                    images = tmdbapi.TV(helpers.tryInt(tmdbid)).images()
                    s = '%s%s%s' % (tmdbconfig['images']['base_url'], tmdbconfig['images']['poster_sizes'][3], sorted(images['posters'], key=lambda x: x['vote_average'], reverse=True)[0]['file_path']) if len(images['posters']) > 0 else ''
                except:
                    s = ''
            if s and not helpers.download_file(s, static_image_path) and s.find('trakt.us'):
                helpers.download_file(s.replace('trakt.us', 'trakt.tv'), static_image_path)
            if tmdbimage and not ek.ek(os.path.isfile, static_image_path):
                self.create_dummy_image(static_image_path, 'tmdb')

            if source is None and tvdbid not in [None, 0, '0'] and not ek.ek(os.path.isfile, static_image_path) and self.should_try_image(static_image_path, 'tvdb'):
                try:
                    r = sickbeard.indexerApi(INDEXER_TVDB).indexer()[helpers.tryInt(tvdbid), False]
                    if hasattr(r, 'data') and 'poster' in r.data:
                        s = r.data['poster']
                except:
                    s = ''
                if s:
                    helpers.download_file(s, static_image_path)
                if not ek.ek(os.path.isfile, static_image_path):
                    self.create_dummy_image(static_image_path, 'tvdb')

            if ek.ek(os.path.isfile, static_image_path):
                self.delete_all_dummy_images(static_image_path)

        if not ek.ek(os.path.isfile, static_image_path):
            self.redirect('images/trans.png')
        else:
            helpers.set_file_timestamp(static_image_path, min_age=3, new_time=None)
            self.redirect('cache/images/%s/%s' % (path, file_name))

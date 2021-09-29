# coding=utf-8
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

from __future__ import with_statement, division

try:
    import json
except ImportError:
    from lib import simplejson as json

# noinspection PyProtectedMember
from mimetypes import MimeTypes

import base64
import copy
import datetime
import glob
import hashlib
import io
import os
import random
import re
import sys
import threading
import time
import traceback
import zipfile

from exceptions_helper import ex, MultipleShowObjectsException
import exceptions_helper
# noinspection PyPep8Naming
import encodingKludge as ek
import sg_helpers
from sg_helpers import scantree

import sickbeard
from . import classes, clients, config, db, helpers, history, image_cache, logger, name_cache, naming, \
    network_timezones, notifiers, nzbget, processTV, sab, scene_exceptions, search_queue, subtitles, ui
from .anime import AniGroupList, pull_anidb_groups, short_group_names
from .browser import folders_at_path
from .common import ARCHIVED, DOWNLOADED, FAILED, IGNORED, SKIPPED, SNATCHED, SNATCHED_ANY, UNAIRED, UNKNOWN, WANTED, \
     SD, HD720p, HD1080p, UHD2160p, Overview, Quality, qualityPresetStrings, statusStrings
from .helpers import get_media_stats, has_image_ext, real_path, remove_article, remove_file_perm, starify
from .indexermapper import MapStatus, map_indexers_to_show, save_mapping
from .indexers.indexer_config import TVINFO_IMDB, TVINFO_TMDB, TVINFO_TRAKT, TVINFO_TVDB, TVINFO_TVMAZE, \
    TVINFO_TRAKT_SLUG, TVINFO_TVDB_SLUG
from .name_parser.parser import InvalidNameException, InvalidShowException, NameParser
from .providers import newznab, rsstorrent
from .scene_numbering import get_scene_absolute_numbering_for_show, get_scene_numbering_for_show, \
    get_xem_absolute_numbering_for_show, get_xem_numbering_for_show, set_scene_numbering_helper
from .search_backlog import FORCED_BACKLOG
from .sgdatetime import SGDatetime, timestamp_near
from .show_name_helpers import abbr_showname

from .show_updater import clean_ignore_require_words
from .trakt_helpers import build_config, trakt_collection_remove_account
from .tv import TVidProdid, Person as TVPerson, Character as TVCharacter, TVSWITCH_NORMAL, tvswitch_names, \
    TVSWITCH_EP_DELETED, tvswitch_ep_names, usable_id

from bs4_parser import BS4Parser
# noinspection PyPackageRequirements
from Cheetah.Template import Template
from unidecode import unidecode
import dateutil.parser

from tornado import gen
# noinspection PyUnresolvedReferences
from tornado.web import RequestHandler, StaticFileHandler, authenticated
from tornado.concurrent import run_on_executor
# tornado.web.RequestHandler above is unresolved until...
# 1) RouteHandler derives from RequestHandler instead of LegacyBaseHandler
# 2) the following line is removed (plus the noinspection deleted)
from ._legacy import LegacyBaseHandler

from lib import subliminal
from lib.cfscrape import CloudflareScraper
from lib.dateutil import tz, zoneinfo
from lib.dateutil.relativedelta import relativedelta
from lib.fuzzywuzzy import fuzz
from lib.api_trakt import TraktAPI
from lib.api_trakt.exceptions import TraktException, TraktAuthException

import lib.rarfile.rarfile as rarfile

from _23 import decode_bytes, decode_str, filter_list, filter_iter, getargspec, list_keys, list_values, \
    map_consume, map_iter, map_list, map_none, ordered_dict, quote_plus, unquote_plus, urlparse
from six import binary_type, integer_types, iteritems, iterkeys, itervalues, moves, PY2, string_types

# noinspection PyUnreachableCode
if False:
    from typing import Any, AnyStr, Dict, List, Optional, Set, Tuple
    from sickbeard.providers.generic import TorrentProvider


# noinspection PyAbstractClass
class PageTemplate(Template):

    def __init__(self, web_handler, *args, **kwargs):

        headers = web_handler.request.headers
        self.xsrf_form_html = re.sub(r'\s*/>$', '>', web_handler.xsrf_form_html())
        self.sbHost = headers.get('X-Forwarded-Host')
        if None is self.sbHost:
            sb_host = headers.get('Host') or 'localhost'
            self.sbHost = re.match('(?msx)^' + (('[^:]+', r'\[.*\]')['[' == sb_host[0]]), sb_host).group(0)
        self.sbHttpPort = sickbeard.WEB_PORT
        self.sbHttpsPort = headers.get('X-Forwarded-Port') or self.sbHttpPort
        self.sbRoot = sickbeard.WEB_ROOT
        self.sbHttpsEnabled = 'https' == headers.get('X-Forwarded-Proto') or sickbeard.ENABLE_HTTPS
        self.sbHandleReverseProxy = sickbeard.HANDLE_REVERSE_PROXY
        self.sbThemeName = sickbeard.THEME_NAME

        self.log_num_errors = len(classes.ErrorViewer.errors)
        if None is not sickbeard.showList:
            self.log_num_not_found_shows = len([cur_so for cur_so in sickbeard.showList
                                                if 0 < cur_so.not_found_count])
            self.log_num_not_found_shows_all = len([cur_so for cur_so in sickbeard.showList
                                                    if 0 != cur_so.not_found_count])
        self.sbPID = str(sickbeard.PID)
        self.menu = [
            {'title': 'Home', 'key': 'home'},
            {'title': 'Episodes', 'key': 'daily-schedule'},
            {'title': 'History', 'key': 'history'},
            {'title': 'Manage', 'key': 'manage'},
            {'title': 'Config', 'key': 'config'},
        ]

        kwargs['file'] = os.path.join(sickbeard.PROG_DIR, 'gui/%s/interfaces/default/' %
                                      sickbeard.GUI_NAME, kwargs['file'])

        self.addtab_limit = sickbeard.MEMCACHE.get('history_tab_limit', 0)
        if not web_handler.application.is_loading_handler:
            self.history_compact = sickbeard.MEMCACHE.get('history_tab')
            self.tvinfo_switch_running = sickbeard.show_queue_scheduler.action.is_switch_running()

        super(PageTemplate, self).__init__(*args, **kwargs)

    def compile(self, *args, **kwargs):
        if not os.path.exists(os.path.join(sickbeard.CACHE_DIR, 'cheetah')):
            os.mkdir(os.path.join(sickbeard.CACHE_DIR, 'cheetah'))

        kwargs['cacheModuleFilesForTracebacks'] = True
        kwargs['cacheDirForModuleFiles'] = os.path.join(sickbeard.CACHE_DIR, 'cheetah')
        return super(PageTemplate, self).compile(*args, **kwargs)


class BaseStaticFileHandler(StaticFileHandler):

    def write_error(self, status_code, **kwargs):
        body = ''
        try:
            if self.request.body:
                body = '\nRequest body: %s' % decode_str(self.request.body)
        except (BaseException, Exception):
            pass
        logger.log('Sent %s error response to a `%s` request for `%s` with headers:\n%s%s' %
                   (status_code, self.request.method, self.request.path, self.request.headers, body), logger.WARNING)
        # suppress traceback by removing 'exc_info' kwarg
        if 'exc_info' in kwargs:
            logger.log('Gracefully handled exception text:\n%s' % traceback.format_exception(*kwargs["exc_info"]),
                       logger.DEBUG)
            del kwargs['exc_info']
        return super(BaseStaticFileHandler, self).write_error(status_code, **kwargs)

    def data_received(self, *args):
        pass

    def set_extra_headers(self, path):
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')
        self.set_header('Cache-Control', 'no-cache, max-age=0')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Expires', '0')
        if sickbeard.SEND_SECURITY_HEADERS:
            self.set_header('X-Frame-Options', 'SAMEORIGIN')


class RouteHandler(LegacyBaseHandler):
    def data_received(self, *args):
        pass

    def decode_data(self, data):
        if isinstance(data, binary_type):
            return decode_str(data)
        if isinstance(data, list):
            return [self.decode_data(d) for d in data]
        if not isinstance(data, string_types):
            return data
        if not PY2:
            return data.encode('latin1').decode('utf-8')
        return data.decode('utf-8')

    @gen.coroutine
    def route_method(self, route, use_404=False, limit_route=None, xsrf_filter=True):

        route = route.strip('/')
        if not route and None is limit_route:
            route = 'index'
        if limit_route:
            route = limit_route(route)
        if '-' in route:
            parts = re.split(r'([/?])', route)
            route = '%s%s' % (parts[0].replace('-', '_'), '' if not len(parts) else ''.join(parts[1:]))

        try:
            method = getattr(self, route)
        except (BaseException, Exception):
            self.finish(use_404 and self.page_not_found() or None)
        else:
            request_kwargs = {k: self.decode_data(v if not (isinstance(v, list) and 1 == len(v)) else v[0])
                              for k, v in iteritems(self.request.arguments) if not xsrf_filter or ('_xsrf' != k)}
            if 'tvid_prodid' in request_kwargs and request_kwargs['tvid_prodid'] in sickbeard.switched_shows:
                # in case show has been switched, redirect to new id
                url = self.request.uri.replace('tvid_prodid=%s' % request_kwargs['tvid_prodid'],
                                               'tvid_prodid=%s' %
                                               sickbeard.switched_shows[request_kwargs['tvid_prodid']])
                self.redirect(url, permanent=True)
                self.finish()
                return
            # filter method specified arguments so *args and **kwargs are not required and unused vars safely dropped
            method_args = []
            # noinspection PyDeprecation
            for arg in list(getargspec(method)):
                if not isinstance(arg, list):
                    arg = [arg]
                method_args += [item for item in arg if None is not item]
            if 'kwargs' in method_args or re.search('[A-Z]', route):
                # no filtering for legacy and routes that depend on *args and **kwargs
                result = yield self.async_call(method, request_kwargs)  # method(**request_kwargs)
            else:
                filter_kwargs = dict(filter_iter(lambda kv: kv[0] in method_args, iteritems(request_kwargs)))
                result = yield self.async_call(method, filter_kwargs)  # method(**filter_kwargs)
            self.finish(result)

    @run_on_executor
    def async_call(self, function, kw):
        try:
            return function(**kw)
        except (BaseException, Exception) as e:
            if PY2:
                raise Exception(traceback.format_exc().replace('\n', '<br>'))
            raise e

    def page_not_found(self):
        self.set_status(404)
        t = PageTemplate(web_handler=self, file='404.tmpl')
        return t.respond()


class BaseHandler(RouteHandler):

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')
        if sickbeard.SEND_SECURITY_HEADERS:
            self.set_header('X-Frame-Options', 'SAMEORIGIN')

    def redirect(self, url, permanent=False, status=None):
        if not url.startswith(sickbeard.WEB_ROOT):
            url = sickbeard.WEB_ROOT + url

        super(BaseHandler, self).redirect(url, permanent, status)

    def get_current_user(self):
        if sickbeard.WEB_USERNAME or sickbeard.WEB_PASSWORD:
            return self.get_secure_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT))
        return True

    def get_image(self, image):
        if ek.ek(os.path.isfile, image):
            mime_type, encoding = MimeTypes().guess_type(image)
            self.set_header('Content-Type', mime_type)
            with ek.ek(open, image, 'rb') as img:
                return img.read()

    def show_poster(self, tvid_prodid=None, which=None, api=None):
        # Redirect initial poster/banner thumb to default images
        if 'poster' == which[0:6]:
            default_image_name = 'poster.png'
        elif 'banner' == which[0:6]:
            default_image_name = 'banner.png'
        else:
            default_image_name = 'backart.png'

        static_image_path = os.path.join('/images', default_image_name)
        if helpers.find_show_by_id(tvid_prodid):
            cache_obj = image_cache.ImageCache()
            tvid_prodid_obj = tvid_prodid and TVidProdid(tvid_prodid)

            image_file_name = []
            if 'poster' == which[0:6]:
                if '_thumb' == which[6:]:
                    image_file_name = [cache_obj.poster_thumb_path(*tvid_prodid_obj.tuple)]
                image_file_name += [cache_obj.poster_path(*tvid_prodid_obj.tuple)]
            elif 'banner' == which[0:6]:
                if '_thumb' == which[6:]:
                    image_file_name = [cache_obj.banner_thumb_path(*tvid_prodid_obj.tuple)]
                image_file_name += [cache_obj.banner_path(*tvid_prodid_obj.tuple)]
            elif 'fanart' == which[0:6]:
                image_file_name = [cache_obj.fanart_path(
                    *tvid_prodid_obj.tuple +
                    ('%s' % (re.sub(r'.*?fanart_(\d+(?:\.\w{1,20})?\.\w{5,8}).*', r'\1.', which, 0, re.I)),))]

            for cur_name in image_file_name:
                if ek.ek(os.path.isfile, cur_name):
                    static_image_path = cur_name
                    break

        if api:
            used_file = ek.ek(os.path.basename, static_image_path)
            if static_image_path.startswith('/images'):
                used_file = 'default'
                static_image_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', static_image_path[1:])
            mime_type, encoding = MimeTypes().guess_type(static_image_path)
            self.set_header('Content-Type', mime_type)
            self.set_header('X-Filename', used_file)
            with ek.ek(open, static_image_path, 'rb') as img:
                return img.read()
        else:
            static_image_path = os.path.normpath(static_image_path.replace(sickbeard.CACHE_DIR, '/cache'))
            static_image_path = static_image_path.replace('\\', '/')
            self.redirect(static_image_path)


class LoginHandler(BaseHandler):

    # noinspection PyUnusedLocal
    def get(self, *args, **kwargs):
        if self.get_current_user():
            self.redirect(self.get_argument('next', '/home/'))
        else:
            t = PageTemplate(web_handler=self, file='login.tmpl')
            t.resp = self.get_argument('resp', '')
            self.set_status(401)
            self.finish(t.respond())

    # noinspection PyUnusedLocal
    def post(self, *args, **kwargs):
        username = sickbeard.WEB_USERNAME
        password = sickbeard.WEB_PASSWORD

        if (self.get_argument('username') == username) and (self.get_argument('password') == password):
            params = dict(expires_days=(None, 30)[0 < int(self.get_argument('remember_me', default='0') or 0)],
                          httponly=True)
            if sickbeard.ENABLE_HTTPS:
                params.update(dict(secure=True))
            self.set_secure_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT),
                                   sickbeard.COOKIE_SECRET, **params)
            self.redirect(self.get_argument('next', '/home/'))
        else:
            next_arg = '&next=' + self.get_argument('next', '/home/')
            self.redirect('/login?resp=authfailed' + next_arg)


class LogoutHandler(BaseHandler):

    # noinspection PyUnusedLocal
    def get(self, *args, **kwargs):
        self.clear_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT))
        self.redirect('/login/')


class CalendarHandler(BaseHandler):

    # noinspection PyUnusedLocal
    def get(self, *args, **kwargs):
        if sickbeard.CALENDAR_UNPROTECTED or self.get_current_user():
            self.write(self.calendar())
        else:
            self.set_status(401)
            self.write('User authentication required')

    def calendar(self):
        """ iCalendar (iCal) - Standard RFC 5546 <https://datatracker.ietf.org/doc/html/rfc5546>
        Works with iCloud, Google Calendar and Outlook.
        Provides a subscribeable URL for iCal subscriptions """

        logger.log(u'Receiving iCal request from %s' % self.request.remote_ip)

        # Limit dates
        past_date = (datetime.date.today() + datetime.timedelta(weeks=-52)).toordinal()
        future_date = (datetime.date.today() + datetime.timedelta(weeks=52)).toordinal()
        utc = tz.gettz('GMT', zoneinfo_priority=True)

        # Get all the shows that are not paused and are currently on air
        my_db = db.DBConnection()
        show_list = my_db.select(
            'SELECT show_name, indexer AS tv_id, indexer_id AS prod_id, network, airs, runtime'
            ' FROM tv_shows'
            ' WHERE (status = \'Continuing\' OR status = \'Returning Series\' ) AND paused != \'1\'')

        nl = '\\n\\n'
        crlf = '\r\n'

        # Create iCal header
        appname = 'SickGear'
        ical = 'BEGIN:VCALENDAR%sVERSION:2.0%sX-WR-CALNAME:%s%sX-WR-CALDESC:%s%sPRODID://%s Upcoming Episodes//%s' \
               % (crlf, crlf, appname, crlf, appname, crlf, appname, crlf)

        for show in show_list:
            # Get all episodes of this show airing between today and next month

            episode_list = my_db.select(
                'SELECT name, season, episode, description, airdate'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' AND airdate >= ? AND airdate < ? ',
                [show['tv_id'], show['prod_id']]
                + [past_date, future_date])

            for episode in episode_list:
                air_date_time = network_timezones.parse_date_time(episode['airdate'], show['airs'],
                                                                  show['network']).astimezone(utc)
                air_date_time_end = air_date_time + datetime.timedelta(
                    minutes=helpers.try_int(show['runtime'], 60))

                # Create event for episode
                ical += 'BEGIN:VEVENT%s' % crlf \
                        + 'DTSTART:%sT%sZ%s' % (air_date_time.strftime('%Y%m%d'),
                                                air_date_time.strftime('%H%M%S'), crlf) \
                        + 'DTEND:%sT%sZ%s' % (air_date_time_end.strftime('%Y%m%d'),
                                              air_date_time_end.strftime('%H%M%S'), crlf) \
                        + u'SUMMARY:%s - %sx%s - %s%s' % (show['show_name'], episode['season'], episode['episode'],
                                                          episode['name'], crlf) \
                        + u'UID:%s-%s-%s-E%sS%s%s' % (appname, datetime.date.today().isoformat(),
                                                      show['show_name'].replace(' ', '-'),
                                                      episode['episode'], episode['season'], crlf) \
                        + u'DESCRIPTION:%s on %s' % ((show['airs'] or '(Unknown airs)'),
                                                     (show['network'] or 'Unknown network')) \
                        + ('' if not episode['description']
                           else u'%s%s' % (nl, episode['description'].splitlines()[0])) \
                        + '%sEND:VEVENT%s' % (crlf, crlf)

        # Ending the iCal
        return ical + 'END:VCALENDAR'


class RepoHandler(BaseStaticFileHandler):

    def parse_url_path(self, url_path):
        logger.log('Kodi req... get(path): %s' % url_path, logger.DEBUG)
        return super(RepoHandler, self).parse_url_path(url_path)

    def set_extra_headers(self, *args, **kwargs):
        super(RepoHandler, self).set_extra_headers(*args, **kwargs)
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')

    def initialize(self, *args, **kwargs):
        super(RepoHandler, self).initialize(*args, **kwargs)

        logger.log('Kodi req... initialize(path): %s' % kwargs['path'], logger.DEBUG)
        cache_client = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'clients')
        cache_client_kodi = ek.ek(os.path.join, cache_client, 'kodi')
        cache_client_kodi_watchedstate = ek.ek(os.path.join, cache_client_kodi, 'service.sickgear.watchedstate.updater')
        for folder in (cache_client,
                       cache_client_kodi,
                       ek.ek(os.path.join, cache_client_kodi, 'repository.sickgear'),
                       cache_client_kodi_watchedstate,
                       ek.ek(os.path.join, cache_client_kodi_watchedstate, 'resources'),
                       ek.ek(os.path.join, cache_client_kodi_watchedstate, 'resources', 'language'),
                       ek.ek(os.path.join, cache_client_kodi_watchedstate, 'resources', 'language', 'English'),
                       ):
            if not ek.ek(os.path.exists, folder):
                ek.ek(os.mkdir, folder)

        with io.open(ek.ek(os.path.join, cache_client_kodi, 'index.html'), 'w') as fh:
            fh.write(self.render_kodi_index())
        with io.open(ek.ek(os.path.join, cache_client_kodi, 'repository.sickgear', 'index.html'), 'w') as fh:
            fh.write(self.render_kodi_repository_sickgear_index())
        with io.open(ek.ek(os.path.join, cache_client_kodi_watchedstate, 'index.html'), 'w') as fh:
            fh.write(self.render_kodi_service_sickgear_watchedstate_updater_index())
        with io.open(ek.ek(os.path.join, cache_client_kodi_watchedstate, 'resources', 'index.html'), 'w') as fh:
            fh.write(self.render_kodi_service_sickgear_watchedstate_updater_resources_index())
        with io.open(ek.ek(
                os.path.join,
                cache_client_kodi_watchedstate, 'resources', 'language', 'index.html'), 'w') as fh:
            fh.write(self.render_kodi_service_sickgear_watchedstate_updater_resources_language_index())
        with io.open(ek.ek(
                os.path.join,
                cache_client_kodi_watchedstate, 'resources', 'language', 'English', 'index.html'), 'w') as fh:
            fh.write(self.render_kodi_service_sickgear_watchedstate_updater_resources_language_english_index())

        '''
        
        if add-on rendered md5 changes, update its zip and then flag to update repo addon
        if repo rendered md5 changes or flag is true, update the repo addon, where repo version *must* be increased
        
        '''
        repo_md5_file = ek.ek(os.path.join, cache_client_kodi, 'addons.xml.md5')
        saved_md5 = None
        try:
            with io.open(repo_md5_file, 'r', encoding='utf8') as fh:
                saved_md5 = fh.readline()
        except (BaseException, Exception):
            pass
        rendered_md5 = self.render_kodi_repo_addons_xml_md5()
        if saved_md5 != rendered_md5:
            with io.open(ek.ek(os.path.join, cache_client_kodi, 'repository.sickgear', 'addon.xml'), 'w') as fh:
                fh.write(self.render_kodi_repo_addon_xml())
            with io.open(ek.ek(os.path.join, cache_client_kodi_watchedstate, 'addon.xml'), 'w') as fh:
                fh.write(self.get_watchedstate_updater_addon_xml())
            with io.open(ek.ek(os.path.join, cache_client_kodi, 'addons.xml'), 'w') as fh:
                fh.write(self.render_kodi_repo_addons_xml())
            with io.open(ek.ek(os.path.join, cache_client_kodi, 'addons.xml.md5'), 'w') as fh:
                fh.write(rendered_md5)

            def save_zip(name, version, zip_path, zip_method):
                zip_name = '%s-%s.zip' % (name, version)
                zip_file = ek.ek(os.path.join, zip_path, zip_name)
                for direntry in helpers.scantree(zip_path, ['resources'], [r'\.(?:md5|zip)$'], filter_kind=False):
                    remove_file_perm(direntry.path)
                zip_data = zip_method()
                with io.open(zip_file, 'wb') as zh:
                    zh.write(zip_data)

                # Force a UNIX line ending, like the md5sum utility.
                with io.open(ek.ek(os.path.join, zip_path, '%s.md5' % zip_name), 'w', newline='\n') as zh:
                    zh.write(u'%s *%s\n' % (self.md5ify(zip_data), zip_name))

            aid, ver = self.repo_sickgear_details()
            save_zip(aid, ver, ek.ek(os.path.join, cache_client_kodi, 'repository.sickgear'),
                     self.kodi_repository_sickgear_zip)

            aid, ver = self.addon_watchedstate_details()
            save_zip(aid, ver, cache_client_kodi_watchedstate,
                     self.kodi_service_sickgear_watchedstate_updater_zip)

        for (src, dst) in (
                (('repository.sickgear', 'icon.png'),
                 (cache_client_kodi, 'repository.sickgear', 'icon.png')),
                (('service.sickgear.watchedstate.updater', 'icon.png'),
                 (cache_client_kodi_watchedstate, 'icon.png')),
                (('service.sickgear.watchedstate.updater', 'resources', 'settings.xml'),
                 (cache_client_kodi_watchedstate, 'resources', 'settings.xml')),
                (('service.sickgear.watchedstate.updater', 'icon.png'),
                 (cache_client_kodi_watchedstate, 'resources', 'icon.png')),
                (('service.sickgear.watchedstate.updater', 'resources', 'language', 'English', 'strings.xml'),
                 (cache_client_kodi_watchedstate, 'resources', 'language', 'English', 'strings.xml')),
        ):
            helpers.copy_file(ek.ek(
                os.path.join, *(sickbeard.PROG_DIR, 'sickbeard', 'clients', 'kodi') + src), ek.ek(os.path.join, *dst))

    def get_content_type(self):
        if '.md5' == self.absolute_path[-4:]:
            return 'text/plain'
        return super(RepoHandler, self).get_content_type()

    def index(self, basepath, filelist):
        t = PageTemplate(web_handler=self, file='repo_index.tmpl')
        t.basepath = basepath
        t.filelist = filelist
        return t.respond()

    def render_kodi_index(self):
        return self.index('/kodi/',
                          ['repository.sickgear/',
                           'service.sickgear.watchedstate.updater/',
                           'addons.xml',
                           'addons.xml.md5',
                           ])

    def render_kodi_repository_sickgear_index(self):
        aid, version = self.repo_sickgear_details()
        return self.index('/kodi/repository.sickgear/',
                          ['addon.xml',
                           'icon.png',
                           '%s-%s.zip' % (aid, version),
                           '%s-%s.zip.md5' % (aid, version),
                           ])

    def render_kodi_service_sickgear_watchedstate_updater_index(self):
        aid, version = self.addon_watchedstate_details()
        return self.index('/kodi/service.sickgear.watchedstate.updater/',
                          ['resources/',
                           'addon.xml',
                           'icon.png',
                           '%s-%s.zip' % (aid, version),
                           '%s-%s.zip.md5' % (aid, version),
                           ])

    def render_kodi_service_sickgear_watchedstate_updater_resources_index(self):
        return self.index('/kodi/service.sickgear.watchedstate.updater/resources',
                          ['language/',
                           'settings.xml',
                           'icon.png',
                           ])

    def render_kodi_service_sickgear_watchedstate_updater_resources_language_index(self):
        return self.index('/kodi/service.sickgear.watchedstate.updater/resources/language',
                          ['English/',
                           ])

    def render_kodi_service_sickgear_watchedstate_updater_resources_language_english_index(self):
        return self.index('/kodi/service.sickgear.watchedstate.updater/resources/language/English',
                          ['strings.xml',
                           ])

    def repo_sickgear_details(self):
        return re.findall(r'(?si)addon\sid="(repository\.[^"]+)[^>]+version="([^"]+)',
                          self.render_kodi_repo_addon_xml())[0]

    def addon_watchedstate_details(self):
        return re.findall(r'(?si)addon\sid="([^"]+)[^>]+version="([^"]+)',
                          self.get_watchedstate_updater_addon_xml())[0]

    def get_watchedstate_updater_addon_xml(self):
        mem_key = 'kodi_xml'
        if int(timestamp_near(datetime.datetime.now())) < sickbeard.MEMCACHE.get(mem_key, {}).get('last_update', 0):
            return sickbeard.MEMCACHE.get(mem_key).get('data')

        with io.open(ek.ek(os.path.join, sickbeard.PROG_DIR, 'sickbeard', 'clients',
                           'kodi', 'service.sickgear.watchedstate.updater', 'addon.xml'), 'r', encoding='utf8') as fh:
            xml = fh.read().strip() % dict(ADDON_VERSION=self.get_addon_version())

        sickbeard.MEMCACHE[mem_key] = dict(last_update=30 + int(timestamp_near(datetime.datetime.now())), data=xml)
        return xml

    @staticmethod
    def get_addon_version():
        mem_key = 'kodi_ver'
        if int(timestamp_near(datetime.datetime.now())) < sickbeard.MEMCACHE.get(mem_key, {}).get('last_update', 0):
            return sickbeard.MEMCACHE.get(mem_key).get('data')

        with io.open(ek.ek(os.path.join, sickbeard.PROG_DIR, 'sickbeard', 'clients',
                           'kodi', 'service.sickgear.watchedstate.updater', 'service.py'), 'r', encoding='utf8') as fh:
            version = re.findall(r'ADDON_VERSION\s*?=\s*?\'([^\']+)', fh.read())[0]

        sickbeard.MEMCACHE[mem_key] = dict(last_update=30 + int(timestamp_near(datetime.datetime.now())), data=version)
        return version

    def render_kodi_repo_addon_xml(self):
        t = PageTemplate(web_handler=self, file='repo_kodi_addon.tmpl')
        return t.respond().strip()

    def render_kodi_repo_addons_xml(self):
        t = PageTemplate(web_handler=self, file='repo_kodi_addons.tmpl')
        # noinspection PyTypeChecker
        t.watchedstate_updater_addon_xml = re.sub(
            r'(?m)^([\s]*<)', r'\t\1',
            '\n'.join(self.get_watchedstate_updater_addon_xml().split('\n')[1:]))  # skip xml header

        t.repo_xml = re.sub(
            r'(?m)^([\s]*<)', r'\t\1',
            '\n'.join(self.render_kodi_repo_addon_xml().split('\n')[1:]))

        return t.respond()

    def render_kodi_repo_addons_xml_md5(self):
        return self.md5ify('\n'.join(self.render_kodi_repo_addons_xml().split('\n')[1:]))

    @staticmethod
    def md5ify(string):
        if not isinstance(string, binary_type):
            string = string.encode('utf-8')
        return u'%s' % hashlib.new('md5', string).hexdigest()

    def kodi_repository_sickgear_zip(self):
        bfr = io.BytesIO()

        try:
            with zipfile.ZipFile(bfr, 'w') as zh:
                zh.writestr('repository.sickgear/addon.xml', self.render_kodi_repo_addon_xml(), zipfile.ZIP_DEFLATED)

                with io.open(ek.ek(os.path.join, sickbeard.PROG_DIR,
                                   'sickbeard', 'clients', 'kodi', 'repository.sickgear', 'icon.png'), 'rb') as fh:
                    infile = fh.read()
                zh.writestr('repository.sickgear/icon.png', infile, zipfile.ZIP_DEFLATED)
        except OSError as e:
            logger.log('Unable to zip: %r / %s' % (e, ex(e)), logger.WARNING)

        zip_data = bfr.getvalue()
        bfr.close()
        return zip_data

    def kodi_service_sickgear_watchedstate_updater_zip(self):
        bfr = io.BytesIO()

        basepath = ek.ek(os.path.join, sickbeard.PROG_DIR, 'sickbeard', 'clients', 'kodi')

        zip_path = ek.ek(os.path.join, basepath, 'service.sickgear.watchedstate.updater')
        devenv_src = ek.ek(os.path.join, sickbeard.PROG_DIR, 'tests', '_devenv.py')
        devenv_dst = ek.ek(os.path.join, zip_path, '_devenv.py')
        if sickbeard.ENV.get('DEVENV') and ek.ek(os.path.exists, devenv_src):
            helpers.copy_file(devenv_src, devenv_dst)
        else:
            helpers.remove_file_perm(devenv_dst)

        for direntry in helpers.scantree(zip_path, exclude=[r'\.xcf$'], filter_kind=False):
            try:
                infile = None
                if 'service.sickgear.watchedstate.updater' in direntry.path and direntry.path.endswith('addon.xml'):
                    infile = self.get_watchedstate_updater_addon_xml()
                if not infile:
                    with io.open(direntry.path, 'rb') as fh:
                        infile = fh.read()

                with zipfile.ZipFile(bfr, 'a') as zh:
                    zh.writestr(ek.ek(os.path.relpath, direntry.path, basepath), infile, zipfile.ZIP_DEFLATED)
            except OSError as e:
                logger.log('Unable to zip %s: %r / %s' % (direntry.path, e, ex(e)), logger.WARNING)

        zip_data = bfr.getvalue()
        bfr.close()
        return zip_data


class NoXSRFHandler(RouteHandler):

    def __init__(self, *arg, **kwargs):

        super(NoXSRFHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    def check_xsrf_cookie(self):
        pass

    # noinspection PyUnusedLocal
    @gen.coroutine
    def post(self, route, *args, **kwargs):

        yield self.route_method(route, limit_route=False, xsrf_filter=False)

    @staticmethod
    def update_watched_state_kodi(payload=None, as_json=True, **kwargs):
        data = {}
        try:
            data = json.loads(payload)
        except (BaseException, Exception):
            pass

        mapped = 0
        mapping = None
        maps = [x.split('=') for x in sickbeard.KODI_PARENT_MAPS.split(',') if any(x)]
        for k, d in iteritems(data):
            try:
                d['label'] = '%s%s{Kodi}' % (d['label'], bool(d['label']) and ' ' or '')
            except (BaseException, Exception):
                return
            try:
                d['played'] = 100 * int(d['played'])
            except (BaseException, Exception):
                d['played'] = 0

            for m in maps:
                result, change = helpers.path_mapper(m[0], m[1], d['path_file'])
                if change:
                    if not mapping:
                        mapping = (d['path_file'], result)
                    mapped += 1
                    d['path_file'] = result
                    break

        if mapping:
            logger.log('Folder mappings used, the first of %s is [%s] in Kodi is [%s] in SickGear' %
                       (mapped, mapping[0], mapping[1]))

        req_version = tuple([int(x) for x in kwargs.get('version', '0.0.0').split('.')])
        this_version = RepoHandler.get_addon_version()
        if not kwargs or (req_version < tuple([int(x) for x in this_version.split('.')])):
            logger.log('Kodi Add-on update available. To upgrade to version %s; '
                       'select "Check for updates" on menu of "SickGear Add-on repository"' % this_version)

        return MainHandler.update_watched_state(data, as_json)


class IsAliveHandler(BaseHandler):

    # noinspection PyUnusedLocal
    @gen.coroutine
    def get(self, *args, **kwargs):
        kwargs = self.request.arguments
        if 'callback' in kwargs and '_' in kwargs:
            callback, _ = kwargs['callback'][0], kwargs['_']
        else:
            self.write('Error: Unsupported Request. Send jsonp request with callback variable in the query string.')
            return

        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')
        self.set_header('Content-Type', 'text/javascript')
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Headers', 'x-requested-with')

        if sickbeard.started:
            results = decode_str(callback) + '(' + json.dumps(
                {'msg': str(sickbeard.PID)}) + ');'
        else:
            results = decode_str(callback) + '(' + json.dumps({'msg': 'nope'}) + ');'

        self.write(results)


class WrongHostWebHandler(BaseHandler):
    def __init__(self, *arg, **kwargs):
        super(BaseHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    @gen.coroutine
    def prepare(self):
        self.send_error(404)


class LoadingWebHandler(BaseHandler):

    def __init__(self, *arg, **kwargs):
        super(BaseHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    def loading_page(self):
        t = PageTemplate(web_handler=self, file='loading.tmpl')
        t.message = classes.loading_msg.message
        return t.respond()

    @staticmethod
    def get_message():
        return json.dumps({'message': classes.loading_msg.message})

    # noinspection PyUnusedLocal
    @authenticated
    @gen.coroutine
    def get(self, route, *args, **kwargs):
        yield self.route_method(route, use_404=True, limit_route=(
            lambda _route: not re.search('get[_-]message', _route) and 'loading-page' or _route))

    post = get


class WebHandler(BaseHandler):

    def __init__(self, *arg, **kwargs):
        super(BaseHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    @authenticated
    @gen.coroutine
    def get(self, route, *args, **kwargs):
        yield self.route_method(route, use_404=True)

    def send_message(self, message):
        with self.lock:
            self.write(message)
            self.flush()

    post = get


class MainHandler(WebHandler):

    def index(self):
        self.redirect('/home/')

    @staticmethod
    def http_error_401_handler():
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
        if 401 == status_code:
            self.finish(self.http_error_401_handler())
        elif 404 == status_code:
            self.redirect(sickbeard.WEB_ROOT + '/home/')
        elif self.settings.get('debug') and 'exc_info' in kwargs:
            exc_info = kwargs['exc_info']
            trace_info = ''.join(['%s<br/>' % line for line in traceback.format_exception(*exc_info)])
            request_info = ''.join(['<strong>%s</strong>: %s<br/>' % (k, self.request.__dict__[k]) for k in
                                    iterkeys(self.request.__dict__)])
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

    def robots_txt(self):
        """ Keep web crawlers out """
        self.set_header('Content-Type', 'text/plain')
        return 'User-agent: *\nDisallow: /'

    def set_layout_view_shows(self, layout):

        if layout not in ('poster', 'small', 'banner', 'simple'):
            layout = 'poster'

        sickbeard.HOME_LAYOUT = layout

        self.redirect('/view-shows/')

    @staticmethod
    def set_display_show_glide(slidetime=None, tvid_prodid=None, start_at=None):

        if tvid_prodid and start_at:
            sickbeard.DISPLAY_SHOW_GLIDE.setdefault(tvid_prodid, {}).update({'start_at': start_at})

        if slidetime:
            sickbeard.DISPLAY_SHOW_GLIDE_SLIDETIME = sg_helpers.try_int(slidetime, 3000)
        sickbeard.save_config()

    @staticmethod
    def set_poster_sortby(sort):

        if sort not in ('name', 'date', 'network', 'progress', 'quality'):
            sort = 'name'

        sickbeard.POSTER_SORTBY = sort
        sickbeard.save_config()

    @staticmethod
    def set_poster_sortdir(direction):

        sickbeard.POSTER_SORTDIR = int(direction)
        sickbeard.save_config()

    def view_shows(self):
        return Home(self.application, self.request).view_shows()

    def set_layout_daily_schedule(self, layout):
        if layout not in ('poster', 'banner', 'list', 'daybyday'):
            layout = 'banner'

        if 'daybyday' == layout:
            sickbeard.EPISODE_VIEW_SORT = 'time'

        sickbeard.EPISODE_VIEW_LAYOUT = layout

        sickbeard.save_config()

        self.redirect('/daily-schedule/')

    def set_display_paused_daily_schedule(self, state=True):

        sickbeard.EPISODE_VIEW_DISPLAY_PAUSED = sg_helpers.try_int(state, 1)

        sickbeard.save_config()

        self.redirect('/daily-schedule/')

    def set_cards_daily_schedule(self, redir=0):

        sickbeard.EPISODE_VIEW_POSTERS = not sickbeard.EPISODE_VIEW_POSTERS

        sickbeard.save_config()

        if int(redir):
            self.redirect('/daily-schedule/')

    def set_sort_daily_schedule(self, sort, redir=1):
        if sort not in ('time', 'network', 'show'):
            sort = 'time'

        sickbeard.EPISODE_VIEW_SORT = sort

        sickbeard.save_config()

        if int(redir):
            self.redirect('/daily-schedule/')

    @staticmethod
    def get_daily_schedule():
        # type: (...) -> Tuple[List[Dict], Dict, Dict, datetime.date, integer_types, integer_types]
        """ display the episodes """
        today_dt = datetime.date.today()
        today = today_dt.toordinal()
        yesterday_dt = today_dt - datetime.timedelta(days=1)
        yesterday = yesterday_dt.toordinal()
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).toordinal()
        next_week_dt = (datetime.date.today() + datetime.timedelta(days=7))
        next_week = (next_week_dt + datetime.timedelta(days=1)).toordinal()
        recently = (yesterday_dt - datetime.timedelta(days=sickbeard.EPISODE_VIEW_MISSED_RANGE)).toordinal()

        done_show_list = []
        qualities = Quality.SNATCHED + Quality.DOWNLOADED + Quality.ARCHIVED + [IGNORED, SKIPPED]

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT *, tv_episodes.network as episode_network, tv_shows.status AS show_status,'
            ' tv_shows.network as show_network, tv_shows.timezone as show_timezone, tv_shows.airtime as show_airtime,'
            ' tv_episodes.timezone as ep_timezone, tv_episodes.airtime as ep_airtime'
            ' FROM tv_episodes, tv_shows'
            ' WHERE tv_shows.indexer = tv_episodes.indexer AND tv_shows.indexer_id = tv_episodes.showid'
            ' AND season != 0 AND airdate >= ? AND airdate <= ?'
            ' AND tv_episodes.status NOT IN (%s)' % ','.join(['?'] * len(qualities)),
            [yesterday, next_week] + qualities)

        for cur_result in sql_result:
            done_show_list.append('%s-%s' % (cur_result['indexer'], cur_result['showid']))

        # noinspection SqlRedundantOrderingDirection
        sql_result += my_db.select(
            'SELECT *, outer_eps.network as episode_network, tv_shows.status AS show_status,'
            ' tv_shows.network as show_network, tv_shows.timezone as show_timezone, tv_shows.airtime as show_airtime,'
            ' outer_eps.timezone as ep_timezone, outer_eps.airtime as ep_airtime'
            ' FROM tv_episodes outer_eps, tv_shows'
            ' WHERE season != 0'
            ' AND tv_shows.indexer || \'-\' || showid NOT IN (%s)' % ','.join(done_show_list)
            + ' AND tv_shows.indexer = outer_eps.indexer AND tv_shows.indexer_id = outer_eps.showid'
              ' AND airdate = (SELECT airdate FROM tv_episodes inner_eps'
              ' WHERE inner_eps.season != 0'
              ' AND inner_eps.indexer = outer_eps.indexer AND inner_eps.showid = outer_eps.showid'
              ' AND inner_eps.airdate >= ?'
              ' ORDER BY inner_eps.airdate ASC LIMIT 1) AND outer_eps.status NOT IN (%s)'
            % ','.join(['?'] * len(Quality.SNATCHED + Quality.DOWNLOADED)),
            [next_week] + Quality.SNATCHED + Quality.DOWNLOADED)

        sql_result += my_db.select(
            'SELECT *, tv_episodes.network as episode_network, tv_shows.status AS show_status,'
            ' tv_shows.network as show_network, tv_shows.timezone as show_timezone, tv_shows.airtime as show_airtime,'
            ' tv_episodes.timezone as ep_timezone, tv_episodes.airtime as ep_airtime'
            ' FROM tv_episodes, tv_shows'
            ' WHERE season != 0'
            ' AND tv_shows.indexer = tv_episodes.indexer AND tv_shows.indexer_id = tv_episodes.showid'
            ' AND airdate <= ? AND airdate >= ? AND tv_episodes.status = ? AND tv_episodes.status NOT IN (%s)'
            % ','.join(['?'] * len(qualities)),
            [tomorrow, recently, WANTED] + qualities)
        sql_result = list(set(sql_result))

        # make a dict out of the sql results
        sql_result = [dict(row) for row in sql_result
                      if Quality.splitCompositeStatus(helpers.try_int(row['status']))[0] not in
                      SNATCHED_ANY + [DOWNLOADED, ARCHIVED, IGNORED, SKIPPED]]

        # multi dimension sort
        sorts = {
            'network': lambda a: (a['data_network'], a['localtime'], a['data_show_name'], a['season'], a['episode']),
            'show': lambda a: (a['data_show_name'], a['localtime'], a['season'], a['episode']),
            'time': lambda a: (a['localtime'], a['data_show_name'], a['season'], a['episode'])
        }

        def value_maybe_article(value=None):
            if None is value:
                return ''
            return (remove_article(value.lower()), value.lower())[sickbeard.SORT_ARTICLE]

        # add localtime to the dict
        cache_obj = image_cache.ImageCache()
        fanarts = {}
        cur_prodid = None
        for index, item in enumerate(sql_result):
            tvid_prodid_obj = TVidProdid({item['indexer']: item['showid']})
            tvid_prodid = str(tvid_prodid_obj)
            sql_result[index]['tv_id'] = item['indexer']
            sql_result[index]['prod_id'] = item['showid']
            sql_result[index]['tvid_prodid'] = tvid_prodid
            if cur_prodid != tvid_prodid:
                cur_prodid = tvid_prodid

            sql_result[index]['network'] = (item['show_network'], item['episode_network'])[
                isinstance(item['episode_network'], string_types) and 0 != len(item['episode_network'].strip())]

            val = network_timezones.get_episode_time(
                item['airdate'], item['airs'], item['show_network'], item['show_airtime'], item['show_timezone'],
                item['timestamp'], item['episode_network'], item['ep_airtime'], item['ep_timezone'])

            # noinspection PyCallByClass,PyTypeChecker
            sql_result[index]['parsed_datetime'] = val
            sql_result[index]['localtime'] = SGDatetime.convert_to_setting(val)
            sql_result[index]['data_show_name'] = value_maybe_article(item['show_name'])
            sql_result[index]['data_network'] = value_maybe_article(item['network'])
            if not sql_result[index]['runtime']:
                sql_result[index]['runtime'] = 5

            imdb_id = None
            if item['imdb_id']:
                try:
                    imdb_id = helpers.try_int(re.search(r'(\d+)', item['imdb_id']).group(1))
                except (BaseException, Exception):
                    pass
            if imdb_id:
                sql_result[index]['imdb_url'] = sickbeard.indexers.indexer_config.tvinfo_config[
                                                     sickbeard.indexers.indexer_config.TVINFO_IMDB][
                                                     'show_url'] % imdb_id
            else:
                sql_result[index]['imdb_url'] = ''

            if tvid_prodid in fanarts:
                continue

            for img in ek.ek(glob.glob, cache_obj.fanart_path(*tvid_prodid_obj.tuple).replace('fanart.jpg', '*')) or []:
                match = re.search(r'(\d+(?:\.\w*)?\.\w{5,8})\.fanart\.', img, re.I)
                if not match:
                    continue
                fanart = [(match.group(1), sickbeard.FANART_RATINGS.get(tvid_prodid, {}).get(match.group(1), ''))]
                if tvid_prodid not in fanarts:
                    fanarts[tvid_prodid] = fanart
                else:
                    fanarts[tvid_prodid] += fanart

        for tvid_prodid in fanarts:
            fanart_rating = [(n, v) for n, v in fanarts[tvid_prodid] if 20 == v]
            if fanart_rating:
                fanarts[tvid_prodid] = fanart_rating
            else:
                rnd = [(n, v) for (n, v) in fanarts[tvid_prodid] if 30 != v]
                grouped = [(n, v) for (n, v) in rnd if 10 == v]
                if grouped:
                    fanarts[tvid_prodid] = [grouped[random.randint(0, len(grouped) - 1)]]
                elif rnd:
                    fanarts[tvid_prodid] = [rnd[random.randint(0, len(rnd) - 1)]]

        return sql_result, fanarts, sorts, next_week_dt, today, next_week

    def daily_schedule(self, layout='None'):
        """ display the episodes """
        t = PageTemplate(web_handler=self, file='episodeView.tmpl')
        sql_result, t.fanart, sorts, next_week_dt, today, next_week = self.get_daily_schedule()
        # Allow local overriding of layout parameter
        if layout and layout in ('banner', 'daybyday', 'list', 'poster'):
            t.layout = layout
        else:
            t.layout = sickbeard.EPISODE_VIEW_LAYOUT

        t.has_art = bool(len(t.fanart))
        t.css = ' '.join([t.layout] +
                         ([], [('landscape', 'portrait')[sickbeard.EPISODE_VIEW_POSTERS]])['daybyday' == t.layout] +
                         ([], ['back-art'])[sickbeard.EPISODE_VIEW_BACKGROUND and t.has_art] +
                         ([], ['translucent'])[sickbeard.EPISODE_VIEW_BACKGROUND_TRANSLUCENT] +
                         [{0: 'reg', 1: 'pro', 2: 'pro ii'}.get(sickbeard.EPISODE_VIEW_VIEWMODE)])
        t.fanart_panel = sickbeard.FANART_PANEL

        sql_result.sort(key=sorts[sickbeard.EPISODE_VIEW_SORT])

        t.next_week = datetime.datetime.combine(next_week_dt, datetime.time(tzinfo=network_timezones.SG_TIMEZONE))
        t.today = datetime.datetime.now(network_timezones.SG_TIMEZONE)
        t.sql_results = sql_result

        return t.respond()

    @staticmethod
    def live_panel(**kwargs):

        if 'allseasons' in kwargs:
            sickbeard.DISPLAY_SHOW_MINIMUM = bool(config.minimax(kwargs['allseasons'], 0, 0, 1))
        elif 'rate' in kwargs:
            which = kwargs['which'].replace('fanart_', '')
            rating = int(kwargs['rate'])
            if rating:
                sickbeard.FANART_RATINGS.setdefault(kwargs['tvid_prodid'], {}).update({which: rating})
            elif sickbeard.FANART_RATINGS.get(kwargs['tvid_prodid'], {}).get(which):
                del sickbeard.FANART_RATINGS[kwargs['tvid_prodid']][which]
                if not sickbeard.FANART_RATINGS[kwargs['tvid_prodid']]:
                    del sickbeard.FANART_RATINGS[kwargs['tvid_prodid']]
        else:
            translucent = bool(config.minimax(kwargs.get('translucent'), 0, 0, 1))
            backart = bool(config.minimax(kwargs.get('backart'), 0, 0, 1))
            viewmode = config.minimax(kwargs.get('viewmode'), 0, 0, 2)

            if 'ds' == kwargs.get('pg'):
                if 'viewart' in kwargs:
                    sickbeard.DISPLAY_SHOW_VIEWART = config.minimax(kwargs['viewart'], 0, 0, 2)
                elif 'translucent' in kwargs:
                    sickbeard.DISPLAY_SHOW_BACKGROUND_TRANSLUCENT = translucent
                elif 'backart' in kwargs:
                    sickbeard.DISPLAY_SHOW_BACKGROUND = backart
                elif 'viewmode' in kwargs:
                    sickbeard.DISPLAY_SHOW_VIEWMODE = viewmode
            elif 'ev' == kwargs.get('pg'):
                if 'translucent' in kwargs:
                    sickbeard.EPISODE_VIEW_BACKGROUND_TRANSLUCENT = translucent
                elif 'backart' in kwargs:
                    sickbeard.EPISODE_VIEW_BACKGROUND = backart
                    sickbeard.FANART_PANEL = 'highlight-off' == sickbeard.FANART_PANEL and 'highlight-off' or \
                                             'highlight2' == sickbeard.FANART_PANEL and 'highlight1' or \
                                             'highlight1' == sickbeard.FANART_PANEL and 'highlight' or 'highlight-off'
                elif 'viewmode' in kwargs:
                    sickbeard.EPISODE_VIEW_VIEWMODE = viewmode

        sickbeard.save_config()

    @staticmethod
    def get_footer_time(change_layout=True, json_dump=True):

        now = datetime.datetime.now()
        events = [
            ('recent', sickbeard.recent_search_scheduler.timeLeft),
            ('backlog', sickbeard.backlog_search_scheduler.next_backlog_timeleft),
        ]

        if sickbeard.DOWNLOAD_PROPERS:
            events += [('propers', sickbeard.properFinder.next_proper_timeleft)]

        if change_layout not in (False, 0, '0', '', None):
            sickbeard.FOOTER_TIME_LAYOUT += 1
            if 2 == sickbeard.FOOTER_TIME_LAYOUT:  # 2 layouts = time + delta
                sickbeard.FOOTER_TIME_LAYOUT = 0
            sickbeard.save_config()

        next_event = []
        for k, v in events:
            try:
                t = v()
            except AttributeError:
                t = None
            if 0 == sickbeard.FOOTER_TIME_LAYOUT:
                next_event += [{k + '_time': t and SGDatetime.sbftime(now + t, markup=True) or 'soon'}]
            else:
                next_event += [{k + '_timeleft': t and str(t).split('.')[0] or 'soon'}]

        if json_dump not in (False, 0, '0', '', None):
            next_event = json.dumps(next_event)

        return next_event

    @staticmethod
    def update_watched_state(payload=None, as_json=True):
        """
        Update db with details of media file that is watched or unwatched

        :param payload: Payload is a dict of dicts
        :type payload: JSON or Dict
        Each dict key in payload is an arbitrary value used to return its associated success or fail response.
        Each dict value in payload comprises a dict of key value pairs where,
            key: path_file: Path and filename of media, required for media to be found.
            type: path_file:  String
            key: played: Optional default=100. Percentage times media has played. If 0, show is set as unwatched.
            type: played: String
            key: label: Optional default=''. Profile name or label in use while playing media.
            type: label: String
            key: date_watched: Optional default=current time. Datetime stamp that episode changed state.
            type: date_watched: Timestamp

        Example:
            dict(
                key01=dict(path_file='\\media\\', played=100, label='Bob', date_watched=1509850398.0),
                key02=dict(path_file='\\media\\file-played1.mkv', played=100, label='Sue', date_watched=1509850398.0),
                key03=dict(path_file='\\media\\file-played2.mkv', played=0, label='Rita', date_watched=1509850398.0)
            )
            JSON:
            '{"key01": {"path_file": "\\media\\file_played1.mkv", "played": 100,
                "label": "Bob", "date_watched": 1509850398.0}}'

        :param as_json: True returns result as JSON otherwise Dict
        :type as_json: Boolean
        :return: if OK, the value of each dict is '' else fail reason string else None if payload is invalid.
        :rtype: JSON if as_json is True otherwise None but with payload dict modified
        Example:
        Dict: {'key123': {''}} : on success
        As JSON: '{"key123": {""}}' : on success
        Dict: {'key123': {'error reason'}}
        As JSON: '{"key123": {"error reason"}}'
        Dict: {'error': {'error reason'}} : 'error' used as default key when bad key, value, or json
        JSON: '{"error": {"error reason"}}' : 'error' used as default key when bad key, value, or json

Example case code using API endpoint, copy/paste, edit to suit, save, then run with: python sg_watched.py
```
import json
import urllib2

# SickGear APIkey
sg_apikey = '0123456789abcdef'
# SickGear server detail
sg_host = 'http://localhost:8081'

url = '%s/api/%s/?cmd=sg.updatewatchedstate' % (sg_host, sg_apikey)
payload = json.dumps(dict(
    key01=dict(path_file='\\media\\path\\', played=100, label='Bob', date_watched=1509850398.0),
    key02=dict(path_file='\\media\\path\\file-played1.mkv', played=100, label='Sue', date_watched=1509850398.0),
    key03=dict(path_file='\\media\\path\\file-played2.mkv', played=0, label='Rita', date_watched=1509850398.0)
))
# payload is POST'ed to SG
rq = urllib2.Request(url, data=payload)
r = urllib2.urlopen(rq)
print json.load(r)
r.close()
```
        """
        try:
            data = json.loads(payload)
        except ValueError:
            payload = {}
            data = payload
        except TypeError:
            data = payload

        sql_result = []
        if data:
            my_db = db.DBConnection(row_type='dict')

            media_paths = map_list(lambda arg: ek.ek(os.path.basename, arg[1]['path_file']), iteritems(data))

            def chunks(lines, n):
                for c in range(0, len(lines), n):
                    yield lines[c:c + n]

            # noinspection PyTypeChecker
            for x in chunks(media_paths, 100):
                # noinspection PyTypeChecker
                sql_result += my_db.select(
                    'SELECT episode_id, status, location, file_size FROM tv_episodes WHERE file_size > 0 AND (%s)' %
                    ' OR '.join(['location LIKE "%%%s"' % i for i in x]))

        if sql_result:
            cl = []

            ep_results = {}
            map_consume(lambda r: ep_results.update({'%s' % ek.ek(os.path.basename, r['location']).lower(): dict(
                        episode_id=r['episode_id'], status=r['status'], location=r['location'],
                        file_size=r['file_size'])}), sql_result)

            for (k, v) in iteritems(data):

                bname = (ek.ek(os.path.basename, v.get('path_file')) or '').lower()
                if not bname:
                    msg = 'Missing media file name provided'
                    data[k] = msg
                    logger.log('Update watched state skipped an item: %s' % msg, logger.WARNING)
                    continue

                if bname in ep_results:
                    date_watched = now = int(timestamp_near(datetime.datetime.now()))
                    if 1500000000 < date_watched:
                        date_watched = helpers.try_int(float(v.get('date_watched')))

                    ep_data = ep_results[bname]
                    # using label and location with upsert to list multi-client items at same location
                    # can omit label to have the latest scanned client upsert an existing client row based on location
                    cl.extend(db.mass_upsert_sql(
                        'tv_episodes_watched',
                        dict(tvep_id=ep_data['episode_id'], clientep_id=v.get('media_id', '') or '',
                             played=v.get('played', 1),
                             date_watched=date_watched, date_added=now,
                             status=ep_data['status'], file_size=ep_data['file_size']),
                        dict(location=ep_data['location'], label=v.get('label', '')), sanitise=False))

                    data[k] = ''

            if cl:
                # noinspection PyUnboundLocalVariable
                my_db.mass_action(cl)

        if as_json:
            if not data:
                data = dict(error='Request made to SickGear with invalid payload')
                logger.log('Update watched state failed: %s' % data['error'], logger.WARNING)

            return json.dumps(data)

    def toggle_specials_view_show(self, tvid_prodid):
        sickbeard.DISPLAY_SHOW_SPECIALS = not sickbeard.DISPLAY_SHOW_SPECIALS

        self.redirect('/home/view-show?tvid_prodid=%s' % tvid_prodid)

    def set_layout_history(self, layout):

        if layout not in ('compact', 'detailed', 'compact_watched', 'detailed_watched',
                          'compact_stats', 'graph_stats', 'connect_failures'):
            if 'provider_failures' == layout:  # layout renamed
                layout = 'connect_failures'
            else:
                layout = 'detailed'

        sickbeard.HISTORY_LAYOUT = layout

        self.redirect('/history/')

    def _generic_message(self, subject, message):
        t = PageTemplate(web_handler=self, file='genericMessage.tmpl')
        t.submenu = Home(self.application, self.request).home_menu()
        t.subject = subject
        t.message = message
        return t.respond()


class Home(MainHandler):

    def home_menu(self):
        return [
            {'title': 'Process Media', 'path': 'home/process-media/'},
            {'title': 'Update Emby', 'path': 'home/update-mb/', 'requires': self.have_emby},
            {'title': 'Update Kodi', 'path': 'home/update-kodi/', 'requires': self.have_kodi},
            {'title': 'Update XBMC', 'path': 'home/update-xbmc/', 'requires': self.have_xbmc},
            {'title': 'Update Plex', 'path': 'home/update-plex/', 'requires': self.have_plex}
        ]

    @staticmethod
    def have_emby():
        return sickbeard.USE_EMBY

    @staticmethod
    def have_kodi():
        return sickbeard.USE_KODI

    @staticmethod
    def have_xbmc():
        return sickbeard.USE_XBMC and sickbeard.XBMC_UPDATE_LIBRARY

    @staticmethod
    def have_plex():
        return sickbeard.USE_PLEX and sickbeard.PLEX_UPDATE_LIBRARY

    @staticmethod
    def _get_episode(tvid_prodid, season=None, episode=None, absolute=None):
        """

        :param tvid_prodid:
        :type tvid_prodid:
        :param season:
        :type season:
        :param episode:
        :type episode:
        :param absolute:
        :type absolute:
        :return:
        :rtype: sickbeard.tv.TVEpisode
        """
        if None is tvid_prodid:
            return 'Invalid show parameters'

        show_obj = helpers.find_show_by_id(tvid_prodid)
        if None is show_obj:
            return 'Invalid show paramaters'

        if absolute:
            ep_obj = show_obj.get_episode(absolute_number=int(absolute))
        elif None is not season and None is not episode:
            ep_obj = show_obj.get_episode(int(season), int(episode))
        else:
            return 'Invalid paramaters'

        if None is ep_obj:
            return "Episode couldn't be retrieved"

        return ep_obj

    def index(self):
        if 'episodes' == sickbeard.DEFAULT_HOME:
            self.redirect('/daily-schedule/')
        elif 'history' == sickbeard.DEFAULT_HOME:
            self.redirect('/history/')
        else:
            self.redirect('/view-shows/')

    def view_shows(self):
        t = PageTemplate(web_handler=self, file='home.tmpl')
        t.showlists = []
        index = 0
        if 'custom' == sickbeard.SHOWLIST_TAGVIEW:
            for name in sickbeard.SHOW_TAGS:
                results = filter_list(lambda so: so.tag == name, sickbeard.showList)
                if results:
                    t.showlists.append(['container%s' % index, name, results])
                index += 1
        elif 'anime' == sickbeard.SHOWLIST_TAGVIEW:
            show_results = filter_list(lambda so: not so.anime, sickbeard.showList)
            anime_results = filter_list(lambda so: so.anime, sickbeard.showList)
            if show_results:
                t.showlists.append(['container%s' % index, 'Show List', show_results])
                index += 1
            if anime_results:
                t.showlists.append(['container%s' % index, 'Anime List', anime_results])

        if 0 == len(t.showlists):
            t.showlists.append(['container0', 'Show List', sickbeard.showList])
        else:
            items = []
            default = 0
            for index, group in enumerate(t.showlists):
                items += group[2]
                default = (default, index)['Show List' == group[1]]
            t.showlists[default][2] += [cur_so for cur_so in sickbeard.showList if cur_so not in items]

        if 'simple' != sickbeard.HOME_LAYOUT:
            t.network_images = {}
            networks = {}
            images_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', 'network')
            for cur_show_obj in sickbeard.showList:
                network_name = 'nonetwork' if None is cur_show_obj.network \
                    else cur_show_obj.network.replace(u'\u00C9', 'e').lower()
                if network_name not in networks:
                    filename = u'%s.png' % network_name
                    if not ek.ek(os.path.isfile, ek.ek(os.path.join, images_path, filename)):
                        filename = u'%s.png' % re.sub(r'(?m)(.*)\s+\(\w{2}\)$', r'\1', network_name)
                        if not ek.ek(os.path.isfile, ek.ek(os.path.join, images_path, filename)):
                            filename = u'nonetwork.png'
                    networks.setdefault(network_name, filename)
                t.network_images.setdefault(cur_show_obj.tvid_prodid, networks[network_name])

        t.submenu = self.home_menu()
        t.layout = sickbeard.HOME_LAYOUT

        # Get all show snatched / downloaded / next air date stats
        my_db = db.DBConnection()
        today = datetime.date.today().toordinal()
        status_quality = ','.join([str(x) for x in Quality.SNATCHED_ANY])
        status_download = ','.join([str(x) for x in Quality.DOWNLOADED + Quality.ARCHIVED])
        status_total = '%s, %s, %s' % (SKIPPED, WANTED, FAILED)

        sql_result = my_db.select(
            'SELECT indexer AS tvid, showid as prodid, '
            + '(SELECT COUNT(*) FROM tv_episodes'
              ' WHERE indexer = tv_eps.indexer AND showid = tv_eps.showid'
              ' AND season > 0 AND episode > 0 AND airdate > 1 AND status IN (%s)) AS ep_snatched,'
              ' (SELECT COUNT(*) FROM tv_episodes'
              ' WHERE indexer = tv_eps.indexer AND showid = tv_eps.showid'
              ' AND season > 0 AND episode > 0 AND airdate > 1 AND status IN (%s)) AS ep_downloaded,'
              ' (SELECT COUNT(*) FROM tv_episodes'
              ' WHERE indexer = tv_eps.indexer AND showid = tv_eps.showid'
              ' AND season > 0 AND episode > 0 AND airdate > 1'
              ' AND ('
              '(airdate <= %s AND (status IN (%s)))'
              ' OR (status IN (%s)) OR (status IN (%s)))) AS ep_total,'
              ' (SELECT airdate FROM tv_episodes'
              ' WHERE indexer = tv_eps.indexer AND showid = tv_eps.showid'
              ' AND airdate >= %s AND (status = %s  OR status = %s)'
              ' ORDER BY airdate ASC LIMIT 1) AS ep_airs_next'
              ' FROM tv_episodes tv_eps GROUP BY indexer, showid'
            % (status_quality, status_download, today, status_total,
               status_quality, status_download, today, UNAIRED, WANTED))

        t.show_stat = {}

        for cur_result in sql_result:
            t.show_stat[TVidProdid({cur_result['tvid']: cur_result['prodid']})()] = cur_result

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

        authed, auth_msg, void = nzbget.test_nzbget(host, bool(config.checkbox_to_value(use_https)), username, password,
                                                    timeout=20)
        return auth_msg

    def test_torrent(self, torrent_method=None, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_url(host)
        if None is not password and set('*') == set(password):
            password = sickbeard.TORRENT_PASSWORD

        client = clients.get_client_instance(torrent_method)

        connection, acces_msg = client(host, username, password).test_authentication()

        return acces_msg

    def test_flaresolverr(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=8191)
        if not hosts:
            return 'Fail: No valid host(s)'

        try:
            fs_ver = CloudflareScraper().test_flaresolverr(host)
            result = 'Successful connection to FlareSolverr %s' % fs_ver
        except(BaseException, Exception):
            result = 'Failed host connection (is it running?)'

        ui.notifications.message('Tested Flaresolverr:', unquote_plus(hosts))
        return result

    @staticmethod
    def discover_emby():
        return notifiers.NotifierFactory().get('EMBY').discover_server()

    def test_emby(self, host=None, apikey=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=8096)
        if not hosts:
            return 'Fail: No valid host(s)'

        result = notifiers.NotifierFactory().get('EMBY').test_notify(hosts, apikey)

        ui.notifications.message('Tested Emby:', unquote_plus(hosts.replace(',', ', ')))
        return result

    def test_kodi(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=8080)
        if not hosts:
            return 'Fail: No valid host(s)'

        if None is not password and set('*') == set(password):
            password = sickbeard.KODI_PASSWORD

        result = notifiers.NotifierFactory().get('KODI').test_notify(hosts, username, password)

        ui.notifications.message('Tested Kodi:', unquote_plus(hosts.replace(',', ', ')))
        return result

    def test_plex(self, host=None, username=None, password=None, server=False):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=32400)
        if not hosts:
            return 'Fail: No valid host(s)'

        if None is not password and set('*') == set(password):
            password = sickbeard.PLEX_PASSWORD

        server = 'true' == server
        n = notifiers.NotifierFactory().get('PLEX')
        method = n.test_update_library if server else n.test_notify
        result = method(hosts, username, password)

        ui.notifications.message('Tested Plex %s(s): ' % ('client', 'Media Server host')[server],
                                 unquote_plus(hosts.replace(',', ', ')))
        return result

    def test_nmj(self, host=None, database=None, mount=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        if not host:
            return 'Fail: No valid host(s)'

        return notifiers.NotifierFactory().get('NMJ').test_notify(unquote_plus(host), database, mount)

    def settings_nmj(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        if not host:
            return 'Fail: No valid host(s)'

        return notifiers.NotifierFactory().get('NMJ').notify_settings(unquote_plus(host))

    def test_nmj2(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        if not host:
            return 'Fail: No valid host(s)'

        return notifiers.NotifierFactory().get('NMJV2').test_notify(unquote_plus(host))

    def settings_nmj2(self, host=None, dbloc=None, instance=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        return notifiers.NotifierFactory().get('NMJV2').notify_settings(unquote_plus(host), dbloc, instance)

    def test_boxcar2(self, access_token=None, sound=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not access_token and starify(access_token, True):
            access_token = sickbeard.BOXCAR2_ACCESSTOKEN

        return notifiers.NotifierFactory().get('BOXCAR2').test_notify(access_token, sound)

    def test_pushbullet(self, access_token=None, device_iden=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not access_token and starify(access_token, True):
            access_token = sickbeard.PUSHBULLET_ACCESS_TOKEN

        return notifiers.NotifierFactory().get('PUSHBULLET').test_notify(access_token, device_iden)

    def get_pushbullet_devices(self, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not access_token and starify(access_token, True):
            access_token = sickbeard.PUSHBULLET_ACCESS_TOKEN

        return notifiers.NotifierFactory().get('PUSHBULLET').get_devices(access_token)

    def test_pushover(self, user_key=None, api_key=None, priority=None, device=None, sound=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not user_key and starify(user_key, True):
            user_key = sickbeard.PUSHOVER_USERKEY

        if None is not api_key and starify(api_key, True):
            api_key = sickbeard.PUSHOVER_APIKEY

        return notifiers.NotifierFactory().get('PUSHOVER').test_notify(user_key, api_key, priority, device, sound)

    def get_pushover_devices(self, user_key=None, api_key=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not user_key and starify(user_key, True):
            user_key = sickbeard.PUSHOVER_USERKEY

        if None is not api_key and starify(api_key, True):
            api_key = sickbeard.PUSHOVER_APIKEY

        return notifiers.NotifierFactory().get('PUSHOVER').get_devices(user_key, api_key)

    def test_growl(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=23053)
        if not hosts:
            return 'Fail: No valid host(s)'

        result = notifiers.NotifierFactory().get('GROWL').test_notify(None, hosts)

        ui.notifications.message('Tested Growl:', unquote_plus(hosts.replace(',', ', ')))
        return result

    def test_prowl(self, prowl_api=None, prowl_priority=0):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not prowl_api and starify(prowl_api, True):
            prowl_api = sickbeard.PROWL_API

        return notifiers.NotifierFactory().get('PROWL').test_notify(prowl_api, prowl_priority)

    def test_libnotify(self):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('LIBNOTIFY').test_notify()

    def trakt_authenticate(self, pin=None, account=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is pin:
            return json.dumps({'result': 'Fail', 'error_message': 'Trakt PIN required for authentication'})

        if account and 'new' == account:
            account = None

        acc = None
        if account:
            acc = helpers.try_int(account, -1)
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
            aid = helpers.try_int(accountid, None)
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

    def load_show_notify_lists(self):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        my_db = db.DBConnection()
        # noinspection SqlResolve
        rows = my_db.select(
            'SELECT indexer || ? ||  indexer_id AS tvid_prodid, notify_list'
            ' FROM tv_shows'
            ' WHERE notify_list NOTNULL'
            ' AND notify_list != ""',
            [TVidProdid.glue])
        notify_lists = {}
        for r in filter_iter(lambda x: x['notify_list'].strip(), rows):
            # noinspection PyTypeChecker
            notify_lists[r['tvid_prodid']] = r['notify_list']

        sorted_show_lists = self.sorted_show_lists()
        response = []
        for current_group in sorted_show_lists:
            data = []
            for show_obj in current_group[1]:
                data.append({
                    'id': show_obj.tvid_prodid,
                    'name': show_obj.name,
                    'list': '' if show_obj.tvid_prodid not in notify_lists else notify_lists[show_obj.tvid_prodid]})
            if data:
                response.append({current_group[0]: data})

        return json.dumps(response)

    def test_slack(self, channel=None, as_authed=False, bot_name=None, icon_url=None, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('SLACK').test_notify(
            channel=channel, as_authed='true' == as_authed,
            bot_name=bot_name, icon_url=icon_url, access_token=access_token)

    def test_discord(self, as_authed=False, username=None, icon_url=None, as_tts=False, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('DISCORD').test_notify(
            as_authed='true' == as_authed, username=username, icon_url=icon_url,
            as_tts='true' == as_tts, access_token=access_token)

    def test_gitter(self, room_name=None, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('GITTER').test_notify(
            room_name=room_name, access_token=access_token)

    def test_telegram(self, send_icon=False, access_token=None, chatid=None, quiet=False):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        r = notifiers.NotifierFactory().get('TELEGRAM').test_notify(
            send_icon=bool(config.checkbox_to_value(send_icon)), access_token=access_token, chatid=chatid, quiet=quiet)
        return json.dumps(r)

    def test_email(self, host=None, port=None, smtp_from=None, use_tls=None, user=None, pwd=None, to=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not pwd and set('*') == set(pwd):
            pwd = sickbeard.EMAIL_PASSWORD

        host = config.clean_host(host)

        return notifiers.NotifierFactory().get('EMAIL').test_notify(host, port, smtp_from, use_tls, user, pwd, to)

    @staticmethod
    def save_show_email(show=None, emails=None):
        # self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        my_db = db.DBConnection()
        success = False
        parse = show.split(TVidProdid.glue)
        if 1 < len(parse) and \
                my_db.action('UPDATE tv_shows SET notify_list = ?'
                             ' WHERE indexer = ? AND indexer_id = ?',
                             [emails, parse[0], parse[1]]):
            success = True
        return json.dumps({'id': show, 'success': success})

    def check_update(self):
        # force a check to see if there is a new version
        if sickbeard.update_software_scheduler.action.check_for_new_version(force=True):
            logger.log(u'Forced version check found results')

        if sickbeard.update_packages_scheduler.action.check_for_new_version(force=True):
            logger.log(u'Forced package version check found results')

        self.redirect('/home/')

    def view_changes(self):

        t = PageTemplate(web_handler=self, file='viewchanges.tmpl')

        t.changelist = [{'type': 'rel', 'ver': '', 'date': 'Nothing to display at this time'}]
        url = 'https://raw.githubusercontent.com/wiki/SickGear/SickGear/sickgear/CHANGES.md'
        response = helpers.get_url(url)
        if not response:
            return t.respond()

        data = response.replace('\xef\xbb\xbf', '').splitlines()

        output, change, max_rel = [], {}, 5
        for line in data:
            if not line.strip():
                continue
            if line.startswith('  '):
                change_parts = re.findall(r'^[\W]+(.*)$', line)
                change['text'] += change_parts and (' %s' % change_parts[0].strip()) or ''
            else:
                if change:
                    output.append(change)
                    change = None
                if line.startswith('* '):
                    change_parts = re.findall(r'^[*\W]+(Add|Change|Fix|Port|Remove|Update)\W(.*)', line)
                    change = change_parts and {'type': change_parts[0][0], 'text': change_parts[0][1].strip()} or {}
                elif not max_rel:
                    break
                elif line.startswith('### '):
                    rel_data = re.findall(r'(?im)^###\W*([^\s]+)\W\(([^)]+)\)', line)
                    rel_data and output.append({'type': 'rel', 'ver': rel_data[0][0], 'date': rel_data[0][1]})
                    max_rel -= 1
                elif line.startswith('# '):
                    max_data = re.findall(r'^#\W*([\d]+)\W*$', line)
                    max_rel = max_data and helpers.try_int(max_data[0], None) or 5
        if change:
            output.append(change)

        t.changelist = output
        return t.respond()

    def shutdown(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        t = PageTemplate(web_handler=self, file='restart.tmpl')
        t.shutdown = True

        sickbeard.events.put(sickbeard.events.SystemEvent.SHUTDOWN)

        return t.respond()

    def restart(self, pid=None, update_pkg=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        t = PageTemplate(web_handler=self, file='restart.tmpl')
        t.shutdown = False

        sickbeard.restart(soft=False, update_pkg=bool(helpers.try_int(update_pkg)))

        return t.respond()

    def update(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        if sickbeard.update_software_scheduler.action.update():
            return self.restart(pid)

        return self._generic_message('Update Failed',
                                     'Update wasn\'t successful, not restarting. Check your log for more information.')

    def branch_checkout(self, branch):
        sickbeard.BRANCH = branch
        ui.notifications.message('Checking out branch: ', branch)
        return self.update(sickbeard.PID)

    def pull_request_checkout(self, branch):
        pull_request = branch
        branch = branch.split(':')[1]
        fetched = sickbeard.update_software_scheduler.action.fetch(pull_request)
        if fetched:
            sickbeard.BRANCH = branch
            ui.notifications.message('Checking out branch: ', branch)
            return self.update(sickbeard.PID)
        else:
            self.redirect('/home/')

    def season_render(self, tvid_prodid=None, season=None, **kwargs):

        response = {'success': False}
        # noinspection PyTypeChecker
        show_obj = None
        if tvid_prodid:
            show_obj = helpers.find_show_by_id(tvid_prodid)
        if not show_obj:
            return json.dumps(response)

        re_season = re.compile(r'(?i)^showseason-(\d+)$')
        season = None if not any(re_season.findall(season)) else \
            helpers.try_int(re_season.findall(season)[0], None)
        if None is season:
            return json.dumps(response)

        t = PageTemplate(web_handler=self, file='inc_displayShow.tmpl')
        t.show_obj = show_obj

        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT *'
                                  ' FROM tv_episodes'
                                  ' WHERE indexer = ? AND showid = ?'
                                  ' AND season = ?'
                                  ' ORDER BY episode DESC',
                                  [show_obj.tvid, show_obj.prodid,
                                   season])
        t.episodes = sql_result

        ep_cats = {}
        for cur_result in sql_result:
            status_overview = show_obj.get_overview(int(cur_result['status']))
            if status_overview:
                ep_cats['%sx%s' % (season, cur_result['episode'])] = status_overview
        t.ep_cats = ep_cats

        args = (int(show_obj.tvid), int(show_obj.prodid))
        t.scene_numbering = get_scene_numbering_for_show(*args)
        t.xem_numbering = get_xem_numbering_for_show(*args)
        t.scene_absolute_numbering = get_scene_absolute_numbering_for_show(*args)
        t.xem_absolute_numbering = get_xem_absolute_numbering_for_show(*args)

        return json.dumps({'success': t.respond()})

    def view_show(self, tvid_prodid=None):

        if None is tvid_prodid:
            return self._generic_message('Error', 'Invalid show ID')

        show_obj = helpers.find_show_by_id(tvid_prodid)
        if None is show_obj:
            return self._generic_message('Error', 'Show not in show list')

        t = PageTemplate(web_handler=self, file='displayShow.tmpl')
        t.submenu = [{'title': 'Edit', 'path': 'home/edit-show?tvid_prodid=%s' % tvid_prodid}]

        try:
            t.showLoc = (show_obj.location, True)
        except exceptions_helper.ShowDirNotFoundException:
            # noinspection PyProtectedMember
            t.showLoc = (show_obj._location, False)

        show_message = []

        if sickbeard.show_queue_scheduler.action.isBeingAdded(show_obj):
            show_message = ['Downloading this show, the information below is incomplete']

        elif sickbeard.show_queue_scheduler.action.isBeingUpdated(show_obj):
            show_message = ['Updating information for this show']

        elif sickbeard.show_queue_scheduler.action.isBeingRefreshed(show_obj):
            show_message = ['Refreshing episodes from disk for this show']

        elif sickbeard.show_queue_scheduler.action.isBeingSubtitled(show_obj):
            show_message = ['Downloading subtitles for this show']

        elif sickbeard.show_queue_scheduler.action.isInRefreshQueue(show_obj):
            show_message = ['Refresh queued for this show']

        elif sickbeard.show_queue_scheduler.action.isInUpdateQueue(show_obj):
            show_message = ['Update queued for this show']

        elif sickbeard.show_queue_scheduler.action.isInSubtitleQueue(show_obj):
            show_message = ['Subtitle download queued for this show']

        if sickbeard.show_queue_scheduler.action.is_show_being_switched(show_obj):
            show_message += ['Switching TV info source and awaiting update for this show']

        elif sickbeard.show_queue_scheduler.action.is_show_switch_queued(show_obj):
            show_message += ['Queuing a switch of TV info source for this show']

        if sickbeard.people_queue_scheduler.action.show_in_queue(show_obj, check_inprogress=True):
            show_message += ['Updating cast for this show']
        elif sickbeard.people_queue_scheduler.action.show_in_queue(show_obj):
            show_message += ['Cast update queued for this show']

        if 0 != show_obj.not_found_count:
            last_found = ('', ' since %s' % SGDatetime.fromordinal(
                show_obj.last_found_on_indexer).sbfdate())[1 < show_obj.last_found_on_indexer]
            show_message += [
                'The master ID of this show has been <span class="addQTip" title="many reasons exist, including: ' +
                '<br>show flagged as a duplicate, removed completely... etc">abandoned</span>%s, ' % last_found +
                '<a href="%s/home/edit-show?tvid_prodid=%s&tvsrc=0&srcid=%s#core-component-group3">replace it here</a>'
                % (sickbeard.WEB_ROOT, tvid_prodid, show_obj.prodid)]

        show_message = '.<br>'.join(show_message)

        t.force_update = 'home/update-show?tvid_prodid=%s&amp;force=1&amp;web=1' % tvid_prodid
        if not sickbeard.show_queue_scheduler.action.isBeingAdded(show_obj):
            if not sickbeard.show_queue_scheduler.action.isBeingUpdated(show_obj):
                t.submenu.append(
                    {'title': 'Remove',
                     'path': 'home/delete-show?tvid_prodid=%s' % tvid_prodid, 'confirm': True})
                t.submenu.append(
                    {'title': 'Re-scan files', 'path': 'home/refresh-show?tvid_prodid=%s' % tvid_prodid})
                t.submenu.append(
                    {'title': 'Force Full Update', 'path': t.force_update})
                t.submenu.append(
                    {'title': 'Cast Update', 'path': 'home/update-cast?tvid_prodid=%s' % tvid_prodid})
                t.submenu.append(
                    {'title': 'Update show in Emby',
                     'path': 'home/update-mb%s' % (
                             TVINFO_TVDB == show_obj.tvid and ('?tvid_prodid=%s' % tvid_prodid) or '/'),
                     'requires': self.have_emby})
                t.submenu.append(
                    {'title': 'Update show in Kodi', 'path': 'home/update-kodi?show_name=%s' % quote_plus(
                        show_obj.name.encode('utf-8')), 'requires': self.have_kodi})
                t.submenu.append(
                    {'title': 'Update show in XBMC',
                     'path': 'home/update-xbmc?show_name=%s' % quote_plus(
                         show_obj.name.encode('utf-8')), 'requires': self.have_xbmc})
                t.submenu.append(
                    {'title': 'Media Rename',
                     'path': 'home/rename-media?tvid_prodid=%s' % tvid_prodid})
                if sickbeard.USE_SUBTITLES and not sickbeard.show_queue_scheduler.action.isBeingSubtitled(
                        show_obj) and show_obj.subtitles:
                    t.submenu.append(
                        {'title': 'Download Subtitles',
                         'path': 'home/subtitle-show?tvid_prodid=%s' % tvid_prodid})

        t.show_obj = show_obj
        with BS4Parser('<html><body>%s</body></html>' % show_obj.overview, features=['html5lib', 'permissive']) as soup:
            try:
                soup.a.replace_with(soup.new_tag(''))
            except (BaseException, Exception):
                pass
            overview = re.sub('(?i)full streaming', '', soup.get_text().strip())
        t.show_obj.overview = overview
        t.show_message = show_message

        ep_counts = {}
        ep_cats = {}
        ep_counts[Overview.SKIPPED] = 0
        ep_counts[Overview.WANTED] = 0
        ep_counts[Overview.QUAL] = 0
        ep_counts[Overview.GOOD] = 0
        ep_counts[Overview.UNAIRED] = 0
        ep_counts[Overview.SNATCHED] = 0
        ep_counts['videos'] = {}
        ep_counts['status'] = {}
        ep_counts['archived'] = {}
        ep_counts['totals'] = {}
        ep_counts['eps_most'] = 0
        ep_counts['eps_all'] = 0
        t.latest_season = 0
        t.has_special = False

        my_db = db.DBConnection()

        failed_check = my_db.select('SELECT status FROM tv_src_switch WHERE old_indexer = ? AND old_indexer_id = ?'
                                    ' AND status != ?', [show_obj.tvid, show_obj.prodid, TVSWITCH_NORMAL])
        if failed_check:
            t.show_message = '%s%s%s' % \
                             (t.show_message, ('<br>', '')[0 == len(t.show_message)],
                              'Failed to switch tv info source: %s' %
                              tvswitch_names.get(failed_check[0]['status'], 'Unknown reason'))

        for row in my_db.select('SELECT season, count(*) AS cnt'
                                ' FROM tv_episodes'
                                ' WHERE indexer = ? AND showid = ?'
                                ' GROUP BY season',
                                [show_obj.tvid, show_obj.prodid]):
            ep_counts['totals'][row['season']] = row['cnt']

        if None is not ep_counts['totals'].get(0):
            t.has_special = True
            if not sickbeard.DISPLAY_SHOW_SPECIALS:
                del (ep_counts['totals'][0])

        ep_counts['eps_all'] = sum(itervalues(ep_counts['totals']))
        ep_counts['eps_most'] = max(list_values(ep_counts['totals']) + [0])
        all_seasons = sorted(iterkeys(ep_counts['totals']), reverse=True)
        t.lowest_season, t.highest_season = all_seasons and (all_seasons[-1], all_seasons[0]) or (0, 0)

        # 55 == seasons 1-10 and excludes the random season 0
        force_display_show_minimum = 30 < ep_counts['eps_most'] or 55 < sum(ep_counts['totals'])
        display_show_minimum = sickbeard.DISPLAY_SHOW_MINIMUM or force_display_show_minimum

        for row in my_db.select('SELECT max(season) AS latest'
                                ' FROM tv_episodes'
                                ' WHERE indexer = ? AND showid = ?'
                                ' AND 1000 < airdate AND ? < status',
                                [show_obj.tvid, show_obj.prodid,
                                 UNAIRED]):
            t.latest_season = row['latest'] or {0: 1, 1: 1, 2: -1}.get(sickbeard.DISPLAY_SHOW_VIEWMODE)

        t.season_min = ([], [1])[2 < t.latest_season] + [t.latest_season]
        t.other_seasons = (list(set(all_seasons) - set(t.season_min)), [])[display_show_minimum]
        t.seasons = []
        for x in all_seasons:
            t.seasons += [(x, [None] if x not in (t.season_min + t.other_seasons) else my_db.select(
                'SELECT *'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' AND season = ?'
                ' ORDER BY episode DESC',
                [show_obj.tvid, show_obj.prodid, x]
            ), scene_exceptions.has_season_exceptions(show_obj.tvid, show_obj.prodid, x))]

        for row in my_db.select('SELECT season, episode, status'
                                ' FROM tv_episodes'
                                ' WHERE indexer = ? AND showid = ?'
                                ' AND season IN (%s)' % ','.join(['?'] * len(t.season_min + t.other_seasons)),
                                [show_obj.tvid, show_obj.prodid]
                                + t.season_min + t.other_seasons):
            status_overview = show_obj.get_overview(row['status'])
            if status_overview:
                ep_cats['%sx%s' % (row['season'], row['episode'])] = status_overview
        t.ep_cats = ep_cats

        for row in my_db.select('SELECT season, count(*) AS cnt, status'
                                ' FROM tv_episodes'
                                ' WHERE indexer = ? AND showid = ?'
                                ' GROUP BY season, status',
                                [show_obj.tvid, show_obj.prodid]):
            status_overview = show_obj.get_overview(row['status'])
            if status_overview:
                ep_counts[status_overview] += row['cnt']
                if ARCHIVED == Quality.splitCompositeStatus(row['status'])[0]:
                    ep_counts['archived'].setdefault(row['season'], 0)
                    ep_counts['archived'][row['season']] = row['cnt'] + ep_counts['archived'].get(row['season'], 0)
                else:
                    ep_counts['status'].setdefault(row['season'], {})
                    ep_counts['status'][row['season']][status_overview] = row['cnt'] + \
                        ep_counts['status'][row['season']].get(status_overview, 0)

        for row in my_db.select('SELECT season, count(*) AS cnt FROM tv_episodes'
                                ' WHERE indexer = ? AND showid = ?'
                                ' AND \'\' != location'
                                ' GROUP BY season',
                                [show_obj.tvid, show_obj.prodid]):
            ep_counts['videos'][row['season']] = row['cnt']
        t.ep_counts = ep_counts

        t.sortedShowLists = self.sorted_show_lists()
        t.tvshow_id_csv = []
        tvshow_names = []
        cur_sel = None
        for cur_tvshow_types in t.sortedShowLists:
            for cur_show_obj in cur_tvshow_types[1]:
                t.tvshow_id_csv.append(cur_show_obj.tvid_prodid)
                tvshow_names.append(cur_show_obj.name)
                if show_obj.tvid_prodid == cur_show_obj.tvid_prodid:
                    cur_sel = len(tvshow_names)

        last_item = len(tvshow_names)
        t.prev_title = ''
        t.next_title = ''
        if cur_sel:
            t.prev_title = 'Prev show, %s' % tvshow_names[(cur_sel - 2, last_item - 1)[1 == cur_sel]]
            t.next_title = 'Next show, %s' % tvshow_names[(cur_sel, 0)[last_item == cur_sel]]

        t.anigroups = None
        if show_obj.is_anime:
            t.anigroups = show_obj.release_groups

        t.fanart = []
        cache_obj = image_cache.ImageCache()
        for img in ek.ek(glob.glob,
                         cache_obj.fanart_path(show_obj.tvid, show_obj.prodid).replace('fanart.jpg', '*')) or []:
            match = re.search(r'(\d+(?:\.(\w*?(\d*)))?\.\w{5,8})\.fanart\.', img, re.I)
            if match and match.group(1):
                t.fanart += [(match.group(1),
                              sickbeard.FANART_RATINGS.get(tvid_prodid, {}).get(match.group(1), ''))]

        t.start_image = None
        ratings = [v for n, v in t.fanart]
        if 20 in ratings:
            t.start_image = ratings.index(20)
        else:
            rnd = [(x, v) for x, (n, v) in enumerate(t.fanart) if 30 != v]
            grouped = [n for (n, v) in rnd if 10 == v]
            if grouped:
                t.start_image = grouped[random.randint(0, len(grouped) - 1)]
            elif rnd:
                t.start_image = rnd[random.randint(0, len(rnd) - 1)][0]
        t.has_art = bool(len(t.fanart))
        t.css = ' '.join(([], ['back-art'])[sickbeard.DISPLAY_SHOW_BACKGROUND and t.has_art] +
                         ([], ['translucent'])[sickbeard.DISPLAY_SHOW_BACKGROUND_TRANSLUCENT] +
                         {0: [], 1: ['poster-right'], 2: ['poster-off']}.get(sickbeard.DISPLAY_SHOW_VIEWART) +
                         ([], ['min'])[display_show_minimum] +
                         ([], ['min-force'])[force_display_show_minimum] +
                         [{0: 'reg', 1: 'pro', 2: 'pro ii'}.get(sickbeard.DISPLAY_SHOW_VIEWMODE)])

        t.clean_show_name = quote_plus(sickbeard.indexermapper.clean_show_name(show_obj.name))

        t.min_initial = Quality.get_quality_ui(min(Quality.splitQuality(show_obj.quality)[0]))
        t.show_obj.exceptions = scene_exceptions.get_scene_exceptions(show_obj.tvid, show_obj.prodid)
        # noinspection PyUnresolvedReferences
        t.all_scene_exceptions = show_obj.exceptions  # normally Unresolved as not a class attribute, force set above
        t.scene_numbering = get_scene_numbering_for_show(show_obj.tvid, show_obj.prodid)
        t.scene_absolute_numbering = get_scene_absolute_numbering_for_show(show_obj.tvid, show_obj.prodid)
        t.xem_numbering = get_xem_numbering_for_show(show_obj.tvid, show_obj.prodid)
        t.xem_absolute_numbering = get_xem_absolute_numbering_for_show(show_obj.tvid, show_obj.prodid)

        return t.respond()

    @staticmethod
    def make_showlist_unique_names():
        def titler(x):
            return (remove_article(x), x)[not x or sickbeard.SORT_ARTICLE].lower()

        sorted_show_list = sorted(sickbeard.showList, key=lambda x: titler(x.name))
        year_check = re.compile(r' \(\d{4}\)$')
        dups = {}

        for i, val in enumerate(sorted_show_list):
            if val.name not in dups:
                # Store index of first occurrence and occurrence value
                dups[val.name] = i
                val.unique_name = val.name
            else:
                # remove cached parsed result
                sickbeard.name_parser.parser.name_parser_cache.flush(val)
                if not year_check.search(sorted_show_list[dups[val.name]].name):
                    # add year to first show
                    first_ep = sorted_show_list[dups[val.name]].first_aired_regular_episode
                    start_year = (first_ep and first_ep.airdate and first_ep.airdate.year) or \
                        sorted_show_list[dups[val.name]].startyear
                    if start_year:
                        sorted_show_list[dups[val.name]].unique_name = '%s (%s)' % (
                            sorted_show_list[dups[val.name]].name, start_year)
                        dups[sorted_show_list[dups[val.name]].unique_name] = i
                if not year_check.search(sorted_show_list[i].name):
                    # add year to duplicate
                    first_ep = sorted_show_list[i].first_aired_regular_episode
                    start_year = (first_ep and first_ep.airdate and first_ep.airdate.year) or sorted_show_list[
                        i].startyear
                    if start_year:
                        sorted_show_list[i].unique_name = '%s (%s)' % (sorted_show_list[i].name, start_year)
                        dups[sorted_show_list[i].unique_name] = i

        name_cache.buildNameCache()

    @staticmethod
    def sorted_show_lists():
        def titler(x):
            return (remove_article(x), x)[not x or sickbeard.SORT_ARTICLE].lower()

        if 'custom' == sickbeard.SHOWLIST_TAGVIEW:
            sorted_show_lists = []
            for tag in sickbeard.SHOW_TAGS:
                results = filter_list(lambda _so: _so.tag == tag, sickbeard.showList)
                if results:
                    sorted_show_lists.append([tag, sorted(results, key=lambda x: titler(x.unique_name))])
            # handle orphaned shows
            if len(sickbeard.showList) != sum([len(so[1]) for so in sorted_show_lists]):
                used_ids = set()
                for so in sorted_show_lists:
                    for y in so[1]:
                        used_ids |= {y.tvid_prodid}

                showlist = dict()
                all_ids = set([cur_so.tvid_prodid for cur_so in sickbeard.showList])
                for iid in list(all_ids - used_ids):
                    show_obj = None
                    try:
                        show_obj = helpers.find_show_by_id(iid)
                    except (BaseException, Exception):
                        pass
                    if show_obj:
                        if show_obj.tag in showlist:
                            showlist[show_obj.tag] += [show_obj]
                        else:
                            showlist[show_obj.tag] = [show_obj]

                sorted_show_lists += [[key, shows] for key, shows in iteritems(showlist)]

        elif 'anime' == sickbeard.SHOWLIST_TAGVIEW:
            shows = []
            anime = []
            for cur_show_obj in sickbeard.showList:
                if cur_show_obj.is_anime:
                    anime.append(cur_show_obj)
                else:
                    shows.append(cur_show_obj)
            sorted_show_lists = [['Shows', sorted(shows, key=lambda x: titler(x.unique_name))],
                                 ['Anime', sorted(anime, key=lambda x: titler(x.unique_name))]]

        else:
            sorted_show_lists = [
                ['Show List', sorted(sickbeard.showList, key=lambda x: titler(x.unique_name))]]

        return sorted_show_lists

    @staticmethod
    def plot_details(tvid_prodid, season, episode):

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT description'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ?'
            ' AND season = ? AND episode = ?',
            TVidProdid(tvid_prodid).list + [int(season), int(episode)])
        return 'Episode not found.' if not sql_result else (sql_result[0]['description'] or '')[:250:]

    @staticmethod
    def media_stats(tvid_prodid=None):

        if None is tvid_prodid:
            shows = sickbeard.showList
        else:
            shows = [helpers.find_show_by_id(tvid_prodid)]

        response = {}
        for cur_show_obj in shows:
            if cur_show_obj and cur_show_obj.path:
                loc_size = helpers.get_size(cur_show_obj.path)
                num_files, smallest, largest, average_size = get_media_stats(cur_show_obj.path)
                response[cur_show_obj.tvid_prodid] = {'message': 'No media files'} if not num_files else \
                    {
                        'nFiles': num_files,
                        'bSmallest': smallest, 'hSmallest': helpers.human(smallest),
                        'bLargest': largest, 'hLargest': helpers.human(largest),
                        'bAverageSize': average_size, 'hAverageSize': helpers.human(average_size)
                    }

                response[cur_show_obj.tvid_prodid].update({
                    'path': cur_show_obj.path, 'bSize': loc_size, 'hSize': helpers.human(loc_size)})

        return json.dumps(response)

    @staticmethod
    def scene_exceptions(tvid_prodid, wanted_season=None):

        exceptions_list = sickbeard.scene_exceptions.get_all_scene_exceptions(tvid_prodid)
        wanted_season = helpers.try_int(wanted_season, None)
        wanted_not_found = None is not wanted_season and wanted_season not in exceptions_list
        if not exceptions_list or wanted_not_found:
            return ('No scene exceptions', 'No season exceptions')[wanted_not_found]

        out = []
        for season, names in iter(sorted(iteritems(exceptions_list))):
            if None is wanted_season or wanted_season == season:
                out.append('S%s: %s' % (('%02d' % season, '*')[-1 == season], ',<br>\n'.join(names)))
        return '\n<hr class="exception-divider">\n'.join(out)

    @staticmethod
    def switch_infosrc(prodid, tvid, m_prodid, m_tvid, set_pause=False, mark_wanted=False):
        tvid = helpers.try_int(tvid)
        prodid = helpers.try_int(prodid)
        m_tvid = helpers.try_int(m_tvid)
        m_prodid = helpers.try_int(m_prodid)
        show_obj = helpers.find_show_by_id({tvid: prodid}, no_mapped_ids=True)
        try:
            sickbeard.show_queue_scheduler.action.switch_show(show_obj=show_obj, new_tvid=m_tvid,
                                                              new_prodid=m_prodid, force_id=True,
                                                              set_pause=set_pause, mark_wanted=mark_wanted)
        except (BaseException, Exception) as e:
            logger.log('Could not add show %s to switch queue: %s' % (show_obj.tvid_prodid, ex(e)), logger.WARNING)

        ui.notifications.message('TV info source switch', 'Queued switch of tv info source')
        return {'Success': 'Switched to new TV info source'}

    def save_mapping(self, tvid_prodid, **kwargs):

        m_tvid = helpers.try_int(kwargs.get('m_tvid'))
        m_prodid = helpers.try_int(kwargs.get('m_prodid'))
        show_obj = helpers.find_show_by_id(tvid_prodid)
        response = {}
        if not show_obj:
            return json.dumps(response)
        new_ids = {}
        save_map = []
        with show_obj.lock:
            for k, v in iteritems(kwargs):
                t = re.search(r'mid-(\d+)', k)
                if t:
                    i = helpers.try_int(v, None)
                    if None is not i:
                        new_ids.setdefault(helpers.try_int(t.group(1)),
                                           {'id': 0,
                                            'status': MapStatus.NONE,
                                            'date': datetime.date.fromordinal(1)
                                            })['id'] = i
                else:
                    t = re.search(r'lockid-(\d+)', k)
                    if t:
                        new_ids.setdefault(helpers.try_int(t.group(1)), {
                            'id': 0, 'status': MapStatus.NONE,
                            'date': datetime.date.fromordinal(1)})['status'] = \
                            (MapStatus.NONE, MapStatus.NO_AUTOMATIC_CHANGE)['true' == v]
            if new_ids:
                for k, v in iteritems(new_ids):
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
            elif show_obj.tvid == m_tvid:
                ui.notifications.message('Mappings unchanged, not saving.')

        master_ids = [show_obj.prodid, helpers.try_int(kwargs.get('tvid')), m_prodid, m_tvid]
        if all([0 < x for x in master_ids]) and sickbeard.TVInfoAPI(m_tvid).config.get('active') and \
                not sickbeard.TVInfoAPI(m_tvid).config.get('defunct') and \
                not sickbeard.TVInfoAPI(m_tvid).config.get('mapped_only') and \
                (m_tvid != show_obj.tvid or m_prodid != show_obj.prodid):
            try:
                new_show_obj = helpers.find_show_by_id({m_tvid: m_prodid}, no_mapped_ids=False, check_multishow=True)
                mtvid_prodid = TVidProdid({m_tvid: m_prodid})()
                if not new_show_obj or (new_show_obj.tvid == show_obj.tvid and new_show_obj.prodid == show_obj.prodid):
                    master_ids += [bool(helpers.try_int(kwargs.get(x))) for x in ('paused', 'markwanted')]
                    response = dict(switch=self.switch_infosrc(*master_ids), mtvid_prodid=mtvid_prodid)
                else:
                    msg = 'Master ID unchanged, because show from %s with ID: %s exists in DB.' % \
                          (sickbeard.TVInfoAPI(m_tvid).name, mtvid_prodid)
                    logger.log(msg, logger.WARNING)
                    ui.notifications.message(*[s.strip() for s in msg.split(',')])
            except MultipleShowObjectsException:
                msg = 'Master ID unchanged, because show from %s with ID: %s exists in DB.' % \
                      (sickbeard.TVInfoAPI(m_tvid).name, m_prodid)
                logger.log(msg, logger.WARNING)
                ui.notifications.message(*[s.strip() for s in msg.split(',')])

        response.update({
            'map': {k: {r: w for r, w in iteritems(v) if 'date' != r} for k, v in iteritems(show_obj.ids)}
        })
        return json.dumps(response)

    @staticmethod
    def force_mapping(tvid_prodid, **kwargs):

        show_obj = helpers.find_show_by_id(tvid_prodid)
        if not show_obj:
            return json.dumps({})
        save_map = []
        with show_obj.lock:
            for k, v in iteritems(kwargs):
                t = re.search(r'lockid-(\d+)', k)
                if t:
                    new_status = (MapStatus.NONE, MapStatus.NO_AUTOMATIC_CHANGE)['true' == v]
                    old_status = show_obj.ids.get(helpers.try_int(t.group(1)), {'status': MapStatus.NONE})['status']
                    if ((MapStatus.NO_AUTOMATIC_CHANGE == new_status and
                         MapStatus.NO_AUTOMATIC_CHANGE != old_status) or
                            (MapStatus.NO_AUTOMATIC_CHANGE != new_status and
                             MapStatus.NO_AUTOMATIC_CHANGE == old_status)):
                        locked_val = helpers.try_int(t.group(1))
                        if 'mid-%s' % locked_val in kwargs:
                            mid_val = helpers.try_int(kwargs['mid-%s' % locked_val], None)
                            if None is not mid_val and 0 <= mid_val:
                                show_obj.ids.setdefault(locked_val, {
                                    'id': 0, 'status': MapStatus.NONE,
                                    'date': datetime.date.fromordinal(1)})['id'] = mid_val
                        show_obj.ids.setdefault(locked_val, {
                            'id': 0, 'status': MapStatus.NONE,
                            'date': datetime.date.fromordinal(1)})['status'] = new_status
                        save_map.append(locked_val)
            if len(save_map):
                save_mapping(show_obj, save_map=save_map)
            map_indexers_to_show(show_obj, force=True)
            ui.notifications.message('Mapping Reloaded')
        return json.dumps({k: {r: w for r, w in iteritems(v) if 'date' != r} for k, v in iteritems(show_obj.ids)})

    @staticmethod
    def fanart_tmpl(t):
        t.fanart = []
        cache_obj = image_cache.ImageCache()
        show_obj = getattr(t, 'show_obj', None) or getattr(t, 'show', None)
        for img in ek.ek(glob.glob, cache_obj.fanart_path(
                show_obj.tvid, show_obj.prodid).replace('fanart.jpg', '*')) or []:
            match = re.search(r'(\d+(?:\.(\w*?(\d*)))?\.\w{5,8})\.fanart\.', img, re.I)
            if match and match.group(1):
                t.fanart += [(match.group(1),
                              sickbeard.FANART_RATINGS.get(show_obj.tvid_prodid, {}).get(match.group(1), ''))]

        t.start_image = None
        ratings = [v for n, v in t.fanart]
        if 20 in ratings:
            t.start_image = ratings.index(20)
        else:
            rnd = [(x, v) for x, (n, v) in enumerate(t.fanart) if 30 != v]
            grouped = [n for (n, v) in rnd if 10 == v]
            if grouped:
                t.start_image = grouped[random.randint(0, len(grouped) - 1)]
            elif rnd:
                t.start_image = rnd[random.randint(0, len(rnd) - 1)][0]

        t.has_art = bool(len(t.fanart))
        t.css = ' '.join(([], ['back-art'])[sickbeard.DISPLAY_SHOW_BACKGROUND and t.has_art] +
                         ([], ['translucent'])[sickbeard.DISPLAY_SHOW_BACKGROUND_TRANSLUCENT] +
                         [{0: 'reg', 1: 'pro', 2: 'pro ii'}.get(sickbeard.DISPLAY_SHOW_VIEWMODE)])

    def edit_show(self, tvid_prodid=None, location=None,
                  any_qualities=None, best_qualities=None, exceptions_list=None,
                  flatten_folders=None, paused=None, direct_call=False, air_by_date=None, sports=None, dvdorder=None,
                  tvinfo_lang=None, subs=None, upgrade_once=None, rls_ignore_words=None,
                  rls_require_words=None, anime=None, allowlist=None, blocklist=None,
                  scene=None, prune=None, tag=None, quality_preset=None, reset_fanart=None,
                  rls_global_exclude_ignore=None, rls_global_exclude_require=None, **kwargs):

        any_qualities = any_qualities if None is not any_qualities else []
        best_qualities = best_qualities if None is not best_qualities else []
        exceptions_list = exceptions_list if None is not exceptions_list else []

        if None is tvid_prodid:
            err_string = 'Invalid show ID: ' + str(tvid_prodid)
            if direct_call:
                return [err_string]
            return self._generic_message('Error', err_string)

        show_obj = helpers.find_show_by_id(tvid_prodid)
        if not show_obj:
            err_string = 'Unable to find the specified show: %s' % tvid_prodid
            if direct_call:
                return [err_string]
            return self._generic_message('Error', err_string)

        show_obj.exceptions = scene_exceptions.get_all_scene_exceptions(tvid_prodid)

        if None is not quality_preset and int(quality_preset):
            best_qualities = []

        if not location and not any_qualities and not best_qualities and not flatten_folders:
            t = PageTemplate(web_handler=self, file='editShow.tmpl')
            t.submenu = self.home_menu()

            t.expand_ids = all([kwargs.get('tvsrc'), helpers.try_int(kwargs.get('srcid'))])
            t.tvsrc = int(kwargs.get('tvsrc', 0))
            t.srcid = helpers.try_int(kwargs.get('srcid'))

            my_db = db.DBConnection()
            # noinspection SqlRedundantOrderingDirection
            t.seasonResults = my_db.select(
                'SELECT DISTINCT season'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' ORDER BY season DESC',
                [show_obj.tvid, show_obj.prodid])

            if show_obj.is_anime:
                if not show_obj.release_groups:
                    show_obj.release_groups = AniGroupList(show_obj.tvid, show_obj.prodid, show_obj.tvid_prodid)
                t.allowlist = show_obj.release_groups.allowlist
                t.blocklist = show_obj.release_groups.blocklist

                t.groups = pull_anidb_groups(show_obj.name)
                if None is t.groups:
                    t.groups = [dict(name='Did not initialise AniDB. Check debug log if reqd.', rating='', range='')]
                elif False is t.groups:
                    t.groups = [dict(name='Fail: AniDB connect. Restart SG else check debug log', rating='', range='')]
                elif isinstance(t.groups, list) and 0 == len(t.groups):
                    t.groups = [dict(name='No groups listed in API response', rating='', range='')]

            with show_obj.lock:
                t.show_obj = show_obj
                t.show_has_scene_map = sickbeard.scene_numbering.has_xem_scene_mapping(
                    show_obj.tvid, show_obj.prodid)

            # noinspection PyTypeChecker
            self.fanart_tmpl(t)
            t.num_ratings = len(sickbeard.FANART_RATINGS.get(tvid_prodid, {}))

            t.unlock_master_id = 0 != show_obj.not_found_count
            t.showname_enc = quote_plus(show_obj.name.encode('utf-8'))

            show_message = ''

            if 0 != show_obj.not_found_count:
                # noinspection PyUnresolvedReferences
                last_found = ('', ' since %s' % SGDatetime.fromordinal(
                    show_obj.last_found_on_indexer).sbfdate())[1 < show_obj.last_found_on_indexer]
                show_message = (
                    'The master ID of this show has been <span class="addQTip" title="many reasons exist, including: '
                    + '\nshow flagged as a duplicate, removed completely... etc">abandoned</span>%s' % last_found
                    + '<br>search for a replacement in the "<b>Related show IDs</b>" section of the "<b>Other</b>" tab')

            t.show_message = show_message

            return t.respond()

        flatten_folders = config.checkbox_to_value(flatten_folders)
        dvdorder = config.checkbox_to_value(dvdorder)
        upgrade_once = config.checkbox_to_value(upgrade_once)
        paused = config.checkbox_to_value(paused)
        air_by_date = config.checkbox_to_value(air_by_date)
        scene = config.checkbox_to_value(scene)
        sports = config.checkbox_to_value(sports)
        anime = config.checkbox_to_value(anime)
        subs = config.checkbox_to_value(subs)

        if config.checkbox_to_value(reset_fanart) and sickbeard.FANART_RATINGS.get(tvid_prodid):
            del sickbeard.FANART_RATINGS[tvid_prodid]
            sickbeard.save_config()

        if tvinfo_lang and tvinfo_lang in sickbeard.TVInfoAPI(show_obj.tvid).setup().config['valid_languages']:
            infosrc_lang = tvinfo_lang
        else:
            infosrc_lang = show_obj.lang

        # if we changed the language then kick off an update
        if infosrc_lang == show_obj.lang:
            do_update = False
        else:
            do_update = True

        if scene == show_obj.scene and anime == show_obj.anime:
            do_update_scene_numbering = False
        else:
            do_update_scene_numbering = True

        if type(any_qualities) != list:
            any_qualities = [any_qualities]

        if type(best_qualities) != list:
            best_qualities = [best_qualities]

        if type(exceptions_list) != list:
            exceptions_list = [exceptions_list]

        # If direct call from mass_edit_update no scene exceptions handling or blockandallow list handling or tags
        if direct_call:
            do_update_exceptions = False
        else:
            do_update_exceptions = True  # TODO: make this smarter and only update on changes

            with show_obj.lock:
                if anime:
                    if not show_obj.release_groups:
                        show_obj.release_groups = AniGroupList(
                            show_obj.tvid, show_obj.prodid, show_obj.tvid_prodid)
                    if allowlist:
                        shortallowlist = short_group_names(allowlist)
                        show_obj.release_groups.set_allow_keywords(shortallowlist)
                    else:
                        show_obj.release_groups.set_allow_keywords([])

                    if blocklist:
                        shortblocklist = short_group_names(blocklist)
                        show_obj.release_groups.set_block_keywords(shortblocklist)
                    else:
                        show_obj.release_groups.set_block_keywords([])

        errors = []
        with show_obj.lock:
            show_obj.quality = Quality.combineQualities(map_list(int, any_qualities), map_list(int, best_qualities))
            show_obj.upgrade_once = upgrade_once

            # reversed for now
            if bool(show_obj.flatten_folders) != bool(flatten_folders):
                show_obj.flatten_folders = flatten_folders
                try:
                    sickbeard.show_queue_scheduler.action.refreshShow(show_obj)
                except exceptions_helper.CantRefreshException as e:
                    errors.append('Unable to refresh this show: ' + ex(e))

            if bool(anime) != show_obj.is_anime:
                sickbeard.name_parser.parser.name_parser_cache.flush(show_obj)

            show_obj.paused = paused
            show_obj.scene = scene
            show_obj.anime = anime
            show_obj.sports = sports
            show_obj.subtitles = subs
            show_obj.air_by_date = air_by_date
            show_obj.tag = tag
            show_obj.prune = config.minimax(prune, 0, 0, 9999)

            if not direct_call:
                show_obj.lang = infosrc_lang
                show_obj.dvdorder = dvdorder
                new_ignore_words, new_i_regex = helpers.split_word_str(rls_ignore_words.strip())
                new_ignore_words -= sickbeard.IGNORE_WORDS
                if 0 == len(new_ignore_words):
                    new_i_regex = False
                show_obj.rls_ignore_words, show_obj.rls_ignore_words_regex = new_ignore_words, new_i_regex
                new_require_words, new_r_regex = helpers.split_word_str(rls_require_words.strip())
                new_require_words -= sickbeard.REQUIRE_WORDS
                if 0 == len(new_require_words):
                    new_r_regex = False
                show_obj.rls_require_words, show_obj.rls_require_words_regex = new_require_words, new_r_regex
                if isinstance(rls_global_exclude_ignore, list):
                    show_obj.rls_global_exclude_ignore = set(r for r in rls_global_exclude_ignore if '.*' != r)
                elif isinstance(rls_global_exclude_ignore, string_types) and '.*' != rls_global_exclude_ignore:
                    show_obj.rls_global_exclude_ignore = {rls_global_exclude_ignore}
                else:
                    show_obj.rls_global_exclude_ignore = set()
                if isinstance(rls_global_exclude_require, list):
                    show_obj.rls_global_exclude_require = set(r for r in rls_global_exclude_require if '.*' != r)
                elif isinstance(rls_global_exclude_require, string_types) and '.*' != rls_global_exclude_require:
                    show_obj.rls_global_exclude_require = {rls_global_exclude_require}
                else:
                    show_obj.rls_global_exclude_require = set()
                clean_ignore_require_words()

            # if we change location clear the db of episodes, change it, write to db, and rescan
            # noinspection PyProtectedMember
            old_path = ek.ek(os.path.normpath, show_obj._location)
            new_path = ek.ek(os.path.normpath, location)
            if old_path != new_path:
                logger.log(u'%s != %s' % (old_path, new_path), logger.DEBUG)
                if not ek.ek(os.path.isdir, new_path) and not sickbeard.CREATE_MISSING_SHOW_DIRS:
                    errors.append(u'New location <tt>%s</tt> does not exist' % new_path)

                # don't bother if we're going to update anyway
                elif not do_update:
                    # change it
                    try:
                        show_obj.location = new_path
                        try:
                            sickbeard.show_queue_scheduler.action.refreshShow(show_obj)
                        except exceptions_helper.CantRefreshException as e:
                            errors.append('Unable to refresh this show:' + ex(e))
                            # grab updated info from TVDB
                            # show_obj.load_episodes_from_tvinfo()
                            # rescan the episodes in the new folder
                    except exceptions_helper.NoNFOException:
                        errors.append(
                            u"The folder at <tt>%s</tt> doesn't contain a tvshow.nfo - "
                            u"copy your files to that folder before you change the directory in SickGear." % new_path)

            # save it to the DB
            show_obj.save_to_db()

        # force the update
        if do_update:
            try:
                sickbeard.show_queue_scheduler.action.updateShow(show_obj, True)
                helpers.cpu_sleep()
            except exceptions_helper.CantUpdateException:
                errors.append('Unable to force an update on the show.')

        if do_update_exceptions:
            try:
                scene_exceptions.update_scene_exceptions(show_obj.tvid, show_obj.prodid, exceptions_list)
                helpers.cpu_sleep()
            except exceptions_helper.CantUpdateException:
                errors.append('Unable to force an update on scene exceptions of the show.')

        if do_update_scene_numbering:
            try:
                sickbeard.scene_numbering.xem_refresh(show_obj.tvid, show_obj.prodid)
                helpers.cpu_sleep()
            except exceptions_helper.CantUpdateException:
                errors.append('Unable to force an update on scene numbering of the show.')

        if direct_call:
            return errors

        if 0 < len(errors):
            ui.notifications.error('%d error%s while saving changes:' % (len(errors), '' if 1 == len(errors) else 's'),
                                   '<ul>' + '\n'.join(['<li>%s</li>' % error for error in errors]) + '</ul>')

        self.redirect('/home/view-show?tvid_prodid=%s' % tvid_prodid)

    def delete_show(self, tvid_prodid=None, full=0):

        if None is tvid_prodid:
            return self._generic_message('Error', 'Invalid show ID')

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            return self._generic_message('Error', 'Unable to find the specified show')

        if sickbeard.show_queue_scheduler.action.isBeingAdded(
                show_obj) or sickbeard.show_queue_scheduler.action.isBeingUpdated(show_obj):
            return self._generic_message("Error", "Shows can't be deleted while they're being added or updated.")

        # if sickbeard.USE_TRAKT and sickbeard.TRAKT_SYNC:
        #     # remove show from trakt.tv library
        #     sickbeard.trakt_checker_scheduler.action.removeShowFromTraktLibrary(show_obj)

        show_obj.delete_show(bool(full))

        ui.notifications.message('%s with %s' % (('Deleting', 'Trashing')[sickbeard.TRASH_REMOVE_SHOW],
                                                 ('media left untouched', 'all related media')[bool(full)]),
                                 '<b>%s</b>' % show_obj.unique_name)
        self.redirect('/home/')

    def update_cast(self, tvid_prodid=None):
        if None is tvid_prodid:
            return self._generic_message('Error', 'Invalid show ID')

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            return self._generic_message('Error', 'Unable to find the specified show')

        # force the update from the DB
        try:
            sickbeard.people_queue_scheduler.action.add_cast_update(show_obj=show_obj, show_info_cast=None)
        except (BaseException, Exception) as e:
            ui.notifications.error('Unable to refresh this show.', ex(e))

        helpers.cpu_sleep()

        self.redirect('/home/view-show?tvid_prodid=%s' % show_obj.tvid_prodid)

    def refresh_show(self, tvid_prodid=None):

        if None is tvid_prodid:
            return self._generic_message('Error', 'Invalid show ID')

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            return self._generic_message('Error', 'Unable to find the specified show')

        # force the update from the DB
        try:
            sickbeard.show_queue_scheduler.action.refreshShow(show_obj)
        except exceptions_helper.CantRefreshException as e:
            ui.notifications.error('Unable to refresh this show.', ex(e))

        helpers.cpu_sleep()

        self.redirect('/home/view-show?tvid_prodid=%s' % show_obj.tvid_prodid)

    def update_show(self, tvid_prodid=None, force=0, web=0):

        if None is tvid_prodid:
            return self._generic_message('Error', 'Invalid show ID')

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            return self._generic_message('Error', 'Unable to find the specified show')

        # force the update
        try:
            sickbeard.show_queue_scheduler.action.updateShow(show_obj, bool(force), bool(web))
        except exceptions_helper.CantUpdateException as e:
            ui.notifications.error('Unable to update this show.',
                                   ex(e))

        helpers.cpu_sleep()

        self.redirect('/home/view-show?tvid_prodid=%s' % show_obj.tvid_prodid)

    def subtitle_show(self, tvid_prodid=None, force=0):

        if None is tvid_prodid:
            return self._generic_message('Error', 'Invalid show ID')

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            return self._generic_message('Error', 'Unable to find the specified show')

        # search and download subtitles
        if sickbeard.USE_SUBTITLES:
            sickbeard.show_queue_scheduler.action.download_subtitles(show_obj)

            helpers.cpu_sleep()

        self.redirect('/home/view-show?tvid_prodid=%s' % show_obj.tvid_prodid)

    def update_mb(self, tvid_prodid=None, **kwargs):

        if notifiers.NotifierFactory().get('EMBY').update_library(
                helpers.find_show_by_id(tvid_prodid), force=True):
            ui.notifications.message('Library update command sent to Emby host(s): ' + sickbeard.EMBY_HOST)
        else:
            ui.notifications.error('Unable to contact one or more Emby host(s): ' + sickbeard.EMBY_HOST)
        self.redirect('/home/')

    def update_kodi(self, show_name=None):

        # only send update to first host in the list -- workaround for kodi sql backend users
        if sickbeard.KODI_UPDATE_ONLYFIRST:
            # only send update to first host in the list -- workaround for kodi sql backend users
            host = sickbeard.KODI_HOST.split(',')[0].strip()
        else:
            host = sickbeard.KODI_HOST

        if notifiers.NotifierFactory().get('KODI').update_library(show_name=show_name):
            ui.notifications.message('Library update command sent to Kodi host(s): ' + host)
        else:
            ui.notifications.error('Unable to contact one or more Kodi host(s): ' + host)
        self.redirect('/home/')

    def update_plex(self):
        result = notifiers.NotifierFactory().get('PLEX').update_library()
        if 'Fail' not in result:
            ui.notifications.message(
                'Library update command sent to',
                'Plex Media Server host(s): ' + sickbeard.PLEX_SERVER_HOST.replace(',', ', '))
        else:
            ui.notifications.error('Unable to contact', 'Plex Media Server host(s): ' + result)
        self.redirect('/home/')

    def set_show_status(self, tvid_prodid=None, eps=None, status=None, direct=False):

        if None is tvid_prodid or None is eps or None is status:
            err_msg = 'You must specify a show and at least one episode'
            if direct:
                ui.notifications.error('Error', err_msg)
                return json.dumps({'result': 'error'})
            return self._generic_message('Error', err_msg)

        use_default = False
        if isinstance(status, string_types) and '-' in status:
            use_default = True
            status = status.replace('-', '')
        status = int(status)

        if status not in statusStrings:
            err_msg = 'Invalid status'
            if direct:
                ui.notifications.error('Error', err_msg)
                return json.dumps({'result': 'error'})
            return self._generic_message('Error', err_msg)

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            err_msg = 'Error', 'Show not in show list'
            if direct:
                ui.notifications.error('Error', err_msg)
                return json.dumps({'result': 'error'})
            return self._generic_message('Error', err_msg)

        min_initial = min(Quality.splitQuality(show_obj.quality)[0])
        segments = {}
        if None is not eps:

            sql_l = []
            for cur_ep in eps.split('|'):

                logger.log(u'Attempting to set status on episode %s to %s' % (cur_ep, status), logger.DEBUG)

                ep_obj = show_obj.get_episode(*tuple([int(x) for x in cur_ep.split('x')]))

                if None is ep_obj:
                    return self._generic_message('Error', 'Episode couldn\'t be retrieved')

                if status in [WANTED, FAILED]:
                    # figure out what episodes are wanted so we can backlog them
                    if ep_obj.season in segments:
                        segments[ep_obj.season].append(ep_obj)
                    else:
                        segments[ep_obj.season] = [ep_obj]

                with ep_obj.lock:
                    required = Quality.SNATCHED_ANY + Quality.DOWNLOADED
                    err_msg = ''
                    # don't let them mess up UNAIRED episodes
                    if UNAIRED == ep_obj.status:
                        err_msg = 'because it is unaired'

                    elif FAILED == status and ep_obj.status not in required:
                        err_msg = 'to failed because it\'s not snatched/downloaded'

                    elif status in Quality.DOWNLOADED \
                            and ep_obj.status not in required + Quality.ARCHIVED + [IGNORED, SKIPPED] \
                            and not ek.ek(os.path.isfile, ep_obj.location):
                        err_msg = 'to downloaded because it\'s not snatched/downloaded/archived'

                    if err_msg:
                        logger.log('Refusing to change status of %s %s' % (cur_ep, err_msg), logger.ERROR)
                        continue

                    if ARCHIVED == status:
                        if ep_obj.status in Quality.DOWNLOADED or direct:
                            ep_obj.status = Quality.compositeStatus(
                                ARCHIVED, (Quality.splitCompositeStatus(ep_obj.status)[1], min_initial)[use_default])
                    elif DOWNLOADED == status:
                        if ep_obj.status in Quality.ARCHIVED:
                            ep_obj.status = Quality.compositeStatus(
                                DOWNLOADED, Quality.splitCompositeStatus(ep_obj.status)[1])
                    else:
                        ep_obj.status = status

                    # mass add to database
                    result = ep_obj.get_sql()
                    if None is not result:
                        sql_l.append(result)

            if 0 < len(sql_l):
                my_db = db.DBConnection()
                my_db.mass_action(sql_l)

        if WANTED == status:
            season_list = ''
            season_wanted = []
            if sickbeard.search_backlog.BacklogSearcher.providers_active(scheduled=False):
                for season, segment in iteritems(segments):  # type: int, List[sickbeard.tv.TVEpisode]
                    if not show_obj.paused:
                        cur_backlog_queue_item = search_queue.BacklogQueueItem(show_obj, segment)
                        sickbeard.search_queue_scheduler.action.add_item(cur_backlog_queue_item)

                    if season not in season_wanted:
                        season_wanted += [season]
                        season_list += u'<li>Season %s</li>' % season
                        logger.log((u'Not adding wanted eps to backlog search for %s season %s because show is paused',
                                    u'Starting backlog search for %s season %s because eps were set to wanted')[
                                       not show_obj.paused] % (show_obj.unique_name, season))

                (title, msg) = (('Not starting backlog', u'Paused show prevented backlog search'),
                                ('Backlog started', u'Backlog search started'))[not show_obj.paused]

                if segments:
                    ui.notifications.message(title,
                                             u'%s for the following seasons of <b>%s</b>:<br /><ul>%s</ul>'
                                             % (msg, show_obj.unique_name, season_list))
            else:
                ui.notifications.message('Not starting backlog', 'No provider has active searching enabled')

        elif FAILED == status:
            msg = u'Retrying search automatically for the following season of <b>%s</b>:<br><ul>' % show_obj.unique_name

            for season, segment in iteritems(segments):  # type: int, List[sickbeard.tv.TVEpisode]
                cur_failed_queue_item = search_queue.FailedQueueItem(show_obj, segment)
                sickbeard.search_queue_scheduler.action.add_item(cur_failed_queue_item)

                msg += '<li>Season %s</li>' % season
                logger.log(u'Retrying search for %s season %s because some eps were set to failed' %
                           (show_obj.unique_name, season))

            msg += '</ul>'

            if segments:
                ui.notifications.message('Retry search started', msg)

        if direct:
            return json.dumps({'result': 'success'})
        self.redirect('/home/view-show?tvid_prodid=%s' % tvid_prodid)

    def rename_media(self, tvid_prodid=None):

        if None is tvid_prodid:
            return self._generic_message('Error', 'You must specify a show')

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            return self._generic_message('Error', 'Show not in show list')

        try:
            _ = show_obj.location
        except exceptions_helper.ShowDirNotFoundException:
            return self._generic_message('Error', "Can't rename episodes when the show dir is missing.")

        ep_obj_rename_list = []

        ep_obj_list = show_obj.get_all_episodes(has_location=True)

        for cur_ep_obj in ep_obj_list:
            # Only want to rename if we have a location
            if cur_ep_obj.location:
                if cur_ep_obj.related_ep_obj:
                    # do we have one of multi-episodes in the rename list already
                    for _cur_ep_obj in cur_ep_obj.related_ep_obj + [cur_ep_obj]:
                        if _cur_ep_obj in ep_obj_rename_list:
                            break
                        ep_status, ep_qual = Quality.splitCompositeStatus(_cur_ep_obj.status)
                        if not ep_qual:
                            continue
                        ep_obj_rename_list.append(cur_ep_obj)
                else:
                    ep_status, ep_qual = Quality.splitCompositeStatus(cur_ep_obj.status)
                    if not ep_qual:
                        continue
                    ep_obj_rename_list.append(cur_ep_obj)

        if ep_obj_rename_list:
            # present season DESC episode DESC on screen
            ep_obj_rename_list.reverse()

        t = PageTemplate(web_handler=self, file='testRename.tmpl')
        t.submenu = [{'title': 'Edit', 'path': 'home/edit-show?tvid_prodid=%s' % show_obj.tvid_prodid}]
        t.ep_obj_list = ep_obj_rename_list
        t.show_obj = show_obj

        # noinspection PyTypeChecker
        self.fanart_tmpl(t)

        return t.respond()

    def do_rename(self, tvid_prodid=None, eps=None):

        if None is tvid_prodid or None is eps:
            err_msg = 'You must specify a show and at least one episode'
            return self._generic_message('Error', err_msg)

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if None is show_obj:
            err_msg = 'Error', 'Show not in show list'
            return self._generic_message('Error', err_msg)

        try:
            _ = show_obj.location
        except exceptions_helper.ShowDirNotFoundException:
            return self._generic_message('Error', "Can't rename episodes when the show dir is missing.")

        if None is eps:
            return self.redirect('/home/view-show?tvid_prodid=%s' % tvid_prodid)

        my_db = db.DBConnection()
        tvid_prodid_obj = TVidProdid(tvid_prodid)
        for cur_ep in eps.split('|'):

            ep_info = cur_ep.split('x')

            # noinspection SqlConstantCondition
            sql_result = my_db.select(
                'SELECT * FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' AND season = ? AND episode = ? AND 5=5',
                tvid_prodid_obj.list
                + [ep_info[0], ep_info[1]])
            if not sql_result:
                logger.log(u'Unable to find an episode for ' + cur_ep + ', skipping', logger.WARNING)
                continue
            related_ep_result = my_db.select('SELECT * FROM tv_episodes WHERE location = ? AND episode != ?',
                                             [sql_result[0]['location'], ep_info[1]])

            root_ep_obj = show_obj.get_episode(int(ep_info[0]), int(ep_info[1]))
            root_ep_obj.related_ep_obj = []

            for cur_ep_result in related_ep_result:
                ep_obj = show_obj.get_episode(int(cur_ep_result['season']), int(cur_ep_result['episode']))
                if ep_obj not in root_ep_obj.related_ep_obj:
                    root_ep_obj.related_ep_obj.append(ep_obj)

            root_ep_obj.rename()

        self.redirect('/home/view-show?tvid_prodid=%s' % tvid_prodid)

    def search_episode(self, tvid_prodid=None, season=None, episode=None, retry=False, **kwargs):

        result = dict(result='failure')

        # retrieve the episode object and fail if we can't get one
        ep_obj = self._get_episode(tvid_prodid, season, episode)
        if not isinstance(ep_obj, str):
            if UNKNOWN == Quality.splitCompositeStatus(ep_obj.status)[0]:
                ep_obj.status = SKIPPED

            # make a queue item for the TVEpisode and put it on the queue
            ep_queue_item = (search_queue.ManualSearchQueueItem(ep_obj.show_obj, ep_obj),
                             search_queue.FailedQueueItem(ep_obj.show_obj, [ep_obj]))[retry]

            sickbeard.search_queue_scheduler.action.add_item(ep_queue_item)

            if None is ep_queue_item.success:  # invocation
                result.update(dict(result=('success', 'queuing')[not ep_queue_item.started]))
            # elif ep_queue_item.success:
            #    return self.search_q_status(
            #        '%s%s%s' % (ep_obj.show_obj.tvid, TVidProdid.glue, ep_obj.show_obj.prodid))  # page refresh

        return json.dumps(result)

    def episode_retry(self, tvid_prodid, season, episode):

        return self.search_episode(tvid_prodid, season, episode, True)

    # Return progress for queued, active and finished episodes
    def search_q_status(self, tvid_prodid=None, **kwargs):

        ep_data_list = []
        seen_eps = set([])

        # Queued searches
        queued = sickbeard.search_queue_scheduler.action.get_queued_manual(tvid_prodid)

        # Active search
        active = sickbeard.search_queue_scheduler.action.get_current_manual_item(tvid_prodid)

        # Finished searches
        sickbeard.search_queue.remove_old_fifo(sickbeard.search_queue.MANUAL_SEARCH_HISTORY)
        results = sickbeard.search_queue.MANUAL_SEARCH_HISTORY

        for item in filter_iter(lambda q: hasattr(q, 'segment_ns'), queued):
            for ep_ns in item.segment_ns:
                ep_data, uniq_sxe = self.prepare_episode(ep_ns, 'queued')
                ep_data_list.append(ep_data)
                seen_eps.add(uniq_sxe)

        if active and hasattr(active, 'segment_ns'):
            episode_params = dict(([('searchstate', 'finished'), ('statusoverview', True)],
                                   [('searchstate', 'searching'), ('statusoverview', False)])[None is active.success],
                                  retrystate=True)
            for ep_ns in active.segment_ns:
                ep_data, uniq_sxe = self.prepare_episode(ep_ns, **episode_params)
                ep_data_list.append(ep_data)
                seen_eps.add(uniq_sxe)

        episode_params = dict(searchstate='finished', retrystate=True, statusoverview=True)
        for item in filter_iter(lambda r: hasattr(r, 'segment_ns') and (
                not tvid_prodid or tvid_prodid == str(r.show_ns.tvid_prodid)), results):
            for ep_ns in filter_iter(
                    lambda e: (e.show_ns.tvid, e.show_ns.prodid, e.season, e.episode) not in seen_eps, item.segment_ns):
                ep_obj = getattr(ep_ns, 'ep_obj', None)
                if not ep_obj:
                    continue
                # try:
                #     show_obj = helpers.find_show_by_id(dict({ep_ns.show_ns.tvid: ep_ns.show_ns.prodid}))
                #     ep_obj = show_obj.get_episode(season=ep_ns.season, episode=ep_ns.episode)
                # except (BaseException, Exception):
                #     continue
                ep_data, uniq_sxe = self.prepare_episode(ep_obj, **episode_params)
                ep_data_list.append(ep_data)
                seen_eps.add(uniq_sxe)

            for snatched in filter_iter(lambda s: ((s.tvid, s.prodid, s.season, s.episode) not in seen_eps),
                                        item.snatched_eps):
                ep_obj = getattr(snatched, 'ep_obj', None)
                if not ep_obj:
                    continue
                # try:
                #     show_obj = helpers.find_show_by_id(snatched[0])
                #     ep_obj = show_obj.get_episode(season=snatched[1], episode=snatched[2])
                # except (BaseException, Exception):
                #     continue
                ep_data, uniq_sxe = self.prepare_episode(ep_obj, **episode_params)
                ep_data_list.append(ep_data)
                seen_eps.add(uniq_sxe)

        return json.dumps(dict(episodes=ep_data_list))

    @staticmethod
    def prepare_episode(ep_type, searchstate, retrystate=False, statusoverview=False):
        """
        Prepare episode data and its unique id

        :param ep_type: Episode structure containing the show that it relates to
        :type ep_type: sickbeard.tv.TVEpisode object or Episode Base Namespace
        :param searchstate: Progress of search
        :type searchstate: string
        :param retrystate: True to add retrystate to data
        :type retrystate: bool
        :param statusoverview: True to add statusoverview to data
        :type statusoverview: bool
        :return: Episode data and its unique episode id
        :rtype: tuple containing a dict and a tuple
        """
        # Find the quality class for the episode
        quality_class = Quality.qualityStrings[Quality.UNKNOWN]
        ep_status, ep_quality = Quality.splitCompositeStatus(ep_type.status)
        for x in (SD, HD720p, HD1080p, UHD2160p):
            if ep_quality in Quality.splitQuality(x)[0]:
                quality_class = qualityPresetStrings[x]
                break

        # show_item: ep_type.show_ns or ep_type.show_obj
        show_item = getattr(ep_type, 'show_%s' % ('ns', 'obj')[isinstance(ep_type, sickbeard.tv.TVEpisode)])

        ep_data = dict(showindexer=show_item.tvid, showindexid=show_item.prodid,
                       season=ep_type.season, episode=ep_type.episode, quality=quality_class,
                       searchstate=searchstate, status=statusStrings[ep_type.status])
        if retrystate:
            retry_statuses = SNATCHED_ANY + [DOWNLOADED, ARCHIVED]
            ep_data.update(dict(retrystate=sickbeard.USE_FAILED_DOWNLOADS and ep_status in retry_statuses))
        if statusoverview:
            ep_data.update(dict(statusoverview=Overview.overviewStrings[
                helpers.get_overview(ep_type.status, show_item.quality, show_item.upgrade_once)]))

        return ep_data, (show_item.tvid, show_item.prodid, ep_type.season, ep_type.episode)

    def search_episode_subtitles(self, tvid_prodid=None, season=None, episode=None):

        if not sickbeard.USE_SUBTITLES:
            return json.dumps({'result': 'failure'})

        # retrieve the episode object and fail if we can't get one
        ep_obj = self._get_episode(tvid_prodid, season, episode)
        if isinstance(ep_obj, str):
            return json.dumps({'result': 'failure'})

        # try do download subtitles for that episode
        try:
            previous_subtitles = set([subliminal.language.Language(x) for x in ep_obj.subtitles])
            ep_obj.subtitles = set([x.language for x in next(itervalues(ep_obj.download_subtitles()))])
        except (BaseException, Exception):
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
        return json.dumps({'result': status,
                           'subtitles': ','.join(sorted([x.alpha2 for x in
                                                         ep_obj.subtitles.union(previous_subtitles)]))})

    @staticmethod
    def set_scene_numbering(tvid_prodid=None, for_season=None, for_episode=None, for_absolute=None,
                            scene_season=None, scene_episode=None, scene_absolute=None):
        # TODO: ui does not currently send for_absolute
        tvid, prodid = TVidProdid(tvid_prodid).list
        result = set_scene_numbering_helper(tvid, prodid, for_season, for_episode, for_absolute, scene_season,
                                            scene_episode, scene_absolute)

        return json.dumps(result)

    @staticmethod
    def fetch_releasegroups(show_name):

        result = pull_anidb_groups(show_name)
        if None is result:
            result = dict(result='fail', resp='init')
        elif False is result:
            result = dict(result='fail', resp='connect')
        elif isinstance(result, list) and 0 == len(result):
            result = dict(result='success',
                          groups=[dict(name='No groups fetched in API response', rating='', range='')])
        else:
            result = dict(result='success', groups=result)
        return json.dumps(result)

    @staticmethod
    def csv_items(text):
        # type: (AnyStr) -> AnyStr
        """Return a text list of items seperated by comma instead of '/' """

        return re.sub(r'\b\s?/\s?\b', ', ', text)

    def role(self, rid, tvid_prodid, **kwargs):
        _ = kwargs.get('oid')  # suppress pyc non used var highlight, oid (original id) is a visual ui key
        t = PageTemplate(web_handler=self, file='cast_role.tmpl')

        character_id = usable_id(rid)
        if not character_id:
            return self._generic_message('Error', 'Invalid character ID')

        try:
            t.show_obj = helpers.find_show_by_id(tvid_prodid)
        except (BaseException, Exception):
            return

        # after this point, only use character.id
        character = TVCharacter(sid=character_id, show_obj=t.show_obj)
        if not character:
            return self._generic_message('Error', 'character ID not found')

        t.character = character
        t.roles = []

        # this basic relate logic uses the link from a character to a person to find the same character name being known
        # across multiple shows. The character name is more likely to be static compared to an actor name.
        # A hardcoded exclusion may be needed if used actor plays a same named character in an _unrelated_ universe,
        # but the chance of this is negligible, therefore, it's worth it to give this a try than not to :)
        known = {}
        main_role_known = False
        rc_clean = re.compile(r'[^a-z0-9]')
        char_name = rc_clean.sub('', character.name.lower())
        for cur_person in (character.person or []):
            person, roles, msg = self.cast(cur_person.id)
            if not msg:
                for cur_role in roles:
                    if known.get(person.id, {}).get(cur_role['character_id']) == cur_role['show_obj'].tvid_prodid:
                        continue
                    # 1 person plays 1-n roles across 1-n shows
                    known.setdefault(person.id, {}).setdefault(
                        cur_role['character_id'], cur_role['show_obj'].tvid_prodid)

                    # mark names that are a subset as the same character
                    # case1 Detective Lt. Louie Provenza became Louie Provenza
                    # case2 Commander Russell Taylor became Commander Taylor
                    # case3 Micheal Tao became Mike Tao (surname is static except for women post marriage)
                    lower_name = cur_role['character_name'].lower()
                    name_parts = lower_name.split()

                    is_main = character.id == cur_role['character_id'] \
                        and character.show_obj.tvid_prodid == cur_role['show_obj'].tvid_prodid

                    # exclusion exceptions, ignoring main role
                    if not is_main and any([
                        # 1 person playing multiple same role surname but each are distinct characters
                        rc_clean.sub('', lower_name).endswith('griffin')
                    ]):
                        continue

                    if any([
                        char_name in rc_clean.sub('', lower_name),
                        char_name in ('', '%s%s' % (name_parts[0], name_parts[-1]))[2 < len(name_parts)],
                        # case3 surname only, provided more than one name part exist
                        (False, name_parts[-1] in char_name)[1 < len(name_parts)],
                        # inclusion exceptions
                        re.search('(?i)^(?:Host|Presenter)[0-9]*$', char_name),
                        re.search('(?i)^(?:Host|Prese)', lower_name) and re.search('(?i)JeremyClarkson', char_name),
                        re.search('(?i)(?:AnnaBaker|BelleStone)', char_name),
                        re.search('(?i)(?:JimmyMcgill|SaulGoodman)', char_name)
                    ]):

                        t.roles.append({
                            'character_name': cur_role['character_name'],
                            'character_id': cur_role['character_id'],
                            'character_rid': cur_role['character_rid'],
                            'show_obj': cur_role['show_obj'],
                            'person_name': person.name,
                            'person_id': person.id
                        })

                        # ensure main role is first
                        if not main_role_known and is_main:
                            main_role_known = True
                            t.roles.insert(0, t.roles.pop(-1))

        return t.respond()

    def cast(self, rid):
        person = roles = None
        msg = None

        person_id = usable_id(rid)
        if person_id:
            person = TVPerson(sid=person_id)
            if person:
                my_db = db.DBConnection()
                sql_result = my_db.select(
                    """
                    SELECT DISTINCT characters.id AS id, name, indexer, indexer_id, 
                    cpy.start_year AS start_year, cpy.end_year AS end_year, 
                    c.indexer AS c_tvid, c.indexer_id AS c_prodid,
                    (SELECT group_concat(character_ids.src || ':' || character_ids.src_id, ';;;')
                    FROM character_ids WHERE character_ids.character_id = characters.id) as c_ids
                    FROM characters
                    LEFT JOIN castlist c ON characters.id = c.character_id
                    LEFT JOIN character_person_map cpm ON characters.id = cpm.character_id
                    LEFT JOIN character_person_years cpy ON characters.id = cpy.character_id
                    AND cpy.person_id = ?
                    WHERE cpm.person_id = ?
                    """, [person.id, person.id])

                pref = [TVINFO_IMDB, TVINFO_TVMAZE, TVINFO_TMDB, TVINFO_TRAKT]
                roles = []
                for cur_char in sql_result or []:
                    ref_id = None
                    pri = 9999
                    for cur_ref_id in (cur_char['c_ids'] and cur_char['c_ids'].split(';;;')) or []:
                        k, v = [helpers.try_int(_v, None) for _v in cur_ref_id.split(':')]
                        if None is not k and None is not v:
                            if k in pref:
                                test_pri = pref.index(k)
                                if test_pri < pri:
                                    pri = test_pri
                                    ref_id = cur_ref_id

                    roles.append({
                        'character_name': self.csv_items(cur_char['name']),
                        'character_id': cur_char['id'],
                        'character_rid': ref_id,
                        'show_obj': helpers.find_show_by_id({cur_char['c_tvid']: cur_char['c_prodid']}),
                        'start_year': cur_char['start_year'], 'end_year': cur_char['end_year']
                    })
            else:
                msg = 'Person ID not found'
        else:
            msg = 'Invalid person ID'

        return person, roles, msg

    def person(self, rid, **kwargs):
        _ = kwargs.get('oid')  # suppress pyc non used var highlight, oid (original id) is a visual ui key
        t = PageTemplate(web_handler=self, file='cast_person.tmpl')
        person, roles, msg = self.cast(rid)
        if msg:
            return self._generic_message('Error', msg)

        t.person = person
        t.roles = roles

        return t.respond()

    @staticmethod
    def _convert_person_data(person_dict):
        event = {}

        for cur_date_kind in ('birthdate', 'deathdate'):
            if person_dict[cur_date_kind]:
                try:
                    doe = datetime.date.fromordinal(person_dict[cur_date_kind])
                    event[cur_date_kind] = doe
                    person_dict[cur_date_kind] = doe.strftime('%Y-%m-%d')
                    person_dict['%s_user' % cur_date_kind] = SGDatetime.sbfdate(doe)
                except (BaseException, Exception):
                    pass

        person_dict['age'] = sg_helpers.calc_age(event['birthdate'], event['deathdate'])

    def _select_person_by_date(self, date_str, date_kind):
        # type: (AnyStr, AnyStr) -> List[Dict]

        if date_kind not in ('birthdate', 'deathdate'):
            return []

        try:
            dt = dateutil.parser.parse(date_str).date()
        except (BaseException, Exception):
            raise Exception('invalid date')

        possible_dates = []
        for cur_year in moves.xrange((1850, 1920)['deathdate' == date_kind], datetime.date.today().year + 1):
            try:
                possible_dates.append(datetime.date(year=cur_year, month=dt.month, day=dt.day).toordinal())
                if 2 == dt.month and 28 == dt.day:
                    try:
                        datetime.date(year=dt.year, month=dt.month, day=29)
                    except (BaseException, Exception):
                        possible_dates.append(datetime.date(year=cur_year, month=dt.month, day=29).toordinal())
            except (BaseException, Exception):
                pass

        my_db = db.DBConnection(row_type='dict')
        sql_result = my_db.select(
            """
            SELECT * FROM persons
            WHERE %s IN (%s)
            """ % (date_kind, ','.join(['?'] * len(possible_dates))), possible_dates)
        for cur_person in sql_result:
            self._convert_person_data(cur_person)

        return sql_result

    def get_persons(self, names=None, **kwargs):
        # type: (AnyStr, dict) -> AnyStr
        """
        :param names:
        :param kwargs: optional `birthday`, optional `deathday`
        :return:
        """
        results = {}
        for cur_date_kind in ('birthdate', 'deathdate'):
            date_arg = kwargs.get(cur_date_kind)
            if date_arg:
                try:
                    results[cur_date_kind] = self._select_person_by_date(date_arg, cur_date_kind)
                except (BaseException, Exception) as e:
                    return json.dumps({'result': 'error', 'error': ex(e)})

        names = names and names.split('|')
        if names:
            my_db = db.DBConnection(row_type='dict')
            sql_result = my_db.select(
                """
                SELECT * FROM persons
                WHERE name IN (%s)
                """ % ','.join(['?'] * len(names)), names)
            for cur_person in sql_result:
                self._convert_person_data(cur_person)
            results['names'] = sql_result

        return json.dumps({'result': 'success', 'person_list': results})

    def get_switch_changed(self):
        t = PageTemplate(web_handler=self, file='switch_show_result.tmpl')
        t.show_list = {}
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT DISTINCT new_indexer, new_indexer_id, COUNT(reason) AS count, reason
            FROM switch_ep_result
            GROUP BY new_indexer, new_indexer_id, reason
            """)
        for cur_show in sql_result:
            try:
                show_obj = helpers.find_show_by_id({cur_show['new_indexer']: cur_show['new_indexer_id']})
            except (BaseException, Exception):
                # todo: what to do with unknown entries
                continue
            if not show_obj:
                continue
            t.show_list.setdefault(show_obj, {}).update(
                {('changed', 'deleted')[TVSWITCH_EP_DELETED == cur_show['reason']]: cur_show['count']})

        return t.respond()

    def get_switch_changed_episodes(self, tvid_prodid):
        t = PageTemplate(web_handler=self, file='switch_episode_result.tmpl')
        try:
            show_obj = helpers.find_show_by_id(tvid_prodid)
        except (BaseException, Exception):
            # todo: what to do with unknown entries
            show_obj = None
        if not show_obj:
            return self.page_not_found()

        t.show_obj = show_obj
        t.ep_list = []
        my_db = db.DBConnection()
        sql_result = my_db.select(
            """
            SELECT * FROM switch_ep_result
            WHERE new_indexer = ? AND new_indexer_id = ?
            ORDER BY season, episode
            """, TVidProdid(tvid_prodid).list)
        for cur_episode in sql_result:
            try:
                ep_obj = show_obj.get_episode(season=cur_episode['season'], episode=cur_episode['episode'],
                                              existing_only=True)
            except (BaseException, Exception):
                ep_obj = None
            t.ep_list.append({'season': cur_episode['season'], 'episode': cur_episode['episode'],
                              'reason': tvswitch_ep_names.get(cur_episode['reason'], 'unknown'), 'ep_obj': ep_obj})

        return t.respond()


class HomeProcessMedia(Home):

    def get(self, route, *args, **kwargs):
        route = route.strip('/')
        if 'files' == route:
            route = 'process_files'
        return super(HomeProcessMedia, self).get(route, *args, **kwargs)

    def index(self):

        t = PageTemplate(web_handler=self, file='home_postprocess.tmpl')
        t.submenu = [x for x in self.home_menu() if 'process-media' not in x['path']]
        return t.respond()

    def process_files(self, dir_name=None, nzb_name=None, quiet=None, process_method=None, force=None,
                      force_replace=None, failed='0', process_type='auto', stream='0', dupekey=None, is_basedir='1',
                      client=None, **kwargs):

        if 'test' in kwargs and kwargs['test'] in ['True', True, 1, '1']:
            return 'Connection success!'

        if not dir_name and ('0' == failed or not nzb_name):
            self.redirect('/home/process-media/')
        else:
            show_id_regex = re.compile(r'^SickGear-([A-Za-z]*)(\d+)-')
            tvid = 0
            show_obj = None
            nzbget_call = isinstance(client, string_types) and 'nzbget' == client
            nzbget_dupekey = nzbget_call and isinstance(dupekey, string_types) and \
                None is not show_id_regex.search(dupekey)
            if nzbget_dupekey:
                m = show_id_regex.match(dupekey)
                istr = m.group(1)
                for i in sickbeard.TVInfoAPI().sources:
                    if istr == sickbeard.TVInfoAPI(i).config.get('dupekey'):
                        tvid = i
                        break
                show_obj = helpers.find_show_by_id({tvid: int(m.group(2))}, no_mapped_ids=True)

            skip_failure_processing = nzbget_call and not nzbget_dupekey

            if nzbget_call and sickbeard.NZBGET_SCRIPT_VERSION != kwargs.get('pp_version', '0'):
                logger.log('Calling SickGear-NG.py script %s is not current version %s, please update.' %
                           (kwargs.get('pp_version', '0'), sickbeard.NZBGET_SCRIPT_VERSION), logger.ERROR)

            if sickbeard.NZBGET_SKIP_PM and nzbget_call and nzbget_dupekey and nzb_name and show_obj:
                processTV.process_minimal(nzb_name, show_obj,
                                          failed in (1, '1', True, 'True', 'true'),
                                          webhandler=None if '0' == stream else self.send_message)
            else:

                cleanup = kwargs.get('cleanup') in ('on', '1')
                if isinstance(dir_name, string_types):
                    dir_name = decode_str(dir_name)
                    if 'auto' != process_type:
                        sickbeard.PROCESS_LAST_DIR = dir_name
                        sickbeard.PROCESS_LAST_METHOD = process_method
                        if 'move' == process_method:
                            sickbeard.PROCESS_LAST_CLEANUP = cleanup
                        sickbeard.save_config()

                    if nzbget_call and isinstance(sickbeard.NZBGET_MAP, string_types) and sickbeard.NZBGET_MAP:
                        m = sickbeard.NZBGET_MAP.split('=')
                        dir_name, not_used = helpers.path_mapper(m[0], m[1], dir_name)

                result = processTV.processDir(dir_name if dir_name else None,
                                              None if not nzb_name else decode_str(nzb_name),
                                              process_method=process_method, pp_type=process_type,
                                              cleanup=cleanup,
                                              force=force in ('on', '1'),
                                              force_replace=force_replace in ('on', '1'),
                                              failed='0' != failed,
                                              webhandler=None if '0' == stream else self.send_message,
                                              show_obj=show_obj, is_basedir=is_basedir in ('on', '1'),
                                              skip_failure_processing=skip_failure_processing, client=client)

                if '0' == stream:
                    regexp = re.compile(r'(?i)<br[\s/]+>', flags=re.UNICODE)
                    result = regexp.sub('\n', result)
                    if None is not quiet and 1 == int(quiet):
                        regexp = re.compile(u'(?i)<a[^>]+>([^<]+)<[/]a>', flags=re.UNICODE)
                        return u'%s' % regexp.sub(r'\1', result)
                    return self._generic_message('Postprocessing results', u'<pre>%s</pre>' % result)

    # noinspection PyPep8Naming
    def processEpisode(self, dir_name=None, nzb_name=None, process_type=None, **kwargs):
        """ legacy function name, stubbed but can _not_ be removed as this
         is potentially used in pp scripts located outside of SG path (need to verify this)
        """
        kwargs['dir_name'] = dir_name or kwargs.pop('dir', None)
        kwargs['nzb_name'] = nzb_name or kwargs.pop('nzbName', None)
        kwargs['process_type'] = process_type or kwargs.pop('type', 'auto')
        kwargs['pp_version'] = kwargs.pop('ppVersion', '0')
        return self.process_files(**kwargs)


class AddShows(Home):

    def get(self, route, *args, **kwargs):
        route = route.strip('/')
        if 'import' == route:
            route = 'import_shows'
        elif 'find' == route:
            route = 'new_show'
        return super(AddShows, self).get(route, *args, **kwargs)

    def index(self):
        t = PageTemplate(web_handler=self, file='home_addShows.tmpl')
        t.submenu = self.home_menu()
        return t.respond()

    @staticmethod
    def get_infosrc_languages():
        result = sickbeard.TVInfoAPI().config['valid_languages']

        # sort list alphabetically with sickbeard.ADD_SHOWS_METALANG as the first item
        if sickbeard.ADD_SHOWS_METALANG in result:
            del result[result.index(sickbeard.ADD_SHOWS_METALANG)]
        result.sort()
        result.insert(0, sickbeard.ADD_SHOWS_METALANG)

        return json.dumps({'results': result})

    @staticmethod
    def generate_show_dir_name(show_name):
        return helpers.generate_show_dir_name(None, show_name)

    @staticmethod
    def _generate_search_text_list(search_term):
        # type: (AnyStr) -> Set[AnyStr]
        used_search_term = re.sub(r'\(?(19|20)\d{2}\)?', '', search_term).strip()
        # fix for users that don't know the correct title
        used_search_term = re.sub(r'(?i)(grown|mixed)(ish)', r'\1-\2', used_search_term)

        b_term = decode_str(used_search_term).strip()
        terms = []
        try:
            for cur_term in ([], [b_term.encode('utf-8')])[PY2] + [unidecode(b_term), b_term]:
                if cur_term not in terms:
                    terms += [cur_term]
        except (BaseException, Exception):
            text = used_search_term.strip()
            terms = [text if not PY2 else text.encode('utf-8')]

        return set(s for s in set([used_search_term] + terms) if s)

    # noinspection PyPep8Naming
    def search_tvinfo_for_showname(self, search_term, lang='en', search_tvid=None):
        if not lang or 'null' == lang:
            lang = sickbeard.ADD_SHOWS_METALANG or 'en'
        if lang != sickbeard.ADD_SHOWS_METALANG:
            sickbeard.ADD_SHOWS_METALANG = lang
            sickbeard.save_config()

        search_tvid = sg_helpers.try_int(search_tvid, None)
        search_term = search_term and search_term.strip()
        ids_to_search, id_srcs, searchable = {}, [], \
            (list(iterkeys(sickbeard.TVInfoAPI().search_sources)), [search_tvid])[
                search_tvid in sickbeard.TVInfoAPI().search_sources]
        id_check = re.finditer(r'((\w+):\W*([t0-9]+))', search_term)
        if id_check:
            for cur_match in id_check:
                total, slug, id_str = cur_match.groups()
                for cur_tvid in sickbeard.TVInfoAPI().all_sources:
                    if sickbeard.TVInfoAPI(cur_tvid).config.get('slug') \
                            and (slug.lower() == sickbeard.TVInfoAPI(cur_tvid).config['slug']
                                 or cur_tvid == sg_helpers.try_int(slug, None)):
                        try:
                            ids_to_search[cur_tvid] = int(id_str.strip().replace('tt', ''))
                        except (BaseException, Exception):
                            pass
                        try:
                            search_term = re.sub(r' *%s *' % re.escape(total), ' ', search_term).strip()
                            if cur_tvid in searchable:
                                id_srcs.append(cur_tvid)
                            break
                        except (BaseException, Exception):
                            continue

        id_check = re.finditer(
            r'(?P<imdb_full>[^ ]+imdb\.com/title/(?P<imdb>tt\d+)[^ ]*)|'
            r'(?P<imdb_id_full>[^ ]*(?P<imdb_id>' + helpers.RE_IMDB_ID + '))[^ ]*|'
            r'(?P<tmdb_full>[^ ]+themoviedb\.org/tv/(?P<tmdb>\d+)[^ ]*)|'
            r'(?P<trakt_full>[^ ]+trakt\.tv/shows/(?P<trakt>[^ /]+)[^ ]*)|'
            r'(?P<tvdb_full>[^ ]+thetvdb\.com/series/(?P<tvdb>[^ /]+)[^ ]*)|'
            r'(?P<tvdb_id_full>[^ ]+thetvdb\.com/[^\d]+(?P<tvdb_id>[^ /]+)[^ ]*)|'
            r'(?P<tvmaze_full>[^ ]+tvmaze\.com/shows/(?P<tvmaze>\d+)/?[^ ]*)', search_term)
        if id_check:
            for cur_match in id_check:
                for cur_tvid, cur_slug in [
                    (TVINFO_IMDB, 'imdb'), (TVINFO_IMDB, 'imdb_id'), (TVINFO_TMDB, 'tmdb'),
                    (TVINFO_TRAKT_SLUG, 'trakt'), (TVINFO_TVDB_SLUG, 'tvdb'), (TVINFO_TVDB, 'tvdb_id'),
                        (TVINFO_TVMAZE, 'tvmaze')]:
                    if cur_match.group(cur_slug):
                        try:
                            slug_match = cur_match.group(cur_slug).strip()
                            if TVINFO_IMDB == cur_tvid:
                                slug_match = slug_match.replace('tt', '')
                            if cur_tvid not in (TVINFO_TVDB_SLUG, TVINFO_TRAKT_SLUG):
                                slug_match = sg_helpers.try_int(slug_match, slug_match)
                            ids_to_search[cur_tvid] = slug_match
                            search_term = re.sub(r' *%s *' % re.escape(cur_match.group('%s_full' % cur_slug)), ' ',
                                                 search_term).strip()
                            if TVINFO_TVDB_SLUG == cur_tvid:
                                cur_tvid = TVINFO_TVDB
                            elif TVINFO_TRAKT_SLUG == cur_tvid:
                                cur_tvid = TVINFO_TRAKT
                            if cur_tvid in searchable:
                                id_srcs.append(cur_tvid)
                        except (BaseException, Exception):
                            pass

        # term is used for relevancy
        term = decode_str(search_term).strip()
        used_search_term = self._generate_search_text_list(search_term)
        text_search_used = bool(used_search_term)

        exclude_results = []
        if TVINFO_TVMAZE in ids_to_search:
            id_srcs = [TVINFO_TVMAZE] + [i for i in id_srcs if TVINFO_TVMAZE != i]
            if TVINFO_TVMAZE not in searchable:
                exclude_results.append(TVINFO_TVMAZE)

        results = {}
        final_results = []
        sources_to_search = id_srcs + [s for s in [TVINFO_TRAKT] + searchable if s not in id_srcs]
        ids_search_used = ids_to_search.copy()

        for cur_tvid in sources_to_search:
            tvinfo_config = sickbeard.TVInfoAPI(cur_tvid).api_params.copy()
            tvinfo_config['language'] = lang
            tvinfo_config['custom_ui'] = classes.AllShowInfosNoFilterListUI
            t = sickbeard.TVInfoAPI(cur_tvid).setup(**tvinfo_config)
            results.setdefault(cur_tvid, {})
            try:
                for cur_result in t.search_show(list(used_search_term), ids=ids_search_used):
                    if TVINFO_TRAKT == cur_tvid and not cur_result['ids'].tvdb:
                        continue
                    tv_src_id = int(cur_result['id'])
                    if cur_tvid in exclude_results:
                        ids_search_used.update({k: v for k, v in iteritems(cur_result.get('ids', {}))
                                                if v and k not in iterkeys(ids_to_search)})
                    else:
                        results[cur_tvid][tv_src_id] = cur_result.copy()
                        results[cur_tvid][tv_src_id]['direct_id'] = \
                            (cur_tvid in ids_to_search and ids_to_search.get(cur_tvid)
                             and tv_src_id == ids_to_search.get(cur_tvid)) or \
                            (TVINFO_TVDB == cur_tvid and cur_result.get('slug') and
                             ids_to_search.get(TVINFO_TVDB_SLUG) == cur_result.get('slug')) or False
                        if results[cur_tvid][tv_src_id]['direct_id'] or \
                                any(ids_to_search[si] == cur_result.get('ids', {})[si] for si in ids_to_search):
                            ids_search_used.update({k: v for k, v in iteritems(cur_result.get('ids', {}))
                                                    if v and k not in iterkeys(ids_to_search)})
                        results[cur_tvid][tv_src_id]['rename_suggest'] = '' \
                            if not results[cur_tvid][tv_src_id]['firstaired'] \
                            else dateutil.parser.parse(results[cur_tvid][tv_src_id]['firstaired']).year
                    if not text_search_used and cur_tvid in ids_to_search and tv_src_id == ids_to_search.get(cur_tvid):
                        used_search_term.update(self._generate_search_text_list(cur_result['seriesname']))
                        if not term:
                            term = decode_str(cur_result['seriesname']).strip()
            except (BaseException, Exception):
                pass

        if TVINFO_TVDB not in searchable:
            try:
                results.pop(TVINFO_TRAKT)
            except (BaseException, Exception):
                pass

        id_names = {tvid: (name, '%s via %s' % (sickbeard.TVInfoAPI(TVINFO_TVDB).name, name))[TVINFO_TRAKT == tvid]
                    for tvid, name in iteritems(sickbeard.TVInfoAPI().all_sources)}

        if TVINFO_TRAKT in results and TVINFO_TVDB in results:
            tvdb_ids = list_keys(results[TVINFO_TVDB])
            results[TVINFO_TRAKT] = {k: v for k, v in iteritems(results[TVINFO_TRAKT]) if v['ids'].tvdb not in tvdb_ids}

        def in_db(tvid, prod_id):
            show_obj = helpers.find_show_by_id({(tvid, TVINFO_TVDB)[TVINFO_TRAKT == tvid]: prod_id},
                                               no_mapped_ids=False, no_exceptions=True)
            return any([show_obj]) and '/home/view-show?tvid_prodid=%s' % show_obj.tvid_prodid

        # noinspection PyUnboundLocalVariable
        map_consume(final_results.extend,
                    [[[id_names[tvid], in_db(*((tvid, int(show['id'])),
                                               (TVINFO_TVDB, show['ids'][TVINFO_TVDB]))[TVINFO_TRAKT == tvid]),
                       tvid, (tvid, TVINFO_TVDB)[TVINFO_TRAKT == tvid],
                       sickbeard.TVInfoAPI((tvid, TVINFO_TVDB)[TVINFO_TRAKT == tvid]).config['slug'],
                       (sickbeard.TVInfoAPI((tvid, TVINFO_TVDB)[TVINFO_TRAKT == tvid]).config['show_url'] %
                        show['ids'][(tvid, TVINFO_TVDB)[TVINFO_TRAKT == tvid]])
                       + ('', '&lid=%s' % sickbeard.TVInfoAPI().config['langabbv_to_id'][lang])[TVINFO_TVDB == tvid],
                       int(show['id']),
                       show['seriesname'], helpers.xhtml_escape(show['seriesname']), show['firstaired'],
                       (isinstance(show['firstaired'], string_types)
                        and SGDatetime.sbfdate(dateutil.parser.parse(show['firstaired'])) or ''),
                       show.get('network', '') or '', show.get('genres', '') or '',  # 11 - 12
                       show.get('language', ''), show.get('language_country_code') or '',  # 13 - 14
                       re.sub(r'([,.!][^,.!]*?)$', '...',
                              re.sub(r'([.!?])(?=\w)', r'\1 ',
                                     helpers.xhtml_escape((show.get('overview', '') or '')[:250:].strip()))),  # 15
                       self._make_search_image_url(tvid, show),  # 16
                       100 - ((show['direct_id'] and 100)
                              or self.get_uw_ratio(term, show['seriesname'], show.get('aliases') or [],
                                                   show.get('language_country_code') or '')),
                       None, None, None, None, None, None, None, None, None,  # 18 - 26
                       show['direct_id'], show.get('rename_suggest')
                       ] for show in itervalues(shows)] for tvid, shows in iteritems(results)])

        def final_order(sortby_index, data, final_sort):
            idx_is_indb = 1
            for (_n, x) in enumerate(data):
                x[sortby_index] = _n + (1000, 0)[x[idx_is_indb] and 'notop' not in sickbeard.RESULTS_SORTBY]
            return data if not final_sort else sorted(data, reverse=False, key=lambda _x: _x[sortby_index])

        def sort_newest(data_result, is_last_sort, combine):
            return sort_date(data_result, is_last_sort, 19, as_combined=combine)

        def sort_oldest(data_result, is_last_sort, combine):
            return sort_date(data_result, is_last_sort, 21, False, combine)

        def sort_date(data_result, is_last_sort, idx_sort, reverse=True, as_combined=False):
            idx_aired = 9
            date_sorted = sorted(data_result, reverse=reverse, key=lambda x: (dateutil.parser.parse(
                    re.match(r'^(?:19|20)\d\d$', str(x[idx_aired])) and ('%s-12-31' % str(x[idx_aired]))
                    or (x[idx_aired] and str(x[idx_aired])) or '1900')))
            combined = final_order(idx_sort + 1, date_sorted, is_last_sort)

            idx_src = 2
            grouped = final_order(idx_sort, sorted(date_sorted, key=lambda x: x[idx_src]), is_last_sort)

            return (grouped, combined)[as_combined]

        def sort_az(data_result, is_last_sort, combine):
            return sort_zaaz(data_result, is_last_sort, 23, as_combined=combine)

        def sort_za(data_result, is_last_sort, combine):
            return sort_zaaz(data_result, is_last_sort, 25, True, combine)

        def sort_zaaz(data_result, is_last_sort, idx_sort, reverse=False, as_combined=False):
            idx_title = 7
            zaaz_sorted = sorted(data_result, reverse=reverse, key=lambda x: (
                (remove_article(x[idx_title].lower()), x[idx_title].lower())[sickbeard.SORT_ARTICLE]))
            combined = final_order(idx_sort + 1, zaaz_sorted, is_last_sort)

            idx_src = 2
            grouped = final_order(idx_sort, sorted(zaaz_sorted, key=lambda x: x[idx_src]), is_last_sort)

            return (grouped, combined)[as_combined]

        def sort_rel(data_result, is_last_sort, as_combined):
            idx_rel_sort, idx_rel = 17, 17
            idx_title = 7
            idx_src = 2
            rel_sorted = sorted(data_result, key=lambda x: (x[idx_rel], x[idx_title], x[idx_src]))
            combined = final_order(idx_rel_sort + 1, rel_sorted, is_last_sort)

            grouped = final_order(idx_rel_sort, sorted(rel_sorted, key=lambda x: (x[idx_src])), is_last_sort)

            return (grouped, combined)[as_combined]

        if 'az' == sickbeard.RESULTS_SORTBY[:2]:
            sort_results = [sort_oldest, sort_newest, sort_rel, sort_za, sort_az]
        elif 'za' == sickbeard.RESULTS_SORTBY[:2]:
            sort_results = [sort_oldest, sort_newest, sort_rel, sort_az, sort_za]
        elif 'newest' == sickbeard.RESULTS_SORTBY[:6]:
            sort_results = [sort_az, sort_rel, sort_oldest, sort_newest]
        elif 'oldest' == sickbeard.RESULTS_SORTBY[:6]:
            sort_results = [sort_az, sort_rel, sort_newest, sort_oldest]
        else:
            sort_results = [sort_za, sort_az, sort_oldest, sort_newest, sort_rel]

        for n, func in enumerate(sort_results):
            final_results = func(final_results, n == len(sort_results) - 1, 'nogroup' == sickbeard.RESULTS_SORTBY[-7:])

        return json.dumps({'results': final_results})

    @staticmethod
    def _make_search_image_url(iid, show_info):
        img_url = ''
        if TVINFO_TRAKT == iid:
            img_url = 'imagecache?path=browse/thumb/trakt&filename=%s&trans=0&tmdbid=%s&tvdbid=%s' % \
                      ('%s.jpg' % show_info['ids'].trakt, show_info.get('tmdb_id'), show_info['ids'].tvdb)
        elif TVINFO_TVDB == iid:
            img_url = 'imagecache?path=browse/thumb/tvdb&filename=%s&trans=0&tvdbid=%s' % \
                      ('%s.jpg' % show_info['id'], show_info['id'])
        elif TVINFO_TVMAZE == iid and show_info.get('image'):
            img_url = 'imagecache?path=browse/thumb/tvmaze&filename=%s&trans=0&source=%s' % \
                      ('%s.jpg' % show_info['id'], show_info['image'])
            sickbeard.CACHE_IMAGE_URL_LIST.add_url(show_info['image'])
        return img_url

    @classmethod
    def get_uw_ratio(cls, search_term, showname, aliases, lang=None):
        search_term = decode_str(search_term, errors='replace')
        showname = decode_str(showname, errors='replace')
        s = fuzz.UWRatio(search_term, showname)
        # check aliases and give them a little lower score
        lower_alias = 0
        for cur_alias in aliases or []:
            ns = fuzz.UWRatio(search_term, cur_alias)
            if (ns - 1) > s:
                s = ns
                lower_alias = 1

        # if lang param is supplied, add scale in order to reorder elements 1) en:lang 2) other:lang 3) alias
        # this spacer behaviour may improve the original logic, but currently isn't due to lang used as off switch
        # scale = 3 will enable spacing for all use cases
        scale = (1, 3)[None is not lang]

        score_scale = (s * scale)
        if score_scale:
            score_scale -= lower_alias

            # if lang param is supplied, and does not specify English, then lower final score
            score_scale -= (1, 0)[None is lang or lang in ('gb',) or not score_scale]

        return score_scale

    def mass_add_table(self, root_dir=None, hash_dir=None, **kwargs):

        root_dir = root_dir or kwargs.get('root_dir[]')
        if not root_dir:
            return 'No folders selected.'

        t = PageTemplate(web_handler=self, file='home_massAddTable.tmpl')
        t.submenu = self.home_menu()
        t.kwargs = {'hash_dir': hash_dir}
        t.dir_list = []

        root_d = sickbeard.ROOT_DIRS.split('|')
        if hash_dir:
            root_dirs = root_d[1:]
        else:
            default_i = 0 if not sickbeard.ROOT_DIRS else int(root_d[0])

            root_dirs = [unquote_plus(x) for x in ([root_dir], root_dir)[type(root_dir) == list]]
            if len(root_dirs) > default_i:
                tmp = root_dirs[default_i]
                root_dirs.remove(tmp)
                root_dirs.insert(0, tmp)

        dir_data = {}
        display_one_dir = None

        for cur_root_dir in root_dirs:
            try:
                for cur_dir in scantree(cur_root_dir, filter_kind=True, recurse=False):

                    normpath = ek.ek(os.path.normpath, cur_dir.path)
                    highlight = hash_dir == re.sub('[^a-z]', '', sg_helpers.md5_for_text(normpath))
                    if hash_dir:
                        display_one_dir = highlight
                    if not hash_dir or display_one_dir:
                        dir_data.setdefault(cur_root_dir, {
                            'highlight': [], 'rename_suggest': [], 'normpath': [], 'name': [], 'sql': []})

                        dir_data[cur_root_dir]['highlight'].append(highlight)
                        dir_data[cur_root_dir]['normpath'].append(normpath)
                        suggest = None
                        if display_one_dir:
                            rename_suggest = ' '
                            if kwargs.get('rename_suggest'):
                                rename_suggest = ' %s ' % kwargs.get('rename_suggest')
                            suggestions = ([], [rename_suggest.rstrip()])[bool(rename_suggest.strip())] + \
                                ['%s(%s)' % (rename_suggest, x) for x in range(10) if 1 < x]
                            for cur_suggestion in suggestions:
                                if not os.path.exists('%s%s' % (normpath, cur_suggestion)):
                                    suggest = cur_suggestion
                                    break
                        dir_data[cur_root_dir]['rename_suggest'].append(suggest)
                        dir_data[cur_root_dir]['name'].append(cur_dir.name)
                        dir_data[cur_root_dir]['sql'].append([
                            """
                            SELECT indexer FROM tv_shows WHERE location = ? LIMIT 1
                            """, [normpath]])
                        if display_one_dir:
                            break
            except (BaseException, Exception):
                pass

            if display_one_dir:
                break

        my_db = db.DBConnection()
        for _, cur_data in iteritems(dir_data):
            cur_data['exists'] = my_db.mass_action(cur_data['sql'])

            for cur_enum, cur_normpath in enumerate(cur_data['normpath']):
                if display_one_dir and not cur_data['highlight'][cur_enum]:
                    continue

                dir_item = dict(normpath=cur_normpath, rootpath='%s%s' % (ek.ek(os.path.dirname, cur_normpath), os.sep),
                                name=cur_data['name'][cur_enum], added_already=any(cur_data['exists'][cur_enum]),
                                highlight=cur_data['highlight'][cur_enum])

                if display_one_dir and cur_data['rename_suggest'][cur_enum]:
                    dir_item['rename_suggest'] = cur_data['rename_suggest'][cur_enum]

                tvid = prodid = show_name = None
                for cur_provider in itervalues(sickbeard.metadata_provider_dict):
                    if prodid and show_name:
                        break

                    (tvid, prodid, show_name) = cur_provider.retrieveShowMetadata(cur_normpath)

                    # default to TVDB if TV info src was not detected
                    if show_name and (not tvid or not prodid):
                        (sn, idx, pid) = helpers.search_infosrc_for_show_id(show_name, tvid, prodid)

                        # set TV info vars from found info
                        if idx and pid:
                            (tvid, prodid, show_name) = (idx, pid, sn)

                # in case we don't have both requirements, set both to None
                if not tvid or not prodid:
                    tvid = prodid = None

                dir_item['existing_info'] = (tvid, prodid, show_name)

                if helpers.find_show_by_id({tvid: prodid}):
                    dir_item['added_already'] = True

                t.dir_list.append(dir_item)

        return t.respond()

    def new_show(self, show_to_add=None, other_shows=None, use_show_name=False, **kwargs):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to add_new_show
        """
        self.set_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Expires', '0')

        t = PageTemplate(web_handler=self, file='home_newShow.tmpl')
        t.submenu = self.home_menu()
        t.enable_anime_options = True
        t.enable_default_wanted = True
        t.kwargs = kwargs

        tvid, show_dir, prodid, show_name = self.split_extra_show(show_to_add)

        # use the given show_dir for the TV info search if available
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

        # tell the template whether we're providing it show name & TV info src
        t.use_provided_info = bool(prodid and tvid and show_name)
        if t.use_provided_info:
            t.provided_prodid = int(prodid or 0)
            t.provided_show_name = show_name

        t.provided_show_dir = show_dir
        t.other_shows = other_shows
        t.infosrc = sickbeard.TVInfoAPI().search_sources
        search_tvid = None
        if use_show_name and 1 == show_name.count(':'):  # if colon is found once
            search_tvid = filter_list(lambda x: bool(x),
                                      [('%s:' % sickbeard.TVInfoAPI(_tvid).config['slug']) in show_name and _tvid
                                       for _tvid, _ in iteritems(t.infosrc)])
            search_tvid = 1 == len(search_tvid) and search_tvid[0]
        t.provided_tvid = search_tvid or int(tvid or sickbeard.TVINFO_DEFAULT)
        t.infosrc_icons = [sickbeard.TVInfoAPI(cur_tvid).config.get('icon') for cur_tvid in t.infosrc]
        t.meta_lang = sickbeard.ADD_SHOWS_METALANG
        t.allowlist = []
        t.blocklist = []
        t.groups = []

        t.show_scene_maps = list(itervalues(sickbeard.scene_exceptions.xem_ids_list))

        has_shows = len(sickbeard.showList)
        t.try_id = []  # [dict try_tip: try_term]
        t.try_id_name = []  # [dict try_tip: try_term]
        t.try_url = []  # [dict try_tip: try_term]
        url_num = 0
        for cur_idx, (cur_tvid, cur_try, cur_id_def, cur_url_def) in enumerate([
                (TVINFO_IMDB, '%s:tt%s', '0944947', 'https://www.imdb.com/title/tt0944947'),
                (TVINFO_TMDB, '%s:%s', '1399', 'https://www.themoviedb.org/tv/1399'),
                (TVINFO_TRAKT, None, None, 'https://trakt.tv/shows/game-of-thrones'),
                (TVINFO_TVDB, None, None, 'https://thetvdb.com/series/game-of-thrones'),
                (TVINFO_TVDB, '%s:%s', '121361', 'https://thetvdb.com/?tab=series&id=121361&lid=7'),
                (TVINFO_TVMAZE, '%s:%s', '82', None)]
        ):
            slug = sickbeard.TVInfoAPI(cur_tvid).config['slug']
            try_id = has_shows and cur_try and sickbeard.showList[-1].ids[cur_tvid].get('id')
            if not cur_idx:
                t.try_name = [{
                    'showname': 'Game of Thrones' if not try_id else sickbeard.showList[-1].name.replace("'", "\\'")}]

            if cur_try:
                id_key = '%s:id%s' % (slug, ('',  ' (GoT)')[not try_id])
                id_val = cur_try % (slug, try_id or cur_id_def)
                t.try_id += [{id_key: id_val}]
                t.try_id_name += [{'%s show name' % id_key: '%s %s' % (id_val, t.try_name[0]['showname'])}]

            if cur_url_def:
                url_num += 1
                t.try_url += [{
                    'url .. %s%s' % (url_num, ('', ' (GoT)')[not cur_try]):
                        cur_url_def if not try_id else sickbeard.TVInfoAPI(cur_tvid).config['show_url'] % try_id}]

        return t.respond()

    def randomhot_anidb(self, **kwargs):

        browse_type = 'AniDB'
        filtered = []

        xref_src = 'https://raw.githubusercontent.com/ScudLee/anime-lists/master/anime-list.xml'
        xml_data = helpers.get_url(xref_src)
        xref_root = xml_data and helpers.parse_xml(xml_data)
        if None is not xref_root and not len(xref_root):
            xref_root = None

        # noinspection HttpUrlsUsage
        url = 'http://api.anidb.net:9001/httpapi?client=sickgear&clientver=1&protover=1&request=main'
        response = helpers.get_url(url)
        if response and None is not xref_root:
            oldest, newest = None, None
            try:
                anime_root = helpers.parse_xml(response)
                hot_anime, random_rec = [anime_root.find(node) for node in ['hotanime', 'randomrecommendation']]
                random_rec = [item.find('./anime') for item in random_rec]
                oldest_dt, newest_dt = 9999999, 0
                for list_type, items in [('hot', list(hot_anime)), ('recommended', random_rec)]:
                    for anime in items:
                        ids = dict(anidb=config.to_int(anime.get('id')))
                        xref_node = xref_root.find('./anime[@anidbid="%s"]' % ids['anidb'])
                        if None is xref_node:
                            continue
                        # noinspection PyUnresolvedReferences
                        tvdbid = config.to_int(xref_node.get('tvdbid'))
                        if None is tvdbid:
                            continue
                        ids.update(dict(tvdb=tvdbid))
                        first_aired, title, image = [None is not y and y.text or y for y in [
                            anime.find(node) for node in ['startdate', 'title', 'picture']]]

                        dt = dateutil.parser.parse(first_aired)
                        dt_ordinal = dt.toordinal()
                        dt_string = SGDatetime.sbfdate(dt)
                        if dt_ordinal < oldest_dt:
                            oldest_dt = dt_ordinal
                            oldest = dt_string
                        if dt_ordinal > newest_dt:
                            newest_dt = dt_ordinal
                            newest = dt_string

                        # img_uri = 'http://img7.anidb.net/pics/anime/%s' % image
                        img_uri = 'https://cdn-eu.anidb.net/images/main/%s' % image
                        images = dict(poster=dict(thumb='imagecache?path=browse/thumb/anidb&source=%s' % img_uri))
                        sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)

                        votes = rating = 0
                        counts = anime.find('./ratings/permanent')
                        if isinstance(counts, object):
                            # noinspection PyUnresolvedReferences
                            votes = counts.get('count')
                            # noinspection PyUnresolvedReferences
                            rated = float(counts.text)
                            rating = 100 < rated and rated / 10 or 10 > rated and 10 * rated or rated

                        # noinspection HttpUrlsUsage
                        filtered.append(dict(
                            type=list_type,
                            ids=ids,
                            premiered=dt_ordinal,
                            premiered_str=dt_string,
                            when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not poss. 16.11.2015
                            title=title.strip(),
                            images=images,
                            url_src_db='http://anidb.net/perl-bin/animedb.pl?show=anime&aid=%s' % ids['anidb'],
                            url_tvdb=sickbeard.TVInfoAPI(TVINFO_TVDB).config['show_url'] % ids['tvdb'],
                            votes=votes, rating=rating,
                            genres='', overview=''
                        ))
            except (BaseException, Exception):
                pass

            kwargs.update(dict(oldest=oldest, newest=newest))

        return self.browse_shows(browse_type, 'Random and Hot at AniDB', filtered, **kwargs)

    def anime_default(self):

        return self.redirect('/add-shows/randomhot-anidb')

    def info_anidb(self, ids, show_name):

        if not filter_list(lambda tvid_prodid: helpers.find_show_by_id(tvid_prodid), ids.split(' ')):
            return self.new_show('|'.join(['', '', '', ' '.join([ids, show_name])]), use_show_name=True, is_anime=True)

    @staticmethod
    def watchlist_config(**kwargs):

        if not isinstance(sickbeard.IMDB_ACCOUNTS, type([])):
            sickbeard.IMDB_ACCOUNTS = list(sickbeard.IMDB_ACCOUNTS)
        accounts = dict(map_none(*[iter(sickbeard.IMDB_ACCOUNTS)] * 2))

        if 'enable' == kwargs.get('action'):
            account_id = re.findall(r'\d{6,32}', kwargs.get('input', ''))
            if not account_id:
                return json.dumps({'result': 'Fail: Invalid IMDb ID'})
            acc_id = account_id[0]

            url = 'https://www.imdb.com/user/ur%s/watchlist' % acc_id + \
                  '?sort=date_added,desc&title_type=tvSeries,tvEpisode,tvMiniSeries&view=detail'
            html = helpers.get_url(url, nocache=True)
            if not html:
                return json.dumps({'result': 'Fail: No list found with id: %s' % acc_id})
            if 'id="unavailable"' in html or 'list is not public' in html or 'not enabled public view' in html:
                return json.dumps({'result': 'Fail: List is not public with id: %s' % acc_id})

            try:
                list_name = re.findall(r'(?i)og:title[^>]+?content[^"]+?"([^"]+?)\s+Watchlist\s*"',
                                       html)[0].replace('\'s', '')
                accounts[acc_id] = list_name or 'noname'
            except (BaseException, Exception):
                return json.dumps({'result': 'Fail: No list found with id: %s' % acc_id})

        else:
            acc_id = kwargs.get('select', '')
            if acc_id not in accounts:
                return json.dumps({'result': 'Fail: Unknown IMDb ID'})

            if 'disable' == kwargs.get('action'):
                accounts[acc_id] = '(Off) %s' % accounts[acc_id].replace('(Off) ', '')
            else:
                del accounts[acc_id]

        gears = [[k, v] for k, v in iteritems(accounts) if 'sickgear' in v.lower()]
        if gears:
            del accounts[gears[0][0]]
        yours = [[k, v] for k, v in iteritems(accounts) if 'your' == v.replace('(Off) ', '').lower()]
        if yours:
            del accounts[yours[0][0]]
        sickbeard.IMDB_ACCOUNTS = [x for tup in sorted(list(iteritems(accounts)), key=lambda t: t[1]) for x in tup]
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

    @staticmethod
    def parse_imdb(data, filtered, kwargs):

        oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0
        show_list = (data or {}).get('list', {}).get('items', {})
        idx_ids = dict(map_iter(lambda so: (so.imdbid, (so.tvid, so.prodid)),
                                filter_iter(lambda _so: getattr(_so, 'imdbid', None), sickbeard.showList)))

        # list_id = (data or {}).get('list', {}).get('id', {})
        for row in show_list:
            row = data.get('titles', {}).get(row.get('const'))
            if not row:
                continue
            try:
                ids = dict(imdb=row.get('id', ''))
                year, ended = 2 * [None]
                if 2 == len(row.get('primary').get('year')):
                    year, ended = row.get('primary').get('year')
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

                overview = row.get('plot')
                rating = row.get('ratings', {}).get('rating', 0)
                voting = row.get('ratings', {}).get('votes', 0)
                images = {}
                img_uri = '%s' % row.get('poster', {}).get('url', '')
                if img_uri and 'tv_series.gif' not in img_uri and 'nopicture' not in img_uri:
                    scale = (lambda low1, high1: int((float(450) / high1) * low1))
                    dims = [row.get('poster', {}).get('width', 0), row.get('poster', {}).get('height', 0)]
                    s = [scale(x, int(max(dims))) for x in dims]
                    img_uri = re.sub(r'(?im)(.*V1_?)(\..*?)$', r'\1UX%s_CR0,0,%s,%s_AL_\2'
                                     % (s[0], s[0], s[1]), img_uri)
                    images = dict(poster=dict(thumb='imagecache?path=browse/thumb/imdb&source=%s' % img_uri))
                    sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)

                filtered.append(dict(
                    premiered=dt_ordinal,
                    premiered_str=year or 'No year',
                    ended_str=ended or '',
                    when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not poss. 16.11.2015
                    genres=', '.join(row.get('metadata', {}).get('genres', {})) or 'No genre yet',
                    ids=ids,
                    images='' if not img_uri else images,
                    overview='No overview yet' if not overview else helpers.xhtml_escape(overview[:250:]),
                    rating=int(helpers.try_float(rating) * 10),
                    title=row.get('primary').get('title'),
                    url_src_db='https://www.imdb.com/%s/' % row.get('primary').get('href').strip('/'),
                    votes=helpers.try_int(voting, 'TBA')))

                tvid, prodid = idx_ids.get(ids['imdb'], (None, None))
                if tvid and tvid in [_tvid for _tvid in sickbeard.TVInfoAPI().search_sources]:
                    infosrc_slug, infosrc_url = (sickbeard.TVInfoAPI(tvid).config[x] for x in ('slug', 'show_url'))
                    filtered[-1]['ids'][infosrc_slug] = prodid
                    filtered[-1]['url_' + infosrc_slug] = infosrc_url % prodid
            except (AttributeError, TypeError, KeyError, IndexError):
                pass

        kwargs.update(dict(oldest=oldest, newest=newest))

        return show_list and True or None

    def parse_imdb_html(self, html, filtered, kwargs):

        img_size = re.compile(r'(?im)(V1[^XY]+([XY]))(\d+)([^\d]+)(\d+)([^\d]+)(\d+)([^\d]+)(\d+)([^\d]+)(\d+)(.*?)$')

        with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
            show_list = soup.select('.lister-list')
            shows = [] if not show_list else show_list[0].select('.lister-item')
            oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0

            for row in shows:
                try:
                    title = row.select('.lister-item-header a[href*=title]')[0]
                    url_path = title['href'].strip('/')
                    ids = dict(imdb=helpers.parse_imdb_id(url_path))
                    year, ended = 2 * [None]
                    first_aired = row.select('.lister-item-header .lister-item-year')
                    if len(first_aired):
                        years = re.findall(r'.*?(\d{4})(?:.*?(\d{4}))?.*', first_aired[0].get_text())
                        year, ended = years and years[0] or 2 * [None]
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
                            scale = (lambda low1, high1: int((float(450) / high1) * low1))
                            high = int(max([match.group(9), match.group(11)]))
                            scaled = [scale(x, high) for x in
                                      [(int(match.group(n)), high)[high == int(match.group(n))] for n in
                                       (3, 5, 7, 9, 11)]]
                            parts = [match.group(1), match.group(4), match.group(6), match.group(8), match.group(10),
                                     match.group(12)]
                            img_uri = img_uri.replace(match.group(), ''.join(
                                [str(y) for x in map_none(parts, scaled) for y in x if None is not y]))
                            images = dict(poster=dict(thumb='imagecache?path=browse/thumb/imdb&source=%s' % img_uri))
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
                        overview='No overview yet' if not overview else helpers.xhtml_escape(overview[:250:]),
                        rating=0 if not len(rating) else int(helpers.try_float(rating) * 10),
                        title=title.get_text().strip(),
                        url_src_db='https://www.imdb.com/%s/' % url_path.strip('/'),
                        votes=0 if not len(voting) else helpers.try_int(voting, 'TBA')))

                    show_obj = helpers.find_show_by_id({TVINFO_IMDB: int(ids['imdb'].replace('tt', ''))},
                                                       no_mapped_ids=False)
                    for tvid in filter_iter(lambda _tvid: _tvid == show_obj.tvid, sickbeard.TVInfoAPI().search_sources):
                        infosrc_slug, infosrc_url = (sickbeard.TVInfoAPI(tvid).config[x] for x in
                                                     ('slug', 'show_url'))
                        filtered[-1]['ids'][infosrc_slug] = show_obj.prodid
                        filtered[-1]['url_' + infosrc_slug] = infosrc_url % show_obj.prodid
                except (AttributeError, TypeError, KeyError, IndexError):
                    continue

            kwargs.update(dict(oldest=oldest, newest=newest))

        return show_list and True or None

    def watchlist_imdb(self, **kwargs):

        if 'add' == kwargs.get('action'):
            return self.redirect('/config/general/#core-component-group2')

        if kwargs.get('action') in ('delete', 'enable', 'disable'):
            return self.watchlist_config(**kwargs)

        browse_type = 'IMDb'

        filtered = []
        footnote = None
        start_year, end_year = (datetime.date.today().year - 10, datetime.date.today().year + 1)
        periods = [(start_year, end_year)] + [(x - 10, x) for x in range(start_year, start_year - 40, -10)]

        accounts = dict(map_none(*[iter(sickbeard.IMDB_ACCOUNTS)] * 2))
        acc_id, list_name = (sickbeard.IMDB_DEFAULT_LIST_ID, sickbeard.IMDB_DEFAULT_LIST_NAME) if \
            0 == helpers.try_int(kwargs.get('account')) or \
            kwargs.get('account') not in accounts or \
            accounts.get(kwargs.get('account'), '').startswith('(Off) ') else \
            (kwargs.get('account'), accounts.get(kwargs.get('account')))

        list_name += ('\'s', '')['your' == list_name.replace('(Off) ', '').lower()]

        url = 'https://www.imdb.com/user/ur%s/watchlist' % acc_id
        url_ui = '?mode=detail&page=1&sort=date_added,desc&' \
                 'title_type=tvSeries,tvEpisode,tvMiniSeries&ref_=wl_ref_typ'

        html = helpers.get_url(url + url_ui, headers={'Accept-Language': 'en-US'})
        if html:
            show_list_found = None
            try:
                data = json.loads((re.findall(r'(?im)IMDb.*?Initial.*?\.push\((.*)\).*?$', html) or ['{}'])[0])
                show_list_found = self.parse_imdb(data, filtered, kwargs)
            except (BaseException, Exception):
                pass
            if not show_list_found:
                show_list_found = self.parse_imdb_html(html, filtered, kwargs)
            kwargs.update(dict(start_year=start_year))

            if len(filtered):
                footnote = ('Note; Some images on this page may be cropped at source: ' +
                            '<a target="_blank" href="%s">%s watchlist at IMDb</a>' % (
                                helpers.anon_url(url + url_ui), list_name))
            elif None is not show_list_found or (None is show_list_found and list_name in html):
                kwargs['show_header'] = True
                kwargs['error_msg'] = 'No TV titles in the <a target="_blank" href="%s">%s watchlist at IMDb</a>' % (
                    helpers.anon_url(url + url_ui), list_name)

        kwargs.update(dict(footnote=footnote, mode='watchlist-%s' % acc_id, periods=periods))
        return self.browse_shows(browse_type, '%s IMDb Watchlist' % list_name, filtered, **kwargs)

    def popular_imdb(self, **kwargs):

        browse_type = 'IMDb'

        filtered = []
        footnote = None
        start_year, end_year = (datetime.date.today().year - 10, datetime.date.today().year + 1)
        periods = [(start_year, end_year)] + [(x - 10, x) for x in range(start_year, start_year - 40, -10)]

        start_year_in, end_year_in = [helpers.try_int(x) for x in (('0,0', kwargs.get('period'))[
            ',' in kwargs.get('period', '')]).split(',')]
        if 1900 < start_year_in < 2050 and 2050 > end_year_in > 1900:
            start_year, end_year = (start_year_in, end_year_in)

        mode = 'popular-%s,%s' % (start_year, end_year)

        page = 'more' in kwargs and '51' or ''
        if page:
            mode += '-more'
        url = 'https://www.imdb.com/search/title?at=0&sort=moviemeter&' \
              'title_type=tvSeries,tvEpisode,tvMiniSeries&year=%s,%s&start=%s' % (start_year, end_year, page)
        html = helpers.get_url(url, headers={'Accept-Language': 'en-US'})
        if html:
            show_list_found = None
            try:
                data = json.loads((re.findall(r'(?im)IMDb.*?Initial.*?\.push\((.*)\).*?$', html) or ['{}'])[0])
                show_list_found = self.parse_imdb(data, filtered, kwargs)
            except (BaseException, Exception):
                pass
            if not show_list_found:
                self.parse_imdb_html(html, filtered, kwargs)
            kwargs.update(dict(mode=mode, periods=periods))

            if len(filtered):
                footnote = ('Note; Some images on this page may be cropped at source: ' +
                            '<a target="_blank" href="%s">IMDb</a>' % helpers.anon_url(url))

        kwargs.update(dict(footnote=footnote))
        return self.browse_shows(browse_type, 'Most Popular IMDb TV', filtered, **kwargs)

    def imdb_default(self):

        return self.redirect('/add-shows/popular-imdb')

    def info_imdb(self, ids, show_name):

        return self.new_show('|'.join(['', '', '', helpers.parse_imdb_id(ids) and ' '.join([ids, show_name])]),
                             use_show_name=True)

    def trakt_anticipated(self):

        return self.browse_trakt(
            'shows/anticipated?limit=%s&' % 100,
            'Anticipated at Trakt',
        )

    def trakt_newseasons(self):

        return self.browse_trakt(
            '/calendars/all/shows/premieres/%s/%s?' % (SGDatetime.sbfdate(
                dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
            'Season premieres at Trakt',
            mode='newseasons',
            footnote='Note; Expect default placeholder images in this list')

    def trakt_newshows(self):

        return self.browse_trakt(
            '/calendars/all/shows/new/%s/%s?' % (SGDatetime.sbfdate(
                dt=datetime.datetime.now() + datetime.timedelta(days=-16), d_preset='%Y-%m-%d'), 32),
            'Brand-new shows at Trakt',
            mode='newshows',
            footnote='Note; Expect default placeholder images in this list')

    def trakt_popular(self):

        return self.browse_trakt(
            'shows/popular?limit=%s&' % 100,
            'Popular at Trakt',
            mode='popular')

    def trakt_trending(self):

        return self.browse_trakt(
            'shows/trending?limit=%s&' % 100,
            'Trending at Trakt',
            mode='trending',
            footnote='Tip: For more Trakt, use "Show" near the top of this view')

    def trakt_watched(self, **kwargs):

        return self.trakt_action('watch', **kwargs)

    def trakt_played(self, **kwargs):

        return self.trakt_action('play', **kwargs)

    def trakt_collected(self, **kwargs):

        return self.trakt_action('collect', **kwargs)

    def trakt_action(self, action, **kwargs):

        cycle, desc, ext = (('month', 'month', ''), ('year', '12 months', '-year'))['year' == kwargs.get('period', '')]
        return self.browse_trakt(
            'shows/%sed/%sly?limit=%s&' % (action, cycle, 100),
            'Most %sed at Trakt during the last %s' % (action, desc),
            mode='%sed%s' % (action, ext))

    def trakt_recommended(self, **kwargs):

        if 'add' == kwargs.get('action'):
            return self.redirect('/config/notifications/#tabs-3')

        account = helpers.try_int(kwargs.get('account'))
        try:
            name = sickbeard.TRAKT_ACCOUNTS[account].name
        except KeyError:
            return self.trakt_default()
        return self.browse_trakt(
            'recommendations/shows?limit=%s&' % 100,
            'Recommended for <b class="grey-text">%s</b> by Trakt' % name,
            mode='recommended-%s' % account, send_oauth=account)

    def trakt_watchlist(self, **kwargs):

        if 'add' == kwargs.get('action'):
            return self.redirect('/config/notifications/#tabs-3')

        account = helpers.try_int(kwargs.get('account'))
        try:
            name = sickbeard.TRAKT_ACCOUNTS[account].name
        except KeyError:
            return self.trakt_default()
        return self.browse_trakt(
            'users/%s/watchlist/shows?limit=%s&' % (sickbeard.TRAKT_ACCOUNTS[account].slug, 100),
            'WatchList for <b class="grey-text">%s</b> by Trakt' % name,
            mode='watchlist-%s' % account, send_oauth=account)

    def trakt_default(self):

        return self.redirect('/add-shows/%s' % ('trakt-trending', sickbeard.TRAKT_MRU)[any(sickbeard.TRAKT_MRU)])

    @staticmethod
    def get_trakt_data(url_path, **kwargs):
        normalised, filtered = ([], [])
        error_msg = None
        try:
            account = kwargs.get('send_oauth')
            if account:
                account = helpers.try_int(account)
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
        except exceptions_helper.ConnectionSkipException as e:
            logger.log('Skipping Trakt because of previous failure: %s' % ex(e))
        except (IndexError, KeyError):
            pass

        if not normalised:
            error_msg = 'No items in watchlist.  Use the "Add to watchlist" button at the Trakt website'
            raise Exception(error_msg)

        oldest_dt = 9999999
        newest_dt = 0
        oldest = None
        newest = None
        for item in normalised:
            ignore = r'''
            ((bbc|channel\s*?5.*?|itv)\s*?(drama|documentaries))|bbc\s*?(comedy|music)|music\s*?specials|tedtalks
                    '''
            language = (item.get('show', {}).get('language') or '').lower()
            language_en = 'en' == language
            country = (item.get('show', {}).get('country') or '').lower()
            country_ok = country in ('uk', 'gb', 'ie', 'ca', 'us', 'au', 'nz', 'za')
            if re.search(ignore, item['show']['title'].strip(), re.I | re.X) or \
                    (not language_en and not country_ok) or \
                    not (item.get('show', {}).get('overview') or item.get('episode', {}).get('overview')):
                continue
            try:
                dt = dateutil.parser.parse(item['show']['first_aired'])
                dt_ordinal = dt.toordinal()
                dt_string = SGDatetime.sbfdate(dt)
                if dt_ordinal < oldest_dt:
                    oldest_dt = dt_ordinal
                    oldest = dt_string
                if dt_ordinal > newest_dt:
                    newest_dt = dt_ordinal
                    newest = dt_string

                tmdbid = item.get('show', {}).get('ids', {}).get('tmdb', 0)
                tvdbid = item.get('show', {}).get('ids', {}).get('tvdb', 0)
                traktid = item.get('show', {}).get('ids', {}).get('trakt', 0)
                images = dict(poster=dict(thumb='imagecache?path=browse/thumb/trakt&filename=%s&tmdbid=%s&tvdbid=%s' %
                                                ('%s.jpg' % traktid, tmdbid, tvdbid)))
                filtered.append(dict(
                    premiered=dt_ordinal,
                    premiered_str=dt_string,
                    when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not yet available 16.11.2015
                    episode_number='' if 'episode' not in item else item['episode']['number'] or 1,
                    episode_overview=(
                        '' if 'episode' not in item else
                        '' if None is item.get('episode', {}).get('overview') and (language_en or country_ok)
                        else item['episode']['overview'].strip() or ''),
                    episode_season='' if 'episode' not in item else item['episode']['season'] or 1,
                    genres=('' if 'genres' not in item['show'] else
                            ', '.join(['%s' % v for v in item['show']['genres']])),
                    ids=item['show']['ids'],
                    images=images,
                    overview=(item.get('show', {}).get('overview') or '').strip(),
                    rating=0 < item['show'].get('rating', 0) and
                           ('%.2f' % (item['show'].get('rating') * 10)).replace('.00', '') or 0,
                    title=item['show']['title'].strip(),
                    language=language,
                    language_img=not language_en and sickbeard.MEMCACHE_FLAG_IMAGES.get(language, False),
                    country=country,
                    country_img=sickbeard.MEMCACHE_FLAG_IMAGES.get(country, False),
                    url_src_db='https://trakt.tv/shows/%s' % item['show']['ids']['slug'],
                    url_tvdb=('', sickbeard.TVInfoAPI(TVINFO_TVDB).config['show_url'] % item['show']['ids']['tvdb'])[
                        isinstance(item['show']['ids']['tvdb'], integer_types)
                        and 0 < item['show']['ids']['tvdb']],
                    votes='0' if 'votes' not in item['show'] else item['show']['votes']))
            except (BaseException, Exception):
                pass

        if 'web_ui' in kwargs:
            return filtered, oldest, newest, error_msg

        return filtered, oldest, newest

    def browse_trakt(self, url_path, browse_title, **kwargs):

        browse_type = 'Trakt'
        normalised, filtered = ([], [])

        if not sickbeard.USE_TRAKT \
                and ('recommended' in kwargs.get('mode', '') or 'watchlist' in kwargs.get('mode', '')):
            error_msg = 'To browse personal recommendations, enable Trakt.tv in Config/Notifications/Social'
            return self.browse_shows(browse_type, browse_title, filtered, error_msg=error_msg, show_header=1, **kwargs)

        try:
            filtered, oldest, newest, error_msg = self.get_trakt_data(url_path, web_ui=True,
                                                                      send_oauth=kwargs.get('send_oauth'))
        except (BaseException, Exception):
            error_msg = 'No items in watchlist.  Use the "Add to watchlist" button at the Trakt website'
            return self.browse_shows(browse_type, browse_title, filtered, error_msg=error_msg, show_header=1, **kwargs)

        for item in filtered:
            key = 'episode_overview'
            if item[key]:
                item[key] = helpers.xhtml_escape(item[key][:250:].strip())
            key = 'overview'
            if item[key]:
                item[key] = helpers.xhtml_escape(item[key][:250:].strip())

        kwargs.update(dict(oldest=oldest, newest=newest, error_msg=error_msg))

        if 'recommended' not in kwargs.get('mode', '') and 'watchlist' not in kwargs.get('mode', ''):
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
    def show_toggle_hide(ids):
        save_config = False
        for sid in ids.split(' '):
            save_config = True
            if sid in sickbeard.BROWSELIST_HIDDEN:
                sickbeard.BROWSELIST_HIDDEN.remove(sid)
            else:
                sickbeard.BROWSELIST_HIDDEN += [sid]
        if save_config:
            sickbeard.save_config()
        return json.dumps({'success': save_config})

    def info_trakt(self, ids, show_name):

        if not filter_list(lambda tvid_prodid: helpers.find_show_by_id(tvid_prodid), ids.split(' ')):
            return self.new_show('|'.join(['', '', '', ' '.join([ids, show_name])]), use_show_name=True)

    def ne_default(self):

        return self.redirect('/add-shows/%s' % ('ne_newpop', sickbeard.NE_MRU)[any(sickbeard.NE_MRU)])

    def ne_newpop(self, **kwargs):
        return self.browse_ne(
            'hotshowsfilter', 'Popular recent premiered shows at Next Episode', mode='newpop', **kwargs)

    def ne_newtop(self, **kwargs):
        return self.browse_ne(
            'hotshowsfilter', 'Top rated recent premiered shows at Next Episode', mode='newtop', **kwargs)

    def ne_upcoming(self, **kwargs):
        return self.browse_ne(
            'upcomingshowsfilter', 'Upcoming shows at Next Episode', mode='upcoming', **kwargs)

    def ne_trending(self, **kwargs):
        return self.browse_ne(
            'trendingshowsfilter', 'Trending shows at Next Episode', mode='trending', **kwargs)

    def browse_ne(self, url_path, browse_title, **kwargs):

        browse_type = 'Nextepisode'

        footnote = None

        page = 1
        if 'more' in kwargs:
            page = 2
            kwargs['mode'] += '-more'

        filtered = []

        import browser_ua

        when_past = True
        if 'upcoming' in url_path:
            when_past = False
            url = '%s.php?t=1&s=1&inwl=0&user_id=' % url_path
        elif 'trending' in url_path:
            url = '%s.php?t=1&a=1&b=1&uid=&status=0&c=1' % url_path
        else:
            url = '%s.php?a=1&b=1&uid=0&status=0&c=2&sortOrder=%s' % (url_path, (0, 1)['Top' in browse_title])
        url = 'https://next-episode.net/PAGES/misc/%s&g=6&channel=0&actors=0&page=%s' % (url, page)

        html = helpers.get_url(url, headers={'User-Agent': browser_ua.get_ua()})
        if html:
            try:
                if re.findall(r'(?i)(<a[^>]+gopage\([^>]+)', html)[0]:
                    kwargs.update(dict(more=1))
            except (BaseException, Exception):
                pass

            with BS4Parser(html) as soup:
                shows = [] if not soup else soup.find_all(class_='list_item')
                oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0
                rc = [(k, re.compile(r'(?i).*?(\d+)\s*%s.*' % v)) for (k, v) in iteritems({
                    'months': 'month', 'days': 'day', 'hours': 'hour', 'minutes': 'min'})]
                rc_show = re.compile(r'^namelink_(\d+)$')
                rc_title_clean = re.compile(r'(?i)(?:\s*\((?:19|20)\d{2}\))?$')
                for row in shows:
                    try:
                        info_tag = row.find('a', id=rc_show)
                        if not info_tag:
                            continue

                        ids = dict(custom=rc_show.findall(info_tag['id'])[0], name='ne')
                        url_path = info_tag['href'].strip()

                        images = {}
                        img_uri = None
                        img_tag = info_tag.find('img')
                        if img_tag and isinstance(img_tag.attrs, dict):
                            img_src = img_tag.attrs.get('src').strip()
                            img_uri = img_src.startswith('//') and ('https:' + img_src) or img_src
                            images = dict(poster=dict(thumb='imagecache?path=browse/thumb/ne&source=%s' % img_uri))
                            sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)

                        title = info_tag.get_text('strip=True')
                        title = rc_title_clean.sub('', title.strip())

                        channel_tag = row.find('span', class_='channel_name')

                        network, date_info, dt = None, None, None
                        channel_tag_copy = copy.copy(channel_tag)
                        if channel_tag_copy:
                            network = channel_tag_copy.a.extract().get_text(strip=True)
                            date_info = re.sub(r'^[^\d]+', '', channel_tag_copy.get_text(strip=True))
                            if date_info:
                                dt = dateutil.parser.parse((date_info, '%s.01.01' % date_info)[4 == len(date_info)])

                        if not when_past and channel_tag:
                            tag = [t for t in channel_tag.next_siblings if hasattr(t, 'attrs')
                                   and 'printed' in ' '.join(t.get('class', ''))]
                            if len(tag):
                                age_args = {}
                                future = re.sub(r'[^\d]+(.*)', r'\1', tag[0].get_text(strip=True))
                                for (dim, rcx) in rc:
                                    value = helpers.try_int(rcx.sub(r'\1', future), None)
                                    if value:
                                        age_args.update({dim: value})

                                if age_args:
                                    dt = datetime.datetime.utcnow()
                                    if 'months' in age_args and 'days' in age_args:
                                        age_args['days'] -= 1
                                        dt += relativedelta(day=1)
                                    dt += relativedelta(**age_args)
                                    date_info = SGDatetime.sbfdate(dt)

                        dt_ordinal = 0
                        dt_string = ''
                        if date_info:
                            dt_ordinal = dt.toordinal()
                            dt_string = date_info
                            if dt_ordinal < oldest_dt:
                                oldest_dt = dt_ordinal
                                oldest = dt_string
                            if dt_ordinal > newest_dt:
                                newest_dt = dt_ordinal
                                newest = dt_string

                        genres = row.find(class_='genre')
                        if genres:
                            genres = re.sub(r',([^\s])', r', \1', genres.get_text(strip=True))
                        overview = row.find(class_='summary')
                        if overview:
                            overview = overview.get_text(strip=True)

                        rating = None
                        rating_tag = row.find(class_='rating')
                        if rating_tag:
                            label_tag = rating_tag.find('label')
                            if label_tag:
                                rating = re.sub(r'.*?width:\s*(\d+).*', r'\1', label_tag.get('style', ''))

                        filtered.append(dict(
                            premiered=dt_ordinal,
                            premiered_str=dt_string,
                            when_past=when_past,  # dt_ordinal < datetime.datetime.now().toordinal(),
                            genres=('No genre yet' if not genres else genres),
                            network=network or None,
                            ids=ids,
                            images='' if not img_uri else images,
                            overview='No overview yet' if not overview else helpers.xhtml_escape(overview[:250:]),
                            rating=(rating, 'TBD')[None is rating],
                            title=title,
                            url_src_db='https://next-episode.net/%s/' % url_path.strip('/'),
                            votes=None))

                    except (AttributeError, IndexError, KeyError, TypeError):
                        continue

                kwargs.update(dict(oldest=oldest, newest=newest))

        kwargs.update(dict(footnote=footnote, use_votes=False))

        mode = kwargs.get('mode', '')
        if mode:
            func = 'ne_%s' % mode
            if callable(getattr(self, func, None)):
                sickbeard.NE_MRU = func
                sickbeard.save_config()
        return self.browse_shows(browse_type, browse_title, filtered, **kwargs)

    # noinspection PyUnusedLocal
    def info_nextepisode(self, ids, show_name):

        return self.new_show('|'.join(['', '', '', show_name]), use_show_name=True)

    def tvm_default(self):

        return self.redirect('/add-shows/%s' % ('tvm_premieres', sickbeard.TVM_MRU)[any(sickbeard.TVM_MRU)])

    def tvm_premieres(self, **kwargs):
        return self.browse_tvm(
            'New Shows at TVmaze', mode='premieres', **kwargs)

    def tvm_returning(self, **kwargs):
        return self.browse_tvm(
            'Returning Shows at TVmaze', mode='returning', **kwargs)

    def browse_tvm(self, browse_title, **kwargs):

        browse_type = 'TVmaze'

        footnote = None
        filtered = []

        tvinfo_config = sickbeard.TVInfoAPI(TVINFO_TVMAZE).api_params.copy()
        t = sickbeard.TVInfoAPI(TVINFO_TVMAZE).setup(**tvinfo_config)
        if 'New' in browse_title:
            episodes = t.get_premieres()
        else:
            episodes = t.get_returning()

        # handle switching between returning and premieres
        sickbeard.BROWSELIST_MRU.setdefault(browse_type, dict())
        showfilter = ('by_returning', 'by_premiered')['New' in browse_title]
        saved_showsort = sickbeard.BROWSELIST_MRU[browse_type].get('tvm_%s' % kwargs['mode']) or '*,asc'
        showsort = saved_showsort + (',%s' % showfilter, '')[3 == len(saved_showsort.split(','))]
        sickbeard.BROWSELIST_MRU[browse_type].update(dict(showfilter=showfilter, showsort=showsort))

        oldest, newest, oldest_dt, newest_dt, use_networks = None, None, 9999999, 0, False
        dedupe = []
        parseinfo = dateutil.parser.parserinfo(dayfirst=False, yearfirst=True)
        base_url = sickbeard.TVInfoAPI(TVINFO_TVMAZE).config['show_url']
        for cur_episode_info in episodes:
            if cur_episode_info.show.id in dedupe:
                continue
            dedupe += [cur_episode_info.show.id]

            try:
                if cur_episode_info.airtime:
                    airtime = dateutil.parser.parse(cur_episode_info.airtime).time()
                else:
                    airtime = cur_episode_info.timestamp \
                              and SGDatetime.from_timestamp(cur_episode_info.timestamp).time()
                if (0, 0) == (airtime.hour, airtime.minute):
                    airtime = dateutil.parser.parse('23:59').time()
                dt = datetime.datetime.combine(
                    dateutil.parser.parse(
                        (cur_episode_info.show.firstaired or cur_episode_info.firstaired), parseinfo).date(), airtime)
                dt_ordinal = dt.toordinal()
                now_ordinal = datetime.datetime.now().toordinal()
                when_past = dt_ordinal < now_ordinal
                dt_string = SGDatetime.sbfdate(dt)

                if dt_ordinal < oldest_dt:
                    oldest_dt = dt_ordinal
                    oldest = dt_string
                if dt_ordinal > newest_dt:
                    newest_dt = dt_ordinal
                    newest = dt_string

                returning = returning_str = None
                if 'Return' in browse_title:
                    returning = '9'
                    returning_str = 'TBC'
                    if cur_episode_info.firstaired:
                        returning = cur_episode_info.firstaired
                        dt_returning = datetime.datetime.combine(
                            dateutil.parser.parse(returning, parseinfo).date(), airtime)
                        when_past = dt_returning.toordinal() < now_ordinal
                        returning_str = SGDatetime.sbfdate(dt_returning)

                try:
                    img_uri = cur_episode_info.show.poster
                    images = dict(poster=dict(thumb='imagecache?path=browse/thumb/tvmaze&source=%s' % img_uri))
                    sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)
                except(BaseException, Exception):
                    images = {}

                ids = dict(tvmaze=cur_episode_info.show.id)
                imdb_id = cur_episode_info.show.imdb_id
                if imdb_id:
                    ids['imdb'] = imdb_id
                tvdb_id = cur_episode_info.show.ids.get(TVINFO_TVDB)
                if tvdb_id:
                    ids['tvdb'] = tvdb_id

                network_name = cur_episode_info.show.network
                cc = 'US'
                if network_name:
                    use_networks = True
                    cc = cur_episode_info.show.network_country_code or cc

                language = ((cur_episode_info.show.language and 'jap' in cur_episode_info.show.language.lower())
                            and 'jp' or 'en')
                filtered.append(dict(
                    ids=ids,
                    premiered=dt_ordinal,
                    premiered_str=dt_string,
                    returning=returning,
                    returning_str=returning_str,
                    when_past=when_past,
                    episode_number=cur_episode_info.episodenumber,
                    episode_season=cur_episode_info.seasonnumber,
                    episode_overview='' if not cur_episode_info.overview else cur_episode_info.overview.strip(),
                    genres=(cur_episode_info.show.genre.strip('|').replace('|', ', ')
                            or ', '.join(cur_episode_info.show.show_type) or ''),
                    images=images,
                    overview=('No overview yet' if not cur_episode_info.show.overview
                              else helpers.xhtml_escape(cur_episode_info.show.overview.strip()[:250:])
                              .strip('*').strip()),
                    title=cur_episode_info.show.seriesname,
                    language=language,
                    language_img=sickbeard.MEMCACHE_FLAG_IMAGES.get(language, False),
                    country=cc,
                    country_img=sickbeard.MEMCACHE_FLAG_IMAGES.get(cc.lower(), False),
                    network=network_name,
                    rating=cur_episode_info.show.rating or cur_episode_info.show.popularity or 0,
                    url_src_db=base_url % cur_episode_info.show.id,
                ))
            except (BaseException, Exception):
                pass
            kwargs.update(dict(oldest=oldest, newest=newest))

        kwargs.update(dict(footnote=footnote, use_votes=False, use_networks=use_networks))

        mode = kwargs.get('mode', '')
        if mode:
            func = 'tvm_%s' % mode
            if callable(getattr(self, func, None)):
                sickbeard.TVM_MRU = func
                sickbeard.save_config()
        return self.browse_shows(browse_type, browse_title, filtered, **kwargs)

    # noinspection PyUnusedLocal
    def info_tvmaze(self, ids, show_name):

        if not filter_list(lambda tvid_prodid: helpers.find_show_by_id(tvid_prodid), ids.split(' ')):
            return self.new_show('|'.join(['', '', '', ' '.join([ids, show_name])]), use_show_name=True)

    def tvc_default(self):

        return self.redirect('/add-shows/%s' % ('tvc_newshows', sickbeard.TVC_MRU)[any(sickbeard.TVC_MRU)])

    def tvc_newshows(self, **kwargs):
        return self.browse_tvc(
            'TV-shows-starting-', 'New Shows at TV Calendar', mode='newshows', **kwargs)

    def tvc_returning(self, **kwargs):
        return self.browse_tvc(
            'TV-shows-starting-', 'Returning Shows at TV Calendar', mode='returning', **kwargs)

    def tvc_latest(self, **kwargs):
        return self.browse_tvc(
            'recent-additions', 'Latest new shows at TV Calendar', mode='latest', **kwargs)

    def browse_tvc(self, url_path, browse_title, **kwargs):

        browse_type = 'TVCalendar'

        footnote = None
        filtered = []
        today = datetime.datetime.today()
        months = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July',
                  'August', 'September', 'October', 'November', 'December']
        this_month = '%s-%s' % (months[today.month], today.strftime('%Y'))
        section = ''
        if kwargs.get('mode', '') in ('newshows', 'returning'):
            section = (kwargs.get('page') or this_month)
            url_path += section

        import browser_ua
        url = 'https://www.pogdesign.co.uk/cat/%s' % url_path
        html = helpers.get_url(url, headers={'User-Agent': browser_ua.get_ua()})
        use_votes = False
        if html:
            prev_month = dt_prev_month = None
            if kwargs.get('mode', '') in ('newshows', 'returning'):
                try:
                    prev_month = re.findall('(?i)href="/cat/tv-shows-starting-([^"]+)', html)[0]
                    dt_prev_month = dateutil.parser.parse('1-%s' % prev_month)
                except (BaseException, Exception):
                    prev_month = None
            get_prev_month = (lambda _dt: _dt.replace(day=1) - datetime.timedelta(days=1))
            get_next_month = (lambda _dt: _dt.replace(day=28) + datetime.timedelta(days=5))
            get_month_year = (lambda _dt: '%s-%s' % (months[_dt.month], _dt.strftime('%Y')))
            if prev_month:
                dt_next_month = get_next_month(dt_prev_month)
                while True:
                    next_month = get_month_year(dt_next_month)
                    if next_month not in (this_month, kwargs.get('page')):
                        break
                    dt_next_month = get_next_month(dt_next_month)
                while True:
                    if prev_month not in (this_month, kwargs.get('page')):
                        break
                    dt_prev_month = get_prev_month(dt_prev_month)
                    prev_month = get_month_year(dt_prev_month)

            else:
                dt_next_month = get_next_month(today)
                next_month = get_month_year(dt_next_month)
                dt_prev_month = get_prev_month(today)
                prev_month = get_month_year(dt_prev_month)

            suppress_item = not kwargs.get('page') or kwargs.get('page') == this_month
            get_date_text = (lambda m_y: m_y.replace('-', ' '))
            next_month_text = get_date_text(next_month)
            prev_month_text = get_date_text(prev_month)
            page_month_text = suppress_item and 'void' or get_date_text(kwargs.get('page'))
            kwargs.update(dict(pages=[
                ('tvc_newshows?page=%s' % this_month, 'New this month'),
                ('tvc_newshows?page=%s' % next_month, '...in %s' % next_month_text)] +
                ([('tvc_newshows?page=%s' % kwargs.get('page'), '...in %s' % page_month_text)], [])[suppress_item] +
                [('tvc_newshows?page=%s' % prev_month, '...in %s' % prev_month_text)] +
                [('tvc_returning?page=%s' % this_month, 'Returning this month'),
                 ('tvc_returning?page=%s' % next_month, '...in %s' % next_month_text)] +
                ([('tvc_returning?page=%s' % kwargs.get('page'), '...in %s' % page_month_text)], [])[suppress_item] +
                [('tvc_returning?page=%s' % prev_month, '...in %s' % prev_month_text)]
            ))

            with BS4Parser(html, parse_only=dict(div={'class': (lambda at: at and 'pgwidth' in at)})) as tbl:
                shows = []
                if kwargs.get('mode', '') in ('latest', 'newshows', 'returning'):
                    tags = tbl.select('h2[class*="midtitle"], div[class*="contbox"]')
                    collect = False
                    for cur_tag in tags:
                        if re.match(r'(?i)h\d+', cur_tag.name) and 'midtitle' in cur_tag.attrs.get('class', []):
                            text = cur_tag.get_text(strip=True)
                            if kwargs['mode'] in ('latest', 'newshows'):
                                if not collect and ('Latest' in text or 'New' in text):
                                    collect = True
                                    continue
                                break
                            elif 'New' in text:
                                continue
                            elif 'Return' in text:
                                collect = True
                                continue
                            break
                        if collect:
                            shows += [cur_tag]

                if not len(shows):
                    kwargs['error_msg'] = 'No TV titles found in <a target="_blank" href="%s">%s</a>%s,' \
                                          ' try another selection' % (
                        helpers.anon_url(url), browse_title, (' for %s' % section.replace('-', ' '), '')[not section])

                # build batches to correct htmlentity typos in overview
                from html5lib.constants import entities
                batches = []
                for cur_n, cur_name in enumerate(entities):
                    if 0 == cur_n % 150:
                        if cur_n:
                            batches += [batch]
                        batch = []
                    batch += [cur_name]
                else:
                    batches += [batch]

                oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0
                for row in shows:
                    try:
                        ids = dict(custom=row.select('input[type="checkbox"]')[0].attrs['value'], name='tvc')
                        info = row.find('a', href=re.compile('^/cat'))
                        url_path = info['href'].strip()

                        title = info.find('h2').get_text(strip=True)
                        img_uri = info.get('data-original', '').strip()
                        if not img_uri:
                            img_uri = re.findall(r'(?i).*?image:\s*url\(([^)]+)', info.attrs['style'])[0].strip()
                        images = dict(poster=dict(thumb='imagecache?path=browse/thumb/tvc&source=%s' % img_uri))
                        sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)
                        title = re.sub(r'(?i)(?::\s*season\s*\d+|\s*\((?:19|20)\d{2}\))?$', '', title.strip())

                        dt_ordinal = 0
                        dt_string = ''
                        date = genre = network = ''
                        date_tag = row.find('span', class_='startz')
                        if date_tag:
                            date_network = re.split(r'(?i)\son\s', ''.join(
                                [t.name and t.get_text() or str(t) for t in date_tag][0:2]))
                            date = re.sub('(?i)^(starts|returns)', '', date_network[0]).strip()
                            network = ('', date_network[1].strip())[2 == len(date_network)]
                        else:
                            date_tag = row.find('span', class_='selby')
                            if date_tag:
                                date = date_tag.get_text(strip=True)
                            network_genre = info.find('span')
                            if network_genre:
                                network_genre = network_genre.get_text(strip=True).split('//')
                                network = network_genre[0]
                                genre = ('', network_genre[1].strip())[2 == len(network_genre)]

                        if date:
                            dt = dateutil.parser.parse(date)
                            dt_ordinal = dt.toordinal()
                            dt_string = SGDatetime.sbfdate(dt)
                            if dt_ordinal < oldest_dt:
                                oldest_dt = dt_ordinal
                                oldest = dt_string
                            if dt_ordinal > newest_dt:
                                newest_dt = dt_ordinal
                                newest = dt_string

                        overview = row.find('span', class_='shwtxt')
                        if overview:
                            overview = re.sub(r'(?sim)(.*?)(?:[.\s]*\*\*NOTE.*?)?(\.{1,3})$', r'\1\2',
                                              overview.get_text(strip=True))
                            for cur_entities in batches:
                                overview = re.sub(r'and(%s)' % '|'.join(cur_entities), r'&\1', overview)

                        votes = None
                        votes_tag = row.find('span', class_='selby')
                        if votes_tag:
                            votes_tag = votes_tag.find('strong')
                            if votes_tag:
                                votes = re.sub(r'(?i)\s*users', '', votes_tag.get_text()).strip()
                                use_votes = True

                        filtered.append(dict(
                            premiered=dt_ordinal,
                            premiered_str=dt_string,
                            when_past=dt_ordinal < datetime.datetime.now().toordinal(),
                            genres=genre,
                            network=network or None,
                            ids=ids,
                            images='' if not img_uri else images,
                            overview='No overview yet' if not overview else helpers.xhtml_escape(overview[:250:]),
                            rating=None,
                            title=title,
                            url_src_db='https://www.pogdesign.co.uk/%s' % url_path.strip('/'),
                            votes=votes or 'n/a'))

                    except (AttributeError, IndexError, KeyError, TypeError):
                        continue

                kwargs.update(dict(oldest=oldest, newest=newest))

        kwargs.update(dict(footnote=footnote, use_ratings=False, use_votes=use_votes, show_header=True))

        mode = kwargs.get('mode', '')
        if mode:
            func = 'tvc_%s' % mode
            if callable(getattr(self, func, None)):
                sickbeard.TVC_MRU = func
                sickbeard.save_config()

        return self.browse_shows(browse_type, browse_title, filtered, **kwargs)

    # noinspection PyUnusedLocal
    def info_tvcalendar(self, ids, show_name):

        return self.new_show('|'.join(['', '', '', show_name]), use_show_name=True)

    def mc_default(self):

        return self.redirect('/add-shows/%s' % ('mc_newseries', sickbeard.MC_MRU)[any(sickbeard.MC_MRU)])

    def mc_newseries(self, **kwargs):
        return self.browse_mc(
            'release-date/new-series/date?', 'New Series at Metacritic', mode='newseries', **kwargs)

    def mc_90days(self, **kwargs):
        return self.browse_mc(
            'score/metascore/90day/filtered?sort=desc&', 'Last 90 days at Metacritic', mode='90days', **kwargs)

    def mc_year(self, **kwargs):
        return self.browse_mc(
            'score/metascore/year/filtered?sort=desc&', 'By year at Metacritic', mode='year', **kwargs)

    def mc_discussed(self, **kwargs):
        return self.browse_mc(
            'score/metascore/discussed/filtered?sort=desc&', 'Most discussed at Metacritic', mode='discussed', **kwargs)

    def mc_shared(self, **kwargs):
        return self.browse_mc(
            'score/metascore/shared/filtered?sort=desc&', 'Most shared at Metacritic', mode='shared', **kwargs)

    def browse_mc(self, url_path, browse_title, **kwargs):

        browse_type = 'Metacritic'

        footnote = None

        page = 'more' in kwargs and '&page=1' or ''
        if page:
            kwargs['mode'] += '-more'

        filtered = []

        import browser_ua
        url = 'https://www.metacritic.com/browse/tv/%sview=detailed%s' % (url_path, page)
        html = helpers.get_url(url, headers={'User-Agent': browser_ua.get_ua()})
        if html:
            try:
                if re.findall('(<a[^>]+rel="next"[^>]+)', html)[0]:
                    kwargs.update(dict(more=1))
            except (BaseException, Exception):
                pass

            with BS4Parser(html, parse_only=dict(table={'class': (lambda at: at and 'clamp-list' in at)})) as tbl:
                # with BS4Parser(html, features=['html5lib', 'permissive']) as soup:
                shows = [] if not tbl else tbl.find_all('tr')
                oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0
                for row in shows:
                    try:
                        ids = dict(custom=row.select('input[type="checkbox"]')[0].attrs['id'], name='mc')
                        info = row.find('a', href=re.compile('^/tv'))
                        url_path = info['href'].strip()

                        images = {}
                        img_uri = None
                        img = info.find('img')
                        if img and isinstance(img.attrs, dict):
                            title = img.attrs.get('alt')
                            img_src = img.attrs.get('src').split('-')
                            img_uri = img_src.pop(0)
                            if img_src:
                                img_uri += '.' + img_src[0].split('.')[-1]
                            images = dict(poster=dict(thumb='imagecache?path=browse/thumb/metac&source=%s' % img_uri))
                            sickbeard.CACHE_IMAGE_URL_LIST.add_url(img_uri)
                        if not title:
                            title = row.find('h3').get_text()
                        title = re.sub(r'(?i)(?::\s*season\s*\d+|\s*\((?:19|20)\d{2}\))?$', '', title.strip())

                        dt_ordinal = 0
                        dt_string = ''
                        date_tags = filter_list(lambda t: t.find('span'), row.find_all('div', class_='clamp-details'))
                        if date_tags:
                            dt = dateutil.parser.parse(date_tags[0].get_text().strip())
                            dt_ordinal = dt.toordinal()
                            dt_string = SGDatetime.sbfdate(dt)
                            if dt_ordinal < oldest_dt:
                                oldest_dt = dt_ordinal
                                oldest = dt_string
                            if dt_ordinal > newest_dt:
                                newest_dt = dt_ordinal
                                newest = dt_string

                        overview = row.find('div', class_='summary').get_text().strip()

                        rating = row.find('div', class_='clamp-metascore')
                        if rating:
                            rating = rating.find('div', class_='metascore_w')
                            if rating:
                                rating = rating.get_text().strip()
                        rating_user = row.find('div', class_='clamp-userscore')
                        if rating_user:
                            rating_user = rating_user.find('div', class_='metascore_w')
                            if rating_user:
                                rating_user = rating_user.get_text().strip()

                        season = -1
                        try:
                            season = re.findall(r'(\d+)(?:[.]\d*?)?$', url_path)[0]
                        except(BaseException, Exception):
                            pass

                        filtered.append(dict(
                            season=int(season),
                            premiered=dt_ordinal,
                            premiered_str=dt_string,
                            when_past=dt_ordinal < datetime.datetime.now().toordinal(),
                            genres='',
                            ids=ids,
                            images='' if not img_uri else images,
                            overview='No overview yet' if not overview else helpers.xhtml_escape(overview[:250:]),
                            rating=0 if not rating else rating or 'TBD',
                            rating_user='tbd' if not rating_user else int(helpers.try_float(rating_user) * 10) or 'tbd',
                            title=title,
                            url_src_db='https://www.metacritic.com/%s/' % url_path.strip('/'),
                            votes=None))

                    except (AttributeError, IndexError, KeyError, TypeError):
                        continue

                kwargs.update(dict(oldest=oldest, newest=newest))

        kwargs.update(dict(footnote=footnote, use_votes=False))

        mode = kwargs.get('mode', '')
        if mode:
            func = 'mc_%s' % mode
            if callable(getattr(self, func, None)):
                sickbeard.MC_MRU = func
                sickbeard.save_config()
        return self.browse_shows(browse_type, browse_title, filtered, **kwargs)

    # noinspection PyUnusedLocal
    def info_metacritic(self, ids, show_name):

        return self.new_show('|'.join(['', '', '', show_name]), use_show_name=True)

    @staticmethod
    def browse_mru(browse_type, **kwargs):
        save_config = False
        if browse_type in ('AniDB', 'IMDb', 'Metacritic', 'Trakt', 'TVCalendar', 'TVmaze', 'Nextepisode'):
            save_config = True
            if browse_type in ('TVmaze',) and kwargs.get('showfilter') and kwargs.get('showsort'):
                sickbeard.BROWSELIST_MRU.setdefault(browse_type, dict()) \
                    .update({kwargs.get('showfilter'): kwargs.get('showsort')})
            else:
                sickbeard.BROWSELIST_MRU[browse_type] = dict(
                    showfilter=kwargs.get('showfilter', ''), showsort=kwargs.get('showsort', ''))
        if save_config:
            sickbeard.save_config()
        return json.dumps({'success': save_config})

    def browse_shows(self, browse_type, browse_title, shows, **kwargs):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to add_new_show
        """
        t = PageTemplate(web_handler=self, file='home_browseShows.tmpl')
        t.submenu = self.home_menu()
        t.browse_type = browse_type
        t.browse_title = browse_title
        t.saved_showfilter = sickbeard.BROWSELIST_MRU.get(browse_type, {}).get('showfilter', '')
        t.saved_showsort = sickbeard.BROWSELIST_MRU.get(browse_type, {}).get('showsort', '*,asc,by_order')
        showsort = t.saved_showsort.split(',')
        t.saved_showsort_sortby = 3 == len(showsort) and showsort[2] or 'by_order'
        t.reset_showsort_sortby = ('votes' in t.saved_showsort_sortby and not kwargs.get('use_votes', True)
                                   or 'rating' in t.saved_showsort_sortby and not kwargs.get('use_ratings', True))
        t.is_showsort_desc = ('desc' == (2 <= len(showsort) and showsort[1] or 'asc')) and not t.reset_showsort_sortby
        t.saved_showsort_view = 1 <= len(showsort) and showsort[0] or '*'
        t.all_shows = []
        t.kwargs = kwargs
        known = []

        t.num_inlibrary = 0
        t.num_hidden = 0
        n_p = NameParser(indexer_lookup=False)
        rc_base = re.compile(r"(?i)^(?:dc|marvel)(?:['s]+\s)?")
        rc_nopost = re.compile(r'(?i)(?:\s*\([^)]+\))?$')
        rc_nopre = re.compile(r'(?i)(?:^\([^)]+\)\s*)?')
        for order, item in enumerate(shows):
            item['order'] = order
            tvid_prodid_list = []

            # first, process known ids
            for tvid, infosrc_slug in filter_iter(
                    lambda tvid_slug: item['ids'].get(tvid_slug[1])
                    and not sickbeard.TVInfoAPI(tvid_slug[0]).config.get('defunct'),
                    map_iter(lambda _tvid: (_tvid, sickbeard.TVInfoAPI(_tvid).config['slug']),
                             iterkeys(sickbeard.TVInfoAPI().all_sources))):
                try:
                    src_id = item['ids'][infosrc_slug]
                    tvid_prodid_list += ['%s:%s' % (infosrc_slug, src_id)]
                    imdb = helpers.parse_imdb_id(src_id)
                    if imdb:
                        src_id = sg_helpers.try_int(imdb.replace('tt', ''))
                    show_obj = helpers.find_show_by_id({tvid: src_id}, no_mapped_ids=False, no_exceptions=True)
                except (BaseException, Exception):
                    continue
                if not item.get('indb') and show_obj:
                    item['indb'] = sickbeard.TVInfoAPI(tvid).config.get('name')
                    t.num_inlibrary += 1

            # then, process custom ids
            if 'custom' in item['ids']:
                base_title = rc_base.sub('', item['title'])
                nopost_title = rc_nopost.sub('', item['title'])
                nopre_title = rc_nopre.sub('', item['title'])
                nopost_base_title = rc_nopost.sub('', base_title)
                nopre_base_title = rc_nopre.sub('', base_title)
                nopost_nopre_base_title = rc_nopost.sub('', nopre_base_title)
                titles = [item['title']]
                titles += ([], [base_title])[base_title not in titles]
                titles += ([], [nopost_title])[nopost_title not in titles]
                titles += ([], [nopre_title])[nopre_title not in titles]
                titles += ([], [nopost_base_title])[nopost_base_title not in titles]
                titles += ([], [nopre_base_title])[nopre_base_title not in titles]
                titles += ([], [nopost_nopre_base_title])[nopost_nopre_base_title not in titles]
                if 'premiered' in item and 1 == item.get('season', -1):
                    titles += ['%s.%s' % (_t, datetime.date.fromordinal(item['premiered']).year) for _t in titles]

                tvid_prodid_list += ['%s:%s' % (item['ids']['name'], item['ids']['custom'])]
                for cur_title in titles:
                    try:
                        _ = n_p.parse('%s.s01e01.mp4' % cur_title)
                        item['indb'] = item['ids']['name']
                        t.num_inlibrary += 1
                        break
                    except (InvalidNameException, InvalidShowException):
                        pass

            item['show_id'] = '%s' % ' '.join(tvid_prodid_list)

            if not item['show_id']:
                if 'tt' in item['ids'].get('imdb', ''):
                    item['show_id'] = item['ids']['imdb']

                if item['ids'].get('custom'):
                    item['show_id'] = item['ids']['custom']

            if item['show_id'] not in known:
                known.append(item['show_id'])
                t.all_shows.append(item)

                if any(filter_iter(lambda tp: tp in sickbeard.BROWSELIST_HIDDEN, tvid_prodid_list)):
                    item['hide'] = True
                    t.num_hidden += 1

        def _title(text):
            return ((remove_article(text), text)[sickbeard.SORT_ARTICLE]).lower()
        if 'order' not in t.saved_showsort_sortby or t.is_showsort_desc:
            for sort_when, sort_type in (
                    ('order', lambda _x: _x['order']),
                    ('name', lambda _x: _title(_x['title'])),
                    ('premiered', lambda _x: (_x['premiered'], _title(_x['title']))),
                    ('returning', lambda _x: (_x['returning'], _title(_x['title']))),
                    ('votes', lambda _x: (helpers.try_int(_x['votes']), _title(_x['title']))),
                    ('rating', lambda _x: (helpers.try_float(_x['rating']), _title(_x['title']))),
                    ('rating_votes', lambda _x: (helpers.try_float(_x['rating']), helpers.try_int(_x['votes']),
                                                 _title(_x['title'])))):
                if sort_when in t.saved_showsort_sortby:
                    t.all_shows.sort(key=sort_type, reverse=t.is_showsort_desc)
                    break

        return t.respond()

    def import_shows(self, **kwargs):
        """
        Prints out the page to add existing shows from a root dir
        """
        t = PageTemplate(web_handler=self, file='home_addExistingShow.tmpl')
        t.submenu = self.home_menu()
        t.enable_anime_options = False
        t.kwargs = kwargs
        t.multi_parents = helpers.maybe_plural(sickbeard.ROOT_DIRS.split('|')[1:]) and 's are' or ' is'

        return t.respond()

    def add_new_show(self, root_dir=None, full_show_path=None, which_series=None, provided_tvid=None, tvinfo_lang='en',
                     other_shows=None, skip_show=None,
                     quality_preset=None, any_qualities=None, best_qualities=None, upgrade_once=None,
                     wanted_begin=None, wanted_latest=None, tag=None,
                     pause=None, prune=None, default_status=None, scene=None, subs=None, flatten_folders=None,
                     anime=None, allowlist=None, blocklist=None,
                     return_to=None, cancel_form=None, rename_suggest=None, **kwargs):
        """
        Receive tvdb id, dir, and other options and create a show from them. If extra show dirs are
        provided then it forwards back to new_show, if not it goes to /home.
        """
        if None is not return_to:
            tvid, void, prodid, show_name = self.split_extra_show(which_series)
            if bool(helpers.try_int(cancel_form)):
                tvid = tvid or provided_tvid or '0'
                prodid = re.findall(r'tvid_prodid=[^%s]+%s([\d]+)' % tuple(2 * [TVidProdid.glue]), return_to)[0]
            return self.redirect(return_to % (tvid, prodid))

        # grab our list of other dirs if given
        if not other_shows:
            other_shows = []
        elif type(other_shows) != list:
            other_shows = [other_shows]

        def finish_add_show():
            # if there are no extra shows then go home
            if not other_shows:
                return self.redirect('/home/')

            # peel off the next one
            next_show_dir = other_shows[0]
            rest_of_show_dirs = other_shows[1:]

            # go to add the next show
            return self.new_show(next_show_dir, rest_of_show_dirs)

        # if we're skipping then behave accordingly
        if skip_show:
            return finish_add_show()

        # sanity check on our inputs
        if (not root_dir and not full_show_path) or not which_series:
            return 'Missing params, no production id or folder:' + repr(which_series) + ' and ' + repr(
                root_dir) + '/' + repr(full_show_path)

        # figure out what show we're adding and where
        series_pieces = which_series.split('|')
        if (which_series and root_dir) or (which_series and full_show_path and 1 < len(series_pieces)):
            if 4 > len(series_pieces):
                logger.log('Unable to add show due to show selection. Not enough arguments: %s' % (repr(series_pieces)),
                           logger.ERROR)
                ui.notifications.error('Unknown error. Unable to add show due to problem with show selection.')
                return self.redirect('/add-shows/import/')

            tvid = int(series_pieces[0])
            prodid = int(series_pieces[2])
            show_name = kwargs.get('folder') or series_pieces[3]
        else:
            # if no TV info source was provided use the default one set in General settings
            if not provided_tvid:
                provided_tvid = sickbeard.TVINFO_DEFAULT

            tvid = int(provided_tvid)
            prodid = int(which_series)
            show_name = os.path.basename(os.path.normpath(full_show_path))

        # use the whole path if it's given, or else append the show name to the root dir to get the full show path
        if full_show_path:
            show_dir = ek.ek(os.path.normpath, full_show_path)
            new_show = False
        else:
            show_dir = helpers.generate_show_dir_name(root_dir, show_name)
            new_show = True

        # if the dir exists, do 'add existing show'
        if ek.ek(os.path.isdir, show_dir) and not full_show_path:
            ui.notifications.error('Unable to add show', u'Found existing folder: ' + show_dir)
            return self.redirect(
                '/add-shows/import?tvid_prodid=%s%s%s&hash_dir=%s%s' %
                (tvid, TVidProdid.glue, prodid, re.sub('[^a-z]', '', sg_helpers.md5_for_text(show_dir)),
                 rename_suggest and ('&rename_suggest=%s' % rename_suggest) or ''))

        # don't create show dir if config says not to
        if sickbeard.ADD_SHOWS_WO_DIR:
            logger.log(u'Skipping initial creation due to config.ini setting (add_shows_wo_dir)')
        else:
            if not helpers.make_dir(show_dir):
                logger.log(u'Unable to add show because can\'t create folder: ' + show_dir, logger.ERROR)
                ui.notifications.error('Unable to add show', u'Can\'t create folder: ' + show_dir)
                return self.redirect('/home/')

            helpers.chmod_as_parent(show_dir)

        # prepare the inputs for passing along
        if not any_qualities:
            any_qualities = []
        if not best_qualities or int(quality_preset):
            best_qualities = []
        if type(any_qualities) != list:
            any_qualities = [any_qualities]
        if type(best_qualities) != list:
            best_qualities = [best_qualities]
        new_quality = Quality.combineQualities(map_list(int, any_qualities), map_list(int, best_qualities))
        upgrade_once = config.checkbox_to_value(upgrade_once)

        wanted_begin = config.minimax(wanted_begin, 0, -1, 10)
        wanted_latest = config.minimax(wanted_latest, 0, -1, 10)
        prune = config.minimax(prune, 0, 0, 9999)

        pause = config.checkbox_to_value(pause)
        scene = config.checkbox_to_value(scene)
        subs = config.checkbox_to_value(subs)
        flatten_folders = config.checkbox_to_value(flatten_folders)

        anime = config.checkbox_to_value(anime)
        if allowlist:
            allowlist = short_group_names(allowlist)
        if blocklist:
            blocklist = short_group_names(blocklist)

        # add the show
        sickbeard.show_queue_scheduler.action.add_show(
            tvid, prodid, show_dir,
            quality=new_quality, upgrade_once=upgrade_once,
            wanted_begin=wanted_begin, wanted_latest=wanted_latest, tag=tag,
            paused=pause, prune=prune, default_status=int(default_status), scene=scene, subtitles=subs,
            flatten_folders=flatten_folders, anime=anime, allowlist=allowlist, blocklist=blocklist,
            show_name=show_name, new_show=new_show, lang=tvinfo_lang
        )
        # ui.notifications.message('Show added', 'Adding the specified show into ' + show_dir)

        return finish_add_show()

    @staticmethod
    def split_extra_show(extra_show):
        if not extra_show:
            return 4 * [None]
        extra_show = decode_str(extra_show, errors='replace')
        split_vals = extra_show.split('|')
        tvid = helpers.try_int(split_vals[0], sickbeard.TVINFO_DEFAULT)
        show_dir = split_vals[1]
        if 4 > len(split_vals):
            return tvid, show_dir, None, None
        prodid = split_vals[2]
        show_name = '|'.join(split_vals[3:])

        return tvid, show_dir, prodid, show_name

    def add_existing_shows(self, shows_to_add=None, prompt_for_settings=None, **kwargs):
        """
        Receives a dir list and add them. Adds the ones with given TVDB IDs first, then forwards
        along to the new_show page.
        """
        if kwargs.get('tvid_prodid'):
            try:
                search = '%s:%s' % [(sickbeard.TVInfoAPI(c_tvid).config['slug'], c_prodid)
                                    for c_tvid, c_prodid in [tuple(kwargs.get('tvid_prodid').split(':'))]][0]
            except (BaseException, Exception):
                search = kwargs.get('tvid_prodid', '')
            return self.redirect(
                '/add-shows/find/?show_to_add=%s&use_show_name=True%s' %
                ('|'.join(['', '', '', search]),
                 '|folder=' in shows_to_add and ('&folder=%s' % shows_to_add.split('|folder=')[-1]) or ''))

        # grab a list of other shows to add, if provided
        if not shows_to_add:
            shows_to_add = []
        elif type(shows_to_add) != list:
            shows_to_add = [shows_to_add]

        prompt_for_settings = config.checkbox_to_value(prompt_for_settings)

        prodid_given = []
        prompt_list = []
        dirs_only = []
        # separate all the ones with production ids
        for cur_dir in shows_to_add:
            if '|' in cur_dir:
                split_vals = cur_dir.split('|')
                if 3 > len(split_vals):
                    dirs_only.append(cur_dir)
            if '|' not in cur_dir:
                dirs_only.append(cur_dir)
            else:
                tvid, show_dir, prodid, show_name = self.split_extra_show(cur_dir)

                if not show_dir or not prodid or not show_name:
                    continue

                src_tvid, src_prodid = [helpers.try_int(x, None) for x in prodid.split(':')]
                if tvid != src_tvid:
                    prompt_list.append(cur_dir.replace(prodid, ''))
                    continue

                prodid_given.append((tvid, show_dir, src_prodid, show_name))

        # if they don't want me to prompt for settings then I can just add all the nfo shows now
        num_added = 0
        for cur_show in prodid_given:
            tvid, show_dir, prodid, show_name = cur_show

            if None is not tvid and None is not prodid:
                # add the show
                sickbeard.show_queue_scheduler.action.add_show(
                    tvid, prodid, show_dir,
                    quality=sickbeard.QUALITY_DEFAULT,
                    paused=sickbeard.PAUSE_DEFAULT, default_status=sickbeard.STATUS_DEFAULT,
                    scene=sickbeard.SCENE_DEFAULT, subtitles=sickbeard.SUBTITLES_DEFAULT,
                    flatten_folders=sickbeard.FLATTEN_FOLDERS_DEFAULT, anime=sickbeard.ANIME_DEFAULT,
                    show_name=show_name
                )
                num_added += 1

        if num_added:
            ui.notifications.message('Shows Added',
                                     'Automatically added ' + str(num_added) + ' from their existing metadata files')

        if prompt_list:
            shows_to_add = prompt_list
            prompt_for_settings = True
        # if they want me to prompt for settings then I will just carry on to the new_show page
        if prompt_for_settings and shows_to_add:
            return self.new_show(shows_to_add[0], shows_to_add[1:])

        # if we're done then go home
        if not dirs_only:
            return self.redirect('/home/')

        # for the remaining shows we need to prompt for each one, so forward this on to the new_show page
        return self.new_show(dirs_only[0], dirs_only[1:])


class Manage(MainHandler):

    @staticmethod
    def manage_menu(exclude='n/a'):
        menu = [
            {'title': 'Backlog Overview', 'path': 'manage/backlog-overview/'},
            {'title': 'Search Tasks', 'path': 'manage/search-tasks/'},
            {'title': 'Show Tasks', 'path': 'manage/show-tasks/'},
            {'title': 'Episode Overview', 'path': 'manage/episode-overview/'}, ]

        if sickbeard.USE_SUBTITLES:
            menu.append({'title': 'Subtitles Missed', 'path': 'manage/subtitle-missed/'})

        if sickbeard.USE_FAILED_DOWNLOADS:
            menu.append({'title': 'Failed Downloads', 'path': 'manage/failed-downloads/'})

        return [x for x in menu if exclude not in x['title']]

    def index(self):
        t = PageTemplate(web_handler=self, file='manage.tmpl')
        t.submenu = self.manage_menu('Bulk')

        t.has_any_sports = False
        t.has_any_anime = False
        t.has_any_flat_folders = False
        t.shows = []
        t.shows_no_loc = []
        for cur_show_obj in sorted(sickbeard.showList, key=lambda _x: _x.name.lower()):
            t.has_any_sports |= bool(cur_show_obj.sports)
            t.has_any_anime |= bool(cur_show_obj.anime)
            t.has_any_flat_folders |= bool(cur_show_obj.flatten_folders)
            if not cur_show_obj.path:
                t.shows_no_loc += [cur_show_obj]
            else:
                t.shows += [cur_show_obj]

        return t.respond()

    def get_status_episodes(self, tvid_prodid, which_status):

        which_status = helpers.try_int(which_status)
        status_list = ((([which_status],
                         Quality.SNATCHED_ANY)[SNATCHED == which_status],
                        Quality.DOWNLOADED)[DOWNLOADED == which_status],
                       Quality.ARCHIVED)[ARCHIVED == which_status]

        my_db = db.DBConnection()
        tvid_prodid_list = TVidProdid(tvid_prodid).list
        # noinspection SqlResolve
        sql_result = my_db.select(
            'SELECT season, episode, name, airdate, status, location'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ? AND season != 0 AND status IN (' + ','.join(
                ['?'] * len(status_list)) + ')', tvid_prodid_list + status_list)

        result = {}
        for cur_result in sql_result:
            if not sickbeard.SEARCH_UNAIRED and 1000 > cur_result['airdate']:
                continue
            cur_season = int(cur_result['season'])
            cur_episode = int(cur_result['episode'])

            if cur_season not in result:
                result[cur_season] = {}

            cur_quality = Quality.splitCompositeStatus(int(cur_result['status']))[1]
            result[cur_season][cur_episode] = {'name': cur_result['name'],
                                               'airdateNever': 1000 > int(cur_result['airdate']),
                                               'qualityCss': Quality.get_quality_css(cur_quality),
                                               'qualityStr': Quality.qualityStrings[cur_quality],
                                               'sxe': '%d x %02d' % (cur_season, cur_episode)}

            if which_status in [SNATCHED, SKIPPED, IGNORED, WANTED]:

                # noinspection SqlResolve
                sql = 'SELECT action, date' \
                      ' FROM history' \
                      ' WHERE indexer = ? AND showid = ?' \
                      ' AND season = ? AND episode = ? AND action in (%s)' \
                      ' ORDER BY date DESC' % ','.join([str(q) for q in Quality.DOWNLOADED + Quality.SNATCHED_ANY])
                event_sql_result = my_db.select(sql, tvid_prodid_list + [cur_season, cur_episode])
                d_status, d_qual, s_status, s_quality, age = 5 * (None,)
                if event_sql_result:
                    for cur_result_event in event_sql_result:
                        if None is d_status and cur_result_event['action'] in Quality.DOWNLOADED:
                            d_status, d_qual = Quality.splitCompositeStatus(cur_result_event['action'])
                        if None is s_status and cur_result_event['action'] in Quality.SNATCHED_ANY:
                            s_status, s_quality = Quality.splitCompositeStatus(cur_result_event['action'])
                            aged = ((datetime.datetime.now() -
                                     datetime.datetime.strptime(str(cur_result_event['date']),
                                                                sickbeard.history.dateFormat))
                                    .total_seconds())
                            h = 60 * 60
                            d = 24 * h
                            days = aged // d
                            age = ([], ['%id' % days])[bool(days)]
                            hours, mins = 0, 0
                            if 7 > days:
                                hours = aged % d // h
                                mins = aged % d % h // 60
                            age = ', '.join(age + ([], ['%ih' % hours])[bool(hours)]
                                            + ([], ['%im' % mins])[not bool(days)])

                        if None is not d_status and None is not s_status:
                            break

                undo_from_history, change_to, status = self.recommend_status(
                    cur_result['status'], cur_result['location'], d_qual, cur_quality)
                if status:
                    result[cur_season][cur_episode]['recommend'] = [('. '.join(
                        (['snatched %s ago' % age], [])[None is age]
                        + ([], ['file %sfound' % ('not ', '')[bool(cur_result['location'])]])[
                            None is d_status or not undo_from_history]
                        + ['%s to <b>%s</b> ?' % (('undo from history',
                                                   'change')[None is d_status or not undo_from_history], change_to)])),
                        status]

        return json.dumps(result)

    @staticmethod
    def recommend_status(cur_status, location=None, d_qual=None, cur_quality=None):

        undo_from_history = False
        change_to = ''
        status = None
        if Quality.NONE == cur_quality:
            return undo_from_history, change_to, status

        cur_status = Quality.splitCompositeStatus(int(cur_status))[0]
        if any([location]):
            undo_from_history = True
            change_to = statusStrings[DOWNLOADED]
            status = [Quality.compositeStatus(DOWNLOADED, d_qual or cur_quality)]
        elif cur_status in Quality.SNATCHED_ANY + [IGNORED, SKIPPED, WANTED]:
            if None is d_qual:
                if cur_status not in [IGNORED, SKIPPED]:
                    change_to = statusStrings[SKIPPED]
                    status = [SKIPPED]
            else:
                # downloaded and removed
                if cur_status in Quality.SNATCHED_ANY + [WANTED] \
                        or sickbeard.SKIP_REMOVED_FILES in [ARCHIVED, IGNORED, SKIPPED]:
                    undo_from_history = True
                    change_to = '%s %s' % (statusStrings[ARCHIVED], Quality.qualityStrings[d_qual])
                    status = [Quality.compositeStatus(ARCHIVED, d_qual)]
                elif sickbeard.SKIP_REMOVED_FILES in [IGNORED, SKIPPED] \
                        and cur_status not in [IGNORED, SKIPPED]:
                    change_to = statusStrings[statusStrings[sickbeard.SKIP_REMOVED_FILES]]
                    status = [sickbeard.SKIP_REMOVED_FILES]

        return undo_from_history, change_to, status

    def episode_overview(self, which_status=None):

        which_status = helpers.try_int(which_status)
        if which_status:
            status_list = ((([which_status],
                             Quality.SNATCHED_ANY)[SNATCHED == which_status],
                            Quality.DOWNLOADED)[DOWNLOADED == which_status],
                           Quality.ARCHIVED)[ARCHIVED == which_status]
        else:
            status_list = []

        t = PageTemplate(web_handler=self, file='manage_episodeStatuses.tmpl')
        t.submenu = self.manage_menu('Episode')
        t.which_status = which_status

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT COUNT(*) AS snatched FROM [tv_episodes] WHERE season > 0 AND episode > 0 AND airdate > 1 AND ' +
            'status IN (%s)' % ','.join([str(quality) for quality in Quality.SNATCHED_ANY]))
        t.default_manage = sql_result and sql_result[0]['snatched'] and SNATCHED or WANTED

        # if we have no status then this is as far as we need to go
        if not status_list:
            return t.respond()

        # noinspection SqlResolve
        status_results = my_db.select(
            'SELECT show_name, tv_shows.indexer AS tvid, tv_shows.indexer_id AS prod_id, airdate'
            ' FROM tv_episodes, tv_shows'
            ' WHERE tv_episodes.status IN (' + ','.join(['?'] * len(status_list)) +
            ') AND season != 0'
            ' AND tv_episodes.indexer = tv_shows.indexer AND tv_episodes.showid = tv_shows.indexer_id'
            ' ORDER BY show_name COLLATE NOCASE',
            status_list)

        ep_counts = {}
        ep_count = 0
        never_counts = {}
        show_names = {}
        sorted_show_ids = []
        for cur_status_result in status_results:
            if not sickbeard.SEARCH_UNAIRED and 1000 > cur_status_result['airdate']:
                continue
            tvid_prodid = TVidProdid({cur_status_result['tvid']: cur_status_result['prod_id']})()
            if tvid_prodid not in ep_counts:
                ep_counts[tvid_prodid] = 1
            else:
                ep_counts[tvid_prodid] += 1
            ep_count += 1
            if tvid_prodid not in never_counts:
                never_counts[tvid_prodid] = 0
            if 1000 > int(cur_status_result['airdate']):
                never_counts[tvid_prodid] += 1

            show_names[tvid_prodid] = cur_status_result['show_name']
            if tvid_prodid not in sorted_show_ids:
                sorted_show_ids.append(tvid_prodid)

        t.show_names = show_names
        t.ep_counts = ep_counts
        t.ep_count = ep_count
        t.never_counts = never_counts
        t.sorted_show_ids = sorted_show_ids
        return t.respond()

    def change_episode_statuses(self, old_status, new_status, wanted_status=sickbeard.common.UNKNOWN, **kwargs):
        status = int(old_status)
        status_list = ((([status],
                         Quality.SNATCHED_ANY)[SNATCHED == status],
                        Quality.DOWNLOADED)[DOWNLOADED == status],
                       Quality.ARCHIVED)[ARCHIVED == status]

        changes, new_status = self.status_changes(new_status, wanted_status, **kwargs)

        my_db = None if not any(changes) else db.DBConnection()
        for tvid_prodid, c_what_to in iteritems(changes):
            tvid_prodid_list = TVidProdid(tvid_prodid).list
            for what, to in iteritems(c_what_to):
                if 'all' == what:
                    sql_result = my_db.select(
                        'SELECT season, episode'
                        ' FROM tv_episodes'
                        ' WHERE status IN (%s)' % ','.join(['?'] * len(status_list)) +
                        ' AND season != 0'
                        ' AND indexer = ? AND showid = ?',
                        status_list + tvid_prodid_list)
                    what = (sql_result and '|'.join(map_iter(lambda r: '%sx%s' % (r['season'], r['episode']),
                                                             sql_result))
                            or None)
                    to = new_status

                Home(self.application, self.request).set_show_status(tvid_prodid, what, to, direct=True)

        self.redirect('/manage/episode-overview/')

    @staticmethod
    def status_changes(new_status, wanted_status=sickbeard.common.UNKNOWN, **kwargs):

        # make a list of all shows and their associated args
        to_change = {}
        for arg in kwargs:
            # only work with checked checkboxes
            if kwargs[arg] == 'on':

                tvid_prodid, _, what = arg.partition('-')
                what, _, to = what.partition('-')
                to = (to, new_status)[not to]
                if 'recommended' != to:
                    to_change.setdefault(tvid_prodid, dict())
                    to_change[tvid_prodid].setdefault(to, [])
                    to_change[tvid_prodid][to] += [what]

        wanted_status = int(wanted_status)
        if wanted_status in (FAILED, WANTED):
            new_status = wanted_status

        changes = {}
        for tvid_prodid, to_what in iteritems(to_change):
            changes.setdefault(tvid_prodid, dict())
            all_to = None
            for to, what in iteritems(to_what):
                if 'all' in what:
                    all_to = to
                    continue
                changes[tvid_prodid].update({'|'.join(sorted(what)): (new_status, to)['recommended' == new_status]})
            if None is not all_to and not any(changes[tvid_prodid]):
                if 'recommended' == new_status:
                    del (changes[tvid_prodid])
                else:
                    changes[tvid_prodid] = {'all': all_to}

        return changes, new_status

    @staticmethod
    def show_subtitle_missed(tvid_prodid, which_subs):

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            'SELECT season, episode, name, subtitles'
            ' FROM tv_episodes'
            ' WHERE indexer = ? AND showid = ?'
            ' AND season != 0 AND status LIKE "%4"',
            TVidProdid(tvid_prodid).list)

        result = {}
        for cur_result in sql_result:
            if 'all' == which_subs:
                if len(set(cur_result['subtitles'].split(',')).intersection(set(subtitles.wanted_languages()))) >= len(
                        subtitles.wanted_languages()):
                    continue
            elif which_subs in cur_result['subtitles'].split(','):
                continue

            cur_season = '{0:02d}'.format(cur_result['season'])
            cur_episode = '{0:02d}'.format(cur_result['episode'])

            if cur_season not in result:
                result[cur_season] = {}

            if cur_episode not in result[cur_season]:
                result[cur_season][cur_episode] = {}

            result[cur_season][cur_episode]['name'] = cur_result['name']

            result[cur_season][cur_episode]['subtitles'] = ','.join([
                subliminal.language.Language(subtitle, strict=False).alpha2
                for subtitle in cur_result['subtitles'].split(',')]) if '' != cur_result['subtitles'] else ''

        return json.dumps(result)

    def subtitle_missed(self, which_subs=None):

        t = PageTemplate(web_handler=self, file='manage_subtitleMissed.tmpl')
        t.submenu = self.manage_menu('Subtitle')
        t.which_subs = which_subs

        if not which_subs:
            return t.respond()

        my_db = db.DBConnection()
        # noinspection SqlResolve
        sql_result = my_db.select(
            'SELECT tv_episodes.subtitles as subtitles, show_name,'
            ' tv_shows.indexer AS tv_id, tv_shows.indexer_id AS prod_id'
            ' FROM tv_episodes, tv_shows'
            ' WHERE tv_shows.subtitles = 1'
            ' AND tv_episodes.status LIKE "%4" AND tv_episodes.season != 0'
            ' AND tv_shows.indexer = tv_episodes.indexer AND tv_episodes.showid = tv_shows.indexer_id'
            ' ORDER BY show_name')

        ep_counts = {}
        show_names = {}
        sorted_show_ids = []
        for cur_result in sql_result:
            if 'all' == which_subs:
                if len(set(cur_result['subtitles'].split(',')).intersection(
                        set(subtitles.wanted_languages()))) >= len(subtitles.wanted_languages()):
                    continue
            elif which_subs in cur_result['subtitles'].split(','):
                continue

            tvid_prodid = TVidProdid({cur_result['tv_id']: cur_result['prod_id']})()
            if tvid_prodid not in ep_counts:
                ep_counts[tvid_prodid] = 1
            else:
                ep_counts[tvid_prodid] += 1

            show_names[tvid_prodid] = cur_result['show_name']
            if tvid_prodid not in sorted_show_ids:
                sorted_show_ids.append(tvid_prodid)

        t.show_names = show_names
        t.ep_counts = ep_counts
        t.sorted_show_ids = sorted_show_ids
        return t.respond()

    def download_subtitle_missed(self, **kwargs):

        if sickbeard.USE_SUBTITLES:
            to_download = {}

            # make a list of all shows and their associated args
            for arg in kwargs:
                tvid_prodid, what = arg.split('-')

                # we don't care about unchecked checkboxes
                if kwargs[arg] != 'on':
                    continue

                if tvid_prodid not in to_download:
                    to_download[tvid_prodid] = []

                to_download[tvid_prodid].append(what)

            for cur_tvid_prodid in to_download:
                # get a list of all the eps we want to download subtitles if 'all' is selected
                if 'all' in to_download[cur_tvid_prodid]:
                    my_db = db.DBConnection()
                    sql_result = my_db.select(
                        'SELECT season, episode'
                        ' FROM tv_episodes'
                        ' WHERE indexer = ? AND showid = ?'
                        ' AND season != 0 AND status LIKE \'%4\'',
                        TVidProdid(cur_tvid_prodid).list)
                    to_download[cur_tvid_prodid] = map_list(lambda x: '%sx%s' % (x['season'], x['episode']), sql_result)

                for epResult in to_download[cur_tvid_prodid]:
                    season, episode = epResult.split('x')

                    show_obj = helpers.find_show_by_id(cur_tvid_prodid)
                    _ = show_obj.get_episode(int(season), int(episode)).download_subtitles()

        self.redirect('/manage/subtitle-missed/')

    def backlog_show(self, tvid_prodid):

        show_obj = helpers.find_show_by_id(tvid_prodid)

        if show_obj:
            sickbeard.backlog_search_scheduler.action.search_backlog([show_obj])

        self.redirect('/manage/backlog-overview/')

    def backlog_overview(self):

        t = PageTemplate(web_handler=self, file='manage_backlogOverview.tmpl')
        t.submenu = self.manage_menu('Backlog')

        show_counts = {}
        show_cats = {}
        t.ep_sql_results = {}

        my_db = db.DBConnection(row_type='dict')
        sql_cmds = []
        show_objects = []
        for cur_show_obj in sickbeard.showList:
            sql_cmds.append([
                'SELECT season, episode, status, airdate, name'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' ORDER BY season DESC, episode DESC',
                [cur_show_obj.tvid, cur_show_obj.prodid]])
            show_objects.append(cur_show_obj)

        sql_results = my_db.mass_action(sql_cmds)

        for i, sql_result in enumerate(sql_results):
            ep_cats = {}
            ep_counts = {
                Overview.UNAIRED: 0, Overview.GOOD: 0, Overview.SKIPPED: 0,
                Overview.WANTED: 0, Overview.QUAL: 0, Overview.SNATCHED: 0}

            for cur_result in sql_result:
                if not sickbeard.SEARCH_UNAIRED and 1 == cur_result['airdate']:
                    continue
                ep_cat = show_objects[i].get_overview(int(cur_result['status']), split_snatch=True)
                if ep_cat in (Overview.WANTED, Overview.QUAL, Overview.SNATCHED_QUAL):
                    cur_result['backlog'] = True
                    if Overview.SNATCHED_QUAL == ep_cat:
                        ep_cat = Overview.SNATCHED
                else:
                    cur_result['backlog'] = False
                if ep_cat:
                    ep_cats['%sx%s' % (cur_result['season'], cur_result['episode'])] = ep_cat
                    ep_counts[ep_cat] += 1

            tvid_prodid = show_objects[i].tvid_prodid
            show_counts[tvid_prodid] = ep_counts
            show_cats[tvid_prodid] = ep_cats
            t.ep_sql_results[tvid_prodid] = sql_result

        t.show_counts = show_counts
        t.show_cats = show_cats
        t.backlog_active_providers = sickbeard.search_backlog.BacklogSearcher.providers_active(scheduled=False)

        return t.respond()

    def mass_edit(self, to_edit=None):

        t = PageTemplate(web_handler=self, file='manage_massEdit.tmpl')
        t.submenu = self.manage_menu()

        if not to_edit:
            return self.redirect('/manage/')

        show_ids = to_edit.split('|')
        show_list = []
        for cur_tvid_prodid in show_ids:
            show_obj = helpers.find_show_by_id(cur_tvid_prodid)
            if show_obj:
                show_list.append(show_obj)

        upgrade_once_all_same = True
        last_upgrade_once = None

        flatten_folders_all_same = True
        last_flatten_folders = None

        paused_all_same = True
        last_paused = None

        prune_all_same = True
        last_prune = None

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

        tvid_all_same = True
        last_tvid = None

        root_dir_list = []

        for cur_show_obj in show_list:

            # noinspection PyProtectedMember
            cur_root_dir = ek.ek(os.path.dirname, cur_show_obj._location)
            if cur_root_dir not in root_dir_list:
                root_dir_list.append(cur_root_dir)

            if upgrade_once_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_upgrade_once not in (None, cur_show_obj.upgrade_once):
                    upgrade_once_all_same = False
                else:
                    last_upgrade_once = cur_show_obj.upgrade_once

            # if we know they're not all the same then no point even bothering
            if paused_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_paused not in (None, cur_show_obj.paused):
                    paused_all_same = False
                else:
                    last_paused = cur_show_obj.paused

            if prune_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_prune not in (None, cur_show_obj.prune):
                    prune_all_same = False
                else:
                    last_prune = cur_show_obj.prune

            if tag_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_tag not in (None, cur_show_obj.tag):
                    tag_all_same = False
                else:
                    last_tag = cur_show_obj.tag

            if anime_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_anime not in (None, cur_show_obj.is_anime):
                    anime_all_same = False
                else:
                    last_anime = cur_show_obj.anime

            if flatten_folders_all_same:
                if last_flatten_folders not in (None, cur_show_obj.flatten_folders):
                    flatten_folders_all_same = False
                else:
                    last_flatten_folders = cur_show_obj.flatten_folders

            if quality_all_same:
                if last_quality not in (None, cur_show_obj.quality):
                    quality_all_same = False
                else:
                    last_quality = cur_show_obj.quality

            if subtitles_all_same:
                if last_subtitles not in (None, cur_show_obj.subtitles):
                    subtitles_all_same = False
                else:
                    last_subtitles = cur_show_obj.subtitles

            if scene_all_same:
                if last_scene not in (None, cur_show_obj.scene):
                    scene_all_same = False
                else:
                    last_scene = cur_show_obj.scene

            if sports_all_same:
                if last_sports not in (None, cur_show_obj.sports):
                    sports_all_same = False
                else:
                    last_sports = cur_show_obj.sports

            if air_by_date_all_same:
                if last_air_by_date not in (None, cur_show_obj.air_by_date):
                    air_by_date_all_same = False
                else:
                    last_air_by_date = cur_show_obj.air_by_date

            if tvid_all_same:
                if last_tvid not in (None, cur_show_obj.tvid):
                    tvid_all_same = False
                else:
                    last_tvid = cur_show_obj.tvid

        t.showList = to_edit
        t.upgrade_once_value = last_upgrade_once if upgrade_once_all_same else None
        t.paused_value = last_paused if paused_all_same else None
        t.prune_value = last_prune if prune_all_same else None
        t.tag_value = last_tag if tag_all_same else None
        t.anime_value = last_anime if anime_all_same else None
        t.flatten_folders_value = last_flatten_folders if flatten_folders_all_same else None
        t.quality_value = last_quality if quality_all_same else None
        t.subtitles_value = last_subtitles if subtitles_all_same else None
        t.scene_value = last_scene if scene_all_same else None
        t.sports_value = last_sports if sports_all_same else None
        t.air_by_date_value = last_air_by_date if air_by_date_all_same else None
        t.tvid_value = last_tvid if tvid_all_same else None
        t.root_dir_list = root_dir_list

        return t.respond()

    def mass_edit_submit(self, to_edit=None, upgrade_once=None, paused=None, anime=None, sports=None, scene=None,
                         flatten_folders=None, quality_preset=False, subs=None, air_by_date=None, any_qualities=None,
                         best_qualities=None, prune=None, tag=None, tvid=None, **kwargs):

        any_qualities = any_qualities if None is not any_qualities else []
        best_qualities = best_qualities if None is not best_qualities else []

        dir_map = {}
        for cur_arg in kwargs:
            if not cur_arg.startswith('orig_root_dir_'):
                continue
            which_index = cur_arg.replace('orig_root_dir_', '')
            end_dir = kwargs['new_root_dir_' + which_index]
            dir_map[kwargs[cur_arg]] = end_dir

        switch_tvid = []
        tvid = sg_helpers.try_int(tvid, tvid)

        show_ids = to_edit.split('|')
        errors = []
        for cur_tvid_prodid in show_ids:
            cur_errors = []
            show_obj = helpers.find_show_by_id(cur_tvid_prodid)
            if not show_obj:
                continue

            # noinspection PyProtectedMember
            cur_root_dir = ek.ek(os.path.dirname, show_obj._location)
            # noinspection PyProtectedMember
            cur_show_dir = ek.ek(os.path.basename, show_obj._location)
            if cur_root_dir in dir_map and cur_root_dir != dir_map[cur_root_dir]:
                new_show_dir = ek.ek(os.path.join, dir_map[cur_root_dir], cur_show_dir)
                if 'nt' != os.name and ':\\' in cur_show_dir:
                    # noinspection PyProtectedMember
                    cur_show_dir = show_obj._location.split('\\')[-1]
                    try:
                        base_dir = dir_map[cur_root_dir].rsplit(cur_show_dir)[0].rstrip('/')
                    except IndexError:
                        base_dir = dir_map[cur_root_dir]
                    new_show_dir = ek.ek(os.path.join, base_dir, cur_show_dir)
                # noinspection PyProtectedMember
                logger.log(u'For show %s changing dir from %s to %s' %
                           (show_obj.unique_name, show_obj._location, new_show_dir))
            else:
                # noinspection PyProtectedMember
                new_show_dir = show_obj._location

            if 'keep' == upgrade_once:
                new_upgrade_once = show_obj.upgrade_once
            else:
                new_upgrade_once = True if 'enable' == upgrade_once else False
            new_upgrade_once = 'on' if new_upgrade_once else 'off'

            if 'keep' == paused:
                new_paused = show_obj.paused
            else:
                new_paused = True if 'enable' == paused else False
            new_paused = 'on' if new_paused else 'off'

            new_prune = (config.minimax(prune, 0, 0, 9999), show_obj.prune)[prune in (None, '', 'keep')]

            if 'keep' == tag:
                new_tag = show_obj.tag
            else:
                new_tag = tag

            if 'keep' != tvid and tvid != show_obj.tvid:
                switch_tvid += ['%s-%s' % (cur_tvid_prodid, tvid)]

            if 'keep' == anime:
                new_anime = show_obj.anime
            else:
                new_anime = True if 'enable' == anime else False
            new_anime = 'on' if new_anime else 'off'

            if 'keep' == sports:
                new_sports = show_obj.sports
            else:
                new_sports = True if 'enable' == sports else False
            new_sports = 'on' if new_sports else 'off'

            if 'keep' == scene:
                new_scene = show_obj.is_scene
            else:
                new_scene = True if 'enable' == scene else False
            new_scene = 'on' if new_scene else 'off'

            if 'keep' == air_by_date:
                new_air_by_date = show_obj.air_by_date
            else:
                new_air_by_date = True if 'enable' == air_by_date else False
            new_air_by_date = 'on' if new_air_by_date else 'off'

            if 'keep' == flatten_folders:
                new_flatten_folders = show_obj.flatten_folders
            else:
                new_flatten_folders = True if 'enable' == flatten_folders else False
            new_flatten_folders = 'on' if new_flatten_folders else 'off'

            if 'keep' == subs:
                new_subtitles = show_obj.subtitles
            else:
                new_subtitles = True if 'enable' == subs else False

            new_subtitles = 'on' if new_subtitles else 'off'

            if 'keep' == quality_preset:
                any_qualities, best_qualities = Quality.splitQuality(show_obj.quality)
            elif int(quality_preset):
                best_qualities = []

            exceptions_list = []

            cur_errors += Home(self.application, self.request).edit_show(
                tvid_prodid=cur_tvid_prodid, location=new_show_dir,
                any_qualities=any_qualities, best_qualities=best_qualities, exceptions_list=exceptions_list,
                upgrade_once=new_upgrade_once, flatten_folders=new_flatten_folders, paused=new_paused,
                sports=new_sports, subs=new_subtitles, anime=new_anime, scene=new_scene, air_by_date=new_air_by_date,
                prune=new_prune, tag=new_tag, direct_call=True)

            if cur_errors:
                logger.log(u'Errors: ' + str(cur_errors), logger.ERROR)
                errors.append('<b>%s:</b>\n<ul>' % show_obj.unique_name + ' '.join(
                    ['<li>%s</li>' % error for error in cur_errors]) + '</ul>')

        if 0 < len(errors):
            ui.notifications.error('%d error%s while saving changes:' % (len(errors), '' if 1 == len(errors) else 's'),
                                   ' '.join(errors))

        if switch_tvid:
            self.mass_switch(to_switch='|'.join(switch_tvid))
            return self.redirect('/manage/show-tasks/')

        self.redirect('/manage/')

    def bulk_change(self, to_update='', to_refresh='', to_rename='',
                    to_subtitle='', to_delete='', to_remove='', **kwargs):

        to_change = dict({_tvid_prodid: helpers.find_show_by_id(_tvid_prodid)
                          for _tvid_prodid in
                          next(iter([_x.split('|') for _x in (to_update, to_refresh, to_rename, to_subtitle,
                                                              to_delete, to_remove) if _x]), '')})

        update, refresh, rename, subtitle, errors = [], [], [], [], []
        for cur_tvid_prodid, cur_show_obj in iteritems(to_change):

            if cur_tvid_prodid in to_delete:
                cur_show_obj.delete_show(True)

            elif cur_tvid_prodid in to_remove:
                cur_show_obj.delete_show()

            else:
                if cur_tvid_prodid in to_update:
                    try:
                        sickbeard.show_queue_scheduler.action.updateShow(cur_show_obj, True, True)
                        update.append(cur_show_obj.name)
                    except exceptions_helper.CantUpdateException as e:
                        errors.append('Unable to update show %s: %s' % (cur_show_obj.unique_name, ex(e)))

                elif cur_tvid_prodid in to_refresh:
                    try:
                        sickbeard.show_queue_scheduler.action.refreshShow(cur_show_obj)
                        refresh.append(cur_show_obj.name)
                    except exceptions_helper.CantRefreshException as e:
                        errors.append('Unable to refresh show %s: %s' % (cur_show_obj.unique_name, ex(e)))

                if cur_tvid_prodid in to_rename:
                    sickbeard.show_queue_scheduler.action.renameShowEpisodes(cur_show_obj)
                    rename.append(cur_show_obj.name)

                if sickbeard.USE_SUBTITLES and cur_tvid_prodid in to_subtitle:
                    sickbeard.show_queue_scheduler.action.download_subtitles(cur_show_obj)
                    subtitle.append(cur_show_obj.name)

        if len(errors):
            ui.notifications.error('Errors encountered', '<br>\n'.join(errors))

        if len(update + refresh + rename + subtitle):
            ui.notifications.message(
                'Queued the following actions:',
                ''.join(['%s:<br>* %s<br>' % (_to_do, '<br>'.join(_shows))
                         for (_to_do, _shows) in (('Updates', update), ('Refreshes', refresh),
                                                  ('Renames', rename), ('Subtitles', subtitle)) if len(_shows)]))
        self.redirect('/manage/')

    def failed_downloads(self, limit=100, to_remove=None):

        my_db = db.DBConnection('failed.db')

        sql = 'SELECT * FROM failed ORDER BY ROWID DESC'
        limit = helpers.try_int(limit, 100)
        if not limit:
            sql_result = my_db.select(sql)
        else:
            sql_result = my_db.select(sql + ' LIMIT ?', [limit + 1])

        to_remove = to_remove.split('|') if None is not to_remove else []

        for release in to_remove:
            item = re.sub('_{3,}', '%', release)
            my_db.action('DELETE FROM failed WHERE `release` like ?', [item])

        if to_remove:
            return self.redirect('/manage/failed-downloads/')

        t = PageTemplate(web_handler=self, file='manage_failedDownloads.tmpl')
        t.over_limit = limit and len(sql_result) > limit
        t.failed_results = t.over_limit and sql_result[0:-1] or sql_result
        t.limit = str(limit)
        t.submenu = self.manage_menu('Failed')

        return t.respond()

    @staticmethod
    def mass_switch(to_switch=None):
        """
        switch multiple given shows to a new tvinfo source
        shows are separated by |
        value for show is: current_tvid:current_prodid-new_tvid:new_prodid-force_id
        parts: new_prodid, force_id are optional
        without new_prodid the mapped id will be used
        with force set to '1' or 'true' the given new id will be used and NO verification for correct show will be done

        to_switch examples:
        to_switch=1:123-3|3:564-1|1:456-3:123|3:55-1:77-1|3:88-1-1

        :param to_switch:
        """
        if not to_switch:
            return json.dumps({'error': 'No list given'})

        shows = to_switch.split('|')
        sl, tv_sources, errors = [], sickbeard.TVInfoAPI().search_sources, []
        for show in shows:
            show_split = show.split('-')
            if 2 == len(show_split):
                old_show, new_show = show_split
                force_id = False
            else:
                old_show, new_show, force_id = show_split
                force_id = force_id in (1, True, '1', 'true', 'True')
            old_show_id = old_show.split(':')
            old_tvid, old_prodid = int(old_show_id[0]), int(old_show_id[1])
            new_show_id = new_show.split(':')
            new_tvid = int(new_show_id[0])
            if new_tvid not in tv_sources:
                logger.log('Skipping %s because target is not a valid source' % show, logger.WARNING)
                errors.append('Skipping %s because target is not a valid source' % show)
                continue
            try:
                show_obj = helpers.find_show_by_id({old_tvid: old_prodid})
            except (BaseException, Exception):
                show_obj = None
            if not show_obj:
                logger.log('Skipping %s because source is not a valid show' % show, logger.WARNING)
                errors.append('Skipping %s because source is not a valid show' % show)
                continue
            if 2 == len(new_show_id):
                new_prodid = int(new_show_id[1])
                try:
                    new_show_obj = helpers.find_show_by_id({new_tvid: new_prodid})
                except (BaseException, Exception):
                    new_show_obj = None
                if new_show_obj:
                    logger.log('Skipping %s because target show with that id already exists in db' % show,
                               logger.WARNING)
                    errors.append('Skipping %s because target show with that id already exists in db' % show)
                    continue
            else:
                new_prodid = None
            if show_obj.tvid == new_tvid and (not new_prodid or new_prodid == show_obj.prodid):
                logger.log('Skipping %s because target same as source' % show, logger.WARNING)
                errors.append('Skipping %s because target same as source' % show)
                continue
            try:
                sickbeard.show_queue_scheduler.action.switch_show(show_obj=show_obj, new_tvid=new_tvid,
                                                                  new_prodid=new_prodid, force_id=force_id)
            except (BaseException, Exception) as e:
                logger.log('Could not add show %s to switch queue: %s' % (show_obj.tvid_prodid, ex(e)), logger.WARNING)
                errors.append('Could not add show %s to switch queue: %s' % (show_obj.tvid_prodid, ex(e)))

        return json.dumps(({'result': 'success'}, {'errors': ', '.join(errors)})[0 < len(errors)])


class ManageSearch(Manage):

    def index(self):
        t = PageTemplate(web_handler=self, file='manage_manageSearches.tmpl')
        # t.backlog_pi = sickbeard.backlog_search_scheduler.action.get_progress_indicator()
        t.backlog_paused = sickbeard.search_queue_scheduler.action.is_backlog_paused()
        t.scheduled_backlog_active_providers = sickbeard.search_backlog.BacklogSearcher.providers_active(scheduled=True)
        t.backlog_running = sickbeard.search_queue_scheduler.action.is_backlog_in_progress()
        t.backlog_is_active = sickbeard.backlog_search_scheduler.action.am_running()
        t.standard_backlog_running = sickbeard.search_queue_scheduler.action.is_standard_backlog_in_progress()
        t.backlog_running_type = sickbeard.search_queue_scheduler.action.type_of_backlog_in_progress()
        t.recent_search_status = sickbeard.search_queue_scheduler.action.is_recentsearch_in_progress()
        t.find_propers_status = sickbeard.search_queue_scheduler.action.is_propersearch_in_progress()
        t.queue_length = sickbeard.search_queue_scheduler.action.queue_length()

        t.submenu = self.manage_menu('Search')

        return t.respond()

    @staticmethod
    def remove_from_search_queue(to_remove=None):
        if not to_remove:
            return json.dumps({'error': 'nothing to do'})
        to_remove = [int(r) for r in to_remove.split('|')]
        sickbeard.search_queue_scheduler.action.remove_from_queue(to_remove=to_remove)
        return json.dumps({'result': 'success'})

    @staticmethod
    def clear_search_queue(search_type=None):
        search_type = helpers.try_int(search_type, None)
        if not search_type:
            return json.dumps({'error': 'nothing to do'})
        sickbeard.search_queue_scheduler.action.clear_queue(action_types=search_type)
        return json.dumps({'result': 'success'})

    @staticmethod
    def retry_provider(provider=None):
        if not provider:
            return
        prov = [p for p in sickbeard.providerList + sickbeard.newznabProviderList if p.get_id() == provider]
        if not prov:
            return
        prov[0].retry_next()
        time.sleep(3)
        return

    def force_backlog(self):
        # force it to run the next time it looks
        if not sickbeard.search_queue_scheduler.action.is_standard_backlog_in_progress():
            sickbeard.backlog_search_scheduler.force_search(force_type=FORCED_BACKLOG)
            logger.log(u'Backlog search forced')
            ui.notifications.message('Backlog search started')

            time.sleep(5)
            self.redirect('/manage/search-tasks/')

    def force_search(self):

        # force it to run the next time it looks
        if not sickbeard.search_queue_scheduler.action.is_recentsearch_in_progress():
            result = sickbeard.recent_search_scheduler.forceRun()
            if result:
                logger.log(u'Recent search forced')
                ui.notifications.message('Recent search started')

        time.sleep(5)
        self.redirect('/manage/search-tasks/')

    def force_find_propers(self):

        # force it to run the next time it looks
        result = sickbeard.proper_finder_scheduler.forceRun()
        if result:
            logger.log(u'Find propers search forced')
            ui.notifications.message('Find propers search started')

        time.sleep(5)
        self.redirect('/manage/search-tasks/')

    def pause_backlog(self, paused=None):
        if '1' == paused:
            sickbeard.search_queue_scheduler.action.pause_backlog()
        else:
            sickbeard.search_queue_scheduler.action.unpause_backlog()

        time.sleep(5)
        self.redirect('/manage/search-tasks/')


class ShowTasks(Manage):

    def index(self):
        t = PageTemplate(web_handler=self, file='manage_showProcesses.tmpl')
        t.queue_length = sickbeard.show_queue_scheduler.action.queue_length()
        t.people_queue = sickbeard.people_queue_scheduler.action.queue_data()
        t.next_run = sickbeard.show_update_scheduler.lastRun.replace(
            hour=sickbeard.show_update_scheduler.start_time.hour)
        t.show_update_running = sickbeard.show_queue_scheduler.action.isShowUpdateRunning() \
            or sickbeard.show_update_scheduler.action.amActive

        my_db = db.DBConnection(row_type='dict')
        sql_result = my_db.select('SELECT n.indexer || ? ||  n.indexer_id AS tvid_prodid,'
                                  ' n.indexer AS tvid, n.indexer_id AS prodid,'
                                  ' n.last_success, n.fail_count, s.show_name'
                                  ' FROM tv_shows_not_found AS n'
                                  ' INNER JOIN tv_shows AS s'
                                  ' ON (n.indexer == s.indexer AND n.indexer_id == s.indexer_id)',
                                  [TVidProdid.glue])
        for cur_result in sql_result:
            date = helpers.try_int(cur_result['last_success'])
            cur_result['last_success'] = ('never', SGDatetime.fromordinal(date).sbfdate())[1 < date]
            cur_result['ignore_warning'] = 0 > cur_result['fail_count']

        defunct_indexer = [i for i in sickbeard.TVInfoAPI().all_sources if sickbeard.TVInfoAPI(i).config.get('defunct')]
        defunct_sql_result = None
        if defunct_indexer:
            defunct_sql_result = my_db.select('SELECT indexer || ? || indexer_id AS tvid_prodid, show_name'
                                              ' FROM tv_shows'
                                              ' WHERE indexer IN (%s)' % ','.join(['?'] * len(defunct_indexer)),
                                              [TVidProdid.glue] + defunct_indexer)
        t.defunct_indexer = defunct_sql_result
        t.not_found_shows = sql_result

        failed_result = my_db.select('SELECT * FROM tv_src_switch WHERE status != ?', [TVSWITCH_NORMAL])
        t.failed_switch = []
        for f in failed_result:
            try:
                show_obj = helpers.find_show_by_id({f['old_indexer']: f['old_indexer_id']})
            except (BaseException, Exception):
                show_obj = None
            new_failed = {'tvid': f['old_indexer'], 'prodid': f['old_indexer_id'], 'new_tvid': f['new_indexer'],
                          'new_prodid': f['new_indexer_id'],
                          'status': tvswitch_names.get(f['status'], 'unknown %s' % f['status']), 'show_obj': show_obj,
                          'uid': f['uid']}
            t.failed_switch.append(new_failed)

        t.submenu = self.manage_menu('Show')

        return t.respond()

    @staticmethod
    def remove_from_show_queue(to_remove=None, force=False):
        if not to_remove:
            return json.dumps({'error': 'nothing to do'})
        force = force in (1, '1', 'true', 'True', True)
        to_remove = [int(r) for r in to_remove.split('|')]
        sickbeard.show_queue_scheduler.action.remove_from_queue(to_remove=to_remove, force=force)
        return json.dumps({'result': 'success'})

    @staticmethod
    def remove_from_people_queue(to_remove=None):
        if not to_remove:
            return json.dumps({'error': 'nothing to do'})
        to_remove = [int(r) for r in to_remove.split('|')]
        sickbeard.people_queue_scheduler.action.remove_from_queue(to_remove=to_remove)
        return json.dumps({'result': 'success'})

    @staticmethod
    def clear_show_queue(show_type=None):
        show_type = helpers.try_int(show_type, None)
        if not show_type:
            return json.dumps({'error': 'nothing to do'})
        if show_type in [sickbeard.show_queue.ShowQueueActions.UPDATE,
                         sickbeard.show_queue.ShowQueueActions.FORCEUPDATE,
                         sickbeard.show_queue.ShowQueueActions.WEBFORCEUPDATE]:
            show_type = [sickbeard.show_queue.ShowQueueActions.UPDATE,
                         sickbeard.show_queue.ShowQueueActions.FORCEUPDATE,
                         sickbeard.show_queue.ShowQueueActions.WEBFORCEUPDATE]
        sickbeard.show_queue_scheduler.action.clear_queue(action_types=show_type)
        return json.dumps({'result': 'success'})

    @staticmethod
    def clear_people_queue(people_type=None):
        people_type = helpers.try_int(people_type, None)
        if not people_type:
            return json.dumps({'error': 'nothing to do'})
        sickbeard.people_queue_scheduler.action.clear_queue(action_types=people_type)
        return json.dumps({'result': 'success'})

    def force_show_update(self):

        result = sickbeard.show_update_scheduler.forceRun()
        if result:
            logger.log(u'Show Update forced')
            ui.notifications.message('Forced Show Update started')

        time.sleep(5)
        self.redirect('/manage/show-tasks/')

    @staticmethod
    def switch_ignore_warning(**kwargs):

        for cur_tvid_prodid, state in iteritems(kwargs):
            show_obj = helpers.find_show_by_id(cur_tvid_prodid)
            if show_obj:
                change = -1
                if 'true' == state:
                    if 0 > show_obj.not_found_count:
                        change = 1
                elif 0 < show_obj.not_found_count:
                    change = 1
                show_obj.not_found_count *= change

        return json.dumps({})


class History(MainHandler):
    flagname_help_watched = 'ui_history_help_watched_supported_clients'
    flagname_wdf = 'ui_history_watched_delete_files'
    flagname_wdr = 'ui_history_watched_delete_records'

    def toggle_help(self):
        db.DBConnection().toggle_flag(self.flagname_help_watched)

    @classmethod
    def menu_tab(cls, limit):

        result = []
        my_db = db.DBConnection(row_type='dict')  # type: db.DBConnection
        history_detailed, history_compact = cls.query_history(my_db)
        dedupe = set()
        for item in history_compact:
            if item.get('tvid_prodid') not in dedupe:
                dedupe.add(item.get('tvid_prodid'))
                item['show_name'] = abbr_showname(item['show_name'])
                result += [item]
                if limit == len(result):
                    break
        return result

    @classmethod
    def query_history(cls, my_db, limit=100):
        # type: (db.DBConnection, int) -> Tuple[List[dict], List[dict]]
        """Query db for historical data

        :param my_db: connection should be instantiated with row_type='dict'
        :param limit: number of db rows to fetch
        :return: two data sets, detailed and compact
        """

        sql = 'SELECT h.*, show_name, s.indexer || ? || s.indexer_id AS tvid_prodid' \
              ' FROM history h, tv_shows s' \
              ' WHERE h.indexer=s.indexer AND h.showid=s.indexer_id' \
              ' AND h.hide = 0' \
              ' ORDER BY date DESC' \
              '%s' % (' LIMIT %s' % limit, '')['0' == limit]
        sql_result = my_db.select(sql, [TVidProdid.glue])

        compact = []

        for cur_result in sql_result:

            action = dict(time=cur_result['date'], action=cur_result['action'],
                          provider=cur_result['provider'], resource=cur_result['resource'])

            if not any([(record['show_id'] == cur_result['showid']
                         and record['indexer'] == cur_result['indexer']
                         and record['season'] == cur_result['season']
                         and record['episode'] == cur_result['episode']
                         and record['quality'] == cur_result['quality']) for record in compact]):
                show_obj = helpers.find_show_by_id({cur_result['indexer']: cur_result['showid']}, no_mapped_ids=False,
                                                   no_exceptions=True)
                cur_res = dict(show_id=cur_result['showid'], indexer=cur_result['indexer'],
                               tvid_prodid=cur_result['tvid_prodid'],
                               show_name=(show_obj and show_obj.unique_name) or cur_result['show_name'],
                               season=cur_result['season'], episode=cur_result['episode'],
                               quality=cur_result['quality'], resource=cur_result['resource'], actions=[])

                cur_res['actions'].append(action)
                cur_res['actions'].sort(key=lambda _x: _x['time'])

                compact.append(cur_res)
            else:
                index = [i for i, record in enumerate(compact)
                         if record['show_id'] == cur_result['showid']
                         and record['season'] == cur_result['season']
                         and record['episode'] == cur_result['episode']
                         and record['quality'] == cur_result['quality']][0]

                cur_res = compact[index]

                cur_res['actions'].append(action)
                cur_res['actions'].sort(key=lambda _x: _x['time'], reverse=True)

        return sql_result, compact

    def index(self, limit=100, layout=None):

        t = PageTemplate(web_handler=self, file='history.tmpl')
        t.limit = limit

        if 'provider_failures' == layout:  # layout renamed
            layout = 'connect_failures'
        if layout in ('compact', 'detailed', 'compact_watched', 'detailed_watched', 'connect_failures'):
            sickbeard.HISTORY_LAYOUT = layout

        my_db = db.DBConnection(row_type='dict')

        result_sets = []
        if sickbeard.HISTORY_LAYOUT in ('compact', 'detailed'):

            sql_result, compact = self.query_history(my_db, limit)

            t.compact_results = compact
            t.history_results = sql_result
            t.submenu = [{'title': 'Clear History', 'path': 'history/clear-history'},
                         {'title': 'Trim History', 'path': 'history/trim-history'}]

            result_sets = ['compact_results', 'history_results']

        elif 'watched' in sickbeard.HISTORY_LAYOUT:

            t.hide_watched_help = my_db.has_flag(self.flagname_help_watched)

            t.results = my_db.select(
                'SELECT tvs.show_name, '
                ' tve.indexer AS tvid, tve.showid AS prodid,'
                ' tve.indexer || ? || tve.showid AS tvid_prodid,'
                ' tve.season, tve.episode, tve.status, tve.file_size,'
                ' tvew.rowid, tvew.tvep_id, tvew.label, tvew.played, tvew.date_watched,'
                ' tvew.status AS status_w, tvew.location, tvew.file_size AS file_size_w, tvew.hide'
                ' FROM [tv_shows] AS tvs'
                ' INNER JOIN [tv_episodes] AS tve ON (tvs.indexer = tve.indexer AND tvs.indexer_id = tve.showid)'
                ' INNER JOIN [tv_episodes_watched] AS tvew ON (tve.episode_id = tvew.tvep_id)'
                ' WHERE 0 = hide'
                ' ORDER BY tvew.date_watched DESC'
                '%s' % (' LIMIT %s' % limit, '')['0' == limit],
                [TVidProdid.glue])

            mru_count = {}
            t.mru_row_ids = []
            for r in t.results:
                r['deleted'] = False
                no_file = not helpers.get_size(r['location'])
                if no_file or not r['file_size']:  # if not filesize, possible file recovered so restore known size
                    if no_file:
                        # file no longer available, can be due to upgrade, so use known details
                        r['deleted'] = True
                    r['status'] = r['status_w']
                    r['file_size'] = r['file_size_w']

                r['status'], r['quality'] = Quality.splitCompositeStatus(helpers.try_int(r['status']))
                r['season'], r['episode'] = '%02i' % r['season'], '%02i' % r['episode']
                if r['tvep_id'] not in mru_count:
                    # depends on SELECT ORDER BY date_watched DESC to determine mru_count
                    mru_count.update({r['tvep_id']: r['played']})
                    t.mru_row_ids += [r['rowid']]
                r['mru_count'] = mru_count[r['tvep_id']]

            result_sets = ['results']

            # restore state of delete dialog
            t.last_delete_files = my_db.has_flag(self.flagname_wdf)
            t.last_delete_records = my_db.has_flag(self.flagname_wdr)

        elif 'stats' in sickbeard.HISTORY_LAYOUT:

            prov_list = [p.name for p in (sickbeard.providerList
                                          + sickbeard.newznabProviderList
                                          + sickbeard.torrentRssProviderList)]
            # noinspection SqlResolve
            sql = 'SELECT COUNT(1) AS count,' \
                  ' MIN(DISTINCT date) AS earliest,' \
                  ' MAX(DISTINCT date) AS latest,' \
                  ' provider ' \
                  'FROM ' \
                  '(SELECT * FROM history h, tv_shows s' \
                  ' WHERE h.showid=s.indexer_id' \
                  ' AND h.provider in ("%s")' % '","'.join(prov_list) + \
                  ' AND h.action in ("%s")' % '","'.join([str(x) for x in Quality.SNATCHED_ANY]) + \
                  ' AND h.hide = 0' \
                  ' ORDER BY date DESC%s)' % (' LIMIT %s' % limit, '')['0' == limit] + \
                  ' GROUP BY provider' \
                  ' ORDER BY count DESC'
            t.stat_results = my_db.select(sql)

            t.earliest = 0
            t.latest = 0
            for r in t.stat_results:
                if r['latest'] > t.latest or not t.latest:
                    t.latest = r['latest']
                if r['earliest'] < t.earliest or not t.earliest:
                    t.earliest = r['earliest']

        elif 'failures' in sickbeard.HISTORY_LAYOUT:

            t.provider_fail_stats = filter_list(lambda stat: len(stat['fails']), [
                dict(name=p.name, id=p.get_id(), active=p.is_active(), prov_img=p.image_name(),
                     prov_id=p.get_id(),  # 2020.03.17 legacy var, remove at future date
                     fails=p.fails.fails_sorted, next_try=p.get_next_try_time,
                     has_limit=getattr(p, 'has_limit', False), tmr_limit_time=p.tmr_limit_time)
                for p in sickbeard.providerList + sickbeard.newznabProviderList])

            t.provider_fail_cnt = len([p for p in t.provider_fail_stats if len(p['fails'])])
            t.provider_fails = t.provider_fail_cnt  # 2020.03.17 legacy var, remove at future date

            t.provider_fail_stats = sorted([item for item in t.provider_fail_stats],
                                           key=lambda y: y.get('fails')[0].get('timestamp'),
                                           reverse=True)
            t.provider_fail_stats = sorted([item for item in t.provider_fail_stats],
                                           key=lambda y: y.get('next_try') or datetime.timedelta(weeks=65535),
                                           reverse=False)

            def img(_item, as_class=False):
                # type: (AnyStr, bool) -> Optional[AnyStr]
                """
                Return an image src, image class, or None based on a recognised identifier

                :param _item: to search for a known domain identifier
                :param as_class: wether a search should return an image (by default) or class
                :return: image src, image class, or None if unknown identifier
                """
                for identifier, result in (
                    (('fanart', 'fanart.png'), ('imdb', 'imdb16.png'), ('metac', 'metac16.png'),
                     ('next-episode', 'nextepisode16.png'),
                     ('predb', 'predb16.png'), ('srrdb', 'srrdb16.png'),
                     ('thexem', 'xem.png'), ('tmdb', 'tmdb16.png'), ('trakt', 'trakt16.png'),
                     ('tvdb', 'thetvdb16.png'), ('tvmaze', 'tvmaze16.png')),
                    (('anidb', 'img-anime-16 square-16'), ('github', 'icon16-github'),
                     ('emby', 'sgicon-emby'), ('plex', 'sgicon-plex'))
                )[as_class]:
                    if identifier in _item:
                        return result

            with sg_helpers.DOMAIN_FAILURES.lock:
                t.domain_fail_stats = filter_list(lambda stat: len(stat['fails']), [
                    dict(name=k, id=sickbeard.GenericProvider.make_id(k), img=img(k), cls=img(k, True),
                         fails=v.fails_sorted, next_try=v.get_next_try_time,
                         has_limit=getattr(v, 'has_limit', False), tmr_limit_time=v.tmr_limit_time)
                    for k, v in iteritems(sg_helpers.DOMAIN_FAILURES.domain_list)])

                t.domain_fail_cnt = len([d for d in t.domain_fail_stats if len(d['fails'])])

                t.domain_fail_stats = sorted([item for item in t.domain_fail_stats],
                                             key=lambda y: y.get('fails')[0].get('timestamp'),
                                             reverse=True)
                t.domain_fail_stats = sorted([item for item in t.domain_fail_stats],
                                             key=lambda y: y.get('next_try') or datetime.timedelta(weeks=65535),
                                             reverse=False)

        article_match = r'^((?:A(?!\s+to)n?)|The)\s+(.*)$'
        for rs in [getattr(t, name, []) for name in result_sets]:
            for r in rs:
                r['name1'] = ''
                r['name2'] = r['data_name'] = r['show_name']
                if not sickbeard.SORT_ARTICLE:
                    try:
                        r['name1'], r['name2'] = re.findall(article_match, r['show_name'])[0]
                        r['data_name'] = r['name2']
                    except (BaseException, Exception):
                        pass

        return t.respond()

    @staticmethod
    def check_site(site_name=''):

        site_url = dict(
            tvdb='api.thetvdb.com', thexem='thexem.info', github='github.com'
        ).get(site_name.replace('check_', ''))

        result = {}

        if site_url:
            import requests
            down_url = 'www.isitdownrightnow.com'
            proto = 'https'
            try:
                requests.head('%s://%s' % (proto, down_url), timeout=5)
            except (BaseException, Exception):
                proto = 'http'
                try:
                    requests.head('%s://%s' % (proto, down_url), timeout=5)
                except (BaseException, Exception):
                    return json.dumps(result)

            resp = helpers.get_url('%s://%s/check.php?domain=%s' % (proto, down_url, site_url))
            if resp:
                check = resp.lower()
                day = re.findall(r'(\d+)\s*day', check)
                hr = re.findall(r'(\d+)\s*hour', check)
                mn = re.findall(r'(\d+)\s*min', check)
                if any([day, hr, mn]):
                    period = ', '.join(
                        (day and ['%sd' % day[0]] or day)
                        + (hr and ['%sh' % hr[0]] or hr)
                        + (mn and ['%sm' % mn[0]] or mn))
                else:
                    try:
                        period = re.findall('[^>]>([^<]+)ago', check)[0].strip()
                    except (BaseException, Exception):
                        try:
                            period = re.findall('[^>]>([^<]+week)', check)[0]
                        except (BaseException, Exception):
                            period = 'quite some time'

                result = {('last_down', 'down_for')['up' not in check and 'down for' in check]: period}

        return json.dumps(result)

    def clear_history(self):

        my_db = db.DBConnection()
        # noinspection SqlConstantCondition
        my_db.action('UPDATE history SET hide = ? WHERE hide = 0', [1])

        ui.notifications.message('History cleared')
        self.redirect('/history/')

    def trim_history(self):

        my_db = db.DBConnection()
        my_db.action('UPDATE history SET hide = ? WHERE date < ' + str(
            (datetime.datetime.now() - datetime.timedelta(days=30)).strftime(history.dateFormat)), [1])

        ui.notifications.message('Removed history entries greater than 30 days old')
        self.redirect('/history/')

    @staticmethod
    def retry_domain(domain=None):

        if domain in sg_helpers.DOMAIN_FAILURES.domain_list:
            sg_helpers.DOMAIN_FAILURES.domain_list[domain].retry_next()
            time.sleep(3)

    @staticmethod
    def update_watched_state_emby():

        import sickbeard.notifiers.emby as emby

        client = emby.EmbyNotifier()
        hosts, keys, message = client.check_config(sickbeard.EMBY_HOST, sickbeard.EMBY_APIKEY)

        if sickbeard.USE_EMBY and hosts:
            logger.log('Updating Emby watched episode states', logger.DEBUG)

            rd = sickbeard.ROOT_DIRS.split('|')[1:] \
                + [x.split('=')[0] for x in sickbeard.EMBY_PARENT_MAPS.split(',') if any(x)]
            rootpaths = sorted(
                ['%s%s' % (ek.ek(os.path.splitdrive, x)[1], os.path.sep) for x in rd], key=len, reverse=True)
            rootdirs = sorted([x for x in rd], key=len, reverse=True)
            headers = {'Content-type': 'application/json'}
            states = {}
            idx = 0
            mapped = 0
            mapping = None
            maps = [x.split('=') for x in sickbeard.EMBY_PARENT_MAPS.split(',') if any(x)]
            args = dict(params=dict(format='json'), timeout=10, parse_json=True, failure_monitor=False)
            for i, cur_host in enumerate(hosts):
                # noinspection HttpUrlsUsage
                base_url = 'http://%s/emby' % cur_host
                headers.update({'X-MediaBrowser-Token': keys[i]})

                users = helpers.get_url(base_url + '/Users', headers=headers, **args)

                for user_id in users and [u.get('Id') for u in users if u.get('Id')] or []:
                    user_url = '%s/Users/%s' % (base_url, user_id)
                    user = helpers.get_url(user_url, headers=headers, **args)

                    folder_ids = user.get('Policy', {}).get('EnabledFolders') or []
                    if not folder_ids and user.get('Policy', {}).get('EnableAllFolders'):
                        folders = helpers.get_url('%s/Library/MediaFolders' % base_url, headers=headers, **args)
                        folder_ids = [_f.get('Id') for _f in folders.get('Items', {}) if _f.get('IsFolder')
                                      and 'tvshows' == _f.get('CollectionType', '') and _f.get('Id')]

                    for folder_id in folder_ids:
                        folder = helpers.get_url('%s/Items/%s' % (user_url, folder_id), headers=headers,
                                                 mute_http_error=True, **args)

                        if not folder or 'tvshows' != folder.get('CollectionType', ''):
                            continue

                        items = helpers.get_url('%s/Items' % user_url, failure_monitor=False, headers=headers,
                                                params=dict(SortBy='DatePlayed,SeriesSortName,SortName',
                                                            SortOrder='Descending',
                                                            IncludeItemTypes='Episode',
                                                            Recursive='true',
                                                            Fields='Path,UserData',
                                                            IsMissing='false',
                                                            IsVirtualUnaired='false',
                                                            StartIndex='0', Limit='100',
                                                            ParentId=folder_id,
                                                            Filters='IsPlayed',
                                                            format='json'), timeout=10, parse_json=True)
                        for d in filter_iter(lambda item: 'Episode' == item.get('Type', ''), items.get('Items')):
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
                                    media_id=d.get('Id', ''),
                                    played=(d.get('UserData', {}).get('PlayedPercentage') or
                                            (d.get('UserData', {}).get('Played') and
                                             d.get('UserData', {}).get('PlayCount') * 100) or 0),
                                    label='%s%s{Emby}' % (user.get('Name', ''), bool(user.get('Name')) and ' ' or ''),
                                    date_watched=SGDatetime.timestamp_far(
                                        dateutil.parser.parse(d.get('UserData', {}).get('LastPlayedDate'))))

                                for m in maps:
                                    result, change = helpers.path_mapper(m[0], m[1], states[idx]['path_file'])
                                    if change:
                                        if not mapping:
                                            mapping = (states[idx]['path_file'], result)
                                        mapped += 1
                                        states[idx]['path_file'] = result
                                        break

                                idx += 1
                            except (BaseException, Exception):
                                continue
            if mapping:
                logger.log('Folder mappings used, the first of %s is [%s] in Emby is [%s] in SickGear' %
                           (mapped, mapping[0], mapping[1]), logger.DEBUG)

            if states:
                # Prune user removed items that are no longer being returned by API
                media_paths = map_list(lambda arg: ek.ek(os.path.basename, arg[1]['path_file']), iteritems(states))
                sql = 'FROM tv_episodes_watched WHERE hide=1 AND label LIKE "%%{Emby}"'
                my_db = db.DBConnection(row_type='dict')
                files = my_db.select('SELECT location %s' % sql)
                for i in filter_iter(lambda f: ek.ek(os.path.basename, f['location']) not in media_paths, files):
                    loc = i.get('location')
                    if loc:
                        my_db.select('DELETE %s AND location="%s"' % (sql, loc))

                MainHandler.update_watched_state(states, False)

            logger.log('Finished updating Emby watched episode states')

    @staticmethod
    def update_watched_state_plex():

        hosts = [x.strip().lower() for x in sickbeard.PLEX_SERVER_HOST.split(',')]
        if sickbeard.USE_PLEX and hosts:
            logger.log('Updating Plex watched episode states', logger.DEBUG)

            from lib.plex import Plex

            plex = Plex(dict(username=sickbeard.PLEX_USERNAME, password=sickbeard.PLEX_PASSWORD,
                             section_filter_path=sickbeard.ROOT_DIRS.split('|')[1:] +
                             [x.split('=')[0] for x in sickbeard.PLEX_PARENT_MAPS.split(',') if any(x)]))

            states = {}
            idx = 0
            played = 0
            mapped = 0
            mapping = None
            maps = [x.split('=') for x in sickbeard.PLEX_PARENT_MAPS.split(',') if any(x)]
            for cur_host in hosts:
                # noinspection HttpUrlsUsage
                parts = re.search(r'(.*):(\d+)$', urlparse('http://' + re.sub(r'^\w+://', '', cur_host)).netloc)
                if not parts:
                    logger.log('Skipping host not in min. host:port format : %s' % cur_host, logger.WARNING)
                elif parts.group(1):
                    plex.plex_host = parts.group(1)
                    if None is not parts.group(2):
                        plex.plex_port = parts.group(2)

                    plex.fetch_show_states()

                    for k, v in iteritems(plex.show_states):
                        if 0 < v.get('played') or 0:
                            played += 1
                            states[idx] = v
                            states[idx]['label'] = '%s%s{Plex}' % (v['label'], bool(v['label']) and ' ' or '')

                            for m in maps:
                                result, change = helpers.path_mapper(m[0], m[1], states[idx]['path_file'])
                                if change:
                                    if not mapping:
                                        mapping = (states[idx]['path_file'], result)
                                    mapped += 1
                                    states[idx]['path_file'] = result
                                    break

                            idx += 1

                    logger.log('Fetched %s of %s played for host : %s' % (len(plex.show_states), played, cur_host),
                               logger.DEBUG)
            if mapping:
                logger.log('Folder mappings used, the first of %s is [%s] in Plex is [%s] in SickGear' %
                           (mapped, mapping[0], mapping[1]), logger.DEBUG)

            if states:
                # Prune user removed items that are no longer being returned by API
                media_paths = map_list(lambda arg: ek.ek(os.path.basename, arg[1]['path_file']), iteritems(states))
                sql = 'FROM tv_episodes_watched WHERE hide=1 AND label LIKE "%%{Plex}"'
                my_db = db.DBConnection(row_type='dict')
                files = my_db.select('SELECT location %s' % sql)
                for i in filter_iter(lambda f: ek.ek(os.path.basename, f['location']) not in media_paths, files):
                    loc = i.get('location')
                    if loc:
                        my_db.select('DELETE %s AND location="%s"' % (sql, loc))

                MainHandler.update_watched_state(states, False)

            logger.log('Finished updating Plex watched episode states')

    def watched(self, tvew_id=None, files=None, records=None):

        my_db = db.DBConnection(row_type='dict')

        # remember state of dialog
        my_db.set_flag(self.flagname_wdf, files)
        my_db.set_flag(self.flagname_wdr, records)

        ids = tvew_id.split('|')
        if not (ids and any([files, records])):
            return

        row_show_ids = {}
        for show_detail in ids:
            rowid, tvid, prodid = show_detail.split('-')
            row_show_ids.update({int(rowid): {int(tvid): int(prodid)}})

        sql_result = my_db.select(
            'SELECT rowid, tvep_id, label, location'
            ' FROM [tv_episodes_watched] WHERE `rowid` in (%s)' % ','.join([str(k) for k in row_show_ids])
        )

        h_records = []
        removed = []
        deleted = {}
        attempted = []
        refresh = []
        for cur_result in sql_result:
            if files and cur_result['location'] not in attempted and 0 < helpers.get_size(cur_result['location']) \
                    and ek.ek(os.path.isfile, cur_result['location']):
                # locations repeat with watch events but attempt to delete once
                attempted += [cur_result['location']]

                result = helpers.remove_file(cur_result['location'])
                if result:
                    logger.log(u'%s file %s' % (result, cur_result['location']))

                    deleted.update({cur_result['tvep_id']: row_show_ids[cur_result['rowid']]})
                    if row_show_ids[cur_result['rowid']] not in refresh:
                        # schedule a show for one refresh after deleting an arbitrary number of locations
                        refresh += [row_show_ids[cur_result['rowid']]]

            if records:
                if not cur_result['label'].endswith('{Emby}') and not cur_result['label'].endswith('{Plex}'):
                    r_del = my_db.action('DELETE FROM [tv_episodes_watched] WHERE `rowid` == ?',
                                         [cur_result['rowid']])
                    if 1 == r_del.rowcount:
                        h_records += ['%s-%s-%s' % (cur_result['rowid'], k, v)
                                      for k, v in iteritems(row_show_ids[cur_result['rowid']])]
                else:
                    r_del = my_db.action('UPDATE [tv_episodes_watched] SET hide=1 WHERE `rowid` == ?',
                                         [cur_result['rowid']])
                    if 1 == r_del.rowcount:
                        removed += ['%s-%s-%s' % (cur_result['rowid'], k, v)
                                    for k, v in iteritems(row_show_ids[cur_result['rowid']])]

        updating = False
        for epid, tvid_prodid_dict in iteritems(deleted):
            sql_result = my_db.select('SELECT season, episode FROM [tv_episodes] WHERE `episode_id` = %s' % epid)
            for cur_result in sql_result:
                show_obj = helpers.find_show_by_id(tvid_prodid_dict)
                ep_obj = show_obj.get_episode(cur_result['season'], cur_result['episode'])
                for n in filter_iter(lambda x: x.name.lower() in ('emby', 'kodi', 'plex'),
                                     notifiers.NotifierFactory().get_enabled()):
                    if 'PLEX' == n.name:
                        if updating:
                            continue
                        updating = True
                    n.update_library(show_obj=show_obj, show_name=show_obj.name, ep_obj=ep_obj)

        for tvid_prodid_dict in refresh:
            try:
                sickbeard.show_queue_scheduler.action.refreshShow(
                    helpers.find_show_by_id(tvid_prodid_dict))
            except (BaseException, Exception):
                pass

        if not any([removed, h_records, len(deleted)]):
            msg = 'No items removed and no files deleted'
        else:
            msg = []
            if deleted:
                msg += ['%s %s media file%s' % (
                    ('Permanently deleted', 'Trashed')[sickbeard.TRASH_REMOVE_SHOW],
                    len(deleted), helpers.maybe_plural(deleted))]
            elif removed:
                msg += ['Removed %s watched history item%s' % (len(removed), helpers.maybe_plural(removed))]
            else:
                msg += ['Deleted %s watched history item%s' % (len(h_records), helpers.maybe_plural(h_records))]
            msg = '<br>'.join(msg)

        ui.notifications.message('History : Watch', msg)

        return json.dumps(dict(success=h_records))


class Config(MainHandler):

    @staticmethod
    def config_menu(exclude='n/a'):
        menu = [
            {'title': 'General', 'path': 'config/general/'},
            {'title': 'Media Providers', 'path': 'config/providers/'},
            {'title': 'Search', 'path': 'config/search/'},
            {'title': 'Subtitles', 'path': 'config/subtitles/'},
            {'title': 'Media Process', 'path': 'config/media-process/'},
            {'title': 'Notifications', 'path': 'config/notifications/'},
            {'title': 'Anime', 'path': 'config/anime/'},
        ]
        return [x for x in menu if exclude not in x['title']]

    def index(self):
        t = PageTemplate(web_handler=self, file='config.tmpl')
        t.submenu = self.config_menu()

        try:
            with open(ek.ek(os.path.join, sickbeard.PROG_DIR, 'CHANGES.md')) as fh:
                t.version = re.findall(r'###[^0-9]+([0-9]+\.[0-9]+\.[0-9]+)', fh.readline())[0]
        except (BaseException, Exception):
            t.version = ''

        current_file = zoneinfo.ZONEFILENAME
        t.tz_fallback = False
        t.tz_version = None
        try:
            if None is not current_file:
                current_file = ek.ek(os.path.basename, current_file)
                zonefile = real_path(ek.ek(os.path.join, sickbeard.ZONEINFO_DIR, current_file))
                if not ek.ek(os.path.isfile, zonefile):
                    t.tz_fallback = True
                    zonefile = ek.ek(os.path.join, ek.ek(os.path.dirname, zoneinfo.__file__), current_file)
                if ek.ek(os.path.isfile, zonefile):
                    t.tz_version = zoneinfo.ZoneInfoFile(zoneinfo.getzoneinfofile_stream()).metadata['tzversion']
        except (BaseException, Exception):
            pass

        t.backup_db_path = sickbeard.BACKUP_DB_MAX_COUNT and \
            (sickbeard.BACKUP_DB_PATH or ek.ek(os.path.join, sickbeard.DATA_DIR, 'backup')) or 'Disabled'

        return t.respond()


class ConfigGeneral(Config):

    def index(self):

        t = PageTemplate(web_handler=self, file='config_general.tmpl')
        t.submenu = self.config_menu('General')
        t.show_tags = ', '.join(sickbeard.SHOW_TAGS)
        t.infosrc = dict([(i, sickbeard.TVInfoAPI().sources[i]) for i in sickbeard.TVInfoAPI().sources
                          if sickbeard.TVInfoAPI(i).config['active']])
        t.request_host = helpers.xhtml_escape(self.request.host_name, False)
        api_keys = '|||'.join([':::'.join(a) for a in sickbeard.API_KEYS])
        t.api_keys = api_keys and sickbeard.API_KEYS or []
        return t.respond()

    @staticmethod
    def update_alt():
        """ Load scene exceptions """

        changed_exceptions, cnt_updated_numbers, min_remain_iv = scene_exceptions.retrieve_exceptions()

        return json.dumps(dict(names=int(changed_exceptions), numbers=cnt_updated_numbers, min_remain_iv=min_remain_iv))

    @staticmethod
    def export_alt(tvid_prodid=None):
        """ Return alternative release names and numbering as json text"""

        # alternative release names and numbers
        alt_names = scene_exceptions.get_all_scene_exceptions(tvid_prodid)
        alt_numbers = get_scene_numbering_for_show(*TVidProdid(tvid_prodid).tuple)  # arbitrary order
        ui_output = 'No alternative names or numbers to export'

        # combine all possible season numbers into a sorted desc list
        seasons = sorted(set(list(set([s for (s, e) in alt_numbers])) + [s for s in alt_names]), reverse=True)
        if seasons:
            if -1 == seasons[-1]:
                seasons = [-1] + seasons[0:-1]  # bubble -1

            # prepare a seasonal ordered dict for output
            alts = ordered_dict([(season, {}) for season in seasons])

            # add original show name
            show_obj = sickbeard.helpers.find_show_by_id(tvid_prodid, no_mapped_ids=True)
            first_key = next(iteritems(alts))[0]
            alts[first_key].update(dict({'#': show_obj.name}))

            # process alternative release names
            for (season, names) in iteritems(alt_names):
                alts[season].update(dict(n=names))

            # process alternative release numbers
            for_target_group = {}
            # uses a sorted list of (for seasons, for episodes) as a method
            # to group (for, target) seasons with lists of target episodes
            for f_se in sorted(alt_numbers):  # sort season list (and therefore, implicitly asc/desc of targets)
                t_se = alt_numbers[f_se]
                for_target_group.setdefault((f_se[0], t_se[0]), [])  # f_se[0] = for_season, t_se[0] = target_season
                for_target_group[(f_se[0], t_se[0])] += [(f_se[1], t_se[1])]  # f_se[1] = for_ep, t_se[1] = target_ep

            # minimise episode lists into ranges e.g. 1x1, 2x2, ... 5x5 => 1x1-5
            minimal = {}
            for ft_s, ft_e_range in iteritems(for_target_group):
                minimal.setdefault(ft_s, [])
                last_f_e = None
                for (f_e, t_e) in ft_e_range:
                    add_new = True
                    if minimal[ft_s]:
                        last = minimal[ft_s][-1]
                        last_t_e = last[-1]
                        if (f_e, t_e) in ((last_f_e + 1, last_t_e + 1), (last_f_e - 1, last_t_e - 1)):
                            add_new = False
                            if 2 == len(last):
                                minimal[ft_s][-1] += [t_e]  # create range
                            else:
                                minimal[ft_s][-1][-1] += (-1, 1)[t_e == last_t_e + 1]  # adjust range
                    last_f_e = f_e
                    if add_new:
                        minimal[ft_s] += [[f_e, t_e]]  # singular

            for (f_s, t_s), ft_list in iteritems(minimal):
                alts[f_s].setdefault('se', [])
                for fe_te in ft_list:
                    alts[f_s]['se'] += [dict({fe_te[0]: '%sx%s' % (t_s, '-'.join(['%s' % x for x in fe_te[1:]]))})]

            ui_output = json.dumps(dict({tvid_prodid: alts}), indent=2, separators=(',', ': '))
        return json.dumps(dict(text='%s\n\n' % ui_output))

    @staticmethod
    def generate_key():
        """ Return a new randomized API_KEY
        """
        # Create some values to seed md5
        seed = str(time.time()) + str(random.random())

        result = hashlib.new('md5', decode_bytes(seed)).hexdigest()

        # Return a hex digest of the md5, eg 49f68a5c8493ec2c0bf489821c21fc3b
        logger.log(u'New API generated')

        return result

    @staticmethod
    def save_root_dirs(root_dir_string=None):

        sickbeard.ROOT_DIRS = root_dir_string

    @staticmethod
    def save_result_prefs(ui_results_sortby=None):

        if ui_results_sortby in ('az', 'za', 'newest', 'oldest', 'rel', 'notop', 'ontop', 'nogroup', 'ingroup'):
            is_notop = ('', ' notop')['notop' in sickbeard.RESULTS_SORTBY]
            is_nogrp = ('', ' nogroup')['nogroup' in sickbeard.RESULTS_SORTBY]
            if 'top' == ui_results_sortby[-3:] or 'group' == ui_results_sortby[-5:]:
                maybe_ontop = (is_notop, ('', ' notop')[not is_notop])['top' == ui_results_sortby[-3:]]
                maybe_ingroup = (is_nogrp, ('', ' nogroup')[not is_nogrp])['group' == ui_results_sortby[-5:]]
                sortby = sickbeard.RESULTS_SORTBY.replace(' notop', '').replace(' nogroup', '')
                sickbeard.RESULTS_SORTBY = '%s%s%s' % (('rel', sortby)[any([sortby])], maybe_ontop, maybe_ingroup)
            else:
                sickbeard.RESULTS_SORTBY = '%s%s%s' % (ui_results_sortby, is_notop, is_nogrp)

            sickbeard.save_config()

    @staticmethod
    def save_add_show_defaults(default_status, any_qualities='', best_qualities='', default_wanted_begin=None,
                               default_wanted_latest=None, default_flatten_folders=False, default_scene=False,
                               default_subs=False, default_anime=False, default_pause=False, default_tag=''):

        any_qualities = ([], any_qualities.split(','))[any(any_qualities)]
        best_qualities = ([], best_qualities.split(','))[any(best_qualities)]

        sickbeard.QUALITY_DEFAULT = int(Quality.combineQualities(map_list(int, any_qualities),
                                                                 map_list(int, best_qualities)))
        sickbeard.WANTED_BEGIN_DEFAULT = config.minimax(default_wanted_begin, 0, -1, 10)
        sickbeard.WANTED_LATEST_DEFAULT = config.minimax(default_wanted_latest, 0, -1, 10)
        sickbeard.SHOW_TAG_DEFAULT = default_tag
        sickbeard.PAUSE_DEFAULT = config.checkbox_to_value(default_pause)
        sickbeard.STATUS_DEFAULT = int(default_status)
        sickbeard.SCENE_DEFAULT = config.checkbox_to_value(default_scene)
        sickbeard.SUBTITLES_DEFAULT = config.checkbox_to_value(default_subs)
        sickbeard.FLATTEN_FOLDERS_DEFAULT = config.checkbox_to_value(default_flatten_folders)
        sickbeard.ANIME_DEFAULT = config.checkbox_to_value(default_anime)

        sickbeard.save_config()

    @staticmethod
    def generateKey(*args, **kwargs):
        """ Return a new randomized API_KEY
        """

        try:
            from hashlib import md5
        except ImportError:
            # noinspection PyUnresolvedReferences,PyCompatibility
            from md5 import md5

        # Create some values to seed md5
        t = str(time.time())
        r = str(random.random())

        # Create the md5 instance and give it the current time
        m = md5(decode_bytes(t))

        # Update the md5 instance with the random variable
        m.update(decode_bytes(r))

        # Return a hex digest of the md5, eg 49f68a5c8493ec2c0bf489821c21fc3b
        app_name = kwargs.get('app_name')
        app_name = '' if not app_name else ' for [%s]' % app_name
        logger.log(u'New apikey generated%s' % app_name)
        return m.hexdigest()

    def create_apikey(self, app_name):
        result = dict()
        if not app_name:
            result['result'] = 'Failed: no name given'
        elif app_name in [k[0] for k in sickbeard.API_KEYS if k[0]]:
            result['result'] = 'Failed: name is not unique'
        else:
            api_key = self.generateKey(app_name=app_name)
            if api_key in [k[1] for k in sickbeard.API_KEYS if k[0]]:
                result['result'] = 'Failed: apikey already exists, try again'
            else:
                sickbeard.API_KEYS.append([app_name, api_key])
                logger.log('Created apikey for [%s]' % app_name, logger.DEBUG)
                result.update(dict(result='Success: apikey added', added=api_key))
                sickbeard.USE_API = 1
                sickbeard.save_config()
                ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        return json.dumps(result)

    @staticmethod
    def revoke_apikey(app_name, api_key):
        result = dict()
        if not app_name:
            result['result'] = 'Failed: no name given'
        elif not api_key or 32 != len(re.sub('(?i)[^0-9a-f]', '', api_key)):
            result['result'] = 'Failed: key not valid'
        elif api_key not in [k[1] for k in sickbeard.API_KEYS if k[0]]:
            result['result'] = 'Failed: key doesn\'t exist'
        else:
            sickbeard.API_KEYS = [ak for ak in sickbeard.API_KEYS if ak[0] and api_key != ak[1]]
            logger.log('Revoked [%s] apikey [%s]' % (app_name, api_key), logger.DEBUG)
            result.update(dict(result='Success: apikey removed', removed=True))
            sickbeard.save_config()
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        return json.dumps(result)

    def save_general(self, launch_browser=None, update_shows_on_start=None, show_update_hour=None,
                     trash_remove_show=None, trash_rotate_logs=None,
                     log_dir=None, web_log=None,
                     indexer_default=None, indexer_timeout=None,
                     show_dirs_with_dots=None,
                     update_notify=None, update_auto=None, update_interval=None, notify_on_update=None,
                     update_packages_notify=None, update_packages_auto=None, update_packages_menu=None,
                     update_packages_interval=None,
                     update_frequency=None,  # deprecated 2020.11.07
                     theme_name=None, default_home=None, fanart_limit=None, showlist_tagview=None, show_tags=None,
                     home_search_focus=None, use_imdb_info=None, display_freespace=None, sort_article=None,
                     fuzzy_dating=None, trim_zero=None, date_preset=None, time_preset=None,
                     timezone_display=None,
                     web_username=None, web_password=None,
                     calendar_unprotected=None, use_api=None, web_port=None,
                     enable_https=None, https_cert=None, https_key=None,
                     web_ipv6=None, web_ipv64=None,
                     handle_reverse_proxy=None, send_security_headers=None, allowed_hosts=None, allow_anyip=None,
                     git_remote=None,
                     git_path=None, cpu_preset=None, anon_redirect=None, encryption_version=None,
                     proxy_setting=None, proxy_indexers=None, file_logging_preset=None, backup_db_oneday=None):

        # 2020.11.07 prevent deprecated var issues from existing ui, delete in future, added
        if None is update_interval and None is not update_frequency:
            update_interval = update_frequency

        results = []

        # Misc
        sickbeard.LAUNCH_BROWSER = config.checkbox_to_value(launch_browser)
        sickbeard.UPDATE_SHOWS_ON_START = config.checkbox_to_value(update_shows_on_start)
        sickbeard.SHOW_UPDATE_HOUR = config.minimax(show_update_hour, 3, 0, 23)
        try:
            with sickbeard.show_update_scheduler.lock:
                sickbeard.show_update_scheduler.start_time = datetime.time(hour=sickbeard.SHOW_UPDATE_HOUR)
        except (BaseException, Exception) as e:
            logger.log('Could not change Show Update Scheduler time: %s' % ex(e), logger.ERROR)
        sickbeard.TRASH_REMOVE_SHOW = config.checkbox_to_value(trash_remove_show)
        sg_helpers.TRASH_REMOVE_SHOW = sickbeard.TRASH_REMOVE_SHOW
        sickbeard.TRASH_ROTATE_LOGS = config.checkbox_to_value(trash_rotate_logs)
        if not config.change_log_dir(log_dir, web_log):
            results += ['Unable to create directory ' + os.path.normpath(log_dir) + ', log directory not changed.']
        if indexer_default:
            sickbeard.TVINFO_DEFAULT = config.to_int(indexer_default)
            if 0 != sickbeard.TVINFO_DEFAULT and not sickbeard.TVInfoAPI(sickbeard.TVINFO_DEFAULT).config.get('active'):
                sickbeard.TVINFO_DEFAULT = TVINFO_TVDB
        if indexer_timeout:
            sickbeard.TVINFO_TIMEOUT = config.to_int(indexer_timeout)
        sickbeard.SHOW_DIRS_WITH_DOTS = config.checkbox_to_value(show_dirs_with_dots)

        # Updates
        config.schedule_update_software_notify(config.checkbox_to_value(update_notify))
        sickbeard.UPDATE_AUTO = config.checkbox_to_value(update_auto)
        config.schedule_update_software(update_interval)
        sickbeard.NOTIFY_ON_UPDATE = config.checkbox_to_value(notify_on_update)

        config.schedule_update_packages_notify(config.checkbox_to_value(update_packages_notify))
        sickbeard.UPDATE_PACKAGES_AUTO = config.checkbox_to_value(update_packages_auto)
        sickbeard.UPDATE_PACKAGES_MENU = config.checkbox_to_value(update_packages_menu)
        config.schedule_update_packages(update_packages_interval)

        # Interface
        sickbeard.THEME_NAME = theme_name
        sickbeard.DEFAULT_HOME = default_home
        sickbeard.FANART_LIMIT = config.minimax(fanart_limit, 3, 0, 500)
        sickbeard.SHOWLIST_TAGVIEW = showlist_tagview

        # 'Show List' is the must have default fallback. Tags in use that are removed from config ui are restored,
        # not deleted. Deduped list order preservation is key to feature function.
        my_db = db.DBConnection()
        sql_result = my_db.select('SELECT DISTINCT tag FROM tv_shows')
        new_names = [u'' + v.strip() for v in (show_tags.split(u','), [])[None is show_tags] if v.strip()]
        orphans = [item for item in [v['tag'] for v in sql_result or []] if item not in new_names]
        cleanser = []
        if 0 < len(orphans):
            cleanser = [item for item in sickbeard.SHOW_TAGS if item in orphans or item in new_names]
            results += [u'An attempt was prevented to remove a show list group name still in use']
        dedupe = {}
        sickbeard.SHOW_TAGS = [dedupe.setdefault(item, item) for item in (cleanser + new_names + [u'Show List'])
                               if item not in dedupe]

        sickbeard.HOME_SEARCH_FOCUS = config.checkbox_to_value(home_search_focus)
        sickbeard.USE_IMDB_INFO = config.checkbox_to_value(use_imdb_info)
        sickbeard.DISPLAY_FREESPACE = config.checkbox_to_value(display_freespace)
        sickbeard.SORT_ARTICLE = config.checkbox_to_value(sort_article)
        sickbeard.FUZZY_DATING = config.checkbox_to_value(fuzzy_dating)
        sickbeard.TRIM_ZERO = config.checkbox_to_value(trim_zero)
        if date_preset:
            sickbeard.DATE_PRESET = date_preset
        if time_preset:
            sickbeard.TIME_PRESET_W_SECONDS = time_preset
            sickbeard.TIME_PRESET = sickbeard.TIME_PRESET_W_SECONDS.replace(u':%S', u'')
        sickbeard.TIMEZONE_DISPLAY = timezone_display

        # Web interface
        restart = False
        reload_page = False
        if sickbeard.WEB_USERNAME != web_username:
            sickbeard.WEB_USERNAME = web_username
            reload_page = True
        if set('*') != set(web_password):
            sickbeard.WEB_PASSWORD = web_password
            reload_page = True

        sickbeard.CALENDAR_UNPROTECTED = config.checkbox_to_value(calendar_unprotected)
        sickbeard.USE_API = config.checkbox_to_value(use_api)
        sickbeard.WEB_PORT = config.to_int(web_port)
        # sickbeard.WEB_LOG is set in config.change_log_dir()

        restart |= sickbeard.ENABLE_HTTPS != config.checkbox_to_value(enable_https)
        sickbeard.ENABLE_HTTPS = config.checkbox_to_value(enable_https)
        if not config.change_https_cert(https_cert):
            results += [
                'Unable to create directory ' + os.path.normpath(https_cert) + ', https cert directory not changed.']
        if not config.change_https_key(https_key):
            results += [
                'Unable to create directory ' + os.path.normpath(https_key) + ', https key directory not changed.']

        sickbeard.WEB_IPV6 = config.checkbox_to_value(web_ipv6)
        sickbeard.WEB_IPV64 = config.checkbox_to_value(web_ipv64)
        sickbeard.HANDLE_REVERSE_PROXY = config.checkbox_to_value(handle_reverse_proxy)
        sickbeard.SEND_SECURITY_HEADERS = config.checkbox_to_value(send_security_headers)
        hosts = ','.join(filter_iter(lambda name: not helpers.re_valid_hostname(with_allowed=False).match(name),
                                     config.clean_hosts(allowed_hosts).split(',')))
        if not hosts or self.request.host_name in hosts:
            sickbeard.ALLOWED_HOSTS = hosts
        sickbeard.ALLOW_ANYIP = config.checkbox_to_value(allow_anyip)

        # Advanced
        sickbeard.GIT_REMOTE = git_remote
        sickbeard.GIT_PATH = git_path
        sickbeard.CPU_PRESET = cpu_preset
        sickbeard.ANON_REDIRECT = anon_redirect
        sickbeard.ENCRYPTION_VERSION = config.checkbox_to_value(encryption_version)
        sickbeard.PROXY_SETTING = proxy_setting
        sg_helpers.PROXY_SETTING = proxy_setting
        sickbeard.PROXY_INDEXERS = config.checkbox_to_value(proxy_indexers)
        sickbeard.FILE_LOGGING_PRESET = file_logging_preset
        # sickbeard.LOG_DIR is set in config.change_log_dir()
        sickbeard.BACKUP_DB_ONEDAY = bool(config.checkbox_to_value(backup_db_oneday))

        logger.log_set_level()

        sickbeard.save_config()

        if 0 < len(results):
            for v in results:
                logger.log(v, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        if restart:
            self.clear_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT))
            self.write('restart')
            reload_page = False

        if reload_page:
            self.clear_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT))
            self.write('reload')

    @staticmethod
    def fetch_pullrequests():
        if 'master' == sickbeard.BRANCH:
            return json.dumps({'result': 'success', 'pulls': []})
        else:
            try:
                pulls = sickbeard.update_software_scheduler.action.list_remote_pulls()
                return json.dumps({'result': 'success', 'pulls': pulls})
            except (BaseException, Exception) as e:
                logger.log(u'exception msg: ' + ex(e), logger.DEBUG)
                return json.dumps({'result': 'fail'})

    @staticmethod
    def fetch_branches():
        try:
            branches = sickbeard.update_software_scheduler.action.list_remote_branches()
            return json.dumps({'result': 'success', 'branches': branches, 'current': sickbeard.BRANCH or 'master'})
        except (BaseException, Exception) as e:
            logger.log(u'exception msg: ' + ex(e), logger.DEBUG)
            return json.dumps({'result': 'fail'})


class ConfigSearch(Config):

    def index(self):

        t = PageTemplate(web_handler=self, file='config_search.tmpl')
        t.submenu = self.config_menu('Search')
        t.using_rls_ignore_words = [(cur_so.tvid_prodid, cur_so.name) for cur_so in sickbeard.showList
                                    if cur_so.rls_ignore_words and cur_so.rls_ignore_words]
        t.using_rls_ignore_words.sort(key=lambda x: x[1], reverse=False)
        t.using_rls_require_words = [(cur_so.tvid_prodid, cur_so.name) for cur_so in sickbeard.showList
                                     if cur_so.rls_require_words and cur_so.rls_require_words]
        t.using_rls_require_words.sort(key=lambda x: x[1], reverse=False)
        t.using_exclude_ignore_words = [(cur_so.tvid_prodid, cur_so.name)
                                        for cur_so in sickbeard.showList if cur_so.rls_global_exclude_ignore]
        t.using_exclude_ignore_words.sort(key=lambda x: x[1], reverse=False)
        t.using_exclude_require_words = [(cur_so.tvid_prodid, cur_so.name)
                                         for cur_so in sickbeard.showList if cur_so.rls_global_exclude_require]
        t.using_exclude_require_words.sort(key=lambda x: x[1], reverse=False)
        t.using_regex = False
        try:
            from sickbeard.name_parser.parser import regex
            t.using_regex = None is not regex
        except (BaseException, Exception):
            pass
        return t.respond()

    def save_search(self, nzb_dir=None, torrent_dir=None,
                    recentsearch_interval=None, backlog_period=None, backlog_limited_period=None, backlog_nofull=None,
                    recentsearch_frequency=None, backlog_frequency=None, backlog_days=None,
                    use_nzbs=None, use_torrents=None, nzb_method=None, torrent_method=None,
                    usenet_retention=None, ignore_words=None, require_words=None,
                    download_propers=None, propers_webdl_onegrp=None,
                    search_unaired=None, unaired_recent_search_only=None, flaresolverr_host=None,
                    allow_high_priority=None,
                    sab_username=None, sab_password=None, sab_apikey=None, sab_category=None, sab_host=None,
                    nzbget_username=None, nzbget_password=None, nzbget_category=None, nzbget_host=None,
                    nzbget_use_https=None, nzbget_priority=None, nzbget_parent_map=None,
                    torrent_username=None, torrent_password=None, torrent_label=None, torrent_label_var=None,
                    torrent_verify_cert=None, torrent_path=None, torrent_seed_time=None, torrent_paused=None,
                    torrent_high_bandwidth=None, torrent_host=None):

        # prevent deprecated var issues from existing ui, delete in future, added 2020.11.07
        if None is recentsearch_interval and None is not recentsearch_frequency:
            recentsearch_interval = recentsearch_frequency
        if None is backlog_period and None is not backlog_frequency:
            backlog_period = backlog_frequency
        if None is backlog_limited_period and None is not backlog_days:
            backlog_limited_period = backlog_days

        results = []

        if not config.change_nzb_dir(nzb_dir):
            results += ['Unable to create directory ' + os.path.normpath(nzb_dir) + ', dir not changed.']

        if not config.change_torrent_dir(torrent_dir):
            results += ['Unable to create directory ' + os.path.normpath(torrent_dir) + ', dir not changed.']

        config.schedule_recentsearch(recentsearch_interval)

        old_backlog_period = sickbeard.BACKLOG_PERIOD
        config.schedule_backlog(backlog_period)
        sickbeard.search_backlog.BacklogSearcher.change_backlog_parts(
            old_backlog_period, sickbeard.BACKLOG_PERIOD)
        sickbeard.BACKLOG_LIMITED_PERIOD = config.to_int(backlog_limited_period, default=7)

        sickbeard.BACKLOG_NOFULL = bool(config.checkbox_to_value(backlog_nofull))
        if sickbeard.BACKLOG_NOFULL:
            my_db = db.DBConnection('cache.db')
            # noinspection SqlConstantCondition
            my_db.action('DELETE FROM backlogparts WHERE 1=1')

        sickbeard.USE_NZBS = config.checkbox_to_value(use_nzbs)
        sickbeard.USE_TORRENTS = config.checkbox_to_value(use_torrents)

        sickbeard.NZB_METHOD = nzb_method
        sickbeard.TORRENT_METHOD = torrent_method
        sickbeard.USENET_RETENTION = config.to_int(usenet_retention, default=500)

        sickbeard.IGNORE_WORDS, sickbeard.IGNORE_WORDS_REGEX = helpers.split_word_str(ignore_words
                                                                                      if ignore_words else '')
        sickbeard.REQUIRE_WORDS, sickbeard.REQUIRE_WORDS_REGEX = helpers.split_word_str(require_words
                                                                                        if require_words else '')

        clean_ignore_require_words()

        config.schedule_download_propers(config.checkbox_to_value(download_propers))
        sickbeard.PROPERS_WEBDL_ONEGRP = config.checkbox_to_value(propers_webdl_onegrp)

        sickbeard.SEARCH_UNAIRED = bool(config.checkbox_to_value(search_unaired))
        sickbeard.UNAIRED_RECENT_SEARCH_ONLY = bool(config.checkbox_to_value(unaired_recent_search_only,
                                                                             value_off=1, value_on=0))

        sickbeard.FLARESOLVERR_HOST = config.clean_url(flaresolverr_host)
        sg_helpers.FLARESOLVERR_HOST = sickbeard.FLARESOLVERR_HOST

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
        sickbeard.NZBGET_MAP = config.kv_csv(nzbget_parent_map)

        sickbeard.TORRENT_USERNAME = torrent_username
        if set('*') != set(torrent_password):
            sickbeard.TORRENT_PASSWORD = torrent_password
        sickbeard.TORRENT_LABEL = torrent_label
        sickbeard.TORRENT_LABEL_VAR = config.to_int((0, torrent_label_var)['rtorrent' == torrent_method], 1)
        if not (0 <= sickbeard.TORRENT_LABEL_VAR <= 5):
            logger.log('Setting rTorrent custom%s is not 0-5, defaulting to custom1' % torrent_label_var, logger.DEBUG)
            sickbeard.TORRENT_LABEL_VAR = 1
        sickbeard.TORRENT_VERIFY_CERT = config.checkbox_to_value(torrent_verify_cert)
        sickbeard.TORRENT_PATH = torrent_path
        sickbeard.TORRENT_SEED_TIME = config.to_int(torrent_seed_time, 0)
        sickbeard.TORRENT_PAUSED = config.checkbox_to_value(torrent_paused)
        sickbeard.TORRENT_HIGH_BANDWIDTH = config.checkbox_to_value(torrent_high_bandwidth)
        sickbeard.TORRENT_HOST = config.clean_url(torrent_host)

        sickbeard.save_config()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/search/')


class ConfigMediaProcess(Config):

    def index(self):

        t = PageTemplate(web_handler=self, file='config_postProcessing.tmpl')
        t.submenu = self.config_menu('Processing')
        return t.respond()

    def save_post_processing(self, tv_download_dir=None, process_automatically=None, mediaprocess_interval=None,
                             autopostprocesser_frequency=None,
                             unpack=None, keep_processed_dir=None, process_method=None,
                             extra_scripts='', sg_extra_scripts='',
                             rename_episodes=None, airdate_episodes=None,
                             move_associated_files=None, postpone_if_sync_files=None,
                             naming_custom_abd=None, naming_custom_sports=None, naming_custom_anime=None,
                             naming_strip_year=None, use_failed_downloads=None, delete_failed=None,
                             skip_removed_files=None, nfo_rename=None,
                             xbmc_data=None, xbmc_12plus_data=None, mediabrowser_data=None, sony_ps3_data=None,
                             wdtv_data=None, tivo_data=None, mede8er_data=None, kodi_data=None,
                             naming_pattern=None, naming_multi_ep=None,
                             naming_anime=None, naming_anime_pattern=None, naming_anime_multi_ep=None,
                             naming_abd_pattern=None, naming_sports_pattern=None):

        # prevent deprecated var issues from existing ui, delete in future, added 2020.11.07
        if None is mediaprocess_interval and None is not autopostprocesser_frequency:
            mediaprocess_interval = autopostprocesser_frequency

        results = []

        if not config.change_tv_download_dir(tv_download_dir):
            results += ['Unable to create directory ' + os.path.normpath(tv_download_dir) + ', dir not changed.']

        new_val = config.checkbox_to_value(process_automatically)
        sickbeard.PROCESS_AUTOMATICALLY = new_val
        config.schedule_mediaprocess(mediaprocess_interval)

        if unpack:
            if 'not supported' != self.is_rar_supported():
                sickbeard.UNPACK = config.checkbox_to_value(unpack)
            else:
                sickbeard.UNPACK = 0
                results.append('Unpacking Not Supported, disabling unpack setting')
        else:
            sickbeard.UNPACK = config.checkbox_to_value(unpack)

        sickbeard.KEEP_PROCESSED_DIR = config.checkbox_to_value(keep_processed_dir)
        sickbeard.PROCESS_METHOD = process_method
        sickbeard.EXTRA_SCRIPTS = [x.strip() for x in extra_scripts.split('|') if x.strip()]
        sickbeard.SG_EXTRA_SCRIPTS = [x.strip() for x in sg_extra_scripts.split('|') if x.strip()]
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

        if 'invalid' != self.is_naming_valid(naming_pattern, naming_multi_ep, anime_type=naming_anime):
            sickbeard.NAMING_PATTERN = naming_pattern
            sickbeard.NAMING_MULTI_EP = int(naming_multi_ep)
            sickbeard.NAMING_ANIME = int(naming_anime)
            sickbeard.NAMING_FORCE_FOLDERS = naming.check_force_season_folders()
        else:
            if int(naming_anime) in [1, 2]:
                results.append('You tried saving an invalid anime naming config, not saving your naming settings')
            else:
                results.append('You tried saving an invalid naming config, not saving your naming settings')

        if 'invalid' != self.is_naming_valid(naming_anime_pattern, naming_anime_multi_ep, anime_type=naming_anime):
            sickbeard.NAMING_ANIME_PATTERN = naming_anime_pattern
            sickbeard.NAMING_ANIME_MULTI_EP = int(naming_anime_multi_ep)
            sickbeard.NAMING_ANIME = int(naming_anime)
            sickbeard.NAMING_FORCE_FOLDERS = naming.check_force_season_folders()
        else:
            if int(naming_anime) in [1, 2]:
                results.append('You tried saving an invalid anime naming config, not saving your naming settings')
            else:
                results.append('You tried saving an invalid naming config, not saving your naming settings')

        if 'invalid' != self.is_naming_valid(naming_abd_pattern, abd=True):
            sickbeard.NAMING_ABD_PATTERN = naming_abd_pattern
        else:
            results.append(
                'You tried saving an invalid air-by-date naming config, not saving your air-by-date settings')

        if 'invalid' != self.is_naming_valid(naming_sports_pattern, sports=True):
            sickbeard.NAMING_SPORTS_PATTERN = naming_sports_pattern
        else:
            results.append(
                'You tried saving an invalid sports naming config, not saving your sports settings')

        sickbeard.save_config()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/media-process/')

    @staticmethod
    def test_naming(pattern=None, multi=None, abd=False, sports=False, anime=False, anime_type=None):

        if None is not multi:
            multi = int(multi)

        if None is not anime_type:
            anime_type = int(anime_type)

        result = naming.test_name(pattern, multi, abd, sports, anime, anime_type)

        result = ek.ek(os.path.join, result['dir'], result['name'])

        return result

    @staticmethod
    def is_naming_valid(pattern=None, multi=None, abd=False, sports=False, anime_type=None):
        if None is pattern:
            return 'invalid'

        if None is not multi:
            multi = int(multi)

        if None is not anime_type:
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

        return 'invalid'

    @staticmethod
    def is_rar_supported():
        """
        Test Packing Support:
        """

        try:
            if 'win32' == sys.platform:
                rarfile.UNRAR_TOOL = ek.ek(os.path.join, sickbeard.PROG_DIR, 'lib', 'rarfile', 'UnRAR.exe')
            rar_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'lib', 'rarfile', 'test.rar')
            if 'This is only a test.' == decode_str(rarfile.RarFile(rar_path).read(r'test/test.txt')):
                return 'supported'
            msg = 'Could not read test file content'
        except (BaseException, Exception) as e:
            msg = ex(e)

        logger.log(u'Rar Not Supported: %s' % msg, logger.ERROR)
        return 'not supported'


class ConfigProviders(Config):

    def index(self):
        t = PageTemplate(web_handler=self, file='config_providers.tmpl')
        t.submenu = self.config_menu('Providers')
        return t.respond()

    @staticmethod
    def can_add_newznab_provider(name, url):
        if not name or not url:
            return json.dumps({'error': 'No Provider Name or url specified'})

        provider_dict = dict(zip([sickbeard.providers.generic_provider_name(x.get_id())
                                 for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))
        provider_url_dict = dict(zip([sickbeard.providers.generic_provider_url(x.url)
                                 for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))

        temp_provider = newznab.NewznabProvider(name, config.clean_url(url))

        e_p = provider_dict.get(sickbeard.providers.generic_provider_name(temp_provider.get_id()), None) or \
            provider_url_dict.get(sickbeard.providers.generic_provider_url(temp_provider.url), None)

        if e_p:
            return json.dumps({'error': 'Provider already exists as %s' % e_p.name})

        return json.dumps({'success': temp_provider.get_id()})

    @staticmethod
    def get_newznab_categories(name, url, key):
        """
        Retrieves a list of possible categories with category id's
        Using the default url/api?cat
        https://yournewznaburl.com/api?t=caps&apikey=yourapikey
        """
        error = not name and 'Name' or not url and 'Url' or not key and 'Apikey' or ''
        if error:
            error = '\nNo provider %s specified' % error
            return json.dumps({'success': False, 'error': error})

        if name in [n.name for n in sickbeard.newznabProviderList if n.url == url]:
            provider = [n for n in sickbeard.newznabProviderList if n.name == name][0]
            tv_categories = provider.clean_newznab_categories(provider.all_cats)
            state = provider.is_enabled()
        else:
            providers = dict(zip([x.get_id() for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))
            temp_provider = newznab.NewznabProvider(name, url, key)
            if None is not key and starify(key, True):
                temp_provider.key = providers[temp_provider.get_id()].key

            tv_categories = temp_provider.clean_newznab_categories(temp_provider.all_cats)
            state = False

        return json.dumps({'success': True, 'tv_categories': tv_categories, 'state': state, 'error': ''})

    @staticmethod
    def can_add_torrent_rss_provider(name, url, cookies):
        if not name:
            return json.dumps({'error': 'Invalid name specified'})

        provider_dict = dict(
            zip([x.get_id() for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        temp_provider = rsstorrent.TorrentRssProvider(name, url, cookies)

        if temp_provider.get_id() in provider_dict:
            return json.dumps({'error': 'A provider exists as [%s]' % provider_dict[temp_provider.get_id()].name})
        else:
            (succ, errMsg) = temp_provider.validate_feed()
            if succ:
                return json.dumps({'success': temp_provider.get_id()})

            return json.dumps({'error': errMsg})

    @staticmethod
    def check_providers_ping():
        for p in sickbeard.providers.sortedProviderList():
            if getattr(p, 'ping_iv', None):
                if p.is_active() and (p.get_id() not in sickbeard.provider_ping_thread_pool
                                      or not sickbeard.provider_ping_thread_pool[p.get_id()].is_alive()):
                    # noinspection PyProtectedMember
                    sickbeard.provider_ping_thread_pool[p.get_id()] = threading.Thread(
                        name='PING-PROVIDER %s' % p.name, target=p._ping)
                    sickbeard.provider_ping_thread_pool[p.get_id()].start()
                elif not p.is_active() and p.get_id() in sickbeard.provider_ping_thread_pool:
                    sickbeard.provider_ping_thread_pool[p.get_id()].stop = True
                    try:
                        sickbeard.provider_ping_thread_pool[p.get_id()].join(120)
                        if not sickbeard.provider_ping_thread_pool[p.get_id()].is_alive():
                            sickbeard.provider_ping_thread_pool.pop(p.get_id())
                    except RuntimeError:
                        pass

        # stop removed providers
        prov = [n.get_id() for n in sickbeard.providers.sortedProviderList()]
        for p in [x for x in sickbeard.provider_ping_thread_pool if x not in prov]:
            sickbeard.provider_ping_thread_pool[p].stop = True
            try:
                sickbeard.provider_ping_thread_pool[p].join(120)
                if not sickbeard.provider_ping_thread_pool[p].is_alive():
                    sickbeard.provider_ping_thread_pool.pop(p)
            except RuntimeError:
                pass

    def save_providers(self, newznab_string='', torrentrss_string='', provider_order=None, **kwargs):

        results = []
        provider_list = []

        # add all the newznab info we have into our list
        newznab_sources = dict(zip([x.get_id() for x in sickbeard.newznabProviderList], sickbeard.newznabProviderList))
        active_ids = []
        reload_page = False
        if newznab_string:
            for curNewznabProviderStr in newznab_string.split('!!!'):

                if not curNewznabProviderStr:
                    continue

                cur_name, cur_url, cur_key, cur_cat = curNewznabProviderStr.split('|')
                cur_url = config.clean_url(cur_url)
                cur_key = cur_key.strip()

                if starify(cur_key, True):
                    cur_key = ''

                # correct user entry mistakes
                test_url = cur_url.lower()
                if 'nzbs2go' in test_url and test_url.endswith('.com/') or 'api/v1/api' in test_url:
                    cur_url = 'https://nzbs2go.com/api/v1/'

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

                    attr = 'filter'
                    if hasattr(nzb_src, attr):
                        setattr(nzb_src, attr,
                                [k for k in nzb_src.may_filter
                                 if config.checkbox_to_value(kwargs.get('%s_filter_%s' % (cur_id, k)))])

                    for attr in filter_iter(lambda a: hasattr(nzb_src, a), [
                        'search_fallback', 'enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog',
                        'scene_only', 'scene_loose', 'scene_loose_active', 'scene_rej_nuked', 'scene_nuked_active'
                    ]):
                        setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(cur_id + '_' + attr)))

                    for attr in ['scene_or_contain', 'search_mode']:
                        attr_check = '%s_%s' % (cur_id, attr)
                        if attr_check in kwargs:
                            setattr(nzb_src, attr, str(kwargs.get(attr_check) or '').strip())
                else:
                    new_provider.enabled = True
                    _ = new_provider.caps  # when adding a custom, trigger server_type update
                    new_provider.enabled = False
                    sickbeard.newznabProviderList.append(new_provider)

                active_ids.append(cur_id)

        # delete anything that is missing
        if sickbeard.USE_NZBS:
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
                    torrss_src = torrent_rss_sources[cur_id]

                    torrss_src.name = cur_name
                    torrss_src.url = cur_url
                    if cur_cookies:
                        torrss_src.cookies = cur_cookies

                    for attr in ['scene_only', 'scene_loose', 'scene_loose_active',
                                 'scene_rej_nuked', 'scene_nuked_active']:
                        setattr(torrss_src, attr, config.checkbox_to_value(kwargs.get(cur_id + '_' + attr)))

                    for attr in ['scene_or_contain']:
                        attr_check = '%s_%s' % (cur_id, attr)
                        if attr_check in kwargs:
                            setattr(torrss_src, attr, str(kwargs.get(attr_check) or '').strip())
                else:
                    sickbeard.torrentRssProviderList.append(new_provider)

                active_ids.append(cur_id)

        # delete anything that is missing
        if sickbeard.USE_TORRENTS:
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

            if src_name in sources and '' != getattr(sources[src_name], 'enabled', '') \
                    and sources[src_name].is_enabled() != src_enabled:
                if isinstance(sources[src_name], sickbeard.providers.newznab.NewznabProvider) and \
                        not sources[src_name].enabled and src_enabled:
                    reload_page = True
                sources[src_name].enabled = src_enabled
                if not reload_page and sickbeard.GenericProvider.TORRENT == sources[src_name].providerType:
                    reload_page = True

            if src_name in newznab_sources:
                if not newznab_sources[src_name].enabled and src_enabled:
                    reload_page = True
                newznab_sources[src_name].enabled = src_enabled
            elif src_name in torrent_rss_sources:
                torrent_rss_sources[src_name].enabled = src_enabled

        # update torrent source settings
        for torrent_src in [src for src in sickbeard.providers.sortedProviderList()
                            if sickbeard.GenericProvider.TORRENT == src.providerType]:  # type: TorrentProvider
            src_id_prefix = torrent_src.get_id() + '_'

            attr = 'url_edit'
            if getattr(torrent_src, attr, None):
                url_edit = ','.join(set(['%s' % url.strip() for url in kwargs.get(
                    src_id_prefix + attr, '').split(',')]))
                torrent_src.url_home = ([url_edit], [])[not url_edit]

            for attr in [x for x in ['password', 'api_key', 'passkey', 'digest', 'hash'] if hasattr(torrent_src, x)]:
                key = str(kwargs.get(src_id_prefix + attr, '')).strip()
                if 'password' == attr:
                    set('*') != set(key) and setattr(torrent_src, attr, key)
                elif not starify(key, True):
                    setattr(torrent_src, attr, key)

            for attr in filter_iter(lambda a: hasattr(torrent_src, a), [
                'username', 'uid', '_seed_ratio', 'scene_or_contain'
            ]):
                setattr(torrent_src, attr, str(kwargs.get(src_id_prefix + attr.replace('_seed_', ''), '')).strip())

            for attr in filter_iter(lambda a: hasattr(torrent_src, a), [
                'minseed', 'minleech', 'seed_time'
            ]):
                setattr(torrent_src, attr, config.to_int(str(kwargs.get(src_id_prefix + attr, '')).strip()))

            attr = 'filter'
            if hasattr(torrent_src, attr) and torrent_src.may_filter:
                setattr(torrent_src, attr,
                        [k for k in getattr(torrent_src, 'may_filter', 'nop')
                         if config.checkbox_to_value(kwargs.get('%sfilter_%s' % (src_id_prefix, k)))])

            for attr in filter_iter(lambda a: hasattr(torrent_src, a), [
                'confirmed', 'freeleech', 'reject_m2ts', 'use_after_get_data', 'enable_recentsearch',
                'enable_backlog', 'search_fallback', 'enable_scheduled_backlog',
                'scene_only', 'scene_loose', 'scene_loose_active',
                'scene_rej_nuked', 'scene_nuked_active'
            ]):
                setattr(torrent_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)))

            for attr, default in filter_iter(lambda arg: hasattr(torrent_src, arg[0]), [
                ('search_mode', 'eponly'),
            ]):
                setattr(torrent_src, attr, str(kwargs.get(src_id_prefix + attr) or default).strip())

        # update nzb source settings
        for nzb_src in [src for src in sickbeard.providers.sortedProviderList() if
                        sickbeard.GenericProvider.NZB == src.providerType]:
            src_id_prefix = nzb_src.get_id() + '_'

            for attr in [x for x in ['api_key', 'digest'] if hasattr(nzb_src, x)]:
                key = str(kwargs.get(src_id_prefix + attr, '')).strip()
                if not starify(key, True):
                    setattr(nzb_src, attr, key)

            attr = 'username'
            if hasattr(nzb_src, attr):
                setattr(nzb_src, attr, str(kwargs.get(src_id_prefix + attr, '')).strip() or None)

            attr = 'enable_recentsearch'
            if hasattr(nzb_src, attr):
                setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)) or
                        not getattr(nzb_src, 'supports_backlog', True))

            for attr in filter_iter(lambda a: hasattr(nzb_src, a),
                                    ['search_fallback', 'enable_backlog', 'enable_scheduled_backlog',
                                     'scene_only', 'scene_loose', 'scene_loose_active',
                                     'scene_rej_nuked', 'scene_nuked_active']):
                setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)))

            for (attr, default) in [('scene_or_contain', ''), ('search_mode', 'eponly')]:
                if hasattr(nzb_src, attr):
                    setattr(nzb_src, attr, str(kwargs.get(src_id_prefix + attr) or default).strip())

        sickbeard.NEWZNAB_DATA = '!!!'.join([x.config_str() for x in sickbeard.newznabProviderList])
        sickbeard.PROVIDER_ORDER = provider_list

        helpers.clear_unused_providers()

        sickbeard.save_config()

        cp = threading.Thread(name='Check-Ping-Providers', target=self.check_providers_ping)
        cp.start()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration', '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        if reload_page:
            self.write('reload')
        else:
            self.redirect('/config/providers/')


class ConfigNotifications(Config):

    def index(self):
        t = PageTemplate(web_handler=self, file='config_notifications.tmpl')
        t.submenu = self.config_menu('Notifications')
        t.root_dirs = []
        if sickbeard.ROOT_DIRS:
            root_pieces = sickbeard.ROOT_DIRS.split('|')
            root_default = helpers.try_int(root_pieces[0], None)
            for i, location in enumerate(root_pieces[1:]):
                t.root_dirs.append({'root_def': root_default and i == root_default,
                                    'loc': location,
                                    'b64': decode_str(base64.urlsafe_b64encode(decode_bytes(location)))})
        return t.respond()

    def save_notifications(
            self,
            use_emby=None, emby_update_library=None, emby_watched_interval=None, emby_parent_maps=None,
            emby_host=None, emby_apikey=None,
            use_kodi=None, kodi_always_on=None, kodi_update_library=None, kodi_update_full=None,
            kodi_update_onlyfirst=None, kodi_parent_maps=None, kodi_host=None, kodi_username=None, kodi_password=None,
            kodi_notify_onsnatch=None, kodi_notify_ondownload=None, kodi_notify_onsubtitledownload=None,
            use_plex=None, plex_update_library=None, plex_watched_interval=None, plex_parent_maps=None,
            plex_username=None, plex_password=None, plex_server_host=None,
            plex_notify_onsnatch=None, plex_notify_ondownload=None, plex_notify_onsubtitledownload=None, plex_host=None,
            use_nmj=None, nmj_host=None, nmj_database=None, nmj_mount=None,
            use_nmjv2=None, nmjv2_host=None, nmjv2_dbloc=None, nmjv2_database=None,
            use_synoindex=None, use_synologynotifier=None, synologynotifier_notify_onsnatch=None,
            synologynotifier_notify_ondownload=None, synologynotifier_notify_onsubtitledownload=None,
            use_pytivo=None, pytivo_host=None, pytivo_share_name=None, pytivo_tivo_name=None,

            use_boxcar2=None, boxcar2_notify_onsnatch=None, boxcar2_notify_ondownload=None,
            boxcar2_notify_onsubtitledownload=None, boxcar2_access_token=None, boxcar2_sound=None,
            use_pushbullet=None, pushbullet_notify_onsnatch=None, pushbullet_notify_ondownload=None,
            pushbullet_notify_onsubtitledownload=None, pushbullet_access_token=None, pushbullet_device_iden=None,
            use_pushover=None, pushover_notify_onsnatch=None, pushover_notify_ondownload=None,
            pushover_notify_onsubtitledownload=None, pushover_userkey=None, pushover_apikey=None,
            pushover_priority=None, pushover_device=None, pushover_sound=None,
            use_growl=None, growl_notify_onsnatch=None, growl_notify_ondownload=None,
            growl_notify_onsubtitledownload=None, growl_host=None,
            use_prowl=None, prowl_notify_onsnatch=None, prowl_notify_ondownload=None,
            prowl_notify_onsubtitledownload=None, prowl_api=None, prowl_priority=0,
            use_libnotify=None, libnotify_notify_onsnatch=None, libnotify_notify_ondownload=None,
            libnotify_notify_onsubtitledownload=None,

            use_trakt=None,
            # trakt_pin=None, trakt_remove_watchlist=None, trakt_use_watchlist=None, trakt_method_add=None,
            # trakt_start_paused=None, trakt_sync=None, trakt_default_indexer=None, trakt_remove_serieslist=None,
            # trakt_collection=None, trakt_accounts=None,
            use_slack=None, slack_notify_onsnatch=None, slack_notify_ondownload=None,
            slack_notify_onsubtitledownload=None, slack_access_token=None, slack_channel=None,
            slack_as_authed=None, slack_bot_name=None, slack_icon_url=None,
            use_discord=None, discord_notify_onsnatch=None, discord_notify_ondownload=None,
            discord_notify_onsubtitledownload=None, discord_access_token=None,
            discord_as_authed=None, discord_username=None, discord_icon_url=None,
            discord_as_tts=None,
            use_gitter=None, gitter_notify_onsnatch=None, gitter_notify_ondownload=None,
            gitter_notify_onsubtitledownload=None, gitter_access_token=None, gitter_room=None,
            use_telegram=None, telegram_notify_onsnatch=None, telegram_notify_ondownload=None,
            telegram_notify_onsubtitledownload=None, telegram_access_token=None, telegram_chatid=None,
            telegram_send_image=None, telegram_quiet=None,
            use_email=None, email_notify_onsnatch=None, email_notify_ondownload=None,
            email_notify_onsubtitledownload=None, email_host=None, email_port=25, email_from=None,
            email_tls=None, email_user=None, email_password=None, email_list=None,
            # email_show_list=None, email_show=None,
            **kwargs):

        results = []

        sickbeard.USE_EMBY = config.checkbox_to_value(use_emby)
        sickbeard.EMBY_UPDATE_LIBRARY = config.checkbox_to_value(emby_update_library)
        sickbeard.EMBY_PARENT_MAPS = config.kv_csv(emby_parent_maps)
        sickbeard.EMBY_HOST = config.clean_hosts(emby_host, allow_base=True)
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
        sickbeard.KODI_PARENT_MAPS = config.kv_csv(kodi_parent_maps)
        sickbeard.KODI_HOST = config.clean_hosts(kodi_host)
        sickbeard.KODI_USERNAME = kodi_username
        if set('*') != set(kodi_password):
            sickbeard.KODI_PASSWORD = kodi_password

        sickbeard.USE_PLEX = config.checkbox_to_value(use_plex)
        sickbeard.PLEX_NOTIFY_ONSNATCH = config.checkbox_to_value(plex_notify_onsnatch)
        sickbeard.PLEX_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(plex_notify_ondownload)
        sickbeard.PLEX_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(plex_notify_onsubtitledownload)
        sickbeard.PLEX_UPDATE_LIBRARY = config.checkbox_to_value(plex_update_library)
        sickbeard.PLEX_PARENT_MAPS = config.kv_csv(plex_parent_maps)
        sickbeard.PLEX_HOST = config.clean_hosts(plex_host)
        sickbeard.PLEX_SERVER_HOST = config.clean_hosts(plex_server_host)
        sickbeard.PLEX_USERNAME = plex_username
        if set('*') != set(plex_password):
            sickbeard.PLEX_PASSWORD = plex_password
        config.schedule_emby_watched(emby_watched_interval)
        config.schedule_plex_watched(plex_watched_interval)

        sickbeard.USE_GROWL = config.checkbox_to_value(use_growl)
        sickbeard.GROWL_NOTIFY_ONSNATCH = config.checkbox_to_value(growl_notify_onsnatch)
        sickbeard.GROWL_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(growl_notify_ondownload)
        sickbeard.GROWL_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(growl_notify_onsubtitledownload)
        sickbeard.GROWL_HOST = config.clean_hosts(growl_host, default_port=23053)

        sickbeard.USE_PROWL = config.checkbox_to_value(use_prowl)
        sickbeard.PROWL_NOTIFY_ONSNATCH = config.checkbox_to_value(prowl_notify_onsnatch)
        sickbeard.PROWL_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(prowl_notify_ondownload)
        sickbeard.PROWL_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(prowl_notify_onsubtitledownload)
        key = prowl_api.strip()
        if not starify(key, True):
            sickbeard.PROWL_API = key
        sickbeard.PROWL_PRIORITY = prowl_priority

        sickbeard.USE_BOXCAR2 = config.checkbox_to_value(use_boxcar2)
        sickbeard.BOXCAR2_NOTIFY_ONSNATCH = config.checkbox_to_value(boxcar2_notify_onsnatch)
        sickbeard.BOXCAR2_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(boxcar2_notify_ondownload)
        sickbeard.BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(boxcar2_notify_onsubtitledownload)
        key = boxcar2_access_token.strip()
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
        sickbeard.TRAKT_UPDATE_COLLECTION = build_config(**kwargs)
        # sickbeard.trakt_checker_scheduler.silent = not sickbeard.USE_TRAKT
        # sickbeard.TRAKT_DEFAULT_INDEXER = int(trakt_default_indexer)
        # sickbeard.TRAKT_SYNC = config.checkbox_to_value(trakt_sync)
        # sickbeard.TRAKT_USE_WATCHLIST = config.checkbox_to_value(trakt_use_watchlist)
        # sickbeard.TRAKT_METHOD_ADD = int(trakt_method_add)
        # sickbeard.TRAKT_REMOVE_WATCHLIST = config.checkbox_to_value(trakt_remove_watchlist)
        # sickbeard.TRAKT_REMOVE_SERIESLIST = config.checkbox_to_value(trakt_remove_serieslist)
        # sickbeard.TRAKT_START_PAUSED = config.checkbox_to_value(trakt_start_paused)

        sickbeard.USE_SLACK = config.checkbox_to_value(use_slack)
        sickbeard.SLACK_NOTIFY_ONSNATCH = config.checkbox_to_value(slack_notify_onsnatch)
        sickbeard.SLACK_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(slack_notify_ondownload)
        sickbeard.SLACK_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(slack_notify_onsubtitledownload)
        sickbeard.SLACK_ACCESS_TOKEN = slack_access_token
        sickbeard.SLACK_CHANNEL = slack_channel
        sickbeard.SLACK_AS_AUTHED = config.checkbox_to_value(slack_as_authed)
        sickbeard.SLACK_BOT_NAME = slack_bot_name
        sickbeard.SLACK_ICON_URL = slack_icon_url

        sickbeard.USE_DISCORD = config.checkbox_to_value(use_discord)
        sickbeard.DISCORD_NOTIFY_ONSNATCH = config.checkbox_to_value(discord_notify_onsnatch)
        sickbeard.DISCORD_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(discord_notify_ondownload)
        sickbeard.DISCORD_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(discord_notify_onsubtitledownload)
        sickbeard.DISCORD_ACCESS_TOKEN = discord_access_token
        sickbeard.DISCORD_AS_AUTHED = config.checkbox_to_value(discord_as_authed)
        sickbeard.DISCORD_USERNAME = discord_username
        sickbeard.DISCORD_ICON_URL = discord_icon_url
        sickbeard.DISCORD_AS_TTS = config.checkbox_to_value(discord_as_tts)

        sickbeard.USE_GITTER = config.checkbox_to_value(use_gitter)
        sickbeard.GITTER_NOTIFY_ONSNATCH = config.checkbox_to_value(gitter_notify_onsnatch)
        sickbeard.GITTER_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(gitter_notify_ondownload)
        sickbeard.GITTER_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(gitter_notify_onsubtitledownload)
        sickbeard.GITTER_ACCESS_TOKEN = gitter_access_token
        sickbeard.GITTER_ROOM = gitter_room

        sickbeard.USE_TELEGRAM = config.checkbox_to_value(use_telegram)
        sickbeard.TELEGRAM_NOTIFY_ONSNATCH = config.checkbox_to_value(telegram_notify_onsnatch)
        sickbeard.TELEGRAM_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(telegram_notify_ondownload)
        sickbeard.TELEGRAM_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(telegram_notify_onsubtitledownload)
        sickbeard.TELEGRAM_ACCESS_TOKEN = telegram_access_token
        sickbeard.TELEGRAM_CHATID = telegram_chatid
        sickbeard.TELEGRAM_SEND_IMAGE = config.checkbox_to_value(telegram_send_image)
        sickbeard.TELEGRAM_QUIET = config.checkbox_to_value(telegram_quiet)

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
        sickbeard.PYTIVO_HOST = config.clean_host(pytivo_host)
        sickbeard.PYTIVO_SHARE_NAME = pytivo_share_name
        sickbeard.PYTIVO_TIVO_NAME = pytivo_tivo_name

        sickbeard.USE_PUSHBULLET = config.checkbox_to_value(use_pushbullet)
        sickbeard.PUSHBULLET_NOTIFY_ONSNATCH = config.checkbox_to_value(pushbullet_notify_onsnatch)
        sickbeard.PUSHBULLET_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(pushbullet_notify_ondownload)
        sickbeard.PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(pushbullet_notify_onsubtitledownload)
        key = pushbullet_access_token.strip()
        if not starify(key, True):
            sickbeard.PUSHBULLET_ACCESS_TOKEN = key
        sickbeard.PUSHBULLET_DEVICE_IDEN = pushbullet_device_iden

        sickbeard.save_config()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/notifications/')


class ConfigSubtitles(Config):

    def index(self):
        t = PageTemplate(web_handler=self, file='config_subtitles.tmpl')
        t.submenu = self.config_menu('Subtitle')
        return t.respond()

    def save_subtitles(self, use_subtitles=None, subtitles_languages=None, subtitles_dir=None,
                       service_order=None, subtitles_history=None, subtitles_finder_interval=None,
                       subtitles_finder_frequency=None,
                       os_hash=None, os_user='', os_pass=''):

        # prevent deprecated var issues from existing ui, delete in future, added 2020.11.07
        if None is subtitles_finder_interval and None is not subtitles_finder_frequency:
            subtitles_finder_interval = subtitles_finder_frequency

        results = []

        if '' == subtitles_finder_interval or None is subtitles_finder_interval:
            subtitles_finder_interval = 1

        config.schedule_subtitles(config.checkbox_to_value(use_subtitles))
        sickbeard.SUBTITLES_LANGUAGES = [lang.alpha2 for lang in subtitles.is_valid_language(
            subtitles_languages.replace(' ', '').split(','))] if '' != subtitles_languages else ''
        sickbeard.SUBTITLES_DIR = subtitles_dir
        sickbeard.SUBTITLES_HISTORY = config.checkbox_to_value(subtitles_history)
        sickbeard.SUBTITLES_FINDER_INTERVAL = config.to_int(subtitles_finder_interval, default=1)
        sickbeard.SUBTITLES_OS_HASH = config.checkbox_to_value(os_hash)

        # Subtitles services
        services_str_list = service_order.split()
        subtitles_services_list = []
        subtitles_services_enabled = []
        for cur_service in services_str_list:
            service, enabled = cur_service.split(':')
            subtitles_services_list.append(service)
            subtitles_services_enabled.append(int(enabled))

        sickbeard.SUBTITLES_SERVICES_LIST = subtitles_services_list
        sickbeard.SUBTITLES_SERVICES_ENABLED = subtitles_services_enabled
        sickbeard.SUBTITLES_SERVICES_AUTH = [[os_user, os_pass]]

        sickbeard.save_config()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/subtitles/')


class ConfigAnime(Config):

    def index(self):

        t = PageTemplate(web_handler=self, file='config_anime.tmpl')
        t.submenu = self.config_menu('Anime')
        return t.respond()

    def save_anime(self, use_anidb=None, anidb_username=None, anidb_password=None, anidb_use_mylist=None,
                   anime_treat_as_hdtv=None):

        results = []

        sickbeard.USE_ANIDB = config.checkbox_to_value(use_anidb)
        sickbeard.ANIDB_USERNAME = anidb_username
        if set('*') != set(anidb_password):
            sickbeard.ANIDB_PASSWORD = anidb_password
        sickbeard.ANIDB_USE_MYLIST = config.checkbox_to_value(anidb_use_mylist)
        sickbeard.ANIME_TREAT_AS_HDTV = config.checkbox_to_value(anime_treat_as_hdtv)

        sickbeard.save_config()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br>\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        self.redirect('/config/anime/')


class UI(MainHandler):

    @staticmethod
    def add_message():
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


class EventLogs(MainHandler):

    @staticmethod
    def error_logs_menu():
        menu = [{'title': 'Download Log', 'path': 'events/download-log/'}]
        if len(classes.ErrorViewer.errors):
            menu += [{'title': 'Clear Errors', 'path': 'errors/clear-log/'}]
        return menu

    def index(self):

        t = PageTemplate(web_handler=self, file='errorlogs.tmpl')
        t.submenu = self.error_logs_menu

        return t.respond()

    def clear_log(self):
        classes.ErrorViewer.clear()
        self.redirect('/events/')

    def download_log(self):
        logfile_name = logger.current_log_file()
        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Description', 'Logfile Download')
        self.set_header('Content-Length', ek.ek(os.path.getsize, logfile_name))
        self.set_header('Content-Disposition', 'attachment; filename=sickgear.log')
        with open(logfile_name, 'rb') as logfile:
            while True:
                try:
                    data = logfile.read(4096)
                    if not data:
                        break
                    self.write(data)
                except (BaseException, Exception):
                    break

    def view_log(self, min_level=logger.MESSAGE, max_lines=500):

        t = PageTemplate(web_handler=self, file='viewlogs.tmpl')
        t.submenu = self.error_logs_menu

        min_level = int(min_level)

        regex = re.compile(r'^\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2}\s*([A-Z]+)\s*([^\s]+)\s+:{2}\s*(.*\r?\n)$')

        final_data = []
        normal_data = []
        truncate = []
        repeated = None
        num_lines = 0
        if os.path.isfile(logger.sb_log_instance.log_file_path):
            for x in logger.sb_log_instance.reverse_readline(logger.sb_log_instance.log_file_path):

                x = helpers.xhtml_escape(decode_str(x, errors='replace'), False)
                try:
                    match = regex.findall(x)[0]
                except(BaseException, Exception):
                    if not any(normal_data) and not any([x.strip()]):
                        continue

                    normal_data.append(re.sub(r'\r?\n', '<br>', x))
                else:
                    level, log = match[0], ' '.join(match[1:])
                    if level not in logger.reverseNames:
                        normal_data = []
                        continue

                    if logger.reverseNames[level] < min_level:
                        normal_data = []
                        continue
                    else:
                        if truncate and not normal_data and truncate[0] == log:
                            truncate += [log]
                            repeated = x
                            continue

                        if 1 < len(truncate):
                            final_data[-1] = repeated.strip() + \
                                             ' <span class="grey-text">(...%s repeat lines)</span>\n' % len(truncate)

                        truncate = [log]

                        final_data.append(x.replace(
                            ' Starting SickGear', ' <span class="prelight2">Starting SickGear</span>'))
                        if any(normal_data):
                            final_data += ['<code><span class="prelight">'] + \
                                          ['<span class="prelight-num">%02s)</span> %s' % (n + 1, x)
                                           for n, x in enumerate(normal_data[::-1])] + \
                                          ['</span></code><br>']
                            num_lines += len(normal_data)
                            normal_data = []

                num_lines += 1

                if num_lines >= max_lines:
                    break

        result = ''.join(final_data)

        t.logLines = result
        t.min_level = min_level

        return t.respond()


class WebFileBrowser(MainHandler):

    def index(self, path='', include_files=False, **kwargs):
        """ prevent issues with requests using legacy params """
        include_files = include_files or kwargs.get('includeFiles') or False
        """ /legacy """

        self.set_header('Content-Type', 'application/json')
        return json.dumps(folders_at_path(path, True, bool(int(include_files))))

    def complete(self, term, include_files=0, **kwargs):
        """ prevent issues with requests using legacy params """
        include_files = include_files or kwargs.get('includeFiles') or False
        """ /legacy """

        self.set_header('Content-Type', 'application/json')
        return json.dumps([entry['path'] for entry in folders_at_path(
            os.path.dirname(term), include_files=bool(int(include_files))) if 'path' in entry])


class ApiBuilder(MainHandler):

    def index(self):
        """ expose the api-builder template """
        t = PageTemplate(web_handler=self, file='apiBuilder.tmpl')

        def titler(x):
            return (remove_article(x), x)[not x or sickbeard.SORT_ARTICLE].lower()

        t.sortedShowList = sorted(sickbeard.showList, key=lambda x: titler(x.name))

        season_sql_result = {}
        episode_sql_result = {}

        my_db = db.DBConnection(row_type='dict')
        for cur_show_obj in t.sortedShowList:
            season_sql_result[cur_show_obj.tvid_prodid] = my_db.select(
                'SELECT DISTINCT season'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' ORDER BY season DESC',
                [cur_show_obj.tvid, cur_show_obj.prodid])

        for cur_show_obj in t.sortedShowList:
            episode_sql_result[cur_show_obj.tvid_prodid] = my_db.select(
                'SELECT DISTINCT season,episode'
                ' FROM tv_episodes'
                ' WHERE indexer = ? AND showid = ?'
                ' ORDER BY season DESC, episode DESC',
                [cur_show_obj.tvid, cur_show_obj.prodid])

        t.seasonSQLResults = season_sql_result
        t.episodeSQLResults = episode_sql_result
        t.indexers = sickbeard.TVInfoAPI().all_sources
        t.searchindexers = sickbeard.TVInfoAPI().search_sources

        if len(sickbeard.API_KEYS):
            # use first APIKEY for apibuilder tests
            t.apikey = sickbeard.API_KEYS[0][1]
        else:
            t.apikey = 'api key not generated'

        return t.respond()


class Cache(MainHandler):

    def index(self):
        my_db = db.DBConnection('cache.db')
        sql_result = my_db.select('SELECT * FROM provider_cache')
        if not sql_result:
            sql_result = []

        t = PageTemplate(web_handler=self, file='cache.tmpl')
        t.cacheResults = sql_result

        return t.respond()


class CachedImages(MainHandler):
    def set_default_headers(self):
        super(CachedImages, self).set_default_headers()
        self.set_header('Cache-Control', 'no-cache, max-age=0')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Expires', '0')

    @staticmethod
    def should_try_image(filename, source, days=1, minutes=0):
        result = True
        try:
            dummy_file = '%s.%s.dummy' % (ek.ek(os.path.splitext, filename)[0], source)
            if ek.ek(os.path.isfile, dummy_file):
                if ek.ek(os.stat, dummy_file).st_mtime \
                        < (int(timestamp_near((datetime.datetime.now()
                                               - datetime.timedelta(days=days, minutes=minutes))))):
                    CachedImages.delete_dummy_image(dummy_file)
                else:
                    result = False
        except (BaseException, Exception):
            pass
        return result

    @staticmethod
    def create_dummy_image(filename, source):
        dummy_file = '%s.%s.dummy' % (ek.ek(os.path.splitext, filename)[0], source)
        CachedImages.delete_dummy_image(dummy_file)
        try:
            with open(dummy_file, 'w'):
                pass
        except (BaseException, Exception):
            pass

    @staticmethod
    def delete_dummy_image(dummy_file):
        try:
            if ek.ek(os.path.isfile, dummy_file):
                ek.ek(os.remove, dummy_file)
        except (BaseException, Exception):
            pass

    @staticmethod
    def delete_all_dummy_images(filename):
        for f in ['tmdb', 'tvdb', 'tvmaze']:
            CachedImages.delete_dummy_image('%s.%s.dummy' % (ek.ek(os.path.splitext, filename)[0], f))

    def index(self, path='', source=None, filename=None, tmdbid=None, tvdbid=None, trans=True):

        path = path.strip('/')
        file_name = ''
        if None is not source:
            file_name = ek.ek(os.path.basename, source)
        elif filename not in [None, 0, '0']:
            file_name = filename
        image_file = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'images', path, file_name)
        image_file = ek.ek(os.path.abspath, image_file.replace('\\', '/'))
        if not ek.ek(os.path.isfile, image_file) and has_image_ext(file_name):
            basepath = ek.ek(os.path.dirname, image_file)
            helpers.make_dirs(basepath)
            poster_url = ''
            tmdb_image = False
            if None is not source and source in sickbeard.CACHE_IMAGE_URL_LIST:
                poster_url = source
            if None is source and tmdbid not in [None, 'None', 0, '0'] \
                    and self.should_try_image(image_file, 'tmdb'):
                tmdb_image = True
                try:
                    tvinfo_config = sickbeard.TVInfoAPI(TVINFO_TMDB).api_params.copy()
                    t = sickbeard.TVInfoAPI(TVINFO_TMDB).setup(**tvinfo_config)
                    show_obj = t.get_show(tmdbid, load_episodes=False, posters=True)
                    if show_obj and show_obj.poster:
                        poster_url = show_obj.poster
                except (BaseException, Exception):
                    poster_url = ''
            if poster_url and not sg_helpers.download_file(poster_url, image_file) and poster_url.find('trakt.us'):
                sg_helpers.download_file(poster_url.replace('trakt.us', 'trakt.tv'), image_file)
            if tmdb_image and not ek.ek(os.path.isfile, image_file):
                self.create_dummy_image(image_file, 'tmdb')

            if None is source and tvdbid not in [None, 'None', 0, '0'] \
                    and not ek.ek(os.path.isfile, image_file) \
                    and self.should_try_image(image_file, 'tvdb'):
                try:
                    tvinfo_config = sickbeard.TVInfoAPI(TVINFO_TVDB).api_params.copy()
                    tvinfo_config['posters'] = True
                    t = sickbeard.TVInfoAPI(TVINFO_TVDB).setup(**tvinfo_config)[helpers.try_int(tvdbid), False]
                    if hasattr(t, 'data') and 'poster' in t.data:
                        poster_url = t.data['poster']
                except (BaseException, Exception):
                    poster_url = ''
                if poster_url:
                    sg_helpers.download_file(poster_url, image_file)
                if not ek.ek(os.path.isfile, image_file):
                    self.create_dummy_image(image_file, 'tvdb')

            if ek.ek(os.path.isfile, image_file):
                self.delete_all_dummy_images(image_file)

        if not ek.ek(os.path.isfile, image_file):
            image_file = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick',
                               'images', ('image-light.png', 'trans.png')[bool(int(trans))])
        else:
            helpers.set_file_timestamp(image_file, min_age=3, new_time=None)

        return self.image_data(image_file)

    @staticmethod
    def should_load_image(filename, days=7):
        # type: (AnyStr, integer_types) -> bool
        """
        should image be (re-)loaded

        :param filename: image file name with path
        :param days: max age to trigger reload of image
        """
        if not ek.ek(os.path.isfile, filename) or \
                ek.ek(os.stat, filename).st_mtime < \
                (int(timestamp_near((datetime.datetime.now() - datetime.timedelta(days=days))))):
            return True
        return False

    @staticmethod
    def find_cast_by_id(ref_id, cast_list):
        for cur_item in cast_list:
            if cur_item.has_ref_id(ref_id):
                return cur_item

    def character(self, rid=None, tvid_prodid=None, thumb=True, pid=None, prefer_person=False, **kwargs):
        """

        :param rid:
        :param tvid_prodid:
        :param thumb: return thumb or normal as fallback
        :param pid: optional person_id
        :param prefer_person: prefer person image if person_id is set and character has more then 1 person assigned
        """
        _ = kwargs.get('oid')  # suppress pyc non used var highlight, oid (original id) is a visual ui key
        show_obj = tvid_prodid and helpers.find_show_by_id(tvid_prodid)
        char_id = usable_id(rid)
        person_id = usable_id(pid)
        if not show_obj or not char_id:
            return
        char_obj = self.find_cast_by_id(char_id, show_obj.cast_list)
        if not char_obj:
            return
        if person_id:
            person_obj = TVPerson(sid=person_id)
            person_id = person_obj.id  # a reference could be passed in, replace it with id for later use
            if not char_obj.person or person_obj not in char_obj.person:
                person_obj = None
        else:
            person_obj = None
        thumb = thumb in (True, '1', 'true', 'True')
        prefer_person = prefer_person in (True, '1', 'true', 'True') and char_obj.person and 1 < len(char_obj.person) \
            and bool(person_obj)

        image_file = None
        if not prefer_person and (char_obj.thumb_url or char_obj.image_url):
            image_cache_obj = image_cache.ImageCache()
            image_normal, image_thumb = image_cache_obj.character_both_path(char_obj, show_obj, person_obj=person_obj)
            sg_helpers.make_dirs(image_cache_obj.characters_dir)
            if self.should_load_image(image_normal) and char_obj.image_url:
                sg_helpers.download_file(char_obj.image_url, image_normal)
            if self.should_load_image(image_thumb) and char_obj.thumb_url:
                sg_helpers.download_file(char_obj.thumb_url, image_thumb)

            primary, fallback = ((image_normal, image_thumb), (image_thumb, image_normal))[thumb]
            if ek.ek(os.path.isfile, primary):
                image_file = primary
            elif ek.ek(os.path.isfile, fallback):
                image_file = fallback

        elif person_id:
            return self.person(rid=char_id, pid=person_id, show_obj=show_obj, thumb=thumb)
        elif char_obj.person and (char_obj.person[0].thumb_url or char_obj.person[0].image_url):
            return self.person(rid=char_id, pid=char_obj.person[0].id, show_obj=show_obj, thumb=thumb)

        return self.image_data(image_file, cast_default=True)

    def person(self, rid=None, pid=None, tvid_prodid=None, show_obj=None, thumb=True, **kwargs):
        _ = kwargs.get('oid')  # suppress pyc non used var highlight, oid (original id) is a visual ui key
        show_obj = show_obj or tvid_prodid and helpers.find_show_by_id(tvid_prodid)
        char_id = usable_id(rid)
        person_id = usable_id(pid)
        if not person_id:
            return
        person_obj = TVPerson(sid=person_id)
        if char_id and show_obj and not person_obj:
            char_obj = self.find_cast_by_id(char_id, show_obj.cast_list)
            person_obj = char_obj.person and char_obj.person[0]
        if not person_obj:
            return
        thumb = thumb in (True, '1', 'true', 'True')

        image_file = None
        if person_obj.thumb_url or person_obj.image_url:
            image_cache_obj = image_cache.ImageCache()
            image_normal, image_thumb = image_cache_obj.person_both_paths(person_obj)
            sg_helpers.make_dirs(image_cache_obj.characters_dir)
            if self.should_load_image(image_normal) and person_obj.image_url:
                sg_helpers.download_file(person_obj.image_url, image_normal)
            if self.should_load_image(image_thumb) and person_obj.thumb_url:
                sg_helpers.download_file(person_obj.thumb_url, image_thumb)

            primary, fallback = ((image_normal, image_thumb), (image_thumb, image_normal))[thumb]
            if ek.ek(os.path.isfile, primary):
                image_file = primary
            elif ek.ek(os.path.isfile, fallback):
                image_file = fallback

        return self.image_data(image_file, cast_default=True)

    def image_data(self, image_file, cast_default=False):
        # type: (Optional[AnyStr], bool) -> Optional[Any]
        """
        return image file binary data

        :param image_file: file path
        :param cast_default: if required, use default cast file path if None is image_file
        :return: binary image data or None
        """
        if cast_default and None is image_file:
            image_file = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', 'poster-person.jpg')

        mime_type, encoding = MimeTypes().guess_type(image_file)
        self.set_header('Content-Type', mime_type)
        with open(image_file, 'rb') as io_stream:
            return io_stream.read()

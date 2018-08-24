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
import glob
import hashlib
import itertools
import io
import os
import random
import re
import sys
import time
import traceback
import urllib
import threading
import zipfile

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
from sickbeard.common import SNATCHED, SNATCHED_ANY, UNAIRED, IGNORED, ARCHIVED, WANTED, FAILED, SKIPPED, DOWNLOADED
from sickbeard.common import SD, HD720p, HD1080p, UHD2160p
from sickbeard.exceptions import ex, MultipleShowObjectsException
from sickbeard.helpers import has_image_ext, remove_article, starify
from sickbeard.indexers.indexer_config import INDEXER_TVDB, INDEXER_TVRAGE, INDEXER_TRAKT
from sickbeard.scene_numbering import get_scene_numbering, set_scene_numbering, get_scene_numbering_for_show, \
    get_xem_numbering_for_show, get_scene_absolute_numbering_for_show, get_xem_absolute_numbering_for_show, \
    get_scene_absolute_numbering, set_scene_numbering_helper
from sickbeard.name_cache import buildNameCache
from sickbeard.browser import foldersAtPath
from sickbeard.blackandwhitelist import BlackAndWhiteList, short_group_names
from sickbeard.search_backlog import FORCED_BACKLOG
from sickbeard.indexermapper import MapStatus, save_mapping, map_indexers_to_show
from sickbeard.tv import show_not_found_retry_days, concurrent_show_not_found_days
from tornado import gen
from tornado.web import RequestHandler, StaticFileHandler, authenticated
from tornado import escape
from lib import adba
from lib import subliminal
from lib.dateutil import tz
import lib.rarfile.rarfile as rarfile
from unidecode import unidecode

from lib.libtrakt import TraktAPI
from lib.libtrakt.exceptions import TraktException, TraktAuthException
from lib.libtrakt.indexerapiinterface import TraktSearchTypes
from trakt_helpers import build_config, trakt_collection_remove_account
from sickbeard.bs4_parser import BS4Parser

from lib.fuzzywuzzy import fuzz
from lib.tmdb_api import TMDB
from lib.tvdb_api.tvdb_exceptions import tvdb_exception

try:
    import json
except ImportError:
    from lib import simplejson as json


class PageTemplate(Template):
    def __init__(self, web_handler, *args, **kwargs):

        headers = web_handler.request.headers
        self.xsrf_form_html = re.sub('\s*/>$', '>', web_handler.xsrf_form_html())
        self.sbHost = headers.get('X-Forwarded-Host')
        if None is self.sbHost:
            sbHost = headers.get('Host') or 'localhost'
            self.sbHost = re.match('(?msx)^' + (('[^:]+', '\[.*\]')['[' == sbHost[0]]), sbHost).group(0)
        self.sbHttpPort = sickbeard.WEB_PORT
        self.sbHttpsPort = headers.get('X-Forwarded-Port') or self.sbHttpPort
        self.sbRoot = sickbeard.WEB_ROOT
        self.sbHttpsEnabled = 'https' == headers.get('X-Forwarded-Proto') or sickbeard.ENABLE_HTTPS
        self.sbHandleReverseProxy = sickbeard.HANDLE_REVERSE_PROXY
        self.sbThemeName = sickbeard.THEME_NAME

        self.log_num_errors = len(classes.ErrorViewer.errors)
        self.log_num_not_found_shows = len([x for x in sickbeard.showList if 0 < x.not_found_count])
        self.log_num_not_found_shows_all = len([x for x in sickbeard.showList if 0 != x.not_found_count])
        self.sbPID = str(sickbeard.PID)
        self.menu = [
            {'title': 'Home', 'key': 'home'},
            {'title': 'Episodes', 'key': 'episodeView'},
            {'title': 'History', 'key': 'history'},
            {'title': 'Manage', 'key': 'manage'},
            {'title': 'Config', 'key': 'config'},
        ]

        kwargs['file'] = os.path.join(sickbeard.PROG_DIR, 'gui/%s/interfaces/default/' %
                                      sickbeard.GUI_NAME, kwargs['file'])
        super(PageTemplate, self).__init__(*args, **kwargs)

    def compile(self, *args, **kwargs):
        if not os.path.exists(os.path.join(sickbeard.CACHE_DIR, 'cheetah')):
            os.mkdir(os.path.join(sickbeard.CACHE_DIR, 'cheetah'))

        kwargs['cacheModuleFilesForTracebacks'] = True
        kwargs['cacheDirForModuleFiles'] = os.path.join(sickbeard.CACHE_DIR, 'cheetah')
        return super(PageTemplate, self).compile(*args, **kwargs)


class BaseStaticFileHandler(StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')
        if sickbeard.SEND_SECURITY_HEADERS:
            self.set_header('X-Frame-Options', 'SAMEORIGIN')


class BaseHandler(RequestHandler):
    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')
        if sickbeard.SEND_SECURITY_HEADERS:
            self.set_header('X-Frame-Options', 'SAMEORIGIN')

    def redirect(self, url, permanent=False, status=None):
        if not url.startswith(sickbeard.WEB_ROOT):
            url = sickbeard.WEB_ROOT + url

        super(BaseHandler, self).redirect(url, permanent, status)

    def get_current_user(self, *args, **kwargs):
        if sickbeard.WEB_USERNAME or sickbeard.WEB_PASSWORD:
            return self.get_secure_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT))
        return True

    def getImage(self, image):
        if ek.ek(os.path.isfile, image):
            mime_type, encoding = MimeTypes().guess_type(image)
            self.set_header('Content-Type', mime_type)
            with ek.ek(open, image, 'rb') as img:
                return img.read()

    def showPoster(self, show=None, which=None, api=None):
        # Redirect initial poster/banner thumb to default images
        if 'poster' == which[0:6]:
            default_image_name = 'poster.png'
        elif 'banner' == which[0:6]:
            default_image_name = 'banner.png'
        else:
            default_image_name = 'backart.png'

        static_image_path = os.path.join('/images', default_image_name)
        if show and sickbeard.helpers.findCertainShow(sickbeard.showList, int(show)):
            cache_obj = image_cache.ImageCache()

            image_file_name = None
            if 'poster' == which:
                image_file_name = cache_obj.poster_path(show)
            elif 'poster_thumb' == which:
                image_file_name = cache_obj.poster_thumb_path(show)
            elif 'banner' == which:
                image_file_name = cache_obj.banner_path(show)
            elif 'banner_thumb' == which:
                image_file_name = cache_obj.banner_thumb_path(show)
            elif 'fanart' == which[0:6]:
                image_file_name = cache_obj.fanart_path('%s%s' % (
                    show, re.sub('.*?fanart_(\d+(?:\.\w{1,20})?\.(?:\w{5,8})).*', r'.\1', which, 0, re.I)))

            if ek.ek(os.path.isfile, image_file_name):
                static_image_path = image_file_name

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
    def get(self, *args, **kwargs):
        if self.get_current_user():
            self.redirect(self.get_argument('next', '/home/'))
        else:
            t = PageTemplate(web_handler=self, file='login.tmpl')
            t.resp = self.get_argument('resp', '')
            self.set_status(401)
            self.finish(t.respond())

    def post(self, *args, **kwargs):
        username = sickbeard.WEB_USERNAME
        password = sickbeard.WEB_PASSWORD

        if (self.get_argument('username') == username) and (self.get_argument('password') == password):
            params = dict(expires_days=(None, 30)[int(self.get_argument('remember_me', default=0) or 0) > 0],
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
    def get(self, *args, **kwargs):
        self.clear_cookie('sickgear-session-%s' % helpers.md5_for_text(sickbeard.WEB_PORT))
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
        utc = tz.gettz('GMT', zoneinfo_priority=True)

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
                    + u'SUMMARY:%s - %sx%s - %s%s' % (show['show_name'], episode['season'], episode['episode'], episode['name'], crlf)\
                    + u'UID:%s-%s-%s-E%sS%s%s' % (appname, datetime.date.today().isoformat(), show['show_name'].replace(' ', '-'), episode['episode'], episode['season'], crlf)\
                    + u'DESCRIPTION:%s on %s' % ((show['airs'] or '(Unknown airs)'), (show['network'] or 'Unknown network'))\
                    + ('' if not episode['description'] else u'%s%s' % (nl, episode['description'].splitlines()[0]))\
                    + '%sEND:VEVENT%s' % (crlf, crlf)

        # Ending the iCal
        return ical + 'END:VCALENDAR'


class RepoHandler(BaseStaticFileHandler):

    def get(self, path, include_body=True, *args, **kwargs):
        super(RepoHandler, self).get(path, include_body)
        logger.log('Kodi req... get(path): %s' % path, logger.DEBUG)

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
            with io.open(repo_md5_file, 'r') as fh:
                saved_md5 = fh.readline()
        except(StandardError, Exception):
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
                for f in helpers.scantree(zip_path, ['resources']):
                    if f.is_file(follow_symlinks=False) and f.name[-4:] in ('.zip', '.md5'):
                        try:
                            ek.ek(os.remove, f.path)
                        except OSError:
                            logger.log('Unable to delete %s: %r / %s' % (f.path, e, str(e)), logger.WARNING)
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
                (('service.sickgear.watchedstate.updater', 'resources', 'language', 'English', 'strings.xml'),
                 (cache_client_kodi_watchedstate, 'resources', 'language', 'English', 'strings.xml')),
        ):
            helpers.copyFile(ek.ek(
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
        return re.findall('(?si)addon\sid="(repository\.[^"]+)[^>]+version="([^"]+)',
                          self.render_kodi_repo_addon_xml())[0]

    def addon_watchedstate_details(self):
        return re.findall('(?si)addon\sid="([^"]+)[^>]+version="([^"]+)',
                          self.get_watchedstate_updater_addon_xml())[0]

    @staticmethod
    def get_watchedstate_updater_addon_xml():
        with io.open(ek.ek(os.path.join, sickbeard.PROG_DIR, 'sickbeard', 'clients',
                        'kodi', 'service.sickgear.watchedstate.updater', 'addon.xml'), 'r') as fh:
            return fh.read().strip()

    def render_kodi_repo_addon_xml(self):
        t = PageTemplate(web_handler=self, file='repo_kodi_addon.tmpl')
        return t.respond().strip()

    def render_kodi_repo_addons_xml(self):
        t = PageTemplate(web_handler=self, file='repo_kodi_addons.tmpl')
        t.watchedstate_updater_addon_xml = re.sub(
            '(?m)^([\s]*<)', r'\t\1',
            '\n'.join(self.get_watchedstate_updater_addon_xml().split('\n')[1:]))  # skip xml header

        t.repo_xml = re.sub(
            '(?m)^([\s]*<)', r'\t\1',
            '\n'.join(self.render_kodi_repo_addon_xml().split('\n')[1:]))

        return t.respond()

    def render_kodi_repo_addons_xml_md5(self):
        return self.md5ify('\n'.join(self.render_kodi_repo_addons_xml().split('\n')[1:]))

    @staticmethod
    def md5ify(string):
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
            logger.log('Unable to zip %s: %r / %s' % (f.path, e, str(e)), logger.WARNING)

        zip_data = bfr.getvalue()
        bfr.close()
        return zip_data

    @staticmethod
    def kodi_service_sickgear_watchedstate_updater_zip():
        bfr = io.BytesIO()

        basepath = ek.ek(os.path.join, sickbeard.PROG_DIR, 'sickbeard', 'clients', 'kodi')

        zip_path = ek.ek(os.path.join, basepath, 'service.sickgear.watchedstate.updater')
        devenv_src = ek.ek(os.path.join, sickbeard.PROG_DIR, 'tests', '_devenv.py')
        devenv_dst = ek.ek(os.path.join, zip_path, '_devenv.py')
        if sickbeard.ENV.get('DEVENV') and ek.ek(os.path.exists, devenv_src):
            helpers.copyFile(devenv_src, devenv_dst)
        else:
            helpers.remove_file_failed(devenv_dst)

        for f in helpers.scantree(zip_path):
            if f.is_file(follow_symlinks=False) and f.name[-4:] not in '.xcf':
                try:
                    with io.open(f.path, 'rb') as fh:
                        infile = fh.read()

                    with zipfile.ZipFile(bfr, 'a') as zh:
                        zh.writestr(ek.ek(os.path.relpath, f.path, basepath), infile, zipfile.ZIP_DEFLATED)
                except OSError as e:
                    logger.log('Unable to zip %s: %r / %s' % (f.path, e, str(e)), logger.WARNING)

        zip_data = bfr.getvalue()
        bfr.close()
        return zip_data


class NoXSRFHandler(RequestHandler):
    def __init__(self, *arg, **kwargs):

        super(NoXSRFHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    def check_xsrf_cookie(self):
        pass

    @gen.coroutine
    def post(self, route, *args, **kwargs):
        route = route.strip('/')
        try:
            method = getattr(self, route)
        except (StandardError, Exception):
            self.finish()
        else:
            kwargss = {k: v if not (isinstance(v, list) and 1 == len(v)) else v[0]
                       for k, v in self.request.arguments.iteritems()}
            result = method(**kwargss)
            if result:
                self.finish(result)

    @staticmethod
    def update_watched_state_kodi(payload=None, as_json=True):
        data = {}
        try:
            data = json.loads(payload)
        except (StandardError, Exception):
            pass

        mapped = 0
        mapping = None
        maps = [x.split('=') for x in sickbeard.KODI_PARENT_MAPS.split(',') if any(x)]
        for k, d in data.iteritems():
            try:
                d['label'] = '%s%s{Kodi}' % (d['label'], bool(d['label']) and ' ' or '')
            except (StandardError, Exception):
                return
            try:
                d['played'] = 100 * int(d['played'])
            except (StandardError, Exception):
                d['played'] = 0

            for m in maps:
                result, change = helpers.path_mapper(m[0], m[1], d['path_file'])
                if change:
                    if not mapping:
                        mapping = (states[idx]['path_file'], result)
                    mapped += 1
                    states[idx]['path_file'] = result
                    break

        if mapping:
            logger.log('Folder mappings used, the first of %s is [%s] in Kodi is [%s] in SickGear' %
                       (mapped, mapping[0], mapping[1]))

        return MainHandler.update_watched_state(data, as_json)


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
        t = PageTemplate(web_handler=self, file='404.tmpl')
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
            kwargss = {k: v if not (isinstance(v, list) and 1 == len(v)) else v[0]
                       for k, v in self.request.arguments.iteritems() if '_xsrf' != k}
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

    def setEpisodeViewCards(self, redir=0, *args, **kwargs):

        sickbeard.EPISODE_VIEW_POSTERS = not sickbeard.EPISODE_VIEW_POSTERS

        sickbeard.save_config()

        if int(redir):
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
        qualities = Quality.SNATCHED + Quality.DOWNLOADED + Quality.ARCHIVED + [IGNORED, SKIPPED]

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
            % ','.join(['?'] * len(Quality.SNATCHED + Quality.DOWNLOADED)),
            done_show_list + [next_week] + Quality.SNATCHED + Quality.DOWNLOADED)

        sql_results += myDB.select(
            'SELECT *, tv_shows.status as show_status FROM tv_episodes, tv_shows WHERE season != 0 AND tv_shows.indexer_id = tv_episodes.showid AND airdate <= ? AND airdate >= ? AND tv_episodes.status = ? AND tv_episodes.status NOT IN (%s)'
            % ','.join(['?'] * len(qualities)),
            [tomorrow, recently, WANTED] + qualities)

        sql_results = list(set(sql_results))

        # make a dict out of the sql results
        sql_results = [dict(row) for row in sql_results
                       if Quality.splitCompositeStatus(helpers.tryInt(row['status']))[0] not in
                       SNATCHED_ANY + [DOWNLOADED, ARCHIVED, IGNORED, SKIPPED]]

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
        cache_obj = image_cache.ImageCache()
        t = PageTemplate(web_handler=self, file='episodeView.tmpl')
        t.fanart = {}
        for index, item in enumerate(sql_results):
            sql_results[index]['localtime'] = sbdatetime.sbdatetime.convert_to_setting(network_timezones.parse_date_time(item['airdate'],
                                                                                       item['airs'], item['network']))
            sql_results[index]['data_show_name'] = value_maybe_article(item['show_name'])
            sql_results[index]['data_network'] = value_maybe_article(item['network'])

            imdb_id = None
            if item['imdb_id']:
                try:
                    imdb_id = helpers.tryInt(re.search(r'(\d+)', item['imdb_id']).group(1))
                except (StandardError, Exception):
                    pass
            if imdb_id:
                sql_results[index]['imdb_url'] = sickbeard.indexers.indexer_config.indexerConfig[
                    sickbeard.indexers.indexer_config.INDEXER_IMDB]['show_url'] % imdb_id
            else:
                sql_results[index]['imdb_url'] = ''

            show_id = item['showid']
            if show_id in t.fanart:
                continue

            for img in ek.ek(glob.glob, cache_obj.fanart_path(show_id).replace('fanart.jpg', '*')) or []:
                match = re.search(r'\.(\d+(?:\.\w*)?\.(?:\w{5,8}))\.fanart\.', img, re.I)
                if not match:
                    continue
                fanart = [(match.group(1), sickbeard.FANART_RATINGS.get(str(show_id), {}).get(match.group(1), ''))]
                if show_id not in t.fanart:
                    t.fanart[show_id] = fanart
                else:
                    t.fanart[show_id] += fanart

        for show in t.fanart:
            fanart_rating = [(n, v) for n, v in t.fanart[show] if 20 == v]
            if fanart_rating:
                t.fanart[show] = fanart_rating
            else:
                rnd = [(n, v) for (n, v) in t.fanart[show] if 30 != v]
                grouped = [(n, v) for (n, v) in rnd if 10 == v]
                if grouped:
                    t.fanart[show] = [grouped[random.randint(0, len(grouped) - 1)]]
                elif rnd:
                    t.fanart[show] = [rnd[random.randint(0, len(rnd) - 1)]]

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

        sql_results.sort(sorts[sickbeard.EPISODE_VIEW_SORT])

        t.next_week = datetime.datetime.combine(next_week_dt, datetime.time(tzinfo=network_timezones.sb_timezone))
        t.today = datetime.datetime.now(network_timezones.sb_timezone)
        t.sql_results = sql_results

        return t.respond()

    def live_panel(self, *args, **kwargs):

        if 'allseasons' in kwargs:
            sickbeard.DISPLAY_SHOW_MINIMUM = bool(config.minimax(kwargs['allseasons'], 0, 0, 1))
        elif 'rate' in kwargs:
            which = kwargs['which'].replace('fanart_', '')
            rating = int(kwargs['rate'])
            if rating:
                sickbeard.FANART_RATINGS.setdefault(kwargs['show'], {}).update({which: rating})
            elif sickbeard.FANART_RATINGS.get(kwargs['show'], {}).get(which):
                del sickbeard.FANART_RATINGS[kwargs['show']][which]
                if not sickbeard.FANART_RATINGS[kwargs['show']]:
                    del sickbeard.FANART_RATINGS[kwargs['show']]
        else:
            translucent = bool(config.minimax(kwargs.get('translucent'), 0, 0, 1))
            backart = bool(config.minimax(kwargs.get('backart'), 0, 0, 1))
            viewmode = config.minimax(kwargs.get('viewmode'), 0, 0, 2)

            if 'ds' == kwargs.get('pg', None):
                if 'viewart' in kwargs:
                    sickbeard.DISPLAY_SHOW_VIEWART = config.minimax(kwargs['viewart'], 0, 0, 2)
                elif 'translucent' in kwargs:
                    sickbeard.DISPLAY_SHOW_BACKGROUND_TRANSLUCENT = translucent
                elif 'backart' in kwargs:
                    sickbeard.DISPLAY_SHOW_BACKGROUND = backart
                elif 'viewmode' in kwargs:
                    sickbeard.DISPLAY_SHOW_VIEWMODE = viewmode
            elif 'ev' == kwargs.get('pg', None):
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
    def getFooterTime(change_layout=True, json_dump=True, *args, **kwargs):

        now = datetime.datetime.now()
        events = [
            ('recent', sickbeard.recentSearchScheduler.timeLeft),
            ('backlog', sickbeard.backlogSearchScheduler.next_backlog_timeleft),
        ]

        if sickbeard.DOWNLOAD_PROPERS:
            events += [('propers', sickbeard.properFinder.next_proper_timeleft)]

        if change_layout not in (False, 0, '0', '', None):
            sickbeard.FOOTER_TIME_LAYOUT += 1
            if sickbeard.FOOTER_TIME_LAYOUT == 2:  # 2 layouts = time + delta
                sickbeard.FOOTER_TIME_LAYOUT = 0
            sickbeard.save_config()

        next_event = []
        for k, v in events:
            try:
                t = v()
            except AttributeError:
                t = None
            if 0 == sickbeard.FOOTER_TIME_LAYOUT:
                next_event += [{k + '_time': t and sbdatetime.sbdatetime.sbftime(now + t, markup=True) or 'soon'}]
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
                key01=dict(path_file='\\media\\path\\', played=100, label='Bob', date_watched=1509850398.0),
                key02=dict(path_file='\\media\\path\\file-played1.mkv', played=100, label='Sue', date_watched=1509850398.0),
                key03=dict(path_file='\\media\\path\\file-played2.mkv', played=0, label='Rita', date_watched=1509850398.0)
            )
            JSON: '{"key01": {"path_file": "\\media\\path\\file_played1.mkv", "played": 100, "label": "Bob", "date_watched": 1509850398.0}}'
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

        sql_results = None
        if data:
            my_db = db.DBConnection(row_type='dict')

            media_paths = map(lambda (_, d): ek.ek(os.path.basename, d['path_file']), data.iteritems())
            sql_results = my_db.select(
                'SELECT episode_id, status, location, file_size FROM tv_episodes WHERE file_size > 0 AND (%s)' %
                ' OR '.join(['location LIKE "%%%s"' % x for x in media_paths]))

        if sql_results:
            cl = []

            ep_results = {}
            map(lambda r: ep_results.update({'%s' % ek.ek(os.path.basename, r['location']).lower(): dict(
                episode_id=r['episode_id'], status=r['status'], location=r['location'], file_size=r['file_size'])}),
                sql_results)

            for (k, v) in iteritems(data):

                bname = (ek.ek(os.path.basename, v.get('path_file')) or '').lower()
                if not bname:
                    msg = 'Missing media file name provided'
                    data[k] = msg
                    logger.log('Update watched state skipped an item: %s' % msg, logger.WARNING)
                    continue

                if bname in ep_results:
                    date_watched = now = sbdatetime.sbdatetime.now().totimestamp(default=0)
                    if 1500000000 < date_watched:
                        date_watched = sickbeard.helpers.tryInt(float(v.get('date_watched')))

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
                my_db.mass_action(cl)

        if as_json:
            if not data:
                data = dict(error='Request made to SickGear with invalid payload')
                logger.log('Update watched state failed: %s' % data['error'], logger.WARNING)

            return json.dumps(data)

    def toggleDisplayShowSpecials(self, show):

        sickbeard.DISPLAY_SHOW_SPECIALS = not sickbeard.DISPLAY_SHOW_SPECIALS

        self.redirect('/home/displayShow?show=' + show)

    def setHistoryLayout(self, layout):

        if layout not in ('compact', 'detailed', 'compact_watched', 'detailed_watched',
                          'compact_stats', 'graph_stats', 'provider_failures'):
            layout = 'detailed'

        sickbeard.HISTORY_LAYOUT = layout

        self.redirect('/history/')

    def _genericMessage(self, subject, message):
        t = PageTemplate(web_handler=self, file='genericMessage.tmpl')
        t.submenu = self.HomeMenu()
        t.subject = subject
        t.message = message
        return t.respond()


class Home(MainHandler):
    def HomeMenu(self):
        return [
            {'title': 'Process Media', 'path': 'home/postprocess/'},
            {'title': 'Update Emby', 'path': 'home/update_emby/', 'requires': self.haveEMBY},
            {'title': 'Update Kodi', 'path': 'home/update_kodi/', 'requires': self.haveKODI},
            {'title': 'Update XBMC', 'path': 'home/update_xbmc/', 'requires': self.haveXBMC},
            {'title': 'Update Plex', 'path': 'home/update_plex/', 'requires': self.havePLEX}
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
        t = PageTemplate(web_handler=self, file='home.tmpl')
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
        else:
            items = []
            default = 0
            for index, group in enumerate(t.showlists):
                items += group[2]
                default = (default, index)['Show List' == group[1]]
            t.showlists[default][2] += [show for show in sickbeard.showList if show not in items]

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
        status_quality = ','.join([str(x) for x in Quality.SNATCHED_ANY])
        status_download = ','.join([str(x) for x in Quality.DOWNLOADED + Quality.ARCHIVED])
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

        connection, acces_msg = client(host, username, password).test_authentication()

        return acces_msg

    @staticmethod
    def discover_emby():
        return notifiers.NotifierFactory().get('EMBY').discover_server()

    def test_emby(self, host=None, apikey=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=8096)
        if not hosts:
            return 'Fail: No valid host(s)'

        result = notifiers.NotifierFactory().get('EMBY').test_notify(hosts, apikey)

        ui.notifications.message('Tested Emby:', urllib.unquote_plus(hosts.replace(',', ', ')))
        return result

    def test_kodi(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        hosts = config.clean_hosts(host, default_port=8080)
        if not hosts:
            return 'Fail: No valid host(s)'

        if None is not password and set('*') == set(password):
            password = sickbeard.KODI_PASSWORD

        result = notifiers.NotifierFactory().get('KODI').test_notify(hosts, username, password)

        ui.notifications.message('Tested Kodi:', urllib.unquote_plus(hosts.replace(',', ', ')))
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
                                 urllib.unquote_plus(hosts.replace(',', ', ')))
        return result

    # def test_xbmc(self, host=None, username=None, password=None):
    #     self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')
    #
    #     hosts = config.clean_hosts(host, default_port=80)
    #     if not hosts:
    #         return 'Fail: No valid host(s)'
    #
    #     if None is not password and set('*') == set(password):
    #         password = sickbeard.XBMC_PASSWORD
    #
    #     result = notifiers.NotifierFactory().get('XBMC').test_notify(hosts, username, password)
    #
    #     ui.notifications.message('Tested XBMC: ', urllib.unquote_plus(hosts.replace(',', ', ')))
    #     return result

    def test_nmj(self, host=None, database=None, mount=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        if not hosts:
            return 'Fail: No valid host(s)'

        return notifiers.NotifierFactory().get('NMJ').test_notify(urllib.unquote_plus(host), database, mount)

    def settings_nmj(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        if not hosts:
            return 'Fail: No valid host(s)'

        return notifiers.NotifierFactory().get('NMJ').notify_settings(urllib.unquote_plus(host))

    def test_nmj2(self, host=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        if not hosts:
            return 'Fail: No valid host(s)'

        return notifiers.NotifierFactory().get('NMJV2').test_notify(urllib.unquote_plus(host))

    def settings_nmj2(self, host=None, dbloc=None, instance=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host)
        return notifiers.NotifierFactory().get('NMJV2').notify_settings(urllib.unquote_plus(host), dbloc, instance)

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

    def test_growl(self, host=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_host(host, default_port=23053)
        if None is not password and set('*') == set(password):
            password = sickbeard.GROWL_PASSWORD

        return notifiers.NotifierFactory().get('GROWL').test_notify(host, password)

    def test_prowl(self, prowl_api=None, prowl_priority=0):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        if None is not prowl_api and starify(prowl_api, True):
            prowl_api = sickbeard.PROWL_API

        return notifiers.NotifierFactory().get('PROWL').test_notify(prowl_api, prowl_priority)

    def test_libnotify(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('LIBNOTIFY').test_notify()

    # def test_pushalot(self, authorization_token=None):
    #     self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')
    #
    #     if None is not authorization_token and starify(authorization_token, True):
    #         authorization_token = sickbeard.PUSHALOT_AUTHORIZATIONTOKEN
    #
    #     return notifiers.NotifierFactory().get('PUSHALOT').test_notify(authorization_token)

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

    def load_show_notify_lists(self, *args, **kwargs):
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

    def test_slack(self, channel=None, as_authed=False, bot_name=None, icon_url=None, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('SLACK').test_notify(
            channel=channel, as_authed='true' == as_authed,
            bot_name=bot_name, icon_url=icon_url, access_token=access_token)

    def test_discordapp(self, as_authed=False, username=None, icon_url=None, as_tts=False, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('DISCORDAPP').test_notify(
            as_authed='true' == as_authed, username=username, icon_url=icon_url,
            as_tts='true' == as_tts, access_token=access_token)

    def test_gitter(self, room_name=None, access_token=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('GITTER').test_notify(
            room_name=room_name, access_token=access_token)

    def test_twitter(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('TWITTER').test_notify()

    def twitter_step1(self, *args, **kwargs):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('TWITTER').get_authorization()

    def twitter_step2(self, key):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        return notifiers.NotifierFactory().get('TWITTER').get_credentials(key)

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
        parse = show.split('_')
        if 1 < len(parse) and \
                my_db.action('UPDATE tv_shows SET notify_list = ? WHERE indexer = ? AND indexer_id = ?',
                             [emails, parse[0], parse[1]]):
            success = True
        return json.dumps({'id': show, 'success': success})

    def viewchanges(self):

        t = PageTemplate(web_handler=self, file='viewchanges.tmpl')

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

        t = PageTemplate(web_handler=self, file='restart.tmpl')
        t.shutdown = True

        sickbeard.events.put(sickbeard.events.SystemEvent.SHUTDOWN)

        return t.respond()

    def restart(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        t = PageTemplate(web_handler=self, file='restart.tmpl')
        t.shutdown = False

        sickbeard.events.put(sickbeard.events.SystemEvent.RESTART)

        return t.respond()

    def update(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            return self.redirect('/home/')

        if sickbeard.versionCheckScheduler.action.update():
            return self.restart(pid)

        return self._genericMessage('Update Failed',
                                    'Update wasn\'t successful, not restarting. Check your log for more information.')

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

    def display_season(self, show=None, season=None):

        response = {'success': False}
        show_obj = None
        if show:
            show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, helpers.tryInt(show, -1))
        if not show_obj:
            return json.dumps(response)

        re_season = re.compile('(?i)^showseason-(\d+)$')
        season = None if not any(re_season.findall(season)) else \
            helpers.tryInt(re_season.findall(season)[0], None)
        if None is season:
            return json.dumps(response)

        t = PageTemplate(web_handler=self, file='inc_displayShow.tmpl')
        t.show = show_obj

        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT * FROM tv_episodes WHERE showid = ? AND season = ? ORDER BY episode DESC',
                                   [show_obj.indexerid, season])
        t.episodes = sql_results

        ep_cats = {}
        for row in sql_results:
            status_overview = show_obj.getOverview(int(row['status']))
            if status_overview:
                ep_cats['%sx%s' % (season, row['episode'])] = status_overview
        t.ep_cats = ep_cats

        args = (int(show_obj.indexerid), int(show_obj.indexer))
        t.scene_numbering = get_scene_numbering_for_show(*args)
        t.xem_numbering = get_xem_numbering_for_show(*args)
        t.scene_absolute_numbering = get_scene_absolute_numbering_for_show(*args)
        t.xem_absolute_numbering = get_xem_absolute_numbering_for_show(*args)

        return json.dumps({'success': t.respond()})

    def displayShow(self, show=None):

        if show is None:
            return self._genericMessage('Error', 'Invalid show ID')
        else:
            showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

            if showObj is None:
                return self._genericMessage('Error', 'Show not in show list')

        t = PageTemplate(web_handler=self, file='displayShow.tmpl')
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

        if 0 != showObj.not_found_count:
            last_found = ('', ' since %s' % sbdatetime.sbdatetime.fromordinal(
                showObj.last_found_on_indexer).sbfdate())[1 < showObj.last_found_on_indexer]
            show_message = (
                'The master ID of this show has been <span class="addQTip" title="many reasons exist, including: '
                + '<br>show flagged as a duplicate, removed completely... etc">abandoned</span>%s, ' % last_found
                + '<a href="%s/home/editShow?show=%s&tvsrc=0&srcid=%s#core-component-group3">replace it here</a>' % (
                    sickbeard.WEB_ROOT, show, show)
                + ('', '<br>%s' % show_message)[0 < len(show_message)])
        t.force_update = 'home/updateShow?show=%d&amp;force=1&amp;web=1' % showObj.indexerid
        if not sickbeard.showQueueScheduler.action.isBeingAdded(showObj):  # @UndefinedVariable
            if not sickbeard.showQueueScheduler.action.isBeingUpdated(showObj):  # @UndefinedVariable
                t.submenu.append(
                    {'title': 'Remove', 'path': 'home/deleteShow?show=%d' % showObj.indexerid, 'confirm': True})
                t.submenu.append({'title': 'Re-scan files', 'path': 'home/refreshShow?show=%d' % showObj.indexerid})
                t.submenu.append(
                    {'title': 'Force Full Update', 'path': t.force_update})
                t.submenu.append({'title': 'Update show in Emby',
                                  'path': 'home/update_emby%s' %
                                          (INDEXER_TVDB == showObj.indexer and ('?show=%s' % showObj.indexerid) or '/'),
                                  'requires': self.haveEMBY})
                t.submenu.append({'title': 'Update show in Kodi',
                                  'path': 'home/update_kodi?show_name=%s' % urllib.quote_plus(
                                  showObj.name.encode('utf-8')), 'requires': self.haveKODI})
                t.submenu.append({'title': 'Update show in XBMC',
                                  'path': 'home/update_xbmc?show_name=%s' % urllib.quote_plus(
                                  showObj.name.encode('utf-8')), 'requires': self.haveXBMC})
                t.submenu.append({'title': 'Media Renamer', 'path': 'home/testRename?show=%d' % showObj.indexerid})
                if sickbeard.USE_SUBTITLES and not sickbeard.showQueueScheduler.action.isBeingSubtitled(
                        showObj) and showObj.subtitles:
                    t.submenu.append(
                        {'title': 'Download Subtitles', 'path': 'home/subtitleShow?show=%d' % showObj.indexerid})

        t.show = showObj
        with BS4Parser('<html><body>%s</body></html>' % showObj.overview, features=['html5lib', 'permissive']) as soup:
            try:
                soup.a.replace_with(soup.new_tag(''))
            except(StandardError, Exception):
                pass
            overview = re.sub('(?i)full streaming', '', soup.get_text().strip())
        t.show.overview = overview
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

        for row in my_db.select('SELECT season, count(*) AS cnt FROM tv_episodes WHERE showid = ?'
                                + ' GROUP BY season', [showObj.indexerid]):
            ep_counts['totals'][row['season']] = row['cnt']

        if None is not ep_counts['totals'].get(0, None):
            t.has_special = True
            if not sickbeard.DISPLAY_SHOW_SPECIALS:
                del(ep_counts['totals'][0])

        ep_counts['eps_all'] = sum(ep_counts['totals'].values())
        ep_counts['eps_most'] = max(ep_counts['totals'].values() + [0])
        all_seasons = sorted(ep_counts['totals'].keys(), reverse=True)
        t.lowest_season, t.highest_season = all_seasons and (all_seasons[-1], all_seasons[0]) or (0, 0)

        # 55 == seasons 1-10 and excludes the random season 0
        force_display_show_minimum = 30 < ep_counts['eps_most'] or 55 < sum(ep_counts['totals'].keys())
        display_show_minimum = sickbeard.DISPLAY_SHOW_MINIMUM or force_display_show_minimum

        for row in my_db.select('SELECT max(season) as latest FROM tv_episodes WHERE showid = ?'
                                + ' and 1000 < airdate and ? < status', [showObj.indexerid, UNAIRED]):
            t.latest_season = row['latest'] or {0: 1, 1: 1, 2: None}.get(sickbeard.DISPLAY_SHOW_VIEWMODE)

        t.season_min = ([], [1])[2 < t.latest_season] + [t.latest_season]
        t.other_seasons = (list(set(all_seasons) - set(t.season_min)), [])[display_show_minimum]
        t.seasons = []
        for x in all_seasons:
            t.seasons += [(x, [None] if x not in (t.season_min + t.other_seasons) else my_db.select(
                'SELECT * FROM tv_episodes WHERE showid = ? AND season = ? ORDER BY episode DESC',
                [showObj.indexerid, x]))]

        for row in my_db.select('SELECT season, episode, status FROM tv_episodes WHERE showid = ? AND season IN (%s)' %
                                ','.join(['?'] * len(t.season_min + t.other_seasons)),
                                [showObj.indexerid] + t.season_min + t.other_seasons):
            status_overview = showObj.getOverview(row['status'])
            if status_overview:
                ep_cats['%sx%s' % (row['season'], row['episode'])] = status_overview
        t.ep_cats = ep_cats

        for row in my_db.select('SELECT season, count(*) AS cnt, status FROM tv_episodes WHERE showid = ?'
                                + ' GROUP BY season, status', [showObj.indexerid]):
            status_overview = showObj.getOverview(row['status'])
            if status_overview:
                ep_counts[status_overview] += row['cnt']
                if ARCHIVED == Quality.splitCompositeStatus(row['status'])[0]:
                    ep_counts['archived'].setdefault(row['season'], 0)
                    ep_counts['archived'][row['season']] = row['cnt'] + ep_counts['archived'].get(row['season'], 0)
                else:
                    ep_counts['status'].setdefault(row['season'], {})
                    ep_counts['status'][row['season']][status_overview] = row['cnt'] + \
                        ep_counts['status'][row['season']].get(status_overview, 0)

        for row in my_db.select('SELECT season, count(*) AS cnt FROM tv_episodes WHERE showid = ?'
                                + ' AND \'\' != location GROUP BY season', [showObj.indexerid]):
            ep_counts['videos'][row['season']] = row['cnt']
        t.ep_counts = ep_counts

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

        t.show.exceptions = scene_exceptions.get_scene_exceptions(showObj.indexerid)

        t.fanart = []
        cache_obj = image_cache.ImageCache()
        for img in ek.ek(glob.glob, cache_obj.fanart_path(showObj.indexerid).replace('fanart.jpg', '*')) or []:
            match = re.search(r'\.(\d+(?:\.(\w*?(\d*)))?\.(?:\w{5,8}))\.fanart\.', img, re.I)
            if match and match.group(1):
                t.fanart += [(match.group(1), sickbeard.FANART_RATINGS.get(show, {}).get(match.group(1), ''))]

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

        t.clean_show_name = urllib.quote_plus(sickbeard.indexermapper.clean_show_name(showObj.name))

        indexerid = int(showObj.indexerid)
        indexer = int(showObj.indexer)
        t.min_initial = Quality.get_quality_ui(min(Quality.splitQuality(showObj.quality)[0]))
        t.all_scene_exceptions = t.show.exceptions
        t.scene_numbering = get_scene_numbering_for_show(indexerid, indexer)
        t.scene_absolute_numbering = get_scene_absolute_numbering_for_show(indexerid, indexer)
        t.xem_numbering = get_xem_numbering_for_show(indexerid, indexer)
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
            # handle orphaned shows
            if len(sickbeard.showList) != sum([len(x[1]) for x in sorted_show_lists]):
                used_ids = set()
                for x in sorted_show_lists:
                    for y in x[1]:
                        used_ids |= {y.indexerid}

                showlist = dict()
                all_ids = set(x.indexerid for x in sickbeard.showList)
                for iid in list(all_ids - used_ids):
                    try:
                        show = helpers.findCertainShow(sickbeard.showList, iid)
                    except (StandardError, Exception):
                        pass
                    if show:
                        if show.tag in showlist:
                            showlist[show.tag] += [show]
                        else:
                            showlist[show.tag] = [show]

                sorted_show_lists += [[key, shows] for key, shows in showlist.items()]

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
        return 'Episode not found.' if not result else (result[0]['description'] or '')[:250:]

    def sceneExceptions(self, show):
        exceptionsList = sickbeard.scene_exceptions.get_all_scene_exceptions(show)
        if not exceptionsList:
            return 'No scene exceptions'

        out = []
        for season, names in iter(sorted(iteritems(exceptionsList))):
            out.append('S%s: %s' % ((season, '*')[-1 == season], ',<br />\n'.join(names)))
        return '---------<br />\n'.join(out)

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
        show = helpers.tryInt(show)
        show_obj = sickbeard.helpers.findCertainShow(sickbeard.showList, show)
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

        master_ids = [show] + [helpers.tryInt(kwargs.get(x)) for x in 'indexer', 'mindexerid', 'mindexer']
        if all([x > 0 for x in master_ids]) and sickbeard.indexerApi(kwargs['mindexer']).config.get('active') and \
                not sickbeard.indexerApi(kwargs['mindexer']).config.get('defunct') and \
                not sickbeard.indexerApi(kwargs['mindexer']).config.get('mapped_only') and \
                (helpers.tryInt(kwargs['mindexer']) != helpers.tryInt(kwargs['indexer']) or
                    helpers.tryInt(kwargs['mindexerid']) != show):
            try:
                new_show_obj = helpers.find_show_by_id(sickbeard.showList, {helpers.tryInt(kwargs['mindexer']): helpers.tryInt(kwargs['mindexerid'])},no_mapped_ids=False)
                if not new_show_obj or (new_show_obj.indexer == show_obj.indexer and new_show_obj.indexerid == show_obj.indexerid):
                    master_ids += [bool(helpers.tryInt(kwargs.get(x))) for x in 'paused', 'markwanted']
                    response = {'switch': self.switchIndexer(*master_ids), 'mid': kwargs['mindexerid']}
                else:
                    ui.notifications.message('Master ID unchanged, because show from %s with ID: %s exists in DB.' %
                                             (sickbeard.indexerApi(kwargs['mindexer']).name, kwargs['mindexerid']))
            except MultipleShowObjectsException:
                pass

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

    @staticmethod
    def fanart_tmpl(t):
        t.fanart = []
        cache_obj = image_cache.ImageCache()
        for img in ek.ek(glob.glob, cache_obj.fanart_path(t.show.indexerid).replace('fanart.jpg', '*')) or []:
            match = re.search(r'\.(\d+(?:\.(\w*?(\d*)))?\.(?:\w{5,8}))\.fanart\.', img, re.I)
            if match and match.group(1):
                t.fanart += [(match.group(1),
                              sickbeard.FANART_RATINGS.get(str(t.show.indexerid), {}).get(match.group(1), ''))]

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

    def editShow(self, show=None, location=None, anyQualities=[], bestQualities=[], exceptions_list=[],
                 flatten_folders=None, paused=None, directCall=False, air_by_date=None, sports=None, dvdorder=None,
                 indexerLang=None, subtitles=None, upgrade_once=None, rls_ignore_words=None,
                 rls_require_words=None, anime=None, blacklist=None, whitelist=None,
                 scene=None, prune=None, tag=None, quality_preset=None, reset_fanart=None, **kwargs):

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
            t = PageTemplate(web_handler=self, file='editShow.tmpl')
            t.submenu = self.HomeMenu()

            t.expand_ids = all([kwargs.get('tvsrc'), helpers.tryInt(kwargs.get('srcid'))])
            t.tvsrc = int(kwargs.get('tvsrc', 0))
            t.srcid = helpers.tryInt(kwargs.get('srcid'))

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

            # noinspection PyTypeChecker
            self.fanart_tmpl(t)
            t.num_ratings = len(sickbeard.FANART_RATINGS.get(str(t.show.indexerid), {}))

            t.unlock_master_id = 0 != showObj.not_found_count
            t.showname_enc = urllib.quote_plus(showObj.name.encode('utf-8'))

            show_message = ''

            if 0 != showObj.not_found_count:
                # noinspection PyUnresolvedReferences
                last_found = ('', ' since %s' % sbdatetime.sbdatetime.fromordinal(
                    showObj.last_found_on_indexer).sbfdate())[1 < showObj.last_found_on_indexer]
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
        subtitles = config.checkbox_to_value(subtitles)

        if config.checkbox_to_value(reset_fanart) and sickbeard.FANART_RATINGS.get(show):
            del sickbeard.FANART_RATINGS[show]
            sickbeard.save_config()

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
            showObj.upgrade_once = upgrade_once

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
            showObj.prune = config.minimax(prune, 0, 0, 9999)

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

    def update_emby(self, show=None):

        if notifiers.NotifierFactory().get('EMBY').update_library(
                sickbeard.helpers.findCertainShow(sickbeard.showList, helpers.tryInt(show, None))):
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

    def update_plex(self, *args, **kwargs):
        result = notifiers.NotifierFactory().get('PLEX').update_library()
        if 'Fail' not in result:
            ui.notifications.message(
                'Library update command sent to', 'Plex Media Server host(s): ' + sickbeard.PLEX_SERVER_HOST.replace(',', ', '))
        else:
            ui.notifications.error('Unable to contact', 'Plex Media Server host(s): ' + result)
        self.redirect('/home/')

    # def update_xbmc(self, show_name=None):
    #
    #     # only send update to first host in the list -- workaround for xbmc sql backend users
    #     if sickbeard.XBMC_UPDATE_ONLYFIRST:
    #         # only send update to first host in the list -- workaround for xbmc sql backend users
    #         host = sickbeard.XBMC_HOST.split(',')[0].strip()
    #     else:
    #         host = sickbeard.XBMC_HOST
    #
    #     if notifiers.NotifierFactory().get('XBMC').update_library(show_name=show_name):
    #         ui.notifications.message('Library update command sent to XBMC host(s): ' + host)
    #     else:
    #         ui.notifications.error('Unable to contact one or more XBMC host(s): ' + host)
    #     self.redirect('/home/')

    def setStatus(self, show=None, eps=None, status=None, direct=False):

        if show is None or eps is None or status is None:
            err_msg = 'You must specify a show and at least one episode'
            if direct:
                ui.notifications.error('Error', err_msg)
                return json.dumps({'result': 'error'})
            return self._genericMessage('Error', err_msg)

        use_default = False
        if isinstance(status, basestring) and '-' in status:
            use_default = True
            status = status.replace('-', '')
        status = int(status)

        if not statusStrings.has_key(status):
            err_msg = 'Invalid status'
            if direct:
                ui.notifications.error('Error', err_msg)
                return json.dumps({'result': 'error'})
            return self._genericMessage('Error', err_msg)

        showObj = sickbeard.helpers.findCertainShow(sickbeard.showList, int(show))

        if showObj is None:
            err_msg = 'Error', 'Show not in show list'
            if direct:
                ui.notifications.error('Error', err_msg)
                return json.dumps({'result': 'error'})
            return self._genericMessage('Error', err_msg)

        min_initial = min(Quality.splitQuality(showObj.quality)[0])
        segments = {}
        if eps is not None:

            sql_l = []
            for curEp in eps.split('|'):

                logger.log(u'Attempting to set status on episode %s to %s' % (curEp, status), logger.DEBUG)

                ep_obj = showObj.getEpisode(*tuple([int(x) for x in curEp.split('x')]))

                if ep_obj is None:
                    return self._genericMessage('Error', 'Episode couldn\'t be retrieved')

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

                    elif status in Quality.DOWNLOADED\
                            and ep_obj.status not in required + Quality.ARCHIVED + [IGNORED, SKIPPED]\
                            and not ek.ek(os.path.isfile, ep_obj.location):
                        err_msg = 'to downloaded because it\'s not snatched/downloaded/archived'

                    if err_msg:
                        logger.log('Refusing to change status of %s %s' % (curEp, err_msg), logger.ERROR)
                        continue

                    if ARCHIVED == status:
                        if ep_obj.status in Quality.DOWNLOADED:
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

        elif FAILED == status:
            msg = u'Retrying search automatically for the following season of <b>%s</b>:<br><ul>' % showObj.name

            for season, segment in segments.items():
                cur_failed_queue_item = search_queue.FailedQueueItem(showObj, segment)
                sickbeard.searchQueueScheduler.action.add_item(cur_failed_queue_item)

                msg += '<li>Season %s</li>' % season
                logger.log(u'Retrying search for %s season %s because some eps were set to failed' %
                           (showObj.name, season))

            msg += '</ul>'

            if segments:
                ui.notifications.message('Retry search started', msg)

        if direct:
            return json.dumps({'result': 'success'})
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
                    for cur_related_ep in cur_ep_obj.relatedEps + [cur_ep_obj]:
                        if cur_related_ep in ep_obj_rename_list:
                            break
                        ep_status, ep_qual = Quality.splitCompositeStatus(cur_related_ep.status)
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
        t.submenu = [{'title': 'Edit', 'path': 'home/editShow?show=%d' % showObj.indexerid}]
        t.ep_obj_list = ep_obj_rename_list
        t.show = showObj

        # noinspection PyTypeChecker
        self.fanart_tmpl(t)

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

        retry_statues = SNATCHED_ANY + [DOWNLOADED, ARCHIVED]
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
                                 'retrystatus': Quality.splitCompositeStatus(searchThread.segment.status)[0] in retry_statues,
                                 'status' : statusStrings[searchThread.segment.status],
                                 'quality': self.getQualityClass(searchThread.segment)})
            elif hasattr(searchThread, 'segment'):
                for epObj in searchThread.segment:
                    episodes.append({'episode': epObj.episode,
                                     'episodeindexid': epObj.indexerid,
                                     'season' : epObj.season,
                                     'searchstatus' : searchstatus,
                                     'retrystatus': Quality.splitCompositeStatus(epObj.status)[0] in retry_statues,
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
                                 'retrystatus': Quality.splitCompositeStatus(searchThread.segment.status)[0] in retry_statues,
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
                                     'retrystatus': Quality.splitCompositeStatus(epObj.status)[0] in retry_statues,
                                     'status' : statusStrings[epObj.status],
                                     'quality': self.getQualityClass(epObj)})

        return json.dumps({'show': show, 'episodes' : episodes})

        #return json.dumps()

    def getQualityClass(self, ep_obj):
        # return the correct json value

        # Find the quality class for the episode
        quality_class = Quality.qualityStrings[Quality.UNKNOWN]
        ep_status, ep_quality = Quality.splitCompositeStatus(ep_obj.status)
        for x in (SD, HD720p, HD1080p, UHD2160p):
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
        try:
            previous_subtitles = set(subliminal.language.Language(x) for x in ep_obj.subtitles)
            ep_obj.subtitles = set(x.language for x in ep_obj.downloadSubtitles().values()[0])
        except(StandardError, Exception):
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

        result = set_scene_numbering_helper(show, indexer, forSeason, forEpisode, forAbsolute, sceneSeason,
                                            sceneEpisode, sceneAbsolute)

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

        t = PageTemplate(web_handler=self, file='home_postprocess.tmpl')
        t.submenu = [x for x in self.HomeMenu() if 'postprocess' not in x['path']]
        return t.respond()

    def processEpisode(self, dir=None, nzbName=None, jobName=None, quiet=None, process_method=None, force=None,
                       force_replace=None, failed='0', type='auto', stream='0', dupekey=None, is_basedir='1',
                       client=None, **kwargs):

        if 'test' in kwargs and kwargs['test'] in ['True', True, 1, '1']:
            return 'Connection success!'

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

            skip_failure_processing = isinstance(client, basestring) and 'nzbget' == client and \
                (not isinstance(dupekey, basestring) or None is re.search(r'^SickGear-([A-Za-z]*)(\d+)-', dupekey))

            if isinstance(client, basestring) and 'nzbget' == client and \
                    sickbeard.NZBGET_SCRIPT_VERSION != kwargs.get('ppVersion', '0'):
                logger.log('Calling SickGear-NG.py script %s is not current version %s, please update.' %
                           (kwargs.get('ppVersion', '0'), sickbeard.NZBGET_SCRIPT_VERSION), logger.ERROR)

            if isinstance(dir, basestring):
                dir = dir.decode('utf-8')
                if isinstance(client, basestring) and 'nzbget' == client and \
                        isinstance(sickbeard.NZBGET_MAP, basestring) and sickbeard.NZBGET_MAP:
                    m = sickbeard.NZBGET_MAP.split('=')
                    dir, not_used = helpers.path_mapper(m[0], m[1], dir)

            result = processTV.processDir(dir if dir else None, nzbName.decode('utf-8') if nzbName else None,
                                          process_method=process_method, type=type,
                                          cleanup='cleanup' in kwargs and kwargs['cleanup'] in ['on', '1'],
                                          force=force in ['on', '1'],
                                          force_replace=force_replace in ['on', '1'],
                                          failed='0' != failed,
                                          webhandler=self.send_message if stream != '0' else None,
                                          showObj=showObj, is_basedir=is_basedir in ['on', '1'],
                                          skip_failure_processing=skip_failure_processing)

            if '0' != stream:
                return
            result = re.sub(r'(?i)<br(?:[\s/]+)>', '\n', result)
            if None is not quiet and 1 == int(quiet):
                return u'%s' % re.sub('(?i)<a[^>]+>([^<]+)<[/]a>', r'\1', result)

            return self._genericMessage('Postprocessing results', u'<pre>%s</pre>' % result)


class NewHomeAddShows(Home):
    def index(self, *args, **kwargs):

        t = PageTemplate(web_handler=self, file='home_addShows.tmpl')
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

    # noinspection PyPep8Naming
    def searchIndexersForShowName(self, search_term, lang='en', indexer=None):
        if not lang or 'null' == lang:
            lang = 'en'
        try:
            search_term = re.findall(r'(?i)thetvdb.*?seriesid=([\d]+)', search_term)[0]
        except (StandardError, Exception):
            pass
        term = search_term.decode('utf-8').strip()
        terms = []
        try:
            for t in term.encode('utf-8'), unidecode(term), term:
                if t not in terms:
                    terms += [t]
        except (StandardError, Exception):
            terms = [search_term.strip().encode('utf-8')]

        results = {}
        final_results = []

        search_id, indexer_id, trakt_id, tmdb_id, INDEXER_TVDB_X = '', None, None, None, INDEXER_TRAKT
        try:
            search_id = re.search(r'(?m)((?:tt\d{4,})|^\d{4,}$)', search_term).group(1)

            lINDEXER_API_PARMS = sickbeard.indexerApi(INDEXER_TVDB_X).api_params.copy()
            lINDEXER_API_PARMS['language'] = lang
            lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsNoFilterListUI
            lINDEXER_API_PARMS['sleep_retry'] = 5
            lINDEXER_API_PARMS['search_type'] = (TraktSearchTypes.tvdb_id, TraktSearchTypes.imdb_id)['tt' in search_id]
            t = sickbeard.indexerApi(INDEXER_TVDB_X).indexer(**lINDEXER_API_PARMS)

            resp = t[search_id][0]
            search_term = resp['seriesname']
            indexer_id = resp['ids']['tvdb']
            trakt_id = resp['ids'].get('trakt')
            tmdb_id = resp['ids'].get('tmdb')

        except (StandardError, Exception):
            search_term = (search_term, '')['tt' in search_id]

        # query Indexers for search term and build list of results
        for indexer in sickbeard.indexerApi().indexers if not int(indexer) else [int(indexer)]:
            lINDEXER_API_PARMS = sickbeard.indexerApi(indexer).api_params.copy()
            lINDEXER_API_PARMS['language'] = lang
            lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsNoFilterListUI
            t = sickbeard.indexerApi(indexer).indexer(**lINDEXER_API_PARMS)

            try:
                # add search results
                if bool(indexer_id):
                    logger.log('Fetching show using id: %s (%s) from tv datasource %s' % (
                        search_id, search_term, sickbeard.indexerApi(indexer).name), logger.DEBUG)
                    r = t[indexer_id, False]
                    results.setdefault((indexer, INDEXER_TVDB_X)['tt' in search_id], {})[int(indexer_id)] = {
                        'id': indexer_id, 'seriesname': r['seriesname'], 'firstaired': r['firstaired'],
                        'network': r['network'], 'overview': r['overview'],
                        'genres': '' if not r['genre'] else r['genre'].lower().strip('|').replace('|', ', '),
                        'trakt_id': trakt_id, 'tmdb_id': tmdb_id
                    }
                    break
                else:
                    logger.log('Searching for shows using search term: %s from tv datasource %s' % (
                        search_term, sickbeard.indexerApi(indexer).name), logger.DEBUG)
                    results.setdefault(indexer, {})
                    for term in terms:
                        try:
                            for r in t[term]:
                                tvdb_id = int(r['id'])
                                if tvdb_id not in results[indexer]:
                                    results.setdefault(indexer, {})[tvdb_id] = r.copy()
                                elif r['seriesname'] != results[indexer][tvdb_id]['seriesname']:
                                    results[indexer][tvdb_id].setdefault('aliases', []).append(r['seriesname'])
                        except tvdb_exception:
                            pass
            except (StandardError, Exception):
                pass

        # query trakt for tvdb ids
        try:
            logger.log('Searching for show using search term: %s from tv datasource Trakt' % search_term, logger.DEBUG)
            resp = []
            lINDEXER_API_PARMS = sickbeard.indexerApi(INDEXER_TVDB_X).api_params.copy()
            lINDEXER_API_PARMS['language'] = lang
            lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsNoFilterListUI
            lINDEXER_API_PARMS['sleep_retry'] = 5
            lINDEXER_API_PARMS['search_type'] = TraktSearchTypes.text
            t = sickbeard.indexerApi(INDEXER_TVDB_X).indexer(**lINDEXER_API_PARMS)

            for term in terms:
                result = t[term]
                resp += result
                match = False
                for r in result:
                    if isinstance(r.get('seriesname'), (str, unicode)) \
                            and term.lower() == r.get('seriesname', '').lower():
                        match = True
                        break
                if match:
                    break
            results_trakt = {}
            for item in resp:
                if 'tvdb' in item['ids'] and item['ids']['tvdb']:
                    if item['ids']['tvdb'] not in results[INDEXER_TVDB]:
                        results_trakt[int(item['ids']['tvdb'])] = {
                            'id': item['ids']['tvdb'], 'seriesname': item['seriesname'],
                            'genres': item['genres'].lower(), 'network': item['network'],
                            'overview': item['overview'], 'firstaired': item['firstaired'],
                            'trakt_id': item['ids']['trakt'], 'tmdb_id': item['ids']['tmdb']}
                    elif item['seriesname'] != results[INDEXER_TVDB][int(item['ids']['tvdb'])]['seriesname']:
                        results[INDEXER_TVDB][int(item['ids']['tvdb'])].setdefault(
                            'aliases', []).append(item['seriesname'])
            results.setdefault(INDEXER_TVDB_X, {}).update(results_trakt)
        except (StandardError, Exception):
            pass

        id_names = {iid: (name, '%s via %s' % (sickbeard.indexerApi(INDEXER_TVDB).name, name))[INDEXER_TVDB_X == iid]
                    for iid, name in sickbeard.indexerApi().all_indexers.iteritems()}
        # noinspection PyUnboundLocalVariable
        map(final_results.extend,
            ([[id_names[iid], any([helpers.find_show_by_id(
                sickbeard.showList, {(iid, INDEXER_TVDB)[INDEXER_TVDB_X == iid]: int(show['id'])},
                no_mapped_ids=False)]) and '/home/displayShow?show=%s' % int(show['id']),
               iid, (iid, INDEXER_TVDB)[INDEXER_TVDB_X == iid],
               sickbeard.indexerApi((iid, INDEXER_TVDB)[INDEXER_TVDB_X == iid]).config['show_url'] % int(show['id']),
               int(show['id']),
               show['seriesname'], self.encode_html(show['seriesname']), show['firstaired'],
               show.get('network', '') or '', show.get('genres', '') or '',
               re.sub(r'([,.!][^,.!]*?)$', '...',
                      re.sub(r'([.!?])(?=\w)', r'\1 ',
                             self.encode_html((show.get('overview', '') or '')[:250:].strip()))),
               self.get_UWRatio(term, show['seriesname'], show.get('aliases', [])), None, None,
               self._make_search_image_url(iid, show)
               ] for show in shows.itervalues()] for iid, shows in results.iteritems()))

        def final_order(sortby_index, data, final_sort):
            idx_is_indb = 1
            for (n, x) in enumerate(data):
                x[sortby_index] = n + (1000, 0)[x[idx_is_indb] and 'notop' not in sickbeard.RESULTS_SORTBY]
            return data if not final_sort else sorted(data, reverse=False, key=lambda x: x[sortby_index])

        def sort_date(data_result, is_last_sort):
            idx_date_sort, idx_src, idx_aired = 13, 2, 8
            return final_order(
                idx_date_sort,
                sorted(
                    sorted(data_result, reverse=True, key=lambda x: (dateutil.parser.parse(
                        re.match('^(?:19|20)\d\d$', str(x[idx_aired])) and ('%s-12-31' % str(x[idx_aired]))
                        or (x[idx_aired] and str(x[idx_aired])) or '1900'))),
                    reverse=False, key=lambda x: x[idx_src]), is_last_sort)

        def sort_az(data_result, is_last_sort):
            idx_az_sort, idx_src, idx_title = 14, 2, 6
            return final_order(
                idx_az_sort,
                sorted(
                    data_result, reverse=False, key=lambda x: (
                        x[idx_src],
                        (remove_article(x[idx_title].lower()), x[idx_title].lower())[sickbeard.SORT_ARTICLE])),
                is_last_sort)

        def sort_rel(data_result, is_last_sort):
            idx_rel_sort, idx_src, idx_rel = 12, 2, 12
            return final_order(
                idx_rel_sort,
                sorted(
                    sorted(data_result, reverse=True, key=lambda x: x[idx_rel]),
                    reverse=False, key=lambda x: x[idx_src]), is_last_sort)

        if 'az' == sickbeard.RESULTS_SORTBY[:2]:
            sort_results = [sort_date, sort_rel, sort_az]
        elif 'date' == sickbeard.RESULTS_SORTBY[:4]:
            sort_results = [sort_az, sort_rel, sort_date]
        else:
            sort_results = [sort_az, sort_date, sort_rel]

        for n, func in enumerate(sort_results):
            final_results = func(final_results, n == len(sort_results) - 1)

        return json.dumps({'results': final_results, 'langid': sickbeard.indexerApi().config['langabbv_to_id'][lang]})

    @staticmethod
    def _make_search_image_url(iid, show):
        img_url = ''
        if INDEXER_TRAKT == iid:
            img_url = 'imagecache?path=browse/thumb/trakt&filename=%s&trans=0&tmdbid=%s&tvdbid=%s' % \
                      ('%s.jpg' % show['trakt_id'], show.get('tmdb_id'), show.get('id'))
        elif INDEXER_TVDB == iid:
            img_url = 'imagecache?path=browse/thumb/tvdb&filename=%s&trans=0&tvdbid=%s' % \
                      ('%s.jpg' % show['id'], show['id'])
        return img_url

    @classmethod
    def get_UWRatio(cls, search_term, showname, aliases):
        s = fuzz.UWRatio(search_term, showname)
        # check aliases and give them a little lower score
        for a in aliases:
            ns = fuzz.UWRatio(search_term, a) - 1
            if ns > s:
                s = ns
        return s

    def massAddTable(self, rootDir=None, **kwargs):
        t = PageTemplate(web_handler=self, file='home_massAddTable.tmpl')
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
                except (StandardError, Exception):
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

        t = PageTemplate(web_handler=self, file='home_newShow.tmpl')
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
                        images = dict(poster=dict(thumb='imagecache?path=browse/thumb/anidb&source=%s' % img_uri))
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
                            url_tvdb=sickbeard.indexerApi(INDEXER_TVDB).config['show_url'] % ids['tvdb'],
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

    def parse_imdb(self, data, filtered, kwargs):

        oldest, newest, oldest_dt, newest_dt = None, None, 9999999, 0
        show_list = (data or {}).get('list', {}).get('items', {})
        idx_ids = dict([(x.imdbid, (x.indexer, x.indexerid)) for x in sickbeard.showList if getattr(x, 'imdbid', None)])
        # list_id = (data or {}).get('list', {}).get('id', {})
        for row in show_list:
            row = data.get('titles', {}).get(row.get('const', None), None)
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
                    img_uri = re.sub('(?im)(.*V1_?)(\..*?)$', r'\1UX%s_CR0,0,%s,%s_AL_\2' % (s[0], s[0], s[1]), img_uri)
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
                    overview='No overview yet' if not overview else self.encode_html(overview[:250:]),
                    rating=int(helpers.tryFloat(rating) * 10),
                    title=row.get('primary').get('title'),
                    url_src_db='http://www.imdb.com/%s/' % row.get('primary').get('href').strip('/'),
                    votes=helpers.tryInt(voting, 'TBA')))

                indexer, indexerid = idx_ids.get(ids['imdb'], (None, None))
                src = ((None, 'tvrage')[INDEXER_TVRAGE == indexer], 'tvdb')[INDEXER_TVDB == indexer]
                if src:
                    filtered[-1]['ids'][src] = indexerid
                    filtered[-1]['url_' + src] = sickbeard.indexerApi(indexer).config['show_url'] % indexerid
            except (AttributeError, TypeError, KeyError, IndexError):
                pass

        kwargs.update(dict(oldest=oldest, newest=newest))

        return show_list and True or None

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
                        overview='No overview yet' if not overview else self.encode_html(overview[:250:]),
                        rating=0 if not len(rating) else int(helpers.tryFloat(rating) * 10),
                        title=title.get_text().strip(),
                        url_src_db='http://www.imdb.com/%s/' % url_path.strip('/'),
                        votes=0 if not len(voting) else helpers.tryInt(voting, 'TBA')))

                    show = filter(lambda x: x.imdbid == ids['imdb'], sickbeard.showList)[0]
                    src = ((None, 'tvrage')[INDEXER_TVRAGE == show.indexer], 'tvdb')[INDEXER_TVDB == show.indexer]
                    if src:
                        filtered[-1]['ids'][src] = show.indexerid
                        filtered[-1]['url_' + src] = sickbeard.indexerApi(show.indexer).config['show_url'] % \
                                                     show.indexerid
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
        url_ui = '?mode=detail&page=1&sort=date_added,desc&title_type=tvSeries%2CtvEpisode&ref_=wl_ref_typ'

        html = helpers.getURL(url + url_ui, headers={'Accept-Language': 'en-US'})
        if html:
            show_list_found = None
            try:
                data = json.loads((re.findall(r'(?im)IMDb.*?Initial.*?\.push\((.*)\).*?$', html) or ['{}'])[0])
                show_list_found = self.parse_imdb(data, filtered, kwargs)
            except (StandardError, Exception):
                pass
            if not show_list_found:
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
            show_list_found = None
            try:
                data = json.loads((re.findall(r'(?im)IMDb.*?Initial.*?\.push\((.*)\).*?$', html) or ['{}'])[0])
                show_list_found = self.parse_imdb(data, filtered, kwargs)
            except (StandardError, Exception):
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

    def trakt_watchlist(self, *args, **kwargs):

        if 'add' == kwargs.get('action'):
            return self.redirect('/config/notifications/#tabs-3')

        account = sickbeard.helpers.tryInt(kwargs.get('account'), None)
        try:
            name = sickbeard.TRAKT_ACCOUNTS[account].name
        except KeyError:
            return self.trakt_default()
        return self.browse_trakt(
                'users/%s/watchlist/shows?limit=%s&' % (sickbeard.TRAKT_ACCOUNTS[account].slug, 100), 'WatchList for <b class="grey-text">%s</b> by Trakt' % name,
                mode='watchlist-%s' % account, send_oauth=account)

    def trakt_default(self):

        return self.redirect('/home/addShows/%s' % ('trakt_trending', sickbeard.TRAKT_MRU)[any(sickbeard.TRAKT_MRU)])

    @staticmethod
    def get_trakt_data(url_path, *args, **kwargs):
        normalised, filtered = ([], [])
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

        if not normalised:
            error_msg = 'No items in watchlist.  Use the "Add to watchlist" button at the Trakt website'
            raise Exception(error_msg)

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
                images = dict(poster=dict(thumb='imagecache?path=browse/thumb/trakt&filename=%s&tmdbid=%s&tvdbid=%s' %
                                                ('%s.jpg' % traktid, tmdbid, tvdbid)))

                filtered.append(dict(
                    premiered=dt_ordinal,
                    premiered_str=dt_string,
                    when_past=dt_ordinal < datetime.datetime.now().toordinal(),  # air time not yet available 16.11.2015
                    episode_number='' if 'episode' not in item else item['episode']['number'] or 1,
                    episode_overview=('' if 'episode' not in item else
                                      item['episode']['overview'].strip() or ''),
                    episode_season='' if 'episode' not in item else item['episode']['season'] or 1,
                    genres=('' if 'genres' not in item['show'] else
                            ', '.join(['%s' % v for v in item['show']['genres']])),
                    ids=item['show']['ids'],
                    images=images,
                    overview=('' if 'overview' not in item['show'] or None is item['show']['overview'] else
                              item['show']['overview'].strip()),
                    rating=0 < item['show'].get('rating', 0) and
                           ('%.2f' % (item['show'].get('rating') * 10)).replace('.00', '') or 0,
                    title=item['show']['title'].strip(),
                    url_src_db='https://trakt.tv/shows/%s' % item['show']['ids']['slug'],
                    url_tvdb=('', sickbeard.indexerApi(INDEXER_TVDB).config['show_url'] % item['show']['ids']['tvdb'])[
                        isinstance(item['show']['ids']['tvdb'], (int, long))
                        and 0 < item['show']['ids']['tvdb']],
                    votes='0' if 'votes' not in item['show'] else item['show']['votes']))
            except (StandardError, Exception):
                pass

        if 'web_ui' in kwargs:
            return filtered, oldest, newest, error_msg

        return filtered, oldest, newest

    def browse_trakt(self, url_path, browse_title, *args, **kwargs):

        browse_type = 'Trakt'
        normalised, filtered = ([], [])

        if not sickbeard.USE_TRAKT and ('recommended' in kwargs.get('mode', '') or 'watchlist' in kwargs.get('mode', '')):
            error_msg = 'To browse personal recommendations, enable Trakt.tv in Config/Notifications/Social'
            return self.browse_shows(browse_type, browse_title, filtered, error_msg=error_msg, show_header=1, **kwargs)

        try:
            filtered, oldest, newest, error_msg = self.get_trakt_data(url_path, web_ui=True,
                                                                      send_oauth=kwargs.get('send_oauth', None))
        except (StandardError, Exception):
            error_msg = 'No items in watchlist.  Use the "Add to watchlist" button at the Trakt website'
            return self.browse_shows(browse_type, browse_title, filtered, error_msg=error_msg, show_header=1, **kwargs)

        for item in filtered:
            key = 'episode_overview'
            if item[key]:
                item[key] = self.encode_html(item[key][:250:].strip())
            key = 'overview'
            if item[key]:
                item[key] = self.encode_html(item[key][:250:].strip())

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
        for sid in ids.split(':'):
            if 3 < len(sid) < 12:
                save_config = True
                if sid in sickbeard.BROWSELIST_HIDDEN:
                    sickbeard.BROWSELIST_HIDDEN.remove(sid)
                else:
                    sickbeard.BROWSELIST_HIDDEN += [sid]
        if save_config:
            sickbeard.save_config()
        return json.dumps({'success': save_config})

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
        t = PageTemplate(web_handler=self, file='home_browseShows.tmpl')
        t.submenu = self.HomeMenu()
        t.browse_type = browse_type
        t.browse_title = browse_title
        t.all_shows = []
        t.kwargs = kwargs
        dedupe = []

        t.num_inlibrary = 0
        t.num_hidden = 0
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
                    t.num_inlibrary += 1
                    break

                if None is not config.to_int(item['show_id'], None):
                    break

            if not item['show_id'] and 'tt' in item['ids'].get('imdb', ''):
                item['show_id'] = item['ids']['imdb']

            if item['show_id'] not in dedupe:
                dedupe.append(item['show_id'])
                t.all_shows.append(item)

                if item['show_id'].split(':')[-1] in sickbeard.BROWSELIST_HIDDEN:
                    t.num_hidden += 1

        return t.respond()

    def import_shows(self, *args, **kwargs):
        """
        Prints out the page to add existing shows from a root dir
        """
        t = PageTemplate(web_handler=self, file='home_addExistingShow.tmpl')
        t.submenu = self.HomeMenu()
        t.enable_anime_options = False
        t.kwargs = kwargs
        t.multi_parents = helpers.maybe_plural(len(sickbeard.ROOT_DIRS.split('|')[1:])) and 's are' or ' is'

        return t.respond()

    def addNewShow(self, whichSeries=None, indexerLang='en', rootDir=None, defaultStatus=None,
                   quality_preset=None, anyQualities=None, bestQualities=None, upgrade_once=None,
                   flatten_folders=None, subtitles=None,
                   fullShowPath=None, other_shows=None, skipShow=None, providedIndexer=None, anime=None,
                   scene=None, blacklist=None, whitelist=None, wanted_begin=None, wanted_latest=None,
                   prune=None, tag=None, return_to=None, cancel_form=None):
        """
        Receive tvdb id, dir, and other options and create a show from them. If extra show dirs are
        provided then it forwards back to new_show, if not it goes to /home.
        """
        if None is not return_to:
            indexer, void, indexer_id, show_name = self.split_extra_show(whichSeries)
            if bool(helpers.tryInt(cancel_form)):
                indexer = indexer or providedIndexer or '0'
                indexer_id = re.findall('show=([\d]+)', return_to)[0]
            return self.redirect(return_to % (indexer, indexer_id))

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
                return self.redirect('/home/addShows/import_shows/')

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
            new_show = False
        else:
            show_dir = ek.ek(os.path.join, rootDir, helpers.sanitizeFileName(show_name))
            new_show = True

        # blanket policy - if the dir exists you should have used 'add existing show' numbnuts
        if ek.ek(os.path.isdir, show_dir) and not fullShowPath:
            ui.notifications.error('Unable to add show', u'Found existing folder: ' + show_dir)
            return self.redirect('/home/addShows/import_shows?sid=%s&hash_dir=%s' % (indexer_id, abs(hash(show_dir))))

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
        upgrade_once = config.checkbox_to_value(upgrade_once)

        wanted_begin = config.minimax(wanted_begin, 0, -1, 10)
        wanted_latest = config.minimax(wanted_latest, 0, -1, 10)
        prune = config.minimax(prune, 0, 0, 9999)

        # add the show
        sickbeard.showQueueScheduler.action.addShow(indexer, indexer_id, show_dir, int(defaultStatus), newQuality,
                                                    flatten_folders, indexerLang, subtitles, anime,
                                                    scene, None, blacklist, whitelist,
                                                    wanted_begin, wanted_latest, prune, tag, new_show=new_show,
                                                    show_name=show_name, upgrade_once=upgrade_once)
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
                                                            scene=sickbeard.SCENE_DEFAULT,
                                                            show_name=show_name)
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
    def ManageMenu(self, exclude='n/a'):
        menu = [
            {'title': 'Backlog Overview', 'path': 'manage/backlogOverview/'},
            {'title': 'Media Search', 'path': 'manage/manageSearches/'},
            {'title': 'Show Processes', 'path': 'manage/showProcesses/'},
            {'title': 'Episode Status', 'path': 'manage/episodeStatuses/'}, ]

        if sickbeard.USE_SUBTITLES:
            menu.append({'title': 'Missed Subtitle Management', 'path': 'manage/subtitleMissed/'})

        if sickbeard.USE_FAILED_DOWNLOADS:
            menu.append({'title': 'Failed Downloads', 'path': 'manage/failedDownloads/'})

        return [x for x in menu if exclude not in x['title']]

    def index(self, *args, **kwargs):
        t = PageTemplate(web_handler=self, file='manage.tmpl')
        t.submenu = self.ManageMenu('Bulk')
        return t.respond()

    def showEpisodeStatuses(self, indexer_id, whichStatus):
        whichStatus = helpers.tryInt(whichStatus)
        status_list = ((([whichStatus],
                         Quality.SNATCHED_ANY)[SNATCHED == whichStatus],
                        Quality.DOWNLOADED)[DOWNLOADED == whichStatus],
                       Quality.ARCHIVED)[ARCHIVED == whichStatus]

        myDB = db.DBConnection()
        cur_show_results = myDB.select(
            'SELECT season, episode, name, airdate, status FROM tv_episodes WHERE showid = ? AND season != 0 AND status IN (' + ','.join(
                ['?'] * len(status_list)) + ')', [int(indexer_id)] + status_list)

        result = {}
        for cur_result in cur_show_results:
            if not sickbeard.SEARCH_UNAIRED and 1000 > cur_result['airdate']:
                continue
            cur_season = int(cur_result['season'])
            cur_episode = int(cur_result['episode'])

            if cur_season not in result:
                result[cur_season] = {}

            cur_quality = Quality.splitCompositeStatus(int(cur_result['status']))[1]
            result[cur_season][cur_episode] = {'name': cur_result['name'],
                                               'airdate_never': 1000 > int(cur_result['airdate']),
                                               'qualityCss': Quality.get_quality_css(cur_quality),
                                               'qualityStr': Quality.qualityStrings[cur_quality],
                                               'sxe': '%d x %02d' % (cur_season, cur_episode)}

        return json.dumps(result)

    def episodeStatuses(self, whichStatus=None):

        whichStatus = helpers.tryInt(whichStatus)
        if whichStatus:
            status_list = ((([whichStatus],
                             Quality.SNATCHED_ANY)[SNATCHED == whichStatus],
                            Quality.DOWNLOADED)[DOWNLOADED == whichStatus],
                           Quality.ARCHIVED)[ARCHIVED == whichStatus]
        else:
            status_list = []

        t = PageTemplate(web_handler=self, file='manage_episodeStatuses.tmpl')
        t.submenu = self.ManageMenu('Episode')
        t.whichStatus = whichStatus

        my_db = db.DBConnection()
        sql_result = my_db.select(
            'SELECT COUNT(*) AS snatched FROM [tv_episodes] WHERE season > 0 AND episode > 0 AND airdate > 1 AND ' +
            'status IN (%s)' % ','.join([str(quality) for quality in Quality.SNATCHED_ANY]))
        t.default_manage = sql_result and sql_result[0]['snatched'] and SNATCHED or WANTED

        # if we have no status then this is as far as we need to go
        if not status_list:
            return t.respond()

        status_results = my_db.select(
            'SELECT show_name, tv_shows.indexer_id as indexer_id, airdate FROM tv_episodes, tv_shows WHERE tv_episodes.status IN (' + ','.join(
                ['?'] * len(
                    status_list)) + ') AND season != 0 AND tv_episodes.showid = tv_shows.indexer_id ORDER BY show_name COLLATE NOCASE',
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
        status = int(oldStatus)
        status_list = ((([status],
                         Quality.SNATCHED_ANY)[SNATCHED == status],
                        Quality.DOWNLOADED)[DOWNLOADED == status],
                       Quality.ARCHIVED)[ARCHIVED == status]

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
                subliminal.language.Language(subtitle, strict=False).alpha2
                for subtitle in cur_result['subtitles'].split(',')) if '' != cur_result['subtitles'] else ''

        return json.dumps(result)

    def subtitleMissed(self, whichSubs=None):

        t = PageTemplate(web_handler=self, file='manage_subtitleMissed.tmpl')
        t.submenu = self.ManageMenu('Subtitle')
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

        t = PageTemplate(web_handler=self, file='manage_backlogOverview.tmpl')
        t.submenu = self.ManageMenu('Backlog')

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

        t = PageTemplate(web_handler=self, file='manage_massEdit.tmpl')
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

        root_dir_list = []

        for curShow in showList:

            cur_root_dir = ek.ek(os.path.dirname, curShow._location)
            if cur_root_dir not in root_dir_list:
                root_dir_list.append(cur_root_dir)

            if upgrade_once_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_upgrade_once not in (None, curShow.upgrade_once):
                    upgrade_once_all_same = False
                else:
                    last_upgrade_once = curShow.upgrade_once

            # if we know they're not all the same then no point even bothering
            if paused_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_paused not in (None, curShow.paused):
                    paused_all_same = False
                else:
                    last_paused = curShow.paused

            if prune_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_prune not in (None, curShow.prune):
                    prune_all_same = False
                else:
                    last_prune = curShow.prune

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
        t.root_dir_list = root_dir_list

        return t.respond()

    def massEditSubmit(self, upgrade_once=None, paused=None, anime=None, sports=None, scene=None,
                       flatten_folders=None, quality_preset=False, subtitles=None, air_by_date=None, anyQualities=[],
                       bestQualities=[], toEdit=None, prune=None, tag=None, *args, **kwargs):

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

            if upgrade_once == 'keep':
                new_upgrade_once = showObj.upgrade_once
            else:
                new_upgrade_once = True if 'enable' == upgrade_once else False
            new_upgrade_once = 'on' if new_upgrade_once else 'off'

            if paused == 'keep':
                new_paused = showObj.paused
            else:
                new_paused = True if paused == 'enable' else False
            new_paused = 'on' if new_paused else 'off'

            new_prune = (config.minimax(prune, 0, 0, 9999), showObj.prune)[prune in (None, '', 'keep')]

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
                                                                       upgrade_once=new_upgrade_once,
                                                                       flatten_folders=new_flatten_folders,
                                                                       paused=new_paused, sports=new_sports,
                                                                       subtitles=new_subtitles, anime=new_anime,
                                                                       scene=new_scene, air_by_date=new_air_by_date,
                                                                       prune=new_prune, tag=new_tag, directCall=True)

            if curErrors:
                logger.log(u'Errors: ' + str(curErrors), logger.ERROR)
                errors.append('<b>%s:</b>\n<ul>' % showObj.name + ' '.join(
                    ['<li>%s</li>' % error for error in curErrors]) + '</ul>')

        if len(errors) > 0:
            ui.notifications.error('%d error%s while saving changes:' % (len(errors), '' if len(errors) == 1 else 's'),
                                   ' '.join(errors))

        self.redirect('/manage/')

    def bulkChange(self, toUpdate=None, toRefresh=None, toRename=None, toDelete=None, toRemove=None, toMetadata=None, toSubtitle=None):

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
            myDB.action('DELETE FROM failed WHERE `release` like ?', [item])

        if toRemove:
            return self.redirect('/manage/failedDownloads/')

        t = PageTemplate(web_handler=self, file='manage_failedDownloads.tmpl')
        t.over_limit = limit and len(sql_results) > limit
        t.failedResults = t.over_limit and sql_results[0:-1] or sql_results
        t.limit = str(limit)
        t.submenu = self.ManageMenu('Failed')

        return t.respond()


class ManageSearches(Manage):
    def index(self, *args, **kwargs):
        t = PageTemplate(web_handler=self, file='manage_manageSearches.tmpl')
        # t.backlog_pi = sickbeard.backlogSearchScheduler.action.get_progress_indicator()
        t.backlog_paused = sickbeard.searchQueueScheduler.action.is_backlog_paused()
        t.backlog_running = sickbeard.searchQueueScheduler.action.is_backlog_in_progress()
        t.backlog_is_active = sickbeard.backlogSearchScheduler.action.am_running()
        t.standard_backlog_running = sickbeard.searchQueueScheduler.action.is_standard_backlog_in_progress()
        t.backlog_running_type = sickbeard.searchQueueScheduler.action.type_of_backlog_in_progress()
        t.recent_search_status = sickbeard.searchQueueScheduler.action.is_recentsearch_in_progress()
        t.find_propers_status = sickbeard.searchQueueScheduler.action.is_propersearch_in_progress()
        t.queue_length = sickbeard.searchQueueScheduler.action.queue_length()

        t.submenu = self.ManageMenu('Search')

        return t.respond()

    def retryProvider(self, provider=None, *args, **kwargs):
        if not provider:
            return
        prov = [p for p in sickbeard.providerList + sickbeard.newznabProviderList if p.get_id() == provider]
        if not prov:
            return
        prov[0].retry_next()
        time.sleep(3)
        return

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


class showProcesses(Manage):
    def index(self, *args, **kwargs):
        t = PageTemplate(web_handler=self, file='manage_showProcesses.tmpl')
        t.queue_length = sickbeard.showQueueScheduler.action.queue_length()
        t.show_list = sickbeard.showList
        t.show_update_running = sickbeard.showQueueScheduler.action.isShowUpdateRunning() or sickbeard.showUpdateScheduler.action.amActive

        myDb = db.DBConnection(row_type='dict')
        sql_results = myDb.select('SELECT n.indexer, n.indexer_id, n.last_success, n.fail_count, s.show_name FROM tv_shows_not_found as n INNER JOIN tv_shows as s ON (n.indexer == s.indexer AND n.indexer_id == s.indexer_id)')
        for s in sql_results:
            date = helpers.tryInt(s['last_success'])
            s['last_success'] = ('never', sbdatetime.sbdatetime.fromordinal(date).sbfdate())[date > 1]
            s['ignore_warning'] = 0 > s['fail_count']
        defunct_indexer = [i for i in sickbeard.indexerApi().all_indexers if sickbeard.indexerApi(i).config.get('defunct')]
        sql_r = None
        if defunct_indexer:
            sql_r = myDb.select('SELECT indexer, indexer_id, show_name FROM tv_shows WHERE indexer IN (%s)' % ','.join(['?'] * len(defunct_indexer)), defunct_indexer)
        t.defunct_indexer = sql_r
        t.not_found_shows = sql_results

        t.submenu = self.ManageMenu('Processes')

        return t.respond()

    def forceShowUpdate(self, *args, **kwargs):

        result = sickbeard.showUpdateScheduler.forceRun()
        if result:
            logger.log(u'Show Update forced')
            ui.notifications.message('Forced Show Update started')

        time.sleep(5)
        self.redirect('/manage/showProcesses/')

    @staticmethod
    def switch_ignore_warning(*args, **kwargs):

        for k, v in kwargs.iteritems():
            try:
                indexer_id, state = k.split('|')
            except ValueError:
                continue
            indexer, indexer_id = helpers.tryInt(v), helpers.tryInt(indexer_id)
            if 0 < indexer and 0 < indexer_id:
                show_obj = helpers.find_show_by_id(sickbeard.showList, {indexer: indexer_id})
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

    def index(self, limit=100):

        t = PageTemplate(web_handler=self, file='history.tmpl')
        t.limit = limit

        my_db = db.DBConnection(row_type='dict')

        result_sets = []
        if sickbeard.HISTORY_LAYOUT in ('compact', 'detailed'):

            # sqlResults = myDB.select('SELECT h.*, show_name, name FROM history h, tv_shows s, tv_episodes e
            #  WHERE h.showid=s.indexer_id AND h.showid=e.showid AND h.season=e.season AND h.episode=e.episode
            #  ORDER BY date DESC LIMIT '+str(numPerPage*(p-1))+', '+str(numPerPage))
            sql = 'SELECT h.*, show_name' \
                  ' FROM history h, tv_shows s' \
                  ' WHERE h.showid=s.indexer_id' \
                  ' ORDER BY date DESC%s' % (' LIMIT %s' % limit, '')['0' == limit]
            sql_results = my_db.select(sql)

            compact = []

            for sql_result in sql_results:

                action = dict(time=sql_result['date'], action=sql_result['action'],
                              provider=sql_result['provider'], resource=sql_result['resource'])

                if not any((record['show_id'] == sql_result['showid']
                            and record['season'] == sql_result['season']
                            and record['episode'] == sql_result['episode']
                            and record['quality'] == sql_result['quality']) for record in compact):

                    cur_res = dict(show_id=sql_result['showid'], show_name=sql_result['show_name'],
                                   season=sql_result['season'], episode=sql_result['episode'],
                                   quality=sql_result['quality'], resource=sql_result['resource'], actions=[])

                    cur_res['actions'].append(action)
                    cur_res['actions'].sort(key=lambda x: x['time'])

                    compact.append(cur_res)
                else:
                    index = [i for i, record in enumerate(compact)
                             if record['show_id'] == sql_result['showid']
                             and record['season'] == sql_result['season']
                             and record['episode'] == sql_result['episode']
                             and record['quality'] == sql_result['quality']][0]

                    cur_res = compact[index]

                    cur_res['actions'].append(action)
                    cur_res['actions'].sort(key=lambda x: x['time'], reverse=True)

            t.compact_results = compact
            t.history_results = sql_results
            t.submenu = [{'title': 'Clear History', 'path': 'history/clearHistory'},
                         {'title': 'Trim History', 'path': 'history/trimHistory'}]

            result_sets = ['compact_results', 'history_results']

        elif 'watched' in sickbeard.HISTORY_LAYOUT:

            t.hide_watched_help = my_db.has_flag(self.flagname_help_watched)

            t.results = my_db.select(
                'SELECT tvs.show_name, '
                ' tve.indexer, tve.showid, tve.season, tve.episode, tve.status, tve.file_size,'
                ' tvew.rowid, tvew.tvep_id, tvew.label, tvew.played, tvew.date_watched,'
                ' tvew.status as status_w, tvew.location, tvew.file_size as file_size_w, tvew.hide'
                ' FROM [tv_shows] AS tvs'
                ' INNER JOIN [tv_episodes] AS tve ON (tvs.indexer == tve.indexer AND tvs.indexer_id == tve.showid)'
                ' INNER JOIN [tv_episodes_watched] AS tvew ON (tve.episode_id == tvew.tvep_id)'
                ' WHERE 0 = hide'
                ' ORDER BY tvew.date_watched DESC'
                '%s' % (' LIMIT %s' % limit, '')['0' == limit])

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

                r['status'], r['quality'] = Quality.splitCompositeStatus(helpers.tryInt(r['status']))
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
            sql = 'SELECT COUNT(1) as count,' \
                  ' MIN(DISTINCT date) as earliest,' \
                  ' MAX(DISTINCT date) as latest,' \
                  ' provider ' \
                  'FROM ' \
                  '(SELECT * FROM history h, tv_shows s' \
                  ' WHERE h.showid=s.indexer_id' \
                  ' AND h.provider in ("%s")' % '","'.join(prov_list) + \
                  ' AND h.action in ("%s")' % '","'.join([str(x) for x in Quality.SNATCHED_ANY]) + \
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

            t.provider_fail_stats = filter(lambda stat: len(stat['fails']), [{
                'active': p.is_active(), 'name': p.name, 'prov_id': p.get_id(), 'prov_img': p.image_name(),
                'fails': p.fails.fails_sorted, 'tmr_limit_time': p.tmr_limit_time,
                'next_try': p.get_next_try_time, 'has_limit': getattr(p, 'has_limit', False)}
                for p in sickbeard.providerList + sickbeard.newznabProviderList])
            t.provider_fail_stats = sorted([item for item in t.provider_fail_stats],
                                           key=lambda y: y.get('fails')[0].get('timestamp'),
                                           reverse=True)
            t.provider_fail_stats = sorted([item for item in t.provider_fail_stats],
                                           key=lambda y: y.get('next_try') or datetime.timedelta(weeks=65535),
                                           reverse=False)

            t.provider_fails = 0 < len([p for p in t.provider_fail_stats if len(p['fails'])])

        article_match = '^((?:A(?!\s+to)n?)|The)\s+(.*)$'
        for rs in [getattr(t, name, []) for name in result_sets]:
            for r in rs:
                r['name1'] = ''
                r['name2'] = r['data_name'] = r['show_name']
                if not sickbeard.SORT_ARTICLE:
                    try:
                        r['name1'], r['name2'] = re.findall(article_match, r['show_name'])[0]
                        r['data_name'] = r['name2']
                    except (StandardError, Exception):
                        pass

        return t.respond()

    def check_site(self, site_name='', *args, **kwargs):

        site_url = dict(
            tvdb='api.thetvdb.com', thexem='thexem.de', github='github.com'
        ).get(site_name.replace('check_', ''))

        result = {}

        if site_url:
            resp = helpers.getURL('https://www.isitdownrightnow.com/check.php?domain=%s' % site_url)
            if resp:
                check = resp.lower()
                day = re.findall(r'(\d+)\s*(?:day)', check)
                hr = re.findall(r'(\d+)\s*(?:hour)', check)
                mn = re.findall(r'(\d+)\s*(?:min)', check)
                if any([day, hr, mn]):
                    period = ', '.join(
                        (day and ['%sd' % day[0]] or day)
                        + (hr and ['%sh' % hr[0]] or hr)
                        + (mn and ['%sm' % mn[0]] or mn))
                else:
                    try:
                        period = re.findall('[^>]>([^<]+)ago', check)[0].strip()
                    except (StandardError, Exception):
                        try:
                            period = re.findall('[^>]>([^<]+week)', check)[0]
                        except (StandardError, Exception):
                            period = 'quite some time'

                result = {('last_down', 'down_for')['up' not in check and 'down for' in check]: period}

        return json.dumps(result)

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

    @staticmethod
    def update_watched_state_emby():

        import sickbeard.notifiers.emby as emby

        client = emby.EmbyNotifier()
        hosts, keys, message = client.check_config(sickbeard.EMBY_HOST, sickbeard.EMBY_APIKEY)

        if sickbeard.USE_EMBY and hosts:
            logger.log('Updating Emby watched episode states', logger.DEBUG)

            rd = sickbeard.ROOT_DIRS.split('|')[1:] + \
                 [x.split('=')[0] for x in sickbeard.EMBY_PARENT_MAPS.split(',') if any(x)]
            rootpaths = sorted(
                ['%s%s' % (ek.ek(os.path.splitdrive, x)[1], os.path.sep) for x in rd], key=len, reverse=True)
            rootdirs = sorted([x for x in rd], key=len, reverse=True)
            headers = {'Content-type': 'application/json'}
            states = {}
            idx = 0
            mapped = 0
            mapping = None
            maps = [x.split('=') for x in sickbeard.EMBY_PARENT_MAPS.split(',') if any(x)]
            for i, cur_host in enumerate(hosts):
                base_url = 'http://%s/emby/Users' % cur_host
                headers.update({'X-MediaBrowser-Token': keys[i]})

                users = sickbeard.helpers.getURL(base_url, headers=headers,
                                                 params=dict(format='json'), timeout=10, json=True)

                for user_id in [u.get('Id') for u in users if u.get('Id')]:
                    user_url = '%s/%s' % (base_url, user_id)
                    user = sickbeard.helpers.getURL(user_url, headers=headers,
                                                    params=dict(format='json'), timeout=10, json=True)

                    for folder_id in user.get('Policy', {}).get('EnabledFolders') or []:
                        folder = sickbeard.helpers.getURL('%s/Items/%s' % (user_url, folder_id), headers=headers,
                                                          params=dict(format='json'), timeout=10, json=True)

                        if not folder or 'tvshows' != folder.get('CollectionType', ''):
                            continue

                        items = sickbeard.helpers.getURL('%s/Items' % user_url, headers=headers,
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
                                                                     format='json'), timeout=10, json=True)
                        for d in filter(lambda item: 'Episode' == item.get('Type', ''), items.get('Items')):
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
                                    played=(d.get('UserData', {}).get('PlayedPercentage') or
                                            (d.get('UserData', {}).get('Played') and
                                             d.get('UserData', {}).get('PlayCount') * 100) or 0),
                                    label='%s%s{Emby}' % (user.get('Name', ''), bool(user.get('Name')) and ' ' or ''),
                                    date_watched=sickbeard.sbdatetime.sbdatetime.totimestamp(
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
                            except(StandardError, Exception):
                                continue
            if mapping:
                logger.log('Folder mappings used, the first of %s is [%s] in Emby is [%s] in SickGear' %
                           (mapped, mapping[0], mapping[1]), logger.DEBUG)

            if states:
                # Prune user removed items that are no longer being returned by API
                my_db = db.DBConnection(row_type='dict')
                media_paths = map(lambda (_, s): ek.ek(os.path.basename, s['path_file']), states.iteritems())
                my_db.select('DELETE FROM tv_episodes_watched WHERE hide=1 AND label LIKE "%%{Emby}" AND %s' %
                             ' AND '.join(['location NOT LIKE "%%%s"' % x for x in media_paths]))

                MainHandler.update_watched_state(states, False)

            logger.log('Finished updating Emby watched episode states')

    @staticmethod
    def update_watched_state_plex():

        hosts = [x.strip().lower() for x in sickbeard.PLEX_SERVER_HOST.split(',')]
        if sickbeard.USE_PLEX and hosts:
            logger.log('Updating Plex watched episode states', logger.DEBUG)

            from plex import Plex
            import urllib2

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
                parts = urllib2.splitport(cur_host)
                if parts[0]:
                    plex.plex_host = parts[0]
                    if None is not parts[1]:
                        plex.plex_port = parts[1]

                    plex.fetch_show_states()

                    for k, v in plex.show_states.iteritems():
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
                my_db = db.DBConnection(row_type='dict')
                media_paths = map(lambda (_, s): ek.ek(os.path.basename, s['path_file']), states.iteritems())
                my_db.select('DELETE FROM tv_episodes_watched WHERE hide=1 AND label LIKE "%%{Plex}" AND %s' %
                             ' AND '.join(['location NOT LIKE "%%%s"' % x for x in media_paths]))

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
            rowid, tvid, shoid = show_detail.split('-')
            row_show_ids.update({int(rowid): {int(tvid): int(shoid)}})

        sql_results = my_db.select(
            'SELECT rowid, tvep_id, label, location'
            ' FROM [tv_episodes_watched] WHERE `rowid` in (%s)' % ','.join([str(k) for k in row_show_ids.keys()])
        )

        h_records = []
        removed = []
        deleted = {}
        attempted = []
        refresh = []
        for r in sql_results:
            if files and r['location'] not in attempted and 0 < helpers.get_size(r['location'])\
                    and ek.ek(os.path.isfile, r['location']):
                # locations repeat with watch events but attempt to delete once
                attempted += [r['location']]

                result = helpers.remove_file(r['location'])
                if result:
                    logger.log(u'%s file %s' % (result, r['location']))

                    deleted.update({r['tvep_id']: row_show_ids[r['rowid']]})
                    if row_show_ids[r['rowid']] not in refresh:
                        # schedule a show for one refresh after deleting an arbitrary number of locations
                        refresh += [row_show_ids[r['rowid']]]

            if records:
                if not r['label'].endswith('{Emby}') and not r['label'].endswith('{Plex}'):
                    r_del = my_db.action('DELETE FROM [tv_episodes_watched] WHERE `rowid` == ?', [r['rowid']])
                    if 1 == r_del.rowcount:
                        h_records += ['%s-%s-%s' % (r['rowid'], k, v) for k, v in row_show_ids[r['rowid']].iteritems()]
                else:
                    r_del = my_db.action('UPDATE [tv_episodes_watched] SET hide=1 WHERE `rowid` == ?', [r['rowid']])
                    if 1 == r_del.rowcount:
                        removed += ['%s-%s-%s' % (r['rowid'], k, v) for k, v in row_show_ids[r['rowid']].iteritems()]

        updating = False
        for epid, tvid_shoid_dict in deleted.iteritems():
            sql_results = my_db.select('SELECT season, episode FROM [tv_episodes] WHERE `episode_id` = %s' % epid)
            for r in sql_results:
                show = helpers.find_show_by_id(sickbeard.showList, tvid_shoid_dict)
                ep_obj = show.getEpisode(r['season'], r['episode'])
                for n in filter(lambda x: x.name.lower() in ('emby', 'kodi', 'plex'),
                                notifiers.NotifierFactory().get_enabled()):
                    if 'PLEX' == n.name:
                        if updating:
                            continue
                        updating = True
                    n.update_library(show=show, show_name=show.name, ep_obj=ep_obj)

        for tvid_shoid_dict in refresh:
            try:
                sickbeard.showQueueScheduler.action.refreshShow(
                    helpers.find_show_by_id(sickbeard.showList, tvid_shoid_dict))
            except (StandardError, Exception):
                pass

        if not any([removed, h_records, len(deleted)]):
            msg = 'No items removed and no files deleted'
        else:
            msg = []
            if deleted:
                msg += ['%s %s media file%s' % (
                    ('Permanently deleted', 'Trashed')[sickbeard.TRASH_REMOVE_SHOW],
                    len(deleted), helpers.maybe_plural(len(deleted)))]
            elif removed:
                msg += ['Removed %s watched history item%s' % (len(removed), helpers.maybe_plural(len(removed)))]
            else:
                msg += ['Deleted %s watched history item%s' % (len(h_records), helpers.maybe_plural(len(h_records)))]
            msg = '<br>'.join(msg)

        ui.notifications.message('History : Watch',  msg)

        return json.dumps(dict(success=h_records))


class Config(MainHandler):
    @staticmethod
    def ConfigMenu(exclude='n/a'):
        menu = [
            {'title': 'General', 'path': 'config/general/'},
            {'title': 'Media Providers', 'path': 'config/providers/'},
            {'title': 'Search', 'path': 'config/search/'},
            {'title': 'Subtitles', 'path': 'config/subtitles/'},
            {'title': 'Post Processing', 'path': 'config/postProcessing/'},
            {'title': 'Notifications', 'path': 'config/notifications/'},
            {'title': 'Anime', 'path': 'config/anime/'},
        ]
        return [x for x in menu if exclude not in x['title']]

    def index(self, *args, **kwargs):
        t = PageTemplate(web_handler=self, file='config.tmpl')
        t.submenu = self.ConfigMenu()

        return t.respond()


class ConfigGeneral(Config):
    def index(self, *args, **kwargs):

        t = PageTemplate(web_handler=self, file='config_general.tmpl')
        t.submenu = self.ConfigMenu('General')
        t.show_tags = ', '.join(sickbeard.SHOW_TAGS)
        t.indexers = dict([(i, sickbeard.indexerApi().indexers[i]) for i in sickbeard.indexerApi().indexers
                           if sickbeard.indexerApi(i).config['active']])
        t.request_host = escape.xhtml_escape(self.request.host_name)
        return t.respond()

    def saveRootDirs(self, rootDirString=None):
        sickbeard.ROOT_DIRS = rootDirString

    def saveResultPrefs(self, ui_results_sortby=None):

        if ui_results_sortby in ('az', 'date', 'rel', 'notop', 'ontop'):
            was_ontop = 'notop' not in sickbeard.RESULTS_SORTBY
            if 'top' == ui_results_sortby[-3:]:
                maybe_ontop = ('', ' notop')[was_ontop]
                sortby = sickbeard.RESULTS_SORTBY.replace(' notop', '')
                sickbeard.RESULTS_SORTBY = '%s%s' % (('rel', sortby)[any([sortby])], maybe_ontop)
            else:
                sickbeard.RESULTS_SORTBY = '%s%s' % (ui_results_sortby, (' notop', '')[was_ontop])

            sickbeard.save_config()

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
        sickbeard.SHOW_TAG_DEFAULT = default_tag

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

    def saveGeneral(self, log_dir=None, web_port=None, web_log=None, encryption_version=None, web_ipv6=None, web_ipv64=None,
                    update_shows_on_start=None, show_update_hour=None,
                    trash_remove_show=None, trash_rotate_logs=None, update_frequency=None, launch_browser=None, web_username=None,
                    use_api=None, api_key=None, indexer_default=None, timezone_display=None, cpu_preset=None, file_logging_preset=None,
                    web_password=None, version_notify=None, enable_https=None, https_cert=None, https_key=None,
                    handle_reverse_proxy=None, send_security_headers=None, allowed_hosts=None,
                    home_search_focus=None, display_freespace=None, sort_article=None, auto_update=None, notify_on_update=None,
                    proxy_setting=None, proxy_indexers=None, anon_redirect=None, git_path=None, git_remote=None, calendar_unprotected=None,
                    fuzzy_dating=None, trim_zero=None, date_preset=None, date_preset_na=None, time_preset=None,
                    indexer_timeout=None, rootDir=None, theme_name=None, default_home=None, use_imdb_info=None,
                    fanart_limit=None, show_tags=None, showlist_tagview=None):

        results = []

        # Misc
        sickbeard.LAUNCH_BROWSER = config.checkbox_to_value(launch_browser)
        sickbeard.UPDATE_SHOWS_ON_START = config.checkbox_to_value(update_shows_on_start)
        sickbeard.SHOW_UPDATE_HOUR = config.minimax(show_update_hour, 3, 0, 23)
        try:
            with sickbeard.showUpdateScheduler.lock:
                sickbeard.showUpdateScheduler.start_time = datetime.time(hour=sickbeard.SHOW_UPDATE_HOUR)
        except (StandardError, Exception) as e:
            logger.log('Could not change Show Update Scheduler time: %s' % ex(e), logger.ERROR)
        sickbeard.TRASH_REMOVE_SHOW = config.checkbox_to_value(trash_remove_show)
        sickbeard.TRASH_ROTATE_LOGS = config.checkbox_to_value(trash_rotate_logs)
        if not config.change_log_dir(log_dir, web_log):
            results += ['Unable to create directory ' + os.path.normpath(log_dir) + ', log directory not changed.']
        if indexer_default:
            sickbeard.INDEXER_DEFAULT = config.to_int(indexer_default)
            if not sickbeard.indexerApi(sickbeard.INDEXER_DEFAULT).config['active']:
                sickbeard.INDEXER_DEFAULT = INDEXER_TVDB
        if indexer_timeout:
            sickbeard.INDEXER_TIMEOUT = config.to_int(indexer_timeout)

        # Updates
        config.schedule_version_notify(config.checkbox_to_value(version_notify))
        sickbeard.AUTO_UPDATE = config.checkbox_to_value(auto_update)
        config.schedule_update(update_frequency)
        sickbeard.NOTIFY_ON_UPDATE = config.checkbox_to_value(notify_on_update)

        # Interface
        sickbeard.THEME_NAME = theme_name
        sickbeard.DEFAULT_HOME = default_home
        sickbeard.FANART_LIMIT = config.minimax(fanart_limit, 3, 0, 500)
        sickbeard.SHOWLIST_TAGVIEW = showlist_tagview

        # 'Show List' is the must have default fallback. Tags in use that are removed from config ui are restored,
        # not deleted. Deduped list order preservation is key to feature function.
        my_db = db.DBConnection()
        sql_results = my_db.select('SELECT DISTINCT tag FROM tv_shows')
        new_names = [u'' + v.strip() for v in (show_tags.split(u','), [])[None is show_tags] if v.strip()]
        orphans = [item for item in [v['tag'] for v in sql_results or []] if item not in new_names]
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
        sickbeard.API_KEY = api_key
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
        hosts = ','.join(filter(lambda name: not helpers.re_valid_hostname(with_allowed=False).match(name),
                                config.clean_hosts(allowed_hosts).split(',')))
        if not hosts or self.request.host_name in hosts:
            sickbeard.ALLOWED_HOSTS = hosts

        # Advanced
        sickbeard.GIT_REMOTE = git_remote
        sickbeard.GIT_PATH = git_path
        sickbeard.CPU_PRESET = cpu_preset
        sickbeard.ANON_REDIRECT = anon_redirect
        sickbeard.ENCRYPTION_VERSION = config.checkbox_to_value(encryption_version)
        sickbeard.PROXY_SETTING = proxy_setting
        sickbeard.PROXY_INDEXERS = config.checkbox_to_value(proxy_indexers)
        sickbeard.FILE_LOGGING_PRESET = file_logging_preset
        # sickbeard.LOG_DIR is set in config.change_log_dir()

        logger.log_set_level()

        sickbeard.save_config()

        if 0 < len(results):
            for v in results:
                logger.log(v, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
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

        t = PageTemplate(web_handler=self, file='config_search.tmpl')
        t.submenu = self.ConfigMenu('Search')
        t.using_rls_ignore_words = [(show.indexerid, show.name)
                                    for show in sickbeard.showList if show.rls_ignore_words and
                                    show.rls_ignore_words.strip()]
        t.using_rls_ignore_words.sort(lambda x, y: cmp(x[1], y[1]), reverse=False)
        t.using_rls_require_words = [(show.indexerid, show.name)
                                     for show in sickbeard.showList if show.rls_require_words and
                                     show.rls_require_words.strip()]
        t.using_rls_require_words.sort(lambda x, y: cmp(x[1], y[1]), reverse=False)
        t.using_regex = False
        try:
            from sickbeard.name_parser.parser import regex
            t.using_regex = None is not regex
        except (StandardError, Exception):
            pass
        return t.respond()

    def saveSearch(self, use_nzbs=None, use_torrents=None, nzb_dir=None,
                   sab_host=None, sab_username=None, sab_password=None, sab_apikey=None, sab_category=None,
                   nzbget_use_https=None, nzbget_host=None, nzbget_username=None, nzbget_password=None,
                   nzbget_category=None, nzbget_priority=None, nzbget_parent_map=None,
                   backlog_days=None, backlog_frequency=None, search_unaired=None, unaired_recent_search_only=None,
                   recentsearch_frequency=None, nzb_method=None, torrent_method=None, usenet_retention=None,
                   download_propers=None, propers_webdl_onegrp=None,
                   allow_high_priority=None,
                   torrent_dir=None, torrent_username=None, torrent_password=None, torrent_host=None,
                   torrent_label=None, torrent_path=None, torrent_verify_cert=None,
                   torrent_seed_time=None, torrent_paused=None, torrent_high_bandwidth=None,
                   ignore_words=None, require_words=None, backlog_nofull=None):

        results = []

        if not config.change_nzb_dir(nzb_dir):
            results += ['Unable to create directory ' + os.path.normpath(nzb_dir) + ', dir not changed.']

        if not config.change_torrent_dir(torrent_dir):
            results += ['Unable to create directory ' + os.path.normpath(torrent_dir) + ', dir not changed.']

        config.schedule_recentsearch(recentsearch_frequency)

        old_backlog_frequency = sickbeard.BACKLOG_FREQUENCY
        config.schedule_backlog(backlog_frequency)
        sickbeard.search_backlog.BacklogSearcher.change_backlog_parts(old_backlog_frequency, sickbeard.BACKLOG_FREQUENCY)
        sickbeard.BACKLOG_DAYS = config.to_int(backlog_days, default=7)

        sickbeard.BACKLOG_NOFULL = bool(config.checkbox_to_value(backlog_nofull))
        if sickbeard.BACKLOG_NOFULL:
            my_db = db.DBConnection('cache.db')
            my_db.action('DELETE FROM backlogparts')

        sickbeard.USE_NZBS = config.checkbox_to_value(use_nzbs)
        sickbeard.USE_TORRENTS = config.checkbox_to_value(use_torrents)

        sickbeard.NZB_METHOD = nzb_method
        sickbeard.TORRENT_METHOD = torrent_method
        sickbeard.USENET_RETENTION = config.to_int(usenet_retention, default=500)

        sickbeard.IGNORE_WORDS = ignore_words if ignore_words else ''
        sickbeard.REQUIRE_WORDS = require_words if require_words else ''

        config.schedule_download_propers(config.checkbox_to_value(download_propers))
        sickbeard.PROPERS_WEBDL_ONEGRP = config.checkbox_to_value(propers_webdl_onegrp)

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
        sickbeard.NZBGET_MAP = config.kv_csv(nzbget_parent_map)

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

        t = PageTemplate(web_handler=self, file='config_postProcessing.tmpl')
        t.submenu = self.ConfigMenu('Processing')
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

        if not config.change_tv_download_dir(tv_download_dir):
            results += ['Unable to create directory ' + os.path.normpath(tv_download_dir) + ', dir not changed.']

        new_val = config.checkbox_to_value(process_automatically)
        sickbeard.PROCESS_AUTOMATICALLY = new_val
        config.schedule_autopostprocesser(autopostprocesser_frequency)

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
        t = PageTemplate(web_handler=self, file='config_providers.tmpl')
        t.submenu = self.ConfigMenu('Providers')
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

    def checkProvidersPing(self):
        for p in sickbeard.providers.sortedProviderList():
            if getattr(p, 'ping_freq', None):
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

    def saveProviders(self, newznab_string='', torrentrss_string='', provider_order=None, **kwargs):

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
                                [k for k in nzb_src.may_filter.keys()
                                 if config.checkbox_to_value(kwargs.get('%s_filter_%s' % (cur_id, k)))])

                    for attr in ['search_fallback', 'enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog',
                                 'scene_only', 'scene_loose', 'scene_loose_active',
                                 'scene_rej_nuked', 'scene_nuked_active',]:
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
                            if sickbeard.GenericProvider.TORRENT == src.providerType]:
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

            for attr in filter(lambda a: hasattr(torrent_src, a), [
                'username', 'uid', '_seed_ratio', 'scene_or_contain'
            ]):
                setattr(torrent_src, attr, str(kwargs.get(src_id_prefix + attr.replace('_seed_', ''), '')).strip())

            for attr in filter(lambda a: hasattr(torrent_src, a), [
                'minseed', 'minleech', 'seed_time'
            ]):
                setattr(torrent_src, attr, config.to_int(str(kwargs.get(src_id_prefix + attr, '')).strip()))

            attr = 'filter'
            if hasattr(torrent_src, attr):
                setattr(torrent_src, attr,
                        [k for k in torrent_src.may_filter.keys()
                         if config.checkbox_to_value(kwargs.get('%sfilter_%s' % (src_id_prefix, k)))])

            for attr in filter(lambda a: hasattr(torrent_src, a), [
                'confirmed', 'freeleech', 'reject_m2ts', 'enable_recentsearch',
                'enable_backlog', 'search_fallback', 'enable_scheduled_backlog',
                'scene_only', 'scene_loose', 'scene_loose_active',
                'scene_rej_nuked', 'scene_nuked_active'
            ]):
                setattr(torrent_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)))

            for attr, default in filter(lambda (a, _): hasattr(torrent_src, a), [
                ('search_mode', 'eponly'),
            ]):
                setattr(torrent_src, attr, str(kwargs.get(src_id_prefix + attr) or default).strip())

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

            attr = 'enable_recentsearch'
            if hasattr(nzb_src, attr):
                setattr(nzb_src, attr, config.checkbox_to_value(kwargs.get(src_id_prefix + attr)) or
                        not getattr(nzb_src, 'supports_backlog', True))

            for attr in filter(lambda x: hasattr(nzb_src, x),
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

        cp = threading.Thread(name='Check-Ping-Providers', target=self.checkProvidersPing)
        cp.start()

        if 0 < len(results):
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration', '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))

        if reload_page:
            self.write('reload')
        else:
            self.redirect('/config/providers/')


class ConfigNotifications(Config):

    def index(self, *args, **kwargs):
        t = PageTemplate(web_handler=self, file='config_notifications.tmpl')
        t.submenu = self.ConfigMenu('Notifications')
        t.root_dirs = []
        if sickbeard.ROOT_DIRS:
            root_pieces = sickbeard.ROOT_DIRS.split('|')
            root_default = helpers.tryInt(root_pieces[0], None)
            for i, location in enumerate(root_pieces[1:]):
                t.root_dirs.append({'root_def': root_default and i == root_default,
                                    'loc': location,
                                    'b64': base64.urlsafe_b64encode(location)})
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
            # use_xbmc=None, xbmc_always_on=None, xbmc_notify_onsnatch=None, xbmc_notify_ondownload=None,
            # xbmc_notify_onsubtitledownload=None, xbmc_update_onlyfirst=None,
            # xbmc_update_library=None, xbmc_update_full=None,
            # xbmc_host=None, xbmc_username=None, xbmc_password=None,
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
            pushover_priority=None, pushover_device=None, pushover_sound=None, pushover_device_list=None,
            use_growl=None, growl_notify_onsnatch=None, growl_notify_ondownload=None,
            growl_notify_onsubtitledownload=None, growl_host=None, growl_password=None,
            use_prowl=None, prowl_notify_onsnatch=None, prowl_notify_ondownload=None,
            prowl_notify_onsubtitledownload=None, prowl_api=None, prowl_priority=0,
            use_libnotify=None, libnotify_notify_onsnatch=None, libnotify_notify_ondownload=None,
            libnotify_notify_onsubtitledownload=None,
            # use_pushalot=None, pushalot_notify_onsnatch=None, pushalot_notify_ondownload=None,
            # pushalot_notify_onsubtitledownload=None, pushalot_authorizationtoken=None,

            use_trakt=None,
            # trakt_pin=None, trakt_remove_watchlist=None, trakt_use_watchlist=None, trakt_method_add=None,
            # trakt_start_paused=None, trakt_sync=None, trakt_default_indexer=None, trakt_remove_serieslist=None,
            # trakt_collection=None, trakt_accounts=None,
            use_slack=None, slack_notify_onsnatch=None, slack_notify_ondownload=None,
            slack_notify_onsubtitledownload=None, slack_access_token=None, slack_channel=None,
            slack_as_authed=None, slack_bot_name=None, slack_icon_url=None,
            use_discordapp=None, discordapp_notify_onsnatch=None, discordapp_notify_ondownload=None,
            discordapp_notify_onsubtitledownload=None, discordapp_access_token=None,
            discordapp_as_authed=None, discordapp_username=None, discordapp_icon_url=None,
            discordapp_as_tts=None,
            use_gitter=None, gitter_notify_onsnatch=None, gitter_notify_ondownload=None,
            gitter_notify_onsubtitledownload=None, gitter_access_token=None, gitter_room=None,
            use_twitter=None, twitter_notify_onsnatch=None, twitter_notify_ondownload=None,
            twitter_notify_onsubtitledownload=None,
            use_email=None, email_notify_onsnatch=None, email_notify_ondownload=None,
            email_notify_onsubtitledownload=None, email_host=None, email_port=25, email_from=None,
            email_tls=None, email_user=None, email_password=None, email_list=None,
            # email_show_list=None, email_show=None,
            **kwargs):

        results = []

        sickbeard.USE_EMBY = config.checkbox_to_value(use_emby)
        sickbeard.EMBY_UPDATE_LIBRARY = config.checkbox_to_value(emby_update_library)
        sickbeard.EMBY_PARENT_MAPS = config.kv_csv(emby_parent_maps)
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
        sickbeard.KODI_PARENT_MAPS = config.kv_csv(kodi_parent_maps)
        sickbeard.KODI_HOST = config.clean_hosts(kodi_host)
        sickbeard.KODI_USERNAME = kodi_username
        if set('*') != set(kodi_password):
            sickbeard.KODI_PASSWORD = kodi_password

        # sickbeard.USE_XBMC = config.checkbox_to_value(use_xbmc)
        # sickbeard.XBMC_ALWAYS_ON = config.checkbox_to_value(xbmc_always_on)
        # sickbeard.XBMC_NOTIFY_ONSNATCH = config.checkbox_to_value(xbmc_notify_onsnatch)
        # sickbeard.XBMC_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(xbmc_notify_ondownload)
        # sickbeard.XBMC_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(xbmc_notify_onsubtitledownload)
        # sickbeard.XBMC_UPDATE_LIBRARY = config.checkbox_to_value(xbmc_update_library)
        # sickbeard.XBMC_UPDATE_FULL = config.checkbox_to_value(xbmc_update_full)
        # sickbeard.XBMC_UPDATE_ONLYFIRST = config.checkbox_to_value(xbmc_update_onlyfirst)
        # sickbeard.XBMC_HOST = config.clean_hosts(xbmc_host)
        # sickbeard.XBMC_USERNAME = xbmc_username
        # if set('*') != set(xbmc_password):
        #     sickbeard.XBMC_PASSWORD = xbmc_password

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
        # sickbeard.traktCheckerScheduler.silent = not sickbeard.USE_TRAKT
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

        sickbeard.USE_DISCORDAPP = config.checkbox_to_value(use_discordapp)
        sickbeard.DISCORDAPP_NOTIFY_ONSNATCH = config.checkbox_to_value(discordapp_notify_onsnatch)
        sickbeard.DISCORDAPP_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(discordapp_notify_ondownload)
        sickbeard.DISCORDAPP_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(discordapp_notify_onsubtitledownload)
        sickbeard.DISCORDAPP_ACCESS_TOKEN = discordapp_access_token
        sickbeard.DISCORDAPP_AS_AUTHED = config.checkbox_to_value(discordapp_as_authed)
        sickbeard.DISCORDAPP_USERNAME = discordapp_username
        sickbeard.DISCORDAPP_ICON_URL = discordapp_icon_url
        sickbeard.DISCORDAPP_AS_TTS = config.checkbox_to_value(discordapp_as_tts)

        sickbeard.USE_GITTER = config.checkbox_to_value(use_gitter)
        sickbeard.GITTER_NOTIFY_ONSNATCH = config.checkbox_to_value(gitter_notify_onsnatch)
        sickbeard.GITTER_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(gitter_notify_ondownload)
        sickbeard.GITTER_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(gitter_notify_onsubtitledownload)
        sickbeard.GITTER_ACCESS_TOKEN = gitter_access_token
        sickbeard.GITTER_ROOM = gitter_room

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

        # sickbeard.USE_PUSHALOT = config.checkbox_to_value(use_pushalot)
        # sickbeard.PUSHALOT_NOTIFY_ONSNATCH = config.checkbox_to_value(pushalot_notify_onsnatch)
        # sickbeard.PUSHALOT_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(pushalot_notify_ondownload)
        # sickbeard.PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(pushalot_notify_onsubtitledownload)
        # key = pushalot_authorizationtoken.strip()
        # if not starify(key, True):
        #     sickbeard.PUSHALOT_AUTHORIZATIONTOKEN = key

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
        t = PageTemplate(web_handler=self, file='config_subtitles.tmpl')
        t.submenu = self.ConfigMenu('Subtitle')
        return t.respond()

    def saveSubtitles(self, use_subtitles=None, subtitles_languages=None, subtitles_dir=None,
                      service_order=None, subtitles_history=None, subtitles_finder_frequency=None):
        results = []

        if subtitles_finder_frequency == '' or subtitles_finder_frequency is None:
            subtitles_finder_frequency = 1

        config.schedule_subtitles(config.checkbox_to_value(use_subtitles))
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

        t = PageTemplate(web_handler=self, file='config_anime.tmpl')
        t.submenu = self.ConfigMenu('Anime')
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
        if len(classes.ErrorViewer.errors):
            return [{'title': 'Download Log', 'path': 'errorlogs/downloadlog/'},
                    {'title': 'Clear Errors', 'path': 'errorlogs/clearerrors/'},]
        return [{'title': 'Download Log', 'path': 'errorlogs/downloadlog/'},]

    def index(self, *args, **kwargs):

        t = PageTemplate(web_handler=self, file='errorlogs.tmpl')
        t.submenu = self.ErrorLogsMenu

        return t.respond()

    def clearerrors(self, *args, **kwargs):
        classes.ErrorViewer.clear()
        self.redirect('/errorlogs/')

    def downloadlog(self, *args, **kwargs):
        logfile_name = logger.current_log_file()
        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Description', 'Logfile Download')
        self.set_header('Content-Length', ek.ek(os.path.getsize, logfile_name))
        self.set_header('Content-Disposition', 'attachment; filename=sickgear.log')
        with open(logfile_name, 'r') as logfile:
            try:
                while True:
                    data = logfile.read(4096)
                    if not data:
                        break
                    self.write(data)
                self.finish()
            except (StandardError, Exception):
                return

    def viewlog(self, min_level=logger.MESSAGE, max_lines=500):

        t = PageTemplate(web_handler=self, file='viewlogs.tmpl')
        t.submenu = self.ErrorLogsMenu

        min_level = int(min_level)

        regex = '^(\d\d\d\d)\-(\d\d)\-(\d\d)\s*(\d\d)\:(\d\d):(\d\d)\s*([A-Z]+)\s*(.+?)\s*\:\:\s*(.*)$'

        final_data = []
        normal_data = []
        truncate = []
        repeated = None
        num_lines = 0

        if os.path.isfile(logger.sb_log_instance.log_file_path):
            for x in logger.sb_log_instance.reverse_readline(logger.sb_log_instance.log_file_path):

                x = x.decode('utf-8', 'replace')
                match = re.match(regex, x)

                if match:
                    level = match.group(7)
                    if level not in logger.reverseNames:
                        normal_data = []
                        continue

                    if logger.reverseNames[level] >= min_level:
                        if truncate and not normal_data and truncate[0] == match.group(8) + match.group(9):
                            truncate += [match.group(8) + match.group(9)]
                            repeated = x
                            continue

                        if 1 < len(truncate):
                            final_data[-1] = repeated.strip() + \
                                             ' <span class="grey-text">(...%s repeat lines)</span>\n' % len(truncate)

                        truncate = [match.group(8) + match.group(9)]

                        final_data.append(x.replace(
                            ' Starting SickGear', ' <span class="prelight2">Starting SickGear</span>'))
                        if any(normal_data):
                            final_data += ['<code><span class="prelight">'] + \
                                          ['<span class="prelight-num">%02s)</span> %s' % (n + 1, x)
                                           for n, x in enumerate(normal_data[::-1])] + \
                                          ['</span></code><br />']
                            num_lines += len(normal_data)
                            normal_data = []
                    else:
                        normal_data = []
                        continue

                else:
                    if not any(normal_data) and not any([x.strip()]):
                        continue

                    normal_data.append(re.sub(r'\r?\n', '<br />', x.replace('<', '&lt;').replace('>', '&gt;')))

                num_lines += 1

                if num_lines >= max_lines:
                    break

        result = ''.join(final_data)

        t.logLines = result
        t.min_level = min_level

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
        t = PageTemplate(web_handler=self, file='apiBuilder.tmpl')

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
        t.indexers = sickbeard.indexerApi().all_indexers
        t.searchindexers = sickbeard.indexerApi().search_indexers

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

        t = PageTemplate(web_handler=self, file='cache.tmpl')
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
            if source is None and tmdbid not in [None, 'None', 0, '0'] \
                    and self.should_try_image(static_image_path, 'tmdb'):
                tmdbimage = True
                try:
                    tmdbapi = TMDB(sickbeard.TMDB_API_KEY)
                    tmdbconfig = tmdbapi.Configuration().info()
                    images = tmdbapi.TV(helpers.tryInt(tmdbid)).images()
                    s = '%s%s%s' % (tmdbconfig['images']['base_url'], tmdbconfig['images']['poster_sizes'][3],
                                    sorted(images['posters'], key=lambda x: x['vote_average'],
                                           reverse=True)[0]['file_path']) if len(images['posters']) > 0 else ''
                except (StandardError, Exception):
                    s = ''
            if s and not helpers.download_file(s, static_image_path) and s.find('trakt.us'):
                helpers.download_file(s.replace('trakt.us', 'trakt.tv'), static_image_path)
            if tmdbimage and not ek.ek(os.path.isfile, static_image_path):
                self.create_dummy_image(static_image_path, 'tmdb')

            if source is None and tvdbid not in [None, 'None', 0, '0'] \
                    and not ek.ek(os.path.isfile, static_image_path) \
                    and self.should_try_image(static_image_path, 'tvdb'):
                try:
                    lINDEXER_API_PARMS = sickbeard.indexerApi(INDEXER_TVDB).api_params.copy()
                    lINDEXER_API_PARMS['posters'] = True
                    r = sickbeard.indexerApi(INDEXER_TVDB).indexer(**lINDEXER_API_PARMS)[helpers.tryInt(tvdbid), False]
                    if hasattr(r, 'data') and 'poster' in r.data:
                        s = r.data['poster']
                except (StandardError, Exception):
                    s = ''
                if s:
                    helpers.download_file(s, static_image_path)
                if not ek.ek(os.path.isfile, static_image_path):
                    self.create_dummy_image(static_image_path, 'tvdb')

            if ek.ek(os.path.isfile, static_image_path):
                self.delete_all_dummy_images(static_image_path)

        if not ek.ek(os.path.isfile, static_image_path):
            static_image_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick',
                                      'images', ('image-light.png', 'trans.png')[bool(int(kwargs.get('trans', 1)))])
        else:
            helpers.set_file_timestamp(static_image_path, min_age=3, new_time=None)

        mime_type, encoding = MimeTypes().guess_type(static_image_path)
        self.set_header('Content-Type', mime_type)
        with open(static_image_path, 'rb') as img:
            return img.read()

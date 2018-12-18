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
from threading import Lock

import datetime
import os
import re
import signal
import socket
import webbrowser

# apparently py2exe won't build these unless they're imported somewhere
import ast
import base64
import os.path
import sys
import uuid

sys.path.insert(1, os.path.abspath('../lib'))
from sickbeard import helpers, encodingKludge as ek
from sickbeard import db, image_cache, logger, naming, metadata, providers, scene_exceptions, scene_numbering, \
    scheduler, auto_post_processer, search_queue, search_propers, search_recent, search_backlog, \
    show_queue, show_updater, subtitles, traktChecker, version_checker, indexermapper, classes, properFinder, \
    watchedstate_queue
from sickbeard.config import check_section, check_setting_int, check_setting_str, ConfigMigrator, minimax
from sickbeard.common import SD, SKIPPED
from sickbeard.databases import mainDB, cache_db, failed_db
from sickbeard.exceptions import ex
from sickbeard.providers.generic import GenericProvider
from sickbeard.providers.newznab import NewznabConstants
from sickbeard.watchedstate import EmbyWatchedStateUpdater, PlexWatchedStateUpdater
from indexers.indexer_config import INDEXER_TVDB
from indexers.indexer_api import indexerApi
from indexers.indexer_exceptions import indexer_shownotfound, indexer_exception, indexer_error, \
    indexer_episodenotfound, indexer_attributenotfound, indexer_seasonnotfound, indexer_userabort, indexerExcepts
from lib.adba.aniDBerrors import (AniDBError, AniDBBannedError)
from lib.configobj import ConfigObj
from lib.libtrakt import TraktAPI
import trakt_helpers
import threading

PID = None

CFG = None
CONFIG_FILE = None

# This is the version of the config we EXPECT to find
CONFIG_VERSION = 17

# Default encryption version (0 for None)
ENCRYPTION_VERSION = 0

PROG_DIR = '.'
MY_FULLNAME = None
MY_NAME = None
MY_ARGS = []
SYS_ENCODING = ''
DATA_DIR = ''

# system events
events = None

recentSearchScheduler = None
backlogSearchScheduler = None
showUpdateScheduler = None
versionCheckScheduler = None
showQueueScheduler = None
searchQueueScheduler = None
properFinderScheduler = None
autoPostProcesserScheduler = None
subtitlesFinderScheduler = None
# traktCheckerScheduler = None
background_mapping_task = None
embyWatchedStateScheduler = None
plexWatchedStateScheduler = None
watchedStateQueueScheduler = None

provider_ping_thread_pool = {}

showList = None
UPDATE_SHOWS_ON_START = False
SHOW_UPDATE_HOUR = 3

# non ui settings
REMOVE_FILENAME_CHARS = None
IMPORT_DEFAULT_CHECKED_SHOWS = None
# /non ui settings

providerList = []
newznabProviderList = []
torrentRssProviderList = []
metadata_provider_dict = {}

MODULE_UPDATE_STRING = None
NEWEST_VERSION_STRING = None
VERSION_NOTIFY = False
AUTO_UPDATE = False
NOTIFY_ON_UPDATE = False
CUR_COMMIT_HASH = None
EXT_UPDATES = False
BRANCH = ''
GIT_REMOTE = ''
CUR_COMMIT_BRANCH = ''

INIT_LOCK = Lock()
started = False

ACTUAL_LOG_DIR = None
LOG_DIR = None
FILE_LOGGING_PRESET = 'DB'

SOCKET_TIMEOUT = None

WEB_PORT = None
WEB_LOG = None
WEB_ROOT = None
WEB_USERNAME = None
WEB_PASSWORD = None
WEB_HOST = None
WEB_IPV6 = None
WEB_IPV64 = None

HANDLE_REVERSE_PROXY = False
SEND_SECURITY_HEADERS = True
ALLOWED_HOSTS = None
PROXY_SETTING = None
PROXY_INDEXERS = True

CPU_PRESET = 'DISABLED'

ANON_REDIRECT = None

USE_API = False
API_KEY = None

ENABLE_HTTPS = False
HTTPS_CERT = None
HTTPS_KEY = None

LAUNCH_BROWSER = False
CACHE_DIR = None
ACTUAL_CACHE_DIR = None
ZONEINFO_DIR = None
ROOT_DIRS = None
TRASH_REMOVE_SHOW = False
TRASH_ROTATE_LOGS = False
HOME_SEARCH_FOCUS = True
DISPLAY_FREESPACE = True
SORT_ARTICLE = False
DEBUG = False
SHOW_TAGS = []
SHOW_TAG_DEFAULT = ''
SHOWLIST_TAGVIEW = ''

METADATA_XBMC = None
METADATA_XBMC_12PLUS = None
METADATA_MEDIABROWSER = None
METADATA_PS3 = None
METADATA_WDTV = None
METADATA_TIVO = None
METADATA_MEDE8ER = None
METADATA_KODI = None

RESULTS_SORTBY = None

QUALITY_DEFAULT = None
STATUS_DEFAULT = None
WANTED_BEGIN_DEFAULT = None
WANTED_LATEST_DEFAULT = None
FLATTEN_FOLDERS_DEFAULT = False
SUBTITLES_DEFAULT = False
INDEXER_DEFAULT = None
INDEXER_TIMEOUT = None
SCENE_DEFAULT = False
ANIME_DEFAULT = False
USE_IMDB_INFO = True
IMDB_ACCOUNTS = []
IMDB_DEFAULT_LIST_ID = '64552276'
IMDB_DEFAULT_LIST_NAME = 'SickGear'
PROVIDER_ORDER = []
PROVIDER_HOMES = {}

NAMING_MULTI_EP = False
NAMING_ANIME_MULTI_EP = False
NAMING_PATTERN = None
NAMING_ABD_PATTERN = None
NAMING_CUSTOM_ABD = False
NAMING_SPORTS_PATTERN = None
NAMING_CUSTOM_SPORTS = False
NAMING_ANIME_PATTERN = None
NAMING_CUSTOM_ANIME = False
NAMING_FORCE_FOLDERS = False
NAMING_STRIP_YEAR = False
NAMING_ANIME = None

USE_NZBS = False
USE_TORRENTS = False

NZB_METHOD = None
NZB_DIR = None
USENET_RETENTION = None
TORRENT_METHOD = None
TORRENT_DIR = None
DOWNLOAD_PROPERS = False
PROPERS_WEBDL_ONEGRP = True
WEBDL_TYPES = []
ALLOW_HIGH_PRIORITY = False
NEWZNAB_DATA = ''

AUTOPOSTPROCESSER_FREQUENCY = None
RECENTSEARCH_FREQUENCY = 0
UPDATE_FREQUENCY = None
RECENTSEARCH_STARTUP = False
BACKLOG_FREQUENCY = None
BACKLOG_NOFULL = False

DEFAULT_AUTOPOSTPROCESSER_FREQUENCY = 10
DEFAULT_RECENTSEARCH_FREQUENCY = 40
DEFAULT_BACKLOG_FREQUENCY = 21
DEFAULT_UPDATE_FREQUENCY = 1
DEFAULT_WATCHEDSTATE_FREQUENCY = 10

MIN_AUTOPOSTPROCESSER_FREQUENCY = 1
MIN_RECENTSEARCH_FREQUENCY = 10
MIN_BACKLOG_FREQUENCY = 7
MAX_BACKLOG_FREQUENCY = 42
MIN_UPDATE_FREQUENCY = 1
MIN_WATCHEDSTATE_FREQUENCY = 10
MAX_WATCHEDSTATE_FREQUENCY = 60

BACKLOG_DAYS = 7
SEARCH_UNAIRED = False
UNAIRED_RECENT_SEARCH_ONLY = True

ADD_SHOWS_WO_DIR = False
CREATE_MISSING_SHOW_DIRS = False
RENAME_EPISODES = False
AIRDATE_EPISODES = False
PROCESS_AUTOMATICALLY = False
KEEP_PROCESSED_DIR = False
PROCESS_METHOD = None
MOVE_ASSOCIATED_FILES = False
POSTPONE_IF_SYNC_FILES = True
NFO_RENAME = True
TV_DOWNLOAD_DIR = None
UNPACK = False
SKIP_REMOVED_FILES = False

NZBGET_USERNAME = None
NZBGET_PASSWORD = None
NZBGET_CATEGORY = None
NZBGET_HOST = None
NZBGET_USE_HTTPS = False
NZBGET_PRIORITY = 100
NZBGET_SCRIPT_VERSION = None
NZBGET_MAP = None

SAB_USERNAME = None
SAB_PASSWORD = None
SAB_APIKEY = None
SAB_CATEGORY = None
SAB_HOST = ''

TORRENT_USERNAME = None
TORRENT_PASSWORD = None
TORRENT_HOST = ''
TORRENT_PATH = ''
TORRENT_SEED_TIME = 0
TORRENT_PAUSED = False
TORRENT_HIGH_BANDWIDTH = False
TORRENT_LABEL = ''
TORRENT_VERIFY_CERT = False

USE_EMBY = False
EMBY_UPDATE_LIBRARY = False
EMBY_PARENT_MAPS = None
EMBY_HOST = None
EMBY_APIKEY = None
EMBY_WATCHEDSTATE_SCHEDULED = False
EMBY_WATCHEDSTATE_FREQUENCY = 0

USE_KODI = False
KODI_ALWAYS_ON = True
KODI_NOTIFY_ONSNATCH = False
KODI_NOTIFY_ONDOWNLOAD = False
KODI_NOTIFY_ONSUBTITLEDOWNLOAD = False
KODI_UPDATE_LIBRARY = False
KODI_UPDATE_FULL = False
KODI_UPDATE_ONLYFIRST = False
KODI_PARENT_MAPS = None
KODI_HOST = ''
KODI_USERNAME = None
KODI_PASSWORD = None

USE_PLEX = False
PLEX_NOTIFY_ONSNATCH = False
PLEX_NOTIFY_ONDOWNLOAD = False
PLEX_NOTIFY_ONSUBTITLEDOWNLOAD = False
PLEX_UPDATE_LIBRARY = False
PLEX_PARENT_MAPS = None
PLEX_SERVER_HOST = None
PLEX_HOST = None
PLEX_USERNAME = None
PLEX_PASSWORD = None
PLEX_WATCHEDSTATE_SCHEDULED = False
PLEX_WATCHEDSTATE_FREQUENCY = 0

USE_XBMC = False
XBMC_ALWAYS_ON = True
XBMC_NOTIFY_ONSNATCH = False
XBMC_NOTIFY_ONDOWNLOAD = False
XBMC_NOTIFY_ONSUBTITLEDOWNLOAD = False
XBMC_UPDATE_LIBRARY = False
XBMC_UPDATE_FULL = False
XBMC_UPDATE_ONLYFIRST = False
XBMC_HOST = ''
XBMC_USERNAME = None
XBMC_PASSWORD = None

QUEUE_UPDATE_LIBRARY = []

USE_NMJ = False
NMJ_HOST = None
NMJ_DATABASE = None
NMJ_MOUNT = None

USE_NMJv2 = False
NMJv2_HOST = None
NMJv2_DATABASE = None
NMJv2_DBLOC = None

USE_SYNOINDEX = False
SYNOINDEX_UPDATE_LIBRARY = True

USE_SYNOLOGYNOTIFIER = False
SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH = False
SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD = False
SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD = False

USE_PYTIVO = False
PYTIVO_HOST = ''
PYTIVO_SHARE_NAME = ''
PYTIVO_TIVO_NAME = ''

USE_BOXCAR2 = False
BOXCAR2_NOTIFY_ONSNATCH = False
BOXCAR2_NOTIFY_ONDOWNLOAD = False
BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD = False
BOXCAR2_ACCESSTOKEN = None
BOXCAR2_SOUND = None

USE_PUSHBULLET = False
PUSHBULLET_NOTIFY_ONSNATCH = False
PUSHBULLET_NOTIFY_ONDOWNLOAD = False
PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD = False
PUSHBULLET_ACCESS_TOKEN = None
PUSHBULLET_DEVICE_IDEN = None

USE_PUSHOVER = False
PUSHOVER_NOTIFY_ONSNATCH = False
PUSHOVER_NOTIFY_ONDOWNLOAD = False
PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD = False
PUSHOVER_USERKEY = None
PUSHOVER_APIKEY = None
PUSHOVER_PRIORITY = '0'
PUSHOVER_DEVICE = None
PUSHOVER_SOUND = None

USE_GROWL = False
GROWL_NOTIFY_ONSNATCH = False
GROWL_NOTIFY_ONDOWNLOAD = False
GROWL_NOTIFY_ONSUBTITLEDOWNLOAD = False
GROWL_HOST = ''
GROWL_PASSWORD = None

USE_PROWL = False
PROWL_NOTIFY_ONSNATCH = False
PROWL_NOTIFY_ONDOWNLOAD = False
PROWL_NOTIFY_ONSUBTITLEDOWNLOAD = False
PROWL_API = None
PROWL_PRIORITY = '0'

USE_LIBNOTIFY = False
LIBNOTIFY_NOTIFY_ONSNATCH = False
LIBNOTIFY_NOTIFY_ONDOWNLOAD = False
LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD = False

USE_PUSHALOT = False
PUSHALOT_NOTIFY_ONSNATCH = False
PUSHALOT_NOTIFY_ONDOWNLOAD = False
PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD = False
PUSHALOT_AUTHORIZATIONTOKEN = None

USE_TRAKT = False
TRAKT_REMOVE_WATCHLIST = False
TRAKT_REMOVE_SERIESLIST = False
TRAKT_USE_WATCHLIST = False
TRAKT_METHOD_ADD = 0
TRAKT_START_PAUSED = False
TRAKT_SYNC = False
TRAKT_DEFAULT_INDEXER = None
TRAKT_UPDATE_COLLECTION = {}

USE_SLACK = False
SLACK_NOTIFY_ONSNATCH = False
SLACK_NOTIFY_ONDOWNLOAD = False
SLACK_NOTIFY_ONSUBTITLEDOWNLOAD = False
SLACK_CHANNEL = None
SLACK_AS_AUTHED = False
SLACK_BOT_NAME = None
SLACK_ICON_URL = None
SLACK_ACCESS_TOKEN = None

USE_DISCORDAPP = False
DISCORDAPP_NOTIFY_ONSNATCH = False
DISCORDAPP_NOTIFY_ONDOWNLOAD = False
DISCORDAPP_NOTIFY_ONSUBTITLEDOWNLOAD = False
DISCORDAPP_AS_AUTHED = False
DISCORDAPP_USERNAME = None
DISCORDAPP_ICON_URL = None
DISCORDAPP_AS_TTS = 0
DISCORDAPP_ACCESS_TOKEN = None

USE_GITTER = False
GITTER_NOTIFY_ONSNATCH = False
GITTER_NOTIFY_ONDOWNLOAD = False
GITTER_NOTIFY_ONSUBTITLEDOWNLOAD = False
GITTER_ROOM = None
GITTER_ACCESS_TOKEN = None

USE_TWITTER = False
TWITTER_NOTIFY_ONSNATCH = False
TWITTER_NOTIFY_ONDOWNLOAD = False
TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD = False
TWITTER_USERNAME = None
TWITTER_PASSWORD = None
TWITTER_PREFIX = None

USE_EMAIL = False
EMAIL_OLD_SUBJECTS = False
EMAIL_NOTIFY_ONSNATCH = False
EMAIL_NOTIFY_ONDOWNLOAD = False
EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD = False
EMAIL_HOST = None
EMAIL_PORT = 25
EMAIL_TLS = False
EMAIL_USER = None
EMAIL_PASSWORD = None
EMAIL_FROM = None
EMAIL_LIST = None

USE_ANIDB = False
ANIDB_USERNAME = None
ANIDB_PASSWORD = None
ANIDB_USE_MYLIST = False
ADBA_CONNECTION = None
ANIME_TREAT_AS_HDTV = False

GUI_NAME = None
DEFAULT_HOME = None
FANART_LIMIT = None
FANART_PANEL = None
FANART_RATINGS = {}
HOME_LAYOUT = None
FOOTER_TIME_LAYOUT = 0
POSTER_SORTBY = None
POSTER_SORTDIR = None
DISPLAY_SHOW_VIEWMODE = 0
DISPLAY_SHOW_BACKGROUND = False
DISPLAY_SHOW_BACKGROUND_TRANSLUCENT = False
DISPLAY_SHOW_VIEWART = 0
DISPLAY_SHOW_MINIMUM = True
DISPLAY_SHOW_SPECIALS = False
EPISODE_VIEW_VIEWMODE = 0
EPISODE_VIEW_BACKGROUND = False
EPISODE_VIEW_BACKGROUND_TRANSLUCENT = False
EPISODE_VIEW_LAYOUT = None
EPISODE_VIEW_SORT = None
EPISODE_VIEW_DISPLAY_PAUSED = False
EPISODE_VIEW_POSTERS = True
EPISODE_VIEW_MISSED_RANGE = None
HISTORY_LAYOUT = None
BROWSELIST_HIDDEN = []

FUZZY_DATING = False
TRIM_ZERO = False
DATE_PRESET = None
TIME_PRESET = None
TIME_PRESET_W_SECONDS = None
TIMEZONE_DISPLAY = None
THEME_NAME = None

USE_SUBTITLES = False
SUBTITLES_LANGUAGES = []
SUBTITLES_DIR = ''
SUBTITLES_SERVICES_LIST = []
SUBTITLES_SERVICES_ENABLED = []
SUBTITLES_HISTORY = False
SUBTITLES_FINDER_FREQUENCY = 1

USE_FAILED_DOWNLOADS = False
DELETE_FAILED = False

EXTRA_SCRIPTS = []

GIT_PATH = None

IGNORE_WORDS = 'core2hd, hevc, MrLss, reenc, x265, danish, deutsch, dutch, flemish, french, ' + \
               'german, italian, nordic, norwegian, portuguese, spanish, swedish, turkish'
REQUIRE_WORDS = ''

WANTEDLIST_CACHE = None

CALENDAR_UNPROTECTED = False

TMDB_API_KEY = 'edc5f123313769de83a71e157758030b'
FANART_API_KEY = '3728ca1a2a937ba0c93b6e63cc86cecb'

# to switch between staging and production TRAKT environment
TRAKT_STAGING = False

TRAKT_TIMEOUT = 60
TRAKT_VERIFY = True
TRAKT_CONNECTED_ACCOUNT = None
TRAKT_ACCOUNTS = {}
TRAKT_MRU = ''

if TRAKT_STAGING:
    # staging trakt values:
    TRAKT_CLIENT_ID = '2aae3052f90b14235d184cc8f709b12b4fd8ae35f339a060a890c70db92be87a'
    TRAKT_CLIENT_SECRET = '900e03471220503843d4a856bfbef17080cddb630f2b7df6a825e96e3ff3c39e'
    TRAKT_PIN_URL = 'https://staging.trakt.tv/pin/638'
    TRAKT_BASE_URL = 'http://api.staging.trakt.tv/'
else:
    # production trakt values:
    TRAKT_CLIENT_ID = 'f1c453c67d81f1307f9118172c408a883eb186b094d5ea33080d59ddedb7fc7c'
    TRAKT_CLIENT_SECRET = '12efb6fb6e863a08934d9904032a90008325df7e23514650cade55e7e7c118c5'
    TRAKT_PIN_URL = 'https://trakt.tv/pin/6314'
    TRAKT_BASE_URL = 'https://api.trakt.tv/'

THETVDB_V2_API_TOKEN = {'token': None, 'datetime': datetime.datetime.fromordinal(1)}

COOKIE_SECRET = base64.b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes)

CACHE_IMAGE_URL_LIST = classes.ImageUrlList()

__INITIALIZED__ = False


def get_backlog_cycle_time():
    cycletime = RECENTSEARCH_FREQUENCY * 2 + 7
    return max([cycletime, 720])


def initialize(console_logging=True):
    with INIT_LOCK:

        # Misc
        global __INITIALIZED__, showList, providerList, newznabProviderList, torrentRssProviderList, \
            WEB_HOST, WEB_ROOT, ACTUAL_CACHE_DIR, CACHE_DIR, ZONEINFO_DIR, ADD_SHOWS_WO_DIR, CREATE_MISSING_SHOW_DIRS, \
            RECENTSEARCH_STARTUP, NAMING_FORCE_FOLDERS, SOCKET_TIMEOUT, DEBUG, INDEXER_DEFAULT, CONFIG_FILE, \
            REMOVE_FILENAME_CHARS, IMPORT_DEFAULT_CHECKED_SHOWS, WANTEDLIST_CACHE, MODULE_UPDATE_STRING, EXT_UPDATES
        # Schedulers
        # global traktCheckerScheduler
        global recentSearchScheduler, backlogSearchScheduler, showUpdateScheduler, \
            versionCheckScheduler, showQueueScheduler, searchQueueScheduler, \
            properFinderScheduler, autoPostProcesserScheduler, subtitlesFinderScheduler, \
            background_mapping_task, provider_ping_thread_pool, \
            embyWatchedStateScheduler, plexWatchedStateScheduler, watchedStateQueueScheduler, \
            MIN_WATCHEDSTATE_FREQUENCY, MAX_WATCHEDSTATE_FREQUENCY, DEFAULT_WATCHEDSTATE_FREQUENCY
        # Add Show Search
        global RESULTS_SORTBY
        # Add Show Defaults
        global STATUS_DEFAULT, QUALITY_DEFAULT, SHOW_TAG_DEFAULT, FLATTEN_FOLDERS_DEFAULT, SUBTITLES_DEFAULT, \
            WANTED_BEGIN_DEFAULT, WANTED_LATEST_DEFAULT, SCENE_DEFAULT, ANIME_DEFAULT
        # Post processing
        global KEEP_PROCESSED_DIR
        # Views
        global GUI_NAME, HOME_LAYOUT, FOOTER_TIME_LAYOUT, POSTER_SORTBY, POSTER_SORTDIR, DISPLAY_SHOW_SPECIALS, \
            EPISODE_VIEW_LAYOUT, EPISODE_VIEW_SORT, EPISODE_VIEW_DISPLAY_PAUSED, \
            EPISODE_VIEW_MISSED_RANGE, EPISODE_VIEW_POSTERS, FANART_PANEL, FANART_RATINGS, \
            EPISODE_VIEW_VIEWMODE, EPISODE_VIEW_BACKGROUND, EPISODE_VIEW_BACKGROUND_TRANSLUCENT, \
            DISPLAY_SHOW_VIEWMODE, DISPLAY_SHOW_BACKGROUND, DISPLAY_SHOW_BACKGROUND_TRANSLUCENT, \
            DISPLAY_SHOW_VIEWART, DISPLAY_SHOW_MINIMUM, DISPLAY_SHOW_SPECIALS, HISTORY_LAYOUT, BROWSELIST_HIDDEN
        # Gen Config/Misc
        global LAUNCH_BROWSER, UPDATE_SHOWS_ON_START, SHOW_UPDATE_HOUR, \
            TRASH_REMOVE_SHOW, TRASH_ROTATE_LOGS, ACTUAL_LOG_DIR, LOG_DIR, INDEXER_TIMEOUT, ROOT_DIRS, \
            VERSION_NOTIFY, AUTO_UPDATE, UPDATE_FREQUENCY, NOTIFY_ON_UPDATE
        # Gen Config/Interface
        global THEME_NAME, DEFAULT_HOME, FANART_LIMIT, SHOWLIST_TAGVIEW, SHOW_TAGS, \
            HOME_SEARCH_FOCUS, USE_IMDB_INFO, IMDB_ACCOUNTS, DISPLAY_FREESPACE, SORT_ARTICLE, FUZZY_DATING, TRIM_ZERO, \
            DATE_PRESET, TIME_PRESET, TIME_PRESET_W_SECONDS, TIMEZONE_DISPLAY, \
            WEB_USERNAME, WEB_PASSWORD, CALENDAR_UNPROTECTED, USE_API, API_KEY, WEB_PORT, WEB_LOG, \
            ENABLE_HTTPS, HTTPS_CERT, HTTPS_KEY, WEB_IPV6, WEB_IPV64, HANDLE_REVERSE_PROXY, \
            SEND_SECURITY_HEADERS, ALLOWED_HOSTS
        # Gen Config/Advanced
        global BRANCH, CUR_COMMIT_BRANCH, GIT_REMOTE, CUR_COMMIT_HASH, GIT_PATH, CPU_PRESET, ANON_REDIRECT, \
            ENCRYPTION_VERSION, PROXY_SETTING, PROXY_INDEXERS, FILE_LOGGING_PRESET
        # Search Settings/Episode
        global DOWNLOAD_PROPERS, PROPERS_WEBDL_ONEGRP, WEBDL_TYPES, RECENTSEARCH_FREQUENCY, \
            BACKLOG_DAYS, BACKLOG_NOFULL, BACKLOG_FREQUENCY, USENET_RETENTION, IGNORE_WORDS, REQUIRE_WORDS, \
            ALLOW_HIGH_PRIORITY, SEARCH_UNAIRED, UNAIRED_RECENT_SEARCH_ONLY
        # Search Settings/NZB search
        global USE_NZBS, NZB_METHOD, NZB_DIR, SAB_HOST, SAB_USERNAME, SAB_PASSWORD, SAB_APIKEY, SAB_CATEGORY, \
            NZBGET_USE_HTTPS, NZBGET_HOST, NZBGET_USERNAME, NZBGET_PASSWORD, NZBGET_CATEGORY, NZBGET_PRIORITY, \
            NZBGET_SCRIPT_VERSION, NZBGET_MAP
        # Search Settings/Torrent search
        global USE_TORRENTS, TORRENT_METHOD, TORRENT_DIR, TORRENT_HOST, TORRENT_USERNAME, TORRENT_PASSWORD, \
            TORRENT_LABEL, TORRENT_PATH, TORRENT_SEED_TIME, TORRENT_PAUSED, TORRENT_HIGH_BANDWIDTH, TORRENT_VERIFY_CERT
        # Media Providers
        global PROVIDER_ORDER, NEWZNAB_DATA, PROVIDER_HOMES
        # Subtitles
        global USE_SUBTITLES, SUBTITLES_LANGUAGES, SUBTITLES_DIR, SUBTITLES_FINDER_FREQUENCY,  \
            SUBTITLES_HISTORY, SUBTITLES_SERVICES_ENABLED, SUBTITLES_SERVICES_LIST
        # Post Processing/Post-Processing
        global TV_DOWNLOAD_DIR, PROCESS_METHOD, PROCESS_AUTOMATICALLY, AUTOPOSTPROCESSER_FREQUENCY, \
            POSTPONE_IF_SYNC_FILES, EXTRA_SCRIPTS, \
            DEFAULT_AUTOPOSTPROCESSER_FREQUENCY, MIN_AUTOPOSTPROCESSER_FREQUENCY, \
            UNPACK, SKIP_REMOVED_FILES, MOVE_ASSOCIATED_FILES, NFO_RENAME, RENAME_EPISODES, AIRDATE_EPISODES, \
            USE_FAILED_DOWNLOADS, DELETE_FAILED
        # Post Processing/Episode Naming
        global NAMING_PATTERN, NAMING_MULTI_EP, NAMING_STRIP_YEAR, NAMING_CUSTOM_ABD, NAMING_ABD_PATTERN, \
            NAMING_CUSTOM_SPORTS, NAMING_SPORTS_PATTERN, \
            NAMING_CUSTOM_ANIME, NAMING_ANIME_PATTERN, NAMING_ANIME_MULTI_EP, NAMING_ANIME
        # Post Processing/Metadata
        global metadata_provider_dict, METADATA_KODI, METADATA_MEDE8ER, METADATA_XBMC, METADATA_MEDIABROWSER, \
            METADATA_PS3, METADATA_TIVO, METADATA_WDTV, METADATA_XBMC_12PLUS
        # Notification Settings/HT and NAS
        global USE_EMBY, EMBY_UPDATE_LIBRARY, EMBY_PARENT_MAPS, EMBY_HOST, EMBY_APIKEY, \
            EMBY_WATCHEDSTATE_SCHEDULED, EMBY_WATCHEDSTATE_FREQUENCY, \
            USE_KODI, KODI_ALWAYS_ON, KODI_UPDATE_LIBRARY, KODI_UPDATE_FULL, KODI_UPDATE_ONLYFIRST, \
            KODI_PARENT_MAPS, KODI_HOST, KODI_USERNAME, KODI_PASSWORD, KODI_NOTIFY_ONSNATCH, \
            KODI_NOTIFY_ONDOWNLOAD, KODI_NOTIFY_ONSUBTITLEDOWNLOAD, \
            USE_XBMC, XBMC_ALWAYS_ON, XBMC_NOTIFY_ONSNATCH, XBMC_NOTIFY_ONDOWNLOAD, XBMC_NOTIFY_ONSUBTITLEDOWNLOAD, \
            XBMC_UPDATE_LIBRARY, XBMC_UPDATE_FULL, XBMC_UPDATE_ONLYFIRST, XBMC_HOST, XBMC_USERNAME, XBMC_PASSWORD, \
            USE_PLEX, PLEX_USERNAME, PLEX_PASSWORD, PLEX_UPDATE_LIBRARY, PLEX_PARENT_MAPS, PLEX_SERVER_HOST, \
            PLEX_NOTIFY_ONSNATCH, PLEX_NOTIFY_ONDOWNLOAD, PLEX_NOTIFY_ONSUBTITLEDOWNLOAD, PLEX_HOST, \
            PLEX_WATCHEDSTATE_SCHEDULED, PLEX_WATCHEDSTATE_FREQUENCY, \
            USE_NMJ, NMJ_HOST, NMJ_DATABASE, NMJ_MOUNT, \
            USE_NMJv2, NMJv2_HOST, NMJv2_DATABASE, NMJv2_DBLOC, \
            USE_SYNOINDEX, \
            USE_SYNOLOGYNOTIFIER, SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH, \
            SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD, SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD, \
            USE_PYTIVO, PYTIVO_HOST, PYTIVO_SHARE_NAME, PYTIVO_TIVO_NAME
        # Notification Settings/Devices
        global USE_GROWL, GROWL_NOTIFY_ONSNATCH, GROWL_NOTIFY_ONDOWNLOAD, GROWL_NOTIFY_ONSUBTITLEDOWNLOAD, \
            GROWL_HOST, GROWL_PASSWORD, \
            USE_PROWL, PROWL_NOTIFY_ONSNATCH, PROWL_NOTIFY_ONDOWNLOAD, PROWL_NOTIFY_ONSUBTITLEDOWNLOAD, \
            PROWL_API, PROWL_PRIORITY, \
            USE_LIBNOTIFY, LIBNOTIFY_NOTIFY_ONSNATCH, LIBNOTIFY_NOTIFY_ONDOWNLOAD, \
            LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD, \
            USE_PUSHOVER, PUSHOVER_NOTIFY_ONSNATCH, PUSHOVER_NOTIFY_ONDOWNLOAD, PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD, \
            PUSHOVER_USERKEY, PUSHOVER_APIKEY, PUSHOVER_PRIORITY, PUSHOVER_DEVICE, PUSHOVER_SOUND, \
            USE_BOXCAR2, BOXCAR2_NOTIFY_ONSNATCH, BOXCAR2_NOTIFY_ONDOWNLOAD, BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD, \
            BOXCAR2_ACCESSTOKEN, BOXCAR2_SOUND, \
            USE_PUSHALOT, PUSHALOT_NOTIFY_ONSNATCH, PUSHALOT_NOTIFY_ONDOWNLOAD, \
            PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD, PUSHALOT_AUTHORIZATIONTOKEN, \
            USE_PUSHBULLET, PUSHBULLET_NOTIFY_ONSNATCH, PUSHBULLET_NOTIFY_ONDOWNLOAD, \
            PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD, PUSHBULLET_ACCESS_TOKEN, PUSHBULLET_DEVICE_IDEN
        # Notification Settings/Social
        global USE_TWITTER, TWITTER_NOTIFY_ONSNATCH, TWITTER_NOTIFY_ONDOWNLOAD, TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD, \
            TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_PREFIX, \
            USE_TRAKT, TRAKT_CONNECTED_ACCOUNT, TRAKT_ACCOUNTS, TRAKT_MRU, TRAKT_VERIFY, \
            TRAKT_USE_WATCHLIST, TRAKT_REMOVE_WATCHLIST, TRAKT_TIMEOUT, TRAKT_METHOD_ADD, TRAKT_START_PAUSED, \
            TRAKT_SYNC, TRAKT_DEFAULT_INDEXER, TRAKT_REMOVE_SERIESLIST, TRAKT_UPDATE_COLLECTION, \
            USE_SLACK, SLACK_NOTIFY_ONSNATCH, SLACK_NOTIFY_ONDOWNLOAD, SLACK_NOTIFY_ONSUBTITLEDOWNLOAD, \
            SLACK_CHANNEL, SLACK_AS_AUTHED, SLACK_BOT_NAME, SLACK_ICON_URL, SLACK_ACCESS_TOKEN, \
            USE_DISCORDAPP, DISCORDAPP_NOTIFY_ONSNATCH, DISCORDAPP_NOTIFY_ONDOWNLOAD, \
            DISCORDAPP_NOTIFY_ONSUBTITLEDOWNLOAD, \
            DISCORDAPP_AS_AUTHED, DISCORDAPP_USERNAME, DISCORDAPP_ICON_URL, DISCORDAPP_AS_TTS, DISCORDAPP_ACCESS_TOKEN,\
            USE_GITTER, GITTER_NOTIFY_ONSNATCH, GITTER_NOTIFY_ONDOWNLOAD, GITTER_NOTIFY_ONSUBTITLEDOWNLOAD,\
            GITTER_ROOM, GITTER_ACCESS_TOKEN, \
            USE_EMAIL, EMAIL_NOTIFY_ONSNATCH, EMAIL_NOTIFY_ONDOWNLOAD, EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD, EMAIL_FROM, \
            EMAIL_HOST, EMAIL_PORT, EMAIL_TLS, EMAIL_USER, EMAIL_PASSWORD, EMAIL_LIST, EMAIL_OLD_SUBJECTS
        # Anime Settings
        global ANIME_TREAT_AS_HDTV, USE_ANIDB, ANIDB_USERNAME, ANIDB_PASSWORD, ANIDB_USE_MYLIST

        if __INITIALIZED__:
            return False

        for stanza in ('General', 'Blackhole', 'SABnzbd', 'NZBGet', 'Emby', 'Kodi', 'XBMC', 'PLEX',
                       'Growl', 'Prowl', 'Twitter', 'Slack', 'Discordapp', 'Boxcar2', 'NMJ', 'NMJv2',
                       'Synology', 'SynologyNotifier',
                       'pyTivo', 'Pushalot', 'Pushbullet', 'Subtitles'):
            check_section(CFG, stanza)

        update_config = False

        WANTEDLIST_CACHE = common.wantedQualities()

        # wanted branch
        BRANCH = check_setting_str(CFG, 'General', 'branch', '')

        # git_remote
        GIT_REMOTE = check_setting_str(CFG, 'General', 'git_remote', 'origin')

        # current commit hash
        CUR_COMMIT_HASH = check_setting_str(CFG, 'General', 'cur_commit_hash', '')
        EXT_UPDATES = (35 > len(CUR_COMMIT_HASH) or not bool(re.match('^[a-z0-9]+$', CUR_COMMIT_HASH))) and \
            ('docker/other', 'snap')['snap' in CUR_COMMIT_HASH]

        # current commit branch
        CUR_COMMIT_BRANCH = check_setting_str(CFG, 'General', 'cur_commit_branch', '')

        ACTUAL_CACHE_DIR = check_setting_str(CFG, 'General', 'cache_dir', 'cache')

        # unless they specify, put the cache dir inside the data dir
        if not os.path.isabs(ACTUAL_CACHE_DIR):
            CACHE_DIR = os.path.join(DATA_DIR, ACTUAL_CACHE_DIR)
        else:
            CACHE_DIR = ACTUAL_CACHE_DIR

        if not helpers.makeDir(CACHE_DIR):
            logger.log(u'!!! Creating local cache dir failed, using system default', logger.ERROR)
            CACHE_DIR = None

        # clean cache folders
        if CACHE_DIR:
            helpers.clearCache()
            ZONEINFO_DIR = ek.ek(os.path.join, CACHE_DIR, 'zoneinfo')
            if not ek.ek(os.path.isdir, ZONEINFO_DIR) and not helpers.make_dirs(ZONEINFO_DIR):
                logger.log(u'!!! Creating local zoneinfo dir failed', logger.ERROR)

        THEME_NAME = check_setting_str(CFG, 'GUI', 'theme_name', 'dark')
        GUI_NAME = check_setting_str(CFG, 'GUI', 'gui_name', 'slick')
        DEFAULT_HOME = check_setting_str(CFG, 'GUI', 'default_home', 'episodes')
        FANART_LIMIT = check_setting_int(CFG, 'GUI', 'fanart_limit', 3)
        FANART_PANEL = check_setting_str(CFG, 'GUI', 'fanart_panel', 'highlight2')
        FANART_RATINGS = check_setting_str(CFG, 'GUI', 'fanart_ratings', None)
        if None is not FANART_RATINGS:
            FANART_RATINGS = ast.literal_eval(FANART_RATINGS or '{}')
        else:
            FANART_RATINGS = ast.literal_eval(check_setting_str(CFG, 'GUI', 'backart_ratings', None) or '{}')
            update_config |= image_cache.ImageCache().clean_fanart()
        USE_IMDB_INFO = bool(check_setting_int(CFG, 'GUI', 'use_imdb_info', 1))
        IMDB_ACCOUNTS = CFG.get('GUI', []).get('imdb_accounts', [IMDB_DEFAULT_LIST_ID, IMDB_DEFAULT_LIST_NAME])
        HOME_SEARCH_FOCUS = bool(check_setting_int(CFG, 'General', 'home_search_focus', HOME_SEARCH_FOCUS))
        DISPLAY_FREESPACE = bool(check_setting_int(CFG, 'General', 'display_freespace', 1))
        SORT_ARTICLE = bool(check_setting_int(CFG, 'General', 'sort_article', 0))
        FUZZY_DATING = bool(check_setting_int(CFG, 'GUI', 'fuzzy_dating', 0))
        TRIM_ZERO = bool(check_setting_int(CFG, 'GUI', 'trim_zero', 0))
        DATE_PRESET = check_setting_str(CFG, 'GUI', 'date_preset', '%x')
        TIME_PRESET_W_SECONDS = check_setting_str(CFG, 'GUI', 'time_preset', '%I:%M:%S %p')
        TIME_PRESET = TIME_PRESET_W_SECONDS.replace(u':%S', u'')
        TIMEZONE_DISPLAY = check_setting_str(CFG, 'GUI', 'timezone_display', 'network')
        SHOW_TAGS = check_setting_str(CFG, 'GUI', 'show_tags', 'Show List').split(',')
        SHOW_TAG_DEFAULT = check_setting_str(CFG, 'GUI', 'show_tag_default',
                                             check_setting_str(CFG, 'GUI', 'default_show_tag', 'Show List'))
        SHOWLIST_TAGVIEW = check_setting_str(CFG, 'GUI', 'showlist_tagview', 'standard')

        ACTUAL_LOG_DIR = check_setting_str(CFG, 'General', 'log_dir', 'Logs')
        # put the log dir inside the data dir, unless an absolute path
        LOG_DIR = os.path.normpath(os.path.join(DATA_DIR, ACTUAL_LOG_DIR))

        if not helpers.makeDir(LOG_DIR):
            logger.log(u'!!! No log folder, logging to screen only!', logger.ERROR)

        FILE_LOGGING_PRESET = check_setting_str(CFG, 'General', 'file_logging_preset', 'DB')

        SOCKET_TIMEOUT = check_setting_int(CFG, 'General', 'socket_timeout', 30)
        socket.setdefaulttimeout(SOCKET_TIMEOUT)

        WEB_HOST = check_setting_str(CFG, 'General', 'web_host', '0.0.0.0')
        WEB_PORT = minimax(check_setting_int(CFG, 'General', 'web_port', 8081), 8081, 21, 65535)
        WEB_ROOT = check_setting_str(CFG, 'General', 'web_root', '').rstrip('/')
        WEB_IPV6 = bool(check_setting_int(CFG, 'General', 'web_ipv6', 0))
        WEB_IPV64 = bool(check_setting_int(CFG, 'General', 'web_ipv64', 0))
        WEB_LOG = bool(check_setting_int(CFG, 'General', 'web_log', 0))
        ENCRYPTION_VERSION = check_setting_int(CFG, 'General', 'encryption_version', 0)
        WEB_USERNAME = check_setting_str(CFG, 'General', 'web_username', '')
        WEB_PASSWORD = check_setting_str(CFG, 'General', 'web_password', '')
        LAUNCH_BROWSER = bool(check_setting_int(CFG, 'General', 'launch_browser', 1))

        CPU_PRESET = check_setting_str(CFG, 'General', 'cpu_preset', 'DISABLED')

        ANON_REDIRECT = check_setting_str(CFG, 'General', 'anon_redirect', '')
        PROXY_SETTING = check_setting_str(CFG, 'General', 'proxy_setting', '')
        PROXY_INDEXERS = bool(check_setting_int(CFG, 'General', 'proxy_indexers', 1))
        # attempt to help prevent users from breaking links by using a bad url
        if not ANON_REDIRECT.endswith('?'):
            ANON_REDIRECT = ''

        UPDATE_SHOWS_ON_START = bool(check_setting_int(CFG, 'General', 'update_shows_on_start', 0))
        SHOW_UPDATE_HOUR = check_setting_int(CFG, 'General', 'show_update_hour', 3)
        SHOW_UPDATE_HOUR = minimax(SHOW_UPDATE_HOUR, 3, 0, 23)

        TRASH_REMOVE_SHOW = bool(check_setting_int(CFG, 'General', 'trash_remove_show', 0))
        TRASH_ROTATE_LOGS = bool(check_setting_int(CFG, 'General', 'trash_rotate_logs', 0))

        USE_API = bool(check_setting_int(CFG, 'General', 'use_api', 0))
        API_KEY = check_setting_str(CFG, 'General', 'api_key', '')

        DEBUG = bool(check_setting_int(CFG, 'General', 'debug', 0))

        ENABLE_HTTPS = bool(check_setting_int(CFG, 'General', 'enable_https', 0))

        HTTPS_CERT = check_setting_str(CFG, 'General', 'https_cert', 'server.crt')
        HTTPS_KEY = check_setting_str(CFG, 'General', 'https_key', 'server.key')

        HANDLE_REVERSE_PROXY = bool(check_setting_int(CFG, 'General', 'handle_reverse_proxy', 0))
        SEND_SECURITY_HEADERS = bool(check_setting_int(CFG, 'General', 'send_security_headers', 1))
        ALLOWED_HOSTS = check_setting_str(CFG, 'General', 'allowed_hosts', '')

        ROOT_DIRS = check_setting_str(CFG, 'General', 'root_dirs', '')
        if not re.match(r'\d+\|[^|]+(?:\|[^|]+)*', ROOT_DIRS):
            ROOT_DIRS = ''

        RESULTS_SORTBY = check_setting_str(CFG, 'General', 'results_sortby', '')

        QUALITY_DEFAULT = check_setting_int(CFG, 'General', 'quality_default', SD)
        STATUS_DEFAULT = check_setting_int(CFG, 'General', 'status_default', SKIPPED)
        WANTED_BEGIN_DEFAULT = check_setting_int(CFG, 'General', 'wanted_begin_default', 0)
        WANTED_LATEST_DEFAULT = check_setting_int(CFG, 'General', 'wanted_latest_default', 0)
        VERSION_NOTIFY = bool(check_setting_int(CFG, 'General', 'version_notify', 1))
        AUTO_UPDATE = bool(check_setting_int(CFG, 'General', 'auto_update', 0))
        NOTIFY_ON_UPDATE = bool(check_setting_int(CFG, 'General', 'notify_on_update', 1))
        FLATTEN_FOLDERS_DEFAULT = bool(check_setting_int(CFG, 'General', 'flatten_folders_default', 0))
        INDEXER_DEFAULT = check_setting_int(CFG, 'General', 'indexer_default', 0)
        if INDEXER_DEFAULT and not indexerApi(INDEXER_DEFAULT).config['active']:
            INDEXER_DEFAULT = INDEXER_TVDB
        INDEXER_TIMEOUT = check_setting_int(CFG, 'General', 'indexer_timeout', 20)
        ANIME_DEFAULT = bool(check_setting_int(CFG, 'General', 'anime_default', 0))
        SCENE_DEFAULT = bool(check_setting_int(CFG, 'General', 'scene_default', 0))

        PROVIDER_ORDER = check_setting_str(CFG, 'General', 'provider_order', '').split()
        PROVIDER_HOMES = ast.literal_eval(check_setting_str(CFG, 'General', 'provider_homes', None) or '{}')

        NAMING_PATTERN = check_setting_str(CFG, 'General', 'naming_pattern', 'Season %0S/%SN - S%0SE%0E - %EN')
        NAMING_ABD_PATTERN = check_setting_str(CFG, 'General', 'naming_abd_pattern', '%SN - %A.D - %EN')
        NAMING_CUSTOM_ABD = bool(check_setting_int(CFG, 'General', 'naming_custom_abd', 0))
        NAMING_SPORTS_PATTERN = check_setting_str(CFG, 'General', 'naming_sports_pattern', '%SN - %A-D - %EN')
        NAMING_ANIME_PATTERN = check_setting_str(CFG, 'General', 'naming_anime_pattern',
                                                 'Season %0S/%SN - S%0SE%0E - %EN')
        NAMING_ANIME = check_setting_int(CFG, 'General', 'naming_anime', 3)
        NAMING_CUSTOM_SPORTS = bool(check_setting_int(CFG, 'General', 'naming_custom_sports', 0))
        NAMING_CUSTOM_ANIME = bool(check_setting_int(CFG, 'General', 'naming_custom_anime', 0))
        NAMING_MULTI_EP = check_setting_int(CFG, 'General', 'naming_multi_ep', 1)
        NAMING_ANIME_MULTI_EP = check_setting_int(CFG, 'General', 'naming_anime_multi_ep', 1)
        NAMING_FORCE_FOLDERS = naming.check_force_season_folders()
        NAMING_STRIP_YEAR = bool(check_setting_int(CFG, 'General', 'naming_strip_year', 0))

        USE_NZBS = bool(check_setting_int(CFG, 'General', 'use_nzbs', 0))
        USE_TORRENTS = bool(check_setting_int(CFG, 'General', 'use_torrents', 0))

        NZB_METHOD = check_setting_str(CFG, 'General', 'nzb_method', 'blackhole')
        if NZB_METHOD not in ('blackhole', 'sabnzbd', 'nzbget'):
            NZB_METHOD = 'blackhole'

        TORRENT_METHOD = check_setting_str(CFG, 'General', 'torrent_method', 'blackhole')
        if TORRENT_METHOD not in ('blackhole', 'deluge', 'download_station', 'qbittorrent',
                                  'rtorrent', 'transmission', 'utorrent'):
            TORRENT_METHOD = 'blackhole'

        DOWNLOAD_PROPERS = bool(check_setting_int(CFG, 'General', 'download_propers', 1))
        PROPERS_WEBDL_ONEGRP = bool(check_setting_int(CFG, 'General', 'propers_webdl_onegrp', 1))

        ALLOW_HIGH_PRIORITY = bool(check_setting_int(CFG, 'General', 'allow_high_priority', 1))

        RECENTSEARCH_STARTUP = bool(check_setting_int(CFG, 'General', 'recentsearch_startup', 0))
        BACKLOG_NOFULL = bool(check_setting_int(CFG, 'General', 'backlog_nofull', 0))
        SKIP_REMOVED_FILES = check_setting_int(CFG, 'General', 'skip_removed_files', 0)

        USENET_RETENTION = check_setting_int(CFG, 'General', 'usenet_retention', 500)

        AUTOPOSTPROCESSER_FREQUENCY = check_setting_int(CFG, 'General', 'autopostprocesser_frequency',
                                                        DEFAULT_AUTOPOSTPROCESSER_FREQUENCY)
        if AUTOPOSTPROCESSER_FREQUENCY < MIN_AUTOPOSTPROCESSER_FREQUENCY:
            AUTOPOSTPROCESSER_FREQUENCY = MIN_AUTOPOSTPROCESSER_FREQUENCY

        RECENTSEARCH_FREQUENCY = check_setting_int(CFG, 'General', 'recentsearch_frequency',
                                                   DEFAULT_RECENTSEARCH_FREQUENCY)
        if RECENTSEARCH_FREQUENCY < MIN_RECENTSEARCH_FREQUENCY:
            RECENTSEARCH_FREQUENCY = MIN_RECENTSEARCH_FREQUENCY

        BACKLOG_FREQUENCY = check_setting_int(CFG, 'General', 'backlog_frequency', DEFAULT_BACKLOG_FREQUENCY)
        BACKLOG_FREQUENCY = minimax(BACKLOG_FREQUENCY, DEFAULT_BACKLOG_FREQUENCY,
                                    MIN_BACKLOG_FREQUENCY, MAX_BACKLOG_FREQUENCY)

        UPDATE_FREQUENCY = check_setting_int(CFG, 'General', 'update_frequency', DEFAULT_UPDATE_FREQUENCY)
        if UPDATE_FREQUENCY < MIN_UPDATE_FREQUENCY:
            UPDATE_FREQUENCY = MIN_UPDATE_FREQUENCY

        BACKLOG_DAYS = check_setting_int(CFG, 'General', 'backlog_days', 7)
        SEARCH_UNAIRED = bool(check_setting_int(CFG, 'General', 'search_unaired', 0))
        UNAIRED_RECENT_SEARCH_ONLY = bool(check_setting_int(CFG, 'General', 'unaired_recent_search_only', 1))

        NZB_DIR = check_setting_str(CFG, 'Blackhole', 'nzb_dir', '')
        TORRENT_DIR = check_setting_str(CFG, 'Blackhole', 'torrent_dir', '')

        TV_DOWNLOAD_DIR = check_setting_str(CFG, 'General', 'tv_download_dir', '')
        PROCESS_AUTOMATICALLY = bool(check_setting_int(CFG, 'General', 'process_automatically', 0))
        UNPACK = bool(check_setting_int(CFG, 'General', 'unpack', 0))
        RENAME_EPISODES = bool(check_setting_int(CFG, 'General', 'rename_episodes', 1))
        AIRDATE_EPISODES = bool(check_setting_int(CFG, 'General', 'airdate_episodes', 0))
        KEEP_PROCESSED_DIR = bool(check_setting_int(CFG, 'General', 'keep_processed_dir', 1))
        PROCESS_METHOD = check_setting_str(CFG, 'General', 'process_method', 'copy' if KEEP_PROCESSED_DIR else 'move')
        MOVE_ASSOCIATED_FILES = bool(check_setting_int(CFG, 'General', 'move_associated_files', 0))
        POSTPONE_IF_SYNC_FILES = bool(check_setting_int(CFG, 'General', 'postpone_if_sync_files', 1))
        NFO_RENAME = bool(check_setting_int(CFG, 'General', 'nfo_rename', 1))
        CREATE_MISSING_SHOW_DIRS = bool(check_setting_int(CFG, 'General', 'create_missing_show_dirs', 0))
        ADD_SHOWS_WO_DIR = bool(check_setting_int(CFG, 'General', 'add_shows_wo_dir', 0))
        REMOVE_FILENAME_CHARS = check_setting_str(CFG, 'General', 'remove_filename_chars', '')
        IMPORT_DEFAULT_CHECKED_SHOWS = bool(check_setting_int(CFG, 'General', 'import_default_checked_shows', 0))

        SAB_USERNAME = check_setting_str(CFG, 'SABnzbd', 'sab_username', '')
        SAB_PASSWORD = check_setting_str(CFG, 'SABnzbd', 'sab_password', '')
        SAB_APIKEY = check_setting_str(CFG, 'SABnzbd', 'sab_apikey', '')
        SAB_CATEGORY = check_setting_str(CFG, 'SABnzbd', 'sab_category', 'tv')
        SAB_HOST = check_setting_str(CFG, 'SABnzbd', 'sab_host', '')

        # first check using official name case, then with case of legacy
        # todo: migrate config, (just not atm due to testing map feature)
        NZBGET_USERNAME = (check_setting_str(CFG, 'NZBGet', 'nzbget_username', '')
                           or check_setting_str(CFG, 'NZBget', 'nzbget_username', 'nzbget'))
        NZBGET_PASSWORD = (check_setting_str(CFG, 'NZBGet', 'nzbget_password', '')
                           or check_setting_str(CFG, 'NZBget', 'nzbget_password', 'tegbzn6789'))
        NZBGET_CATEGORY = (check_setting_str(CFG, 'NZBGet', 'nzbget_category', '')
                           or check_setting_str(CFG, 'NZBget', 'nzbget_category', 'tv'))
        NZBGET_HOST = (check_setting_str(CFG, 'NZBGet', 'nzbget_host', '')
                       or check_setting_str(CFG, 'NZBget', 'nzbget_host', ''))
        NZBGET_USE_HTTPS = (bool(check_setting_int(CFG, 'NZBGet', 'nzbget_use_https', 0))
                            or bool(check_setting_int(CFG, 'NZBget', 'nzbget_use_https', 0)))
        NZBGET_PRIORITY = check_setting_int(CFG, 'NZBGet', 'nzbget_priority', None)
        if None is NZBGET_PRIORITY:
            NZBGET_PRIORITY = check_setting_int(CFG, 'NZBget', 'nzbget_priority', 100)
        NZBGET_MAP = check_setting_str(CFG, 'NZBGet', 'nzbget_map', '')

        try:
            ng_script_file = ek.ek(os.path.join, ek.ek(os.path.dirname, ek.ek(os.path.dirname, __file__)),
                                   'autoProcessTV', 'SickGear-NG', 'SickGear-NG.py')
            with open(ng_script_file, 'r') as ng:
                text = ng.read()
            NZBGET_SCRIPT_VERSION = re.search(r'__version__ =.*\'([0-9.]+)\'.*$', text, flags=re.M).group(1)
        except (StandardError, Exception):
            NZBGET_SCRIPT_VERSION = None

        TORRENT_USERNAME = check_setting_str(CFG, 'TORRENT', 'torrent_username', '')
        TORRENT_PASSWORD = check_setting_str(CFG, 'TORRENT', 'torrent_password', '')
        TORRENT_HOST = check_setting_str(CFG, 'TORRENT', 'torrent_host', '')
        TORRENT_PATH = check_setting_str(CFG, 'TORRENT', 'torrent_path', '')
        TORRENT_SEED_TIME = check_setting_int(CFG, 'TORRENT', 'torrent_seed_time', 0)
        TORRENT_PAUSED = bool(check_setting_int(CFG, 'TORRENT', 'torrent_paused', 0))
        TORRENT_HIGH_BANDWIDTH = bool(check_setting_int(CFG, 'TORRENT', 'torrent_high_bandwidth', 0))
        TORRENT_LABEL = check_setting_str(CFG, 'TORRENT', 'torrent_label', '')
        TORRENT_VERIFY_CERT = bool(check_setting_int(CFG, 'TORRENT', 'torrent_verify_cert', 0))

        USE_EMBY = bool(check_setting_int(CFG, 'Emby', 'use_emby', 0))
        EMBY_UPDATE_LIBRARY = bool(check_setting_int(CFG, 'Emby', 'emby_update_library', 0))
        EMBY_PARENT_MAPS = check_setting_str(CFG, 'Emby', 'emby_parent_maps', '')
        EMBY_HOST = check_setting_str(CFG, 'Emby', 'emby_host', '')
        EMBY_APIKEY = check_setting_str(CFG, 'Emby', 'emby_apikey', '')
        EMBY_WATCHEDSTATE_SCHEDULED = bool(check_setting_int(CFG, 'Emby', 'emby_watchedstate_scheduled', 0))
        EMBY_WATCHEDSTATE_FREQUENCY = minimax(check_setting_int(
            CFG, 'Emby', 'emby_watchedstate_frequency', DEFAULT_WATCHEDSTATE_FREQUENCY),
            DEFAULT_WATCHEDSTATE_FREQUENCY, MIN_WATCHEDSTATE_FREQUENCY, MAX_WATCHEDSTATE_FREQUENCY)

        USE_KODI = bool(check_setting_int(CFG, 'Kodi', 'use_kodi', 0))
        KODI_ALWAYS_ON = bool(check_setting_int(CFG, 'Kodi', 'kodi_always_on', 1))
        KODI_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Kodi', 'kodi_notify_onsnatch', 0))
        KODI_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Kodi', 'kodi_notify_ondownload', 0))
        KODI_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Kodi', 'kodi_notify_onsubtitledownload', 0))
        KODI_UPDATE_LIBRARY = bool(check_setting_int(CFG, 'Kodi', 'kodi_update_library', 0))
        KODI_UPDATE_FULL = bool(check_setting_int(CFG, 'Kodi', 'kodi_update_full', 0))
        KODI_UPDATE_ONLYFIRST = bool(check_setting_int(CFG, 'Kodi', 'kodi_update_onlyfirst', 0))
        KODI_PARENT_MAPS = check_setting_str(CFG, 'Kodi', 'kodi_parent_maps', '')
        KODI_HOST = check_setting_str(CFG, 'Kodi', 'kodi_host', '')
        KODI_USERNAME = check_setting_str(CFG, 'Kodi', 'kodi_username', '')
        KODI_PASSWORD = check_setting_str(CFG, 'Kodi', 'kodi_password', '')

        USE_XBMC = bool(check_setting_int(CFG, 'XBMC', 'use_xbmc', 0))
        XBMC_ALWAYS_ON = bool(check_setting_int(CFG, 'XBMC', 'xbmc_always_on', 1))
        XBMC_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'XBMC', 'xbmc_notify_onsnatch', 0))
        XBMC_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'XBMC', 'xbmc_notify_ondownload', 0))
        XBMC_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'XBMC', 'xbmc_notify_onsubtitledownload', 0))
        XBMC_UPDATE_LIBRARY = bool(check_setting_int(CFG, 'XBMC', 'xbmc_update_library', 0))
        XBMC_UPDATE_FULL = bool(check_setting_int(CFG, 'XBMC', 'xbmc_update_full', 0))
        XBMC_UPDATE_ONLYFIRST = bool(check_setting_int(CFG, 'XBMC', 'xbmc_update_onlyfirst', 0))
        XBMC_HOST = check_setting_str(CFG, 'XBMC', 'xbmc_host', '')
        XBMC_USERNAME = check_setting_str(CFG, 'XBMC', 'xbmc_username', '')
        XBMC_PASSWORD = check_setting_str(CFG, 'XBMC', 'xbmc_password', '')

        USE_PLEX = bool(check_setting_int(CFG, 'Plex', 'use_plex', 0))
        PLEX_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Plex', 'plex_notify_onsnatch', 0))
        PLEX_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Plex', 'plex_notify_ondownload', 0))
        PLEX_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Plex', 'plex_notify_onsubtitledownload', 0))
        PLEX_UPDATE_LIBRARY = bool(check_setting_int(CFG, 'Plex', 'plex_update_library', 0))
        PLEX_PARENT_MAPS = check_setting_str(CFG, 'Plex', 'plex_parent_maps', '')
        PLEX_SERVER_HOST = check_setting_str(CFG, 'Plex', 'plex_server_host', '')
        PLEX_HOST = check_setting_str(CFG, 'Plex', 'plex_host', '')
        PLEX_USERNAME = check_setting_str(CFG, 'Plex', 'plex_username', '')
        PLEX_PASSWORD = check_setting_str(CFG, 'Plex', 'plex_password', '')
        PLEX_WATCHEDSTATE_SCHEDULED = bool(check_setting_int(CFG, 'Plex', 'plex_watchedstate_scheduled', 0))
        PLEX_WATCHEDSTATE_FREQUENCY = minimax(check_setting_int(
            CFG, 'Plex', 'plex_watchedstate_frequency', DEFAULT_WATCHEDSTATE_FREQUENCY),
            DEFAULT_WATCHEDSTATE_FREQUENCY, MIN_WATCHEDSTATE_FREQUENCY, MAX_WATCHEDSTATE_FREQUENCY)

        USE_GROWL = bool(check_setting_int(CFG, 'Growl', 'use_growl', 0))
        GROWL_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Growl', 'growl_notify_onsnatch', 0))
        GROWL_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Growl', 'growl_notify_ondownload', 0))
        GROWL_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Growl', 'growl_notify_onsubtitledownload', 0))
        GROWL_HOST = check_setting_str(CFG, 'Growl', 'growl_host', '')
        GROWL_PASSWORD = check_setting_str(CFG, 'Growl', 'growl_password', '')

        USE_PROWL = bool(check_setting_int(CFG, 'Prowl', 'use_prowl', 0))
        PROWL_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Prowl', 'prowl_notify_onsnatch', 0))
        PROWL_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Prowl', 'prowl_notify_ondownload', 0))
        PROWL_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Prowl', 'prowl_notify_onsubtitledownload', 0))
        PROWL_API = check_setting_str(CFG, 'Prowl', 'prowl_api', '')
        PROWL_PRIORITY = check_setting_str(CFG, 'Prowl', 'prowl_priority', '0')

        USE_TWITTER = bool(check_setting_int(CFG, 'Twitter', 'use_twitter', 0))
        TWITTER_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Twitter', 'twitter_notify_onsnatch', 0))
        TWITTER_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Twitter', 'twitter_notify_ondownload', 0))
        TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Twitter', 'twitter_notify_onsubtitledownload', 0))
        TWITTER_USERNAME = check_setting_str(CFG, 'Twitter', 'twitter_username', '')
        TWITTER_PASSWORD = check_setting_str(CFG, 'Twitter', 'twitter_password', '')
        TWITTER_PREFIX = check_setting_str(CFG, 'Twitter', 'twitter_prefix', 'SickGear')

        USE_BOXCAR2 = bool(check_setting_int(CFG, 'Boxcar2', 'use_boxcar2', 0))
        BOXCAR2_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Boxcar2', 'boxcar2_notify_onsnatch', 0))
        BOXCAR2_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Boxcar2', 'boxcar2_notify_ondownload', 0))
        BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Boxcar2', 'boxcar2_notify_onsubtitledownload', 0))
        BOXCAR2_ACCESSTOKEN = check_setting_str(CFG, 'Boxcar2', 'boxcar2_accesstoken', '')
        BOXCAR2_SOUND = check_setting_str(CFG, 'Boxcar2', 'boxcar2_sound', 'default')

        USE_PUSHOVER = bool(check_setting_int(CFG, 'Pushover', 'use_pushover', 0))
        PUSHOVER_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Pushover', 'pushover_notify_onsnatch', 0))
        PUSHOVER_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Pushover', 'pushover_notify_ondownload', 0))
        PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Pushover', 'pushover_notify_onsubtitledownload', 0))
        PUSHOVER_USERKEY = check_setting_str(CFG, 'Pushover', 'pushover_userkey', '')
        PUSHOVER_APIKEY = check_setting_str(CFG, 'Pushover', 'pushover_apikey', '')
        PUSHOVER_PRIORITY = check_setting_str(CFG, 'Pushover', 'pushover_priority', '0')
        PUSHOVER_DEVICE = check_setting_str(CFG, 'Pushover', 'pushover_device', 'all')
        PUSHOVER_SOUND = check_setting_str(CFG, 'Pushover', 'pushover_sound', 'pushover')

        USE_LIBNOTIFY = bool(check_setting_int(CFG, 'Libnotify', 'use_libnotify', 0))
        LIBNOTIFY_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Libnotify', 'libnotify_notify_onsnatch', 0))
        LIBNOTIFY_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Libnotify', 'libnotify_notify_ondownload', 0))
        LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Libnotify', 'libnotify_notify_onsubtitledownload', 0))

        USE_NMJ = bool(check_setting_int(CFG, 'NMJ', 'use_nmj', 0))
        NMJ_HOST = check_setting_str(CFG, 'NMJ', 'nmj_host', '')
        NMJ_DATABASE = check_setting_str(CFG, 'NMJ', 'nmj_database', '')
        NMJ_MOUNT = check_setting_str(CFG, 'NMJ', 'nmj_mount', '')

        USE_NMJv2 = bool(check_setting_int(CFG, 'NMJv2', 'use_nmjv2', 0))
        NMJv2_HOST = check_setting_str(CFG, 'NMJv2', 'nmjv2_host', '')
        NMJv2_DATABASE = check_setting_str(CFG, 'NMJv2', 'nmjv2_database', '')
        NMJv2_DBLOC = check_setting_str(CFG, 'NMJv2', 'nmjv2_dbloc', '')

        USE_SYNOINDEX = bool(check_setting_int(CFG, 'Synology', 'use_synoindex', 0))

        USE_SYNOLOGYNOTIFIER = bool(check_setting_int(CFG, 'SynologyNotifier', 'use_synologynotifier', 0))
        SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH = bool(
            check_setting_int(CFG, 'SynologyNotifier', 'synologynotifier_notify_onsnatch', 0))
        SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD = bool(
            check_setting_int(CFG, 'SynologyNotifier', 'synologynotifier_notify_ondownload', 0))
        SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'SynologyNotifier', 'synologynotifier_notify_onsubtitledownload', 0))

        USE_TRAKT = bool(check_setting_int(CFG, 'Trakt', 'use_trakt', 0))
        TRAKT_REMOVE_WATCHLIST = bool(check_setting_int(CFG, 'Trakt', 'trakt_remove_watchlist', 0))
        TRAKT_REMOVE_SERIESLIST = bool(check_setting_int(CFG, 'Trakt', 'trakt_remove_serieslist', 0))
        TRAKT_USE_WATCHLIST = bool(check_setting_int(CFG, 'Trakt', 'trakt_use_watchlist', 0))
        TRAKT_METHOD_ADD = check_setting_int(CFG, 'Trakt', 'trakt_method_add', 0)
        TRAKT_START_PAUSED = bool(check_setting_int(CFG, 'Trakt', 'trakt_start_paused', 0))
        TRAKT_SYNC = bool(check_setting_int(CFG, 'Trakt', 'trakt_sync', 0))
        TRAKT_DEFAULT_INDEXER = check_setting_int(CFG, 'Trakt', 'trakt_default_indexer', 1)
        TRAKT_UPDATE_COLLECTION = trakt_helpers.read_config_string(
            check_setting_str(CFG, 'Trakt', 'trakt_update_collection', ''))
        TRAKT_ACCOUNTS = TraktAPI.read_config_string(check_setting_str(CFG, 'Trakt', 'trakt_accounts', ''))
        TRAKT_MRU = check_setting_str(CFG, 'Trakt', 'trakt_mru', '')

        USE_PYTIVO = bool(check_setting_int(CFG, 'pyTivo', 'use_pytivo', 0))
        PYTIVO_HOST = check_setting_str(CFG, 'pyTivo', 'pytivo_host', '')
        PYTIVO_SHARE_NAME = check_setting_str(CFG, 'pyTivo', 'pytivo_share_name', '')
        PYTIVO_TIVO_NAME = check_setting_str(CFG, 'pyTivo', 'pytivo_tivo_name', '')

        USE_PUSHALOT = bool(check_setting_int(CFG, 'Pushalot', 'use_pushalot', 0))
        PUSHALOT_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Pushalot', 'pushalot_notify_onsnatch', 0))
        PUSHALOT_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Pushalot', 'pushalot_notify_ondownload', 0))
        PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Pushalot', 'pushalot_notify_onsubtitledownload', 0))
        PUSHALOT_AUTHORIZATIONTOKEN = check_setting_str(CFG, 'Pushalot', 'pushalot_authorizationtoken', '')

        USE_PUSHBULLET = bool(check_setting_int(CFG, 'Pushbullet', 'use_pushbullet', 0))
        PUSHBULLET_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Pushbullet', 'pushbullet_notify_onsnatch', 0))
        PUSHBULLET_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Pushbullet', 'pushbullet_notify_ondownload', 0))
        PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Pushbullet', 'pushbullet_notify_onsubtitledownload', 0))
        PUSHBULLET_ACCESS_TOKEN = check_setting_str(CFG, 'Pushbullet', 'pushbullet_access_token', '')
        PUSHBULLET_DEVICE_IDEN = check_setting_str(CFG, 'Pushbullet', 'pushbullet_device_iden', '')

        USE_SLACK = bool(check_setting_int(CFG, 'Slack', 'use_slack', 0))
        SLACK_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Slack', 'slack_notify_onsnatch', 0))
        SLACK_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Slack', 'slack_notify_ondownload', 0))
        SLACK_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Slack', 'slack_notify_onsubtitledownload', 0))
        SLACK_CHANNEL = check_setting_str(CFG, 'Slack', 'slack_channel', '')
        SLACK_AS_AUTHED = bool(check_setting_int(CFG, 'Slack', 'slack_as_authed', 0))
        SLACK_BOT_NAME = check_setting_str(CFG, 'Slack', 'slack_bot_name', '')
        SLACK_ICON_URL = check_setting_str(CFG, 'Slack', 'slack_icon_url', '')
        SLACK_ACCESS_TOKEN = check_setting_str(CFG, 'Slack', 'slack_access_token', '')

        USE_DISCORDAPP = bool(check_setting_int(CFG, 'Discordapp', 'use_discordapp', 0))
        DISCORDAPP_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Discordapp', 'discordapp_notify_onsnatch', 0))
        DISCORDAPP_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Discordapp', 'discordapp_notify_ondownload', 0))
        DISCORDAPP_NOTIFY_ONSUBTITLEDOWNLOAD = bool(
            check_setting_int(CFG, 'Discordapp', 'discordapp_notify_onsubtitledownload', 0))
        DISCORDAPP_AS_AUTHED = bool(check_setting_int(CFG, 'Discordapp', 'discordapp_as_authed', 0))
        DISCORDAPP_USERNAME = check_setting_str(CFG, 'Discordapp', 'discordapp_username', '')
        DISCORDAPP_ICON_URL = check_setting_str(CFG, 'Discordapp', 'discordapp_icon_url', '')
        DISCORDAPP_AS_TTS = bool(check_setting_str(CFG, 'Discordapp', 'discordapp_as_tts', 0))
        DISCORDAPP_ACCESS_TOKEN = check_setting_str(CFG, 'Discordapp', 'discordapp_access_token', '')

        USE_GITTER = bool(check_setting_int(CFG, 'Gitter', 'use_gitter', 0))
        GITTER_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Gitter', 'gitter_notify_onsnatch', 0))
        GITTER_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Gitter', 'gitter_notify_ondownload', 0))
        GITTER_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Gitter', 'gitter_notify_onsubtitledownload', 0))
        GITTER_ROOM = check_setting_str(CFG, 'Gitter', 'gitter_room', '')
        GITTER_ACCESS_TOKEN = check_setting_str(CFG, 'Gitter', 'gitter_access_token', '')

        USE_EMAIL = bool(check_setting_int(CFG, 'Email', 'use_email', 0))
        EMAIL_OLD_SUBJECTS = bool(check_setting_int(CFG, 'Email', 'email_old_subjects',
                                                    None is not EMAIL_HOST and any(EMAIL_HOST)))
        EMAIL_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Email', 'email_notify_onsnatch', 0))
        EMAIL_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Email', 'email_notify_ondownload', 0))
        EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD = bool(check_setting_int(CFG, 'Email', 'email_notify_onsubtitledownload', 0))
        EMAIL_HOST = check_setting_str(CFG, 'Email', 'email_host', '')
        EMAIL_PORT = check_setting_int(CFG, 'Email', 'email_port', 25)
        EMAIL_TLS = bool(check_setting_int(CFG, 'Email', 'email_tls', 0))
        EMAIL_USER = check_setting_str(CFG, 'Email', 'email_user', '')
        EMAIL_PASSWORD = check_setting_str(CFG, 'Email', 'email_password', '')
        EMAIL_FROM = check_setting_str(CFG, 'Email', 'email_from', '')
        EMAIL_LIST = check_setting_str(CFG, 'Email', 'email_list', '')

        USE_SUBTITLES = bool(check_setting_int(CFG, 'Subtitles', 'use_subtitles', 0))
        SUBTITLES_LANGUAGES = check_setting_str(CFG, 'Subtitles', 'subtitles_languages', '').split(',')
        if SUBTITLES_LANGUAGES[0] == '':
            SUBTITLES_LANGUAGES = []
        SUBTITLES_DIR = check_setting_str(CFG, 'Subtitles', 'subtitles_dir', '')
        SUBTITLES_SERVICES_LIST = check_setting_str(CFG, 'Subtitles', 'SUBTITLES_SERVICES_LIST', '').split(',')
        SUBTITLES_SERVICES_ENABLED = [int(x) for x in
                                      check_setting_str(CFG, 'Subtitles', 'SUBTITLES_SERVICES_ENABLED', '').split('|')
                                      if x]
        SUBTITLES_DEFAULT = bool(check_setting_int(CFG, 'Subtitles', 'subtitles_default', 0))
        SUBTITLES_HISTORY = bool(check_setting_int(CFG, 'Subtitles', 'subtitles_history', 0))
        SUBTITLES_FINDER_FREQUENCY = check_setting_int(CFG, 'Subtitles', 'subtitles_finder_frequency', 1)

        USE_FAILED_DOWNLOADS = bool(check_setting_int(CFG, 'FailedDownloads', 'use_failed_downloads', 0))
        DELETE_FAILED = bool(check_setting_int(CFG, 'FailedDownloads', 'delete_failed', 0))

        GIT_PATH = check_setting_str(CFG, 'General', 'git_path', '')

        IGNORE_WORDS = check_setting_str(CFG, 'General', 'ignore_words', IGNORE_WORDS)
        REQUIRE_WORDS = check_setting_str(CFG, 'General', 'require_words', REQUIRE_WORDS)

        CALENDAR_UNPROTECTED = bool(check_setting_int(CFG, 'General', 'calendar_unprotected', 0))

        EXTRA_SCRIPTS = [x.strip() for x in check_setting_str(CFG, 'General', 'extra_scripts', '').split('|') if
                         x.strip()]

        USE_ANIDB = bool(check_setting_int(CFG, 'ANIDB', 'use_anidb', 0))
        ANIDB_USERNAME = check_setting_str(CFG, 'ANIDB', 'anidb_username', '')
        ANIDB_PASSWORD = check_setting_str(CFG, 'ANIDB', 'anidb_password', '')
        ANIDB_USE_MYLIST = bool(check_setting_int(CFG, 'ANIDB', 'anidb_use_mylist', 0))

        ANIME_TREAT_AS_HDTV = bool(check_setting_int(CFG, 'ANIME', 'anime_treat_as_hdtv', 0))

        METADATA_XBMC = check_setting_str(CFG, 'General', 'metadata_xbmc', '0|0|0|0|0|0|0|0|0|0')
        METADATA_XBMC_12PLUS = check_setting_str(CFG, 'General', 'metadata_xbmc_12plus', '0|0|0|0|0|0|0|0|0|0')
        METADATA_MEDIABROWSER = check_setting_str(CFG, 'General', 'metadata_mediabrowser', '0|0|0|0|0|0|0|0|0|0')
        METADATA_PS3 = check_setting_str(CFG, 'General', 'metadata_ps3', '0|0|0|0|0|0|0|0|0|0')
        METADATA_WDTV = check_setting_str(CFG, 'General', 'metadata_wdtv', '0|0|0|0|0|0|0|0|0|0')
        METADATA_TIVO = check_setting_str(CFG, 'General', 'metadata_tivo', '0|0|0|0|0|0|0|0|0|0')
        METADATA_MEDE8ER = check_setting_str(CFG, 'General', 'metadata_mede8er', '0|0|0|0|0|0|0|0|0|0')
        METADATA_KODI = check_setting_str(CFG, 'General', 'metadata_kodi', '0|0|0|0|0|0|0|0|0|0')

        HOME_LAYOUT = check_setting_str(CFG, 'GUI', 'home_layout', 'poster')
        FOOTER_TIME_LAYOUT = check_setting_int(CFG, 'GUI', 'footer_time_layout', 0)
        POSTER_SORTBY = check_setting_str(CFG, 'GUI', 'poster_sortby', 'name')
        POSTER_SORTDIR = check_setting_int(CFG, 'GUI', 'poster_sortdir', 1)
        DISPLAY_SHOW_VIEWMODE = check_setting_int(CFG, 'GUI', 'display_show_viewmode', 2)
        DISPLAY_SHOW_BACKGROUND = bool(check_setting_int(CFG, 'GUI', 'display_show_background', 1))
        DISPLAY_SHOW_BACKGROUND_TRANSLUCENT = bool(check_setting_int(
            CFG, 'GUI', 'display_show_background_translucent', 1))
        DISPLAY_SHOW_VIEWART = check_setting_int(CFG, 'GUI', 'display_show_viewart', 0)
        DISPLAY_SHOW_MINIMUM = bool(check_setting_int(CFG, 'GUI', 'display_show_minimum', 1))
        DISPLAY_SHOW_SPECIALS = bool(check_setting_int(CFG, 'GUI', 'display_show_specials', 0))

        EPISODE_VIEW_VIEWMODE = check_setting_int(CFG, 'GUI', 'episode_view_viewmode', 2)
        EPISODE_VIEW_BACKGROUND = bool(check_setting_int(CFG, 'GUI', 'episode_view_background', 1))
        EPISODE_VIEW_BACKGROUND_TRANSLUCENT = bool(check_setting_int(
            CFG, 'GUI', 'episode_view_background_translucent', 1))
        EPISODE_VIEW_LAYOUT = check_setting_str(CFG, 'GUI', 'episode_view_layout', 'daybyday')
        EPISODE_VIEW_SORT = check_setting_str(CFG, 'GUI', 'episode_view_sort', 'time')
        EPISODE_VIEW_DISPLAY_PAUSED = bool(check_setting_int(CFG, 'GUI', 'episode_view_display_paused', 1))
        EPISODE_VIEW_POSTERS = bool(check_setting_int(CFG, 'GUI', 'episode_view_posters', 1))
        EPISODE_VIEW_MISSED_RANGE = check_setting_int(CFG, 'GUI', 'episode_view_missed_range', 7)

        HISTORY_LAYOUT = check_setting_str(CFG, 'GUI', 'history_layout', 'detailed')
        BROWSELIST_HIDDEN = [
            x.strip() for x in check_setting_str(CFG, 'GUI', 'browselist_hidden', '').split('|~|') if x.strip()]

        # initialize NZB and TORRENT providers
        providerList = providers.makeProviderList()

        NEWZNAB_DATA = check_setting_str(CFG, 'Newznab', 'newznab_data', '')
        newznabProviderList = providers.getNewznabProviderList(NEWZNAB_DATA)

        torrentrss_data = check_setting_str(CFG, 'TorrentRss', 'torrentrss_data', '')
        torrentRssProviderList = providers.getTorrentRssProviderList(torrentrss_data)

        # dynamically load provider settings
        for torrent_prov in [curProvider for curProvider in providers.sortedProviderList()
                             if GenericProvider.TORRENT == curProvider.providerType]:
            prov_id = torrent_prov.get_id()
            prov_id_uc = torrent_prov.get_id().upper()
            torrent_prov.enabled = bool(check_setting_int(CFG, prov_id_uc, prov_id, False))

            # check str with a def of list, don't add to block settings
            if getattr(torrent_prov, 'url_edit', None):
                torrent_prov.url_home = check_setting_str(CFG, prov_id_uc, prov_id + '_url_home', [])

            # check int with a default of str, don't add to block settings
            attr = 'seed_time'
            if hasattr(torrent_prov, attr):
                torrent_prov.seed_time = check_setting_int(CFG, prov_id_uc, '%s_%s' % (prov_id, attr), '')

            # custom cond, don't add to block settings
            attr = 'enable_recentsearch'
            if hasattr(torrent_prov, attr):
                torrent_prov.enable_recentsearch = bool(check_setting_int(
                    CFG, prov_id_uc, '%s_%s' % (prov_id, attr), True)) or not getattr(torrent_prov, 'supports_backlog')

            # check str with a default of list, don't add to block settings
            if hasattr(torrent_prov, 'filter'):
                torrent_prov.filter = check_setting_str(CFG, prov_id_uc, prov_id + '_filter', [])

            for (attr, default) in [
                ('enable_backlog', True), ('enable_scheduled_backlog', True),
                ('api_key', ''), ('hash', ''), ('digest', ''),
                ('username', ''), ('uid', ''), ('password', ''), ('passkey', ''),
                ('options', ''),
                ('_seed_ratio', ''), ('minseed', 0), ('minleech', 0),
                ('scene_only', False), ('scene_or_contain', ''), ('scene_loose', False), ('scene_loose_active', False),
                ('scene_rej_nuked', False), ('scene_nuked_active', False),
                ('freeleech', False), ('confirmed', False), ('reject_m2ts', False),
                ('search_mode', 'eponly'), ('search_fallback', False)
            ]:
                if hasattr(torrent_prov, attr):
                    attr_check = '%s_%s' % (prov_id, attr.strip('_'))
                    if isinstance(default, bool):
                        setattr(torrent_prov, attr, bool(check_setting_int(CFG, prov_id_uc, attr_check, default)))
                    elif isinstance(default, basestring):
                        setattr(torrent_prov, attr, check_setting_str(CFG, prov_id_uc, attr_check, default))
                    elif isinstance(default, int):
                        setattr(torrent_prov, attr, check_setting_int(CFG, prov_id_uc, attr_check, default))

        for nzb_prov in [curProvider for curProvider in providers.sortedProviderList()
                         if GenericProvider.NZB == curProvider.providerType]:
            prov_id = nzb_prov.get_id()
            prov_id_uc = nzb_prov.get_id().upper()
            nzb_prov.enabled = bool(check_setting_int(CFG, prov_id_uc, prov_id, False))

            attr = 'enable_recentsearch'
            if hasattr(nzb_prov, attr):
                nzb_prov.enable_recentsearch = bool(check_setting_int(
                    CFG, prov_id_uc, '%s_%s' % (prov_id, attr), True)) or not getattr(nzb_prov, 'supports_backlog')

            for (attr, default) in [
                ('enable_backlog', True), ('enable_scheduled_backlog', True),
                ('api_key', ''), ('username', ''),
                ('scene_only', False), ('scene_or_contain', ''), ('scene_loose', False), ('scene_loose_active', False),
                ('scene_rej_nuked', False), ('scene_nuked_active', False),
                ('search_mode', 'eponly'), ('search_fallback', False), ('server_type', NewznabConstants.SERVER_DEFAULT)
            ]:
                if hasattr(nzb_prov, attr):
                    attr_check = '%s_%s' % (prov_id, attr.strip('_'))
                    if isinstance(default, bool):
                        setattr(nzb_prov, attr, bool(check_setting_int(CFG, prov_id_uc, attr_check, default)))
                    elif isinstance(default, basestring):
                        setattr(nzb_prov, attr, check_setting_str(CFG, prov_id_uc, attr_check, default))
                    elif isinstance(default, int):
                        setattr(nzb_prov, attr, check_setting_int(CFG, prov_id_uc, attr_check, default))

        if not os.path.isfile(CONFIG_FILE):
            logger.log(u'Unable to find \'%s\', all settings will be default!' % CONFIG_FILE, logger.DEBUG)
            update_config = True

        if update_config:
            save_config()

        # start up all the threads
        old_log = os.path.join(LOG_DIR, 'sickbeard.log')
        if os.path.isfile(old_log):
            try:
                os.rename(old_log, os.path.join(LOG_DIR, logger.sb_log_instance.log_file))
            except (StandardError, Exception):
                pass
        logger.sb_log_instance.init_logging(console_logging=console_logging)

        # initialize the main SB database
        my_db = db.DBConnection()
        db.MigrationCode(my_db)

        # initialize the cache database
        my_db = db.DBConnection('cache.db')
        db.upgradeDatabase(my_db, cache_db.InitialSchema)

        # initialize the failed downloads database
        my_db = db.DBConnection('failed.db')
        db.upgradeDatabase(my_db, failed_db.InitialSchema)

        # fix up any db problems
        my_db = db.DBConnection()
        db.sanityCheckDatabase(my_db, mainDB.MainSanityCheck)

        # migrate the config if it needs it
        migrator = ConfigMigrator(CFG)
        migrator.migrate_config()

        # initialize metadata_providers
        metadata_provider_dict = metadata.get_metadata_generator_dict()
        for cur_metadata_tuple in [(METADATA_XBMC, metadata.xbmc),
                                   (METADATA_XBMC_12PLUS, metadata.xbmc_12plus),
                                   (METADATA_MEDIABROWSER, metadata.mediabrowser),
                                   (METADATA_PS3, metadata.ps3),
                                   (METADATA_WDTV, metadata.wdtv),
                                   (METADATA_TIVO, metadata.tivo),
                                   (METADATA_MEDE8ER, metadata.mede8er),
                                   (METADATA_KODI, metadata.kodi),
                                   ]:
            (cur_metadata_config, cur_metadata_class) = cur_metadata_tuple
            tmp_provider = cur_metadata_class.metadata_class()
            tmp_provider.set_config(cur_metadata_config)
            metadata_provider_dict[tmp_provider.name] = tmp_provider

        # initialize schedulers
        # updaters
        update_now = datetime.timedelta(minutes=0)
        versionCheckScheduler = scheduler.Scheduler(
            version_checker.CheckVersion(),
            cycleTime=datetime.timedelta(hours=UPDATE_FREQUENCY),
            threadName='CHECKVERSION',
            silent=False)

        showQueueScheduler = scheduler.Scheduler(
            show_queue.ShowQueue(),
            cycleTime=datetime.timedelta(seconds=3),
            threadName='SHOWQUEUE')

        showUpdateScheduler = scheduler.Scheduler(
            show_updater.ShowUpdater(),
            cycleTime=datetime.timedelta(hours=1),
            start_time=datetime.time(hour=SHOW_UPDATE_HOUR),
            threadName='SHOWUPDATER',
            prevent_cycle_run=showQueueScheduler.action.isShowUpdateRunning)  # 3AM

        # searchers
        searchQueueScheduler = scheduler.Scheduler(
            search_queue.SearchQueue(),
            cycleTime=datetime.timedelta(seconds=3),
            threadName='SEARCHQUEUE')

        # enter 4490 (was 4489) for experimental internal provider frequencies
        update_interval = datetime.timedelta(minutes=(RECENTSEARCH_FREQUENCY, 1)[4499 == RECENTSEARCH_FREQUENCY])
        recentSearchScheduler = scheduler.Scheduler(
            search_recent.RecentSearcher(),
            cycleTime=update_interval,
            run_delay=update_now if RECENTSEARCH_STARTUP else datetime.timedelta(minutes=5),
            threadName='RECENTSEARCHER',
            prevent_cycle_run=searchQueueScheduler.action.is_recentsearch_in_progress)

        if [x for x in providers.sortedProviderList() if x.is_active() and
                x.enable_backlog and x.providerType == GenericProvider.NZB]:
            nextbacklogpossible = datetime.datetime.fromtimestamp(
                search_backlog.BacklogSearcher().last_runtime) + datetime.timedelta(hours=23)
            now = datetime.datetime.now()
            if nextbacklogpossible > now:
                time_diff = nextbacklogpossible - now
                if (time_diff > datetime.timedelta(hours=12) and
                        nextbacklogpossible - datetime.timedelta(hours=12) > now):
                    time_diff = time_diff - datetime.timedelta(hours=12)
            else:
                time_diff = datetime.timedelta(minutes=0)
            backlogdelay = helpers.tryInt((time_diff.total_seconds() / 60) + 10, 10)
        else:
            backlogdelay = 10
        backlogSearchScheduler = search_backlog.BacklogSearchScheduler(
            search_backlog.BacklogSearcher(),
            cycleTime=datetime.timedelta(minutes=get_backlog_cycle_time()),
            run_delay=datetime.timedelta(minutes=backlogdelay),
            threadName='BACKLOG',
            prevent_cycle_run=searchQueueScheduler.action.is_standard_backlog_in_progress)

        propers_searcher = search_propers.ProperSearcher()
        last_proper_search = datetime.datetime.fromtimestamp(properFinder.get_last_proper_search())
        time_diff = datetime.timedelta(days=1) - (datetime.datetime.now() - last_proper_search)
        if time_diff < datetime.timedelta(seconds=0):
            properdelay = 20
        else:
            properdelay = helpers.tryInt((time_diff.total_seconds() / 60) + 5, 20)

        properFinderScheduler = scheduler.Scheduler(
            propers_searcher,
            cycleTime=datetime.timedelta(days=1),
            run_delay=datetime.timedelta(minutes=properdelay),
            threadName='FINDPROPERS',
            prevent_cycle_run=searchQueueScheduler.action.is_propersearch_in_progress)

        # processors
        autoPostProcesserScheduler = scheduler.Scheduler(
            auto_post_processer.PostProcesser(),
            cycleTime=datetime.timedelta(minutes=AUTOPOSTPROCESSER_FREQUENCY),
            threadName='POSTPROCESSER',
            silent=not PROCESS_AUTOMATICALLY)
        """
        traktCheckerScheduler = scheduler.Scheduler(
            traktChecker.TraktChecker(), cycleTime=datetime.timedelta(hours=1),
            threadName='TRAKTCHECKER', silent=not USE_TRAKT)
        """
        subtitlesFinderScheduler = scheduler.Scheduler(
            subtitles.SubtitlesFinder(),
            cycleTime=datetime.timedelta(hours=SUBTITLES_FINDER_FREQUENCY),
            threadName='FINDSUBTITLES',
            silent=not USE_SUBTITLES)

        showList = []

        background_mapping_task = threading.Thread(name='LOAD-MAPPINGS', target=indexermapper.load_mapped_ids)

        watchedStateQueueScheduler = scheduler.Scheduler(
            watchedstate_queue.WatchedStateQueue(),
            cycleTime=datetime.timedelta(seconds=3),
            threadName='WATCHEDSTATEQUEUE')

        embyWatchedStateScheduler = scheduler.Scheduler(
            EmbyWatchedStateUpdater(),
            cycleTime=datetime.timedelta(minutes=EMBY_WATCHEDSTATE_FREQUENCY),
            run_delay=datetime.timedelta(minutes=5),
            threadName='EMBYWATCHEDSTATE')

        plexWatchedStateScheduler = scheduler.Scheduler(
            PlexWatchedStateUpdater(),
            cycleTime=datetime.timedelta(minutes=PLEX_WATCHEDSTATE_FREQUENCY),
            run_delay=datetime.timedelta(minutes=5),
            threadName='PLEXWATCHEDSTATE')

        try:
            import _scandir
        except ImportError:
            _scandir = None

        try:
            import ctypes
        except ImportError:
            ctypes = None

        if None is not _scandir and None is not ctypes and not getattr(_scandir, 'DirEntry', None):
            MODULE_UPDATE_STRING = \
                'Your scandir binary module is outdated, using the slow but newer Python module.' \
                '<br>Upgrade the binary at a command prompt with' \
                ' # <span class="boldest">python -m pip install -U scandir</span>' \
                '<br>Important: You <span class="boldest">must</span> Shutdown SickGear before upgrading'

        __INITIALIZED__ = True
        return True


def enabled_schedulers(is_init=False):
    # ([], [traktCheckerScheduler])[USE_TRAKT] + \
    for s in ([], [events])[is_init] + \
            [recentSearchScheduler, backlogSearchScheduler, showUpdateScheduler,
             versionCheckScheduler, showQueueScheduler, searchQueueScheduler, properFinderScheduler,
             autoPostProcesserScheduler, subtitlesFinderScheduler,
             embyWatchedStateScheduler, plexWatchedStateScheduler, watchedStateQueueScheduler] + \
            ([events], [])[is_init]:
        yield s


def start():
    global started

    with INIT_LOCK:
        if __INITIALIZED__:
            # Load all Indexer mappings in background
            indexermapper.defunct_indexer = [
                i for i in indexerApi().all_indexers if indexerApi(i).config.get('defunct')]
            indexermapper.indexer_list = [i for i in indexerApi().all_indexers]
            background_mapping_task.start()

            for p in providers.sortedProviderList():
                if p.is_active() and getattr(p, 'ping_freq', None):
                    # noinspection PyProtectedMember
                    provider_ping_thread_pool[p.get_id()] = threading.Thread(
                        name='PING-PROVIDER %s' % p.name, target=p._ping)
                    provider_ping_thread_pool[p.get_id()].start()

            for thread in enabled_schedulers(is_init=True):
                thread.start()

            started = True


def restart(soft=True):
    if soft:
        halt()
        save_all()
        logger.log(u'Re-initializing all data')
        initialize()
    else:
        events.put(events.SystemEvent.RESTART)


def sig_handler(signum=None, _=None):
    is_ctrlbreak = 'win32' == sys.platform and signal.SIGBREAK == signum
    msg = u'Signal "%s" found' % (signal.SIGINT == signum and 'CTRL-C' or is_ctrlbreak and 'CTRL+BREAK' or
                                  signal.SIGTERM == signum and 'Termination' or signum)
    if None is signum or signum in (signal.SIGINT, signal.SIGTERM) or is_ctrlbreak:
        logger.log('%s, saving and exiting...' % msg)
        events.put(events.SystemEvent.SHUTDOWN)
    else:
        logger.log('%s, not exiting' % msg)


def halt():
    global __INITIALIZED__, started

    with INIT_LOCK:

        if __INITIALIZED__:

            logger.log('Exiting threads')

            for p in provider_ping_thread_pool:
                provider_ping_thread_pool[p].stop = True

            for p in provider_ping_thread_pool:
                try:
                    provider_ping_thread_pool[p].join(10)
                    logger.log('Thread %s has exit' % provider_ping_thread_pool[p].name)
                except RuntimeError:
                    logger.log('Fail, thread %s did not exit' % provider_ping_thread_pool[p].name)
                    pass

            if ADBA_CONNECTION:
                try:
                    ADBA_CONNECTION.logout()
                except AniDBBannedError as e:
                    logger.log('AniDB Error %s' % ex(e), logger.DEBUG)
                except AniDBError:
                    pass
                try:
                    ADBA_CONNECTION.join(10)
                    logger.log('Thread %s has exit' % ADBA_CONNECTION.name)
                except (StandardError, Exception):
                    logger.log('Fail, thread %s did not exit' % ADBA_CONNECTION.name)

            for thread in enabled_schedulers():
                thread.stop()

            for thread in enabled_schedulers():
                try:
                    thread.join(10)
                    logger.log('Thread %s has exit' % thread.name)
                except RuntimeError:
                    logger.log('Thread %s did not exit' % thread.name)

            __INITIALIZED__ = False
            started = False


def save_all():
    global showList

    # write all shows
    logger.log(u'Saving all shows to the database')
    for show in showList:
        show.saveToDB()

    # save config
    logger.log(u'Saving config file to disk')
    save_config()


def save_config():
    new_config = ConfigObj()
    new_config.filename = CONFIG_FILE

    # For passwords you must include the word `password` in the item_name and
    # add `helpers.encrypt(ITEM_NAME, ENCRYPTION_VERSION)` in save_config()
    new_config['General'] = {}
    s_z = check_setting_int(CFG, 'General', 'stack_size', 0)
    if s_z:
        new_config['General']['stack_size'] = s_z
    new_config['General']['config_version'] = CONFIG_VERSION
    new_config['General']['branch'] = BRANCH
    new_config['General']['git_remote'] = GIT_REMOTE
    new_config['General']['cur_commit_hash'] = CUR_COMMIT_HASH
    new_config['General']['cur_commit_branch'] = CUR_COMMIT_BRANCH
    new_config['General']['encryption_version'] = int(ENCRYPTION_VERSION)
    new_config['General']['log_dir'] = ACTUAL_LOG_DIR if ACTUAL_LOG_DIR else 'Logs'
    new_config['General']['file_logging_preset'] = FILE_LOGGING_PRESET if FILE_LOGGING_PRESET else 'DB'
    new_config['General']['socket_timeout'] = SOCKET_TIMEOUT
    new_config['General']['web_host'] = WEB_HOST
    new_config['General']['web_port'] = WEB_PORT
    new_config['General']['web_ipv6'] = int(WEB_IPV6)
    new_config['General']['web_ipv64'] = int(WEB_IPV64)
    new_config['General']['web_log'] = int(WEB_LOG)
    new_config['General']['web_root'] = WEB_ROOT
    new_config['General']['web_username'] = WEB_USERNAME
    new_config['General']['web_password'] = helpers.encrypt(WEB_PASSWORD, ENCRYPTION_VERSION)
    new_config['General']['cpu_preset'] = CPU_PRESET
    new_config['General']['anon_redirect'] = ANON_REDIRECT
    new_config['General']['use_api'] = int(USE_API)
    new_config['General']['api_key'] = API_KEY
    new_config['General']['debug'] = int(DEBUG)
    new_config['General']['enable_https'] = int(ENABLE_HTTPS)
    new_config['General']['https_cert'] = HTTPS_CERT
    new_config['General']['https_key'] = HTTPS_KEY
    new_config['General']['handle_reverse_proxy'] = int(HANDLE_REVERSE_PROXY)
    new_config['General']['send_security_headers'] = int(SEND_SECURITY_HEADERS)
    new_config['General']['allowed_hosts'] = ALLOWED_HOSTS
    new_config['General']['use_nzbs'] = int(USE_NZBS)
    new_config['General']['use_torrents'] = int(USE_TORRENTS)
    new_config['General']['nzb_method'] = NZB_METHOD
    new_config['General']['torrent_method'] = TORRENT_METHOD
    new_config['General']['usenet_retention'] = int(USENET_RETENTION)
    new_config['General']['autopostprocesser_frequency'] = int(AUTOPOSTPROCESSER_FREQUENCY)
    new_config['General']['recentsearch_frequency'] = int(RECENTSEARCH_FREQUENCY)
    new_config['General']['backlog_frequency'] = int(BACKLOG_FREQUENCY)
    new_config['General']['update_frequency'] = int(UPDATE_FREQUENCY)
    new_config['General']['download_propers'] = int(DOWNLOAD_PROPERS)
    new_config['General']['propers_webdl_onegrp'] = int(PROPERS_WEBDL_ONEGRP)
    new_config['General']['allow_high_priority'] = int(ALLOW_HIGH_PRIORITY)
    new_config['General']['recentsearch_startup'] = int(RECENTSEARCH_STARTUP)
    new_config['General']['backlog_nofull'] = int(BACKLOG_NOFULL)
    new_config['General']['skip_removed_files'] = int(SKIP_REMOVED_FILES)
    new_config['General']['results_sortby'] = str(RESULTS_SORTBY)
    new_config['General']['quality_default'] = int(QUALITY_DEFAULT)
    new_config['General']['status_default'] = int(STATUS_DEFAULT)
    new_config['General']['wanted_begin_default'] = int(WANTED_BEGIN_DEFAULT)
    new_config['General']['wanted_latest_default'] = int(WANTED_LATEST_DEFAULT)
    new_config['General']['flatten_folders_default'] = int(FLATTEN_FOLDERS_DEFAULT)
    new_config['General']['indexer_default'] = int(INDEXER_DEFAULT)
    new_config['General']['indexer_timeout'] = int(INDEXER_TIMEOUT)
    new_config['General']['anime_default'] = int(ANIME_DEFAULT)
    new_config['General']['scene_default'] = int(SCENE_DEFAULT)
    new_config['General']['provider_order'] = ' '.join(PROVIDER_ORDER)
    new_config['General']['provider_homes'] = '%s' % dict([(pid, v) for pid, v in PROVIDER_HOMES.items() if pid in [
        p.get_id() for p in [x for x in providers.sortedProviderList() if GenericProvider.TORRENT == x.providerType]]])
    new_config['General']['version_notify'] = int(VERSION_NOTIFY)
    new_config['General']['auto_update'] = int(AUTO_UPDATE)
    new_config['General']['notify_on_update'] = int(NOTIFY_ON_UPDATE)
    new_config['General']['naming_strip_year'] = int(NAMING_STRIP_YEAR)
    new_config['General']['naming_pattern'] = NAMING_PATTERN
    new_config['General']['naming_custom_abd'] = int(NAMING_CUSTOM_ABD)
    new_config['General']['naming_abd_pattern'] = NAMING_ABD_PATTERN
    new_config['General']['naming_custom_sports'] = int(NAMING_CUSTOM_SPORTS)
    new_config['General']['naming_sports_pattern'] = NAMING_SPORTS_PATTERN
    new_config['General']['naming_custom_anime'] = int(NAMING_CUSTOM_ANIME)
    new_config['General']['naming_anime_pattern'] = NAMING_ANIME_PATTERN
    new_config['General']['naming_multi_ep'] = int(NAMING_MULTI_EP)
    new_config['General']['naming_anime_multi_ep'] = int(NAMING_ANIME_MULTI_EP)
    new_config['General']['naming_anime'] = int(NAMING_ANIME)
    new_config['General']['launch_browser'] = int(LAUNCH_BROWSER)
    new_config['General']['update_shows_on_start'] = int(UPDATE_SHOWS_ON_START)
    new_config['General']['show_update_hour'] = int(SHOW_UPDATE_HOUR)
    new_config['General']['trash_remove_show'] = int(TRASH_REMOVE_SHOW)
    new_config['General']['trash_rotate_logs'] = int(TRASH_ROTATE_LOGS)
    new_config['General']['home_search_focus'] = int(HOME_SEARCH_FOCUS)
    new_config['General']['display_freespace'] = int(DISPLAY_FREESPACE)
    new_config['General']['sort_article'] = int(SORT_ARTICLE)
    new_config['General']['proxy_setting'] = PROXY_SETTING
    new_config['General']['proxy_indexers'] = int(PROXY_INDEXERS)

    new_config['General']['metadata_xbmc'] = METADATA_XBMC
    new_config['General']['metadata_xbmc_12plus'] = METADATA_XBMC_12PLUS
    new_config['General']['metadata_mediabrowser'] = METADATA_MEDIABROWSER
    new_config['General']['metadata_ps3'] = METADATA_PS3
    new_config['General']['metadata_wdtv'] = METADATA_WDTV
    new_config['General']['metadata_tivo'] = METADATA_TIVO
    new_config['General']['metadata_mede8er'] = METADATA_MEDE8ER
    new_config['General']['metadata_kodi'] = METADATA_KODI

    new_config['General']['backlog_days'] = int(BACKLOG_DAYS)
    new_config['General']['search_unaired'] = int(SEARCH_UNAIRED)
    new_config['General']['unaired_recent_search_only'] = int(UNAIRED_RECENT_SEARCH_ONLY)

    new_config['General']['cache_dir'] = ACTUAL_CACHE_DIR if ACTUAL_CACHE_DIR else 'cache'
    new_config['General']['root_dirs'] = ROOT_DIRS if ROOT_DIRS else ''
    new_config['General']['tv_download_dir'] = TV_DOWNLOAD_DIR
    new_config['General']['keep_processed_dir'] = int(KEEP_PROCESSED_DIR)
    new_config['General']['process_method'] = PROCESS_METHOD
    new_config['General']['move_associated_files'] = int(MOVE_ASSOCIATED_FILES)
    new_config['General']['postpone_if_sync_files'] = int(POSTPONE_IF_SYNC_FILES)
    new_config['General']['nfo_rename'] = int(NFO_RENAME)
    new_config['General']['process_automatically'] = int(PROCESS_AUTOMATICALLY)
    new_config['General']['unpack'] = int(UNPACK)
    new_config['General']['rename_episodes'] = int(RENAME_EPISODES)
    new_config['General']['airdate_episodes'] = int(AIRDATE_EPISODES)
    new_config['General']['create_missing_show_dirs'] = int(CREATE_MISSING_SHOW_DIRS)
    new_config['General']['add_shows_wo_dir'] = int(ADD_SHOWS_WO_DIR)
    new_config['General']['remove_filename_chars'] = REMOVE_FILENAME_CHARS
    new_config['General']['import_default_checked_shows'] = int(IMPORT_DEFAULT_CHECKED_SHOWS)

    new_config['General']['extra_scripts'] = '|'.join(EXTRA_SCRIPTS)
    new_config['General']['git_path'] = GIT_PATH
    new_config['General']['ignore_words'] = IGNORE_WORDS
    new_config['General']['require_words'] = REQUIRE_WORDS
    new_config['General']['calendar_unprotected'] = int(CALENDAR_UNPROTECTED)

    for src in filter(lambda px: GenericProvider.TORRENT == px.providerType, providers.sortedProviderList()):
        src_id = src.get_id()
        src_id_uc = src_id.upper()
        new_config[src_id_uc] = {}
        if int(src.enabled):
            new_config[src_id_uc][src_id] = int(src.enabled)
        if getattr(src, 'url_edit', None):
            new_config[src_id_uc][src_id + '_url_home'] = src.url_home

        if getattr(src, 'password', None):
            new_config[src_id_uc][src_id + '_password'] = helpers.encrypt(src.password, ENCRYPTION_VERSION)

        for (attr, value) in [
            (k, getattr(src, k, v) if not v else helpers.tryInt(getattr(src, k, None)))
            for (k, v) in [
                ('enable_recentsearch', 1), ('enable_backlog', 1), ('enable_scheduled_backlog', 1),
                ('api_key', None), ('passkey', None), ('digest', None), ('hash', None), ('username', ''), ('uid', ''),
                ('minseed', 1), ('minleech', 1), ('seed_time', None),
                ('confirmed', 1), ('freeleech', 1), ('reject_m2ts', 1),
                ('scene_only', None), ('scene_or_contain', ''), ('scene_loose', None), ('scene_loose_active', None),
                ('scene_rej_nuked', None), ('scene_nuked_active', None),
                ('search_mode', None), ('search_fallback', 1)
            ]
                if hasattr(src, k)]:
            if (value and not ('search_mode' == attr and 'eponly' == value)
                    # must allow the following to save '0' not '1' because default is enable (1) instead of disable (0)
                    and (attr not in ('enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog'))
                    or not value and (attr in ('enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog'))):
                new_config[src_id_uc]['%s_%s' % (src_id, attr)] = value

        if getattr(src, '_seed_ratio', None):
            new_config[src_id_uc][src_id + '_seed_ratio'] = src.seed_ratio()
        if getattr(src, 'filter', None):
            new_config[src_id_uc][src_id + '_filter'] = src.filter

        if not new_config[src_id_uc]:
            del new_config[src_id_uc]

    for src in filter(lambda px: GenericProvider.NZB == px.providerType, providers.sortedProviderList()):
        src_id = src.get_id()
        src_id_uc = src.get_id().upper()
        new_config[src_id_uc] = {}
        if int(src.enabled):
            new_config[src_id_uc][src_id] = int(src.enabled)

        for attr in filter(lambda a: None is not getattr(src, a, None), ('api_key', 'username', 'search_mode')):
            if 'search_mode' != attr or 'eponly' != getattr(src, attr):
                new_config[src_id_uc]['%s_%s' % (src_id, attr)] = getattr(src, attr)

        for attr in filter(lambda a: None is not getattr(src, a, None), (
                'enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog',
                'scene_only', 'scene_loose', 'scene_loose_active',
                'scene_rej_nuked', 'scene_nuked_active',
                'search_fallback', 'server_type')):
            value = helpers.tryInt(getattr(src, attr, None))
            # must allow the following to save '0' not '1' because default is enable (1) instead of disable (0)
            if (value and (attr not in ('enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog'))
                    or not value and (attr in ('enable_recentsearch', 'enable_backlog', 'enable_scheduled_backlog'))):
                new_config[src_id_uc]['%s_%s' % (src_id, attr)] = value

        attr = 'scene_or_contain'
        if getattr(src, attr, None):
            new_config[src_id_uc]['%s_%s' % (src_id, attr)] = getattr(src, attr, '')

        if not new_config[src_id_uc]:
            del new_config[src_id_uc]

    from collections import OrderedDict
    cfg_keys = []
    for (cfg, items) in OrderedDict([
        # -----------------------------------
        # Config/Search
        # -----------------------------------
        ('Blackhole', [
            ('nzb_dir', NZB_DIR), ('torrent_dir', TORRENT_DIR)]),
        ('NZBGet', [
            ('username', NZBGET_USERNAME), ('password', helpers.encrypt(NZBGET_PASSWORD, ENCRYPTION_VERSION)),
            ('host', NZBGET_HOST),
            ('category', NZBGET_CATEGORY),
            ('use_https', int(NZBGET_USE_HTTPS)),
            ('priority', NZBGET_PRIORITY),
            ('map', NZBGET_MAP),
        ]),
        ('SABnzbd', [
            ('username', SAB_USERNAME), ('password', helpers.encrypt(SAB_PASSWORD, ENCRYPTION_VERSION)),
            ('apikey', SAB_APIKEY),
            ('host', SAB_HOST),
            ('category', SAB_CATEGORY),
        ]),
        ('TORRENT', [
            ('username', TORRENT_USERNAME), ('password', helpers.encrypt(TORRENT_PASSWORD, ENCRYPTION_VERSION)),
            ('host', TORRENT_HOST),
            ('path', TORRENT_PATH),
            ('seed_time', int(TORRENT_SEED_TIME)),
            ('paused', int(TORRENT_PAUSED)),
            ('high_bandwidth', int(TORRENT_HIGH_BANDWIDTH)),
            ('label', TORRENT_LABEL),
            ('verify_cert', int(TORRENT_VERIFY_CERT)),
        ]),
        # -----------------------------------
        # Config/Notifications
        # -----------------------------------
        ('Emby', [
            ('use_%s', int(USE_EMBY)),
            ('apikey', EMBY_APIKEY), ('host', EMBY_HOST),
            ('update_library', int(EMBY_UPDATE_LIBRARY)),
            ('watchedstate_scheduled', int(EMBY_WATCHEDSTATE_SCHEDULED)),
            ('watchedstate_frequency', int(EMBY_WATCHEDSTATE_FREQUENCY)),
            ('parent_maps', EMBY_PARENT_MAPS),
        ]),
        ('Kodi', [
            ('use_%s', int(USE_KODI)),
            ('username', KODI_USERNAME), ('password', helpers.encrypt(KODI_PASSWORD, ENCRYPTION_VERSION)),
            ('host', KODI_HOST),
            ('always_on', int(KODI_ALWAYS_ON)), ('update_library', int(KODI_UPDATE_LIBRARY)),
            ('update_full', int(KODI_UPDATE_FULL)),
            ('update_onlyfirst', int(KODI_UPDATE_ONLYFIRST)),
            ('parent_maps', KODI_PARENT_MAPS),
        ]),
        ('Plex', [
            ('use_%s', int(USE_PLEX)),
            ('username', PLEX_USERNAME), ('password', helpers.encrypt(PLEX_PASSWORD, ENCRYPTION_VERSION)),
            ('host', PLEX_HOST),
            ('update_library', int(PLEX_UPDATE_LIBRARY)),
            ('watchedstate_scheduled', int(PLEX_WATCHEDSTATE_SCHEDULED)),
            ('watchedstate_frequency', int(PLEX_WATCHEDSTATE_FREQUENCY)),
            ('parent_maps', PLEX_PARENT_MAPS),
            ('server_host', PLEX_SERVER_HOST),
        ]),
        ('XBMC', [
            ('use_%s', int(USE_XBMC)),
            ('username', XBMC_USERNAME), ('password', helpers.encrypt(XBMC_PASSWORD, ENCRYPTION_VERSION)),
            ('host', XBMC_HOST),
            ('always_on', int(XBMC_ALWAYS_ON)), ('update_library', int(XBMC_UPDATE_LIBRARY)),
            ('update_full', int(XBMC_UPDATE_FULL)),
            ('update_onlyfirst', int(XBMC_UPDATE_ONLYFIRST)),
        ]),
        ('NMJ', [
            ('use_%s', int(USE_NMJ)),
            ('host', NMJ_HOST),
            ('database', NMJ_DATABASE),
            ('mount', NMJ_MOUNT),
        ]),
        ('NMJv2', [
            ('use_%s', int(USE_NMJv2)),
            ('host', NMJv2_HOST),
            ('database', NMJv2_DATABASE),
            ('dbloc', NMJv2_DBLOC),
        ]),
        ('Synology', [
            ('use_synoindex', int(USE_SYNOINDEX)),
        ]),
        ('SynologyNotifier', [
            ('use_%s', int(USE_SYNOLOGYNOTIFIER)),
        ]),
        ('pyTivo', [
            ('use_%s', int(USE_PYTIVO)),
            ('host', PYTIVO_HOST),
            ('share_name', PYTIVO_SHARE_NAME),
            ('tivo_name', PYTIVO_TIVO_NAME),
        ]),
        ('Boxcar2', [
            ('use_%s', int(USE_BOXCAR2)),
            ('accesstoken', BOXCAR2_ACCESSTOKEN),
            ('sound', BOXCAR2_SOUND if 'default' != BOXCAR2_SOUND else None),
        ]),
        ('Pushbullet', [
            ('use_%s', int(USE_PUSHBULLET)),
            ('access_token', PUSHBULLET_ACCESS_TOKEN),
            ('device_iden', PUSHBULLET_DEVICE_IDEN),
        ]),
        ('Pushover', [
            ('use_%s', int(USE_PUSHOVER)),
            ('userkey', PUSHOVER_USERKEY),
            ('apikey', PUSHOVER_APIKEY),
            ('priority', PUSHOVER_PRIORITY if '0' != PUSHOVER_PRIORITY else None),
            ('device', PUSHOVER_DEVICE if 'all' != PUSHOVER_DEVICE else None),
            ('sound', PUSHOVER_SOUND if 'pushover' != PUSHOVER_SOUND else None),
        ]),
        ('Growl', [
            ('use_%s', int(USE_GROWL)),
            ('host', GROWL_HOST),
            ('password', helpers.encrypt(GROWL_PASSWORD, ENCRYPTION_VERSION)),
        ]),
        ('Prowl', [
            ('use_%s', int(USE_PROWL)),
            ('api', PROWL_API),
            ('priority', PROWL_PRIORITY if '0' != PROWL_PRIORITY else None),
        ]),
        ('Libnotify', [
            ('use_%s', int(USE_LIBNOTIFY))
        ]),
        # deprecated service
        # new_config['Pushalot'] = {}
        # new_config['Pushalot']['use_pushalot'] = int(USE_PUSHALOT)
        # new_config['Pushalot']['pushalot_authorizationtoken'] = PUSHALOT_AUTHORIZATIONTOKEN
        ('Trakt', [
            ('use_%s', int(USE_TRAKT)),
            ('update_collection', TRAKT_UPDATE_COLLECTION and trakt_helpers.build_config_string(TRAKT_UPDATE_COLLECTION)),
            ('accounts', TraktAPI.build_config_string(TRAKT_ACCOUNTS)),
            ('mru', TRAKT_MRU),
            # new_config['Trakt'] = {}
            # new_config['Trakt']['trakt_remove_watchlist'] = int(TRAKT_REMOVE_WATCHLIST)
            # new_config['Trakt']['trakt_remove_serieslist'] = int(TRAKT_REMOVE_SERIESLIST)
            # new_config['Trakt']['trakt_use_watchlist'] = int(TRAKT_USE_WATCHLIST)
            # new_config['Trakt']['trakt_method_add'] = int(TRAKT_METHOD_ADD)
            # new_config['Trakt']['trakt_start_paused'] = int(TRAKT_START_PAUSED)
            # new_config['Trakt']['trakt_sync'] = int(TRAKT_SYNC)
            # new_config['Trakt']['trakt_default_indexer'] = int(TRAKT_DEFAULT_INDEXER)
        ]),
        ('Slack', [
            ('use_%s', int(USE_SLACK)),
            ('channel', SLACK_CHANNEL),
            ('as_authed', int(SLACK_AS_AUTHED)),
            ('bot_name', SLACK_BOT_NAME),
            ('icon_url', SLACK_ICON_URL),
            ('access_token', SLACK_ACCESS_TOKEN),
        ]),
        ('Discordapp', [
            ('use_%s', int(USE_DISCORDAPP)),
            ('as_authed', int(DISCORDAPP_AS_AUTHED)),
            ('username', DISCORDAPP_USERNAME),
            ('icon_url', DISCORDAPP_ICON_URL),
            ('as_tts', int(DISCORDAPP_AS_TTS)),
            ('access_token', DISCORDAPP_ACCESS_TOKEN),
        ]),
        ('Gitter', [
            ('use_%s', int(USE_GITTER)),
            ('room', GITTER_ROOM),
            ('access_token', GITTER_ACCESS_TOKEN),
        ]),
        ('Twitter', [
            ('use_%s', int(USE_TWITTER)),
            ('username', TWITTER_USERNAME), ('password', helpers.encrypt(TWITTER_PASSWORD, ENCRYPTION_VERSION)),
            ('prefix', TWITTER_PREFIX),
        ]),
        ('Email', [
            ('use_%s', int(USE_EMAIL)),
            ('old_subjects', int(EMAIL_OLD_SUBJECTS)),
            ('host', EMAIL_HOST), ('port', int(EMAIL_PORT) if 25 != int(EMAIL_PORT) else None),
            ('tls', int(EMAIL_TLS)),
            ('user', EMAIL_USER), ('password', helpers.encrypt(EMAIL_PASSWORD, ENCRYPTION_VERSION)),
            ('from', EMAIL_FROM),
            ('list', EMAIL_LIST),
        ]),
        # (, [(, )]),
    ]).items():
        cfg_lc = cfg.lower()
        cfg_keys += [cfg]
        new_config[cfg] = {}
        for (k, v) in filter(lambda (_, y): any([y]) or (
                # allow saving where item value default is non-zero but 0 is a required setting value
                cfg_lc in ('kodi', 'xbmc', 'synoindex', 'nzbget') and _ in ('always_on', 'priority')), items):
            k = '%s' in k and (k % cfg_lc) or (cfg_lc + '_' + k)
            # correct for cases where keys are named in an inconsistent manner to parent stanza
            k = k.replace('blackhole_', '').replace('sabnzbd_', 'sab_')
            new_config[cfg].update({k: v})

    for (notifier, onsnatch, ondownload, onsubtitledownload) in [
        ('Kodi', KODI_NOTIFY_ONSNATCH, KODI_NOTIFY_ONDOWNLOAD, KODI_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Plex', PLEX_NOTIFY_ONSNATCH, PLEX_NOTIFY_ONDOWNLOAD, PLEX_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('XBMC', XBMC_NOTIFY_ONSNATCH, XBMC_NOTIFY_ONDOWNLOAD, XBMC_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('SynologyNotifier', SYNOLOGYNOTIFIER_NOTIFY_ONSNATCH, SYNOLOGYNOTIFIER_NOTIFY_ONDOWNLOAD,
         SYNOLOGYNOTIFIER_NOTIFY_ONSUBTITLEDOWNLOAD),

        ('Boxcar2', BOXCAR2_NOTIFY_ONSNATCH, BOXCAR2_NOTIFY_ONDOWNLOAD, BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Pushbullet', PUSHBULLET_NOTIFY_ONSNATCH, PUSHBULLET_NOTIFY_ONDOWNLOAD, PUSHBULLET_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Pushover', PUSHOVER_NOTIFY_ONSNATCH, PUSHOVER_NOTIFY_ONDOWNLOAD, PUSHOVER_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Growl', GROWL_NOTIFY_ONSNATCH, GROWL_NOTIFY_ONDOWNLOAD, GROWL_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Prowl', PROWL_NOTIFY_ONSNATCH, PROWL_NOTIFY_ONDOWNLOAD, PROWL_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Libnotify', LIBNOTIFY_NOTIFY_ONSNATCH, LIBNOTIFY_NOTIFY_ONDOWNLOAD, LIBNOTIFY_NOTIFY_ONSUBTITLEDOWNLOAD),
        # ('Pushalot', PUSHALOT_NOTIFY_ONSNATCH, PUSHALOT_NOTIFY_ONDOWNLOAD, PUSHALOT_NOTIFY_ONSUBTITLEDOWNLOAD),

        ('Slack', SLACK_NOTIFY_ONSNATCH, SLACK_NOTIFY_ONDOWNLOAD, SLACK_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Discordapp', DISCORDAPP_NOTIFY_ONSNATCH, DISCORDAPP_NOTIFY_ONDOWNLOAD, DISCORDAPP_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Gitter', GITTER_NOTIFY_ONSNATCH, GITTER_NOTIFY_ONDOWNLOAD, GITTER_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Twitter', TWITTER_NOTIFY_ONSNATCH, TWITTER_NOTIFY_ONDOWNLOAD, TWITTER_NOTIFY_ONSUBTITLEDOWNLOAD),
        ('Email', EMAIL_NOTIFY_ONSNATCH, EMAIL_NOTIFY_ONDOWNLOAD, EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD),
    ]:
        if any([onsnatch, ondownload, onsubtitledownload]):
            if onsnatch:
                new_config[notifier]['%s_notify_onsnatch' % notifier.lower()] = int(onsnatch)
            if ondownload:
                new_config[notifier]['%s_notify_ondownload' % notifier.lower()] = int(ondownload)
            if onsubtitledownload:
                new_config[notifier]['%s_notify_onsubtitledownload' % notifier.lower()] = int(onsubtitledownload)

    # remove empty stanzas
    for k in filter(lambda c: not new_config[c], cfg_keys):
        del new_config[k]

    new_config['Newznab'] = {}
    new_config['Newznab']['newznab_data'] = NEWZNAB_DATA

    torrent_rss = '!!!'.join([x.config_str() for x in torrentRssProviderList])
    if torrent_rss:
        new_config['TorrentRss'] = {}
        new_config['TorrentRss']['torrentrss_data'] = torrent_rss

    new_config['GUI'] = {}
    new_config['GUI']['gui_name'] = GUI_NAME
    new_config['GUI']['theme_name'] = THEME_NAME
    new_config['GUI']['default_home'] = DEFAULT_HOME
    new_config['GUI']['fanart_limit'] = FANART_LIMIT
    new_config['GUI']['fanart_panel'] = FANART_PANEL
    new_config['GUI']['fanart_ratings'] = '%s' % FANART_RATINGS
    new_config['GUI']['use_imdb_info'] = int(USE_IMDB_INFO)
    new_config['GUI']['imdb_accounts'] = IMDB_ACCOUNTS
    new_config['GUI']['fuzzy_dating'] = int(FUZZY_DATING)
    new_config['GUI']['trim_zero'] = int(TRIM_ZERO)
    new_config['GUI']['date_preset'] = DATE_PRESET
    new_config['GUI']['time_preset'] = TIME_PRESET_W_SECONDS
    new_config['GUI']['timezone_display'] = TIMEZONE_DISPLAY

    new_config['GUI']['show_tags'] = ','.join(SHOW_TAGS)
    new_config['GUI']['showlist_tagview'] = SHOWLIST_TAGVIEW

    new_config['GUI']['home_layout'] = HOME_LAYOUT
    new_config['GUI']['footer_time_layout'] = FOOTER_TIME_LAYOUT
    new_config['GUI']['poster_sortby'] = POSTER_SORTBY
    new_config['GUI']['poster_sortdir'] = POSTER_SORTDIR

    new_config['GUI']['display_show_viewmode'] = int(DISPLAY_SHOW_VIEWMODE)
    new_config['GUI']['display_show_background'] = int(DISPLAY_SHOW_BACKGROUND)
    new_config['GUI']['display_show_background_translucent'] = int(DISPLAY_SHOW_BACKGROUND_TRANSLUCENT)
    new_config['GUI']['display_show_viewart'] = int(DISPLAY_SHOW_VIEWART)
    new_config['GUI']['display_show_minimum'] = int(DISPLAY_SHOW_MINIMUM)
    new_config['GUI']['display_show_specials'] = int(DISPLAY_SHOW_SPECIALS)

    new_config['GUI']['episode_view_viewmode'] = int(EPISODE_VIEW_VIEWMODE)
    new_config['GUI']['episode_view_background'] = int(EPISODE_VIEW_BACKGROUND)
    new_config['GUI']['episode_view_background_translucent'] = int(EPISODE_VIEW_BACKGROUND_TRANSLUCENT)
    new_config['GUI']['episode_view_layout'] = EPISODE_VIEW_LAYOUT
    new_config['GUI']['episode_view_sort'] = EPISODE_VIEW_SORT
    new_config['GUI']['episode_view_display_paused'] = int(EPISODE_VIEW_DISPLAY_PAUSED)
    new_config['GUI']['episode_view_posters'] = int(EPISODE_VIEW_POSTERS)
    new_config['GUI']['episode_view_missed_range'] = int(EPISODE_VIEW_MISSED_RANGE)
    new_config['GUI']['poster_sortby'] = POSTER_SORTBY
    new_config['GUI']['poster_sortdir'] = POSTER_SORTDIR
    new_config['GUI']['show_tags'] = ','.join(SHOW_TAGS)
    new_config['GUI']['showlist_tagview'] = SHOWLIST_TAGVIEW
    new_config['GUI']['show_tag_default'] = SHOW_TAG_DEFAULT
    new_config['GUI']['history_layout'] = HISTORY_LAYOUT
    new_config['GUI']['browselist_hidden'] = '|~|'.join(BROWSELIST_HIDDEN)

    new_config['Subtitles'] = {}
    new_config['Subtitles']['use_subtitles'] = int(USE_SUBTITLES)
    new_config['Subtitles']['subtitles_languages'] = ','.join(SUBTITLES_LANGUAGES)
    new_config['Subtitles']['SUBTITLES_SERVICES_LIST'] = ','.join(SUBTITLES_SERVICES_LIST)
    new_config['Subtitles']['SUBTITLES_SERVICES_ENABLED'] = '|'.join([str(x) for x in SUBTITLES_SERVICES_ENABLED])
    new_config['Subtitles']['subtitles_dir'] = SUBTITLES_DIR
    new_config['Subtitles']['subtitles_default'] = int(SUBTITLES_DEFAULT)
    new_config['Subtitles']['subtitles_history'] = int(SUBTITLES_HISTORY)
    new_config['Subtitles']['subtitles_finder_frequency'] = int(SUBTITLES_FINDER_FREQUENCY)

    new_config['FailedDownloads'] = {}
    new_config['FailedDownloads']['use_failed_downloads'] = int(USE_FAILED_DOWNLOADS)
    new_config['FailedDownloads']['delete_failed'] = int(DELETE_FAILED)

    new_config['ANIDB'] = {}
    new_config['ANIDB']['use_anidb'] = int(USE_ANIDB)
    new_config['ANIDB']['anidb_username'] = ANIDB_USERNAME
    new_config['ANIDB']['anidb_password'] = helpers.encrypt(ANIDB_PASSWORD, ENCRYPTION_VERSION)
    new_config['ANIDB']['anidb_use_mylist'] = int(ANIDB_USE_MYLIST)

    new_config['ANIME'] = {}
    new_config['ANIME']['anime_treat_as_hdtv'] = int(ANIME_TREAT_AS_HDTV)

    new_config.write()


def launch_browser(start_port=None):
    if not start_port:
        start_port = WEB_PORT
    browser_url = 'http%s://localhost:%d%s' % (('s', '')[not ENABLE_HTTPS], start_port, WEB_ROOT)
    try:
        webbrowser.open(browser_url, 2, 1)
    except (StandardError, Exception):
        try:
            webbrowser.open(browser_url, 1, 1)
        except (StandardError, Exception):
            logger.log('Unable to launch a browser', logger.ERROR)

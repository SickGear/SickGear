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

import datetime
import os.path
import re

# noinspection PyPep8Naming
import encodingKludge as ek

import sickbeard
import sickbeard.providers
from . import db, helpers, logger, naming
from lib.api_trakt import TraktAPI

from _23 import filter_list, urlsplit, urlunsplit
from six import string_types


naming_ep_type = ('%(seasonnumber)dx%(episodenumber)02d',
                  's%(seasonnumber)02de%(episodenumber)02d',
                  'S%(seasonnumber)02dE%(episodenumber)02d',
                  '%(seasonnumber)02dx%(episodenumber)02d')

sports_ep_type = ('%(seasonnumber)dx%(episodenumber)02d',
                  's%(seasonnumber)02de%(episodenumber)02d',
                  'S%(seasonnumber)02dE%(episodenumber)02d',
                  '%(seasonnumber)02dx%(episodenumber)02d')

naming_ep_type_text = ('1x02', 's01e02', 'S01E02', '01x02')

naming_multi_ep_type = {0: ['-%(episodenumber)02d'] * len(naming_ep_type),
                        1: [' - %s' % x for x in naming_ep_type],
                        2: [x + '%(episodenumber)02d' for x in ('x', 'e', 'E', 'x')]}
naming_multi_ep_type_text = ('extend', 'duplicate', 'repeat')

naming_sep_type = (' - ', ' ')
naming_sep_type_text = (' - ', 'space')


def change_https_cert(https_cert):
    if '' == https_cert:
        sickbeard.HTTPS_CERT = ''
        return True

    if os.path.normpath(sickbeard.HTTPS_CERT) != os.path.normpath(https_cert):
        if helpers.make_dir(os.path.dirname(os.path.abspath(https_cert))):
            sickbeard.HTTPS_CERT = os.path.normpath(https_cert)
            logger.log(u'Changed https cert path to %s' % https_cert)
        else:
            return False

    return True


def change_https_key(https_key):
    if '' == https_key:
        sickbeard.HTTPS_KEY = ''
        return True

    if os.path.normpath(sickbeard.HTTPS_KEY) != os.path.normpath(https_key):
        if helpers.make_dir(os.path.dirname(os.path.abspath(https_key))):
            sickbeard.HTTPS_KEY = os.path.normpath(https_key)
            logger.log(u'Changed https key path to %s' % https_key)
        else:
            return False

    return True


def change_log_dir(log_dir, web_log):
    log_dir_changed = False
    abs_log_dir = os.path.normpath(os.path.join(sickbeard.DATA_DIR, log_dir))
    web_log_value = checkbox_to_value(web_log)

    if os.path.normpath(sickbeard.LOG_DIR) != abs_log_dir:
        if helpers.make_dir(abs_log_dir):
            sickbeard.ACTUAL_LOG_DIR = os.path.normpath(log_dir)
            sickbeard.LOG_DIR = abs_log_dir

            logger.sb_log_instance.init_logging()
            logger.log(u'Initialized new log file in %s' % sickbeard.LOG_DIR)
            log_dir_changed = True

        else:
            return False

    if sickbeard.WEB_LOG != web_log_value or log_dir_changed:
        sickbeard.WEB_LOG = web_log_value

    return True


def change_nzb_dir(nzb_dir):
    if '' == nzb_dir:
        sickbeard.NZB_DIR = ''
        return True

    if os.path.normpath(sickbeard.NZB_DIR) != os.path.normpath(nzb_dir):
        if helpers.make_dir(nzb_dir):
            sickbeard.NZB_DIR = os.path.normpath(nzb_dir)
            logger.log(u'Changed NZB folder to %s' % nzb_dir)
        else:
            return False

    return True


def change_torrent_dir(torrent_dir):
    if '' == torrent_dir:
        sickbeard.TORRENT_DIR = ''
        return True

    if os.path.normpath(sickbeard.TORRENT_DIR) != os.path.normpath(torrent_dir):
        if helpers.make_dir(torrent_dir):
            sickbeard.TORRENT_DIR = os.path.normpath(torrent_dir)
            logger.log(u'Changed torrent folder to %s' % torrent_dir)
        else:
            return False

    return True


def change_tv_download_dir(tv_download_dir):
    if '' == tv_download_dir:
        sickbeard.TV_DOWNLOAD_DIR = ''
        return True

    if os.path.normpath(sickbeard.TV_DOWNLOAD_DIR) != os.path.normpath(tv_download_dir):
        if helpers.make_dir(tv_download_dir):
            sickbeard.TV_DOWNLOAD_DIR = os.path.normpath(tv_download_dir)
            logger.log(u'Changed TV download folder to %s' % tv_download_dir)
        else:
            return False

    return True


def schedule_mediaprocess(iv):
    sickbeard.MEDIAPROCESS_INTERVAL = to_int(iv, default=sickbeard.DEFAULT_MEDIAPROCESS_INTERVAL)

    if sickbeard.MEDIAPROCESS_INTERVAL < sickbeard.MIN_MEDIAPROCESS_INTERVAL:
        sickbeard.MEDIAPROCESS_INTERVAL = sickbeard.MIN_MEDIAPROCESS_INTERVAL

    sickbeard.media_process_scheduler.cycleTime = datetime.timedelta(minutes=sickbeard.MEDIAPROCESS_INTERVAL)
    sickbeard.media_process_scheduler.set_paused_state()


def schedule_recentsearch(iv):
    sickbeard.RECENTSEARCH_INTERVAL = to_int(iv, default=sickbeard.DEFAULT_RECENTSEARCH_INTERVAL)

    if sickbeard.RECENTSEARCH_INTERVAL < sickbeard.MIN_RECENTSEARCH_INTERVAL:
        sickbeard.RECENTSEARCH_INTERVAL = sickbeard.MIN_RECENTSEARCH_INTERVAL

    sickbeard.recent_search_scheduler.cycleTime = datetime.timedelta(minutes=sickbeard.RECENTSEARCH_INTERVAL)


def schedule_backlog(iv):
    sickbeard.BACKLOG_PERIOD = minimax(iv, sickbeard.DEFAULT_BACKLOG_PERIOD,
                                       sickbeard.MIN_BACKLOG_PERIOD, sickbeard.MAX_BACKLOG_PERIOD)

    sickbeard.backlog_search_scheduler.action.cycleTime = sickbeard.BACKLOG_PERIOD


def schedule_update_software(iv):
    sickbeard.UPDATE_INTERVAL = to_int(iv, default=sickbeard.DEFAULT_UPDATE_INTERVAL)

    if sickbeard.UPDATE_INTERVAL < sickbeard.MIN_UPDATE_INTERVAL:
        sickbeard.UPDATE_INTERVAL = sickbeard.MIN_UPDATE_INTERVAL

    sickbeard.update_software_scheduler.cycleTime = datetime.timedelta(hours=sickbeard.UPDATE_INTERVAL)


def schedule_update_software_notify(update_notify):
    old_setting = sickbeard.UPDATE_NOTIFY

    sickbeard.UPDATE_NOTIFY = update_notify

    if not update_notify:
        sickbeard.NEWEST_VERSION_STRING = None

    if not old_setting and update_notify:
        sickbeard.update_software_scheduler.action.run()


def schedule_update_packages(iv):
    sickbeard.UPDATE_PACKAGES_INTERVAL = minimax(iv, sickbeard.DEFAULT_UPDATE_PACKAGES_INTERVAL,
                                                 sickbeard.MIN_UPDATE_PACKAGES_INTERVAL,
                                                 sickbeard.MAX_UPDATE_PACKAGES_INTERVAL)

    sickbeard.update_packages_scheduler.cycleTime = datetime.timedelta(hours=sickbeard.UPDATE_PACKAGES_INTERVAL)


def schedule_update_packages_notify(update_packages_notify):
    # this adds too much time to the save_config button click, see below
    # old_setting = sickbeard.UPDATE_PACKAGES_NOTIFY

    sickbeard.UPDATE_PACKAGES_NOTIFY = update_packages_notify

    if not update_packages_notify:
        sickbeard.NEWEST_VERSION_STRING = None

    # this adds too much time to the save_config button click,
    # also the call to save_config raises the risk of a race condition
    # user must instead restart to activate an update on startup
    # if not old_setting and update_packages_notify:
    #     sickbeard.update_packages_scheduler.action.run()


def schedule_download_propers(download_propers):
    if sickbeard.DOWNLOAD_PROPERS != download_propers:
        sickbeard.DOWNLOAD_PROPERS = download_propers
        sickbeard.proper_finder_scheduler.set_paused_state()


def schedule_trakt(use_trakt):
    if sickbeard.USE_TRAKT == use_trakt:
        return

    sickbeard.USE_TRAKT = use_trakt
    # if sickbeard.USE_TRAKT:
    #     sickbeard.trakt_checker_scheduler.start()
    # else:
    #     sickbeard.trakt_checker_scheduler.stop()
    #     logger.log(u'Waiting for the TRAKTCHECKER thread to exit')
    #     try:
    #         sickbeard.trakt_checker_scheduler.join(10)
    #     except:
    #         pass


def schedule_subtitles(use_subtitles):
    if sickbeard.USE_SUBTITLES != use_subtitles:
        sickbeard.USE_SUBTITLES = use_subtitles
        sickbeard.subtitles_finder_scheduler.set_paused_state()


def schedule_emby_watched(emby_watched_interval):
    emby_watched_iv = minimax(emby_watched_interval, sickbeard.DEFAULT_WATCHEDSTATE_INTERVAL,
                              0, sickbeard.MAX_WATCHEDSTATE_INTERVAL)
    if emby_watched_iv and emby_watched_iv != sickbeard.EMBY_WATCHEDSTATE_INTERVAL:
        sickbeard.EMBY_WATCHEDSTATE_INTERVAL = emby_watched_iv
        sickbeard.emby_watched_state_scheduler.cycleTime = datetime.timedelta(minutes=emby_watched_iv)

    sickbeard.EMBY_WATCHEDSTATE_SCHEDULED = bool(emby_watched_iv)
    sickbeard.emby_watched_state_scheduler.set_paused_state()


def schedule_plex_watched(plex_watched_interval):
    plex_watched_iv = minimax(plex_watched_interval, sickbeard.DEFAULT_WATCHEDSTATE_INTERVAL,
                              0, sickbeard.MAX_WATCHEDSTATE_INTERVAL)
    if plex_watched_iv and plex_watched_iv != sickbeard.PLEX_WATCHEDSTATE_INTERVAL:
        sickbeard.PLEX_WATCHEDSTATE_INTERVAL = plex_watched_iv
        sickbeard.plex_watched_state_scheduler.cycleTime = datetime.timedelta(minutes=plex_watched_iv)

    sickbeard.PLEX_WATCHEDSTATE_SCHEDULED = bool(plex_watched_iv)
    sickbeard.plex_watched_state_scheduler.set_paused_state()


def check_section(cfg, section):
    """ Check if INI section exists, if not create it """
    if section not in cfg:
        cfg[section] = {}
        return False
    return True


def checkbox_to_value(option, value_on=1, value_off=0):
    """
    Turns checkbox option 'on' or 'true' to value_on (1)
    any other value returns value_off (0)
    """

    if type(option) is list:
        option = option[-1]

    if 'on' == option or 'true' == option:
        return value_on

    return value_off


def clean_host(host, default_port=None, allow_base=False):
    """
    Returns host or host:port or empty string from a given url or host
    If no port is found and default_port is given use host:default_port
    """

    host = host.strip()

    if host:

        match_host_port = re.search(r'(?:http.*://)?(?P<host>[^:/]+).?(?P<port>(?<!/)[0-9]*)(?P<base>.*)', host)

        cleaned_host = match_host_port.group('host')
        cleaned_port = match_host_port.group('port')
        if allow_base:
            cleaned_base = match_host_port.group('base')
        else:
            cleaned_base = ''

        if cleaned_host:

            if cleaned_port:
                host = '%s:%s%s' % (cleaned_host, cleaned_port, cleaned_base)

            elif default_port:
                host = '%s:%s%s' % (cleaned_host, default_port, cleaned_base)

            else:
                host = '%s%s' % (cleaned_host, cleaned_base)

        else:
            host = ''

    return host


def clean_hosts(hosts, default_port=None, allow_base=False):
    cleaned_hosts = []

    for cur_host in [host.strip() for host in hosts.split(',')]:
        if cur_host:
            cleaned_host = clean_host(cur_host, default_port, allow_base=allow_base)
            if cleaned_host:
                cleaned_hosts.append(cleaned_host)

    if cleaned_hosts:
        cleaned_hosts = ','.join(cleaned_hosts)

    else:
        cleaned_hosts = ''

    return cleaned_hosts


def clean_url(url, add_slash=True):
    """ Returns an cleaned url starting with a scheme and folder with trailing '/' or an empty string """

    if url and url.strip():

        url = url.strip()

        if '://' not in url:
            url = '//' + url

        scheme, netloc, path, query, fragment = urlsplit(url, 'http')

        if not path.endswith('/'):
            basename, ext = ek.ek(os.path.splitext, ek.ek(os.path.basename, path))
            if not ext and add_slash:
                path += '/'

        cleaned_url = urlunsplit((scheme, netloc, path, query, fragment))

    else:
        cleaned_url = ''

    return cleaned_url


def kv_csv(data, default=''):
    """
    Returns a cleansed CSV string of key value pairs
    Elements must have one '=' in order to be returned
    Elements are stripped of leading/trailing whitespace but may contain whitespace (e.g. "tv shows")
    """
    if not isinstance(data, string_types):
        return default

    return ','.join(['='.join([i.strip() for i in i.split('=')]) for i in data.split(',')
                     if 1 == len(re.findall('=', i)) and all(i.replace(' ', '').split('='))])


def to_int(val, default=0):
    """ Return int value of val or default on error """

    try:
        val = int(val)
    except (BaseException, Exception):
        val = default

    return val


def minimax(val, default, low, high):
    """ Return value forced within range """

    val = to_int(val, default=default)

    if val < low:
        return low
    if val > high:
        return high

    return val


def check_setting_int(config, cfg_name, item_name, def_val):
    try:
        my_val = int(config[cfg_name][item_name])
    except (BaseException, Exception):
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except (BaseException, Exception):
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val
    logger.log('%s -> %s' % (item_name, my_val), logger.DEBUG)
    return my_val


def check_setting_float(config, cfg_name, item_name, def_val):
    try:
        my_val = float(config[cfg_name][item_name])
    except (BaseException, Exception):
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except (BaseException, Exception):
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val

    logger.log('%s -> %s' % (item_name, my_val), logger.DEBUG)
    return my_val


def check_setting_str(config, cfg_name, item_name, def_val, log=True):
    """
    For passwords you must include the word `password` in the item_name and
    add `helpers.encrypt(ITEM_NAME, ENCRYPTION_VERSION)` in save_config()
    """

    if bool(item_name.find('password') + 1):
        log = False
        encryption_version = sickbeard.ENCRYPTION_VERSION
    else:
        encryption_version = 0

    try:
        my_val = helpers.decrypt(config[cfg_name][item_name], encryption_version)
    except (BaseException, Exception):
        my_val = def_val
        try:
            config[cfg_name][item_name] = helpers.encrypt(my_val, encryption_version)
        except (BaseException, Exception):
            config[cfg_name] = {}
            config[cfg_name][item_name] = helpers.encrypt(my_val, encryption_version)

    if log:
        logger.log('%s -> %s' % (item_name, my_val), logger.DEBUG)
    else:
        logger.log('%s -> ******' % item_name, logger.DEBUG)

    return (my_val, def_val)['None' == my_val]


class ConfigMigrator(object):
    def __init__(self, config_obj):
        """
        Initializes a config migrator that can take the config from the version indicated in the config
        file up to the version required by SG
        """

        self.config_obj = config_obj

        # check the version of the config
        self.config_version = check_setting_int(config_obj, 'General', 'config_version', sickbeard.CONFIG_VERSION)
        self.expected_config_version = sickbeard.CONFIG_VERSION
        self.migration_names = {1: 'Custom naming',
                                2: 'Sync backup number with version number',
                                3: 'Rename omgwtfnzb variables',
                                4: 'Add newznab cat_ids',
                                5: 'Metadata update',
                                6: 'Rename daily search to recent search',
                                7: 'Rename coming episodes to episode view',
                                8: 'Disable searches on start',
                                9: 'Rename pushbullet variables',
                                10: 'Reset backlog interval to default',
                                11: 'Migrate anime split view to new layout',
                                12: 'Add "hevc" and some non-english languages to ignore words if not found',
                                13: 'Change default dereferrer url to blank',
                                14: 'Convert Trakt to multi-account',
                                15: 'Transmithe.net rebranded Nebulance',
                                16: 'Purge old cache image folders',
                                17: 'Add "vp9", "av1" to ignore words if not found',
                                18: 'Update "Spanish" ignore word',
                                19: 'Change (mis)use of Anonymous redirect dereferer.org service to nullrefer.com',
                                20: 'Change Growl',
                                21: 'Rename vars misusing frequency',
                                22: 'Change Anonymous redirect',
                                }

    def migrate_config(self):
        """ Calls each successive migration until the config is the same version as SG expects """

        if self.config_version > self.expected_config_version:
            logger.log_error_and_exit(
                u'Your config version (%s) has been incremented past what this version of SickGear supports (%s).\n'
                'If you have used other forks or a newer version of SickGear, your config file may be unusable due to '
                'their modifications.' % (self.config_version, self.expected_config_version))

        sickbeard.CONFIG_VERSION = self.config_version

        while self.config_version < self.expected_config_version:
            next_version = self.config_version + 1

            if next_version in self.migration_names:
                migration_name = ': %s' % self.migration_names[next_version]
            else:
                migration_name = ''

            logger.log(u'Backing up config before upgrade')
            if not helpers.backup_versioned_file(sickbeard.CONFIG_FILE, self.config_version):
                logger.log_error_and_exit(u'Config backup failed, abort upgrading config')
            else:
                logger.log(u'Proceeding with upgrade')

            # do the migration, expect a method named _migrate_v<num>
            logger.log(u'Migrating config up to version %s %s' % (next_version, migration_name))
            getattr(self, '_migrate_v%s' % next_version)()
            self.config_version = next_version

            # save new config after migration
            sickbeard.CONFIG_VERSION = self.config_version
            logger.log(u'Saving config file to disk')
            sickbeard.save_config()

    @staticmethod
    def deprecate_anon_service():
        """
        Change deprecated anon redirect service URLs
        """
        if re.search(r'https?://(?:nullrefer.com|dereferer.org)', sickbeard.ANON_REDIRECT):
            sickbeard.ANON_REDIRECT = r'https://anonymz.com/?'

    # Migration v1: Custom naming
    def _migrate_v1(self):
        """
        Reads in the old naming settings from your config and generates a new config template from them.
        """

        sickbeard.NAMING_PATTERN = self._name_to_pattern()
        logger.log('Based on your old settings I am setting your new naming pattern to: %s' % sickbeard.NAMING_PATTERN)

        sickbeard.NAMING_CUSTOM_ABD = bool(check_setting_int(self.config_obj, 'General', 'naming_dates', 0))

        if sickbeard.NAMING_CUSTOM_ABD:
            sickbeard.NAMING_ABD_PATTERN = self._name_to_pattern(True)
            logger.log('Adding a custom air-by-date naming pattern to your config: %s' % sickbeard.NAMING_ABD_PATTERN)
        else:
            sickbeard.NAMING_ABD_PATTERN = naming.name_abd_presets[0]

        sickbeard.NAMING_MULTI_EP = int(check_setting_int(self.config_obj, 'General', 'naming_multi_ep_type', 1))

        # see if any of their shows used season folders
        my_db = db.DBConnection()
        season_folder_shows = my_db.select('SELECT * FROM tv_shows WHERE flatten_folders = 0')

        # if any shows had season folders on then prepend season folder to the pattern
        if season_folder_shows:

            old_season_format = check_setting_str(self.config_obj, 'General', 'season_folders_format', 'Season %02d')

            if old_season_format:
                try:
                    new_season_format = old_season_format % 9
                    new_season_format = str(new_season_format).replace('09', '%0S')
                    new_season_format = new_season_format.replace('9', '%S')

                    logger.log(u'Changed season folder format from %s to %s, prepending it to your naming config' %
                               (old_season_format, new_season_format))
                    sickbeard.NAMING_PATTERN = new_season_format + os.sep + sickbeard.NAMING_PATTERN

                except (TypeError, ValueError):
                    logger.log(u'Can not change %s to new season format' % old_season_format, logger.ERROR)

        # if no shows had it on then don't flatten any shows and don't put season folders in the config
        else:

            logger.log(u'No shows were using season folders before so I am disabling flattening on all shows')

            # don't flatten any shows at all
            my_db.action('UPDATE tv_shows SET flatten_folders = 0 WHERE 1=1')

        sickbeard.NAMING_FORCE_FOLDERS = naming.check_force_season_folders()

    def _name_to_pattern(self, abd=False):

        # get the old settings from the file
        use_periods = bool(check_setting_int(self.config_obj, 'General', 'naming_use_periods', 0))
        ep_type = check_setting_int(self.config_obj, 'General', 'naming_ep_type', 0)
        sep_type = check_setting_int(self.config_obj, 'General', 'naming_sep_type', 0)
        use_quality = bool(check_setting_int(self.config_obj, 'General', 'naming_quality', 0))

        use_show_name = bool(check_setting_int(self.config_obj, 'General', 'naming_show_name', 1))
        use_ep_name = bool(check_setting_int(self.config_obj, 'General', 'naming_ep_name', 1))

        # make the presets into templates
        naming_ep_tmpl = ('%Sx%0E',
                          's%0Se%0E',
                          'S%0SE%0E',
                          '%0Sx%0E')
        naming_sep_tmpl = (' - ', ' ')

        # set up our data to use
        if use_periods:
            show_name = '%S.N'
            ep_name = '%E.N'
            ep_quality = '%Q.N'
            abd_string = '%A.D'
        else:
            show_name = '%SN'
            ep_name = '%EN'
            ep_quality = '%QN'
            abd_string = '%A-D'

        if abd:
            ep_string = abd_string
        else:
            ep_string = naming_ep_tmpl[ep_type]

        final_name = ''

        # start with the show name
        if use_show_name:
            final_name += show_name + naming_sep_tmpl[sep_type]

        # add the season/ep stuff
        final_name += ep_string

        # add the episode name
        if use_ep_name:
            final_name += naming_sep_tmpl[sep_type] + ep_name

        # add the quality
        if use_quality:
            final_name += naming_sep_tmpl[sep_type] + ep_quality

        if use_periods:
            final_name = re.sub(r'\s+', '.', final_name)

        return final_name

    # Migration v2: Dummy migration to sync backup number with config version number
    def _migrate_v2(self):
        return

    # Migration v2: Rename omgwtfnzb variables
    def _migrate_v3(self):
        """
        Reads in the old naming settings from your config and generates a new config template from them.
        """
        # get the old settings from the file and store them in the new variable names
        for prov in [curProvider for curProvider in sickbeard.providers.sortedProviderList()
                     if 'omgwtfnzbs' == curProvider.name]:
            prov.username = check_setting_str(self.config_obj, 'omgwtfnzbs', 'omgwtfnzbs_uid', '')
            prov.api_key = check_setting_str(self.config_obj, 'omgwtfnzbs', 'omgwtfnzbs_key', '')

    # Migration v4: Add default newznab cat_ids
    def _migrate_v4(self):
        """ Update newznab providers so that the category IDs can be set independently via the config """

        new_newznab_data = []
        old_newznab_data = check_setting_str(self.config_obj, 'Newznab', 'newznab_data', '')

        if old_newznab_data:
            old_newznab_data_list = old_newznab_data.split('!!!')

            for cur_provider_data in old_newznab_data_list:
                try:
                    name, url, key, enabled = cur_provider_data.split('|')
                except ValueError:
                    logger.log(u'Skipping Newznab provider string: "%s", incorrect format' % cur_provider_data,
                               logger.ERROR)
                    continue

                if 'Sick Beard Index' == name:
                    key = '0'

                cat_ids = '5030,5040,5060'
                # if name == 'NZBs.org':
                #     cat_ids = '5030,5040,5060,5070,5090'

                cur_provider_data_list = [name, url, key, cat_ids, enabled]
                new_newznab_data.append('|'.join(cur_provider_data_list))

            sickbeard.NEWZNAB_DATA = '!!!'.join(new_newznab_data)

    # Migration v5: Metadata upgrade
    def _migrate_v5(self):
        """ Updates metadata values to the new format

        Quick overview of what the upgrade does:

        new | old | description (new)
        ----+-----+--------------------
          1 |  1  | show metadata
          2 |  2  | episode metadata
          3 |  4  | show fanart
          4 |  3  | show poster
          5 |  -  | show banner
          6 |  5  | episode thumb
          7 |  6  | season poster
          8 |  -  | season banner
          9 |  -  | season all poster
         10 |  -  | season all banner

        Note that the ini places start at 1 while the list index starts at 0.
        old format: 0|0|0|0|0|0 -- 6 places
        new format: 0|0|0|0|0|0|0|0|0|0 -- 10 places

        Drop the use of use_banner option.
        Migrate the poster override to just using the banner option (applies to xbmc only).
        """

        metadata_xbmc = check_setting_str(self.config_obj, 'General', 'metadata_xbmc', '0|0|0|0|0|0')
        metadata_xbmc_12plus = check_setting_str(self.config_obj, 'General', 'metadata_xbmc_12plus', '0|0|0|0|0|0')
        metadata_mediabrowser = check_setting_str(self.config_obj, 'General', 'metadata_mediabrowser', '0|0|0|0|0|0')
        metadata_ps3 = check_setting_str(self.config_obj, 'General', 'metadata_ps3', '0|0|0|0|0|0')
        metadata_wdtv = check_setting_str(self.config_obj, 'General', 'metadata_wdtv', '0|0|0|0|0|0')
        metadata_tivo = check_setting_str(self.config_obj, 'General', 'metadata_tivo', '0|0|0|0|0|0')
        metadata_mede8er = check_setting_str(self.config_obj, 'General', 'metadata_mede8er', '0|0|0|0|0|0')
        metadata_kodi = check_setting_str(self.config_obj, 'General', 'metadata_kodi', '0|0|0|0|0|0')

        use_banner = bool(check_setting_int(self.config_obj, 'General', 'use_banner', 0))

        def _migrate_metadata(metadata, metadata_name, banner):
            cur_metadata = metadata.split('|')
            # if target has the old number of values, do upgrade
            if 6 == len(cur_metadata):
                logger.log(u'Upgrading ' + metadata_name + ' metadata, old value: ' + metadata)
                cur_metadata.insert(4, '0')
                cur_metadata.append('0')
                cur_metadata.append('0')
                cur_metadata.append('0')
                # swap show fanart, show poster
                cur_metadata[3], cur_metadata[2] = cur_metadata[2], cur_metadata[3]
                # if user was using banner to override the poster,
                # instead enable the banner option and deactivate poster
                if 'XBMC' == metadata_name and banner:
                    cur_metadata[4], cur_metadata[3] = cur_metadata[3], '0'
                # write new format
                metadata = '|'.join(cur_metadata)
                logger.log(u'Upgrading %s metadata, new value: %s' % (metadata_name, metadata))

            elif 10 == len(cur_metadata):
                metadata = '|'.join(cur_metadata)
                logger.log(u'Keeping %s metadata, value: %s' % (metadata_name, metadata))
            else:
                logger.log(u'Skipping %s: "%s", incorrect format' % (metadata_name, metadata), logger.ERROR)
                metadata = '0|0|0|0|0|0|0|0|0|0'
                logger.log(u'Setting %s metadata, new value: %s' % (metadata_name, metadata))

            return metadata

        sickbeard.METADATA_XBMC = _migrate_metadata(metadata_xbmc, 'XBMC', use_banner)
        sickbeard.METADATA_XBMC_12PLUS = _migrate_metadata(metadata_xbmc_12plus, 'XBMC 12+', use_banner)
        sickbeard.METADATA_MEDIABROWSER = _migrate_metadata(metadata_mediabrowser, 'MediaBrowser', use_banner)
        sickbeard.METADATA_PS3 = _migrate_metadata(metadata_ps3, 'PS3', use_banner)
        sickbeard.METADATA_WDTV = _migrate_metadata(metadata_wdtv, 'WDTV', use_banner)
        sickbeard.METADATA_TIVO = _migrate_metadata(metadata_tivo, 'TIVO', use_banner)
        sickbeard.METADATA_MEDE8ER = _migrate_metadata(metadata_mede8er, 'Mede8er', use_banner)
        sickbeard.METADATA_KODI = _migrate_metadata(metadata_kodi, 'Kodi', use_banner)

    # Migration v6: Rename daily search to recent search
    def _migrate_v6(self):
        sickbeard.RECENTSEARCH_INTERVAL = check_setting_int(self.config_obj, 'General', 'dailysearch_frequency',
                                                            sickbeard.DEFAULT_RECENTSEARCH_INTERVAL)

        sickbeard.RECENTSEARCH_STARTUP = bool(check_setting_int(self.config_obj, 'General', 'dailysearch_startup', 1))
        if sickbeard.RECENTSEARCH_INTERVAL < sickbeard.MIN_RECENTSEARCH_INTERVAL:
            sickbeard.RECENTSEARCH_INTERVAL = sickbeard.MIN_RECENTSEARCH_INTERVAL

        for curProvider in sickbeard.providers.sortedProviderList():
            if hasattr(curProvider, 'enable_recentsearch'):
                curProvider.enable_recentsearch = bool(check_setting_int(
                    self.config_obj, curProvider.get_id().upper(), curProvider.get_id() + '_enable_dailysearch', 1))

    def _migrate_v7(self):
        sickbeard.EPISODE_VIEW_LAYOUT = check_setting_str(self.config_obj, 'GUI', 'coming_eps_layout', 'banner')
        sickbeard.EPISODE_VIEW_SORT = check_setting_str(self.config_obj, 'GUI', 'coming_eps_sort', 'time')
        if 'date' == sickbeard.EPISODE_VIEW_SORT:
            sickbeard.EPISODE_VIEW_SORT = 'time'
        sickbeard.EPISODE_VIEW_DISPLAY_PAUSED = (
            check_setting_int(self.config_obj, 'GUI', 'coming_eps_display_paused', 0))
        sickbeard.EPISODE_VIEW_MISSED_RANGE = check_setting_int(self.config_obj, 'GUI', 'coming_eps_missed_range', 7)

    @staticmethod
    def _migrate_v8():
        # removing settings from gui and making it a hidden debug option
        sickbeard.RECENTSEARCH_STARTUP = False

    def _migrate_v9(self):
        sickbeard.PUSHBULLET_ACCESS_TOKEN = check_setting_str(self.config_obj, 'Pushbullet', 'pushbullet_api', '')
        sickbeard.PUSHBULLET_DEVICE_IDEN = check_setting_str(self.config_obj, 'Pushbullet', 'pushbullet_device', '')

    @staticmethod
    def _migrate_v10():
        # reset backlog interval to default
        sickbeard.BACKLOG_PERIOD = sickbeard.DEFAULT_BACKLOG_PERIOD

    def _migrate_v11(self):
        if check_setting_int(self.config_obj, 'ANIME', 'anime_split_home', ''):
            sickbeard.SHOWLIST_TAGVIEW = 'anime'
        else:
            sickbeard.SHOWLIST_TAGVIEW = 'default'

    def _migrate_v12(self):
        # add words to ignore list and insert spaces to improve the ui config readability
        words_to_add = ['hevc', 'reenc', 'x265', 'danish', 'deutsch', 'flemish', 'italian',
                        'nordic', 'norwegian', 'portuguese', 'spanish', 'turkish']
        self.add_ignore_words(words_to_add)

    def _migrate_v13(self):
        self.deprecate_anon_service()

    def _migrate_v14(self):
        old_token = check_setting_str(self.config_obj, 'Trakt', 'trakt_token', '')
        old_refresh_token = check_setting_str(self.config_obj, 'Trakt', 'trakt_refresh_token', '')
        if old_token and old_refresh_token:
            TraktAPI.add_account(old_token, old_refresh_token, None)

    # Migration v15: Transmithe.net variables
    def _migrate_v15(self):
        try:
            neb = filter_list(lambda p: 'Nebulance' in p.name, sickbeard.providers.sortedProviderList())[0]
        except (BaseException, Exception):
            return
        # get the old settings from the file and store them in the new variable names
        old_id = 'transmithe_net'
        old_id_uc = old_id.upper()
        neb.enabled = bool(check_setting_int(self.config_obj, old_id_uc, old_id, 0))
        setattr(neb, 'username', check_setting_str(self.config_obj, old_id_uc, old_id + '_username', ''))
        neb.password = check_setting_str(self.config_obj, old_id_uc, old_id + '_password', '')
        neb.minseed = check_setting_int(self.config_obj, old_id_uc, old_id + '_minseed', 0)
        neb.minleech = check_setting_int(self.config_obj, old_id_uc, old_id + '_minleech', 0)
        neb.freeleech = bool(check_setting_int(self.config_obj, old_id_uc, old_id + '_freeleech', 0))
        neb.enable_recentsearch = bool(check_setting_int(
            self.config_obj, old_id_uc, old_id + '_enable_recentsearch', 1)) or not getattr(neb, 'supports_backlog')
        neb.enable_backlog = bool(check_setting_int(self.config_obj, old_id_uc, old_id + '_enable_backlog', 1))
        neb.search_mode = check_setting_str(self.config_obj, old_id_uc, old_id + '_search_mode', 'eponly')
        neb.search_fallback = bool(check_setting_int(self.config_obj, old_id_uc, old_id + '_search_fallback', 0))
        neb.seed_time = check_setting_int(self.config_obj, old_id_uc, old_id + '_seed_time', '')
        neb._seed_ratio = check_setting_str(self.config_obj, old_id_uc, old_id + '_seed_ratio', '')

    # Migration v16: Purge old cache image folder name
    @staticmethod
    def _migrate_v16():
        if sickbeard.CACHE_DIR and ek.ek(os.path.isdir, sickbeard.CACHE_DIR):
            cache_default = sickbeard.CACHE_DIR
            dead_paths = ['anidb', 'imdb', 'trakt']
            for path in dead_paths:
                sickbeard.CACHE_DIR = '%s/images/%s' % (cache_default, path)
                helpers.clear_cache(True)
                try:
                    ek.ek(os.rmdir, sickbeard.CACHE_DIR)
                except OSError:
                    pass
            sickbeard.CACHE_DIR = cache_default

    @staticmethod
    def add_ignore_words(wordlist, removelist=None):
        # add words to ignore list and insert spaces to improve the ui config readability
        if not isinstance(wordlist, list):
            wordlist = [wordlist]
        if not isinstance(removelist, list):
            removelist = ([removelist], [])[None is removelist]

        new_list = set()
        dedupe = []
        using_regex = False
        for ignore_word in list(sickbeard.IGNORE_WORDS) + wordlist:  # words:
            word = ignore_word.strip()
            if word.startswith('regex:'):
                word = word.lstrip('regex:').strip()
                using_regex = True  # 'regex:'
            if word:
                check_word = word.lower()
                if check_word not in dedupe and check_word not in removelist:
                    dedupe += [check_word]
                    if 'spanish' in check_word:
                        word = re.sub(r'(?i)(portuguese)\|spanish(\|swedish)', r'\1\2', word)
                    new_list.add(word)

        sickbeard.IGNORE_WORDS = new_list
        sickbeard.IGNORE_WORDS_REGEX = using_regex

    def _migrate_v17(self):

        self.add_ignore_words(['vp9', 'av1'])

    def _migrate_v18(self):

        self.add_ignore_words([r'regex:^(?=.*?\bspanish\b)((?!spanish.?princess).)*$'], ['spanish'])

    def _migrate_v19(self):
        self.deprecate_anon_service()

    def _migrate_v20(self):
        growl_host = check_setting_str(self.config_obj, 'Growl', 'growl_host', '')
        growl_password = check_setting_str(self.config_obj, 'Growl', 'growl_password', '')
        if growl_password:
            sickbeard.GROWL_HOST = '%s@%s' % (growl_password, growl_host)

    def _migrate_v21(self):
        sickbeard.MEDIAPROCESS_INTERVAL = check_setting_int(
            self.config_obj, 'General', 'autopostprocesser_frequency', sickbeard.DEFAULT_MEDIAPROCESS_INTERVAL)
        sickbeard.BACKLOG_PERIOD = check_setting_int(
            self.config_obj, 'General', 'backlog_frequency', sickbeard.DEFAULT_BACKLOG_PERIOD)
        sickbeard.BACKLOG_LIMITED_PERIOD = check_setting_int(self.config_obj, 'General', 'backlog_days', 7)
        sickbeard.RECENTSEARCH_INTERVAL = check_setting_int(
            self.config_obj, 'General', 'recentsearch_frequency', sickbeard.DEFAULT_RECENTSEARCH_INTERVAL)
        sickbeard.UPDATE_INTERVAL = check_setting_int(
            self.config_obj, 'General', 'update_frequency', sickbeard.DEFAULT_UPDATE_INTERVAL)

        sickbeard.EMBY_WATCHEDSTATE_INTERVAL = minimax(check_setting_int(
            self.config_obj, 'Emby', 'emby_watchedstate_frequency', sickbeard.DEFAULT_WATCHEDSTATE_INTERVAL),
            sickbeard.DEFAULT_WATCHEDSTATE_INTERVAL, sickbeard.MIN_WATCHEDSTATE_INTERVAL,
            sickbeard.MAX_WATCHEDSTATE_INTERVAL)
        sickbeard.PLEX_WATCHEDSTATE_INTERVAL = minimax(check_setting_int(
            self.config_obj, 'Plex', 'plex_watchedstate_frequency', sickbeard.DEFAULT_WATCHEDSTATE_INTERVAL),
            sickbeard.DEFAULT_WATCHEDSTATE_INTERVAL, sickbeard.MIN_WATCHEDSTATE_INTERVAL,
            sickbeard.MAX_WATCHEDSTATE_INTERVAL)

        sickbeard.SUBTITLES_FINDER_INTERVAL = check_setting_int(
            self.config_obj, 'Subtitles', 'subtitles_finder_frequency', 1)

    def _migrate_v22(self):
        self.deprecate_anon_service()

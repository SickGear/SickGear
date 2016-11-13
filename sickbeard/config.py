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

import os.path
import datetime
import re
import urlparse

import sickbeard
import sickbeard.providers
from sickbeard import encodingKludge as ek
from sickbeard import helpers, logger, naming, db
from lib.libtrakt import TraktAPI


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


def change_HTTPS_CERT(https_cert):
    if https_cert == '':
        sickbeard.HTTPS_CERT = ''
        return True

    if os.path.normpath(sickbeard.HTTPS_CERT) != os.path.normpath(https_cert):
        if helpers.makeDir(os.path.dirname(os.path.abspath(https_cert))):
            sickbeard.HTTPS_CERT = os.path.normpath(https_cert)
            logger.log(u'Changed https cert path to %s' % https_cert)
        else:
            return False

    return True


def change_HTTPS_KEY(https_key):
    if https_key == '':
        sickbeard.HTTPS_KEY = ''
        return True

    if os.path.normpath(sickbeard.HTTPS_KEY) != os.path.normpath(https_key):
        if helpers.makeDir(os.path.dirname(os.path.abspath(https_key))):
            sickbeard.HTTPS_KEY = os.path.normpath(https_key)
            logger.log(u'Changed https key path to %s' % https_key)
        else:
            return False

    return True


def change_LOG_DIR(log_dir, web_log):
    log_dir_changed = False
    abs_log_dir = os.path.normpath(os.path.join(sickbeard.DATA_DIR, log_dir))
    web_log_value = checkbox_to_value(web_log)

    if os.path.normpath(sickbeard.LOG_DIR) != abs_log_dir:
        if helpers.makeDir(abs_log_dir):
            sickbeard.ACTUAL_LOG_DIR = os.path.normpath(log_dir)
            sickbeard.LOG_DIR = abs_log_dir

            logger.sb_log_instance.initLogging()
            logger.log(u'Initialized new log file in %s' % sickbeard.LOG_DIR)
            log_dir_changed = True

        else:
            return False

    if sickbeard.WEB_LOG != web_log_value or log_dir_changed:
        sickbeard.WEB_LOG = web_log_value

    return True


def change_NZB_DIR(nzb_dir):
    if nzb_dir == '':
        sickbeard.NZB_DIR = ''
        return True

    if os.path.normpath(sickbeard.NZB_DIR) != os.path.normpath(nzb_dir):
        if helpers.makeDir(nzb_dir):
            sickbeard.NZB_DIR = os.path.normpath(nzb_dir)
            logger.log(u'Changed NZB folder to %s' % nzb_dir)
        else:
            return False

    return True


def change_TORRENT_DIR(torrent_dir):
    if torrent_dir == '':
        sickbeard.TORRENT_DIR = ''
        return True

    if os.path.normpath(sickbeard.TORRENT_DIR) != os.path.normpath(torrent_dir):
        if helpers.makeDir(torrent_dir):
            sickbeard.TORRENT_DIR = os.path.normpath(torrent_dir)
            logger.log(u'Changed torrent folder to %s' % torrent_dir)
        else:
            return False

    return True


def change_TV_DOWNLOAD_DIR(tv_download_dir):
    if tv_download_dir == '':
        sickbeard.TV_DOWNLOAD_DIR = ''
        return True

    if os.path.normpath(sickbeard.TV_DOWNLOAD_DIR) != os.path.normpath(tv_download_dir):
        if helpers.makeDir(tv_download_dir):
            sickbeard.TV_DOWNLOAD_DIR = os.path.normpath(tv_download_dir)
            logger.log(u'Changed TV download folder to %s' % tv_download_dir)
        else:
            return False

    return True


def change_AUTOPOSTPROCESSER_FREQUENCY(freq):
    sickbeard.AUTOPOSTPROCESSER_FREQUENCY = to_int(freq, default=sickbeard.DEFAULT_AUTOPOSTPROCESSER_FREQUENCY)

    if sickbeard.AUTOPOSTPROCESSER_FREQUENCY < sickbeard.MIN_AUTOPOSTPROCESSER_FREQUENCY:
        sickbeard.AUTOPOSTPROCESSER_FREQUENCY = sickbeard.MIN_AUTOPOSTPROCESSER_FREQUENCY

    sickbeard.autoPostProcesserScheduler.cycleTime = datetime.timedelta(minutes=sickbeard.AUTOPOSTPROCESSER_FREQUENCY)


def change_RECENTSEARCH_FREQUENCY(freq):
    sickbeard.RECENTSEARCH_FREQUENCY = to_int(freq, default=sickbeard.DEFAULT_RECENTSEARCH_FREQUENCY)

    if sickbeard.RECENTSEARCH_FREQUENCY < sickbeard.MIN_RECENTSEARCH_FREQUENCY:
        sickbeard.RECENTSEARCH_FREQUENCY = sickbeard.MIN_RECENTSEARCH_FREQUENCY

    sickbeard.recentSearchScheduler.cycleTime = datetime.timedelta(minutes=sickbeard.RECENTSEARCH_FREQUENCY)


def change_BACKLOG_FREQUENCY(freq):
    sickbeard.BACKLOG_FREQUENCY = minimax(freq, sickbeard.DEFAULT_BACKLOG_FREQUENCY, sickbeard.MIN_BACKLOG_FREQUENCY, sickbeard.MAX_BACKLOG_FREQUENCY)

    sickbeard.backlogSearchScheduler.action.cycleTime = sickbeard.BACKLOG_FREQUENCY


def change_UPDATE_FREQUENCY(freq):
    sickbeard.UPDATE_FREQUENCY = to_int(freq, default=sickbeard.DEFAULT_UPDATE_FREQUENCY)

    if sickbeard.UPDATE_FREQUENCY < sickbeard.MIN_UPDATE_FREQUENCY:
        sickbeard.UPDATE_FREQUENCY = sickbeard.MIN_UPDATE_FREQUENCY

    sickbeard.versionCheckScheduler.cycleTime = datetime.timedelta(hours=sickbeard.UPDATE_FREQUENCY)


def change_VERSION_NOTIFY(version_notify):
    oldSetting = sickbeard.VERSION_NOTIFY

    sickbeard.VERSION_NOTIFY = version_notify

    if not version_notify:
        sickbeard.NEWEST_VERSION_STRING = None

    if not oldSetting and version_notify:
        sickbeard.versionCheckScheduler.action.run()


def change_DOWNLOAD_PROPERS(download_propers):
    if sickbeard.DOWNLOAD_PROPERS == download_propers:
        return

    sickbeard.DOWNLOAD_PROPERS = download_propers
    if sickbeard.DOWNLOAD_PROPERS:
        sickbeard.properFinderScheduler.start()
    else:
        sickbeard.properFinderScheduler.stop.set()
        logger.log(u'Waiting for the PROPERFINDER thread to exit')
        try:
            sickbeard.properFinderScheduler.join(10)
        except:
            pass


def change_USE_TRAKT(use_trakt):
    if sickbeard.USE_TRAKT == use_trakt:
        return

    sickbeard.USE_TRAKT = use_trakt
    # if sickbeard.USE_TRAKT:
    #     sickbeard.traktCheckerScheduler.start()
    # else:
    #     sickbeard.traktCheckerScheduler.stop.set()
    #     logger.log(u'Waiting for the TRAKTCHECKER thread to exit')
    #     try:
    #         sickbeard.traktCheckerScheduler.join(10)
    #     except:
    #         pass


def change_USE_SUBTITLES(use_subtitles):
    if sickbeard.USE_SUBTITLES == use_subtitles:
        return

    sickbeard.USE_SUBTITLES = use_subtitles
    if sickbeard.USE_SUBTITLES:
        sickbeard.subtitlesFinderScheduler.start()
    else:
        sickbeard.subtitlesFinderScheduler.stop.set()
        logger.log(u'Waiting for the SUBTITLESFINDER thread to exit')
        try:
            sickbeard.subtitlesFinderScheduler.join(10)
        except:
            pass


def CheckSection(CFG, sec):
    """ Check if INI section exists, if not create it """
    try:
        CFG[sec]
        return True
    except:
        CFG[sec] = {}
        return False


def checkbox_to_value(option, value_on=1, value_off=0):
    """
    Turns checkbox option 'on' or 'true' to value_on (1)
    any other value returns value_off (0)
    """

    if type(option) is list:
        option = option[-1]

    if option == 'on' or option == 'true':
        return value_on

    return value_off


def clean_host(host, default_port=None):
    """
    Returns host or host:port or empty string from a given url or host
    If no port is found and default_port is given use host:default_port
    """

    host = host.strip()

    if host:

        match_host_port = re.search(r'(?:http.*://)?(?P<host>[^:/]+).?(?P<port>[0-9]*).*', host)

        cleaned_host = match_host_port.group('host')
        cleaned_port = match_host_port.group('port')

        if cleaned_host:

            if cleaned_port:
                host = '%s:%s' % (cleaned_host, cleaned_port)

            elif default_port:
                host = '%s:%s' % (cleaned_host, default_port)

            else:
                host = cleaned_host

        else:
            host = ''

    return host


def clean_hosts(hosts, default_port=None):
    cleaned_hosts = []

    for cur_host in [x.strip() for x in hosts.split(',')]:
        if cur_host:
            cleaned_host = clean_host(cur_host, default_port)
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

        scheme, netloc, path, query, fragment = urlparse.urlsplit(url, 'http')

        if not path.endswith('/'):
            basename, ext = ek.ek(os.path.splitext, ek.ek(os.path.basename, path))
            if not ext and add_slash:
                path += '/'

        cleaned_url = urlparse.urlunsplit((scheme, netloc, path, query, fragment))

    else:
        cleaned_url = ''

    return cleaned_url


def to_int(val, default=0):
    """ Return int value of val or default on error """

    try:
        val = int(val)
    except:
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
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val
    logger.log('%s -> %s' % (item_name, my_val), logger.DEBUG)
    return my_val


def check_setting_float(config, cfg_name, item_name, def_val):
    try:
        my_val = float(config[cfg_name][item_name])
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except:
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
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = helpers.encrypt(my_val, encryption_version)
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = helpers.encrypt(my_val, encryption_version)

    if log:
        logger.log('%s -> %s' % (item_name, my_val), logger.DEBUG)
    else:
        logger.log('%s -> ******' % item_name, logger.DEBUG)

    return (my_val, def_val)['None' == my_val]


class ConfigMigrator():
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
                                10: 'Reset backlog frequency to default',
                                11: 'Migrate anime split view to new layout',
                                12: 'Add "hevc" and some non-english languages to ignore words if not found',
                                13: 'Change default dereferrer url to blank',
                                14: 'Convert Trakt to multi-account'}

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
            if not helpers.backupVersionedFile(sickbeard.CONFIG_FILE, self.config_version):
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
        myDB = db.DBConnection()
        season_folder_shows = myDB.select('SELECT * FROM tv_shows WHERE flatten_folders = 0')

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
            myDB.action('UPDATE tv_shows SET flatten_folders = 0')

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
        naming_ep_type = ('%Sx%0E',
                          's%0Se%0E',
                          'S%0SE%0E',
                          '%0Sx%0E')
        naming_sep_type = (' - ', ' ')

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
            ep_string = naming_ep_type[ep_type]

        finalName = ''

        # start with the show name
        if use_show_name:
            finalName += show_name + naming_sep_type[sep_type]

        # add the season/ep stuff
        finalName += ep_string

        # add the episode name
        if use_ep_name:
            finalName += naming_sep_type[sep_type] + ep_name

        # add the quality
        if use_quality:
            finalName += naming_sep_type[sep_type] + ep_quality

        if use_periods:
            finalName = re.sub('\s+', '.', finalName)

        return finalName

    # Migration v2: Dummy migration to sync backup number with config version number
    def _migrate_v2(self):
        return

    # Migration v2: Rename omgwtfnzb variables
    def _migrate_v3(self):
        """
        Reads in the old naming settings from your config and generates a new config template from them.
        """
        # get the old settings from the file and store them in the new variable names
        for prov in [curProvider for curProvider in sickbeard.providers.sortedProviderList() if curProvider.name == 'omgwtfnzbs']:
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

                if name == 'Sick Beard Index':
                    key = '0'

                if name == 'NZBs.org':
                    cat_ids = '5030,5040,5060,5070,5090'
                else:
                    cat_ids = '5030,5040,5060'

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

        def _migrate_metadata(metadata, metadata_name, use_banner):
            cur_metadata = metadata.split('|')
            # if target has the old number of values, do upgrade
            if len(cur_metadata) == 6:
                logger.log(u'Upgrading ' + metadata_name + ' metadata, old value: ' + metadata)
                cur_metadata.insert(4, '0')
                cur_metadata.append('0')
                cur_metadata.append('0')
                cur_metadata.append('0')
                # swap show fanart, show poster
                cur_metadata[3], cur_metadata[2] = cur_metadata[2], cur_metadata[3]
                # if user was using use_banner to override the poster,
                # instead enable the banner option and deactivate poster
                if metadata_name == 'XBMC' and use_banner:
                    cur_metadata[4], cur_metadata[3] = cur_metadata[3], '0'
                # write new format
                metadata = '|'.join(cur_metadata)
                logger.log(u'Upgrading %s metadata, new value: %s' % (metadata_name, metadata))

            elif len(cur_metadata) == 10:
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
        sickbeard.RECENTSEARCH_FREQUENCY = check_setting_int(self.config_obj, 'General', 'dailysearch_frequency',
                                                             sickbeard.DEFAULT_RECENTSEARCH_FREQUENCY)

        sickbeard.RECENTSEARCH_STARTUP = bool(check_setting_int(self.config_obj, 'General', 'dailysearch_startup', 1))
        if sickbeard.RECENTSEARCH_FREQUENCY < sickbeard.MIN_RECENTSEARCH_FREQUENCY:
            sickbeard.RECENTSEARCH_FREQUENCY = sickbeard.MIN_RECENTSEARCH_FREQUENCY

        for curProvider in sickbeard.providers.sortedProviderList():
            if hasattr(curProvider, 'enable_recentsearch'):
                curProvider.enable_recentsearch = bool(check_setting_int(
                    self.config_obj, curProvider.get_id().upper(), curProvider.get_id() + '_enable_dailysearch', 1))

    def _migrate_v7(self):
        sickbeard.EPISODE_VIEW_LAYOUT = check_setting_str(self.config_obj, 'GUI', 'coming_eps_layout', 'banner')
        sickbeard.EPISODE_VIEW_SORT = check_setting_str(self.config_obj, 'GUI', 'coming_eps_sort', 'time')
        if 'date' == sickbeard.EPISODE_VIEW_SORT:
            sickbeard.EPISODE_VIEW_SORT = 'time'
        sickbeard.EPISODE_VIEW_DISPLAY_PAUSED = bool(
            check_setting_int(self.config_obj, 'GUI', 'coming_eps_display_paused', 0))
        sickbeard.EPISODE_VIEW_MISSED_RANGE = check_setting_int(self.config_obj, 'GUI', 'coming_eps_missed_range', 7)

    def _migrate_v8(self):
        # removing settings from gui and making it a hidden debug option
        sickbeard.RECENTSEARCH_STARTUP = False

    def _migrate_v9(self):
        sickbeard.PUSHBULLET_ACCESS_TOKEN = check_setting_str(self.config_obj, 'Pushbullet', 'pushbullet_api', '')
        sickbeard.PUSHBULLET_DEVICE_IDEN = check_setting_str(self.config_obj, 'Pushbullet', 'pushbullet_device', '')

    def _migrate_v10(self):
        # reset backlog frequency to default
        sickbeard.BACKLOG_FREQUENCY = sickbeard.DEFAULT_BACKLOG_FREQUENCY

    def _migrate_v11(self):
        if check_setting_int(self.config_obj, 'ANIME', 'anime_split_home', ''):
            sickbeard.SHOWLIST_TAGVIEW = 'anime'
        else:
            sickbeard.SHOWLIST_TAGVIEW = 'default'

    def _migrate_v12(self):
        # add words to ignore list and insert spaces to improve the ui config readability
        words_to_add = ['hevc', 'reenc', 'x265', 'danish', 'deutsch', 'flemish', 'italian', 'nordic', 'norwegian', 'portuguese', 'spanish', 'turkish']
        config_words = sickbeard.IGNORE_WORDS.split(',')
        new_list = []
        for new_word in words_to_add:
            add_word = True
            for ignore_word in config_words:
                ignored = ignore_word.strip().lower()
                if ignored and ignored not in new_list:
                    new_list += [ignored]
                if re.search(r'(?i)%s' % new_word, ignored):
                    add_word = False
            if add_word:
                new_list += [new_word]

        sickbeard.IGNORE_WORDS = ', '.join(sorted(new_list))

    def _migrate_v13(self):
        # change dereferrer.org urls to blank, but leave any other url untouched
        if sickbeard.ANON_REDIRECT == 'http://dereferer.org/?':
            sickbeard.ANON_REDIRECT = ''

    def _migrate_v14(self):
        old_token = check_setting_str(self.config_obj, 'Trakt', 'trakt_token', '')
        old_refresh_token = check_setting_str(self.config_obj, 'Trakt', 'trakt_refresh_token', '')
        if old_token and old_refresh_token:
            TraktAPI.add_account(old_token, old_refresh_token, None)

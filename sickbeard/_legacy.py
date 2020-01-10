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

#
# This file contains deprecated routes and parameters
# Eventually, this file and its use will be removed from SG core.
#
import threading
import traceback

import sickbeard
from . import logger
from .indexers.indexer_config import TVINFO_IMDB, TVINFO_TVDB
from .tv import TVidProdid

from tornado import gen
from tornado.web import RequestHandler

from _23 import decode_str, filter_iter
from six import iteritems

""" deprecated_item, remove in 2020 = 8 items """
""" prevent issues with requests using legacy params = 3 items"""
# TODO: deprecated items, find the above comments and remove in 2020


class LegacyBase(RequestHandler):

    # todo: move to RouteHandler after removing _legacy module
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
        return super(LegacyBase, self).write_error(status_code, **kwargs)

    def data_received(self, *args):
        pass


class LegacyBaseHandler(LegacyBase):

    def redirect_args(self, new_url, exclude=(None,), **kwargs):
        args = '&'.join(['%s=%s' % (k, v) for (k, v) in
                         filter_iter(lambda arg: arg[1] not in exclude, iteritems(kwargs))])
        self.redirect('%s%s' % (new_url, ('', '?' + args)[bool(args)]), permanent=True)

    """ deprecated from BaseHandler ------------------------------------------------------------------------------------
    """
    def getImage(self, *args, **kwargs):
        return self.get_image(*args, **kwargs)

    def get_image(self, *args, **kwargs):
        # abstract method
        pass

    def showPoster(self, show=None, **kwargs):
        # test:  /showPoster/?show=73141&which=poster_thumb
        return self.show_poster(TVidProdid(show)(), **kwargs)

    def show_poster(self, *args, **kwargs):
        # abstract method
        pass

    """ deprecated from MainHandler ------------------------------------------------------------------------------------
    """
    def episodeView(self, **kwargs):
        self.redirect_args('/daily-schedule', exclude=(None, False), **kwargs)

    def setHomeLayout(self, *args, **kwargs):
        return self.set_layout_view_shows(*args, **kwargs)

    def set_layout_view_shows(self, *args, **kwargs):
        # abstract method
        pass

    def setPosterSortBy(self, *args):
        return self.set_poster_sortby(*args)

    @staticmethod
    def set_poster_sortby(*args):
        # abstract method
        pass

    def setPosterSortDir(self, *args):
        return self.set_poster_sortdir(*args)

    @staticmethod
    def set_poster_sortdir(*args):
        # abstract method
        pass

    def setEpisodeViewLayout(self, *args):
        return self.set_layout_daily_schedule(*args)

    def set_layout_daily_schedule(self, *args):
        # abstract method
        pass

    def toggleEpisodeViewDisplayPaused(self):
        return self.toggle_display_paused_daily_schedule()

    def toggle_display_paused_daily_schedule(self):
        # abstract method
        pass

    def setEpisodeViewCards(self, *args, **kwargs):
        return self.set_cards_daily_schedule(*args, **kwargs)

    def set_cards_daily_schedule(self, *args, **kwargs):
        # abstract method
        pass

    def setEpisodeViewSort(self, *args, **kwargs):
        return self.set_sort_daily_schedule(*args, **kwargs)

    def set_sort_daily_schedule(self, *args, **kwargs):
        # abstract method
        pass

    def getFooterTime(self, *args, **kwargs):
        return self.get_footer_time(*args, **kwargs)

    @staticmethod
    def get_footer_time(*args, **kwargs):
        # abstract method
        pass

    def toggleDisplayShowSpecials(self, **kwargs):
        return self.toggle_specials_view_show(TVidProdid(kwargs.get('show'))())

    def toggle_specials_view_show(self, *args):
        # abstract method
        pass

    def setHistoryLayout(self, *args):
        return self.set_layout_history(*args)

    def set_layout_history(self, *args):
        # abstract method
        pass

    """ deprecated from Home -------------------------------------------------------------------------------------------
    """
    def showlistView(self):
        self.redirect('/view-shows', permanent=True)

    def viewchanges(self):
        self.redirect('/home/view-changes', permanent=True)

    def displayShow(self, **kwargs):
        self.migrate_redir('view-show', **kwargs)

    def editShow(self, **kwargs):
        kwargs['any_qualities'] = kwargs.pop('anyQualities', None)
        kwargs['best_qualities'] = kwargs.pop('bestQualities', None)
        kwargs['exceptions_list'] = kwargs.pop('exceptions_list', None)
        kwargs['direct_call'] = kwargs.pop('directCall', False)
        kwargs['tvinfo_lang'] = kwargs.pop('indexerLang', None)
        kwargs['subs'] = kwargs.pop('subtitles', None)
        self.migrate_redir('edit-show', **kwargs)

    def testRename(self, **kwargs):
        self.migrate_redir('rename-media', **kwargs)

    def migrate_redir(self, new_url, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        self.redirect_args('/home/%s' % new_url, exclude=(None, False), **kwargs)

    def setStatus(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.set_show_status(**kwargs)

    def set_show_status(self, **kwargs):
        # abstract method
        pass

    def branchCheckout(self, *args):
        return self.branch_checkout(*args)

    def branch_checkout(self, *args):
        # abstract method
        pass

    def pullRequestCheckout(self, *args):
        return self.pull_request_checkout(*args)

    def pull_request_checkout(self, *args):
        # abstract method
        pass

    def display_season(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.season_render(**kwargs)

    def season_render(self, **kwargs):
        # abstract method
        pass

    def plotDetails(self, show, *args):
        return self.plot_details(TVidProdid(show)(), *args)

    @staticmethod
    def plot_details(*args):
        # abstract method
        pass

    def sceneExceptions(self, show):
        return self.scene_exceptions(TVidProdid(show)())

    @staticmethod
    def scene_exceptions(*args):
        # abstract method
        pass

    def saveMapping(self, show, **kwargs):
        kwargs['m_tvid'] = kwargs.pop('mindexer', 0)
        kwargs['m_prodid'] = kwargs.pop('mindexerid', 0)
        return self.save_mapping(TVidProdid(show)(), **kwargs)

    def save_mapping(self, *args, **kwargs):
        # abstract method
        pass

    def forceMapping(self, show, **kwargs):
        return self.force_mapping(TVidProdid(show)(), **kwargs)

    @staticmethod
    def force_mapping(*args, **kwargs):
        # abstract method
        pass

    def deleteShow(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.delete_show(**kwargs)

    def delete_show(self, *args, **kwargs):
        # abstract method
        pass

    def refreshShow(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.refresh_show(**kwargs)

    def refresh_show(self, *args, **kwargs):
        # abstract method
        pass

    def updateShow(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.update_show(**kwargs)

    def update_show(self, *args, **kwargs):
        # abstract method
        pass

    def subtitleShow(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.subtitle_show(**kwargs)

    def subtitle_show(self, *args, **kwargs):
        # abstract method
        pass

    def doRename(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.do_rename(**kwargs)

    def do_rename(self, *args, **kwargs):
        # abstract method
        pass

    def episode_search(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.search_episode(**kwargs)

    def search_episode(self, *args, **kwargs):
        # abstract method
        pass

    def searchEpisodeSubtitles(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.search_episode_subtitles(**kwargs)

    def search_episode_subtitles(self, *args, **kwargs):
        # abstract method
        pass

    def setSceneNumbering(self, **kwargs):
        return self.set_scene_numbering(
            tvid_prodid={kwargs.pop('indexer', ''): kwargs.pop('show', '')},
            for_season=kwargs.get('forSeason'), for_episode=kwargs.get('forEpisode'),
            scene_season=kwargs.get('sceneSeason'), scene_episode=kwargs.get('sceneEpisode'),
            scene_absolute=kwargs.get('sceneAbsolute'))

    @staticmethod
    def set_scene_numbering(*args, **kwargs):
        # abstract method
        pass

    def update_emby(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.update_mb(**kwargs)

    def update_mb(self, *args, **kwargs):
        # abstract method
        pass

    def search_q_progress(self, **kwargs):
        kwargs['tvid_prodid'] = TVidProdid(kwargs.pop('show', ''))()
        return self.search_q_status(**kwargs)

    def search_q_status(self, *args, **kwargs):
        # abstract method
        pass

    """ deprecated from NewHomeAddShows i.e. HomeAddShows --------------------------------------------------------------
    """
    def addExistingShows(self, **kwargs):
        kwargs['prompt_for_settings'] = kwargs.pop('promptForSettings', None)
        self.redirect_args('/add-shows/add-existing-shows', **kwargs)

    def addAniDBShow(self, **kwargs):
        self.migrate_redir_add_shows('info-anidb', TVINFO_TVDB, **kwargs)

    def addIMDbShow(self, **kwargs):
        self.migrate_redir_add_shows('info-imdb', TVINFO_IMDB, **kwargs)

    def addTraktShow(self, **kwargs):
        self.migrate_redir_add_shows('info-trakt', TVINFO_TVDB, **kwargs)

    def migrate_redir_add_shows(self, new_url, tvinfo, **kwargs):
        prodid = kwargs.pop('indexer_id', None)
        if prodid:
            kwargs['ids'] = prodid
        if TVINFO_TVDB == tvinfo and prodid:
            kwargs['ids'] = TVidProdid({tvinfo: prodid})()
        kwargs['show_name'] = kwargs.pop('showName', None)
        self.redirect_args('/add-shows/%s' % new_url, **kwargs)

    def getIndexerLanguages(self):
        return self.get_infosrc_languages()

    @staticmethod
    def get_infosrc_languages():
        # abstract method
        pass

    def sanitizeFileName(self, *args):
        # todo: find where this is called in JS or tmpl, the old name must still be used as refactor didnt find it
        return self.sanitize_file_name(*args)

    def sanitize_file_name(self, *args):
        # abstract method
        pass

    def searchIndexersForShowName(self, *args, **kwargs):
        return self.search_tvinfo_for_showname(*args, **kwargs)

    def search_tvinfo_for_showname(self, *args, **kwargs):
        # abstract method
        pass

    def massAddTable(self, **kwargs):
        return self.mass_add_table(
            root_dir=kwargs.pop('rootDir', None), **kwargs)

    def mass_add_table(self, *args, **kwargs):
        # abstract method
        pass

    def addNewShow(self, **kwargs):
        return self.add_new_show(
            provided_tvid=kwargs.pop('providedIndexer', None),
            which_series=kwargs.pop('whichSeries', None),
            tvinfo_lang=kwargs.pop('indexerLang', 'en'),
            root_dir=kwargs.pop('rootDir', None),
            default_status=kwargs.pop('defaultStatus', None),
            any_qualities=kwargs.pop('anyQualities', None),
            best_qualities=kwargs.pop('bestQualities', None),
            subs=kwargs.pop('subtitles', None),
            full_show_path=kwargs.pop('fullShowPath', None),
            skip_show=kwargs.pop('skipShow', None),
            **kwargs)

    def add_new_show(self, *args, **kwargs):
        # abstract method
        pass

    """ deprecated from ConfigGeneral ----------------------------------------------------------------------------------
    """
    def generateKey(self):
        return self.generate_key()

    @staticmethod
    def generate_key():
        # abstract method
        pass

    def saveRootDirs(self, **kwargs):
        return self.save_root_dirs(root_dir_string=kwargs.get('rootDirString'))

    @staticmethod
    def save_root_dirs(**kwargs):
        # abstract method
        pass

    def saveResultPrefs(self, **kwargs):
        return self.save_result_prefs(**kwargs)

    @staticmethod
    def save_result_prefs(**kwargs):
        # abstract method
        pass

    def saveAddShowDefaults(self, *args, **kwargs):
        return self.save_add_show_defaults(*args, **kwargs)

    @staticmethod
    def save_add_show_defaults(*args, **kwargs):
        # abstract method
        pass

    def saveGeneral(self, **kwargs):
        return self.save_general(**kwargs)

    def save_general(self, **kwargs):
        # abstract method
        pass

    """ deprecated from ConfigSearch -----------------------------------------------------------------------------------
    """
    def saveSearch(self, **kwargs):
        return self.save_search(**kwargs)

    def save_search(self, **kwargs):
        # abstract method
        pass

    """ deprecated from ConfigProviders --------------------------------------------------------------------------------
    """
    def canAddNewznabProvider(self, *args):
        return self.can_add_newznab_provider(*args)

    @staticmethod
    def can_add_newznab_provider(*args):
        # abstract method
        pass

    def saveNewznabProvider(self, *args, **kwargs):
        # todo: find where this is called in JS or tmpl, the old name must still be used as refactor didnt find it
        return self.save_newznab_provider(*args, **kwargs)

    @staticmethod
    def save_newznab_provider(*args, **kwargs):
        # abstract method
        pass

    def getNewznabCategories(self, *args):
        return self.get_newznab_categories(*args)

    @staticmethod
    def get_newznab_categories(*args):
        # abstract method
        pass

    def deleteNewznabProvider(self, *args):
        # todo: find where this is called in JS or tmpl, the old name must still be used as refactor didnt find it
        return self.delete_newznab_provider(*args)

    @staticmethod
    def delete_newznab_provider(*args):
        # abstract method
        pass

    def canAddTorrentRssProvider(self, *args):
        return self.can_add_torrent_rss_provider(*args)

    @staticmethod
    def can_add_torrent_rss_provider(*args):
        # abstract method
        pass

    def saveTorrentRssProvider(self, *args):
        # todo: find where this is called in JS or tmpl, the old name must still be used as refactor didnt find it
        return self.save_torrent_rss_provider(*args)

    @staticmethod
    def save_torrent_rss_provider(*args):
        # abstract method
        pass

    def deleteTorrentRssProvider(self, **kwargs):
        # todo: find where this is called in JS or tmpl, the old name must still be used as refactor didnt find it
        return self.delete_torrent_rss_provider(kwargs.get('id'))

    @staticmethod
    def delete_torrent_rss_provider(*args):
        # abstract method
        pass

    def checkProvidersPing(self):
        return self.check_providers_ping()

    @staticmethod
    def check_providers_ping():
        # abstract method
        pass

    def saveProviders(self, *args, **kwargs):
        return self.save_providers(*args, **kwargs)

    def save_providers(self, *args, **kwargs):
        # abstract method
        pass

    """ deprecated from ConfigPostProcessing ---------------------------------------------------------------------------
    """
    def savePostProcessing(self, **kwargs):
        return self.save_post_processing(**kwargs)

    def save_post_processing(self, **kwargs):
        # abstract method
        pass

    def testNaming(self, *args, **kwargs):
        return self.test_naming(*args, **kwargs)

    @staticmethod
    def test_naming(*args, **kwargs):
        # abstract method
        pass

    def isNamingValid(self, *args, **kwargs):
        return self.is_naming_valid(*args, **kwargs)

    @staticmethod
    def is_naming_valid(*args, **kwargs):
        # abstract method
        pass

    def isRarSupported(self):
        return self.is_rar_supported()

    @staticmethod
    def is_rar_supported():
        # abstract method
        pass

    """ deprecated from ConfigSubtitles --------------------------------------------------------------------------------
    """
    def saveSubtitles(self, **kwargs):
        return self.save_subtitles(**kwargs)

    def save_subtitles(self, **kwargs):
        # abstract method
        pass

    """ deprecated from ConfigAnime ------------------------------------------------------------------------------------
    """
    def saveAnime(self, **kwargs):
        return self.save_anime(**kwargs)

    def save_anime(self, **kwargs):
        # abstract method
        pass

    """ deprecated from Manage -----------------------------------------------------------------------------------------
    """
    def episode_statuses(self, **kwargs):
        self.redirect_args('/manage/episode-overview', **kwargs)

    def subtitleMissed(self, **kwargs):
        kwargs['which_subs'] = kwargs.pop('whichSubs', None)
        self.redirect_args('/manage/subtitle_missed', **kwargs)

    def show_episode_statuses(self, **kwargs):
        return self.get_status_episodes(TVidProdid(kwargs.get('indexer_id'))(), kwargs.get('which_status'))

    @staticmethod
    def get_status_episodes(*args):
        # abstract method
        pass

    def showSubtitleMissed(self, **kwargs):
        return self.show_subtitle_missed(TVidProdid(kwargs.get('indexer_id'))(), kwargs.get('whichSubs'))

    @staticmethod
    def show_subtitle_missed(*args):
        # abstract method
        pass

    def downloadSubtitleMissed(self, **kwargs):
        return self.download_subtitle_missed(**kwargs)

    def download_subtitle_missed(self, **kwargs):
        # abstract method
        pass

    def backlogShow(self, **kwargs):
        return self.backlog_show(TVidProdid(kwargs.get('indexer_id'))())

    def backlog_show(self, *args):
        # abstract method
        pass

    def backlogOverview(self):
        self.redirect('/manage/backlog_overview', permanent=True)

    def massEdit(self, **kwargs):
        return self.mass_edit(to_edit=kwargs.get('toEdit'))

    def mass_edit(self, **kwargs):
        # abstract method
        pass

    def massEditSubmit(self, **kwargs):
        kwargs['to_edit'] = kwargs.pop('toEdit', None)
        kwargs['subs'] = kwargs.pop('subtitles', None)
        kwargs['any_qualities'] = kwargs.pop('anyQualities', None)
        kwargs['best_qualities'] = kwargs.pop('bestQualities', None)
        return self.mass_edit_submit(**kwargs)

    def mass_edit_submit(self, **kwargs):
        # abstract method
        pass

    def bulkChange(self, **kwargs):
        return self.bulk_change(
            to_update=kwargs.get('toUpdate'), to_refresh=kwargs.get('toRefresh'),
            to_rename=kwargs.get('toRename'), to_delete=kwargs.get('toDelete'), to_remove=kwargs.get('toRemove'),
            to_metadata=kwargs.get('toMetadata'), to_subtitle=kwargs.get('toSubtitle'))

    def bulk_change(self, **kwargs):
        # abstract method
        pass

    def failedDownloads(self, **kwargs):
        kwargs['to_remove'] = kwargs.pop('toRemove', None)
        return self.failed_downloads(**kwargs)

    def failed_downloads(self, **kwargs):
        # abstract method
        pass

    """ deprecated from ManageSearches ---------------------------------------------------------------------------------
    """
    def retryProvider(self, **kwargs):
        return self.retry_provider(**kwargs)

    @staticmethod
    def retry_provider(**kwargs):
        # abstract method
        pass

    def forceVersionCheck(self):
        return self.check_update()

    def check_update(self):
        # abstract method
        pass

    def forceBacklog(self):
        return self.force_backlog()

    def force_backlog(self):
        # abstract method
        pass

    def forceSearch(self):
        return self.force_search()

    def force_search(self):
        # abstract method
        pass

    def forceFindPropers(self):
        return self.force_find_propers()

    def force_find_propers(self):
        # abstract method
        pass

    def pauseBacklog(self, **kwargs):
        return self.pause_backlog(**kwargs)

    def pause_backlog(self, **kwargs):
        # abstract method
        pass

    """ deprecated from ShowProcesses ----------------------------------------------------------------------------------
    """
    def forceShowUpdate(self):
        return self.force_show_update()

    def force_show_update(self):
        # abstract method
        pass

    """ deprecated from History ----------------------------------------------------------------------------------------
    """
    def clearHistory(self):
        return self.clear_history()

    def clear_history(self):
        # abstract method
        pass

    def trimHistory(self):
        return self.trim_history()

    def trim_history(self):
        # abstract method
        pass

    """ deprecated from ErrorLogs --------------------------------------------------------------------------------------
    """
    def clearerrors(self):
        self.redirect('/errors/clear-log')

    def viewlog(self, **kwargs):
        self.redirect_args('/events/view-log/', **kwargs)

    def downloadlog(self):
        return self.download_log()

    def download_log(self):
        # abstract method
        pass

    """ ------------------------------------------------------------------------------------------------------------ """
    """ ------------------------------------------------------------------------------------------------------------ """
    """ end of base deprecated function stubs """
    """ ------------------------------------------------------------------------------------------------------------ """
    """ ------------------------------------------------------------------------------------------------------------ """


class LegacyRouteHandler(RequestHandler):

    def data_received(self, *args):
        pass

    def __init__(self, *arg, **kwargs):
        super(LegacyRouteHandler, self).__init__(*arg, **kwargs)
        self.lock = threading.Lock()

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.set_header('X-Robots-Tag', 'noindex, nofollow, noarchive, nocache, noodp, noydir, noimageindex, nosnippet')
        if sickbeard.SEND_SECURITY_HEADERS:
            self.set_header('X-Frame-Options', 'SAMEORIGIN')

    # noinspection PyUnusedLocal
    @gen.coroutine
    def get(self, *args, **kwargs):
        getattr(self, 'index')()

    def redirect(self, url, permanent=False, status=None):
        if not url.startswith(sickbeard.WEB_ROOT):
            url = sickbeard.WEB_ROOT + url

        super(LegacyRouteHandler, self).redirect(url, permanent, status)


class LegacyManageManageSearches(LegacyRouteHandler):

    """ deprecated from ManageSearches ---------------------------------------------------------------------------------
    """
    def index(self):
        self.redirect('/manage/search-tasks/', permanent=True)


class LegacyManageShowProcesses(LegacyRouteHandler):

    """ deprecated from ManageShowProcesses ----------------------------------------------------------------------------
    """
    def index(self):
        self.redirect('/manage/show-tasks/', permanent=True)


class LegacyConfigPostProcessing(LegacyRouteHandler):

    """ deprecated from ConfigPostProcessing ---------------------------------------------------------------------------
    """
    def index(self):
        self.redirect('/config/media-process/', permanent=True)


class LegacyHomeAddShows(LegacyRouteHandler):

    """ deprecated from NewHomeAddShows i.e. HomeAddShows --------------------------------------------------------------
    """
    def index(self):
        self.redirect('/add-shows/', permanent=True)


class LegacyErrorLogs(LegacyRouteHandler):

    """ deprecated from ErrorLogs --------------------------------------------------------------------------------------
    """
    def index(self):
        self.redirect('/events/', permanent=True)

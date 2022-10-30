import os
from sys import exc_info, platform
import threading

from tornado.ioloop import IOLoop
from tornado.routing import AnyMatches, Rule
# noinspection PyProtectedMember
from tornado.web import Application, _ApplicationRouter

from . import logger, webapi, webserve
from ._legacy import LegacyConfigPostProcessing, LegacyHomeAddShows, \
    LegacyManageManageSearches, LegacyManageShowProcesses, LegacyErrorLogs
from .helpers import create_https_certificates, re_valid_hostname
import sickbeard

from _23 import PY38
from six import PY2

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Dict


class MyApplication(Application):

    def __init__(self, *args, **kwargs):
        super(MyApplication, self).__init__(*args, **kwargs)
        self.is_loading_handler = False  # type: bool

    def reset_handlers(self):
        self.is_loading_handler = False
        self.wildcard_router = _ApplicationRouter(self, [])
        self.default_router = _ApplicationRouter(self, [
            Rule(AnyMatches(), self.wildcard_router)
        ])


class WebServer(threading.Thread):
    def __init__(self, options=None):
        # type: (Dict) -> None
        threading.Thread.__init__(self)
        self._ready_event = threading.Event()
        self.daemon = True
        self.alive = True
        self.name = 'TORNADO'
        self.io_loop = None
        self.server = None

        self.options = options or {}
        self.options.setdefault('port', 8081)
        self.options.setdefault('host', '0.0.0.0')
        self.options.setdefault('log_dir', None)
        self.options.setdefault('username', '')
        self.options.setdefault('password', '')
        self.options.setdefault('web_root', None)
        assert isinstance(self.options['port'], int)
        assert 'data_root' in self.options

        # web root
        self.options['web_root'] = ('/' + self.options['web_root'].lstrip('/')) if self.options['web_root'] else ''

        # tornado setup
        self.enable_https = self.options['enable_https']
        self.https_cert = self.options['https_cert']
        self.https_key = self.options['https_key']

        if self.enable_https:
            make_cert = False
            update_cfg = False
            for (attr, ext) in [('https_cert', '.crt'), ('https_key', '.key')]:
                ssl_path = getattr(self, attr, None)
                if ssl_path and not os.path.isfile(ssl_path):
                    if not ssl_path.endswith(ext):
                        setattr(self, attr, os.path.join(ssl_path, 'server%s' % ext))
                        setattr(sickbeard, attr.upper(), 'server%s' % ext)
                    make_cert = True

            # If either the HTTPS certificate or key do not exist, make some self-signed ones.
            if make_cert:
                if not create_https_certificates(self.https_cert, self.https_key):
                    logger.log(u'Unable to create CERT/KEY files, disabling HTTPS')
                    update_cfg |= False is not sickbeard.ENABLE_HTTPS
                    sickbeard.ENABLE_HTTPS = False
                    self.enable_https = False
                else:
                    update_cfg = True

            if not (os.path.isfile(self.https_cert) and os.path.isfile(self.https_key)):
                logger.log(u'Disabled HTTPS because of missing CERT and KEY files', logger.WARNING)
                update_cfg |= False is not sickbeard.ENABLE_HTTPS
                sickbeard.ENABLE_HTTPS = False
                self.enable_https = False

            if update_cfg:
                sickbeard.save_config()

        # Load the app
        self.app = MyApplication([],
                                 debug=True,
                                 serve_traceback=True,
                                 autoreload=False,
                                 compress_response=True,
                                 cookie_secret=sickbeard.COOKIE_SECRET,
                                 xsrf_cookies=True,
                                 login_url='%s/login/' % self.options['web_root'],
                                 default_handler_class=webserve.WrongHostWebHandler)

        self.re_host_pattern = re_valid_hostname()
        self._add_loading_rules()

    def _add_loading_rules(self):
        self.app.is_loading_handler = True
        # webui login/logout handlers
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/login(/?)' % self.options['web_root'], webserve.LoginHandler),
            (r'%s/logout(/?)' % self.options['web_root'], webserve.LogoutHandler),
        ])

        # Static File Handlers
        self.app.add_handlers(self.re_host_pattern, [
            # favicon
            (r'%s/(favicon\.ico)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images', 'ico')}),

            # images
            (r'%s/images/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images')}),

            # css
            (r'%s/css/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'css')}),

            # javascript
            (r'%s/js/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'js')}),
        ])

        # Main Handler
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/api(/?.*)' % self.options['web_root'], webapi.ApiServerLoading),
            (r'%s/home/is-alive(/?.*)' % self.options['web_root'], webserve.IsAliveHandler),
            (r'%s/ui(/?.*)' % self.options['web_root'], webserve.UI),
            (r'%s(/?.*)' % self.options['web_root'], webserve.LoadingWebHandler),
            # ----------------------------------------------------------------------------------------------------------
            # legacy deprecated Aug 2019
            (r'%s/home/is_alive(/?.*)' % self.options['web_root'], webserve.IsAliveHandler),
        ])

        self.app.add_handlers(r'.*', [(r'.*', webserve.WrongHostWebHandler)])

    def _add_default_rules(self):
        self.app.is_loading_handler = False
        # webui login/logout handlers
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/login(/?)' % self.options['web_root'], webserve.LoginHandler),
            (r'%s/logout(/?)' % self.options['web_root'], webserve.LogoutHandler),
        ])

        # Web calendar handler (Needed because option Unprotected calendar)
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/calendar' % self.options['web_root'], webserve.CalendarHandler),
        ])

        # Static File Handlers
        self.app.add_handlers(self.re_host_pattern, [
            # favicon
            (r'%s/(favicon\.ico)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images', 'ico')}),

            # images
            (r'%s/images/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images')}),

            # cached images
            (r'%s/cache/images/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(sickbeard.CACHE_DIR, 'images')}),

            # css
            (r'%s/css/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'css')}),

            # javascript
            (r'%s/js/(.*)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'js')}),

            # logfile
            (r'%s/logfile/(.*)' % self.options['web_root'], webserve.LogfileHandler),

            (r'%s/kodi/((?:(?![|]verifypeer=false).)*)' % self.options['web_root'], webserve.RepoHandler,
             {'path': os.path.join(sickbeard.CACHE_DIR, 'clients', 'kodi'),
              'default_filename': 'index.html'}),
        ])

        # Main Handler
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/ui(/?.*)' % self.options['web_root'], webserve.UI),
            (r'%s/home/is-alive(/?.*)' % self.options['web_root'], webserve.IsAliveHandler),
            (r'%s/imagecache(/?.*)' % self.options['web_root'], webserve.CachedImages),
            (r'%s/cache(/?.*)' % self.options['web_root'], webserve.Cache),
            (r'%s(/?update-watched-state-kodi/?)' % self.options['web_root'], webserve.NoXSRFHandler),
            (r'%s/add-shows(/?.*)' % self.options['web_root'], webserve.AddShows),
            (r'%s/home/process-media(/?.*)' % self.options['web_root'], webserve.HomeProcessMedia),
            (r'%s/config/general(/?.*)' % self.options['web_root'], webserve.ConfigGeneral),
            (r'%s/config/search(/?.*)' % self.options['web_root'], webserve.ConfigSearch),
            (r'%s/config/providers(/?.*)' % self.options['web_root'], webserve.ConfigProviders),
            (r'%s/config/media-process(/?.*)' % self.options['web_root'], webserve.ConfigMediaProcess),
            (r'%s/config/subtitles(/?.*)' % self.options['web_root'], webserve.ConfigSubtitles),
            (r'%s/config/notifications(/?.*)' % self.options['web_root'], webserve.ConfigNotifications),
            (r'%s/config/anime(/?.*)' % self.options['web_root'], webserve.ConfigAnime),
            (r'%s/manage/search-tasks(/?.*)' % self.options['web_root'], webserve.ManageSearch),
            (r'%s/manage/show-tasks(/?.*)' % self.options['web_root'], webserve.ShowTasks),
            (r'%s/api/builder(/?)(.*)' % self.options['web_root'], webserve.ApiBuilder),
            (r'%s/api(/?.*)' % self.options['web_root'], webapi.Api),
            # ----------------------------------------------------------------------------------------------------------
            # legacy deprecated Aug 2019
            (r'%s/home/addShows/?$' % self.options['web_root'], LegacyHomeAddShows),
            (r'%s/manage/manageSearches/?$' % self.options['web_root'], LegacyManageManageSearches),
            (r'%s/manage/showProcesses/?$' % self.options['web_root'], LegacyManageShowProcesses),
            (r'%s/config/postProcessing/?$' % self.options['web_root'], LegacyConfigPostProcessing),
            (r'%s/errorlogs/?$' % self.options['web_root'], LegacyErrorLogs),
            (r'%s/home/is_alive(/?.*)' % self.options['web_root'], webserve.IsAliveHandler),
            (r'%s/home/addShows(/?.*)' % self.options['web_root'], webserve.AddShows),
            (r'%s/manage/manageSearches(/?.*)' % self.options['web_root'], webserve.ManageSearch),
            (r'%s/manage/showProcesses(/?.*)' % self.options['web_root'], webserve.ShowTasks),
            (r'%s/config/postProcessing(/?.*)' % self.options['web_root'], webserve.ConfigMediaProcess),
            (r'%s/errorlogs(/?.*)' % self.options['web_root'], webserve.EventLogs),
            # ----------------------------------------------------------------------------------------------------------
            # legacy deprecated Aug 2019 - never remove as used in external scripts
            (r'%s/home/postprocess(/?.*)' % self.options['web_root'], webserve.HomeProcessMedia),
            (r'%s(/?update_watched_state_kodi/?)' % self.options['web_root'], webserve.NoXSRFHandler),
            # regular catchall routes - keep here at the bottom
            (r'%s/home(/?.*)' % self.options['web_root'], webserve.Home),
            (r'%s/manage/(/?.*)' % self.options['web_root'], webserve.Manage),
            (r'%s/config(/?.*)' % self.options['web_root'], webserve.Config),
            (r'%s/browser(/?.*)' % self.options['web_root'], webserve.WebFileBrowser),
            (r'%s/errors(/?.*)' % self.options['web_root'], webserve.EventLogs),
            (r'%s/events(/?.*)' % self.options['web_root'], webserve.EventLogs),
            (r'%s/history(/?.*)' % self.options['web_root'], webserve.History),
            (r'%s(/?.*)' % self.options['web_root'], webserve.MainHandler),
        ])

        self.app.add_handlers(r'.*', [(r'.*', webserve.WrongHostWebHandler)])

    def run(self):
        protocol, ssl_options = (('http', None),
                                 ('https', {'certfile': self.https_cert, 'keyfile': self.https_key}))[self.enable_https]

        logger.log(u'Starting SickGear on %s://%s:%s/' % (protocol, self.options['host'],  self.options['port']))

        # python 3 needs to start event loop first
        if not PY2:
            import asyncio
            if 'win32' == platform and PY38:
                # noinspection PyUnresolvedReferences
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.set_event_loop(asyncio.new_event_loop())
            from tornado_py3.platform.asyncio import AnyThreadEventLoopPolicy
            asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())

        try:
            self.server = self.app.listen(self.options['port'], self.options['host'], ssl_options=ssl_options,
                                          xheaders=sickbeard.HANDLE_REVERSE_PROXY, protocol=protocol)
        except (BaseException, Exception):
            etype, evalue, etb = exc_info()
            logger.log('Could not start webserver on %s. Exception: %s, Error: %s' % (
                self.options['port'], etype, evalue), logger.ERROR)
            return

        self.io_loop = IOLoop.current()

        # add event set to be called first as soon as io_loop is started to inform other threads webserver has started
        self.io_loop.add_callback(self._ready_event.set)
        try:
            self.io_loop.start()
            self.io_loop.close(True)
        except (IOError, ValueError):
            # Ignore errors like 'ValueError: I/O operation on closed kqueue fd'. These might be thrown during a reload.
            pass

    def wait_server_start(self, timeout=30):
        if not self._ready_event.wait(timeout=timeout):
            raise Exception('Tornado Server failed to start')
        self._ready_event.clear()

    def switch_handlers(self, new_handler='_add_default_rules'):
        if hasattr(self, new_handler):
            def d_f(s, nh):
                s.app.reset_handlers()
                getattr(s, nh)()
                sickbeard.classes.loading_msg.reset()
            self.io_loop.add_callback(d_f, self, new_handler)
            logger.log('Switching HTTP Server handlers to %s' % new_handler, logger.DEBUG)

    def shut_down(self):
        self.alive = False
        if None is not self.io_loop:
            self.io_loop.add_callback(lambda x: x.stop(), self.io_loop)

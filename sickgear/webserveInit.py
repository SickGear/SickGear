import os
from sys import exc_info
import threading

from tornado.ioloop import IOLoop
from tornado.routing import AnyMatches, Rule
# noinspection PyProtectedMember
from tornado.web import Application, _ApplicationRouter

from . import logger, webapi, webserve
from .helpers import create_https_certificates, re_valid_hostname
import sickgear

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
        self.options['web_root'] = f'/{self.options["web_root"].lstrip("/")}' if self.options['web_root'] else ''

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
                        setattr(self, attr, os.path.join(ssl_path, f'server{ext}'))
                        setattr(sickgear, attr.upper(), f'server{ext}')
                    make_cert = True

            # If either the HTTPS certificate or key do not exist, make some self-signed ones.
            if make_cert:
                if not create_https_certificates(self.https_cert, self.https_key):
                    logger.log('Unable to create CERT/KEY files, disabling HTTPS')
                    update_cfg |= False is not sickgear.ENABLE_HTTPS
                    sickgear.ENABLE_HTTPS = False
                    self.enable_https = False
                else:
                    update_cfg = True

            if not (os.path.isfile(self.https_cert) and os.path.isfile(self.https_key)):
                logger.warning('Disabled HTTPS because of missing CERT and KEY files')
                update_cfg |= False is not sickgear.ENABLE_HTTPS
                sickgear.ENABLE_HTTPS = False
                self.enable_https = False

            if update_cfg:
                sickgear.save_config()

        # Load the app
        self.app = MyApplication([],
                                 debug=True,
                                 serve_traceback=True,
                                 autoreload=False,
                                 compress_response=True,
                                 cookie_secret=sickgear.COOKIE_SECRET,
                                 xsrf_cookies=True,
                                 login_url=f'{self.options["web_root"]}/login/',
                                 default_handler_class=webserve.WrongHostWebHandler)

        self.re_host_pattern = re_valid_hostname()
        self._add_loading_rules()

    def _add_loading_rules(self):
        self.app.is_loading_handler = True
        # webui login/logout handlers
        self.app.add_handlers(self.re_host_pattern, [
            (rf"{self.options['web_root']}/login(/?)", webserve.LoginHandler),
            (rf"{self.options['web_root']}/logout(/?)", webserve.LogoutHandler),
        ])

        # Static File Handlers
        self.app.add_handlers(self.re_host_pattern, [
            # favicon
            (rf"{self.options['web_root']}/(favicon\.ico)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images', 'ico')}),

            # images
            (rf"{self.options['web_root']}/images/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images')}),

            # css
            (rf"{self.options['web_root']}/css/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'css')}),

            # javascript
            (rf"{self.options['web_root']}/js/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'js')}),
        ])

        # Main Handler
        self.app.add_handlers(self.re_host_pattern, [
            (rf"{self.options['web_root']}/api(/?.*)", webapi.ApiServerLoading),
            (rf"{self.options['web_root']}/home/is-alive(/?.*)", webserve.IsAliveHandler),
            (rf"{self.options['web_root']}/ui(/?.*)", webserve.UI),
            (rf"{self.options['web_root']}(/?.*)", webserve.LoadingWebHandler),
            # ----------------------------------------------------------------------------------------------------------
            # legacy deprecated Aug 2019
            (rf"{self.options['web_root']}/home/is_alive(/?.*)", webserve.IsAliveHandler),
        ])

        self.app.add_handlers(r'.*', [(r'.*', webserve.WrongHostWebHandler)])

    def _add_default_rules(self):
        self.app.is_loading_handler = False
        # webui login/logout handlers
        self.app.add_handlers(self.re_host_pattern, [
            (rf"{self.options['web_root']}/login(/?)", webserve.LoginHandler),
            (rf"{self.options['web_root']}/logout(/?)", webserve.LogoutHandler),
        ])

        # Web calendar handler (Needed because option Unprotected calendar)
        self.app.add_handlers(self.re_host_pattern, [
            (rf"{self.options['web_root']}/calendar", webserve.CalendarHandler),
        ])

        # Static File Handlers
        self.app.add_handlers(self.re_host_pattern, [
            # favicon
            (rf"{self.options['web_root']}/(favicon\.ico)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images', 'ico')}),

            # images
            (rf"{self.options['web_root']}/images/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images')}),

            # cached images
            (rf"{self.options['web_root']}/cache/images/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(sickgear.CACHE_DIR, 'images')}),

            # css
            (rf"{self.options['web_root']}/css/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'css')}),

            # javascript
            (rf"{self.options['web_root']}/js/(.*)", webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'js')}),

            # logfile
            (rf"{self.options['web_root']}/logfile/(.*)", webserve.LogfileHandler),

            (rf"{self.options['web_root']}/kodi/((?:(?![|]verifypeer=false).)*)", webserve.RepoHandler,
             {'path': os.path.join(sickgear.CACHE_DIR, 'clients', 'kodi'),
              'default_filename': 'index.html'}),

            (rf"{self.options['web_root']}/kodi-legacy/((?:(?![|]verifypeer=false).)*)", webserve.RepoHandler,
             {'path': os.path.join(sickgear.CACHE_DIR, 'clients', 'kodi'),
              'default_filename': 'index.html', 'legacy': True}),
        ])

        # Main Handler
        self.app.add_handlers(self.re_host_pattern, [
            (rf"{self.options['web_root']}/ui(/?.*)", webserve.UI),
            (rf"{self.options['web_root']}/home/is-alive(/?.*)", webserve.IsAliveHandler),
            (rf"{self.options['web_root']}/imagecache(/?.*)", webserve.CachedImages),
            (rf"{self.options['web_root']}/cache(/?.*)", webserve.Cache),
            (rf"{self.options['web_root']}(/?update-watched-state-kodi/?)", webserve.NoXSRFHandler),
            (rf"{self.options['web_root']}(/?update-watched-state-kodi-legacy/?)", webserve.NoXSRFHandler,
             {'legacy': True}),
            (rf"{self.options['web_root']}/add-shows(/?.*)", webserve.AddShows),
            (rf"{self.options['web_root']}/home/process-media(/?.*)", webserve.HomeProcessMedia),
            (rf"{self.options['web_root']}/config/general(/?.*)", webserve.ConfigGeneral),
            (rf"{self.options['web_root']}/config/search(/?.*)", webserve.ConfigSearch),
            (rf"{self.options['web_root']}/config/providers(/?.*)", webserve.ConfigProviders),
            (rf"{self.options['web_root']}/config/media-process(/?.*)", webserve.ConfigMediaProcess),
            (rf"{self.options['web_root']}/config/subtitles(/?.*)", webserve.ConfigSubtitles),
            (rf"{self.options['web_root']}/config/notifications(/?.*)", webserve.ConfigNotifications),
            (rf"{self.options['web_root']}/config/anime(/?.*)", webserve.ConfigAnime),
            (rf"{self.options['web_root']}/manage/search-tasks(/?.*)", webserve.ManageSearch),
            (rf"{self.options['web_root']}/manage/show-tasks(/?.*)", webserve.ShowTasks),
            (rf"{self.options['web_root']}/api/builder(/?)(.*)", webserve.ApiBuilder),
            (rf"{self.options['web_root']}/api(/?.*)", webapi.Api),
            # ----------------------------------------------------------------------------------------------------------
            # legacy deprecated Aug 2019 - NEVER remove as used in external scripts
            (rf"{self.options['web_root']}/home/postprocess(/?.*)", webserve.HomeProcessMedia),
            # regular catchall routes - keep here at the bottom
            (rf"{self.options['web_root']}/home(/?.*)", webserve.Home),
            (rf"{self.options['web_root']}/manage/(/?.*)", webserve.Manage),
            (rf"{self.options['web_root']}/config(/?.*)", webserve.Config),
            (rf"{self.options['web_root']}/browser(/?.*)", webserve.WebFileBrowser),
            (rf"{self.options['web_root']}/errors(/?.*)", webserve.EventLogs),
            (rf"{self.options['web_root']}/events(/?.*)", webserve.EventLogs),
            (rf"{self.options['web_root']}/history(/?.*)", webserve.History),
            (rf"{self.options['web_root']}(/?.*)", webserve.MainHandler),
        ])

        self.app.add_handlers(r'.*', [(r'.*', webserve.WrongHostWebHandler)])

    def run(self):
        protocol, ssl_options = (('http', None),
                                 ('https', {'certfile': self.https_cert, 'keyfile': self.https_key}))[self.enable_https]

        logger.log(f'Starting SickGear on {protocol}://{self.options["host"]}:{self.options["port"]}/')

        # python 3 needs to start event loop first
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        from tornado.platform.asyncio import AnyThreadEventLoopPolicy
        asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())

        try:
            self.server = self.app.listen(self.options['port'], self.options['host'], ssl_options=ssl_options,
                                          xheaders=sickgear.HANDLE_REVERSE_PROXY, protocol=protocol)
        except (BaseException, Exception):
            etype, evalue, etb = exc_info()
            logger.error(f'Could not start webserver on {self.options["port"]}. Exception: {etype}, Error: {evalue}')
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
                sickgear.classes.loading_msg.reset()
            self.io_loop.add_callback(d_f, self, new_handler)
            logger.debug(f'Switching HTTP Server handlers to {new_handler}')

    def shut_down(self):
        self.alive = False
        if None is not self.io_loop:
            self.io_loop.add_callback(lambda x: x.stop(), self.io_loop)

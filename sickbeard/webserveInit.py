import os
import threading
import sys
import sickbeard
import webserve
import webapi

from sickbeard import logger
from sickbeard.helpers import create_https_certificates, re_valid_hostname
from tornado.web import Application, _ApplicationRouter
from tornado.ioloop import IOLoop
from tornado.routing import AnyMatches, Rule


class MyApplication(Application):

    def __init__(self, *args, **kwargs):
        super(MyApplication, self).__init__(*args, **kwargs)

    def reset_handlers(self):
        self.wildcard_router = _ApplicationRouter(self, [])
        self.default_router = _ApplicationRouter(self, [
            Rule(AnyMatches(), self.wildcard_router)
        ])


class WebServer(threading.Thread):
    def __init__(self, options=None):
        threading.Thread.__init__(self)
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
                                 login_url='%s/login/' % self.options['web_root'])

        self.re_host_pattern = re_valid_hostname()
        self._add_loading_rules()

    def _add_loading_rules(self):
        # webui login/logout handlers
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/login(/?)' % self.options['web_root'], webserve.LoginHandler),
            (r'%s/logout(/?)' % self.options['web_root'], webserve.LogoutHandler),
        ])

        # Static File Handlers
        self.app.add_handlers(self.re_host_pattern, [
            # favicon
            (r'%s/(favicon\.ico)' % self.options['web_root'], webserve.BaseStaticFileHandler,
             {'path': os.path.join(self.options['data_root'], 'images/ico/favicon.ico')}),

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
            (r'%s/home/is_alive(/?.*)' % self.options['web_root'], webserve.IsAliveHandler),
            (r'%s(/?.*)' % self.options['web_root'], webserve.LoadingWebHandler),
        ])

        self.app.add_handlers(r'.*', [(r'.*', webserve.WrongHostWebHandler)])

    def _add_default_rules(self):
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
             {'path': os.path.join(self.options['data_root'], 'images/ico/favicon.ico')}),

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

            (r'%s/kodi/(.*)' % self.options['web_root'], webserve.RepoHandler,
             {'path': os.path.join(sickbeard.CACHE_DIR, 'clients', 'kodi'),
              'default_filename': 'index.html'}),
        ])

        # Main Handler
        self.app.add_handlers(self.re_host_pattern, [
            (r'%s/api/builder(/?)(.*)' % self.options['web_root'], webserve.ApiBuilder),
            (r'%s/api(/?.*)' % self.options['web_root'], webapi.Api),
            (r'%s/imagecache(/?.*)' % self.options['web_root'], webserve.CachedImages),
            (r'%s/cache(/?.*)' % self.options['web_root'], webserve.Cache),
            (r'%s/config/general(/?.*)' % self.options['web_root'], webserve.ConfigGeneral),
            (r'%s/config/search(/?.*)' % self.options['web_root'], webserve.ConfigSearch),
            (r'%s/config/providers(/?.*)' % self.options['web_root'], webserve.ConfigProviders),
            (r'%s/config/subtitles(/?.*)' % self.options['web_root'], webserve.ConfigSubtitles),
            (r'%s/config/postProcessing(/?.*)' % self.options['web_root'], webserve.ConfigPostProcessing),
            (r'%s/config/notifications(/?.*)' % self.options['web_root'], webserve.ConfigNotifications),
            (r'%s/config/anime(/?.*)' % self.options['web_root'], webserve.ConfigAnime),
            (r'%s/config(/?.*)' % self.options['web_root'], webserve.Config),
            (r'%s/errorlogs(/?.*)' % self.options['web_root'], webserve.ErrorLogs),
            (r'%s/history(/?.*)' % self.options['web_root'], webserve.History),
            (r'%s/home/is_alive(/?.*)' % self.options['web_root'], webserve.IsAliveHandler),
            (r'%s/home/addShows(/?.*)' % self.options['web_root'], webserve.NewHomeAddShows),
            (r'%s/home/postprocess(/?.*)' % self.options['web_root'], webserve.HomePostProcess),
            (r'%s/home(/?.*)' % self.options['web_root'], webserve.Home),
            (r'%s/manage/manageSearches(/?.*)' % self.options['web_root'], webserve.ManageSearches),
            (r'%s/manage/showProcesses(/?.*)' % self.options['web_root'], webserve.showProcesses),
            (r'%s/manage/(/?.*)' % self.options['web_root'], webserve.Manage),
            (r'%s/ui(/?.*)' % self.options['web_root'], webserve.UI),
            (r'%s/browser(/?.*)' % self.options['web_root'], webserve.WebFileBrowser),
            (r'%s(/?update_watched_state_kodi/?)' % self.options['web_root'], webserve.NoXSRFHandler),
            (r'%s(/?.*)' % self.options['web_root'], webserve.MainHandler),
        ])

        self.app.add_handlers(r'.*', [(r'.*', webserve.WrongHostWebHandler)])

    def run(self):
        protocol, ssl_options = (('http', None),
                                 ('https', {'certfile': self.https_cert, 'keyfile': self.https_key}))[self.enable_https]

        logger.log(u'Starting SickGear on ' + protocol + '://' + str(self.options['host']) + ':' + str(
            self.options['port']) + '/')

        try:
            self.server = self.app.listen(self.options['port'], self.options['host'], ssl_options=ssl_options,
                                          xheaders=sickbeard.HANDLE_REVERSE_PROXY, protocol=protocol)
        except (StandardError, Exception):
            etype, evalue, etb = sys.exc_info()
            logger.log(
                'Could not start webserver on %s. Excpeption: %s, Error: %s' % (self.options['port'], etype, evalue),
                logger.ERROR)
            return

        self.io_loop = IOLoop.current()

        try:
            self.io_loop.start()
            self.io_loop.close(True)
        except (IOError, ValueError):
            # Ignore errors like 'ValueError: I/O operation on closed kqueue fd'. These might be thrown during a reload.
            pass

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
            self.io_loop.stop()

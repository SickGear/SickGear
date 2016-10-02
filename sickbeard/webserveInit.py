import os
import threading
import sys
import sickbeard
import webserve
import webapi

from sickbeard import logger
from sickbeard.helpers import create_https_certificates
from tornado.web import Application
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop


class WebServer(threading.Thread):
    def __init__(self, options={}, io_loop=None):
        threading.Thread.__init__(self)
        self.daemon = True
        self.alive = True
        self.name = 'TORNADO'
        self.io_loop = io_loop or IOLoop.current()

        self.options = options
        self.options.setdefault('port', 8081)
        self.options.setdefault('host', '0.0.0.0')
        self.options.setdefault('log_dir', None)
        self.options.setdefault('username', '')
        self.options.setdefault('password', '')
        self.options.setdefault('web_root', None)
        assert isinstance(self.options['port'], int)
        assert 'data_root' in self.options

        # web root
        self.options['web_root'] = ('/' + self.options['web_root'].lstrip('/')) if self.options[
            'web_root'] else ''

        # tornado setup
        self.enable_https = self.options['enable_https']
        self.https_cert = self.options['https_cert']
        self.https_key = self.options['https_key']

        if self.enable_https:
            # If either the HTTPS certificate or key do not exist, make some self-signed ones.
            if not (self.https_cert and os.path.exists(self.https_cert))\
                    or not (self.https_key and os.path.exists(self.https_key)):
                if not create_https_certificates(self.https_cert, self.https_key):
                    logger.log(u'Unable to create CERT/KEY files, disabling HTTPS')
                    sickbeard.ENABLE_HTTPS = False
                    self.enable_https = False

            if not (os.path.exists(self.https_cert) and os.path.exists(self.https_key)):
                logger.log(u'Disabled HTTPS because of missing CERT and KEY files', logger.WARNING)
                sickbeard.ENABLE_HTTPS = False
                self.enable_https = False

        # Load the app
        self.app = Application([],
                               debug=True,
                               autoreload=False,
                               gzip=True,
                               xheaders=sickbeard.HANDLE_REVERSE_PROXY,
                               cookie_secret=sickbeard.COOKIE_SECRET,
                               login_url='%s/login/' % self.options['web_root']
                               )

        # Main Handler
        self.app.add_handlers('.*$', [
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
            (r'%s/manage/showQueueOverview(/?.*)' % self.options['web_root'], webserve.showQueueOverview),
            (r'%s/manage/(/?.*)' % self.options['web_root'], webserve.Manage),
            (r'%s/ui(/?.*)' % self.options['web_root'], webserve.UI),
            (r'%s/browser(/?.*)' % self.options['web_root'], webserve.WebFileBrowser),
            (r'%s(/?.*)' % self.options['web_root'], webserve.MainHandler),
        ])

        # webui login/logout handlers
        self.app.add_handlers('.*$', [
            (r'%s/login(/?)' % self.options['web_root'], webserve.LoginHandler),
            (r'%s/logout(/?)' % self.options['web_root'], webserve.LogoutHandler),
        ])

        # Web calendar handler (Needed because option Unprotected calendar)
        self.app.add_handlers('.*$', [
            (r'%s/calendar' % self.options['web_root'], webserve.CalendarHandler),
        ])

        # Static File Handlers
        self.app.add_handlers('.*$', [
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
        ])

    def run(self):
        if self.enable_https:
            protocol = 'https'
            self.server = HTTPServer(self.app, ssl_options={'certfile': self.https_cert, 'keyfile': self.https_key})
        else:
            protocol = 'http'
            self.server = HTTPServer(self.app)

        logger.log(u'Starting SickGear on ' + protocol + '://' + str(self.options['host']) + ':' + str(
            self.options['port']) + '/')

        try:
            self.server.listen(self.options['port'], self.options['host'])
        except:
            etype, evalue, etb = sys.exc_info()
            logger.log(
                'Could not start webserver on %s. Excpeption: %s, Error: %s' % (self.options['port'], etype, evalue),
                logger.ERROR)
            return

        try:
            self.io_loop.start()
            self.io_loop.close(True)
        except (IOError, ValueError):
            # Ignore errors like 'ValueError: I/O operation on closed kqueue fd'. These might be thrown during a reload.
            pass

    def shutDown(self):
        self.alive = False
        self.io_loop.stop()
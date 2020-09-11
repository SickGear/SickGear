#!/usr/bin/env python

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

from __future__ import print_function
from __future__ import with_statement

import os.path
import sys
import warnings

sickbeardPath = os.path.split(os.path.split(sys.argv[0])[0])[0]
sys.path.insert(1, os.path.join(sickbeardPath, 'lib'))
sys.path.insert(1, sickbeardPath)

warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')
warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')

try:
    import requests
except ImportError:
    print('You need to install python requests library')
    sys.exit(1)

try:  # Try importing Python 3 modules
    import configparser
    # noinspection PyUnresolvedReferences
    import urllib.request as urllib2
    # noinspection PyUnresolvedReferences,PyCompatibility
    from urllib.parse import urlencode
except ImportError:  # On error, import Python 2 modules
    # noinspection PyPep8Naming,PyUnresolvedReferences
    import ConfigParser as configparser
    # noinspection PyUnresolvedReferences
    import urllib2
    # noinspection PyUnresolvedReferences
    from urllib import urlencode


# noinspection DuplicatedCode
def process_files(dir_to_process, org_nzb_name=None, status=None):
    # Default values
    host = 'localhost'
    port = '8081'
    default_url = 'http://%s:%s/' % (host, port)
    ssl = username = password = ''
    web_root = '/'

    # Get values from config_file
    config = configparser.RawConfigParser()
    config_filename = os.path.join(os.path.dirname(sys.argv[0]), 'autoProcessTV.cfg')

    if not os.path.isfile(config_filename):
        print('ERROR: %s doesn\'t exist' % config_filename)
        print('copy /rename %s.sample and edit\n' % config_filename)
        print('Trying default url: %s\n' % default_url)

    else:
        try:
            print('Loading config from %s\n' % config_filename)

            with open(config_filename, 'r') as fp:
                """ Under py3, `config.readfp` is flagged deprecated with advice to use read_file instead.
                However, py2 doesn't have `read_file`, so a little defensive coding is added here
                """
                if callable(getattr(config, 'read_file', None)):
                    config.read_file(fp)
                else:
                    # noinspection PyDeprecation
                    config.readfp(fp)

            # Replace default values with config_file values
            host = config.get('SickBeard', 'host')
            port = config.get('SickBeard', 'port')
            username = config.get('SickBeard', 'username')
            password = config.get('SickBeard', 'password')

            try:
                ssl = int(config.get('SickBeard', 'ssl')) and 's' or ''

            except (configparser.NoOptionError, ValueError):
                pass

            try:
                web_root = config.get('SickBeard', 'web_root')
                web_root = ('/%s/' % web_root.strip('/')).replace('//', '/')

            except configparser.NoOptionError:
                pass

        except EnvironmentError:
            e = sys.exc_info()[1]
            print('Could not read configuration file: ' + str(e))
            # There was a config_file, don't use default values but exit
            sys.exit(1)

    params = {'dir_name': dir_to_process, 'quiet': 1, 'is_basedir': 0}

    if None is not org_nzb_name:
        params['nzb_name'] = org_nzb_name

    if None is not status:
        params['failed'] = status

    url = 'http%s://%s:%s%s' % (ssl, host, port, web_root)
    login_url = url + 'login'
    url = url + 'home/process-media/files'

    print('Opening URL: ' + url)

    try:
        sess = requests.Session()
        if username or password:
            r = sess.get(login_url, verify=False)
            login_params = {'username': username, 'password': password}
            if 401 == r.status_code and r.cookies.get('_xsrf'):
                login_params['_xsrf'] = r.cookies.get('_xsrf')
            sess.post(login_url, data=login_params, stream=True, verify=False)
        result = sess.get(url, params=params, stream=True, verify=False)
        if 401 == result.status_code:
            print('Verify and use correct username and password in autoProcessTV.cfg')
        else:
            for line in result.iter_lines(decode_unicode=True):
                if line:
                    print(line.strip())

    except IOError:
        e = sys.exc_info()[1]
        print('Unable to open URL: ' + str(e))
        sys.exit(1)


if '__main__' == __name__:
    print('This module is supposed to be used as import in other scripts and not run standalone.')
    print('Use sabToSickBeard instead.')
    sys.exit(1)

#!/usr/bin/env python

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

warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')
warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')

# noinspection DuplicatedCode
versions = [((3, 10, 0), (3, 14, 2))]   # inclusive version ranges
if not any(list(map(lambda v: v[0] <= sys.version_info[:3] <= v[1], versions))) and not int(os.environ.get('PYT', 0)):
    major, minor, micro = sys.version_info[:3]
    print(f'Python {major}.{minor}.{micro} detected.')
    print('Sorry, SickGear requires a Python version %s' % ', '.join(map(
        lambda r: '%s - %s' % tuple(map(lambda v: str(v).replace(', ', '.')[1:-1], r)), versions)))
    sys.exit(1)

sg_path = os.path.split(os.path.split(sys.argv[0])[0])[0]
sys.path.insert(1, os.path.join(sg_path, 'lib'))
sys.path.insert(1, sg_path)

try:
    import requests
except ImportError:
    print('You must install python requests library')
    sys.exit(1)

try:  # Try importing Python 3 modules
    import configparser
    # noinspection PyUnresolvedReferences
    import urllib.request as urllib2
    # noinspection PyUnresolvedReferences,PyCompatibility
    from urllib.parse import urlencode
except ImportError:  # On error, exit
    sys.exit(1)


# noinspection DuplicatedCode
def process_files(dir_to_process, org_nzb_name=None, status=None):
    # Default values
    host = 'localhost'
    port = '8081'
    username = password = ''
    use_ssl = ''  # or 's'
    web_root = ''  # e.g. "/path"
    url = f'http{use_ssl}://{host}:{port}{web_root}'

    # Get values from config_file
    config = configparser.RawConfigParser()
    config_filename = os.path.join(os.path.dirname(sys.argv[0]), 'autoProcessTV.cfg')

    if not os.path.isfile(config_filename):
        print(f'ERROR: {config_filename} doesn\'t exist')
        print(f'copy/rename {config_filename}.sample and edit\n')
        print(f'Trying default url: {url}\n')

    else:
        try:
            print(f'Loading config from {config_filename}\n')

            with open(config_filename, 'r') as fp:
                config.read_file(fp)

            def cfg_get(cfg, option):
                try:
                    return cfg.get('SickGear', option)
                except (configparser.NoOptionError, configparser.NoSectionError):
                    return cfg.get('SickBeard', option)

            # Replace default values with config_file values
            host, port, username, password = [cfg_get(config, _option)
                                              for _option in ('host', 'port', 'username', 'password')]

            try:
                use_ssl = int(cfg_get(config, 'ssl')) and 's' or ''
            except (configparser.NoOptionError, ValueError, TypeError):
                pass

            try:
                web_root = cfg_get(config, 'web_root')
                web_root = web_root.strip('/').strip()
                web_root = any(web_root) and f'/{web_root}' or ''
            except configparser.NoOptionError:
                pass

            url = f'http{use_ssl}://{host}:{port}{web_root}'

        except EnvironmentError:
            e = sys.exc_info()[1]
            print(f'Could not read configuration file: {str(e)}')
            # There was a config_file, don't use default values but exit
            sys.exit(1)

    params = {'dir_name': dir_to_process, 'quiet': 1, 'is_basedir': 0}

    if None is not org_nzb_name:
        params['nzb_name'] = org_nzb_name

    if None is not status:
        params['failed'] = status

    login_url = f'{url}/login'
    url = f'{url}/home/process-media/files'

    print(f'Opening URL: {url}')

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
        print(f'Unable to open URL: {str(e)}')
        sys.exit(1)


if '__main__' == __name__:
    print('This module is supposed to be used as import in other scripts and not run standalone.')
    print('Use sabToSickGear instead.')
    sys.exit(1)

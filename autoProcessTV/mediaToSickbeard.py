#!/usr/bin/env python2
from __future__ import print_function
try:  # PY3
    import configparser
except ImportError:  # PY2
    # noinspection PyPep8Naming
    import ConfigParser as configparser
import logging
import os
import sys
import time
import warnings

sickbeardPath = os.path.split(os.path.split(sys.argv[0])[0])[0]
sys.path.insert(1, os.path.join(sickbeardPath, 'lib'))
sys.path.insert(1, sickbeardPath)
configFilename = os.path.join(sickbeardPath, 'config.ini')

warnings.filterwarnings('ignore', module=r'.*connectionpool.*', message='.*certificate verification.*')
warnings.filterwarnings('ignore', module=r'.*ssl_.*', message='.*SSLContext object.*')

try:
    import requests
except ImportError:
    print ('You need to install python requests library')
    sys.exit(1)

config = configparser.ConfigParser()

try:
    fp = open(configFilename, 'r')
    config.readfp(fp)
    fp.close()
except IOError as e:
    print('Could not find/read Sickbeard config.ini: ' + str(e))
    print(
        'Possibly wrong mediaToSickbeard.py location. Ensure the file is in the autoProcessTV subdir of your Sickbeard '
        'installation')
    time.sleep(3)
    sys.exit(1)

scriptlogger = logging.getLogger('mediaToSickbeard')
formatter = logging.Formatter('%(asctime)s %(levelname)-8s MEDIATOSICKBEARD :: %(message)s', '%b-%d %H:%M:%S')

# Get the log dir setting from SB config
logdirsetting = config.get('General', 'log_dir') if config.get('General', 'log_dir') else 'Logs'
# put the log dir inside the SickBeard dir, unless an absolute path
logdir = os.path.normpath(os.path.join(sickbeardPath, logdirsetting))
logfile = os.path.join(logdir, 'sickbeard.log')


try:
    handler = logging.FileHandler(logfile)
except (BaseException, Exception):
    print('Unable to open/create the log file at ' + logfile)
    time.sleep(3)
    sys.exit()

handler.setFormatter(formatter)
scriptlogger.addHandler(handler)
scriptlogger.setLevel(logging.DEBUG)


def utorrent():
    # print 'Calling utorrent'
    if 2 > len(sys.argv):
        scriptlogger.error('No folder supplied - is this being called from uTorrent?')
        print('No folder supplied - is this being called from uTorrent?')
        time.sleep(3)
        sys.exit()

    dirName = sys.argv[1]
    nzbName = sys.argv[2]

    return dirName, nzbName


def transmission():

    dirName = os.getenv('TR_TORRENT_DIR')
    nzbName = os.getenv('TR_TORRENT_NAME')

    return dirName, nzbName


# noinspection DuplicatedCode
def deluge():

    if 4 > len(sys.argv):
        scriptlogger.error('No folder supplied - is this being called from Deluge?')
        print('No folder supplied - is this being called from Deluge?')
        time.sleep(3)
        sys.exit()

    dirName = sys.argv[3]
    nzbName = sys.argv[2]

    return dirName, nzbName


def blackhole():

    if None is not os.getenv('TR_TORRENT_DIR'):
        scriptlogger.debug('Processing script triggered by Transmission')
        print('Processing script triggered by Transmission')
        scriptlogger.debug(u'TR_TORRENT_DIR: ' + os.getenv('TR_TORRENT_DIR'))
        scriptlogger.debug(u'TR_TORRENT_NAME: ' + os.getenv('TR_TORRENT_NAME'))
        dirName = os.getenv('TR_TORRENT_DIR')
        nzbName = os.getenv('TR_TORRENT_NAME')
    else:
        if 2 > len(sys.argv):
            scriptlogger.error('No folder supplied - Your client should invoke the script with a Dir and a Relese Name')
            print('No folder supplied - Your client should invoke the script with a Dir and a Release Name')
            time.sleep(3)
            sys.exit()

        dirName = sys.argv[1]
        nzbName = sys.argv[2]

    return dirName, nzbName


# noinspection DuplicatedCode
def main():
    scriptlogger.info(u'Starting external PostProcess script ' + __file__)

    host = config.get('General', 'web_host')
    port = config.get('General', 'web_port')
    username = config.get('General', 'web_username')
    password = config.get('General', 'web_password')
    try:
        ssl = int(config.get('General', 'enable_https'))
    except (configparser.NoOptionError, ValueError):
        ssl = 0

    try:
        web_root = config.get('General', 'web_root')
    except configparser.NoOptionError:
        web_root = ''

    tv_dir = config.get('General', 'tv_download_dir')
    use_torrents = int(config.get('General', 'use_torrents'))
    torrent_method = config.get('General', 'torrent_method')

    if not use_torrents:
        scriptlogger.error(u'Enable Use Torrent on Sickbeard to use this Script. Aborting!')
        print(u'Enable Use Torrent on Sickbeard to use this Script. Aborting!')
        time.sleep(3)
        sys.exit()

    if torrent_method not in ['utorrent', 'transmission', 'deluge', 'blackhole']:
        scriptlogger.error(u'Unknown Torrent Method. Aborting!')
        print(u'Unknown Torrent Method. Aborting!')
        time.sleep(3)
        sys.exit()

    dirName, nzbName = eval(locals()['torrent_method'])()

    if None is dirName:
        scriptlogger.error(u'MediaToSickbeard script need a dir to be run. Aborting!')
        print(u'MediaToSickbeard script need a dir to be run. Aborting!')
        time.sleep(3)
        sys.exit()

    if not os.path.isdir(dirName):
        scriptlogger.error(u'Folder ' + dirName + ' does not exist. Aborting AutoPostProcess.')
        print(u'Folder ' + dirName + ' does not exist. Aborting AutoPostProcess.')
        time.sleep(3)
        sys.exit()

    if nzbName and os.path.isdir(os.path.join(dirName, nzbName)):
        dirName = os.path.join(dirName, nzbName)

    params = {'dir_name': dirName, 'quiet': 1}

    if None is not nzbName:
        params['nzb_name'] = nzbName

    if ssl:
        protocol = 'https://'
    else:
        protocol = 'http://'

    if '0.0.0.0' == host:
        host = 'localhost'

    url = protocol + host + ':' + port + web_root + '/home/process-media/files'
    login_url = protocol + host + ':' + port + web_root + '/login'

    scriptlogger.debug('Opening URL: ' + url + ' with params=' + str(params))
    print('Opening URL: ' + url + ' with params=' + str(params))

    try:
        sess = requests.Session()
        if username or password:
            r = sess.get(login_url, verify=False)
            login_params = {'username': username, 'password': password}
            if 401 == r.status_code and r.cookies.get('_xsrf'):
                login_params['_xsrf'] = r.cookies.get('_xsrf')
            sess.post(login_url, data=login_params, stream=True, verify=False)
        response = sess.get(url, auth=(username, password), params=params, verify=False,  allow_redirects=False)
    except (BaseException, Exception) as _e:
        scriptlogger.error(u': Unknown exception raised when opening url: ' + str(_e))
        time.sleep(3)
        sys.exit()

    if 401 == response.status_code:
        scriptlogger.error(u'Verify and use correct username and password in autoProcessTV.cfg')
        print('Verify and use correct username and password in autoProcessTV.cfg')
        time.sleep(3)
        sys.exit()

    if 200 == response.status_code:
        scriptlogger.info(u'Script ' + __file__ + ' Succesfull')
        print('Script ' + __file__ + ' Succesfull')
        time.sleep(3)
        sys.exit()


if '__main__' == __name__:
    main()

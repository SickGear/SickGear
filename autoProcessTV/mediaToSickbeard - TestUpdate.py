#!/usr/bin/env python2
from __future__ import print_function
import sys
import os
import time
import ConfigParser
import logging
#
# todo: add 'qbittorrent' to list of available clients (line 146) and a function to pull args from sys.argv
#
sickgearPath = os.path.split(os.path.split(sys.argv[0])[0])[0]
sys.path.insert(1, os.path.join(sickgearPath, 'lib'))
sys.path.insert(1, sickgearPath)
configFilename = os.path.join(sickgearPath, 'config.ini')

try:
    import requests
except ImportError:
    print ('You need to install python requests library')
    sys.exit(1)

config = ConfigParser.ConfigParser()

try:
    fp = open(configFilename, 'r')
    config.readfp(fp)
    fp.close()
except IOError as e:
    print('Could not find/read SickGear config.ini: ' + str(e))
    print('Possibly wrong mediaToSickGear.py location. Ensure the file is in the autoProcessTV subdir of your SickGear'
          ' installation')
    time.sleep(3)
    sys.exit(1)

scriptlogger = logging.getLogger('mediaToSickGear')
formatter = logging.Formatter('%(asctime)s %(levelname)-8s MEDIATOSICKGEAR :: %(message)s', '%b-%d %H:%M:%S')

# Get the log dir setting from SB config
logdirsetting = config.get('General', 'log_dir') if config.get('General', 'log_dir') else 'Logs'
# put the log dir inside the SickGear dir, unless an absolute path
logdir = os.path.normpath(os.path.join(sickgearPath, logdirsetting))
logfile = os.path.join(logdir, 'sickbeard.log')


try:
    handler = logging.FileHandler(logfile)
except:
    print('Unable to open/create the log file at %s' % logfile)
    time.sleep(3)
    sys.exit()

handler.setFormatter(formatter)
scriptlogger.addHandler(handler)
scriptlogger.setLevel(logging.DEBUG)


def utorrent():
    # print('Calling utorrent')
    if 2 > len(sys.argv):
        msg = 'No folder supplied - is this being called from uTorrent?'
        scriptlogger.error(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

    dir_name = sys.argv[1]
    nzb_name = sys.argv[2]

    return dir_name, nzb_name


def transmission():

    dirname = os.getenv('TR_TORRENT_DIR')
    nzb_name = os.getenv('TR_TORRENT_NAME')

    return dirname, nzb_name


def deluge():

    if 4 > len(sys.argv):
        scriptlogger.error('No folder supplied - is this being called from Deluge?')
        print('No folder supplied - is this being called from Deluge?')
        time.sleep(3)
        sys.exit()

    dir_name = sys.argv[3]
    nzb_name = sys.argv[2]

    return dir_name, nzb_name


def blackhole():

    if None is not os.getenv('TR_TORRENT_DIR'):
        msg = 'Processing script triggered by Transmission'
        scriptlogger.debug(msg)
        print(msg)
        dir_name = os.getenv('TR_TORRENT_DIR')
        nzb_name = os.getenv('TR_TORRENT_NAME')
        scriptlogger.debug(u'TR_TORRENT_DIR: ' + dir_name)
        scriptlogger.debug(u'TR_TORRENT_NAME: ' + nzb_name)
    else:
        if len(sys.argv) < 2:
            scriptlogger.error('No folder supplied - Your client should invoke the script with a Dir and a Relese Name')
            print('No folder supplied - Your client should invoke the script with a Dir and a Release Name')
            time.sleep(3)
            sys.exit()

        dir_name = sys.argv[1]
        nzb_name = sys.argv[2]

    return dir_name, nzb_name


def main():
    scriptlogger.info(u'Starting external PostProcess script ' + __file__)

    host = config.get('General', 'web_host')
    port = config.get('General', 'web_port')
    username = config.get('General', 'web_username')
    password = config.get('General', 'web_password')
    try:
        ssl = int(config.get('General', 'enable_https'))
    except (ConfigParser.NoOptionError, ValueError):
        ssl = 0

    try:
        web_root = config.get('General', 'web_root')
    except ConfigParser.NoOptionError:
        web_root = ''

    tv_dir = config.get('General', 'tv_download_dir')
    use_torrents = int(config.get('General', 'use_torrents'))
    torrent_method = config.get('General', 'torrent_method')

    if not use_torrents:
        msg = 'Enable Use Torrent on Sickgear to use this Script. Aborting!'
        scriptlogger.error(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

    if torrent_method not in ['blackhole', 'deluge', 'transmission', 'utorrent']:
        msg = 'Unknown Torrent Method. Aborting!'
        scriptlogger.error(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

    dir_name, nzb_name = eval(locals()['torrent_method'])()

    if dir_name is None:
        msg = 'MediaToSickGear script need a dir to be run. Aborting!'
        scriptlogger.error(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

    if not os.path.isdir(dir_name):
        msg = u'Folder %s does not exist. Aborting AutoPostProcess.' % dir_name
        scriptlogger.error(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

    if nzb_name and os.path.isdir(os.path.join(dir_name, nzb_name)):
        dir_name = os.path.join(dir_name, nzb_name)

    params = {'quiet': 1, 'dir': dir_name}

    if None is not nzb_name:
        params['nzbName'] = nzb_name

    protocol = 'http%s://' % ('', 's')[ssl]

    if host == '0.0.0.0':
        host = 'localhost'

    domain = '%s%s:%s%s/' % (protocol, host, port, web_root)
    url = '%shome/postprocess/processEpisode' % domain
    login_url = '%slogin' % domain

    msg = 'Opening URL: %s with params=%s' % (url, str(params))
    scriptlogger.debug(msg)
    print(msg)

    try:
        sess = requests.Session()
        sess.post(login_url, data={'username': username, 'password': password}, stream=True, verify=False)
        response = sess.get(url, auth=(username, password), params=params, verify=False,  allow_redirects=False)
    except Exception as e:
        scriptlogger.error(u': Unknown exception raised when opening url: %s' % e)
        time.sleep(3)
        sys.exit()

    if 401 == response.status_code:
        msg = 'Verify and use correct username and password in autoProcessTV.cfg'
        scriptlogger.error(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

    if 200 == response.status_code:
        msg = u'Script  %s Successful' % __file__
        scriptlogger.info(msg)
        print(msg)
        time.sleep(3)
        sys.exit()

if __name__ == '__main__':
    main()

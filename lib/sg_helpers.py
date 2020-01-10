# encoding:utf-8
# ---------------
# functions are placed here to remove cyclic import issues from placement in helpers
#
import codecs
import getpass
import io
import logging
import os
import re
import socket
import stat
import tempfile
import traceback
# noinspection PyPep8Naming
import encodingKludge as ek
from exceptions_helper import ex
from _23 import filter_list, html_unescape, urlparse, urlunparse
from six import iteritems, string_types, text_type
from lib.cachecontrol import CacheControl, caches
from cfscrape import CloudflareScraper
import requests

# noinspection PyUnreachableCode
if False:
    # noinspection PyUnresolvedReferences
    from typing import Any, AnyStr, Dict, NoReturn, Iterable, Iterator, List, Optional, Tuple, Union
    from lxml_etree import etree

# Mapping error status codes to official W3C names
http_error_code = {
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',
    308: 'Permanent Redirect',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request-URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    429: 'Too Many Requests',
    431: 'Request Header Fields Too Large',
    444: 'No Response',
    451: 'Unavailable For Legal Reasons',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    511: 'Network Authentication Required'}

logger = logging.getLogger('sg_helper')
logger.addHandler(logging.NullHandler())

USER_AGENT = ''
CACHE_DIR = None
PROXY_SETTING = None
NOTIFIERS = None


# try to convert to int, if it fails the default will be returned
def try_int(s, s_default=0):
    try:
        return int(s)
    except (BaseException, Exception):
        return s_default


def _maybe_request_url(e, def_url=''):
    return hasattr(e, 'request') and hasattr(e.request, 'url') and ' ' + e.request.url or def_url


def clean_data(data):
    """Cleans up strings, lists, dicts returned

    Issues corrected:
    - Replaces &amp; with &
    - Trailing whitespace
    - Decode html entities
    :param data: data
    :type data: List or Dict or AnyStr
    :return:
    :rtype: List or Dict or AnyStr
    """

    if isinstance(data, list):
        return [clean_data(d) for d in data]
    if isinstance(data, dict):
        return {k: clean_data(v) for k, v in iteritems(data)}
    if isinstance(data, string_types):
        return html_unescape(data).strip().replace(u'&amp;', u'&')
    return data


def get_system_temp_dir():
    """
    :return: Returns the [system temp dir]/tvdb_api-u501 (or tvdb_api-myuser)
    :rtype: AnyStr
    """
    if hasattr(os, 'getuid'):
        uid = 'u%d' % (os.getuid())
    else:
        # For Windows
        try:
            uid = getpass.getuser()
        except ImportError:
            return ek.ek(os.path.join, tempfile.gettempdir(), 'SickGear')

    return ek.ek(os.path.join, tempfile.gettempdir(), 'SickGear-%s' % uid)


def proxy_setting(setting, request_url, force=False):
    """
    Returns a list of a) proxy_setting address value or a PAC is fetched and parsed if proxy_setting
    starts with "PAC:" (case-insensitive) and b) True/False if "PAC" is found in the proxy_setting.

    The PAC data parser is crude, javascript is not eval'd. The first "PROXY URL" found is extracted with a list
    of "url_a_part.url_remaining", "url_b_part.url_remaining", "url_n_part.url_remaining" and so on.
    Also, PAC data items are escaped for matching therefore regular expression items will not match a request_url.

    If force is True or request_url contains a PAC parsed data item then the PAC proxy address is returned else False.
    None is returned in the event of an error fetching PAC data.

    """

    # check for "PAC" usage
    match = re.search(r'^\s*PAC:\s*(.*)', setting, re.I)
    if not match:
        return setting, False
    pac_url = match.group(1)

    # prevent a recursive test with existing proxy setting when fetching PAC url
    global PROXY_SETTING
    proxy_setting_backup = PROXY_SETTING
    PROXY_SETTING = ''

    resp = ''
    try:
        resp = get_url(pac_url)
    except (BaseException, Exception):
        pass
    PROXY_SETTING = proxy_setting_backup

    if not resp:
        return None, False

    proxy_address = None
    request_url_match = False
    parsed_url = urlparse(request_url)
    netloc = parsed_url.netloc
    for pac_data in re.finditer(r"""(?:[^'"]*['"])([^.]+\.[^'"]*)(?:['"])""", resp, re.I):
        data = re.search(r"""PROXY\s+([^'"]+)""", pac_data.group(1), re.I)
        if data:
            if force:
                return data.group(1), True
            proxy_address = (proxy_address, data.group(1))[None is proxy_address]
        elif re.search(re.escape(pac_data.group(1)), netloc, re.I):
            request_url_match = True
            if None is not proxy_address:
                break

    if None is proxy_address:
        return None, True

    return (False, proxy_address)[request_url_match], True


def get_url(url,  # type: AnyStr
            post_data=None,  # type: Optional
            params=None,  # type: Optional
            headers=None,  # type: Optional[Dict]
            timeout=30,  # type: int
            session=None,  # type: Optional[requests.Session]
            parse_json=False,  # type: bool
            raise_status_code=False,  # type: bool
            raise_exceptions=False,  # type: bool
            as_binary=False,  # type: bool
            encoding=None,  # type: Optional[AnyStr]
            **kwargs
            ):
    # type: (...) -> Optional[Union[AnyStr, bool, bytes, Dict, Tuple[Union[Dict, List], requests.Session]]]
    """
    Either
    1) Returns a byte-string retrieved from the url provider.
    2) Return True/False if success after using kwargs 'savefile' set to file pathname.
    3) Returns Tuple response, session if success after setting kwargs 'resp_sess' True.
    4) JSON Dict if parse_json=True.

    :param url: url
    :param post_data: post data
    :param params:
    :param headers: headers to add
    :param timeout: timeout
    :param session: optional session object
    :param parse_json: return JSON Dict
    :param raise_status_code: raise exception for status codes
    :param raise_exceptions: raise exceptions
    :param as_binary: return bytes instead of text
    :param encoding: overwrite encoding return header if as_binary is False
    :param kwargs:
    :return:
    """

    response_attr = ('text', 'content')[as_binary]

    # selectively mute some errors
    mute = filter_list(lambda x: kwargs.pop(x, False), [
        'mute_connect_err', 'mute_read_timeout', 'mute_connect_timeout', 'mute_http_error'])

    # reuse or instantiate request session
    resp_sess = kwargs.pop('resp_sess', None)
    if None is session:
        session = CloudflareScraper.create_scraper()
        session.headers.update({'User-Agent': USER_AGENT})

    # download and save file or simply fetch url
    savename = kwargs.pop('savename', None)
    if savename:
        # session streaming
        session.stream = True

    if not kwargs.pop('nocache', False):
        cache_dir = CACHE_DIR or get_system_temp_dir()
        session = CacheControl(sess=session, cache=caches.FileCache(ek.ek(os.path.join, cache_dir, 'sessions')))

    provider = kwargs.pop('provider', None)

    # handle legacy uses of `json` param
    if kwargs.get('json'):
        parse_json = kwargs.pop('json')

    # session master headers
    req_headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Accept-Encoding': 'gzip,deflate'}
    if headers:
        req_headers.update(headers)
    if hasattr(session, 'reserved') and 'headers' in session.reserved:
        req_headers.update(session.reserved['headers'] or {})
    session.headers.update(req_headers)

    # session parameters
    session.params = params

    # session ssl verify
    session.verify = False

    # don't trust os environments (auth, proxies, ...)
    session.trust_env = False

    response = None
    try:
        # sanitise url
        parsed = list(urlparse(url))
        parsed[2] = re.sub('/{2,}', '/', parsed[2])  # replace two or more / with one
        url = urlunparse(parsed)

        # session proxies
        if PROXY_SETTING:
            (proxy_address, pac_found) = proxy_setting(PROXY_SETTING, url)
            msg = '%sproxy for url: %s' % (('', 'PAC parsed ')[pac_found], url)
            if None is proxy_address:
                logger.debug('Proxy error, aborted the request using %s' % msg)
                return
            elif proxy_address:
                logger.debug('Using %s' % msg)
                session.proxies = {'http': proxy_address, 'https': proxy_address}

        # decide if we get or post data to server
        if post_data or 'post_json' in kwargs:
            if True is post_data:
                post_data = None

            if post_data:
                kwargs.setdefault('data', post_data)

            if 'post_json' in kwargs:
                kwargs.setdefault('json', kwargs.pop('post_json'))

            response = session.post(url, timeout=timeout, **kwargs)
        else:
            response = session.get(url, timeout=timeout, **kwargs)
            if response.ok and not response.content and 'url=' in response.headers.get('Refresh', '').lower():
                url = response.headers.get('Refresh').lower().split('url=')[1].strip('/')
                if not url.startswith('http'):
                    parsed[2] = '/%s' % url
                    url = urlunparse(parsed)
                response = session.get(url, timeout=timeout, **kwargs)

        # if encoding is not in header try to use best guess
        # ignore downloads with savename
        if not savename and not as_binary:
            if encoding:
                response.encoding = encoding
            elif not response.encoding or 'charset' not in response.headers.get('Content-Type', ''):
                response.encoding = response.apparent_encoding

        # noinspection PyProtectedMember
        if provider and provider._has_signature(response.text):
            return getattr(response, response_attr)

        if raise_status_code:
            response.raise_for_status()

        if not response.ok:
            http_err_text = 'CloudFlare Ray ID' in response.text and \
                            'CloudFlare reports, "Website is offline"; ' or ''
            if response.status_code in http_error_code:
                http_err_text += http_error_code[response.status_code]
            elif response.status_code in range(520, 527):
                http_err_text += 'Origin server connection failure'
            else:
                http_err_text = 'Custom HTTP error code'
                if 'mute_http_error' not in mute:
                    logger.debug(u'Response not ok. %s: %s from requested url %s'
                                 % (response.status_code, http_err_text, url))
            return

    except requests.exceptions.HTTPError as e:
        if raise_status_code:
            response.raise_for_status()
        logger.warning(u'HTTP error %s while loading URL%s' % (
            e.errno, _maybe_request_url(e)))
        return
    except requests.exceptions.ConnectionError as e:
        if 'mute_connect_err' not in mute:
            logger.warning(u'Connection error msg:%s while loading URL%s' % (
                ex(e), _maybe_request_url(e)))
        if raise_exceptions:
            raise e
        return
    except requests.exceptions.ReadTimeout as e:
        if 'mute_read_timeout' not in mute:
            logger.warning(u'Read timed out msg:%s while loading URL%s' % (
                ex(e), _maybe_request_url(e)))
        if raise_exceptions:
            raise e
        return
    except (requests.exceptions.Timeout, socket.timeout) as e:
        if 'mute_connect_timeout' not in mute:
            logger.warning(u'Connection timed out msg:%s while loading URL %s' % (
                ex(e), _maybe_request_url(e, url)))
        if raise_exceptions:
            raise e
        return
    except (BaseException, Exception) as e:
        if ex(e):
            logger.warning(u'Exception caught while loading URL %s\r\nDetail... %s\r\n%s'
                           % (url, ex(e), traceback.format_exc()))
        else:
            logger.warning(u'Unknown exception while loading URL %s\r\nDetail... %s'
                           % (url, traceback.format_exc()))
        if raise_exceptions:
            raise e
        return

    if parse_json:
        try:
            data_json = response.json()
            if resp_sess:
                return ({}, data_json)[isinstance(data_json, (dict, list))], session
            return ({}, data_json)[isinstance(data_json, (dict, list))]
        except (TypeError, Exception) as e:
            logger.warning(u'JSON data issue from URL %s\r\nDetail... %s' % (url, ex(e)))
            if raise_exceptions:
                raise e
            return None

    if savename:
        try:
            write_file(savename, response, raw=True, raise_exceptions=raise_exceptions)
        except (BaseException, Exception) as e:
            if raise_exceptions:
                raise e
            return
        return True

    if resp_sess:
        return getattr(response, response_attr), session

    return getattr(response, response_attr)


def file_bit_filter(mode):
    for bit in [stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH, stat.S_ISUID, stat.S_ISGID]:
        if mode & bit:
            mode -= bit

    return mode


def remove_file_failed(filename):
    """
    delete given file

    :param filename: filename
    :type filename: AnyStr
    """
    try:
        ek.ek(os.remove, filename)
    except (BaseException, Exception):
        pass


def chmod_as_parent(child_path):
    """

    :param child_path: path
    :type child_path: AnyStr
    :return:
    :rtype: None
    """
    if os.name in ('nt', 'ce'):
        return

    parent_path = ek.ek(os.path.dirname, child_path)

    if not parent_path:
        logger.debug(u'No parent path provided in %s, unable to get permissions from it' % child_path)
        return

    parent_path_stat = ek.ek(os.stat, parent_path)
    parent_mode = stat.S_IMODE(parent_path_stat[stat.ST_MODE])

    child_path_stat = ek.ek(os.stat, child_path)
    child_path_mode = stat.S_IMODE(child_path_stat[stat.ST_MODE])

    if ek.ek(os.path.isfile, child_path):
        child_mode = file_bit_filter(parent_mode)
    else:
        child_mode = parent_mode

    if child_path_mode == child_mode:
        return

    child_path_owner = child_path_stat.st_uid
    user_id = os.geteuid()  # only available on UNIX

    if 0 != user_id and user_id != child_path_owner:
        logger.debug(u'Not running as root or owner of %s, not trying to set permissions' % child_path)
        return

    try:
        ek.ek(os.chmod, child_path, child_mode)
        logger.debug(u'Setting permissions for %s to %o as parent directory has %o'
                     % (child_path, child_mode, parent_mode))
    except OSError:
        logger.error(u'Failed to set permission for %s to %o' % (child_path, child_mode))


def make_dirs(path, syno=True):
    """
    Creates any folders that are missing and assigns them the permissions of their
    parents
    :param path: path
    :type path: AnyStr
    :param syno:
    :type syno: bool
    :return: success
    :rtype: bool
    """
    if not ek.ek(os.path.isdir, path):
        # Windows, create all missing folders
        if os.name in ('nt', 'ce'):
            try:
                logger.debug(u'Path %s doesn\'t exist, creating it' % path)
                ek.ek(os.makedirs, path)
            except (OSError, IOError) as e:
                logger.error(u'Failed creating %s : %s' % (path, ex(e)))
                return False

        # not Windows, create all missing folders and set permissions
        else:
            sofar = ''
            folder_list = path.split(os.path.sep)

            # look through each sub folder and make sure they all exist
            for cur_folder in folder_list:
                sofar += cur_folder + os.path.sep

                # if it exists then just keep walking down the line
                if ek.ek(os.path.isdir, sofar):
                    continue

                try:
                    logger.debug(u'Path %s doesn\'t exist, creating it' % sofar)
                    ek.ek(os.mkdir, sofar)
                    # use normpath to remove end separator, otherwise checks permissions against itself
                    chmod_as_parent(ek.ek(os.path.normpath, sofar))
                    # todo: reenable
                    if syno:
                        # do the library update for synoindex
                        NOTIFIERS.NotifierFactory().get('SYNOINDEX').addFolder(sofar)
                except (OSError, IOError) as e:
                    logger.error(u'Failed creating %s : %s' % (sofar, ex(e)))
                    return False

    return True


def write_file(filepath,  # type: AnyStr
               data,  # type: Union[AnyStr, etree.Element, requests.Response]
               raw=False,  # type: bool
               xmltree=False,  # type: bool
               utf8=False,  # type: bool
               raise_exceptions=False  # type: bool
               ):  # type: (...) -> bool
    """

    :param filepath: filepath
    :param data: data to write
    :param raw: write binary or text
    :param xmltree: use xmel tree
    :param utf8: use UTF8
    :param raise_exceptions: raise excepitons
    :return: succuess
    """
    result = False

    if make_dirs(ek.ek(os.path.dirname, filepath), False):
        try:
            if raw:
                with ek.ek(io.FileIO, filepath, 'wb') as fh:
                    for chunk in data.iter_content(chunk_size=1024):
                        if chunk:
                            fh.write(chunk)
                            fh.flush()
                    ek.ek(os.fsync, fh.fileno())
            else:
                w_mode = 'w'
                if utf8:
                    w_mode = 'a'
                    with ek.ek(io.FileIO, filepath, 'wb') as fh:
                        fh.write(codecs.BOM_UTF8)

                if xmltree:
                    with ek.ek(io.FileIO, filepath, w_mode) as fh:
                        if utf8:
                            data.write(fh, encoding='utf-8')
                        else:
                            data.write(fh)
                else:
                    if isinstance(data, text_type):
                        with ek.ek(io.open, filepath, w_mode, encoding='utf-8') as fh:
                            fh.write(data)
                    else:
                        with ek.ek(io.FileIO, filepath, w_mode) as fh:
                            fh.write(data)

            chmod_as_parent(filepath)

            result = True
        except (EnvironmentError, IOError) as e:
            logger.error('Unable to write file %s : %s' % (filepath, ex(e)))
            if raise_exceptions:
                raise e

    return result


def long_path(path):
    # type: (AnyStr) -> AnyStr
    """add long path prefix for Windows"""
    if 'nt' == os.name and 260 < len(path) and not path.startswith('\\\\?\\') and ek.ek(os.path.isabs, path):
        return '\\\\?\\' + path
    return path

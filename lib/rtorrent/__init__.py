# Copyright (c) 2013 Chris Lucas, <chris@chrisjlucas.com>
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS",  WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os.path
import time

from .lib.torrentparser import TorrentParser
from .lib.xmlrpc.basic_auth import BasicAuthTransport
from .lib.xmlrpc.http import HTTPServerProxy
from .lib.xmlrpc.scgi import SCGIServerProxy

from . import rpc
from .common import convert_version_tuple_to_str, find_torrent, is_valid_port, join_uri, update_uri
from .compat import urlparse, xmlrpclib
from .file import File, methods as file_methods
from .group import Group
from .peer import Peer, methods as peer_methods
from .rpc import Method
from .torrent import Torrent, methods as torrent_methods
from .tracker import Tracker, methods as tracker_methods

from _23 import filter_iter, filter_list, map_list


__version__ = '0.2.10'
__author__ = 'Chris Lucas'
__maintainer__ = 'SickGear'
__contact__ = 'chris@chrisjlucas.com'
__license__ = 'MIT'

MIN_RTORRENT_VERSION = (0, 8, 1)
MIN_RTORRENT_VERSION_STR = convert_version_tuple_to_str(MIN_RTORRENT_VERSION)


class RTorrent(object):
    """ Create a new rTorrent connection """
    rpc_prefix = None

    def __init__(self, uri, username=None, password=None, check_connection=True, sp=None, sp_kwargs=None):

        self.username = username
        self.password = password

        self.scheme, self.uri = self._transform_uri(uri)
        if sp:
            self.sp = sp
        elif self.scheme in ['http', 'https']:
            self.sp = HTTPServerProxy
        elif 'scgi' == self.scheme:
            self.sp = SCGIServerProxy
        else:
            raise NotImplementedError()

        self.sp_kwargs = sp_kwargs or {}

        self.torrents = []  # : List of L{Torrent} instances
        self._rpc_methods = []  # : List of rTorrent RPC methods
        self._torrent_cache = []
        self._client_version_tuple = ()
        self.use_target = False
        self.dht_port = None
        self.request_interval = 3

        if check_connection:
            self._check_connection()

    @staticmethod
    def _transform_uri(uri):
        scheme = urlparse(uri).scheme

        if 'httprpc' == scheme or scheme.startswith('httprpc+'):
            # Transform URI with new path and scheme
            uri = join_uri(uri, 'plugins/httprpc/action.php', construct=False)

            # Try find HTTPRPC transport (token after '+' in 'httprpc+https'), otherwise assume HTTP
            transport = 'http' if '+' not in scheme else scheme[scheme.index('+') + 1:]

            uri = update_uri(uri, scheme=transport)

        return urlparse(uri).scheme, uri

    def get_connection(self):
        """Get ServerProxy instance"""

        if not (self.username and self.password):
            return self.sp(self.uri, **self.sp_kwargs)

        if 'scgi' == self.scheme:
            raise NotImplementedError()

        return self.sp(self.uri,
                       transport=BasicAuthTransport('https' == self.scheme, self.username, self.password),
                       **self.sp_kwargs)

    def test_connection(self):
        """
        Test connection to rT
        :return: True of connection successful, otherwise False
        :rtype: Boolean
        """
        try:
            self._check_connection()
            return True
        except (BaseException, Exception):
            return False

    def _check_connection(self):
        # check for rpc methods that should be available
        assert self.method_exists('system.client_version'), \
            'Required RPC method (client_version) not available. Check connection settings in client.'
        assert self.method_exists('system.library_version'), \
            'Required RPC method (system.library_version) not available. Check connection settings in client.'

        # minimum rTorrent version check
        assert self._meets_version_requirement() is True, \
            'Error: Minimum rTorrent version required is %s' % MIN_RTORRENT_VERSION_STR

    def method_exists(self, name):
        """
        Check if rpc method exists
        :param name: Name of method
        :type name: str
        :return: True if method is found
        :rtype: Boolean
        """
        return name in self.get_rpc_methods()

    def get_rpc_methods(self):
        """ Get list of raw RPC commands

        @return: raw RPC commands
        @rtype: list
        """

        return self._rpc_methods or self._fetch_rpc_methods()

    def _fetch_rpc_methods(self):

        self._rpc_methods = self.get_connection().system.listMethods()

        return self._rpc_methods

    def _meets_version_requirement(self):
        return self.get_client_version_tuple() >= MIN_RTORRENT_VERSION

    def get_client_version_tuple(self):
        conn = self.get_connection()

        if not self._client_version_tuple:
            if not hasattr(self, 'client_version'):
                setattr(self, 'client_version',
                        conn.system.client_version())

            rtver = getattr(self, 'client_version')
            self._client_version_tuple = tuple([int(i) for i in
                                                rtver.split('.')])

        return self._client_version_tuple

    def get_torrents(self, view='main'):
        """Get list of all torrents in specified view

        @return: list of L{Torrent} instances

        @rtype: list

        @todo: add validity check for specified view
        """
        self.torrents = []
        retriever_methods = filter_list(lambda m: m.is_retriever() and m.is_available(self), torrent_methods)
        mc = rpc.Multicall(self)

        if self.method_exists('d.multicall2'):
            mc.add('d.multicall2', '', view, 'd.hash=',
                   *map_list(lambda m2: ((getattr(m2, 'aliases') or [''])[-1] or m2.rpc_call) + '=', retriever_methods))
        else:
            mc.add('d.multicall', view, 'd.get_hash=',
                   *map_list(lambda m1: m1.rpc_call + '=', retriever_methods))

        results = mc.call()[0]  # only sent one call, only need first result

        for result in results:
            self.torrents.append(
                Torrent(self, info_hash=result[0],
                        **dict((mc.varname, rpc.process_result(mc, r))
                               for (mc, r) in list(zip(retriever_methods, result[1:])))))  # result[0]=info_hash

        self._manage_torrent_cache()
        return self.torrents

    def _manage_torrent_cache(self):
        """Carry tracker/peer/file lists over to new torrent list"""
        for t in self._torrent_cache:
            new_torrent = common.find_torrent(t.info_hash, self.torrents)
            if new_torrent is not None:
                new_torrent.files = t.files
                new_torrent.peers = t.peers
                new_torrent.trackers = t.trackers

        self._torrent_cache = self.torrents

    def _get_load_function(self, file_type, start, verbose):
        """Determine correct "load torrent" RPC method"""
        func_name = file_type in ('url', 'file', 'raw') and (
            dict(sv='load_raw_start_verbose', s='load_raw_start', v='load_raw_verbose', ld='load_raw'),
            dict(sv='load_start_verbose', s='load_start', v='load_verbose', ld='load')
        )['url' == file_type][
            ((('ld', 'v')[verbose], 's')[start], 'sv')[start and verbose]] or None

        if not self.method_exists(func_name):
            if 'load' == func_name:
                func_name = 'load.normal'
            func_name = func_name.replace('load_', 'load.')
            if not self.method_exists(func_name):
                func_name = None

        return func_name

    def execute_func(self, func_name, param=None, extra=None):
        
        param = ([param], param)[isinstance(param, list)]
        for x in (extra or []):
            try:
                call, arg = x.split('=')
                method = rpc.find_method(call)
                method_name = next(filter_iter(lambda m: self.method_exists(m), (method.rpc_call,) + method.aliases))
                param += ['%s=%s' % (method_name, arg)]
            except (BaseException, Exception):
                pass

        method = getattr(self.get_connection(), func_name)

        if not self.use_target:
            try:
                method(*param)
            except (BaseException, Exception):
                self.use_target = True
        if self.use_target:
            method('', *param)

    def load_magnet(self, magneturl, info_hash, extra=None, start=False, verbose=False, verify_load=True):

        func_name = self._get_load_function('url', start, verbose)
        # load magnet
        self.execute_func(func_name, magneturl, extra)

        t = None
        if verify_load:
            info_hash = info_hash.upper()
            max_retries = 10
            while max_retries:
                try:
                    t = next(filter_iter(lambda td: td.info_hash.upper() == info_hash, self.get_torrents()))
                    break
                except (BaseException, Exception):
                    time.sleep(self.request_interval)
                    max_retries -= 1

        return t

    def load_torrent(self, data, extra=None, start=False, verbose=False, verify_load=True, verify_retries=3):
        """
        Loads torrent into rTorrent (with various enhancements)

        @param data: can be a url, a path to a local file, or the raw data
        of a torrent file
        @type data: str

        @param extra: extra commands to send
        @type extra: array

        @param start: start torrent when loaded
        @type start: bool

        @param verbose: print error messages to rTorrent log
        @type verbose: bool

        @param verify_load: verify that torrent was added to rTorrent successfully
        @type verify_load: bool

        @param verify_retries: number of times to attempt verification
        @type verify_load: int

        @return: Depends on verify_load:
                 - if verify_load is True, (and the torrent was
                 loaded successfully), it'll return a L{Torrent} instance
                 - if verify_load is False, it'll return None

        @rtype: L{Torrent} instance or None

        @raise AssertionError: If the torrent wasn't successfully added to rTorrent
                               - Check L{TorrentParser} for the AssertionError's
                               it raises


        @note: Because this function includes url verification (if a url was input)
        as well as verification as to whether the torrent was successfully added,
        this function doesn't execute instantaneously. If that's what you're
        looking for, use load_torrent_simple() instead.
        """
        tp = TorrentParser(data)
        info_hash = tp.info_hash

        # load torrent
        self.execute_func(self._get_load_function('url', False, False), '')
        self.execute_func(self._get_load_function('raw', start, verbose), xmlrpclib.Binary(tp.raw_torrent), extra)

        t = None
        if verify_load:
            while verify_retries:
                try:
                    t = next(filter_iter(lambda td: td.info_hash == info_hash, self.get_torrents()))
                    break
                except (BaseException, Exception):
                    time.sleep(self.request_interval)
                    verify_retries -= 1

            assert None is not t, 'Adding torrent was unsuccessful.'

        return t

    def load_torrent_simple(self, data, file_type, extra=None, start=False, verbose=False):
        """Loads torrent into rTorrent

        @param data: can be a url, a path to a local file, or the raw data
        of a torrent file
        @type data: str

        @param file_type: valid options: "url", "file", or "raw"
        @type file_type: str

        @param extra: extra commands to send
        @type extra: array

        @param start: start torrent when loaded
        @type start: bool

        @param verbose: print error messages to rTorrent log
        @type verbose: bool

        @return: None

        @raise AssertionError: if incorrect file_type is specified

        @note: This function was written for speed, it includes no enhancements.
        If you input a url, it won't check if it's valid. You also can't get
        verification that the torrent was successfully added to rTorrent.
        Use load_torrent() if you would like these features.
        """
        assert file_type in ['raw', 'file', 'url'], \
            'Invalid file_type, options are: \'url\', \'file\', \'raw\'.'
        func_name = self._get_load_function(file_type, start, verbose)

        if 'file' == file_type:
            # since we have to assume we're connected to a remote rTorrent
            # client, we have to read the file and send it to rT as raw
            assert os.path.isfile(data), \
                'Invalid path: "{0}"'.format(data)
            data = open(data, 'rb').read()
        elif 'raw' == file_type:
            self.execute_func(self._get_load_function('url', False, False), '')

        finput = None
        if file_type in ['raw', 'file']:
            finput = xmlrpclib.Binary(data)
        elif 'url' == file_type:
            finput = data

        self.execute_func(func_name, finput, extra)

    def get_views(self):
        p = self.get_connection()
        return p.view_list()

    def create_group(self, name, persistent=True, view=None):
        p = self.get_connection()

        if persistent is True:
            p.group.insert_persistent_view('', name)
        else:
            assert view is not None, 'view parameter required on non-persistent groups'
            p.group.insert('', name, view)

        self._fetch_rpc_methods()

    def get_group(self, name):
        assert name is not None, 'group name required'

        grp = Group(self, name)
        grp.update()
        return grp

    def set_dht_port(self, port):
        """Set DHT port

        @param port: port
        @type port: int

        @raise AssertionError: if invalid port is given
        """
        assert is_valid_port(port), 'Valid port range is 0-65535'
        # noinspection PyUnresolvedReferences
        self.dht_port = self._p.set_dht_port(port)

    def enable_check_hash(self):
        """Alias for set_check_hash(True)"""
        # noinspection PyUnresolvedReferences
        self.set_check_hash(True)

    def disable_check_hash(self):
        """Alias for set_check_hash(False)"""
        # noinspection PyUnresolvedReferences
        self.set_check_hash(False)

    def find_torrent(self, info_hash):
        """Frontend for common.find_torrent"""
        return common.find_torrent(info_hash, self.get_torrents())

    def has_local_id(self, info_hash):
        method = rpc.find_method('d.get_local_id')
        result = True
        try:
            func = next(filter_iter(lambda m: self.method_exists(m), (method.rpc_call,) + method.aliases))
            getattr(self.get_connection(), func)(info_hash)
        except(xmlrpclib.Fault, BaseException):
            result = False
        return result

    def poll(self):
        """ poll rTorrent to get latest torrent/peer/tracker/file information

        @note: This essentially refreshes every aspect of the rTorrent
        connection, so it can be very slow if working with a remote
        connection that has a lot of torrents loaded.

        @return: None
        """
        self.update()
        torrents = self.get_torrents()
        for t in torrents:
            t.poll()

    def update(self):
        """Refresh rTorrent client info

        @note: All fields are stored as attributes to self.

        @return: None
        """
        mc = rpc.Multicall(self)

        for method in filter_iter(lambda m: m.is_retriever() and m.is_available(self), methods):
            mc.add(method)

        mc.call()


def _build_class_methods(class_obj):
    # multicall add class
    caller = (lambda self, mc, method, *args: mc.add(method, self.rpc_id, *args))

    caller.__doc__ = """Same as Multicall.add(), but with automatic inclusion
                        of the rpc_id

                        @param multicall: A L{Multicall} instance
                        @type: multicall: Multicall

                        @param method: L{Method} instance or raw rpc method
                        @type: Method or str

                        @param args: optional arguments to pass
                        """
    setattr(class_obj, 'multicall_add', caller)


def __compare_rpc_methods(rt_new, rt_old):
    from pprint import pprint
    rt_new_methods = set(rt_new.get_rpc_methods())
    rt_old_methods = set(rt_old.get_rpc_methods())
    print('New Methods:')
    pprint(rt_new_methods - rt_old_methods)
    print('Methods not in new rTorrent:')
    pprint(rt_old_methods - rt_new_methods)


def __check_supported_methods(rt):
    from pprint import pprint
    supported_methods = set(
        [m.rpc_call for m in methods + file_methods + torrent_methods + tracker_methods + peer_methods])
    all_methods = set(rt.get_rpc_methods())

    print('Methods NOT in supported methods')
    pprint(all_methods - supported_methods)
    print('Supported methods NOT in all methods')
    pprint(supported_methods - all_methods)


methods = [
    # RETRIEVERS
    Method(RTorrent, 'get_xmlrpc_size_limit', 'get_xmlrpc_size_limit',
           aliases=('network.xmlrpc.size_limit',)),
    Method(RTorrent, 'get_proxy_address', 'get_proxy_address',
           aliases=('network.proxy_address',)),
    Method(RTorrent, 'get_split_suffix', 'get_split_suffix',
           aliases=('system.file.split_suffix',)),
    Method(RTorrent, 'get_up_limit', 'get_upload_rate',
           aliases=('throttle.global_up.max_rate',)),
    Method(RTorrent, 'get_max_memory_usage', 'get_max_memory_usage',
           aliases=('pieces.memory.max',)),
    Method(RTorrent, 'get_max_open_files', 'get_max_open_files',
           aliases=('network.max_open_files',)),
    Method(RTorrent, 'get_min_peers_seed', 'get_min_peers_seed',
           aliases=('throttle.min_peers.seed',)),
    Method(RTorrent, 'get_use_udp_trackers', 'get_use_udp_trackers',
           aliases=('trackers.use_udp',)),
    Method(RTorrent, 'get_preload_min_size', 'get_preload_min_size',
           aliases=('pieces.preload.min_size',)),
    Method(RTorrent, 'get_max_uploads', 'get_max_uploads',
           aliases=('throttle.max_uploads',)),
    Method(RTorrent, 'get_max_peers', 'get_max_peers',
           aliases=('throttle.max_peers.normal',)),
    Method(RTorrent, 'get_timeout_sync', 'get_timeout_sync',
           aliases=('pieces.sync.timeout',)),
    Method(RTorrent, 'get_receive_buffer_size', 'get_receive_buffer_size',
           aliases=('network.receive_buffer.size',)),
    Method(RTorrent, 'get_split_file_size', 'get_split_file_size',
           aliases=('system.file.split_size',)),
    Method(RTorrent, 'get_dht_throttle', 'get_dht_throttle',
           aliases=('dht.throttle.name',)),
    Method(RTorrent, 'get_max_peers_seed', 'get_max_peers_seed',
           aliases=('throttle.max_peers.seed',)),
    Method(RTorrent, 'get_min_peers', 'get_min_peers',
           aliases=('throttle.min_peers.normal',)),
    Method(RTorrent, 'get_tracker_numwant', 'get_tracker_numwant',
           aliases=('trackers.numwant',)),
    Method(RTorrent, 'get_max_open_sockets', 'get_max_open_sockets',
           aliases=('network.max_open_sockets',)),
    Method(RTorrent, 'get_session', 'get_session',
           aliases=('session.path',)),
    Method(RTorrent, 'get_ip', 'get_ip',
           aliases=('network.local_address',)),
    Method(RTorrent, 'get_scgi_dont_route', 'get_scgi_dont_route',
           aliases=('network.scgi.dont_route',)),
    Method(RTorrent, 'get_hash_read_ahead', 'get_hash_read_ahead'),
    Method(RTorrent, 'get_http_cacert', 'get_http_cacert',
           aliases=('network.http.cacert',)),
    Method(RTorrent, 'get_dht_port', 'get_dht_port',
           aliases=('dht.port',)),
    Method(RTorrent, 'get_handshake_log', 'get_handshake_log'),
    Method(RTorrent, 'get_preload_type', 'get_preload_type',
           aliases=('pieces.preload.type',)),
    Method(RTorrent, 'get_max_open_http', 'get_max_open_http',
           aliases=('network.http.max_open',)),
    Method(RTorrent, 'get_http_capath', 'get_http_capath',
           aliases=('network.http.capath',)),
    Method(RTorrent, 'get_max_downloads_global', 'get_max_downloads_global',
           aliases=('throttle.max_downloads.global',)),
    Method(RTorrent, 'get_name', 'get_name',
           aliases=('session.name',)),
    Method(RTorrent, 'get_session_on_completion', 'get_session_on_completion',
           aliases=('session.on_completion',)),
    Method(RTorrent, 'get_down_limit', 'get_download_rate',
           aliases=('throttle.global_down.max_rate',)),
    Method(RTorrent, 'get_down_total', 'get_down_total',
           aliases=('throttle.global_down.total',)),
    Method(RTorrent, 'get_up_rate', 'get_up_rate',
           aliases=('throttle.global_up.rate',)),
    Method(RTorrent, 'get_hash_max_tries', 'get_hash_max_tries'),
    Method(RTorrent, 'get_peer_exchange', 'get_peer_exchange',
           aliases=('protocol.pex',)),
    Method(RTorrent, 'get_down_rate', 'get_down_rate',
           aliases=('throttle.global_down.rate',)),
    Method(RTorrent, 'get_connection_seed', 'get_connection_seed',
           aliases=('protocol.connection.seed',)),
    Method(RTorrent, 'get_http_proxy', 'get_http_proxy',
           aliases=('network.http.proxy_address',)),
    Method(RTorrent, 'get_stats_preloaded', 'get_stats_preloaded',
           aliases=('pieces.stats_preloaded',)),
    Method(RTorrent, 'get_timeout_safe_sync', 'get_timeout_safe_sync',
           aliases=('pieces.sync.timeout_safe',)),
    Method(RTorrent, 'get_hash_interval', 'get_hash_interval'),
    Method(RTorrent, 'get_port_random', 'get_port_random',
           aliases=('network.port_random',)),
    Method(RTorrent, 'get_directory', 'get_directory',
           aliases=('directory.default',)),
    Method(RTorrent, 'get_port_open', 'get_port_open',
           aliases=('network.port_open',)),
    Method(RTorrent, 'get_max_file_size', 'get_max_file_size',
           aliases=('system.file.max_size',)),
    Method(RTorrent, 'get_stats_not_preloaded', 'get_stats_not_preloaded',
           aliases=('pieces.stats_not_preloaded',)),
    Method(RTorrent, 'get_memory_usage', 'get_memory_usage',
           aliases=('pieces.memory.current',)),
    Method(RTorrent, 'get_connection_leech', 'get_connection_leech',
           aliases=('protocol.connection.leech',)),
    Method(RTorrent, 'get_check_hash', 'get_check_hash',
           boolean=True,
           aliases=('pieces.hash.on_completion',)
           ),
    Method(RTorrent, 'get_session_lock', 'get_session_lock',
           aliases=('session.use_lock',)),
    Method(RTorrent, 'get_preload_required_rate', 'get_preload_required_rate',
           aliases=('pieces.preload.min_rate',)),
    Method(RTorrent, 'get_max_uploads_global', 'get_max_uploads_global',
           aliases=('throttle.max_uploads.global',)),
    Method(RTorrent, 'get_send_buffer_size', 'get_send_buffer_size',
           aliases=('network.send_buffer.size',)),
    Method(RTorrent, 'get_port_range', 'get_port_range',
           aliases=('network.port_range',)),
    Method(RTorrent, 'get_max_downloads_div', 'get_max_downloads_div',
           aliases=('throttle.max_downloads.div',)),
    Method(RTorrent, 'get_max_uploads_div', 'get_max_uploads_div',
           aliases=('throttle.max_uploads.div',)),
    Method(RTorrent, 'get_safe_sync', 'get_safe_sync',
           aliases=('pieces.sync.always_safe',)),
    Method(RTorrent, 'get_bind', 'get_bind',
           aliases=('network.bind_address',)),
    Method(RTorrent, 'get_up_total', 'get_up_total',
           aliases=('throttle.global_up.total',)),
    Method(RTorrent, 'get_client_version', 'system.client_version'),
    Method(RTorrent, 'get_library_version', 'system.library_version'),
    Method(RTorrent, 'get_api_version', 'system.api_version',
           min_version=(0, 9, 1)
           ),
    Method(RTorrent, 'get_system_time', 'system.time',
           docstring="""Get the current time of the system rTorrent is running on

           @return: time (posix)
           @rtype: int""",
           ),

    # MODIFIERS
    Method(RTorrent, 'set_http_proxy', 'set_http_proxy',
           aliases=('network.http.proxy_address.set',)),
    Method(RTorrent, 'set_max_memory_usage', 'set_max_memory_usage',
           aliases=('pieces.memory.max.set',)),
    Method(RTorrent, 'set_max_file_size', 'set_max_file_size',
           aliases=('system.file.max_size.set',)),
    Method(RTorrent, 'set_bind', 'set_bind',
           docstring="""Set address bind

           @param arg: ip address
           @type arg: str
           """,
           aliases=('network.bind_address.set',)
           ),
    Method(RTorrent, 'set_up_limit', 'set_upload_rate',
           docstring="""Set global upload limit (in bytes)

           @param arg: speed limit
           @type arg: int
           """,
           aliases=('throttle.global_up.max_rate.set',)
           ),
    Method(RTorrent, 'set_port_random', 'set_port_random',
           aliases=('network.port_random.set',)),
    Method(RTorrent, 'set_connection_leech', 'set_connection_leech',
           aliases=('protocol.connection.leech.set',)),
    Method(RTorrent, 'set_tracker_numwant', 'set_tracker_numwant',
           aliases=('trackers.numwant.set',)),
    Method(RTorrent, 'set_max_peers', 'set_max_peers',
           aliases=('throttle.max_peers.normal.set',)),
    Method(RTorrent, 'set_min_peers', 'set_min_peers',
           aliases=('throttle.min_peers.normal.set',)),
    Method(RTorrent, 'set_max_uploads_div', 'set_max_uploads_div',
           aliases=('throttle.max_uploads.div.set',)),
    Method(RTorrent, 'set_max_open_files', 'set_max_open_files',
           aliases=('network.max_open_files.set',)),
    Method(RTorrent, 'set_max_downloads_global', 'set_max_downloads_global',
           aliases=('throttle.max_downloads.global.set',)),
    Method(RTorrent, 'set_session_lock', 'set_session_lock',
           aliases=('session.use_lock.set',)),
    Method(RTorrent, 'set_session', 'set_session',
           aliases=('session.path.set',)),
    Method(RTorrent, 'set_split_suffix', 'set_split_suffix',
           aliases=('system.file.split_suffix.set',)),
    Method(RTorrent, 'set_hash_interval', 'set_hash_interval'),
    Method(RTorrent, 'set_handshake_log', 'set_handshake_log'),
    Method(RTorrent, 'set_port_range', 'set_port_range',
           aliases=('network.port_range.set',)),
    Method(RTorrent, 'set_min_peers_seed', 'set_min_peers_seed',
           aliases=('throttle.min_peers.seed.set',)),
    Method(RTorrent, 'set_scgi_dont_route', 'set_scgi_dont_route',
           aliases=('network.scgi.dont_route.set',)),
    Method(RTorrent, 'set_preload_min_size', 'set_preload_min_size',
           aliases=('pieces.preload.min_size.set',)),
    Method(RTorrent, 'set_log.tracker', 'set_log.tracker'),
    Method(RTorrent, 'set_max_uploads_global', 'set_max_uploads_global',
           aliases=('throttle.max_uploads.global.set',)),
    Method(RTorrent, 'set_down_limit', 'set_download_rate',
           docstring="""Set global download limit (in bytes)

           @param arg: speed limit
           @type arg: int
           """,
           aliases=('throttle.global_down.max_rate.set',)
           ),
    Method(RTorrent, 'set_preload_required_rate', 'set_preload_required_rate',
           aliases=('pieces.preload.min_rate.set',)),
    Method(RTorrent, 'set_hash_read_ahead', 'set_hash_read_ahead'),
    Method(RTorrent, 'set_max_peers_seed', 'set_max_peers_seed',
           aliases=('throttle.max_peers.seed.set',)),
    Method(RTorrent, 'set_max_uploads', 'set_max_uploads',
           aliases=('throttle.max_uploads.set',)),
    Method(RTorrent, 'set_session_on_completion', 'set_session_on_completion',
           aliases=('session.on_completion.set',)),
    Method(RTorrent, 'set_max_open_http', 'set_max_open_http',
           aliases=('network.http.max_open.set',)),
    Method(RTorrent, 'set_directory', 'set_directory',
           aliases=('directory.default.set',)),
    Method(RTorrent, 'set_http_cacert', 'set_http_cacert',
           aliases=('network.http.cacert.set',)),
    Method(RTorrent, 'set_dht_throttle', 'set_dht_throttle',
           aliases=('dht.throttle.name.set',)),
    Method(RTorrent, 'set_hash_max_tries', 'set_hash_max_tries'),
    Method(RTorrent, 'set_proxy_address', 'set_proxy_address',
           aliases=('network.proxy_address.set',)),
    Method(RTorrent, 'set_split_file_size', 'set_split_file_size',
           aliases=('system.file.split_size.set',)),
    Method(RTorrent, 'set_receive_buffer_size', 'set_receive_buffer_size',
           aliases=('network.receive_buffer.size.set',)),
    Method(RTorrent, 'set_use_udp_trackers', 'set_use_udp_trackers',
           aliases=('trackers.use_udp.set',)),
    Method(RTorrent, 'set_connection_seed', 'set_connection_seed',
           aliases=('protocol.connection.seed.set',)),
    Method(RTorrent, 'set_xmlrpc_size_limit', 'set_xmlrpc_size_limit',
           aliases=('network.xmlrpc.size_limit.set',)),
    Method(RTorrent, 'set_xmlrpc_dialect', 'set_xmlrpc_dialect',
           aliases=('network.xmlrpc.dialect.set',)),
    Method(RTorrent, 'set_safe_sync', 'set_safe_sync',
           aliases=('pieces.sync.always_safe.set',)),
    Method(RTorrent, 'set_http_capath', 'set_http_capath',
           aliases=('network.http.capath.set',)),
    Method(RTorrent, 'set_send_buffer_size', 'set_send_buffer_size',
           aliases=('network.send_buffer.size.set',)),
    Method(RTorrent, 'set_max_downloads_div', 'set_max_downloads_div',
           aliases=('throttle.max_downloads.div.set',)),
    Method(RTorrent, 'set_name', 'set_name',
           aliases=('session.name.set',)),
    Method(RTorrent, 'set_port_open', 'set_port_open',
           aliases=('network.port_open.set',)),
    Method(RTorrent, 'set_timeout_sync', 'set_timeout_sync',
           aliases=('pieces.sync.timeout.set',)),
    Method(RTorrent, 'set_peer_exchange', 'set_peer_exchange',
           aliases=('protocol.pex.set',)),
    Method(RTorrent, 'set_ip', 'set_ip',
           docstring="""Set IP

           @param arg: ip address
           @type arg: str
           """,
           aliases=('network.local_address.set',)
           ),
    Method(RTorrent, 'set_timeout_safe_sync', 'set_timeout_safe_sync',
           aliases=('pieces.sync.timeout_safe.set',)),
    Method(RTorrent, 'set_preload_type', 'set_preload_type',
           aliases=('pieces.preload.type.set',)),
    Method(RTorrent, 'set_check_hash', 'set_check_hash',
           docstring="""Enable/Disable hash checking on finished torrents

            @param arg: True to enable, False to disable
            @type arg: bool
            """,
           boolean=True,
           aliases=('pieces.hash.on_completion.set',)
           )
]

class_methods = [
    (RTorrent, methods),
    (File, file_methods),
    (Torrent, torrent_methods),
    (Tracker, tracker_methods),
    (Peer, peer_methods)]

for c, methods in class_methods:
    # noinspection PyProtectedMember
    rpc._build_rpc_methods(c, methods)
    _build_class_methods(c)

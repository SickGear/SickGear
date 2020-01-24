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
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from . import rpc
from .common import safe_repr
from .rpc import Method


class Peer(object):
    """Represents an individual peer within a L{Torrent} instance."""
    def __init__(self, _rt_obj, info_hash, **kwargs):
        self._rt_obj = _rt_obj
        self.id = None
        self.info_hash = info_hash  # : info hash for the torrent the peer is associated with
        for k in kwargs:
            setattr(self, k, kwargs.get(k, None))

        self.rpc_id = '{0}:p{1}'.format(
            self.info_hash, self.id or '')  # : unique id to pass to rTorrent

    def __repr__(self):
        return safe_repr('Peer(id={0})', self.id or '')

    def update(self):
        """Refresh peer data

        @note: All fields are stored as attributes to self.

        @return: None
        """
        mc = rpc.Multicall(self)

        for method in filter(lambda fx: fx.is_retriever() and fx.is_available(self._rt_obj), methods):
            mc.add(method, self.rpc_id)

        mc.call()


methods = [
    # RETRIEVERS
    Method(Peer, 'is_preferred', 'p.is_preferred',
           boolean=True,
           ),
    Method(Peer, 'get_down_rate', 'p.get_down_rate',
           aliases=('p.down_rate',)),
    Method(Peer, 'is_unwanted', 'p.is_unwanted',
           boolean=True,
           ),
    Method(Peer, 'get_peer_total', 'p.get_peer_total',
           aliases=('p.peer_total',)),
    Method(Peer, 'get_peer_rate', 'p.get_peer_rate',
           aliases=('p.peer_rate',)),
    Method(Peer, 'get_port', 'p.get_port',
           aliases=('p.port',)),
    Method(Peer, 'is_snubbed', 'p.is_snubbed',
           boolean=True,
           ),
    Method(Peer, 'get_id_html', 'p.get_id_html',
           aliases=('p.id_html',)),
    Method(Peer, 'get_up_rate', 'p.get_up_rate',
           aliases=('p.up_rate',)),
    Method(Peer, 'is_banned', 'p.banned',
           boolean=True,
           ),
    Method(Peer, 'get_completed_percent', 'p.get_completed_percent',
           aliases=('p.completed_percent',)),
    Method(Peer, 'completed_percent', 'p.completed_percent'),
    Method(Peer, 'get_id', 'p.get_id',
           aliases=('p.id',)),
    Method(Peer, 'is_obfuscated', 'p.is_obfuscated',
           boolean=True,
           ),
    Method(Peer, 'get_down_total', 'p.get_down_total',
           aliases=('p.down_total',)),
    Method(Peer, 'get_client_version', 'p.get_client_version',
           aliases=('p.client_version',)),
    Method(Peer, 'get_address', 'p.get_address',
           aliases=('p.address',)),
    Method(Peer, 'is_incoming', 'p.is_incoming',
           boolean=True,
           ),
    Method(Peer, 'is_encrypted', 'p.is_encrypted',
           boolean=True,
           ),
    Method(Peer, 'get_options_str', 'p.get_options_str',
           aliases=('p.options_str',)),
    Method(Peer, 'get_client_version', 'p.client_version'),
    Method(Peer, 'get_up_total', 'p.get_up_total',
           aliases=('p.up_total',)),

    # MODIFIERS
]

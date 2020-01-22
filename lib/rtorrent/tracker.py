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

from .common import safe_repr
from .rpc import Method, Multicall


class Tracker(object):
    """Represents an individual tracker within a L{Torrent} instance."""

    def __init__(self, _rt_obj, info_hash, **kwargs):
        self._rt_obj = _rt_obj
        self.info_hash = info_hash  # : info hash for the torrent using this tracker
        for k in kwargs:
            setattr(self, k, kwargs.get(k, None))

        # for clarity's sake...
        self.index = self.group  # : position of tracker within the torrent's tracker list
        self.rpc_id = '{0}:t{1}'.format(
            self.info_hash, self.index)  # : unique id to pass to rTorrent

    def __repr__(self):
        return safe_repr('Tracker(index={0}, url="{1}")',
                         self.index, self.url)

    def enable(self):
        """Alias for set_enabled("yes")"""
        self.set_enabled('yes')

    def disable(self):
        """Alias for set_enabled("no")"""
        self.set_enabled('no')

    def update(self):
        """Refresh tracker data

        @note: All fields are stored as attributes to self.

        @return: None
        """
        mc = Multicall(self)

        for method in filter(lambda fx: fx.is_retriever() and fx.is_available(self._rt_obj), methods):
            mc.add(method, self.rpc_id)

        mc.call()

    def append_tracker(self, tracker):
        """
        Append tracker to current tracker group

        @param tracker: The tracker url
        @type tracker: str

        @return: if successful, 0
        @rtype: int
        """
        mc = Multicall(self)

        self.multicall_add(mc, 'd.tracker.insert', self.index, tracker)

        return mc.call()[-1]


methods = [
    # RETRIEVERS
    Method(Tracker, 'is_enabled', 't.is_enabled', boolean=True),
    Method(Tracker, 'get_id', 't.get_id',
           aliases=('t.id',)),
    Method(Tracker, 'get_scrape_incomplete', 't.get_scrape_incomplete',
           aliases=('t.scrape_incomplete',)),
    Method(Tracker, 'is_open', 't.is_open', boolean=True),
    Method(Tracker, 'get_min_interval', 't.get_min_interval',
           aliases=('t.min_interval',)),
    Method(Tracker, 'get_scrape_downloaded', 't.get_scrape_downloaded',
           aliases=('t.scrape_downloaded',)),
    Method(Tracker, 'get_group', 't.get_group',
           aliases=('t.group',)),
    Method(Tracker, 'get_scrape_time_last', 't.get_scrape_time_last',
           aliases=('t.scrape_time_last',)),
    Method(Tracker, 'get_type', 't.get_type',
           aliases=('t.type',)),
    Method(Tracker, 'get_normal_interval', 't.get_normal_interval',
           aliases=('t.normal_interval',)),
    Method(Tracker, 'get_url', 't.get_url',
           aliases=('t.url',)),
    Method(Tracker, 'get_scrape_complete', 't.get_scrape_complete',
           min_version=(0, 8, 9),
           aliases=('t.scrape_complete',)
           ),
    Method(Tracker, 'get_activity_time_last', 't.activity_time_last',
           min_version=(0, 8, 9),
           ),
    Method(Tracker, 'get_activity_time_next', 't.activity_time_next',
           min_version=(0, 8, 9),
           ),
    Method(Tracker, 'get_failed_time_last', 't.failed_time_last',
           min_version=(0, 8, 9),
           ),
    Method(Tracker, 'get_failed_time_next', 't.failed_time_next',
           min_version=(0, 8, 9),
           ),
    Method(Tracker, 'get_success_time_last', 't.success_time_last',
           min_version=(0, 8, 9),
           ),
    Method(Tracker, 'get_success_time_next', 't.success_time_next',
           min_version=(0, 8, 9),
           ),
    Method(Tracker, 'can_scrape', 't.can_scrape',
           min_version=(0, 9, 1),
           boolean=True
           ),
    Method(Tracker, 'get_failed_counter', 't.failed_counter',
           min_version=(0, 8, 9)
           ),
    Method(Tracker, 'get_scrape_counter', 't.scrape_counter',
           min_version=(0, 8, 9)
           ),
    Method(Tracker, 'get_success_counter', 't.success_counter',
           min_version=(0, 8, 9)
           ),
    Method(Tracker, 'is_usable', 't.is_usable',
           min_version=(0, 9, 1),
           boolean=True
           ),
    Method(Tracker, 'is_busy', 't.is_busy',
           min_version=(0, 9, 1),
           boolean=True
           ),
    Method(Tracker, 'is_extra_tracker', 't.is_extra_tracker',
           min_version=(0, 9, 1),
           boolean=True,
           ),
    Method(Tracker, 'get_latest_sum_peers', 't.latest_sum_peers',
           min_version=(0, 9, 0)
           ),
    Method(Tracker, 'get_latest_new_peers', 't.latest_new_peers',
           min_version=(0, 9, 0)
           ),

    # MODIFIERS
    Method(Tracker, 'set_enabled', 't.set_enabled',
           aliases=('t.is_enabled.set',)),
]

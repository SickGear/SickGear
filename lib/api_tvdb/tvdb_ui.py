#!/usr/bin/env python2
# encoding:utf-8
# author:dbr/Ben
# project:tvdb_api
# repository:http://github.com/dbr/tvdb_api
# license:unlicense (http://unlicense.org/)

"""Contains included user interfaces for Tvdb show selection.

A UI is a callback. A class, it's __init__ function takes two arguments:

- config, which is the Tvdb config dict, setup in tvdb_api.py
- log, which is Tvdb's logger instance (which uses the logging module). You can
call log.info() log.warning() etc

It must have a method "select_series", this is passed a list of dicts, each dict
contains the the keys "name" (human readable show name), and "sid" (the shows
ID as on thetvdb.com). For example:

[{'name': u'Lost', 'sid': u'73739'},
 {'name': u'Lost Universe', 'sid': u'73181'}]

The "select_series" method must return the appropriate dict, or it can raise
tvdb_userabort (if the selection is aborted), tvdb_shownotfound (if the show
cannot be found).

A simple example callback, which returns a random series:

# >>> import random
# >>> from tvdb_ui import BaseUI
# >>> class RandomUI(BaseUI):
# ...    def select_series(self, allSeries):
# ...            import random
# ...            return random.choice(allSeries)

Then to use it..

# >>> from tvdb_api import Tvdb
# >>> t = Tvdb(custom_ui = RandomUI)
# >>> random_matching_series = t['Lost']
# >>> type(random_matching_series)
# <class 'tvdb_api.Show'>
"""

__author__ = "dbr/Ben"
__version__ = "1.9"

import logging
import warnings

from .tvdb_exceptions import TvdbUserabort
from six import moves


def log():
    return logging.getLogger(__name__)


class BaseUI(object):
    """Default non-interactive UI, which auto-selects first results
    """
    def __init__(self, config, log=None):
        self.config = config
        if None is not log:
            warnings.warn("the UI's log parameter is deprecated, instead use\n"
                          "use import logging; logging.getLogger('ui').info('blah')\n"
                          "The self.log attribute will be removed in the next version")
            self.log = logging.getLogger(__name__)

    def select_series(self, all_series):
        return all_series[0]


class ConsoleUI(BaseUI):
    """Interactively allows the user to select a show from a console based UI
    """

    @staticmethod
    def _displaySeries(all_series, limit=6):
        """Helper function, lists series with corresponding ID
        """
        if None is not limit:
            toshow = all_series[:limit]
        else:
            toshow = all_series

        print('TVDB Search Results:')
        for i, cshow in enumerate(toshow):
            i_show = i + 1  # Start at more human readable number 1 (not 0)
            log().debug('Showing allSeries[%s], series %s)' % (i_show, all_series[i]['seriesname']))
            if 0 == i:
                extra = " (default)"
            else:
                extra = ""

            print ('%s -> %s [%s] # http://thetvdb.com/?tab=series&id=%s&lid=%s%s' % (
                i_show,
                cshow['seriesname'].encode('UTF-8', 'ignore'),
                cshow['language'].encode('UTF-8', 'ignore'),
                str(cshow['id']),
                cshow['lid'],
                extra
            ))

    def select_series(self, all_series):
        self._displaySeries(all_series)

        if 1 == len(all_series):
            # Single result, return it!
            print('Automatically selecting only result')
            return all_series[0]

        if self.config['select_first'] is True:
            print('Automatically returning first search result')
            return all_series[0]

        while True:  # return breaks this loop
            try:
                print('Enter choice (first number, return for default, \'all\', ? for help):')
                ans = moves.input()
            except KeyboardInterrupt:
                raise TvdbUserabort("User aborted (^c keyboard interupt)")
            except EOFError:
                raise TvdbUserabort("User aborted (EOF received)")

            log().debug('Got choice of: %s' % ans)
            try:
                selected_id = int(ans) - 1  # The human entered 1 as first result, not zero
            except ValueError:  # Input was not number
                if 0 == len(ans.strip()):
                    # Default option
                    log().debug('Default option, returning first series')
                    return all_series[0]
                if "q" == ans:
                    log().debug('Got quit command (q)')
                    raise TvdbUserabort("User aborted ('q' quit command)")
                elif "?" == ans:
                    print('## Help')
                    print('# Enter the number that corresponds to the correct show.')
                    print('# a - display all results')
                    print('# all - display all results')
                    print('# ? - this help')
                    print('# q - abort tvnamer')
                    print('# Press return with no input to select first result')
                elif ans.lower() in ["a", "all"]:
                    self._displaySeries(all_series, limit=None)
                else:
                    log().debug('Unknown keypress %s' % ans)
            else:
                log().debug('Trying to return ID: %d' % selected_id)
                try:
                    return all_series[selected_id]
                except IndexError:
                    log().debug('Invalid show number entered!')
                    print('Invalid number (%s) selected!')
                    self._displaySeries(all_series)

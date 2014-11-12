#!/usr/bin/env python2
#encoding:utf-8
#author:dbr/Ben (ripped from tvdb:echel0n)
#project:tvrage_api

#license:unlicense (http://unlicense.org/)

"""Contains included user interface for TVRage show selection"""

import logging
import warnings

def log():
    return logging.getLogger(__name__)

class BaseUI:
    """Default non-interactive UI, which auto-selects first results
    """
    def __init__(self, config, log = None):
        self.config = config
        if log is not None:
            warnings.warn("the UI's log parameter is deprecated, instead use\n"
                "use import logging; logging.getLogger('ui').info('blah')\n"
                "The self.log attribute will be removed in the next version")
            self.log = logging.getLogger(__name__)

    def selectSeries(self, allSeries):
        return allSeries[0]
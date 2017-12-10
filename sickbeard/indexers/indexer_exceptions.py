#!/usr/bin/env python2
#encoding:utf-8
#project:indexer_api
#license:unlicense (http://unlicense.org/)

"""Custom exceptions used or raised by indexer_api"""

from lib.tvdb_api.tvdb_exceptions import \
    tvdb_exception, tvdb_attributenotfound, tvdb_episodenotfound, tvdb_error, \
    tvdb_seasonnotfound, tvdb_shownotfound, tvdb_userabort, tvdb_tokenexpired

from lib.tvdb_api_v1.tvdb_exceptions import \
    tvdb_exception_v1, tvdb_attributenotfound_v1, tvdb_episodenotfound_v1, tvdb_error_v1, \
    tvdb_seasonnotfound_v1, tvdb_shownotfound_v1, tvdb_userabort_v1

indexerExcepts = [
    'indexer_exception', 'indexer_error', 'indexer_userabort',
    'indexer_shownotfound', 'indexer_seasonnotfound', 'indexer_episodenotfound',
    'indexer_attributenotfound', 'indexer_authenticationerror']

tvdbExcepts = [
    'tvdb_exception', 'tvdb_error', 'tvdb_userabort', 'tvdb_shownotfound',
    'tvdb_seasonnotfound', 'tvdb_episodenotfound', 'tvdb_attributenotfound',
    'tvdb_tokenexpired']

tvdbV1Excepts = [
    'tvdb_exception_v1', 'tvdb_error_v1', 'tvdb_userabort_v1', 'tvdb_shownotfound_v1',
    'tvdb_seasonnotfound_v1', 'tvdb_episodenotfound_v1', 'tvdb_attributenotfound_v1']

# link API exceptions to our exception handler
indexer_exception = tvdb_exception, tvdb_exception_v1
indexer_error = tvdb_error, tvdb_error_v1
indexer_authenticationerror = tvdb_tokenexpired
indexer_userabort = tvdb_userabort, tvdb_userabort_v1
indexer_attributenotfound = tvdb_attributenotfound, tvdb_attributenotfound_v1
indexer_episodenotfound = tvdb_episodenotfound, tvdb_episodenotfound_v1
indexer_seasonnotfound = tvdb_seasonnotfound, tvdb_seasonnotfound_v1
indexer_shownotfound = tvdb_shownotfound, tvdb_shownotfound_v1
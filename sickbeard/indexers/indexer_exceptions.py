#!/usr/bin/env python2
# encoding:utf-8
# project:indexer_api
# license:unlicense (http://unlicense.org/)

__all__ = ['check_exception_type', 'ExceptionTuples',
           'BaseTVinfoException', 'BaseTVinfoError', 'BaseTVinfoAuthenticationerror',
           'BaseTVinfoUserabort', 'BaseTVinfoAttributenotfound', 'BaseTVinfoEpisodenotfound',
           'BaseTVinfoSeasonnotfound', 'BaseTVinfoShownotfound']

"""Custom exceptions used or raised by indexer_api"""

from lib.tvdb_api.tvdb_exceptions import \
    TvdbException, TvdbAttributenotfound, TvdbEpisodenotfound, TvdbError, \
    TvdbSeasonnotfound, TvdbShownotfound, TvdbUserabort, TvdbTokenexpired

indexer_excepts = [
    'tvinfo_exception', 'tvinfo_error', 'tvinfo_userabort',
    'tvinfo_shownotfound', 'tvinfo_seasonnotfound', 'tvinfo_episodenotfound',
    'tvinfo_attributenotfound', 'tvinfo_authenticationerror']

tvdb_excepts = [
    'tvdb_exception', 'tvdb_error', 'tvdb_userabort', 'tvdb_shownotfound',
    'tvdb_seasonnotfound', 'tvdb_episodenotfound', 'tvdb_attributenotfound',
    'tvdb_tokenexpired']

tvdbv1_excepts = [
    'tvdb_exception_v1', 'tvdb_error_v1', 'tvdb_userabort_v1', 'tvdb_shownotfound_v1',
    'tvdb_seasonnotfound_v1', 'tvdb_episodenotfound_v1', 'tvdb_attributenotfound_v1']


class BaseTVinfoException(Exception):
    pass


class BaseTVinfoError(Exception):
    pass


class BaseTVinfoAuthenticationerror(Exception):
    pass


class BaseTVinfoUserabort(Exception):
    pass


class BaseTVinfoAttributenotfound(Exception):
    pass


class BaseTVinfoEpisodenotfound(Exception):
    pass


class BaseTVinfoSeasonnotfound(Exception):
    pass


class BaseTVinfoShownotfound(Exception):
    pass


# link API exceptions to our exception handler
class ExceptionTuples:
    tvinfo_exception = TvdbException, BaseTVinfoException
    tvinfo_error = TvdbError, BaseTVinfoError
    tvinfo_authenticationerror = TvdbTokenexpired, BaseTVinfoAuthenticationerror
    tvinfo_userabort = TvdbUserabort, BaseTVinfoUserabort
    tvinfo_attributenotfound = TvdbAttributenotfound, BaseTVinfoAttributenotfound
    tvinfo_episodenotfound = TvdbEpisodenotfound, BaseTVinfoEpisodenotfound
    tvinfo_seasonnotfound = TvdbSeasonnotfound, BaseTVinfoSeasonnotfound
    tvinfo_shownotfound = TvdbShownotfound, BaseTVinfoShownotfound


def check_exception_type(ex, ex_class, *args):
    # type: (...) -> bool
    if issubclass(ex.__class__, ex_class + args):
        return True
    return False

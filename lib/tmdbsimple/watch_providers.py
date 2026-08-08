# -*- coding: utf-8 -*-

"""
tmdbsimple.watch_providers
~~~~~~~~~~~~~~~~~~~~~~~~~~

This module implements the Watch Providers functionality of tmdbsimple.

Created by Celia Oakley on 2026-05-24.

:copyright: (c) 2013-2026 by Celia Oakley
:license: GPLv3, see LICENSE for more details
"""

from .base import TMDB


class WatchProviders(TMDB):
    """
    Watch Providers functionality.

    See: https://developer.themoviedb.org/reference/watch-providers-available-regions
         https://developer.themoviedb.org/reference/watch-providers-movie-list
         https://developer.themoviedb.org/reference/watch-provider-tv-list
    """
    BASE_PATH = 'watch/providers'
    URLS = {
        'regions': '/regions',
        'movie': '/movie',
        'tv': '/tv',
    }

    def regions(self, **kwargs):
        """
        Get the list of the countries we have watch provider (OTT/streaming)
        data for.

        Args:
            language: (optional) ISO 639-1 code. Default en-US.

        Returns:
            A dict respresentation of the JSON returned from the API.
        """
        path = self._get_path('regions')

        response = self._GET(path, kwargs)
        self._set_attrs_to_values(response)
        return response

    def movie(self, **kwargs):
        """
        Get the list of streaming providers we have for movies.

        Args:
            language: (optional) ISO 639-1 code. Default en-US.
            watch_region: (optional) ISO 3166-1 code. Filter by region.

        Returns:
            A dict respresentation of the JSON returned from the API.
        """
        path = self._get_path('movie')

        response = self._GET(path, kwargs)
        self._set_attrs_to_values(response)
        return response

    def tv(self, **kwargs):
        """
        Get the list of streaming providers we have for TV shows.

        Args:
            language: (optional) ISO 639-1 code. Default en-US.
            watch_region: (optional) ISO 3166-1 code. Filter by region.

        Returns:
            A dict respresentation of the JSON returned from the API.
        """
        path = self._get_path('tv')

        response = self._GET(path, kwargs)
        self._set_attrs_to_values(response)
        return response

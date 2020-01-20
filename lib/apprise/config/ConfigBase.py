# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 Chris Caron <lead2gold@gmail.com>
# All rights reserved.
#
# This code is licensed under the MIT License.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files(the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and / or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions :
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import os
import re
import six
import time

from .. import plugins
from ..AppriseAsset import AppriseAsset
from ..URLBase import URLBase
from ..common import ConfigFormat
from ..common import CONFIG_FORMATS
from ..utils import GET_SCHEMA_RE
from ..utils import parse_list
from ..utils import parse_bool


class ConfigBase(URLBase):
    """
    This is the base class for all supported configuration sources
    """

    # The Default Encoding to use if not otherwise detected
    encoding = 'utf-8'

    # The default expected configuration format unless otherwise
    # detected by the sub-modules
    default_config_format = ConfigFormat.TEXT

    # This is only set if the user overrides the config format on the URL
    # this should always initialize itself as None
    config_format = None

    # Don't read any more of this amount of data into memory as there is no
    # reason we should be reading in more. This is more of a safe guard then
    # anything else. 128KB (131072B)
    max_buffer_size = 131072

    def __init__(self, cache=True, **kwargs):
        """
        Initialize some general logging and common server arguments that will
        keep things consistent when working with the configurations that
        inherit this class.

        By default we cache our responses so that subsiquent calls does not
        cause the content to be retrieved again.  For local file references
        this makes no difference at all.  But for remote content, this does
        mean more then one call can be made to retrieve the (same) data.  This
        method can be somewhat inefficient if disabled.  Only disable caching
        if you understand the consequences.

        You can alternatively set the cache value to an int identifying the
        number of seconds the previously retrieved can exist for before it
        should be considered expired.
        """

        super(ConfigBase, self).__init__(**kwargs)

        # Tracks the time the content was last retrieved on.  This place a role
        # for cases where we are not caching our response and are required to
        # re-retrieve our settings.
        self._cached_time = None

        # Tracks previously loaded content for speed
        self._cached_servers = None

        if 'encoding' in kwargs:
            # Store the encoding
            self.encoding = kwargs.get('encoding')

        if 'format' in kwargs:
            # Store the enforced config format
            self.config_format = kwargs.get('format').lower()

            if self.config_format not in CONFIG_FORMATS:
                # Simple error checking
                err = 'An invalid config format ({}) was specified.'.format(
                    self.config_format)
                self.logger.warning(err)
                raise TypeError(err)

        # Set our cache flag; it can be True or a (positive) integer
        try:
            self.cache = cache if isinstance(cache, bool) else int(cache)
            if self.cache < 0:
                err = 'A negative cache value ({}) was specified.'.format(
                    cache)
                self.logger.warning(err)
                raise TypeError(err)

        except (ValueError, TypeError):
            err = 'An invalid cache value ({}) was specified.'.format(cache)
            self.logger.warning(err)
            raise TypeError(err)

        return

    def servers(self, asset=None, **kwargs):
        """
        Performs reads loaded configuration and returns all of the services
        that could be parsed and loaded.

        """

        if not self.expired():
            # We already have cached results to return; use them
            return self._cached_servers

        # Our cached response object
        self._cached_servers = list()

        # read() causes the child class to do whatever it takes for the
        # config plugin to load the data source and return unparsed content
        # None is returned if there was an error or simply no data
        content = self.read(**kwargs)
        if not isinstance(content, six.string_types):
            # Set the time our content was cached at
            self._cached_time = time.time()

            # Nothing more to do; return our empty cache list
            return self._cached_servers

        # Our Configuration format uses a default if one wasn't one detected
        # or enfored.
        config_format = \
            self.default_config_format \
            if self.config_format is None else self.config_format

        # Dynamically load our parse_ function based on our config format
        fn = getattr(ConfigBase, 'config_parse_{}'.format(config_format))

        # Execute our config parse function which always returns a list
        self._cached_servers.extend(fn(content=content, asset=asset))

        if len(self._cached_servers):
            self.logger.info('Loaded {} entries from {}'.format(
                len(self._cached_servers), self.url()))
        else:
            self.logger.warning('Failed to load configuration from {}'.format(
                self.url()))

        # Set the time our content was cached at
        self._cached_time = time.time()

        return self._cached_servers

    def read(self):
        """
        This object should be implimented by the child classes

        """
        return None

    def expired(self):
        """
        Simply returns True if the configuration should be considered
        as expired or False if content should be retrieved.
        """
        if isinstance(self._cached_servers, list) and self.cache:
            # We have enough reason to look further into our cached content
            # and verify it has not expired.
            if self.cache is True:
                # we have not expired, return False
                return False

            # Verify our cache time to determine whether we will get our
            # content again.
            age_in_sec = time.time() - self._cached_time
            if age_in_sec <= self.cache:
                # We have not expired; return False
                return False

        # If we reach here our configuration should be considered
        # missing and/or expired.
        return True

    @staticmethod
    def parse_url(url, verify_host=True):
        """Parses the URL and returns it broken apart into a dictionary.

        This is very specific and customized for Apprise.

        Args:
            url (str): The URL you want to fully parse.
            verify_host (:obj:`bool`, optional): a flag kept with the parsed
                 URL which some child classes will later use to verify SSL
                 keys (if SSL transactions take place).  Unless under very
                 specific circumstances, it is strongly recomended that
                 you leave this default value set to True.

        Returns:
            A dictionary is returned containing the URL fully parsed if
            successful, otherwise None is returned.
        """

        results = URLBase.parse_url(url, verify_host=verify_host)

        if not results:
            # We're done; we failed to parse our url
            return results

        # Allow overriding the default config format
        if 'format' in results['qsd']:
            results['format'] = results['qsd'].get('format')
            if results['format'] not in CONFIG_FORMATS:
                URLBase.logger.warning(
                    'Unsupported format specified {}'.format(
                        results['format']))
                del results['format']

        # Defines the encoding of the payload
        if 'encoding' in results['qsd']:
            results['encoding'] = results['qsd'].get('encoding')

        # Our cache value
        if 'cache' in results['qsd']:
            # First try to get it's integer value
            try:
                results['cache'] = int(results['qsd']['cache'])

            except (ValueError, TypeError):
                # No problem, it just isn't an integer; now treat it as a bool
                # instead:
                results['cache'] = parse_bool(results['qsd']['cache'])

        return results

    @staticmethod
    def config_parse_text(content, asset=None):
        """
        Parse the specified content as though it were a simple text file only
        containing a list of URLs. Return a list of loaded notification plugins

        Optionally associate an asset with the notification.

        The file syntax is:

            #
            # pound/hashtag allow for line comments
            #
            # One or more tags can be idenified using comma's (,) to separate
            # them.
            <Tag(s)>=<URL>

            # Or you can use this format (no tags associated)
            <URL>

        """
        # For logging, track the line number
        line = 0

        response = list()

        # Define what a valid line should look like
        valid_line_re = re.compile(
            r'^\s*(?P<line>([;#]+(?P<comment>.*))|'
            r'(\s*(?P<tags>[^=]+)=|=)?\s*'
            r'(?P<url>[a-z0-9]{2,9}://.*))?$', re.I)

        try:
            # split our content up to read line by line
            content = re.split(r'\r*\n', content)

        except TypeError:
            # content was not expected string type
            ConfigBase.logger.error('Invalid apprise text data specified')
            return list()

        for entry in content:
            # Increment our line count
            line += 1

            result = valid_line_re.match(entry)
            if not result:
                # Invalid syntax
                ConfigBase.logger.error(
                    'Invalid apprise text format found '
                    '{} on line {}.'.format(entry, line))

                # Assume this is a file we shouldn't be parsing. It's owner
                # can read the error printed to screen and take action
                # otherwise.
                return list()

            # Store our url read in
            url = result.group('url')
            if not url:
                # Comment/empty line; do nothing
                continue

            # Acquire our url tokens
            results = plugins.url_to_dict(url)
            if results is None:
                # Failed to parse the server URL
                ConfigBase.logger.warning(
                    'Unparseable URL {} on line {}.'.format(url, line))
                continue

            # Build a list of tags to associate with the newly added
            # notifications if any were set
            results['tag'] = set(parse_list(result.group('tags')))

            ConfigBase.logger.trace(
                'URL {} unpacked as:{}{}'.format(
                    url, os.linesep, os.linesep.join(
                        ['{}="{}"'.format(k, v) for k, v in results.items()])))

            # Prepare our Asset Object
            results['asset'] = \
                asset if isinstance(asset, AppriseAsset) else AppriseAsset()

            try:
                # Attempt to create an instance of our plugin using the
                # parsed URL information
                plugin = plugins.SCHEMA_MAP[results['schema']](**results)

                # Create log entry of loaded URL
                ConfigBase.logger.debug('Loaded URL: {}'.format(plugin.url()))

            except Exception as e:
                # the arguments are invalid or can not be used.
                ConfigBase.logger.warning(
                    'Could not load URL {} on line {}.'.format(
                        url, line))
                ConfigBase.logger.debug('Loading Exception: %s' % str(e))
                continue

            # if we reach here, we successfully loaded our data
            response.append(plugin)

        # Return what was loaded
        return response

    def pop(self, index=-1):
        """
        Removes an indexed Notification Service from the stack and returns it.

        By default, the last element of the list is removed.
        """

        if not isinstance(self._cached_servers, list):
            # Generate ourselves a list of content we can pull from
            self.servers()

        # Pop the element off of the stack
        return self._cached_servers.pop(index)

    def __getitem__(self, index):
        """
        Returns the indexed server entry associated with the loaded
        notification servers
        """
        if not isinstance(self._cached_servers, list):
            # Generate ourselves a list of content we can pull from
            self.servers()

        return self._cached_servers[index]

    def __iter__(self):
        """
        Returns an iterator to our server list
        """
        if not isinstance(self._cached_servers, list):
            # Generate ourselves a list of content we can pull from
            self.servers()

        return iter(self._cached_servers)

    def __len__(self):
        """
        Returns the total number of servers loaded
        """
        if not isinstance(self._cached_servers, list):
            # Generate ourselves a list of content we can pull from
            self.servers()

        return len(self._cached_servers)

    def __bool__(self):
        """
        Allows the Apprise object to be wrapped in an Python 3.x based 'if
        statement'.  True is returned if our content was downloaded correctly.
        """
        if not isinstance(self._cached_servers, list):
            # Generate ourselves a list of content we can pull from
            self.servers()

        return True if self._cached_servers else False

    def __nonzero__(self):
        """
        Allows the Apprise object to be wrapped in an Python 2.x based 'if
        statement'.  True is returned if our content was downloaded correctly.
        """
        if not isinstance(self._cached_servers, list):
            # Generate ourselves a list of content we can pull from
            self.servers()

        return True if self._cached_servers else False

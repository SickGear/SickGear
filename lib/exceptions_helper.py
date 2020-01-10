# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from six import PY2, string_types

if PY2:
    from encodingKludge import fixStupidEncodings

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr


def ex(e):
    # type: (BaseException) -> AnyStr
    """Returns a unicode string from the exception text if it exists"""

    if not PY2:
        return str(e)

    e_message = u''

    if not e or not e.args:
        return e_message

    for arg in e.args:

        if None is not arg:
            if isinstance(arg, string_types):
                fixed_arg = fixStupidEncodings(arg, True)

            else:
                try:
                    fixed_arg = u'error ' + fixStupidEncodings(str(arg), True)

                except (BaseException, Exception):
                    fixed_arg = None

            if fixed_arg:
                if not e_message:
                    e_message = fixed_arg

                else:
                    e_message = e_message + ' : ' + fixed_arg

    return e_message


class SickBeardException(Exception):
    """Generic SickGear Exception - should never be thrown, only subclassed"""


class ConfigErrorException(SickBeardException):
    """Error in the config file"""


class LaterException(SickBeardException):
    """Something bad happened that I'll make a real exception for later"""


class NoNFOException(SickBeardException):
    """No NFO was found!"""


class NoShowDirException(SickBeardException):
    """Unable to find the show's directory"""


class FileNotFoundException(SickBeardException):
    """The specified file doesn't exist"""


class MultipleDBEpisodesException(SickBeardException):
    """Found multiple episodes in the DB! Must fix DB first"""


class MultipleDBShowsException(SickBeardException):
    """Found multiple shows in the DB! Must fix DB first"""


class MultipleShowObjectsException(SickBeardException):
    """Found multiple objects for the same show! Something is very wrong"""


class WrongShowException(SickBeardException):
    """The episode doesn't belong to the same show as its parent folder"""


class ShowNotFoundException(SickBeardException):
    """The show wasn't found on the Indexer"""


class EpisodeNotFoundException(SickBeardException):
    """The episode wasn't found on the Indexer"""


class ShowDirNotFoundException(SickBeardException):
    """The show dir doesn't exist"""


class AuthException(SickBeardException):
    """Your authentication information is incorrect"""


class EpisodeDeletedException(SickBeardException):
    """This episode has been deleted"""


class CantRefreshException(SickBeardException):
    """The show can't be refreshed right now"""


class CantUpdateException(SickBeardException):
    """The show can't be updated right now"""


class PostProcessingFailed(SickBeardException):
    """Post-processing the episode failed"""


class FailedProcessingFailed(SickBeardException):
    """Post-processing the failed release failed"""


class FailedHistoryMultiSnatchException(SickBeardException):
    """Episode was snatched again before the first one was done"""


class FailedHistoryNotFoundException(SickBeardException):
    """The release was not found in the failed download history tracker"""


class EpisodeNotFoundByAbsoluteNumberException(SickBeardException):
    """The show wasn't found in the DB while looking at Absolute Numbers"""

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

# noinspection PyUnreachableCode
if False:
    from typing import AnyStr


def ex(e):
    # type: (BaseException) -> AnyStr
    """Returns a unicode string from the exception text if it exists"""

    return str(e)


# noinspection DuplicatedCode
class SickGearException(Exception):
    """Generic SickGear Exception - should never be thrown, only subclassed"""


class ConfigErrorException(SickGearException):
    """Error in the config file"""


class LaterException(SickGearException):
    """Something bad happened that I'll make a real exception for later"""


class NoNFOException(SickGearException):
    """No NFO was found!"""


class NoShowDirException(SickGearException):
    """Unable to find the show's directory"""


class FileNotFoundException(SickGearException):
    """The specified file doesn't exist"""


class MultipleDBEpisodesException(SickGearException):
    """Found multiple episodes in the DB! Must fix DB first"""


class MultipleDBShowsException(SickGearException):
    """Found multiple shows in the DB! Must fix DB first"""


class MultipleShowObjectsException(SickGearException):
    """Found multiple objects for the same show! Something is very wrong"""


class WrongShowException(SickGearException):
    """The episode doesn't belong to the same show as its parent folder"""


class ShowNotFoundException(SickGearException):
    """The show wasn't found on the Indexer"""


class EpisodeNotFoundException(SickGearException):
    """The episode wasn't found on the Indexer"""


class ShowDirNotFoundException(SickGearException):
    """The show dir doesn't exist"""


class AuthException(SickGearException):
    """Your authentication information is incorrect"""


class EpisodeDeletedException(SickGearException):
    """This episode has been deleted"""


class CantRefreshException(SickGearException):
    """The show can't be refreshed right now"""


class CantUpdateException(SickGearException):
    """The show can't be updated right now"""


class CantSwitchException(SickGearException):
    """The show can't be switched right now"""


class PostProcessingFailed(SickGearException):
    """Post-processing the episode failed"""


class FailedProcessingFailed(SickGearException):
    """Post-processing the failed release failed"""


class FailedHistoryMultiSnatchException(SickGearException):
    """Episode was snatched again before the first one was done"""


class FailedHistoryNotFoundException(SickGearException):
    """The release was not found in the failed download history tracker"""


class EpisodeNotFoundByAbsoluteNumberException(SickGearException):
    """The show wasn't found in the DB while looking at Absolute Numbers"""


class ConnectionSkipException(SickGearException):
    """Connection was skipped because of previous errors"""

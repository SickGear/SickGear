class BaseTVinfoException(Exception):
    """Base Exception
    """
    pass


class BaseTVinfoError(BaseTVinfoException):
    """Base Error
    """
    pass


class BaseTVinfoUserabort(BaseTVinfoError):
    """User aborted the interactive selection (via
    the q command, ^c etc)
    """
    pass


class BaseTVinfoShownotfound(BaseTVinfoError):
    """Show cannot be found
    """
    pass


class BaseTVinfoSeasonnotfound(BaseTVinfoError):
    """Season cannot be found
    """
    pass


class BaseTVinfoEpisodenotfound(BaseTVinfoError):
    """Episode cannot be found
    """
    pass


class BaseTVinfoAttributenotfound(BaseTVinfoError):
    """Raised if an episode does not have the requested
    attribute (such as a episode name)
    """
    pass


class BaseTVinfoAuthenticationerror(BaseTVinfoError):
    """auth expired or missing
    """
    pass


class BaseTVinfoIndexerInitError(BaseTVinfoError):
    pass

class BaseTVinfoException(Exception):
    """Base Exception
    """

    def __init__(self, *args, **kwargs):
        default_message = kwargs.pop('default_message', type(self).__name__)

        # if any arguments are passed...
        if args or kwargs:
            # ... pass them to the super constructor
            super(BaseTVinfoException, self).__init__(*args, **kwargs)
        else:  # else, the exception was raised without arguments ...
            # ... pass the default message to the super constructor
            super(BaseTVinfoException, self).__init__(default_message)


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

class TraktException(Exception):
    pass


class TraktAuthException(TraktException):
    pass


class TraktServerBusy(TraktException):
    pass


class TraktShowNotFound(TraktException):
    pass
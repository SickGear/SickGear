from lib.tvinfo_base.exceptions import *


class TraktException(BaseTVinfoException):
    pass


class TraktError(TraktException, BaseTVinfoError):
    pass


class TraktAuthException(TraktError):
    pass


class TraktServerBusy(TraktError):
    pass


class TraktShowNotFound(BaseTVinfoShownotfound, TraktError):
    pass


class TraktCloudFlareException(TraktError):
    pass


class TraktMethodNotExisting(TraktError):
    pass


class TraktTimeout(TraktError):
    pass


class TraktValueError(TraktError):
    pass


class TraktServerError(TraktError):
    def __init__(self, *args, **kwargs):
        self.error_code = kwargs.get('error_code')
        kwargs = {}
        if 0 < len(args):
            args = tuple(['%s, Server Error: %s' % (args[0], self.error_code)])
        else:
            args = tuple(['Server Error: %s' % self.error_code])
        super(TraktServerError, self).__init__(*args, **kwargs)


class TraktLockedUserAccount(TraktError):
    pass


class TraktInvalidGrant(TraktError):
    pass


class TraktFreemiumLimit(TraktError):
    pass


class TraktPersonNotFound(BaseTVinfoPersonNotFound, TraktError):
    pass
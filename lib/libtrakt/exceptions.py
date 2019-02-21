class TraktException(Exception):
    pass


class TraktAuthException(TraktException):
    pass


class TraktServerBusy(TraktException):
    pass


class TraktShowNotFound(TraktException):
    pass


class TraktCloudFlareException(TraktException):
    pass


class TraktMethodNotExisting(TraktException):
    pass


class TraktTimeout(TraktException):
    pass


class TraktValueError(TraktException):
    pass


class TraktServerError(TraktException):
    def __init__(self, *args, **kwargs):
        self.error_code = kwargs.get('error_code')
        kwargs = {}
        if 0 < len(args):
            args = tuple(['%s, Server Error: %s' % (args[0], self.error_code)])
        else:
            args = tuple(['Server Error: %s' % self.error_code])
        super(TraktServerError, self).__init__(*args, **kwargs)

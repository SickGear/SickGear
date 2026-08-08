class IMDbGQLException(Exception):
    pass


class IMDbGQLError(IMDbGQLException):
    pass


class IMDbGQLPersonNotFound(IMDbGQLException):
    pass

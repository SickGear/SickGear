import functools
import inspect
import traceback
import warnings


def deprecated(message=''):
    """
    This decorator can be used to mark functions as deprecated.
    It will result in a warning being emitted when the function
    is used first time and filter is set for show DeprecationWarning.
    File and line usage point is output to direct to the place to change.
    """
    def decorator_wrapper(func):
        @functools.wraps(func)
        def function_wrapper(*args, **kwargs):
            current_call_source = '|'.join(traceback.format_stack(inspect.currentframe()))
            if current_call_source not in function_wrapper.last_call_source:
                warnings.warn('{} is being deprecated! {}'.format(func.__name__, message),
                              category=DeprecationWarning, stacklevel=2)
                function_wrapper.last_call_source.add(current_call_source)
            return func(*args, **kwargs)

        function_wrapper.last_call_source = set()
        return function_wrapper
    return decorator_wrapper


class LegacyParseResult(object):

    def __init__(self, show=None, **kwargs):
        if show:
            self.show_obj = show

    @property
    @deprecated('(ParseResult) Use show_obj __getter__ instead')
    def show(self):
        return self.show_obj

    @property
    def show_obj(self):
        raise NotImplementedError

    @show.setter
    @deprecated('(ParseResult) Use show_obj __setter__ instead')
    def show(self, val):
        self.show_obj = val

    @show_obj.setter
    def show_obj(self, *arg):
        raise NotImplementedError


class LegacyTVShow(object):
    def __init__(self, tvid, prodid):
        # type: (int, int) -> None
        super(LegacyTVShow, self).__init__()

        self._indexer = int(tvid)
        self._indexerid = int(prodid)

    # TODO: deprecating TVShow.indexer
    # indexer = property(lambda self: self._indexer, dirty_setter('_indexer'))
    @property
    @deprecated('(TVShow) Use tvid_prodid or tvid __getter__ instead')
    def indexer(self):
        return self.tvid

    @property
    def tvid(self):
        raise NotImplementedError

    @indexer.setter
    @deprecated('(TVShow) Use tvid_prodid or tvid __setter__ instead')
    def indexer(self, val):
        self.tvid = val

    @tvid.setter
    def tvid(self, val):
        raise NotImplementedError

    # TODO: deprecating TVShow.indexerid
    # indexerid = property(lambda self: self._indexerid, self.dirty_setter('_indexerid'))
    @property
    @deprecated('(TVShow) Use tvid_prodid or prodid __getter__ instead')
    def indexerid(self):
        return self.prodid

    @property
    def prodid(self):
        raise NotImplementedError

    @indexerid.setter
    @deprecated('(TVShow) Use tvid_prodid or prodid __setter__ instead')
    def indexerid(self, val):
        self.prodid = val

    @prodid.setter
    def prodid(self, val):
        raise NotImplementedError


class LegacyTVEpisode(object):

    def __init__(self, tvid):
        super(LegacyTVEpisode, self).__init__()

        self._indexer = tvid
        self._indexerid = 0

    # TODO: deprecating TVEpisode.show
    @property
    @deprecated('(TVEpisode) Use show_obj __getter__ instead')
    def show(self):
        return self.show_obj

    @property
    def show_obj(self):
        raise NotImplementedError

    @show.setter
    @deprecated('(TVEpisode) Use show_obj __setter__ instead')
    def show(self, val):
        self.show_obj = val

    @show_obj.setter
    def show_obj(self, val):
        raise NotImplementedError

    # TODO: deprecating TVEpisode.indexer
    # indexer = property(lambda self: self._indexer, self.dirty_setter('_indexer'))
    @property
    @deprecated('(TVEpisode) Use tvid __getter__ instead')
    def indexer(self):
        return self.tvid

    @property
    def tvid(self):
        raise NotImplementedError

    @indexer.setter
    @deprecated('(TVEpisode) Use tvid __setter__ instead')
    def indexer(self, val):
        self.tvid = val

    @tvid.setter
    def tvid(self, val):
        raise NotImplementedError

    # TODO: deprecating TVEpisode.indexerid
    # indexerid = property(lambda self: self._indexerid, self.dirty_setter('_indexerid'))
    # TODO: bring the following line into use when TVEpisode.indexerid is gone
    # epid = property(lambda self: self._epid, self.dirty_setter('_epid'))
    @property
    @deprecated('(TVEpisode) Use epid __getter__ instead')
    def indexerid(self):
        return self.epid

    @property
    def epid(self):
        raise NotImplementedError

    @indexerid.setter
    @deprecated('(TVEpisode) Use epid __setter__ instead')
    def indexerid(self, val):
        self.epid = val

    @epid.setter
    def epid(self, val):
        raise NotImplementedError


class LegacySearchResult(object):

    @property
    @deprecated('(Classes.SearchResult) Use show_obj __getter__ instead')
    def show(self):
        return self.show_obj

    @property
    def show_obj(self):
        raise NotImplementedError

    @show.setter
    @deprecated('(Classes.SearchResult) Use show_obj __setter__ instead')
    def show(self, val):
        self.show_obj = val

    @show_obj.setter
    def show_obj(self, *arg):
        raise NotImplementedError


class LegacyProper(object):

    def __init__(self, show=None, **kwargs):
        if show:
            self.show_obj = show

    @property
    @deprecated('(Classes.Proper) Use show_obj __getter__ instead')
    def show(self):
        return self.show_obj

    @property
    def show_obj(self):
        raise NotImplementedError

    @show.setter
    @deprecated('(Classes.Proper) Use show_obj __setter__ instead')
    def show(self, val):
        self.show_obj = val

    @show_obj.setter
    def show_obj(self, *arg):
        raise NotImplementedError


class LegacyFailedProcessor(object):

    @property
    @deprecated('(FailedProcessor) Use show_obj __getter__ instead')
    def show(self):
        return self.show_obj

    @property
    def show_obj(self):
        raise NotImplementedError

    @show.setter
    @deprecated('(FailedProcessor) Use show_obj __getter__ instead')
    def show(self, val):
        self.show_obj = val

    @show_obj.setter
    def show_obj(self, *arg):
        raise NotImplementedError

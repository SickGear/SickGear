import re
import threading

# noinspection PyProtectedMember,PyUnresolvedReferences
from concurrent.futures.thread import _WorkItem


class GenericWorkItem(_WorkItem):

    number_regex = re.compile(r'(_\d+)$')

    def _set_thread_name(self):
        try:
            ct = threading.current_thread()
            ct.name = '%s^WEB%s' % (self.args[0].__class__.__name__.upper(), self.number_regex.search(ct.name).group(1))
        except (BaseException, Exception):
            pass

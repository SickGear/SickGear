# coding=utf-8
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

# noinspection PyUnresolvedReferences
import sys

# noinspection PyProtectedMember
from .futures.thread import _base, BrokenThreadPool, ThreadPoolExecutor

from .base import *


class SgWorkItem(GenericWorkItem):

    def run(self):
        if self.future.set_running_or_notify_cancel():
            try:
                self._set_thread_name()
                result = self.fn(*self.args, **self.kwargs)
            except (BaseException, Exception):
                e, tb = sys.exc_info()[1:]
                self.future.set_exception_info(e, tb)
            else:
                self.future.set_result(result)


class SgThreadPoolExecutor(ThreadPoolExecutor):

    def submit(self, fn, *args, **kwargs):
        with self._shutdown_lock:
            if self._broken:
                raise BrokenThreadPool(self._broken)
            if self._shutdown:
                raise RuntimeError('cannot schedule new futures after shutdown')

            f = _base.Future()
            w = SgWorkItem(f, fn, args, kwargs)

            self._work_queue.put(w)
            self._adjust_thread_count()
            return f

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

import sys

# noinspection PyCompatibility
from concurrent.futures import ThreadPoolExecutor
# noinspection PyCompatibility,PyProtectedMember,PyUnresolvedReferences
from concurrent.futures.thread import _base, _shutdown, BrokenThreadPool

from .base import *

ge_py314 = sys.version_info[:3] >= (3, 14)


class SgWorkItem(GenericWorkItem):

    def run(self, *args):
        if self.future.set_running_or_notify_cancel():
            try:
                self._set_thread_name()
                if ge_py314:
                    ctx = args[0]
                    result = ctx.run(self.task)
                else:
                    result = self.fn(*self.args, **self.kwargs)
            except BaseException as exc:
                self.future.set_exception(exc)
                # Break a reference cycle with the exception 'exc'
                self = None
            else:
                self.future.set_result(result)


class SgThreadPoolExecutor(ThreadPoolExecutor):
    def submit(*args, **kwargs):
        if 2 <= len(args):
            self, fn, *args = args
        elif not args:
            raise TypeError('descriptor \'submit\' of \'ThreadPoolExecutor\' object needs an argument')
        elif 'fn' in kwargs:
            fn = kwargs.pop('fn')
            self, *args = args
            import warnings
            warnings.warn('Passing \'fn\' as keyword argument is deprecated', DeprecationWarning, stacklevel=2)
        else:
            raise TypeError('submit expected at least 1 positional argument, got %d' % (len(args) - 1))

        with self._shutdown_lock:
            if self._broken:
                raise BrokenThreadPool(self._broken)
            if self._shutdown:
                raise RuntimeError('cannot schedule new futures after shutdown')
            if _shutdown:
                raise RuntimeError('cannot schedule new futures after interpreter shutdown')

            f = _base.Future()
            if ge_py314:
                task = self._resolve_work_item_task(fn, args, kwargs)
                w = SgWorkItem(f, task)
            else:
                w = SgWorkItem(f, fn, args, kwargs)

            self._work_queue.put(w)
            self._adjust_thread_count()
            return f

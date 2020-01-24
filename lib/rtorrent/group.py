# Copyright (c) 2013 Dean Gardiner, <gardiner91@gmail.com>
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from . import rpc
from .rpc import Method

from _23 import filter_iter


class Group(object):
    __name__ = 'Group'

    def __init__(self, _rt_obj, name):
        self._rt_obj = _rt_obj
        self.name = name
        self.multicall_add = None

        self.methods = [
            # RETRIEVERS
            Method(Group, 'get_max', 'group.' + self.name + '.ratio.max', varname='max'),
            Method(Group, 'get_min', 'group.' + self.name + '.ratio.min', varname='min'),
            Method(Group, 'get_upload', 'group.' + self.name + '.ratio.upload', varname='upload'),

            # MODIFIERS
            Method(Group, 'set_max', 'group.' + self.name + '.ratio.max.set', varname='max'),
            Method(Group, 'set_min', 'group.' + self.name + '.ratio.min.set', varname='min'),
            Method(Group, 'set_upload', 'group.' + self.name + '.ratio.upload.set', varname='upload')
        ]

        # noinspection PyProtectedMember
        rpc._build_rpc_methods(self, self.methods)

        # Setup multicall_add method
        caller = (lambda mc, method, *args: mc.add(method, *args))
        setattr(self, 'multicall_add', caller)

    def _get_prefix(self):
        return 'group.' + self.name + '.ratio.'

    def update(self):
        mc = rpc.Multicall(self)

        for method in filter(lambda m: m.is_retriever() and m.is_available(self._rt_obj), self.methods):
            mc.add(method)

        mc.call()

    def enable(self):
        p = self._rt_obj.get_connection()
        return getattr(p, self._get_prefix() + 'enable')()

    def disable(self):
        p = self._rt_obj.get_connection()
        return getattr(p, self._get_prefix() + 'disable')()

    def _get_method(self, *choices):
        try:
            return next(filter_iter(lambda method: self._rt_obj.method_exists(method), choices))
        except (BaseException, Exception):
            pass

    def set_command(self, *methods):
        method = self._get_method(*('system.method.set', 'method.set'))
        if method:
            methods = [m + '=' for m in methods]

            mc = rpc.Multicall(self)

            self.multicall_add(
                mc, method,
                self._get_prefix() + 'command',
                *methods
            )

            return mc.call()[-1]

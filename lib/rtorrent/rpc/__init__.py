# Copyright (c) 2013 Chris Lucas, <chris@chrisjlucas.com>
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
# THE SOFTWARE IS PROVIDED "AS IS",  WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from ..common import bool_to_int, convert_version_tuple_to_str, safe_repr
from ..compat import xmlrpclib
from ..err import MethodError

import inspect
import re

import rtorrent

from _23 import filter_iter, map_list


def get_varname(rpc_call):
    """Transform rpc method into variable name.

    @newfield example: Example
    @example: if the name of the rpc method is 'p.get_down_rate', the variable
    name will be 'down_rate'
    """
    # extract variable name from xmlrpc func name
    r = re.search(
        r'(^([dtfp]|system)\.|(is|[sg]et)_)+([^=]*?)(?:=|.[sg]et)?$', rpc_call, re.I)
    if r:
        return r.groups()[-1]


def _handle_unavailable_rpc_method(method, rt_obj):
    msg = 'Method isn\'t available.'
    if rt_obj.get_client_version_tuple() < method.min_version:
        msg = 'This method is only available in ' \
              'RTorrent version v{0} or later'.format(convert_version_tuple_to_str(method.min_version))

    raise MethodError(msg)


class DummyClass(object):
    def __init__(self):
        pass


class Method(object):
    """Represents an individual RPC method"""

    def __init__(self, _class, method_name, rpc_call, docstring=None, **kwargs):
        self._class = _class  # : Class this method is associated with
        self.class_name = _class.__name__
        self.method_name = method_name  # : name of public-facing method
        self.rpc_call = rpc_call  # : name of rpc method
        self.docstring = docstring  # : docstring for rpc method (optional)
        self.min_version = kwargs.get('min_version', (0, 0, 0))  # : Minimum version of rTorrent required
        self.boolean = kwargs.get('boolean', False)  # : returns boolean value?
        self.post_process_func = kwargs.get('post_process_func', None)  # : custom post process function
        self.aliases = kwargs.get('aliases', [])  # : aliases for method (optional)
        self.required_args = []  # : Arguments required when calling the method (not utilized)
        self.method_type = self._get_method_type()
        self.varname = None  # : variable for the result of the method call, usually set to self.varname

    def __repr__(self):
        return safe_repr('Method(method_name="{0}", rpc_call="{1}")', self.method_name, self.rpc_call)

    def _get_method_type(self):
        """Determine whether method is a modifier or a retriever"""
        if 'set_' == self.method_name[:4]:
            return 'm'  # modifier
        return 'r'  # retriever

    def is_modifier(self):
        return 'm' == self.method_type

    def is_retriever(self):
        return 'r' == self.method_type

    def is_available(self, rt_obj):

        if rt_obj.get_client_version_tuple() >= self.min_version:
            try:
                self.varname = get_varname(next(filter_iter(lambda f: rt_obj.method_exists(f),
                                                            (self.rpc_call,) + tuple(getattr(self, 'aliases', '')))))
                return True
            except IndexError:
                pass

        return False


class Multicall(object):
    # noinspection PyUnusedLocal
    def __init__(self, class_obj, **kwargs):
        self.class_obj = class_obj
        if 'RTorrent' == class_obj.__class__.__name__:
            self.rt_obj = class_obj
        else:
            # noinspection PyProtectedMember
            self.rt_obj = class_obj._rt_obj
        self.calls = []

    def add(self, method, *args):
        """Add call to multicall

        @param method: L{Method} instance or name of raw RPC method
        @type method: Method or str

        @param args: call arguments
        """
        # if a raw rpc method was given instead of a Method instance,
        # try and find the instance for it. And if all else fails, create a
        # dummy Method instance
        if isinstance(method, str):
            result = find_method(method)
            # if result not found
            if -1 == result:
                # noinspection PyTypeChecker
                method = Method(DummyClass, method, method)
            else:
                method = result

        # ensure method is available before adding
        if not method.is_available(self.rt_obj):
            _handle_unavailable_rpc_method(method, self.rt_obj)

        self.calls.append((method, args))

    def list_calls(self):
        for c in self.calls:
            print(c)

    def call(self):
        """Execute added multicall calls

        @return: the results (post-processed), in the order they were added
        @rtype: tuple
        """
        xmc = xmlrpclib.MultiCall(self.rt_obj.get_connection())
        for call in self.calls:
            method, args = call
            rpc_call = method.rpc_call
            if not self.rt_obj.method_exists(rpc_call):
                for alias in getattr(method, 'aliases', None) or []:
                    if self.rt_obj.method_exists(alias):
                        rpc_call = alias
                        break
            getattr(xmc, rpc_call)(*args)

        try:
            results = tuple(next(filter_iter(lambda x: isinstance(x, list), xmc().results)))
        except IndexError:
            return [[]]

        results_processed = []

        for r, c in list(zip(results, self.calls)):
            method = c[0]  # Method instance
            result = process_result(method, r)
            results_processed.append(result)
            # assign result to class_obj
            exists = hasattr(self.class_obj, method.varname)
            if not exists or not inspect.ismethod(getattr(self.class_obj, method.varname)):
                setattr(self.class_obj, method.varname, result)

        return tuple(results_processed)


def call_method(class_obj, method, *args):
    """Handles single RPC calls

    @param class_obj: Peer/File/Torrent/Tracker/RTorrent instance
    @type class_obj: object

    @param method: L{Method} instance or name of raw RPC method
    @type method: Method or str
    """
    if method.is_retriever():
        args = args[:-1]
    else:
        assert args[-1] is not None, 'No argument given.'

    if 'RTorrent' == class_obj.__class__.__name__:
        rt_obj = class_obj
    else:
        # noinspection PyProtectedMember,PyUnresolvedReferences
        rt_obj = class_obj._rt_obj

    # check if rpc method is even available
    if not method.is_available(rt_obj):
        _handle_unavailable_rpc_method(method, rt_obj)

    mc = Multicall(class_obj)
    mc.add(method, *args)
    # only added one method, only getting one result back
    ret_value = mc.call()[0]

    return ret_value


def find_method(rpc_call):
    """Return L{Method} instance associated with given RPC call"""
    try:
        rpc_call = rpc_call.lower()
        return next(filter_iter(lambda m: rpc_call in map_list(
            lambda n: n.lower(), [m.rpc_call] + list(getattr(m, 'aliases', []))),
                      rtorrent.methods + rtorrent.torrent.methods +
                      rtorrent.file.methods + rtorrent.tracker.methods + rtorrent.peer.methods))
    except IndexError:
        return -1


def process_result(method, result):
    """Process given C{B{result}} based on flags set in C{B{method}}

    @param method: L{Method} instance
    @type method: Method

    @param result: result to be processed (the result of given L{Method} instance)

    @note: Supported Processing:
        - bololean - convert ones and zeros returned by rTorrent and
        convert to python boolean values
    """
    # handle custom post processing function
    if method.post_process_func is not None:
        result = method.post_process_func(result)

    # is boolean?
    if method.boolean:
        if result in [1, '1']:
            result = True
        elif result in [0, '0']:
            result = False

    return result


def _build_rpc_methods(class_, method_list):
    """Build glorified aliases to raw RPC methods"""
    instance = None
    if not inspect.isclass(class_):
        instance = class_
        class_ = instance.__class__

    method_store = (instance, class_)[None is instance]
    for m in method_list:
        class_name = m.class_name
        if class_name != class_.__name__:
            continue

        caller = None
        if 'RTorrent' == class_name:
            caller = (lambda self, arg=None, method=m: call_method(self, method, bool_to_int(arg)))
        elif class_name in ['Torrent', 'Tracker', 'File', 'Peer']:
            caller = (lambda self, arg=None, method=m: call_method(self, method, self.rpc_id, bool_to_int(arg)))
        elif 'Group' == class_name:
            caller = (lambda arg=None, method=m: call_method(instance, method, bool_to_int(arg)))

        if None is not caller:
            for method_name in [m.method_name] + list(getattr(m, 'aliases', [])):
                setattr(method_store, method_name, caller)

            m.docstring = m.docstring or ''
            caller.__doc__ = """{0}
    
            @note: Variable where the result for this method is stored: {1}.{2}""".format(
                m.docstring, class_name, m.varname)  # print(m)

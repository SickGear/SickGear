import functools
from hachoir.core.iso639 import ISO639_2


@functools.total_ordering
class Language:

    def __init__(self, code):
        code = str(code)
        if code not in ISO639_2:
            raise ValueError("Invalid language code: %r" % code)
        self.code = code

    def __eq__(self, other):
        if other.__class__ != Language:
            return NotImplemented
        return self.code == other.code

    def __lt__(self, other):
        if other.__class__ != Language:
            return NotImplemented
        return self.code < other.code

    def __str__(self):
        return ISO639_2[self.code]

    def __repr__(self):
        return "<Language '%s', code=%r>" % (str(self), self.code)

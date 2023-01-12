"""
Parent of all field classes in :mod:`hachoir.field`.
"""

from hachoir.stream import InputFieldStream
from hachoir.core.log import Logger
from hachoir.core.tools import makePrintable
from weakref import ref as weakref_ref


class FieldError(Exception):
    """
    Error raised by a :class:`Field`
    """
    pass


def joinPath(path, name):
    if path != "/":
        return "/".join((path, name))
    else:
        return "/%s" % name


class MissingField(KeyError, FieldError):

    def __init__(self, field, key):
        KeyError.__init__(self)
        self.field = field
        self.key = key

    def __str__(self):
        return 'Can\'t get field "%s" from %s' % (self.key, self.field.path)


class Field(Logger):
    static_size = None
    """(optional) Helper to compute field size.

    May have types:
        None: field size is computed dynamically.
        int: field size, in bits.
        callable: function that receives the same arguments as the constructor,
            without ``parent``.
    """

    is_field_set = False
    """bool: True if this field contains other fields (ie. is a field set),
    False otherwise.
    """

    def __init__(self, parent, name, size=None, description=None):
        """Set default class attributes, set right address if None address is
        given.

        Args:
            parent (Field): Parent field of this field
            name (str): The name of the field, it must be unique in `parent`. If
                it ends with `[]`, end will be replaced with "[new_id]" (eg.
                "raw[]" becomes "raw[0]", next will be "raw[1]", and then
                "raw[2]", etc.)
            size (int, optional): Size of the field in bits. If `None` then it
                will be computed later.
            address (int, optional): Address in bit relative to the parent
                absolute address.
            description (str, optional): String description
        """
        assert issubclass(parent.__class__, Field)
        assert (size is None) or (0 <= size)
        self._parent = parent
        if not name:
            raise ValueError("empty field name")
        self._name = name
        self._address = parent.nextFieldAddress()
        self._size = size
        self._description = description

    def _logger(self):
        return self.path

    def createDescription(self):
        """Override in derived classes to provide :attr:`description`."""
        return ""

    @property
    def description(self):
        """str: Informal description of this field. Cached.

        The description of a field may provide a general summary of its usage
        or for field sets it can be used to give a short indication of the
        contents without having to expand the node.
        """
        if self._description is None:
            try:
                self._description = self.createDescription()
                if isinstance(self._description, str):
                    self._description = makePrintable(
                        self._description, "ISO-8859-1")
            except Exception as err:
                self.error("Error getting description: " + str(err))
                self._description = ""
        return self._description

    def __str__(self):
        """Alias for :attr:`display`."""
        return self.display

    def __repr__(self):
        return "<%s path=%r, address=%s, size=%s>" % (
            self.__class__.__name__, self.path, self._address, self._size)

    def hasValue(self):
        """bool: Check if field has a value."""
        return self.value is not None

    def createValue(self):
        """Override in derived classes to provide :attr:`value`."""
        raise NotImplementedError()

    @property
    def value(self):
        """Value of field."""
        try:
            return self.__value
        except AttributeError:
            try:
                self.__value = self.createValue()
            except Exception as err:
                self.error("Unable to create value: %s" % str(err))
                self.__value = None
            return self.__value

    @property
    def parent(self):
        """GenericFieldSet: Parent of this field."""
        return self._parent

    def createDisplay(self):
        """Override in derived classes to provide :attr:`display`."""
        return str(self.value)

    @property
    def display(self):
        """str: Short, human-friendly string representing field contents."""
        try:
            return self.__display
        except AttributeError:
            try:
                self.__display = self.createDisplay()
            except Exception as err:
                self.error("Unable to create display: %s" % err)
                self.__display = ""
            return self.__display

    def createRawDisplay(self):
        value = self.value
        if isinstance(value, str):
            return makePrintable(value, "ASCII")
        else:
            return str(value)

    @property
    def raw_display(self):
        """str: Represents raw field content"""
        try:
            return self.__raw_display
        except AttributeError:
            try:
                self.__raw_display = self.createRawDisplay()
            except Exception as err:
                self.error("Unable to create raw display: %s" % err)
                self.__raw_display = ""
            return self.__raw_display

    @property
    def name(self):
        """str: Field name, unique in its parent field set list."""
        return self._name

    @property
    def index(self):
        """int: index of the field in parent field set, starting from 0."""
        if not self._parent:
            return None
        return self._parent.getFieldIndex(self)

    @property
    def path(self):
        """str: Full path of this field starting from the root field."""
        if not self._parent:
            return '/'
        names = []
        field = self
        while field is not None:
            names.append(field._name)
            field = field._parent
        names[-1] = ''
        return '/'.join(reversed(names))

    @property
    def address(self):
        """int: Relative address to parent address, in bits."""
        return self._address

    @property
    def absolute_address(self):
        """int: Absolute address (from beginning of stream), in bits."""
        address = self._address
        current = self._parent
        while current:
            address += current._address
            current = current._parent
        return address

    @property
    def size(self):
        """int: Size of this field, in bits. Cached."""
        return self._size

    def _getField(self, name, const):
        if name.strip("."):
            return None
        field = self
        for index in range(1, len(name)):
            field = field._parent
            if field is None:
                break
        return field

    def getField(self, key, const=True):
        """
        Args:
            key (str): relative or absolute path for the desired field.
            const (bool): For field sets, whether to consume additional input to
                find a matching field.

        Returns:
            Field: The field matching the provided path.
        """
        if key:
            if key[0] == "/":
                if self._parent:
                    current = self._parent.root
                else:
                    current = self
                if len(key) == 1:
                    return current
                key = key[1:]
            else:
                current = self
            for part in key.split("/"):
                field = current._getField(part, const)
                if field is None:
                    raise MissingField(current, part)
                current = field
            return current
        raise KeyError("Key must not be an empty string!")

    def __getitem__(self, key):
        """Alias for :meth:`getField`, with ``const=False``"""
        return self.getField(key, False)

    def __contains__(self, key):
        """Check whether a field set contains the provided field.

        Args:
            key (str): The path to the field.

        Returns:
            bool
        """
        try:
            return self.getField(key, False) is not None
        except FieldError:
            return False

    def _createInputStream(self, **args):
        """Override in derived classes to provide the input stream returned by
        :meth:`getSubIStream`.

        Returns:
            InputFieldStream
        """
        assert self._parent
        return InputFieldStream(self, **args)

    def getSubIStream(self):
        """
        Returns:
            InputFieldStream: an input stream containing the field content.
        """
        if hasattr(self, "_sub_istream"):
            stream = self._sub_istream()
        else:
            stream = None
        if stream is None:
            stream = self._createInputStream()
            self._sub_istream = weakref_ref(stream)
        return stream

    def setSubIStream(self, createInputStream):
        """
        Args:
            createInputStream (``callback(cis, **args)``): Function to use in place of
                :meth:`_createInputStream`. Receives the previous value of
                ``_createInputStream`` as its first argument, for chaining.
        """
        cis = self._createInputStream
        self._createInputStream = lambda **args: createInputStream(cis, **args)

    def __bool__(self):
        """Method called by code like "if field: (...)".
        Always returns True
        """
        return True

    def getFieldType(self):
        return self.__class__.__name__

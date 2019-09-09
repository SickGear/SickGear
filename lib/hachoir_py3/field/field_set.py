from hachoir_py3.field import BasicFieldSet, GenericFieldSet


class FieldSet(GenericFieldSet):

    def __init__(self, parent, name, *args, **kw):
        assert issubclass(parent.__class__, BasicFieldSet)
        GenericFieldSet.__init__(
            self, parent, name, parent.stream, *args, **kw)

cdef extern from *:
    """
    /* Cython 3.2 emits this Python 3.8 symbol for limited-API imports. */
    #if defined(Py_LIMITED_API) && Py_LIMITED_API < 0x03080000
        static PyObject *charset_normalizer_import_get_module(PyObject *name) {
            PyObject *modules = PyImport_GetModuleDict();
            PyObject *module = PyDict_GetItemWithError(modules, name);
            Py_XINCREF(module);
            return module;
        }
        #define PyImport_GetModule charset_normalizer_import_get_module
    #endif

    /* Keep native Unicode reads fast while retaining cp37-abi3 support. */
    #ifdef Py_LIMITED_API
        #define charset_normalizer_unicode_kind(unicode) (0)
        #define charset_normalizer_unicode_data(unicode) (NULL)
        #define charset_normalizer_unicode_read(unicode, kind, data, index) \
            ((void)(kind), (void)(data), PyUnicode_ReadChar((unicode), (index)))
    #else
        #define charset_normalizer_unicode_kind(unicode) PyUnicode_KIND(unicode)
        #define charset_normalizer_unicode_data(unicode) PyUnicode_DATA(unicode)
        #define charset_normalizer_unicode_read(unicode, kind, data, index) \
            PyUnicode_READ((kind), (data), (index))
    #endif
    """
    int _unicode_kind "charset_normalizer_unicode_kind"(object unicode) noexcept
    void* _unicode_data "charset_normalizer_unicode_data"(object unicode) noexcept
    Py_UCS4 _unicode_read "charset_normalizer_unicode_read"(
        object unicode, int kind, void* data, Py_ssize_t index
    ) noexcept

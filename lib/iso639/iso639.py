from functools import lru_cache
from operator import itemgetter
from typing import Dict, Iterator, List, Optional, Set, Tuple, Union

from .datafile import load_file
from .exceptions import DeprecatedLanguageValue, InvalidLanguageValue


class Lang(tuple):
    """ISO 639 reference name and identifiers of a language or group of
    languages.

    Can be instantiated with any ISO 639 identifier or name as an argument.
    Case sensitive.

    ...

    Parameters
    ----------
    name_or_identifier : str or Lang, optional
        ISO 639 identifier or name, by default None.
    name : str, optional
        ISO 639 name (or other name), by default None.
    pt1 : str, optional
        Two-letter ISO 639-1 identifier, by default None.
    pt2b : str, optional
        Three-letter ISO 639-2/B identifier for bibliographic applications, by
        default None.
    pt2t : str, optional
        Three-letter ISO 639-2/T identifier for terminology applications, by
        default None.
    pt3 : str, optional
        Three-letter ISO 639-3 identifier, by default None.
    pt5 : str, optional
        Three-letter ISO 639-5 identifier, by default None.

    Raises
    ------
    InvalidLanguageValue
        Raised when the arguments are not valid and compatible.
    DeprecatedLanguageValue
        Raised when the arguments point to a deprecated ISO 639 language name
        or identifier.

    Attributes
    ----------
    name : str
        ISO 639-3 reference name for languages, ISO 639-5 English name for
        groups of languages.
    pt1 : str
        Two-letter ISO 639-1 identifier, if there is one.
    pt2b : str
        Three-letter ISO 639-2/B identifier for bibliographic applications, if
        there is one.
    pt2t : str
        Three-letter ISO 639-2/T identifier for terminology applications,
        if there is one.
    pt3 : str
        Three-letter ISO 639-3 identifier, if there is one.
    pt5 : str
        Three-letter ISO 639-5 identifier, if there is one.

    Examples
    --------
    >>> lg = Lang("eng")
    >>> lg
    Lang(name='English', pt1='en', pt2b='eng', pt2t='eng', pt3='eng', pt5='')
    >>> lg.name
    'English'
    """

    _tags = ("name", "pt1", "pt2b", "pt2t", "pt3", "pt5")
    _abrs = {
        "A": "Ancient",
        "C": "Constructed",
        "E": "Extinct",
        "H": "Historical",
        "I": "Individual",
        "L": "Living",
        "M": "Macrolanguage",
        "S": "Special",
    }

    _data = load_file("mapping_data")
    _scope = load_file("mapping_scope")
    _type = load_file("mapping_type")
    _deprecated = load_file("mapping_deprecated")
    _macro = load_file("mapping_macro")
    _ref_name = load_file("mapping_ref_name")
    _other_names = load_file("mapping_other_names")

    __slots__ = ()  # set immutability of Lang

    def __new__(
        cls,
        name_or_identifier: Optional[Union[str, "Lang"]] = None,
        name: Optional[str] = None,
        pt1: Optional[str] = None,
        pt2b: Optional[str] = None,
        pt2t: Optional[str] = None,
        pt3: Optional[str] = None,
        pt5: Optional[str] = None,
    ):
        # parse main argument
        if name_or_identifier is None:
            arg_lang_tuple = None
        else:
            arg_lang_tuple = cls._validate_arg(name_or_identifier)

        # parse other arguments
        if all(v is None for v in (name, pt1, pt2b, pt2t, pt3, pt5)):
            kwargs_lang_tuple = None
        else:
            kwargs_lang_tuple = cls._validate_kwargs(
                name=name, pt1=pt1, pt2b=pt2b, pt2t=pt2t, pt3=pt3, pt5=pt5
            )

        # check compatiblity between main argument and other arguments
        if arg_lang_tuple is None and kwargs_lang_tuple is None:
            lang_tuple = None
        elif arg_lang_tuple is not None and kwargs_lang_tuple is None:
            lang_tuple = arg_lang_tuple
        elif kwargs_lang_tuple is not None and arg_lang_tuple is None:
            lang_tuple = kwargs_lang_tuple
        elif (
            arg_lang_tuple is not None
            and kwargs_lang_tuple is not None
            and arg_lang_tuple == kwargs_lang_tuple
        ):
            lang_tuple = arg_lang_tuple
        else:
            lang_tuple = tuple()

        # chack if arguments match a deprecated language value
        if lang_tuple == tuple():
            cls._assert_not_deprecated(
                name_or_identifier=name_or_identifier,
                name=name,
                pt1=pt1,
                pt2b=pt2b,
                pt2t=pt2t,
                pt3=pt3,
                pt5=pt5,
            )

        if not lang_tuple:
            raise InvalidLanguageValue(
                name_or_identifier=name_or_identifier,
                name=name,
                pt1=pt1,
                pt2b=pt2b,
                pt2t=pt2t,
                pt3=pt3,
                pt5=pt5,
            )
        else:
            # instantiate as a tuple of ISO 639 language values
            return tuple.__new__(cls, lang_tuple)

    def __repr__(self):
        chunks = ["=".join((tg, repr(getattr(self, tg)))) for tg in self._tags]

        return "Lang({})".format(", ".join(chunks))

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return type(other) is type(self) and hash(other) == hash(self)

    def __lt__(self, other) -> bool:
        for i in range(min(len(self), len(other))):
            if self[i] < other[i]:
                return True
            elif self[i] > other[i]:
                return False
        return len(self) < len(other)

    def __getnewargs__(self):
        unpickling_args = (self.name,)

        return unpickling_args

    @property
    def name(self) -> str:
        """The ISO 639 reference name of the language or group of languages."""
        return tuple.__getitem__(self, 0)

    @property
    def pt1(self) -> str:
        """The ISO 639-1 identifier of the language."""
        return tuple.__getitem__(self, 1)

    @property
    def pt2b(self) -> str:
        """The ISO 639-2/B identifier of the language or group of languages."""
        return tuple.__getitem__(self, 2)

    @property
    def pt2t(self) -> str:
        """The ISO 639-2/T identifier of the language or group of languages."""
        return tuple.__getitem__(self, 3)

    @property
    def pt3(self) -> str:
        """The ISO 639-3 identifier of the language."""
        return tuple.__getitem__(self, 4)

    @property
    def pt5(self) -> str:
        """The ISO 639-5 identifier of the group of languages."""
        return tuple.__getitem__(self, 5)

    def asdict(self) -> Dict[str, str]:
        """Get the attributes of the `Lang` as a Python dictionary.

        Returns
        -------
        Dict[str, str]
            A dictionary containing the values of the 'name', 'pt1', 'pt2b',
            'pt2t', 'pt3' and 'pt5' attibutes.
        """

        return {tg: getattr(self, tg) for tg in self._tags}

    def scope(self) -> Optional[str]:
        """Get the scope of the language according to ISO 639-3.

        Returns
        -------
        str
            The scope of the language among 'Individual','Macrolanguage' and
            'Special'. Returns None for groups of languages.
        """
        return self._get_scope(self.pt3)

    def type(self) -> Optional[str]:
        """Get the type of the language according to ISO 639-3.

        Returns
        -------
        str
            The ISO 639-3 type of this language among 'Ancient',
            'Constructed', 'Extinct', 'Historical', 'Living' and'Special'.
            Returns None for groups of languages.
        """
        return self._get_type(self.pt3)

    def macro(self) -> Optional["Lang"]:
        """Get the macrolanguage of an individual language.

        Returns
        -------
        iso639.Lang
            The macrolanguage of the individual language, if there is one.
        """
        macro_pt3 = self._get_macro(self.pt3)
        return Lang(macro_pt3) if macro_pt3 else macro_pt3

    def individuals(self) -> List["Lang"]:
        """Get all individual languages of a macrolanguage.

        Returns
        -------
        list of Lang
            The `Lang` instances of the individual languages of a
            macrolanguage, sorted by name.
        """
        return [Lang(ind) for ind in self._get_individuals(self.pt3)]

    def other_names(self) -> List[str]:
        """Get all the names of this language that are not its reference name.

        Returns
        -------
        list of str
            The possible other ISO 639-3 printed names or ISO 639-3 inverted
            names or ISO 639-2 English names of the language, in alphabetical
            order.
        """
        return self._get_other_names(self.name)

    @classmethod
    def _validate_arg(cls, arg_value):
        if isinstance(arg_value, Lang):
            return tuple(map(lambda x: getattr(arg_value, x), cls._tags))
        elif isinstance(arg_value, str):
            if len(arg_value) == 3 and arg_value.lower() == arg_value:
                for tg in ("pt3", "pt2b", "pt2t", "pt5"):
                    lang_tuple = cls._get_language_tuple(tg, arg_value)
                    if lang_tuple:
                        return lang_tuple
            elif len(arg_value) == 2 and arg_value.lower() == arg_value:
                return cls._get_language_tuple("pt1", arg_value)
            else:
                return cls._get_language_tuple("name", arg_value)

        return tuple()

    @classmethod
    def _validate_kwargs(cls, **kwargs):
        lang_tuples = set()
        for tg, v in kwargs.items():
            if v:
                lang_tuples.add(cls._get_language_tuple(tg, v))
        if len(lang_tuples) == 1:
            return lang_tuples.pop()

        return tuple()

    @classmethod
    def _assert_not_deprecated(cls, **kwargs):
        deprecated = []
        for kw, arg_value in kwargs.items():
            if arg_value is None:
                continue
            elif kw == "name_or_identifier":
                keys = ("id", "name")
            elif kw == "name":
                keys = ("name",)
            elif kw in ("pt1", "pt2b", "pt2t", "pt3", "pt5"):
                keys = ("id",)
            else:
                keys = ()

            for k in keys:
                try:
                    d = cls._deprecated[k][arg_value]
                except KeyError:
                    pass
                else:
                    d[k] = arg_value
                    deprecated.append(d)

        if deprecated and deprecated.count(deprecated[0]) == 1:
            raise DeprecatedLanguageValue(**deprecated[0])

        return True

    @classmethod
    def _get_language_tuple(cls, tag, arg_value):
        if tag == "name":
            ref_value = cls._ref_name.get(arg_value, arg_value)
        else:
            ref_value = arg_value

        try:
            lang_dict = cls._data[tag][ref_value]
        except KeyError:
            lang_tuple = tuple()
        else:
            lang_dict[tag] = ref_value
            lang_tuple = itemgetter(*cls._tags)(lang_dict)

        return lang_tuple

    @classmethod
    def _get_scope(cls, pt3_value):
        abr = cls._scope.get(pt3_value)

        return cls._abrs.get(abr)

    @classmethod
    def _get_type(cls, pt3_value):
        abr = cls._type.get(pt3_value)

        return cls._abrs.get(abr)

    @classmethod
    def _get_macro(cls, pt3_value):
        return cls._macro["individual"].get(pt3_value)

    @classmethod
    def _get_individuals(cls, pt3_value):
        return cls._macro["macro"].get(pt3_value, [])

    @classmethod
    def _get_other_names(cls, ref_name_value):
        return cls._other_names.get(ref_name_value, [])


def iter_langs() -> Iterator[Lang]:
    """Iterate through all languages that are in ISO 639.

    Does not yield languages that are depracted according to ISO 639.

    Yields
    -------
    Lang
        `Lang` instances ordered alphabetically by reference name.
    """
    sorted_lang_names = load_file("list_langs")

    return (Lang(lang_name) for lang_name in sorted_lang_names)


@lru_cache
def _get_language_values(identifiers_or_names: Tuple[str]) -> Set[str]:
    tags = set(identifiers_or_names)
    all_tags = {"pt1", "pt2b", "pt2t", "pt3", "pt5", "name", "other_name"}
    invalid_tags = tags - all_tags
    if invalid_tags:
        raise ValueError(
            f"Invalid identifiers or names: {', '.join(invalid_tags)}. "
            f"Valid options are: {', '.join(sorted(all_tags))}."
        )
    language_values = set()
    if "other_name" in tags:
        mapping = load_file("mapping_ref_name")
        language_values.update(mapping.keys())
        tags.remove("other_name")
    if tags:
        mapping = load_file("mapping_data")
        for tag in tags:
            language_values.update(mapping[tag].keys())
    return language_values


def is_language(
    value: str,
    identifiers_or_names: Union[str, Tuple[str, ...]] = (
        "pt1",
        "pt2b",
        "pt2t",
        "pt3",
        "pt5",
        "name",
        "other_name",
    ),
) -> bool:
    """Check if a given value corresponds to a valid ISO 639 language
    identifier or name.

    Parameters
    ----------
    value : str
        The language value to validate.
    identifiers_or_names : str or tuple of str, optional
        The ISO 639 identifiers or names to check against. Defaults to all
        available identifiers and names.

    Returns
    -------
    bool
        True if the value is valid for the given identifiers and names, False
        otherwise.

    Raises
    ------
    TypeError
        When `identifiers_or_names` is not a tuple or a tuple of strings.
    ValueError
        When string(s) of `identifiers_or_names` are not 'pt1', 'pt2b', 'pt2t',
        'pt3', 'pt5', 'name' or 'other_name'.

    Examples
    --------
    >>> is_language("fr")
    True
    >>> is_language("French")
    True
    >>> is_language("fr", "pt3")
    False
    >>> is_language("fre", ("pt2b", "pt2t"))
    True
    """
    if isinstance(identifiers_or_names, str):
        identifiers_or_names = (identifiers_or_names,)
    elif isinstance(identifiers_or_names, (list, set)) and all(
        isinstance(s, str) for s in identifiers_or_names
    ):
        identifiers_or_names = tuple(identifiers_or_names)
    elif not isinstance(identifiers_or_names, tuple):
        raise TypeError(
            "'identifiers_or_names' must be a string or an iterable of "
            f"strings, got {type(identifiers_or_names).__name__}."
        )
    elif not all(isinstance(s, str) for s in identifiers_or_names):
        all_types = (type(v).__name__ for v in identifiers_or_names)
        raise TypeError(
            "'identifiers_or_names' must be a string or an iterable of "
            f"strings, got tuple of {' and '.join(all_types)}.",
        )
    return value in _get_language_values(identifiers_or_names)

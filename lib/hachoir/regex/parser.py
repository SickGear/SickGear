r"""
Parse string to create Regex object.

TODO:
 - Support \: \001, \x00, \0, \ \[, \(, \{, etc.
 - Support Python extensions: (?:...), (?P<name>...), etc.
 - Support \<, \>, \s, \S, \w, \W, \Z <=> $, \d, \D, \A <=> ^, \b, \B, [[:space:]], etc.
"""

from hachoir.regex import (RegexString, RegexEmpty, RegexRepeat,
                           RegexDot, RegexWord, RegexStart, RegexEnd,
                           RegexRange, RegexRangeItem, RegexRangeCharacter)
import re

REGEX_COMMAND_CHARACTERS = '.^$[](){}|+?*\\'


def parseRange(text, start):
    r"""
    >>> parseRange('[a]b', 1)
    (<RegexRange '[a]'>, 3)
    >>> parseRange('[a-z]b', 1)
    (<RegexRange '[a-z]'>, 5)
    >>> parseRange('[^a-z-]b', 1)
    (<RegexRange '[^a-z-]'>, 7)
    >>> parseRange('[^]-]b', 1)
    (<RegexRange '[^]-]'>, 5)
    >>> parseRange(r'[\]abc]', 1)
    (<RegexRange '[]a-c]'>, 7)
    >>> parseRange(r'[a\-x]', 1)
    (<RegexRange '[ax-]'>, 6)
    """
    index = start
    char_range = []
    exclude = False
    if text[index] == '^':
        exclude = True
        index += 1
    if text[index] == ']':
        char_range.append(RegexRangeCharacter(']'))
        index += 1
    while index < len(text) and text[index] != ']':
        if index + 1 < len(text) \
                and text[index] == '\\':
            char_range.append(RegexRangeCharacter(text[index + 1]))
            index += 2
        elif index + 1 < len(text) \
                and text[index] == '-' and text[index + 1] == ']':
            break
        elif index + 3 < len(text) \
                and text[index + 1] == '-' \
                and text[index + 2] != ']':
            char_range.append(RegexRangeItem(
                ord(text[index]), ord(text[index + 2])))
            index += 3
        else:
            char_range.append(RegexRangeCharacter(text[index]))
            index += 1
    if index < len(text) and text[index] == '-':
        char_range.append(RegexRangeCharacter('-'))
        index += 1
    if index == len(text) or text[index] != ']':
        raise SyntaxError('Invalid range: %s' % text[start - 1:index])
    return RegexRange(char_range, exclude), index + 1


def parseOr(text, start):
    """
    >>> parseOr('(a)', 1)
    (<RegexString 'a'>, 3)
    >>> parseOr('(a|c)', 1)
    (<RegexRange '[ac]'>, 5)
    >>> parseOr(' (a|[bc]|d)', 2)
    (<RegexRange '[a-d]'>, 11)
    """
    index = start
    # (?:...): Skip Python prefix '?:'
    if text[index:index + 2] == '?:':
        index += 2
    if text[index] == '?':
        raise NotImplementedError("Doesn't support Python extension (?...)")
    regex = None
    while True:
        new_regex, index = _parse(text, index, "|)")
        if regex:
            regex = regex | new_regex
        else:
            regex = new_regex
        if len(text) <= index:
            raise SyntaxError('Missing closing parenthesis')
        if text[index] == ')':
            break
        index += 1
    index += 1
    if regex is None:
        regex = RegexEmpty()
    return regex, index


REPEAT_REGEX = re.compile("([0-9]+)(,[0-9]*)?}")


def parseRepeat(text, start):
    """
    >>> parseRepeat('a{0,1}b', 2)
    (0, 1, 6)
    >>> parseRepeat('a{12}', 2)
    (12, 12, 5)
    """
    match = REPEAT_REGEX.match(text, start)
    if not match:
        raise SyntaxError('Unable to parse repetition ' + text[start:])
    rmin = int(match.group(1))
    if match.group(2):
        text = match.group(2)[1:]
        if text:
            rmax = int(text)
        else:
            rmax = None
    else:
        rmax = rmin
    return (rmin, rmax, match.end(0))


CHAR_TO_FUNC = {'[': parseRange, '(': parseOr}
CHAR_TO_CLASS = {'.': RegexDot, '^': RegexStart, '$': RegexEnd}
CHAR_TO_REPEAT = {'*': (0, None), '?': (0, 1), '+': (1, None)}


def _parse(text, start=0, until=None):
    if len(text) == start:
        return RegexEmpty(), 0
    index = start
    regex = RegexEmpty()
    last = None
    while index < len(text):
        char = text[index]
        if until and char in until:
            break
        if char in REGEX_COMMAND_CHARACTERS:
            if char in CHAR_TO_FUNC:
                new_regex, index = CHAR_TO_FUNC[char](text, index + 1)
            elif char in CHAR_TO_CLASS:
                new_regex = CHAR_TO_CLASS[char]()
                index += 1
            elif char == '{':
                rmin, rmax, index = parseRepeat(text, index + 1)
                new_regex = RegexRepeat(last, rmin, rmax)
                last = None
            elif char in CHAR_TO_REPEAT:
                rmin, rmax = CHAR_TO_REPEAT[char]
                if last is None:
                    raise SyntaxError(
                        'Repetition character (%s) without previous expression' % text[index])
                new_regex = RegexRepeat(last, rmin, rmax)
                last = None
                index += 1
            elif char == "\\":
                index += 1
                if index == len(text):
                    raise SyntaxError(
                        "Antislash (\\) without escaped character")
                char = text[index]
                if char == 'b':
                    new_regex = RegexWord()
                else:
                    if not (char in REGEX_COMMAND_CHARACTERS or char in " '"):
                        raise SyntaxError(
                            "Operator '\\%s' is not supported" % char)
                    new_regex = RegexString(char)
                index += 1
            else:
                raise NotImplementedError(
                    "Operator '%s' is not supported" % char)
            if last:
                regex = regex + last
            last = new_regex
        else:
            subtext = text[index]
            index += 1
            if last:
                regex = regex + last
            last = RegexString(subtext)
    if last:
        regex = regex + last
    return regex, index


def parse(text):
    r"""
    >>> parse('')
    <RegexEmpty ''>
    >>> parse('abc')
    <RegexString 'abc'>
    >>> parse("chats?")
    <RegexAnd 'chats?'>
    >>> parse('[bc]d')
    <RegexAnd '[bc]d'>
    >>> parse("\\.")
    <RegexString '\.'>
    """
    regex, index = _parse(text)
    assert index == len(text)
    return regex


if __name__ == "__main__":
    import doctest
    doctest.testmod()

from sys import version_info

try:
    # noinspection PyPackageRequirements
    from lxml import etree
    is_lxml = True
except ImportError:
    is_lxml = False
    etree = None
    if 2 == version_info[0]:
        try:
            # noinspection PyPep8Naming
            import xml.etree.cElementTree as etree
        except ImportError:
            etree = None

if not is_lxml and not etree:
    # noinspection PyPep8Naming
    import xml.etree.ElementTree as etree

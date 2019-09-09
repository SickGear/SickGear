try:
    # noinspection PyPackageRequirements
    from lxml import etree
    is_lxml = True
except ImportError:
    is_lxml = False
    try:
        # noinspection PyPep8Naming
        import xml.etree.cElementTree as etree
    except ImportError:
        # noinspection PyPep8Naming
        import xml.etree.ElementTree as etree

import sys

PY2 = sys.version_info[0] == 2
sub_name = 'feedparser_py%s' % ('3', '2')[PY2]

locals()['feedparser'] = __import__('feedparser')
sys.modules['feedparser'] = __import__(sub_name)

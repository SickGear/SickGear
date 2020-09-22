import sys

PY2 = sys.version_info[0] == 2
sub_name = 'diskcache_py%s' % ('3', '2')[PY2]

locals()['diskcache'] = __import__('diskcache')
sys.modules['diskcache'] = __import__(sub_name)

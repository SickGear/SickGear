import sys

PY2 = sys.version_info[0] == 2
sub_name = 'soupsieve_py%s' % ('3', '2')[PY2]

locals()['soupsieve'] = __import__('soupsieve')
sys.modules['soupsieve'] = __import__(sub_name)

import sys

PY2 = sys.version_info[0] == 2
sub_name = 'bs4_py%s' % ('3', '2')[PY2]

locals()['bs4'] = __import__('bs4')
sys.modules['bs4'] = __import__(sub_name)
sys.modules['bs4.element'] = __import__('%s.element' % sub_name)
sys.modules['bs4.builder'] = __import__('%s.builder' % sub_name)

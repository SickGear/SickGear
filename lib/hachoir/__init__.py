import sys

PY2 = sys.version_info[0] == 2
sub_name = 'hachoir_py%s' % ('3', '2')[PY2]

locals()['hachoir'] = __import__('hachoir')
sys.modules['hachoir'] = __import__(sub_name)
for mod, subs in [('parser', ['createParser']), ('metadata', ['extractMetadata']), ('stream', ['FileInputStream'])]:
    package = __import__('%s.%s' % (sub_name, mod), fromlist=subs)
    sys.modules['hachoir.%s' % mod] = package
    sys.modules['lib.hachoir.%s' % mod] = package

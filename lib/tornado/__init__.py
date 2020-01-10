import sys

PY2 = sys.version_info[0] == 2
sub_name = 'tornado_py%s' % ('3', '2')[PY2]

main_subs = ['gen', 'escape']
locals()['tornado'] = __import__('tornado', fromlist=main_subs)
sys.modules['tornado'] = __import__(sub_name, fromlist=main_subs)
for mod, subs in [('web', ['RequestHandler', 'StaticFileHandler', 'authenticated', 'Application',
                           '_ApplicationRouter']),
                  ('ioloop', ['IOLoop']),
                  ('routing', ['AnyMatches', 'Rule'])]:
    package = __import__('%s.%s' % (sub_name, mod), fromlist=subs)
    sys.modules['tornado.%s' % mod] = package
    sys.modules['lib.tornado.%s' % mod] = package

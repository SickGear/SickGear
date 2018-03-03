import json
import urllib2

# SickGear APIkey
sg_apikey = 'fa9e0d0b21f563179a0164c78ecb6f61'
# SickGear server detail
sg_host = 'http://localhost:7081'

url = '%s/api/%s/?cmd=sg.updatewatchedstate' % (sg_host, sg_apikey)
payload = json.dumps(dict(
    key01=dict(path_file='\\media\\path\\', played=100, label='Bob', date_watched=1509850398.0),
    key02=dict(path_file='\\media\\path\\file-played1.mkv', played=150, label='Sue', date_watched=1509850398.0),
    key03=dict(path_file='\\media\\path\\file-played2.mkv', played=0, label='Rita', date_watched=1509850398.0)
))
# payload is POST'ed to SG
rq = urllib2.Request(url, data=payload)
r = urllib2.urlopen(rq)
print json.load(r)
r.close()

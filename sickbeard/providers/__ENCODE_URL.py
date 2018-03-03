# 1) copy these imports to top of code

import base64
import random

# 2) run this somewhere
# proxy source providers:
# https://unblocked-pw.github.io/ (aka: https://unblocked.vc/)
# https://unblockall.org/
# https://unblocker.win/
# https://unblocker.cc/
# https://proxyportal.net/
# https://torrents.me/proxy/

# Torrentday
# to_enc = ['workisboring.com', 'unusualperson.com', 'read-books.org', 'servep2p.com', 'net-freaks.com']

# Torrentz2
# to_enc = ['torrentz2.is', 'torrentz2.cc', 'torrentz2.tv',
#           'torrentz.bz', 'torrentz.bypassed.cool', 'torrentz.bypassed.st',
#           'torrentz.immunicity.st', 'torrentz.ukunblock.men',
#           'torrentz.unblocked.bid', 'torrentz.unblocked.lol', 'torrentz.unblocked.st',
#           'torrentz.unblockall.org', 'torrentz.unlockproj.party']

# (PA) proxylist
# https://torrents.me/proxy/
# https://proxyportal.me/thepiratebay-proxy
# The pirate bay, proxies from https://torrents.me/proxy/pirate-bay/
# to_enc = ['bayproxy.win', 'kanyebay.co.uk/?load=', 'piratebay2.org', 'piratebayfast.co.uk/?load=',
#           'piratebayquick.co.uk/?load=', 'pirateproxy.top', 'proxypirate.top', 'proxytpb.website',
#           'prxy.party', 'thehiddenbay.cc', 'themagnetbay.info',
#           'thepiratebay.bypassed.st', 'thepiratebay.immunicity.st',
#           'thepiratebay.unblocked.lol', 'thepiratebay.unblocked.st', 'thepiratebay.unblockall.org',
#           'piratebay.unlockproj.club'
#           'tpbclean.info', 'tpproxy.site', 'tpbproxy.win', 'tpbrun.win'] + \
#          ['knaben.tk/s/keepgoing.php?url=']

# to_enc = ['torlock.unblocked.bet', 'torlock.unblocked.bid', 't0rlock.unblocked.lol']

# Limetorrents
to_enc = ['limetorrents.unblocked.vc', 'limetorrents.unblockall.org',
          'limetorrents.unblocker.cc', 'limetorrents.unblocker.win']

# BT Scene
# to_enc = [
#     # https://
#     'btscene.unblocked.vc', 'btsone1.unblocked.lol',
#     Fails (even though worked 5 mins before):
#     'btscene.unblockall.org', 'btscene.unblocked.st'
#     'btscene.unblocker.cc', 'btscene.unblocker.win']

encoded = []
for url in to_enc:
    url_enc = base64.b64encode(url)
    unused = [{' ', '0', '1', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u',
               'v', 'w', 'x', 'y', 'z', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S',
               'T', 'U', 'V', 'W', 'X', 'Y', 'Z'} - set(url_enc)]
    unused = [x for x in unused[0] if x.lower() in unused[0]]  # remove chars that dont have a lowercase
    chunks, chunk_size = len(url_enc), len(url_enc) // 6
    splat = [url_enc[i:i + chunk_size][::-1] for i in range(0, chunks, chunk_size)]
    encoded.append(([x for x in splat], unused))

_code = ''
for (url_enc, charlist) in encoded:
    chars = []
    b = []
    char = random.choice(charlist)
    chars += [char]
    charlist2 = list(''.join(charlist).replace(char, ''))
    char2 = random.choice(charlist2)
    chars += [' ', char2]
    chars = list(set(chars))
    for block in url_enc:
        blist = list(block)
        blist.insert(random.randint(1, len(blist) - 1), random.choice(chars))
        blist.insert(random.randint(1, len(blist) - 1), random.choice(chars))
        b += [''.join(blist)]
    _code += "[re.sub('[%s\s%s]+', '', x[::-1]) for x in [\n" % (char, char2)
    _code += '\t%s]],\n' % repr(b).replace('[', '').replace(']', '')
# break here to test value is correctly reconstructed into urls
pass

# break here, copy value of variable _code, paste into code below to test, restart,
# check values, then copy to provider.

_url_home = ['https://%s/' % base64.b64decode(x) for x in [''.join(x) for x in [
    # Insert value of var CODE here

]]]

# break here to test value is correctly reconstructed into urls
pass

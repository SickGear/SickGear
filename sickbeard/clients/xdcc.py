import socket
import os
import thread
import time
import random
import re
import sqlite3
from datetime import datetime
from collections import deque

DEBUG = 0

SERVERS = [
    {
        'network': 'scenep2p', 'host': 'irc.scenep2p.net', 'port': 6667,
        'channels': ['#THE.SOURCE']
    },
    {
        'network': 'abjects', 'host': 'irc.abjects.net', 'port': 6667,
        'channels': ['#beast-xdcc', '#beast-chat', '#moviegods', '#mg-chat']
    },
]


QUEUE = deque()

NICK = "habi%i" % random.randint(1, 500)


def load_queue():
    f = open('queue.txt', 'r')
    while 1:
        l = f.readline().strip()
        if l == '':
            break
        (network, nick, number, filename) = l.split("\t")[:4]
        QUEUE.append({'network': network, 'nick': nick, 'number': long(number), 'filename': filename, 'status': 'new'})
    f.close()


class Xdcc:
    def __init__(self, config, observers):
        self.network = config['network']
        self.host = config['host']
        self.port = config['port']
        self.channels = config['channels']
        self.sf = None
        self.observers = observers

    def start(self):
        thread.start_new_thread(self.run, ())

    def log(self, message):
        print "%s\t%s\t%s" % (datetime.now(), self.network, message)

    def failed(self, qe):
        self.append('failed.txt', qe)

    def done(self, qe):
        qe['status'] = 'done'
        self.append('done.txt', qe)
        QUEUE.remove(qe)
        store_queue()

    def append(self, filename, qe):
        f = open(filename, 'a')
        f.write("%s\t%s" % (datetime.now(), entry_to_line(qe)))
        f.close()

    def store_queue(self):
        write_collection(QUEUE, 'queue.txt', 'w')

    def send(self, msg):
        if DEBUG == 1:
            self.log("SEND: %s" % msg)
        self.sf.write(msg)
        self.sf.write('\r\n')
        self.sf.flush()

    def download(self, qe, filename, addr_number, port, size):
        qe['status'] = 'downloading'
        store_queue()
        self.log("Downloading %s which is %i Bytes in size" % (filename, long(size)))
        ip_address = '%i.%i.%i.%i' % (addr_number / 2 ** 24, addr_number % 2 ** 24 / 2 ** 16, addr_number % 2 ** 16 / 256, addr_number % 256)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip_address, port))
        source = s.makefile()
        destination = open(filename, 'ab')
        bufsize = 2**20
        start = None
        total_start = datetime.now()
        bandwidth = '?'
        while 1:
            position = os.path.getsize(filename)
            if position >= size:
                break
            if start is not None:
                now = datetime.now()
                elapsed = now - start
                bandwidth = "%.1f" % (bufsize / elapsed.total_seconds() / 1000)
            total_elapsed = datetime.now() - total_start
            average_bandwidth = "%.1f" % (position / total_elapsed.total_seconds() / 1000)
            self.log("%s - %i / %i (%i%%) at %s KB/s (avg %s KB/s)" % (filename, position, size, position * 100 / size, bandwidth, average_bandwidth))
            try:
                start = datetime.now()
                data = source.read(min(size - position, bufsize))
            except socket.error as e:
                self.log('Error downloading.')
                break
            if len(data) == 0:
                break
            destination.write(data)
            destination.flush()
        self.log("Download of %s finished" % qe['filename'])
        source.close()
        s.close()
        destination.close()
        actual_file_size = os.path.getsize(filename)
        if actual_file_size < size:
            self.fail_with_status(qe, 'file_too_short')
        else:
            self.done(qe)

    def run(self):
        self.sf = self.connect()
        self.send_user_info()

        ip_address = 0
        size = 0
        active = 0
        joining = 0

        while 1:
            qe = None
            for item in QUEUE:
                if item['network'] == self.network:
                    qe = item
                    break
            if active and qe is not None:
                if qe['status'] == 'new' or (qe['status'] == 'requested' and qe['time'] + 5*60 < time.time()):
                    self.send_request(qe)
            line = self.sf.readline().strip()
            if line == '':
                continue
            if DEBUG == 1:
                self.log("RECV: %s" % line)
            (source, rest) = line.split(' ', 1)
            if source == 'ERROR':
                self.log('RECEIVED ERROR. Exiting!')
                break
            if source == 'PING':
                self.send('PONG %s' % rest)
                continue
            if (source == ":%s" % NICK or rest.find('MODE %s' % NICK) >= 0) and joining == 0:
                self.join_channels()
                joining = 1
                continue
            if rest.find('366') == 0:  # end of names list
                active = 1
            m = re.match(':(.+)!.+@.+', source)
            if m is not None:
                nick = m.group(1)
                (action, trail) = rest.split(' ', 1)
                if action == 'PRIVMSG':
                    (target, data) = trail.split(' ', 1)
                    if target in self.channels:
                        for observer in self.observers:
                            observer.channel_message(self.network, target, nick, data)
                        continue
            if qe is None:
                continue
            if rest.find('401 %s %s' % (NICK, qe['nick'])) == 0:
                self.fail_with_offline(qe)
                continue
            if source.find(':%s!' % qe['nick']) == 0:
                (message, nick, rest) = rest.split(' ', 2)
                if message == 'NOTICE' and nick == NICK:
                    self.log("Received notice from %s: %s" % (qe['nick'], rest))
                    if rest.find('Invalid Pack Number') >= 0:
                        self.fail_with_invalid(qe)
                        continue
                    if rest.find('You already requested that pack') >= 0:
                        self.requested(qe)
                    if rest.find('All Slots Full') >= 0:
                        if rest.find('Added you to the main queue') >= 0 or rest.find('You already have that item queued') >= 0:
                            self.queued(qe)
                    continue
                if message == 'PRIVMSG' and nick == NICK:
                    self.log("RECV: %s" % line)
                    if rest.find("\1DCC SEND") >= 0:
                        dcc_params, filename, ip_address, port, size = self.parse_dcc_send_message(rest)
                        if port == 0 and len(dcc_params) == 7:
                            self.fail_with_reverse_dcc(filename, qe)
                            continue
                        if filename != qe['filename']:
                            self.fail_with_wrong_file_name(filename, qe)
                            continue
                        if os.path.isfile(filename) and os.path.getsize(filename) > 0:
                            filesize = os.path.getsize(filename)
                            if filesize >= size:
                                self.abort_resend_and_move_to_done(filename, qe)
                            else:
                                self.send_resume(filename, filesize, port, qe)
                        else:
                            thread.start_new_thread(self.download, (qe, filename, ip_address, port, size))
                        continue
                    if rest.find('DCC ACCEPT') > 0:
                        self.start_dcc_download(ip_address, qe, rest, size)
                        continue

    def parse_dcc_send_message(self, message):
        (lead, dcc_info, trail) = message.split("\1")
        dcc_params = dcc_info.split(' ')
        filename = dcc_params[2]
        ip_address = long(dcc_params[3])
        port = long(dcc_params[4])
        size = long(dcc_params[5])
        return dcc_params, filename, ip_address, port, size

    def start_dcc_download(self, ip_address, qe, rest, size):
        (lead, dccinfo, trail) = rest.split("\1")
        (dcc, accept, filename, port, position) = dccinfo.split(' ')
        thread.start_new_thread(self.download, (qe, filename, ip_address, long(port), size))

    def send_resume(self, filename, filesize, port, qe):
        self.log("Resuming %s which is %i Bytes in size" % (filename, filesize))
        self.send("PRIVMSG %s :\1DCC RESUME %s %i %i\1" % (qe['nick'], filename, port, filesize))

    def abort_resend_and_move_to_done(self, filename, qe):
        self.log("Aborting resend of done %s" % filename)
        self.done(qe)
        self.send("NOTICE %s :\1DCC REJECT SEND %s\1" % (qe['nick'], filename))
        self.send("PRIVMSG %s :XDCC CANCEL" % qe['nick'])

    def fail_with_wrong_file_name(self, filename, qe):
        self.log("Failed download from %s. Expected file %s but received %s" % (qe['nick'], qe['filename'], filename))
        self.fail_with_status(qe, 'wrong_filename')
        self.send("NOTICE %s :\1DCC REJECT SEND %s\1" % (qe['nick'], filename))
        self.send("PRIVMSG %s :XDCC CANCEL" % qe['nick'])

    def fail_with_reverse_dcc(self, filename, qe):
        self.log("Failed download from %s for %s. Revere DCC not supported." % (qe['nick'], filename))
        self.fail_with_status(qe, 'reverse_dcc_required')
        self.send("NOTICE %s :\1DCC REJECT SEND %s\1" % (qe['nick'], filename))
        self.send("PRIVMSG %s :XDCC CANCEL" % qe['nick'])

    def fail_with_invalid(self, qe):
        self.log("Failed download from %s for %s. Invalid packet number." % (qe['nick'], qe['filename']))
        self.fail_with_status(qe, 'invalid')

    def fail_with_status(self, qe, status):
        qe['status'] = status
        QUEUE.remove(qe)
        self.failed(qe)
        store_queue()

    def fail_with_offline(self, qe):
        self.log("Failed download from %s for %s. Bot offline." % (qe['nick'], qe['filename']))
        self.fail_with_status(qe, 'offline')

    def join_channels(self):
        for channel in self.channels:
            self.log("Joining %s" % channel)
            self.send('JOIN %s' % channel)

    def send_request(self, qe):
        self.log("Requesting packet %i (%s) from %s" % (qe['number'], qe['filename'], qe['nick']))
        self.send("PRIVMSG %s :xdcc send #%i" % (qe['nick'], qe['number']))
        self.requested(qe)

    def requested(self, qe):
        qe['status'] = 'requested'
        qe['time'] = time.time()
        store_queue()

    def queued(self, qe):
        self.log("Request of %s has been queued by %s" % (qe['filename'], qe['nick']))
        qe['status'] = 'queued'
        qe['time'] = time.time()
        store_queue()

    def connect(self):
        self.log("Connecting to %s ..." % self.host)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.host, self.port))
        return s.makefile()

    def send_user_info(self):
        self.send('NICK %s' % NICK)
        self.send('USER %s 0 * :%s' % (NICK, NICK))


class OfferObserver:
    def __init__(self):
        self.connection = sqlite3.connect('xdcc.db', check_same_thread=False, isolation_level=None)
        self.create_tables()
        self.offers = {}

    def create_tables(self):
        self.connection.execute('''create table if not exists offers (
                                   network text, channel text, nick text, 
                                   number integer, name text, size text, gets integer, date datetime,
                                   primary key(network, nick, number))''')

    # ^B**^B <count> packs ^B**^B  <open_slots> of <slots> slots open, Min: <min_bw>, Record: <record_bw>
    # ^B**^B Bandwidth Usage ^B**^B Current: <current_bw>, Record: <record_bw>
    # ^B**^B To request a file, type "/MSG <nick> XDCC SEND x" ^B**^B
    # ^B#<number>  ^B   <gets>x [ <size>] ^B<filename>^O
    # Total Offered: <size>  Total Transferred: <size>
    def channel_message(self, network, channel, nick, message):
        # ^B#<number>  ^B   <gets>x [ <size>] ^B<filename>^O
        m = re.match('.*?#(\d+).*? +(\d+)x \[ *(.*?)] (.*)', message)
        if m is not None:
            number = m.group(1)
            gets = m.group(2)
            size = m.group(3)
            filename = m.group(4)
            return self.offer(network, nick, number, filename, gets, size)
        # ^B**^B <count> packs ^B**^B  <open_slots> of <slots> slots open, Min: <min_bw>, Record: <record_bw>
        m = re.match('.*?(\d+) packs .*? +(\d+) of (\d+) slots open', message)
        if m is not None:
            count = m.group(1)
            open_slots = m.group(2)
            slots = m.group(3)
            return self.start_offer(network, channel, nick, count, open_slots, slots)
        # ^B**^B Bandwidth Usage ^B**^B Current: <current_bw>, Record: <record_bw>
        m = re.match('.*?Bandwidth Usage.+?Current: (.+), Record: (.+)', message)
        if m is not None:
            current_bw = m.group(1)
            record_bw = m.group(2)
            return self.bw_offer(network, nick, current_bw, record_bw)
        # Total Offered: <size>  Total Transferred: <size>
        m = re.match('.*?Total Offered: +(.+) +Total Transferred: +(.+)', message)
        if m is not None:
            offer_size = m.group(1)
            transfer_size = m.group(2)
            return self.finish_offer(network, nick, offer_size, transfer_size)

    def start_offer(self, network, channel, nick, count, open_slots, slots):
        self.log(network, "Collecting %s offers for %s in %s" % (count, nick, channel))
        self.offers[network, nick] = {'network': network, 'channel': channel, 'nick': nick, 'count': count,
                                      'slots': slots, 'open_slots': open_slots, 'packs': {}}

    def bw_offer(self, network, nick, current_bw, record_bw):
        if (network, nick) not in self.offers:
            return
        offer = self.offers[network, nick]
        offer['current_bw'] = current_bw
        offer['record_bw'] = record_bw

    def finish_offer(self, network, nick, size, transferred):
        if (network, nick) not in self.offers:
            return
        offer = self.offers[network, nick]
        offer['size'] = size
        offer['transferred'] = transferred
        self.write_offer(offer)
        del self.offers[network, nick]

    def write_offer(self, offer):
        self.log(offer['network'], "Writing %s packs for %s in %s" % (offer['count'], offer['nick'], offer['channel']))
        inserts = []
        for key in offer['packs']:
            pack = offer['packs'][key]
            inserts.append((offer['network'], offer['channel'], offer['nick'],
                            pack['number'], pack['filename'], pack['size'], pack['gets'], datetime.now()))
        try:
            self.connection.execute('delete from offers where network=? and nick=?', (offer['network'], offer['nick']))
            self.connection.executemany('replace into offers values(?,?,?,?,?,?,?,?)', inserts)
        except sqlite3.DatabaseError as e:
            self.log(offer['network'], "Error while trying to write packs for %s: %s" % (offer['nick'], e.message))

    def offer(self, network, nick, number, filename, gets, size):
        if (network, nick) not in self.offers:
            return
        filename = self.strip_format_codes(filename)
        offer = self.offers[network, nick]
        offer['packs'][number] = {'number': number, 'filename': filename, 'size': size, 'gets': gets}

    def strip_format_codes(self, str):
        regex = re.compile("\x1f|\x02|\x12|\x0f|\x16|\x03(?:\d{1,2}(?:,\d{1,2})?)?", re.UNICODE)
        return regex.sub("", str)

    def log(self, network, message):
        print "%s\t%s\t%s" % (datetime.now(), network, message)


def xdcc(servers):
    offer_observer = OfferObserver()
    load_queue()
    for server in servers:
        Xdcc(server, [offer_observer]).start()
    while 1:
        time.sleep(5)
        add()


def add():
    files = [f for f in os.listdir('add') if os.path.isfile(os.path.join('add', f))]
    for file in files:
        p = os.path.join('add', file)
        f = open(p, 'r')
        while 1:
            l = f.readline().strip()
            if l == '':
                break
            (network, nick, number, filename) = l.split("\t")[:4]
            QUEUE.append({'network': network, 'nick': nick, 'number': long(number), 'filename': filename, 'status': 'new'})
            store_queue()
        f.close()
        os.remove(p)


def store_queue():
    write_collection(QUEUE, 'queue.txt', 'w')


def entry_to_line(qe):
    return "%s\t%s\t%i\t%s\t%s\n" % (qe['network'], qe['nick'], qe['number'], qe['filename'], qe['status'])


def write_collection(queue, filename, mode):
    f = open(filename, mode)
    for qe in queue:
        f.write(entry_to_line(qe))
    f.close()


xdcc(SERVERS)

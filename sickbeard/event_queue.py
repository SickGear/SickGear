from lib.six import moves

import threading


class Event(object):
    def __init__(self, etype):
        self._type = etype

    @property
    def type(self):
        return self._type


class Events(threading.Thread):
    def __init__(self, callback):
        super(Events, self).__init__()
        self.queue = moves.queue.Queue()
        self.daemon = True
        self.callback = callback
        self.name = 'EVENT-QUEUE'
        self._stopper = threading.Event()

    def put(self, etype):
        self.queue.put(etype)

    def stopit(self):
        self._stopper.set()

    def run(self):
        while not self._stopper.is_set():
            try:
                # get event type
                etype = self.queue.get(True, 1)

                # perform callback if we got a event type
                self.callback(etype)

                # event completed
                self.queue.task_done()
            except moves.queue.Empty:
                pass

        # exiting thread
        self._stopper.clear()

    # System Events
    class SystemEvent(Event):
        RESTART = 'RESTART'
        SHUTDOWN = 'SHUTDOWN'

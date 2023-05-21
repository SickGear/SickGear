import queue
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
        self.queue = queue.Queue()
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
                ev_type = self.queue.get(True, 1)
            except queue.Empty:
                ev_type = 'Empty'
            except(BaseException, Exception):
                ev_type = None
            if ev_type in (self.SystemEvent.RESTART, self.SystemEvent.SHUTDOWN, None, 'Empty'):
                if ev_type in ('Empty',):
                    continue
                from sickgear import logger
                logger.debug(f'Callback {self.callback.__name__}(event type:{ev_type})')

            try:
                # perform callback if we got an event type
                self.callback(ev_type)

                # event completed
                self.queue.task_done()
            except queue.Empty:
                pass

        # exiting thread
        self._stopper.clear()

    # System Events
    class SystemEvent(Event):
        RESTART = 'RESTART'
        SHUTDOWN = 'SHUTDOWN'

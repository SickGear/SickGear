from lib.six import moves

import threading


class Event:
    def __init__(self, event_type):
        self._type = event_type

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
        self.stop = threading.Event()

    def put(self, event_type):
        self.queue.put(event_type)

    def run(self):
        event_type = None
        while not self.stop.is_set():
            try:
                # get event type
                if not event_type:
                    event_type = self.queue.get(True, 1)

                # perform callback if we got a event type
                self.callback(event_type)

                # event completed
                self.queue.task_done()

            except moves.queue.Empty:
                pass

        # exiting thread
        self.stop.clear()

    # System Events
    class SystemEvent(Event):
        RESTART = 'RESTART'
        SHUTDOWN = 'SHUTDOWN'

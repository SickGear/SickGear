from time import time

DATARATE_UPDATE = 1.0   # Time slice (in second) for datarate computation


class DataRate:
    """
    Compute average speed in bits per second of a function.
    Store self.size data rates to compute good average speed.
    Don't compute average before self.min_size values are computed.
    """

    def __init__(self, offset, size=20, min_size=3):
        self.last_offset = offset
        self.last_time = time()
        self.datarates = []
        # Average bit rate
        self.average = None
        # Number of stored value used to compute average data rate
        self.size = size
        self.min_size = min_size

    def update(self, offset):
        # Compute time delta
        difftime = time() - self.last_time
        if difftime < DATARATE_UPDATE:
            # Only update each second
            return
        self.last_time = time()

        # Compute data rate
        rate = float(offset - self.last_offset) / difftime
        self.last_offset = offset

        # Update statistics
        self.datarates.append(rate)
        self.datarates = self.datarates[-self.size:]
        if self.min_size <= len(self.datarates):
            self.average = sum(self.datarates) / len(self.datarates)

from ..common import NotifyType as NotifyType
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

NOTIFY_BLINK1_ENABLED: bool
BLINK1_VENDOR_ID: int
BLINK1_PRODUCT_ID: int
BLINK1_REPORT_ID: int
BLINK1_REPORT_SIZE: int
BLINK1_CMD_FADE: Incomplete

class Blink1LED:
    """
    Defines the LED to focus on
    """
    ALL: int
    FIRST: int
    SECOND: int

BLINK1_LED_CHOICES: Incomplete
BLINK1_LED_MAP: Incomplete
BLINK1_DEFAULT_DURATION_MS: int
BLINK1_MIN_DURATION_MS: int
BLINK1_MAX_DURATION_MS: int
BLINK1_DEFAULT_FADE_MS: int
BLINK1_MIN_FADE_MS: int
BLINK1_MAX_FADE_MS: int

def _blink1_fade_buf(red, green, blue, fade_ms, ledn):
    """Build the 9-byte HID feature-report buffer for a fade-to-RGB command.

    The blink(1) wire format (all values unsigned 8-bit unless noted):
      [0] REPORT_ID (0x01)
      [1] command 'c' (0x63)
      [2] red
      [3] green
      [4] blue
      [5] fade_time high byte  (fade_time = fade_ms // 10, 16-bit big-endian)
      [6] fade_time low byte
      [7] ledn (0=all, 1=LED1, 2=LED2)
      [8] 0x00 (padding)
    """

class NotifyBlink1(NotifyBase):
    """A wrapper for blink(1) USB LED notifications.

    Colors are driven by Apprise's notification-type color map
    (info=blue, success=green, warning=yellow, failure=red).
    No external blink1 library is required; the USB HID wire protocol
    is implemented directly via the hidapi package.
    """
    enabled = NOTIFY_BLINK1_ENABLED
    requirements: Incomplete
    service_name: Incomplete
    service_url: str
    protocol: str
    setup_url: str
    title_maxlen: int
    request_rate_per_sec: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    serial: Incomplete
    duration: Incomplete
    fade: Incomplete
    ledn: Incomplete
    def __init__(self, serial=None, duration=None, fade=None, ledn=None, **kwargs) -> None:
        """Initialize Blink1 Object."""
    def _open_device(self):
        """Open and return a hidapi device handle for the blink(1).

        Returns None and logs a warning when the device cannot be found.
        """
    def _send_fade(self, dev, red, green, blue, fade_ms):
        """Send a single fade-to-RGB HID feature report.

        Returns True on success, False if the report could not be sent.
        """
    @property
    def url_identifier(self):
        """Returns all fields that uniquely identify this connection."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform blink(1) Notification."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments to re-instantiate."""
    @staticmethod
    def runtime_deps():
        """Return optional runtime dependency package names."""

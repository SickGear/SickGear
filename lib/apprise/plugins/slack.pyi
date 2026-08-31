from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..conversion import build_backtick_run_index as build_backtick_run_index, commonmark_emphasis_run as commonmark_emphasis_run, commonmark_escape_link_url as commonmark_escape_link_url, commonmark_force_close_spans as commonmark_force_close_spans, commonmark_scan_angle_dest as commonmark_scan_angle_dest, find_unescaped_run as find_unescaped_run
from ..utils.parse import is_email as is_email, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from collections.abc import Generator

SLACK_HTTP_ERROR_MAP: Incomplete
CHANNEL_LIST_DELIM: Incomplete
CHANNEL_RE: Incomplete

class SlackMode:
    """Tracks the mode of which we're using Slack."""
    WEBHOOK: str
    WEBHOOK_GOV: str
    BOT: str
    WORKFLOW: str
    WORKFLOW_TRIGGER: str

SLACK_MODES: Incomplete

class NotifySlack(NotifyBase):
    """A wrapper for Slack Notifications."""
    service_name: str
    service_url: str
    secure_protocol: str
    request_rate_per_sec: float
    setup_url: str
    attachment_support: bool
    webhook_url: str
    webhook_gov_url: str
    workflow_url: str
    workflow_trigger_url: str
    api_url: str
    image_size: Incomplete
    body_maxlen: int
    max_slack_template_size: int
    notify_format: Incomplete
    default_notification_channel: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    _re_formatting_map: Incomplete
    _re_channel_support: Incomplete
    _re_user_id_support: Incomplete
    _re_url_support: Incomplete
    @classmethod
    def _commonmark_to_slack(cls, body):
        """Translate CommonMark to Slack ``mrkdwn``.

        CommonMark          Slack mrkdwn
        ------------------  -----------------
        **bold**            *bold*
        *italic*            _italic_
        `code`              `code`
        [label](<url>)      <url|label>
        &, <, >             HTML entities

        Slack retains supported backslash escapes and uses its native anchor
        syntax for labeled links.
        """
    mode: Incomplete
    access_token: Incomplete
    token_a: Incomplete
    token_b: Incomplete
    token_c: Incomplete
    workflow_path: Incomplete
    _lookup_users: Incomplete
    use_blocks: Incomplete
    channels: Incomplete
    _re_formatting_rules: Incomplete
    include_image: Incomplete
    include_footer: Incomplete
    include_timestamp: Incomplete
    template: Incomplete
    tokens: Incomplete
    def __init__(self, access_token=None, token_a=None, token_b=None, token_c=None, targets=None, include_image=None, include_footer=None, include_timestamp=None, use_blocks=None, mode=None, template=None, tokens=None, workflow_path=None, **kwargs) -> None:
        """Initialize Slack Object."""
    def gen_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """Return a validated Block Kit attachment, or ``False``."""
    def _build_send_calls(self, body=None, title=None, body_format=None, **kwargs) -> Generator[Incomplete, Incomplete]:
        """Split HTML-derived CommonMark before Slack conversion.

        Markdown-aware splitting protects links; ``send()`` then converts each
        chunk to independently valid ``mrkdwn``.
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, body_format=None, **kwargs):
        """Perform Slack Notification."""
    def lookup_userid(self, email):
        """Takes an email address and attempts to resolve/acquire it's user id
        for notification purposes."""
    def _send(self, url, payload, attach=None, http_method: str = 'post', params=None, **kwargs):
        """Wrapper to the requests (post) object."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """
        Supports:
          - https://hooks.slack.com/services/TOKEN_A/TOKEN_B/TOKEN_C
          - https://hooks.slack-gov.com/services/TOKEN_A/TOKEN_B/TOKEN_C
          - https://hooks.slack.com/workflows/T.../F.../X.../Y...
          - https://hooks.slack.com/triggers/T.../X.../Y...
        """

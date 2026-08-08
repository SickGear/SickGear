from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import is_email as is_email, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

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
        """Generate our payload from an external Block Kit JSON template.

        Returns the validated attachment content dict (which must contain
        a non-empty 'blocks' list with typed entries) to be placed into
        the Slack attachments array.  Returns False on any failure.
        """
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
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

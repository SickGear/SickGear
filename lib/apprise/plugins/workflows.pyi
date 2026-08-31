from ..apprise_attachment import AppriseAttachment as AppriseAttachment
from ..common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from ..utils.templates import TemplateType as TemplateType, apply_template as apply_template
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

class APIVersion:
    """
    Define API Versions
    """
    WORKFLOW: str
    POWER_AUTOMATE: str

WORKFLOWS_MENTION_RE: Incomplete

class NotifyWorkflows(NotifyBase):
    """A wrapper for Microsoft Workflows (MS Teams) Notifications."""
    service_name: str
    service_url: str
    secure_protocol: Incomplete
    setup_url: str
    image_size: Incomplete
    body_maxlen: int
    notify_format: Incomplete
    max_workflows_template_size: int
    adaptive_card_version: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    template_kwargs: Incomplete
    workflow: Incomplete
    signature: Incomplete
    include_image: Incomplete
    power_automate: Incomplete
    routing_id: Incomplete
    wrap: Incomplete
    template: Incomplete
    api_version: Incomplete
    tokens: Incomplete
    def __init__(self, workflow, signature, include_image=None, power_automate=None, routing_id=None, version=None, template=None, tokens=None, wrap=None, **kwargs) -> None:
        """Initialize Microsoft Workflows Object."""
    def gen_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """This function generates our payload whether it be the generic one
        Apprise generates by default, or one provided by a specified external
        template."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Microsoft Teams Notification."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """
        Support parsing the webhook straight out of workflows
            https://HOST:443/workflows/WORKFLOWID/triggers/manual/paths/invoke
            or
            https://HOST:443/powerautomate/automations/direct/workflows
            /WORKFLOWID/triggers/manual/paths/invoke
        """

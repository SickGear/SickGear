from ..common import NotifyFormat as NotifyFormat, NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_email as is_email, parse_emails as parse_emails, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_REGION: Incomplete
AWS_HTTP_ERROR_MAP: Incomplete

class NotifySES(NotifyBase):
    """A wrapper for AWS SES (Amazon Simple Email Service)"""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    attachment_support: bool
    request_rate_per_sec: float
    notify_format: Incomplete
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    aws_session_token: Incomplete
    aws_access_key_id: Incomplete
    aws_secret_access_key: Incomplete
    aws_region_name: Incomplete
    targets: Incomplete
    cc: Incomplete
    bcc: Incomplete
    names: Incomplete
    notify_url: Incomplete
    aws_service_name: str
    aws_canonical_uri: str
    aws_auth_version: str
    aws_auth_algorithm: str
    aws_auth_request: str
    from_name: Incomplete
    from_addr: Incomplete
    reply_to: Incomplete
    def __init__(self, access_key_id, secret_access_key, region_name, reply_to=None, from_addr=None, from_name=None, targets=None, cc=None, bcc=None, session_token=None, **kwargs) -> None:
        """Initialize Notify AWS SES Object."""
    def send(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Wrapper to send_notification since we can alert more then one
        channel."""
    def _post(self, payload, to):
        """Wrapper to request.post() to manage it's response better and make
        the send() function cleaner and easier to maintain.

        This function returns True if the _post was successful and False if it
        wasn't.
        """
    def aws_prepare_request(self, payload, reference=None):
        """Takes the intended payload and returns the headers for it.

        The payload is presumed to have been already urlencoded()
        """
    def aws_auth_signature(self, to_sign, reference):
        """Generates a AWS v4 signature based on provided payload which should
        be in the form of a string."""
    @staticmethod
    def aws_response_to_dict(aws_response):
        '''Takes an AWS Response object as input and returns it as a dictionary
        but not befor extracting out what is useful to us first.

        eg:
          IN:

            <SendRawEmailResponse
                 xmlns="http://ses.amazonaws.com/doc/2010-12-01/">
              <SendRawEmailResult>
                <MessageId>
                   010f017d87656ee2-a2ea291f-79ea-
                   44f3-9d25-00d041de3007-000000</MessageId>
              </SendRawEmailResult>
              <ResponseMetadata>
                <RequestId>7abb454e-904b-4e46-a23c-2f4d2fc127a6</RequestId>
              </ResponseMetadata>
            </SendRawEmailResponse>

          OUT:
           {
             \'type\': \'SendRawEmailResponse\',
              \'message_id\': \'010f017d87656ee2-a2ea291f-79ea-
                             44f3-9d25-00d041de3007-000000\',
              \'request_id\': \'7abb454e-904b-4e46-a23c-2f4d2fc127a6\',
           }
        '''
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

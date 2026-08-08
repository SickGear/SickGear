from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import is_phone_no as is_phone_no, parse_list as parse_list, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete

IS_TOPIC: Incomplete
IS_REGION: Incomplete
AWS_HTTP_ERROR_MAP: Incomplete

class SNSMode:
    """Tracks the mode of operation for SNS Notifications."""
    SMS: str
    TOPIC: str

SNS_MODES: Incomplete

class NotifySNS(NotifyBase):
    """A wrapper for AWS SNS (Amazon Simple Notification)"""
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    request_rate_per_sec: float
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    aws_session_token: Incomplete
    aws_access_key_id: Incomplete
    aws_secret_access_key: Incomplete
    aws_region_name: Incomplete
    topics: Incomplete
    phone: Incomplete
    notify_url: Incomplete
    aws_service_name: str
    aws_canonical_uri: str
    aws_auth_version: str
    aws_auth_algorithm: str
    aws_auth_request: str
    mode: Incomplete
    def __init__(self, access_key_id, secret_access_key, region_name, targets=None, session_token=None, mode=None, **kwargs) -> None:
        """Initialize Notify AWS SNS Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
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
            <CreateTopicResponse
                  xmlns="http://sns.amazonaws.com/doc/2010-03-31/">
              <CreateTopicResult>
                <TopicArn>arn:aws:sns:us-east-1:000000000000:abcd</TopicArn>
                   </CreateTopicResult>
               <ResponseMetadata>
               <RequestId>604bef0f-369c-50c5-a7a4-bbd474c83d6a</RequestId>
               </ResponseMetadata>
           </CreateTopicResponse>

          OUT:
           {
              type: \'CreateTopicResponse\',
              request_id: \'604bef0f-369c-50c5-a7a4-bbd474c83d6a\',
              topic_arn: \'arn:aws:sns:us-east-1:000000000000:abcd\',
           }
        '''
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    @property
    def title_maxlen(self):
        """Maximum title length: 100 for topic mode, 0 for SMS."""
    @property
    def body_maxlen(self):
        """Maximum body length: 256 KB for topic mode, 160 for SMS."""
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us to re-
        instantiate this object."""

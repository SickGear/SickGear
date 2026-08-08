from ...common import NotifyFormat as NotifyFormat, NotifyImageSize as NotifyImageSize, NotifyType as NotifyType, PersistentStoreMode as PersistentStoreMode
from ...exception import AppriseException as AppriseException
from ...url import PrivacyMode as PrivacyMode
from ...utils.parse import is_hostname as is_hostname, parse_bool as parse_bool, parse_list as parse_list, validate_regex as validate_regex
from ..base import NotifyBase as NotifyBase
from .e2ee import MATRIX_E2EE_SUPPORT as MATRIX_E2EE_SUPPORT, MatrixMegOlmSession as MatrixMegOlmSession, MatrixOlmAccount as MatrixOlmAccount, encrypt_attachment as encrypt_attachment, verify_device_keys as verify_device_keys, verify_signed_otk as verify_signed_otk
from _typeshed import Incomplete

MATRIX_V1_WEBHOOK_PATH: str
MATRIX_V2_API_PATH: str
MATRIX_V3_API_PATH: str
MATRIX_V3_MEDIA_PATH: str
MATRIX_V2_MEDIA_PATH: str

class MatrixDiscoveryException(AppriseException):
    """Apprise Matrix Exception Class."""

MATRIX_HTTP_ERROR_MAP: Incomplete
IS_ROOM_ALIAS: Incomplete
IS_ROOM_ID: Incomplete
IS_USER: Incomplete
IS_IMAGE: Incomplete

class MatrixMessageType:
    """The Matrix Message types."""
    TEXT: str
    NOTICE: str

MATRIX_MESSAGE_TYPES: Incomplete

class MatrixVersion:
    V2: str
    V3: str

MATRIX_VERSIONS: Incomplete

class MatrixWebhookMode:
    DISABLED: str
    MATRIX: str
    SLACK: str
    T2BOT: str
    HOOKSHOT: str

MATRIX_WEBHOOK_MODES: Incomplete

class NotifyMatrix(NotifyBase):
    """A wrapper for Matrix Notifications."""
    service_name: str
    service_url: str
    protocol: str
    secure_protocol: str
    attachment_support: bool
    setup_url: str
    image_size: Incomplete
    body_maxlen: int
    request_rate_per_sec: float
    default_retries: int
    default_wait_ms: int
    storage_mode: Incomplete
    default_cache_expiry_sec: Incomplete
    default_e2ee_otk_count: int
    default_e2ee_otk_replenish_threshold: int
    discovery_base_key: str
    discovery_identity_key: str
    discovery_cache_length_sec: int
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    rooms: Incomplete
    users: Incomplete
    home_server: Incomplete
    user_id: Incomplete
    access_token: Incomplete
    device_id: Incomplete
    transaction_id: int
    _e2ee_account: Incomplete
    include_image: Incomplete
    discovery: Incomplete
    hsreq: Incomplete
    webhook_path: Incomplete
    e2ee: Incomplete
    mode: Incomplete
    version: Incomplete
    msgtype: Incomplete
    def __init__(self, targets=None, mode=None, msgtype=None, version=None, include_image=None, discovery=None, hsreq=None, webhook_path=None, e2ee=None, **kwargs) -> None:
        """Initialize Matrix Object."""
    def send(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Matrix Notification."""
    def _send_webhook_notification(self, body, title: str = '', notify_type=..., **kwargs):
        """Perform Matrix Notification as a webhook."""
    _re_slack_formatting_map: Incomplete
    _re_slack_formatting_rules: Incomplete
    def _slack_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """Format the payload for a Slack based message."""
    def _matrix_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """Format the payload for a Matrix based message."""
    def _t2bot_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """Format the payload for a T2Bot Matrix based messages."""
    def _hookshot_webhook_payload(self, body, title: str = '', notify_type=..., **kwargs):
        """Format the payload for a matrix-hookshot webhook."""
    def _send_server_notification(self, body, title: str = '', notify_type=..., attach=None, **kwargs):
        """Perform Direct Matrix Server Notification (no webhook)"""
    def _send_attachments(self, attach):
        """Posts all of the provided attachments."""
    def _register(self):
        """Register with the service if possible."""
    def _login(self):
        """Acquires the matrix token required for making future requests.

        If we fail we return False, otherwise we return True
        """
    def _whoami(self):
        """Resolve user_id, device_id, and home_server via GET /account/whoami.

        Called when a raw access token is supplied (no login flow), so
        the server never returned these identifiers directly.  Results
        are cached in the persistent store for future calls.

        Returns True on success, False otherwise.
        """
    def _logout(self):
        """Relinquishes token from remote server."""
    def _room_join(self, room):
        """Joins a matrix room if we're not already in it.

        Otherwise it attempts to create it if it doesn't exist and
        always returns the room_id if it was successful, otherwise it
        returns None
        """
    def _room_create(self, room):
        """Creates a matrix room and return it's room_id if successful
        otherwise None is returned."""
    def _joined_rooms(self):
        """Returns a list of the current rooms the logged in user is a
        part of."""
    def _room_id(self, room):
        """Get room id from its alias.
        Args:
            room (str): The room alias name.

        Returns:
            returns the room id if it can, otherwise it returns None
        """
    def _fetch(self, path, payload=None, params=None, attachment=None, method: str = 'POST', url_override=None, ok_status=None):
        '''Wrapper to request.post() to manage it\'s response better and
        make the send() function cleaner and easier to maintain.

        This function always returns a 3-tuple:
            (success, response, status_code)

        The response is a dict when JSON is parseable, otherwise an empty
        dict. The status_code defaults to 500 on local failures.

        *ok_status* is an optional collection of additional HTTP status codes
        to treat as success (no warning logged).  Use it for calls where a
        non-200 response is expected and meaningful, e.g. 404 on a state-event
        probe that returns "not found" = "feature not enabled".
        '''
    def _e2ee_room_encrypted(self, room_id):
        """Return ``True`` if *room_id* has E2EE enabled on the server.

        The result is cached in the persistent store so subsequent sends
        to the same room do not issue additional network requests.
        """
    def _e2ee_setup(self):
        """Ensure the E2EE device account exists and keys are uploaded.

        Creates a new :class:`MatrixOlmAccount` if one does not yet
        exist in the persistent store, then calls
        :meth:`_e2ee_upload_keys` if the server has not yet received
        our device keys for the current access token.

        Returns ``True`` on success, ``False`` on failure.
        """
    def _e2ee_upload_keys(self):
        """POST device keys to ``/_matrix/client/v3/keys/upload``."""
    def _e2ee_replenish_otks(self, claimed_count: int = 0, skipped_no_otk: int = 0):
        """Top up the server-side OTK pool after a ``/keys/claim`` event.

        Parameters:
          claimed_count   -- number of OTKs successfully consumed by the
                             preceding ``/keys/claim`` (= ``built_count``
                             from :meth:`_e2ee_share_room_key`)
          skipped_no_otk  -- devices that were skipped because the server
                             returned no OTK for them (pool already dry)

        A replenishment upload is issued when any of the following is true:

        - ``skipped_no_otk > 0``: the pool was already depleted during
          the current claim -- top up immediately so the next key share
          can reach those devices.
        - estimated remaining OTKs after claim <
          ``default_e2ee_otk_replenish_threshold``: pool is running low.
        - server count was never recorded (unknown state): replenish as a
          precaution.

        Only ``one_time_keys`` is uploaded so the server does not treat
        this as a device re-registration.

        Returns ``True`` on success (or when no top-up was needed),
        ``False`` on network failure (non-fatal -- the preceding send
        already succeeded).
        """
    def _e2ee_get_megolm(self, room_id):
        """Return the current outbound MegOLM session for *room_id*.

        Creates a new session when none exists or when the existing one
        has reached the rotation threshold.  Also clears the
        ``e2ee_key_shared_*`` flag so the new session key is re-shared.
        """
    def _e2ee_save_megolm(self, room_id, session) -> None:
        """Persist the updated MegOLM session state."""
    def _e2ee_room_members(self, room_id):
        '''Query device keys for all joined members of *room_id*.

        Returns a nested dict::

            {user_id: {device_id: {"curve25519": ..., "ed25519": ...}}}

        Returns ``None`` on HTTP failure, empty dict when the room has
        no members (unlikely but tolerated).
        '''
    def _e2ee_share_room_key(self, room_id, session):
        """Send the MegOLM session key to all devices in *room_id*.

        Flow:
          1. Fetch joined-member device keys via /keys/query
          2. Claim one-time keys via /keys/claim
          3. Create outbound Olm sessions and encrypt the room-key event
          4. Deliver via PUT /sendToDevice/m.room.encrypted/{txnId}

        Returns ``True`` on success (partial device failures are
        tolerated), ``False`` only when a critical step fails.
        """
    def _e2ee_send_to_room(self, room_id, body, title, notify_type):
        """Encrypt and send one message to *room_id* via MegOLM.

        Shares the MegOLM session key with room members when the
        session is new or has just been rotated.
        Returns ``True`` on success, ``False`` on failure.
        """
    def _e2ee_send_attachment(self, attachment, room_id, session):
        """Encrypt *attachment* and deliver it to *room_id* via MegOLM.

        Steps:
        1. Read the file into memory and encrypt with AES-256-CTR.
        2. Upload the ciphertext to the media server (content_uri).
        3. Build an ``m.room.message`` inner event whose ``file`` field
           carries the EncryptedFile metadata (key + iv + sha256).
        4. Encrypt the inner event with MegOLM and PUT to the room.

        Returns ``True`` on success, ``False`` on any failure.
        """
    def _dm_room_find_or_create(self, user):
        """Resolve *user* (``@localpart`` or ``@localpart:homeserver``)
        to a Matrix room ID suitable for direct messaging.

        Lookup order:
        1. Persistent-store cache.
        2. ``GET /user/{selfId}/account_data/m.direct`` -- check whether
           an existing DM room already exists for this user.
        3. ``POST /createRoom`` with ``is_direct=true`` and an invite for
           the target user.  The ``m.direct`` account-data entry is then
           updated so other clients also recognise the room as a DM.

        Returns the room ID string on success, or ``None`` on failure.
        """
    def __del__(self) -> None:
        """Ensure we relinquish our token."""
    @property
    def url_identifier(self):
        """Returns all of the identifiers that make this URL unique from
        another simliar one.

        Targets or end points should never be identified here.
        """
    @staticmethod
    def runtime_deps():
        """Return runtime dependency package names.

        E2EE support requires the `cryptography` package.
        """
    def url(self, privacy: bool = False, *args, **kwargs):
        """Returns the URL built dynamically based on specified
        arguments."""
    def __len__(self) -> int:
        """Returns the number of targets associated with this
        notification."""
    @staticmethod
    def parse_url(url):
        """Parses the URL and returns enough arguments that can allow us
        to re-instantiate this object."""
    @staticmethod
    def parse_native_url(url):
        """
        Support https://webhooks.t2bot.io/api/v1/matrix/hook/WEBHOOK_TOKEN/
        """
    def server_discovery(self):
        """
        Home Server Discovery as documented here:
           https://spec.matrix.org/v1.11/client-server-api/#well-known-uri
        """
    @property
    def base_url(self):
        """Returns the base_url if known."""
    @property
    def identity_url(self):
        """Returns the identity_url if known."""

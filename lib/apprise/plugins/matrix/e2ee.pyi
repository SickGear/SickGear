from _typeshed import Incomplete

MATRIX_E2EE_SUPPORT: bool
MEGOLM_ROTATION_MSGS: int
MEGOLM_ROTATION_AGE: Incomplete
MATRIX_MEGOLM_STORE_VERSION: int

def _b64enc(data):
    """Matrix-style unpadded base64 of *data* as ASCII."""
def _b64dec(s):
    """Decode a base64 string; tolerates missing padding and URL-safe chars."""
def _hmac_sha256(key, data):
    """32-byte HMAC-SHA-256 of *data* keyed by *key*."""
def _hkdf_sha256(ikm, length, salt, info):
    """HKDF-SHA-256.  *salt* may be ``None`` or explicit ``bytes``."""
def _aes_cbc_encrypt(key, iv, plaintext):
    """AES-256-CBC-encrypt *plaintext* with PKCS#7 padding."""
def _varint(n):
    """Encode *n* as a protobuf-style base-128 varint."""
def _pb_bytes(field_num, data):
    """Protobuf wire-type 2 (length-delimited bytes) field."""
def _pb_varint_field(field_num, value):
    """Protobuf wire-type 0 (varint) field."""
def _canonical_json(obj):
    """UTF-8 canonical JSON (sorted keys, no spaces) for signing."""
def _verify_ed25519(public_key_b64, message_bytes, signature_b64):
    """Verify an Ed25519 signature.

    Returns ``True`` when *signature_b64* is a valid signature of
    *message_bytes* under *public_key_b64*.  Returns ``False`` on any
    error (wrong key, bad signature, decode failure, etc.).

    Requires ``MATRIX_E2EE_SUPPORT`` (the ``cryptography`` package).
    """
def verify_device_keys(dev_info, user_id, device_id):
    '''Verify the Ed25519 self-signature on a /keys/query device object.

    Per the spec, the signed payload must carry ``user_id`` and
    ``device_id`` fields whose values match the identity being
    verified.  This prevents a malicious homeserver from substituting
    keys from one device into the record of another.

    Returns ``True`` only when all of the following hold:
    - ``dev_info["user_id"] == user_id``
    - ``dev_info["device_id"] == device_id``
    - The Ed25519 self-signature over the canonical payload is valid.
    '''
def verify_signed_otk(otk_obj, user_id, device_id, ed25519_pub_b64):
    """Verify the Ed25519 signature on a ``signed_curve25519`` OTK.

    The device signs the OTK object (excluding ``signatures``) with the
    same Ed25519 key published in its device keys.

    Returns ``True`` only when the signature is present and valid.
    """
def encrypt_attachment(data):
    '''Encrypt *data* bytes for upload to a Matrix E2EE room.

    Implements the Matrix attachment encryption spec (v2):
      https://spec.matrix.org/v1.11/client-server-api/#sending-encrypted-attachments

    Algorithm: AES-256-CTR.
    IV: 8 random bytes followed by 8 zero bytes (avoids counter wrap).

    Returns a ``(ciphertext, file_info)`` tuple where *file_info* is the
    ``EncryptedFile`` object to embed in the ``m.room.message`` event:

    .. code-block:: json

        {
            "v": "v2",
            "key": { "kty": "oct", "alg": "A256CTR", "k": "<key>",
                     "key_ops": ["encrypt", "decrypt"], "ext": true },
            "iv": "<base64url-nopad 16-byte IV>",
            "hashes": { "sha256": "<base64 SHA-256 of ciphertext>" }
        }
    '''

class MatrixOlmAccount:
    '''Device-level Curve25519 + Ed25519 key pair.

    Generates a new key pair on first use and persists it via
    ``to_dict()`` / ``from_dict()``.  Also creates outbound Olm sessions
    used to distribute MegOLM room keys to other devices.

    Reference: Olm spec, Section 2 ("Keys").
    '''
    _ik: Incomplete
    _sk: Incomplete
    _ik_pub: Incomplete
    _sk_pub: Incomplete
    _otks: Incomplete
    _fallback_otk: Incomplete
    def __init__(self, ik_priv_b64=None, sk_priv_b64=None, otks=None, fallback_otk=None) -> None:
        """Initialise from saved keys or generate a fresh key pair.

        Parameters are the base64-encoded raw 32-byte private key bytes
        for the Curve25519 identity key (*ik*) and Ed25519 signing key
        (*sk*).  Supply both or neither.
        """
    @property
    def identity_key(self):
        """Base64-encoded Curve25519 public identity key."""
    @property
    def signing_key(self):
        """Base64-encoded Ed25519 public signing key."""
    def sign(self, data):
        """Ed25519-sign *data* (bytes or str) and return base64."""
    def to_dict(self):
        """Export private keys for persistent storage."""
    @staticmethod
    def from_dict(data):
        """Restore from a ``to_dict()`` snapshot."""
    def device_keys_payload(self, user_id, device_id):
        """Build the signed ``device_keys`` object for ``POST /keys/upload``.

        Reference:
          https://spec.matrix.org/v1.11/client-server-api/
          #post_matrixclientv3keysupload
        """
    def _signed_curve25519_key(self, user_id, device_id, key_b64):
        """Wrap a Curve25519 key in a signed KeyObject."""
    def _ensure_otks(self, count: int = 10) -> None:
        """Ensure at least *count* signed_curve25519 one-time keys exist."""
    def one_time_keys_payload(self, user_id, device_id, count: int = 10):
        """Build signed ``one_time_keys`` for ``POST /keys/upload``."""
    def fallback_keys_payload(self, user_id, device_id):
        """Build signed ``fallback_keys`` for ``POST /keys/upload``."""
    def mark_keys_as_published(self) -> None:
        """Mark the current OTK batch as published.

        This mirrors stable python-olm's ``Account.mark_keys_as_published()``:
        the uploaded one-time keys are no longer treated as the next
        unpublished batch, so a subsequent upload can generate a fresh set.
        """
    def create_outbound_session(self, their_identity_key_b64, their_one_time_key_b64):
        '''Create an outbound Olm session to a remote device.

        Performs the X3DH triple-DH key exchange and returns a
        :class:`MatrixOlmSession` ready to encrypt the first message.

        Parameters:
          their_identity_key_b64  - recipient\'s base64 Curve25519 pub key
          their_one_time_key_b64  - recipient\'s base64 Curve25519 OTK

        Reference: Olm spec, Section 4.1 ("Session establishment").
        '''

class MatrixOlmSession:
    '''Single-use outbound Olm session (type-0 pre-key messages only).

    Sufficient for delivering the MegOLM room-key to one recipient device.
    Each call to :meth:`encrypt` advances the chain ratchet once.

    Reference: Olm spec, Section 5 ("Message format").
    '''
    _our_ik_pub: Incomplete
    _eph_pub: Incomplete
    _their_otk_pub: Incomplete
    _their_ik_pub: Incomplete
    _root_key: Incomplete
    _chain_key: Incomplete
    _counter: int
    def __init__(self, our_ik_pub, eph_pub, their_otk_pub, their_ik_pub, root_key, chain_key) -> None: ...
    @property
    def their_identity_key(self):
        """Base64-encoded Curve25519 identity key of the remote device."""
    def encrypt(self, plaintext):
        '''Encrypt *plaintext* (str) as an Olm pre-key (type-0) message.

        Returns ``{"type": 0, "body": "<base64>"}`` suitable for
        inclusion in the ``ciphertext`` object of an
        ``m.olm.v1.curve25519-aes-sha2`` event.

        Reference: Olm spec, Section 5.1.
        '''

class MatrixMegOlmSession:
    """Outbound MegOLM session for room-message encryption.

    State: a 4-component 256-bit ratchet R[0..3], a 32-bit counter,
    and a per-session Ed25519 signing key.  The ratchet advances after
    every encrypted message.  See :data:`MEGOLM_ROTATION_MSGS` and
    :data:`MEGOLM_ROTATION_AGE` for rotation thresholds.

    Reference: MegOLM spec.
    """
    _ratchet: Incomplete
    _counter: Incomplete
    _sk: Incomplete
    _sk_pub: Incomplete
    session_id: Incomplete
    created_at: Incomplete
    def __init__(self, ratchet=None, counter: int = 0, sk_priv_b64=None, created_at=None) -> None:
        """New session (random state) or restore from ``to_dict()``."""
    def _advance(self) -> None:
        """Advance the MegOLM ratchet by one step.

        Mirrors libolm megolm.c ``megolm_advance`` and vodozemac ratchet.rs
        ``Ratchet::advance``.

        The ratchet has 4 parts R[0..3].  On each step, determine the
        highest-index part h that stays constant:
          - counter+1 is a multiple of 2^24  → h=0 (advance R[0..3] from R[0])
          - counter+1 is a multiple of 2^16  → h=1 (advance R[1..3] from R[1])
          - counter+1 is a multiple of 2^8   → h=2 (advance R[2..3] from R[2])
          - otherwise                         → h=3 (advance R[3] from R[3])

        All derived parts are computed from the ORIGINAL value of R[h]
        (saved before any modification), then R[h] itself is updated last.
        This matches libolm's loop which processes higher indices first
        (i = 3 down to h), ensuring data[h] is still the original when it
        is finally overwritten at i==h.
        """
    def _message_keys(self):
        '''Derive (aes_key, mac_key, iv) from the full ratchet state R_i.

        Per the MegOLM spec Section 4.3 and vodozemac (cipher/key.rs
        ``new_megolm``), the HKDF IKM is the complete 128-byte ratchet value
        R_i = R[0]||R[1]||R[2]||R[3].  Using only R[3] (32 bytes) produces
        different keys from what any standard client derives.

        Spec:  AES_KEY||HMAC_KEY||AES_IV = HKDF(0, R_i, "MEGOLM_KEYS", 80)
        '''
    def should_rotate(self, msg_count=None):
        """Return ``True`` if this session has reached a rotation threshold."""
    def encrypt(self, payload_dict):
        """Encrypt *payload_dict* and return base64 MegOLM ciphertext.

        Wire format (MegOLM spec, Section 4):
          version (1 B = 0x03)
          | Protobuf body (field 8: message_index varint,
          |                field 9: ciphertext bytes)
          | HMAC-SHA-256 (8 B)
          | Ed25519 sig (64 B)

        Reference: MegOLM spec, Section 4.
        """
    def session_key(self):
        """Base64 MegOLM session key for sharing in ``m.room_key`` events.

        Wire format (libolm outbound_group_session.c,
        ``olm_outbound_group_session_key``):
          version (1 B = 0x02) | counter (4 B big-endian)
          | R[0..3] (128 B) | Ed25519 signing pub key (32 B)
          | Ed25519 signature (64 B) over all preceding 165 bytes

        The signature lets the recipient verify the session key came from the
        device that owns the Ed25519 signing key published in /keys/upload.
        Without it, vodozemac and other clients reject the key.

        Reference: MegOLM spec, Section 2; libolm
        ``outbound_group_session.c``.
        """
    def to_dict(self):
        """Export session state for persistent storage."""
    @staticmethod
    def from_dict(data):
        """Restore from a ``to_dict()`` snapshot."""

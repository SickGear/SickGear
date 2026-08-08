from _typeshed import Incomplete

_RE_TAG: Incomplete

class AppriseTag:
    """Wraps a tag string and carries optional priority and retry metadata.

    The tag name is the canonical identity; two AppriseTag objects (or an
    AppriseTag and a plain str) are considered equal when their tag names
    match, regardless of priority or retry.  Hash is likewise based solely
    on the tag name so that set intersection and membership tests work
    transparently against sets that contain plain strings.

    Supported string formats:
      tagname          -> priority=0, retry=None
      priority:tagname -> priority=N, retry=None  (config / YAML)
      tagname:retry    -> priority=0, retry=N     (CLI runtime override)
      priority:tagname:retry -> priority=N, retry=N
    """
    __slots__: Incomplete
    _tag: Incomplete
    priority: Incomplete
    retry: Incomplete
    has_priority: Incomplete
    def __init__(self, tag, priority: int = 0, retry=None, has_priority: bool = False) -> None:
        '''Initialise an AppriseTag directly from its constituent parts.

        Prefer AppriseTag.parse() when constructing from a raw string because
        it handles the "priority:tag:retry" tokenisation automatically.

        Args:
            tag (str): The bare tag name.  Always stored lowercased.
            priority (int, optional): Numeric dispatch priority.  Lower numbers
                are dispatched first (0 = highest urgency).  Defaults to 0.
            retry (int or None, optional): Call-level retry count carried by
                this tag token, or None when none was specified.
            has_priority (bool, optional): True when the priority was
                explicitly written in the source string (e.g. "0:endpoint"),
                False when it was absent and the default of 0 was assumed.
                This flag drives the exclusive-vs-escalation dispatch decision.
        '''
    @classmethod
    def parse(cls, value):
        """Return an AppriseTag parsed from a string (or the same object
        if already an AppriseTag).

        Unrecognised strings fall back to a zero-priority, no-retry tag
        whose name is the entire input lowercased.
        """
    def __str__(self) -> str:
        """Return the bare lowercase tag name."""
    def __repr__(self) -> str:
        """Return a developer-readable representation including non-default
        priority and retry values so they are visible in tracebacks."""
    def __hash__(self):
        """Hash based solely on the lowercased tag name.

        This must equal hash(tag_name_string) so that AppriseTag objects
        can be mixed with plain strings inside sets and dictionaries without
        any special handling in is_exclusive_match or elsewhere.
        """
    def __eq__(self, other):
        '''Compare identity by tag name only.

        An AppriseTag is considered equal to a plain string when their
        lowercased tag names match, enabling transparent membership tests
        such as ``"endpoint" in {AppriseTag("endpoint")}``.
        '''
    def __lt__(self, other):
        """Compare tag names lexicographically to allow sorting.

        Used when a deterministic ordering of tags is needed (e.g. for
        reproducible log output).
        """
    def __bool__(self) -> bool:
        """Return False for an empty tag name, True otherwise."""

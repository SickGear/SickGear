class InvalidLanguageValue(Exception):
    """Exception raised when the arguments passed to the `Lang` constructor are
    not valid and compatible:
    - ISO 639-1 identifier
    - ISO 639-2 English name
    - ISO 639-2/B identifier
    - ISO 639-2/T identifier
    - ISO 639-3 identifier
    - ISO 639-3 inverted name
    - ISO 639-3 printed name
    - ISO 639-3 reference name
    - ISO 639-5 identifier
    """

    def __init__(self, **kwargs):

        self.invalid_value = {
            k: v
            for k, v in kwargs.items()
            if k == "name_or_identifier" or v is not None
        }
        if len(self.invalid_value) == 1:
            main_arg = self.invalid_value["name_or_identifier"]
            self.msg = f"{repr(main_arg)} is not a valid Lang argument."
        else:
            self.msg = (
                f"**{self.invalid_value} are not valid Lang keyword arguments."
            )

        super().__init__(self.msg)


class DeprecatedLanguageValue(Exception):
    """Exception raised when the argument passed to the `Lang` constructor
    points to a deprecated ISO 639 language name or identifier.
    """

    def __init__(self, *args, **kwargs):

        reasons = {
            "C": "change",
            "D": "duplicate",
            "N": "non-existent",
            "S": "split",
            "M": "merge",
            "Add": "newly added",
            "Dep": "deprecated",
            "CC": "code change",
            "NC": "name change",
            "NA": "variant name(s) added",
        }
        if reason_code := kwargs.get("reason"):
            reason = reasons.get(reason_code, "unknown reason")
        else:
            reason = "unknown reason"
        if kwargs.get("change_to"):
            remedy = "Use [{change_to}] instead.".format(**kwargs)
        elif kwargs.get("ret_remedy"):
            remedy = kwargs["ret_remedy"]
            if not remedy.endswith("."):
                remedy += "."
        else:
            remedy = ""
        pt = (
            "As of {effective}, [{id}] for {name} is deprecated "
            "due to {0}. {1}"
        )

        self.msg = pt.format(reason, remedy, **kwargs)
        self.id = kwargs.get("id", "")
        self.name = kwargs.get("name", "")
        self.reason = kwargs.get("reason", "")
        self.change_to = kwargs.get("change_to", "")
        self.ret_remedy = kwargs.get("ret_remedy", "")
        self.effective = kwargs.get("effective", "")

        super().__init__(self.msg)

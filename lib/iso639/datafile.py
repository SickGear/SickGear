import json
from importlib.resources import files
from typing import Any

FILENAMES = {
    "mapping_data": "data/iso-639.json",
    "mapping_scope": "data/iso-639_scope.json",
    "mapping_type": "data/iso-639_type.json",
    "mapping_deprecated": "data/iso-639_deprecated.json",
    "mapping_macro": "data/iso-639_macro.json",
    "mapping_ref_name": "data/iso-639_ref_name.json",
    "mapping_other_names": "data/iso-639_other_names.json",
    "list_langs": "data/iso-639_langs.json",
}


def get_file(file_alias: str) -> Any:
    """Get the path of a local data file"""
    return files(__package__).joinpath(FILENAMES[file_alias])


def load_file(file_alias: str) -> Any:
    """Load local JSON file"""
    file_path = get_file(file_alias)
    try:
        with file_path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

from enum import Enum


class ActionKind(str, Enum):
    """Enumeration of possible actions for DICOM de-identification."""

    REMOVE = "X"
    KEEP = "K"

    REPLACE = "D"
    REPLACE_0 = "Z"
    UID = "U"

    REJECT = "R"

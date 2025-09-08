from pathlib import Path
from typing import Optional, cast

import pydicom

TEST_PATH = Path(__file__).resolve().parent
RESOURCES_PATH = TEST_PATH / "resources"
TEST_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage


def tag(keyword: Optional[str] = None, tag_int: Optional[int] = None) -> str:
    """Convert a DICOM keyword to a (gggg,eeee) tag string."""
    if keyword is None and tag_int is None:
        raise ValueError("Either keyword or tag_int must be provided")
    keyword = cast(str, keyword)
    if tag_int is None:
        tag_int = pydicom.datadict.tag_for_keyword(keyword) or 0
    return f"({tag_int >> 16:04X},{tag_int & 0xFFFF:04X})"

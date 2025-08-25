from pathlib import Path
from typing import Any, Dict

import pydicom

from grand_challenge_dicom_de_identifier.deidentifier import (
    ActionKind,
    DeIdentifier,
)
from tests import RESOURCES_PATH

CT_IMAGE_SOP = "1.2.840.10008.5.1.4.1.1.2"


def procedure_factory(
    tag_actions: Dict[str, ActionKind],
    sop_class: str = CT_IMAGE_SOP,
    sop_default: ActionKind = ActionKind.REMOVE,
    tag_default: ActionKind = ActionKind.REMOVE,
) -> Dict[str, Any]:
    """Build a procedure for a single SOP class."""
    tags = {}
    for tag_name, action in tag_actions.items():
        tag_int = pydicom.datadict.tag_for_keyword(tag_name) or 0
        # Convert to (gggg,eeee) format of procedures
        tag = f"({tag_int >> 16:04X},{tag_int & 0xFFFF:04X})"
        tags[tag] = {"default": action}

    return {
        "default": sop_default,
        "version": "test-procedure",
        "sopClass": {
            sop_class: {
                "default": tag_default,
                "tags": tags,
            }
        },
    }


def test_deidentify_files(tmp_path: Path) -> None:  # noqa
    deidentifier = DeIdentifier(
        procedure=procedure_factory(
            tag_actions={
                "PatientName": ActionKind.REMOVE,
                "Modality": ActionKind.KEEP,
            },
        )
    )

    original = RESOURCES_PATH / "ct_minimal.dcm"
    anonmynized = tmp_path / "ct_minimal_anonymized.dcm"

    deidentifier.process_file(
        original,
        output=anonmynized,
    )

    # Sanity: read the original and check the tags
    original_ds = pydicom.dcmread(original)
    assert getattr(original_ds, "PatientName", None) == "Test^Patient"
    assert getattr(original_ds, "Modality", None) == "CT"

    # Read the processed file and check de-identification
    processed_ds = pydicom.dcmread(anonmynized)
    assert not getattr(processed_ds, "PatientName", None)  # Should be removed
    assert getattr(processed_ds, "Modality", None) == "CT"  # Should be kept

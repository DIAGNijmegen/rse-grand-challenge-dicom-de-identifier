# mypy: disallow-untyped-decorators=False

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict

import pydicom
import pytest
from pydicom.dataset import Dataset

from grand_challenge_dicom_de_identifier.deidentifier import (
    ActionKind,
    DeIdentifier,
)
from grand_challenge_dicom_de_identifier.exceptions import (
    RejectedDICOMFileError,
)
from tests import RESOURCES_PATH

CT_IMAGE_SOP = "1.2.840.10008.5.1.4.1.1.2"


def procedure_factory(
    tag_actions: Dict[str, ActionKind],
    sop_class: str = CT_IMAGE_SOP,
    sop_default: ActionKind = ActionKind.REJECT,
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


@pytest.mark.parametrize(
    "dicom_sop_class, procedure_sop_class, default, context",
    (
        (
            "1.2.840.10008.5.1.4.1.1.4",
            "1.2.840.10008.5.1.4.1.1.4",
            ActionKind.KEEP,
            nullcontext(),
        ),
        (
            "1.2.840.10008.5.1.4.1.1.4",
            "1.2.840.10008.5.1.4.1.1.4",
            ActionKind.REJECT,
            nullcontext(),
        ),
        (
            "1.2.840.10008.5.1.4.1.1.4",
            "1.2.840.10008.5.1.4.1.1.128",
            ActionKind.KEEP,
            nullcontext(),
        ),
        (
            "1.2.840.10008.5.1.4.1.1.4",
            "1.2.840.10008.5.1.4.1.1.128",
            ActionKind.REJECT,
            pytest.raises(RejectedDICOMFileError),
        ),
        (
            "1.2.840.10008.5.1.4.1.1.4",
            "1.2.840.10008.5.1.4.1.1.128",
            "NOT_A_VALID_ACTION",
            pytest.raises(NotImplementedError),
        ),
    ),
)
def test_sop_class_handling(  # noqa
    dicom_sop_class: str,
    procedure_sop_class: str,
    default: ActionKind,
    context: Any,
) -> None:
    # Create a minimal DICOM dataset with a SOPClassUID
    ds = Dataset()
    ds.SOPClassUID = dicom_sop_class

    deidentifier = DeIdentifier(
        procedure=procedure_factory(
            tag_actions={},
            sop_class=procedure_sop_class,
            sop_default=default,
        )
    )

    with context:
        deidentifier.process_dataset(ds)


@pytest.mark.parametrize(
    "procedure_tag_actions, default, context",
    (
        (
            {"PatientName": ActionKind.KEEP},
            ActionKind.KEEP,
            nullcontext(),
        ),
        (
            {},
            ActionKind.KEEP,
            nullcontext(),
        ),
        (
            {"PatientName": "NOT_A_VALID_ACTION"},
            ActionKind.KEEP,
            pytest.raises(NotImplementedError),
        ),
        (
            {},
            "NOT_A_VALID_ACTION",
            pytest.raises(NotImplementedError),
        ),
        (
            {"PatientName": ActionKind.REJECT},
            ActionKind.REJECT,
            pytest.raises(RejectedDICOMFileError),
        ),
        (
            {},
            ActionKind.REJECT,
            pytest.raises(RejectedDICOMFileError),
        ),
    ),
)
def test_action_handling(  # noqa
    procedure_tag_actions: Dict[str, ActionKind | str],
    default: ActionKind | str,
    context: Any,
) -> None:
    # Create a minimal DICOM dataset with a SOPClassUID
    ds = Dataset()
    ds.SOPClassUID = CT_IMAGE_SOP
    ds.PatientName = "Test^Patient"

    deidentifier = DeIdentifier(
        procedure=procedure_factory(
            tag_actions=procedure_tag_actions,  # type: ignore
            sop_class=CT_IMAGE_SOP,
            tag_default=default,  # type: ignore
        )
    )

    with context:
        deidentifier.process_dataset(ds)

# mypy: disallow-untyped-decorators=False

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict

import pydicom
import pytest
from pydicom.dataset import Dataset

from grand_challenge_dicom_de_identifier.deidentifier import DicomDeidentifier
from grand_challenge_dicom_de_identifier.exceptions import (
    RejectedDICOMFileError,
)
from grand_challenge_dicom_de_identifier.models import ActionKind
from tests import RESOURCES_PATH

TEST_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage


def tag(keyword: str) -> str:
    """Convert a DICOM keyword to a (gggg,eeee) tag string."""
    tag_int = pydicom.datadict.tag_for_keyword(keyword) or 0
    return f"({tag_int >> 16:04X},{tag_int & 0xFFFF:04X})"


def test_deidentify_files(tmp_path: Path) -> None:  # noqa
    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("PatientName"): {"default": ActionKind.REMOVE},
                        tag("Modality"): {"default": ActionKind.KEEP},
                    },
                }
            },
        }
    )

    original = RESOURCES_PATH / "ct_minimal.dcm"
    anonmynized = tmp_path / "ct_minimal_anonymized.dcm"

    deidentifier.deidentify_file(
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
    "dicom_sop_class, procedure, context",
    (
        (  # Sanity: regular match
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    TEST_SOP_CLASS: {"tags": {}},
                },
                "default": ActionKind.KEEP,
            },
            nullcontext(),
        ),
        (  # Sanity: regular match REJECT behaviour
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    TEST_SOP_CLASS: {"tags": {}},
                },
                "default": ActionKind.REJECT,
            },
            nullcontext(),
        ),
        (  # Default is: regular match REJECT behaviour
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    TEST_SOP_CLASS: {"tags": {}},
                },
                "default": ActionKind.REJECT,
            },
            nullcontext(),
        ),
        (  # No SOP Class match: KEEP via default
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tags": {}},
                },
                "default": ActionKind.KEEP,
            },
            nullcontext(),
        ),
        (  # No SOP Class match: REJECT
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tags": {}},
                },
                "default": ActionKind.REJECT,
                "justification": "TEST default justification",
            },
            pytest.raises(
                RejectedDICOMFileError, match="TEST default justification"
            ),
        ),
        (  # No SOP Class match: REJECT even if no default is specified
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tags": {}},
                },
            },
            pytest.raises(RejectedDICOMFileError),
        ),
        (  # No SOP Class match: REJECT, no justification
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tags": {}},
                },
                "default": ActionKind.REJECT,
            },
            pytest.raises(
                RejectedDICOMFileError,
                match="is not supported",
            ),
        ),
        (  # No SOP Class match: invalid action
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tags": {}},
                },
                "default": "NOT_A_VALID_ACTION",
            },
            pytest.raises(NotImplementedError),
        ),
    ),
)
def test_sop_class_handling(  # noqa
    dicom_sop_class: str,
    procedure: Dict[str, Any],
    context: Any,
) -> None:
    ds = Dataset()
    ds.SOPClassUID = dicom_sop_class

    deidentifier = DicomDeidentifier(procedure=procedure)

    with context:
        deidentifier.deidentify_dataset(ds)


@pytest.mark.parametrize(
    "procedure, context",
    (
        (
            {  # Sanity: regular KEEP
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {
                            tag("PatientName"): {"default": ActionKind.KEEP}
                        },
                    }
                },
            },
            nullcontext(),
        ),
        (  # Sanity: regular KEEP, via defaults
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {},
                        "default": ActionKind.KEEP,
                    }
                },
            },
            nullcontext(),
        ),
        (  # Unsupported action
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {
                            tag("PatientName"): {
                                "default": "NOT_A_VALID_ACTION"
                            }
                        },
                    }
                },
            },
            pytest.raises(NotImplementedError),
        ),
        (  # Unsupported action, via defaults
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {},
                        "default": "NOT_A_VALID_ACTION",
                    },
                }
            },
            pytest.raises(NotImplementedError),
        ),
        (  # Rejection via tag action
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {
                            tag("PatientName"): {
                                "default": ActionKind.REJECT,
                                "justification": "TEST tag-specific rejection",
                            }
                        },
                    }
                },
            },
            pytest.raises(
                RejectedDICOMFileError, match="TEST tag-specific rejection"
            ),
        ),
        (  # Rejection via tag action, no justification
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {
                            tag("PatientName"): {
                                "default": ActionKind.REJECT,
                            }
                        },
                    }
                },
            },
            pytest.raises(
                RejectedDICOMFileError, match="no justification provided"
            ),
        ),
        (  # Rejection via defaults
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {},
                        "default": ActionKind.REJECT,
                        "justification": "TEST default rejection",
                    }
                },
            },
            pytest.raises(
                RejectedDICOMFileError, match="TEST default rejection"
            ),
        ),
        (  # Rejection via defaults, no justification
            {
                "sopClass": {
                    TEST_SOP_CLASS: {
                        "tags": {},
                        "default": ActionKind.REJECT,
                    }
                },
            },
            pytest.raises(
                RejectedDICOMFileError, match="no justification provided"
            ),
        ),
    ),
)
def test_action_handling(  # noqa
    procedure: Dict[str, Any],
    context: Any,
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(procedure=procedure)

    with context:
        deidentifier.deidentify_dataset(ds)


def test_keep_action() -> None:  # noqa
    # Create a minimal DICOM dataset with a SOPClassUID
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("PatientName"): {"default": ActionKind.KEEP},
                    },
                }
            },
        }
    )

    assert ds.PatientName == "Test^Patient"
    deidentifier.deidentify_dataset(ds)
    assert ds.PatientName == "Test^Patient"


def test_remove_action() -> None:  # noqa
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("PatientName"): {"default": ActionKind.REMOVE},
                    },
                }
            },
        }
    )

    assert ds.PatientName == "Test^Patient"
    deidentifier.deidentify_dataset(ds)
    assert getattr(ds, "PatientName", None) is None


def test_reject_action() -> None:  # noqa
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("PatientName"): {"default": ActionKind.REJECT},
                    },
                }
            },
        }
    )

    assert ds.PatientName == "Test^Patient"
    with pytest.raises(RejectedDICOMFileError):
        deidentifier.deidentify_dataset(ds)


def test_uid_action() -> None:  # noqa

    def gen_dataset() -> Dataset:
        ds = Dataset()
        ds.SOPClassUID = TEST_SOP_CLASS
        ds.PatientName = "Test^Patient"
        ds.Modality = "CT"
        return ds

    ds = gen_dataset()
    ds_same = gen_dataset()
    ds_partial_same = gen_dataset()
    ds_partial_same.Modality = "MT"  # Different modality

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("PatientName"): {"default": ActionKind.UID},
                        tag("Modality"): {"default": ActionKind.UID},
                    },
                }
            },
        }
    )

    # First pass
    deidentifier.deidentify_dataset(ds)
    assert ds.PatientName != "Test^Patient"
    assert ds.Modality != "CT"

    # Should be stable for the same values
    deidentifier.deidentify_dataset(ds_same)
    assert ds_same.PatientName == ds.PatientName
    assert ds_same.Modality == ds.Modality

    # Mixed values should lead to partially different UIDs
    deidentifier.deidentify_dataset(ds_partial_same)
    assert ds_partial_same.PatientName == ds.PatientName
    assert ds_partial_same.Modality != ds.Modality

    # New Deidentifier should lead to different UIDs
    another_deidentifier = DicomDeidentifier(procedure=deidentifier.procedure)
    new_ds = gen_dataset()

    another_deidentifier.deidentify_dataset(new_ds)
    assert new_ds.PatientName != ds.PatientName
    assert new_ds.Modality != ds.Modality

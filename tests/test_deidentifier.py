# mypy: disallow-untyped-decorators=False

import struct
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Optional

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
        (  # No SOP Class match: fallback to REJECT when no default is specified
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
        ds.StudyInstanceUID = "1.2.3"
        ds.SeriesInstanceUID = "3.4.5"
        return ds

    ds = gen_dataset()
    ds_same = gen_dataset()
    ds_partial_same = gen_dataset()
    ds_partial_same.SeriesInstanceUID = "6.7.8"  # Different UID

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("StudyInstanceUID"): {"default": ActionKind.UID},
                        tag("SeriesInstanceUID"): {"default": ActionKind.UID},
                    },
                }
            },
        }
    )

    # First pass
    deidentifier.deidentify_dataset(ds)
    assert ds.StudyInstanceUID != "1.2.3"
    assert ds.SeriesInstanceUID != "3.4.5"

    # Should be stable for the same values
    deidentifier.deidentify_dataset(ds_same)
    assert ds_same.StudyInstanceUID == ds.StudyInstanceUID
    assert ds_same.SeriesInstanceUID == ds.SeriesInstanceUID

    # Mixed values should lead to partially different UIDs
    deidentifier.deidentify_dataset(ds_partial_same)
    assert ds_partial_same.StudyInstanceUID == ds.StudyInstanceUID
    assert ds_partial_same.SeriesInstanceUID != ds.SeriesInstanceUID

    # New Deidentifier should lead to different UIDs
    another_deidentifier = DicomDeidentifier(procedure=deidentifier.procedure)
    new_ds = gen_dataset()

    another_deidentifier.deidentify_dataset(new_ds)
    assert new_ds.StudyInstanceUID != ds.StudyInstanceUID
    assert new_ds.SeriesInstanceUID != ds.SeriesInstanceUID


@pytest.mark.parametrize(
    "action",
    (
        ActionKind.REPLACE,
        ActionKind.REPLACE_0,
    ),
)
def test_replace_action(action: ActionKind) -> None:  # noqa
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("PatientName"): {"default": action},
                    },
                }
            },
        }
    )

    assert ds.PatientName == "Test^Patient"
    deidentifier.deidentify_dataset(ds)
    assert ds.PatientName == "DUMMY^PATIENT^^^"


def test_fallback_default_action() -> None:  # noqa
    """Test that missing default action leads to REMOVE being aplied."""
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(
        procedure={  # Note: no default action has been specified
            "sopClass": {TEST_SOP_CLASS: {"tags": {}}},
        }
    )

    assert ds.PatientName == "Test^Patient"
    deidentifier.deidentify_dataset(ds)
    assert (
        getattr(ds, "PatientName", None) is None
    ), "Default action should be REMOVE"


def test_patient_identity_removed_tag() -> None:  # noqa
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("SOPClassUID"): {"default": ActionKind.KEEP},
                        tag("PatientIdentityRemoved"): {
                            "default": ActionKind.KEEP
                        },
                    },
                }
            },
        }
    )

    assert "PatientIdentityRemoved" not in ds, "Sanity"
    deidentifier.deidentify_dataset(ds)
    assert getattr(ds, "PatientIdentityRemoved", None) == "YES"

    # Should stay YES when run multiple times
    deidentifier.deidentify_dataset(ds)
    assert getattr(ds, "PatientIdentityRemoved", None) == "YES"


def test_deidentification_method_tag() -> None:  # noqa
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    deidentifier = DicomDeidentifier(
        procedure={  # Note: no default action has been specified
            "version": "test-procedure",
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {  # Required to ensure a double pass succeeds
                        tag("SOPClassUID"): {
                            "default": ActionKind.KEEP,
                        },
                        tag("DeidentificationMethod"): {
                            "default": ActionKind.KEEP
                        },
                    },
                }
            },
        }
    )

    assert "DeidentificationMethod" not in ds, "Sanity"
    deidentifier.deidentify_dataset(ds)
    assert (
        "De-identified by Python DICOM de-identifier using procedure"
        in getattr(ds, "DeidentificationMethod", "")
    )

    # Doing it twice ammends it
    methods = getattr(ds, "DeidentificationMethod", "").split(";")
    assert len(methods) == 1

    deidentifier.deidentify_dataset(ds)

    methods = getattr(ds, "DeidentificationMethod", "").split(";")
    assert len(methods) == 2


@pytest.mark.parametrize(
    "VR, expected",
    (
        ("AE", "DUMMY_AE"),
        ("AS", "030Y"),
        ("AT", b"\x00\x00\x00\x00"),
        ("CS", "DUMMY"),
        ("DA", "20000101"),
        ("DS", "0.0"),
        ("DT", "20000101120000.000000"),
        ("FL", 0.0),
        ("FD", 0.0),
        ("IS", "0"),
        ("LO", "DUMMY_LONG_STRING"),
        ("LT", "DUMMY LONG TEXT"),
        ("OB", bytes([0x00])),
        ("OD", struct.pack("d", 0.0)),
        ("OF", struct.pack("f", 0.0)),
        ("OL", struct.pack("I", 0x00000000)),
        ("OV", struct.pack("Q", 0)),
        ("OW", struct.pack("H", 0x0000)),
        ("PN", "DUMMY^PATIENT^^^"),
        ("SH", "DUMMY"),
        ("SL", 0),
        ("SQ", []),
        ("SS", 0),
        ("ST", "DUMMY SHORT TEXT"),
        ("SV", 0),
        ("TM", "120000.000000"),
        ("UC", "DUMMY UNLIMITED CHARACTERS"),
        ("UI", "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0"),
        ("UL", 0),
        ("UN", bytes([0x00])),
        ("UR", "http://dummy.example.test"),
        ("US", 0),
        ("UT", "DUMMY UNLIMITED TEXT"),
        ("UV", 0),
    ),
)
def test_dummy_values(VR: str, expected: Any) -> None:  # noqa
    deidentifier = DicomDeidentifier(procedure={})
    dummy = deidentifier._get_dummy_value(vr=VR)
    assert dummy == expected, f"VR {VR} produced unexpected dummy value"


def test_missing_dummy_value() -> None:  # noqa
    deidentifier = DicomDeidentifier(procedure={})
    with pytest.raises(NotImplementedError):
        _ = deidentifier._get_dummy_value(vr="NOT_A_VALID_VR")


@pytest.mark.parametrize(
    "action, expected_number",
    (
        (ActionKind.KEEP, 2),
        (ActionKind.REPLACE, 2),
        (ActionKind.REPLACE_0, 2),
        (ActionKind.REMOVE, 0),
    ),
)
def test_sequence_handling_remove_replace_keep(  # noqa
    action: ActionKind, expected_number: int
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    # Create a sequence with two items
    ds.ReferencedStudySequence = pydicom.sequence.Sequence(
        [
            Dataset(),
            Dataset(),
        ],
    )
    ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID = "1.2.3"
    ds.ReferencedStudySequence[1].ReferencedSOPInstanceUID = "4.5.6"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("ReferencedStudySequence"): {"default": action},
                        tag("ReferencedSOPInstanceUID"): {
                            "default": ActionKind.KEEP
                        },
                    },
                }
            },
        }
    )
    deidentifier.deidentify_dataset(ds)

    sequence = getattr(ds, "ReferencedStudySequence", [])
    assert len(sequence) == expected_number


@pytest.mark.parametrize(
    "action, expected_value",
    (
        (
            ActionKind.KEEP,
            "1.2.3",
        ),
        (
            ActionKind.REPLACE,
            "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0",
        ),
        (
            ActionKind.REMOVE,
            None,
        ),
    ),
)
def test_within_sequence_tag_handling(  # noqa
    action: ActionKind, expected_value: Optional[str]
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    # Create a sequence with two items
    ds.ReferencedStudySequence = pydicom.sequence.Sequence([Dataset()])
    ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID = "1.2.3"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("ReferencedStudySequence"): {
                            "default": ActionKind.KEEP
                        },
                        tag("ReferencedSOPInstanceUID"): {
                            "default": action,
                        },
                    },
                }
            },
        }
    )
    deidentifier.deidentify_dataset(ds)

    if expected_value is None:
        assert not hasattr(
            ds.ReferencedStudySequence[0], "ReferencedSOPInstanceUID"
        )
    else:
        value = ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID
        assert value == expected_value


def test_within_sequence_tag_handling_after_replace() -> None:  # noqa
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    # Create a sequence with two items
    ds.ReferencedStudySequence = pydicom.sequence.Sequence([Dataset()])
    ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID = "1.2.3"
    ds.ReferencedStudySequence[0].ReferencedSOPClassUID = "3.4.5"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tags": {
                        tag("ReferencedStudySequence"): {
                            "default": ActionKind.REPLACE
                        },
                        tag("ReferencedSOPInstanceUID"): {
                            "default": ActionKind.REMOVE,
                        },
                    },
                    "default": ActionKind.KEEP,
                }
            },
        }
    )
    deidentifier.deidentify_dataset(ds)

    # The sequence is REPLACEd but the inner tag is REMOVED
    assert hasattr(ds, "ReferencedStudySequence")
    value = ds.ReferencedStudySequence[0].ReferencedSOPClassUID
    assert value == "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0"  # Dummy value
    assert not hasattr(
        ds.ReferencedStudySequence[0], "ReferencedSOPInstanceUID"
    )

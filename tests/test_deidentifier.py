# mypy: disallow-untyped-decorators=False

import struct
from contextlib import nullcontext
from typing import Any, Dict, Optional, cast

import pydicom
import pytest
from pydicom import DataElement
from pydicom.dataset import Dataset

from grand_challenge_dicom_de_identifier.deidentifier import DicomDeidentifier
from grand_challenge_dicom_de_identifier.exceptions import (
    RejectedDICOMFileError,
)
from grand_challenge_dicom_de_identifier.models import ActionKind
from tests import TEST_SOP_CLASS, tag


@pytest.mark.parametrize(
    "dicom_sop_class, procedure, context",
    (
        (  # Sanity: regular match
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    TEST_SOP_CLASS: {"tag": {}},
                },
                "default": ActionKind.KEEP,
            },
            nullcontext(),
        ),
        (  # Sanity: regular match REJECT behaviour
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    TEST_SOP_CLASS: {"tag": {}},
                },
                "default": ActionKind.REJECT,
            },
            nullcontext(),
        ),
        (  # Default is: regular match REJECT behaviour
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    TEST_SOP_CLASS: {"tag": {}},
                },
                "default": ActionKind.REJECT,
            },
            nullcontext(),
        ),
        (  # No SOP Class match: KEEP via default
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tag": {}},
                },
                "default": ActionKind.KEEP,
            },
            nullcontext(),
        ),
        (  # No SOP Class match: REJECT
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tag": {}},
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
                    "1.2.840.10008.5.1.4.1.1.128": {"tag": {}},
                },
            },
            pytest.raises(RejectedDICOMFileError),
        ),
        (  # No SOP Class match: REJECT, no justification
            TEST_SOP_CLASS,
            {
                "sopClass": {
                    "1.2.840.10008.5.1.4.1.1.128": {"tag": {}},
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
                    "1.2.840.10008.5.1.4.1.1.128": {"tag": {}},
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
                        "tag": {
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
                        "tag": {},
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
                        "tag": {
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
                        "tag": {},
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
                        "tag": {
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
                        "tag": {
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
                        "tag": {},
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
                        "tag": {},
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
                    "tag": {
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
                    "tag": {
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
                    "tag": {
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
                    "tag": {
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
    "action, vr, initial_value, expected_value",
    (
        (
            ActionKind.REPLACE,
            "PN",
            "Test^Patient",
            "DUMMY^PATIENT^^^",
        ),
        (  # Does a dummy value normally
            ActionKind.REPLACE_0,
            "PN",
            "Test^Patient",
            "DUMMY^PATIENT^^^",
        ),
        (  # Unless it matches the blanking VRs
            ActionKind.REPLACE_0,
            "CS",
            "Foo",
            "",
        ),
        (
            ActionKind.REPLACE_0,
            "LO",
            "Foo",
            "",
        ),
        (
            ActionKind.REPLACE_0,
            "LT",
            "Foo",
            "",
        ),
        (
            ActionKind.REPLACE_0,
            "SH",
            "Foo",
            "",
        ),
        (
            ActionKind.REPLACE_0,
            "ST",
            "Foo",
            "",
        ),
        (
            ActionKind.REPLACE_0,
            "UC",
            "Foo",
            "",
        ),
        (
            ActionKind.REPLACE_0,
            "UT",
            "Foo",
            "",
        ),
    ),
)
def test_replace_action(  # noqa
    action: ActionKind,
    vr: str,
    initial_value: Any,
    expected_value: Any,
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    tag_id = 0x00100010

    ds.add_new(tag_id, vr, initial_value)

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tag": {
                        tag(tag_int=tag_id): {
                            "default": action,
                        }
                    },
                },
            }
        }
    )

    assert cast(DataElement, ds[tag_id]).value == initial_value, "Sanity"

    deidentifier.deidentify_dataset(ds)

    assert cast(DataElement, ds[tag_id]).value == expected_value


def test_fallback_default_action() -> None:  # noqa
    """Test that missing default action leads to REMOVE being aplied."""
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier = DicomDeidentifier(
        procedure={  # Note: no default action has been specified
            "sopClass": {TEST_SOP_CLASS: {"tag": {}}},
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
                    "tag": {
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
                    "tag": {  # Required to ensure a double pass succeeds
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

    expected_value = (
        "grand-challenge-dicom-de-identifier:procedure:test-procedure"
    )
    assert ds.DeidentificationMethod == expected_value

    # Doing it twice ammends it
    deidentifier.deidentify_dataset(ds)
    assert cast(DataElement, ds["DeidentificationMethod"]).VM == 2


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
                    "tag": {
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
    "sequence_action, tag_action, expected_value",
    (
        (
            ActionKind.KEEP,
            ActionKind.KEEP,
            "1.2.3",  # Unchanged
        ),
        (
            ActionKind.KEEP,
            ActionKind.REPLACE,
            "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0",  # Replaced
        ),
        (
            ActionKind.REPLACE,
            ActionKind.REPLACE,
            "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0",  # Replaced
        ),
        (
            ActionKind.REPLACE,
            ActionKind.REMOVE,
            "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0",  # Replaced
        ),
        (
            ActionKind.REPLACE,
            ActionKind.KEEP,
            "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0",  # Replaced
        ),
        (
            ActionKind.REMOVE,
            ActionKind.REMOVE,
            None,  # Removed
        ),
        (
            ActionKind.REMOVE,
            ActionKind.KEEP,
            None,  # Removed
        ),
    ),
)
def test_within_sequence_tag_handling(  # noqa
    sequence_action: ActionKind,
    tag_action: ActionKind,
    expected_value: Optional[str],
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    ds.ReferencedStudySequence = pydicom.sequence.Sequence([Dataset()])
    ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID = "1.2.3"

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tag": {
                        tag("ReferencedStudySequence"): {
                            "default": sequence_action
                        },
                        tag("ReferencedSOPInstanceUID"): {
                            "default": tag_action,
                        },
                    },
                }
            },
        }
    )
    deidentifier.deidentify_dataset(ds)

    if expected_value is None:
        assert not hasattr(ds, "ReferencedStudySequence")
    else:
        value = ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID
        assert value == expected_value


@pytest.mark.parametrize(
    "action",
    (
        ActionKind.KEEP,
        ActionKind.REMOVE,
        ActionKind.REPLACE,
        ActionKind.REPLACE_0,
    ),
)
def test_unique_value(action: ActionKind) -> None:  # noqa
    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tag": {
                        tag("PatientName"): {
                            "default": action,
                            "justification": "action justification",
                        },
                    },
                }
            },
        },
        assert_unique_value_for={"PatientName"},
    )

    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    ds.PatientName = "Test^Patient"

    deidentifier.deidentify_dataset(ds)

    ds_other = Dataset()
    ds_other.SOPClassUID = TEST_SOP_CLASS
    ds_other.PatientName = "Test^AnotherPatient"

    with pytest.raises(
        RejectedDICOMFileError, match="has differing values across files"
    ):
        deidentifier.deidentify_dataset(ds_other)


@pytest.mark.parametrize(
    "start_value",
    ["Test^Patient", None],
)
@pytest.mark.parametrize(
    "action",
    [
        ActionKind.REMOVE,
        ActionKind.REPLACE,
        ActionKind.KEEP,
        ActionKind.REJECT,
    ],
)
@pytest.mark.parametrize(
    "element_keyword, arg_keyword",
    [
        ("StudyInstanceUID", "study_instance_uid_suffix"),
        ("SeriesInstanceUID", "series_instance_uid_suffix"),
    ],
)
def test_forced_suffix(  # noqa
    start_value: Optional[str],
    action: ActionKind,
    element_keyword: str,
    arg_keyword: str,
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS
    if start_value is not None:
        setattr(ds, element_keyword, start_value)

    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tag": {
                        tag("PatientName"): {"default": action},
                    },
                }
            },
        },
        **{arg_keyword: "1.2.3"},
    )

    deidentifier.deidentify_dataset(ds)
    new_value = cast(DataElement, ds[element_keyword]).value
    assert new_value == "1.2.826.0.1.3680043.10.1666.1.2.3"


@pytest.mark.parametrize(
    "keyword",
    (
        "study_instance_uid_suffix",
        "series_instance_uid_suffix",
    ),
)
@pytest.mark.parametrize(
    "value, context",
    (
        ("", nullcontext()),
        ("1.2.3", nullcontext()),
        (
            "1.2.3.",
            pytest.raises(
                ValueError,
                match="Invalid value for VR UI:",
            ),
        ),
        (
            ".1.2.3",
            pytest.raises(
                ValueError,
                match="Invalid value for VR UI:",
            ),
        ),
        (
            "1..2.3",
            pytest.raises(
                ValueError,
                match="Invalid value for VR UI",
            ),
        ),
        (
            "1.2a.3",
            pytest.raises(
                ValueError,
                match="Invalid value for VR UI",
            ),
        ),
        (
            "1" * 65,  # Can only be 64 chars
            pytest.raises(
                ValueError,
                match="exceeds the maximum length of 64",
            ),
        ),
    ),
)
def test_forced_forced_validity(  # noqa
    keyword: str,
    value: str,
    context: Any,
) -> None:
    ds = Dataset()
    ds.SOPClassUID = TEST_SOP_CLASS

    with context:
        _ = DicomDeidentifier(
            procedure={
                "sopClass": {TEST_SOP_CLASS: {"tag": {}}},
            },
            **{
                keyword: value,
            },
        )

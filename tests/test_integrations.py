import io
from zipfile import Path

import pydicom

from grand_challenge_dicom_de_identifier.deidentifier import DicomDeidentifier
from grand_challenge_dicom_de_identifier.models import ActionKind
from tests import RESOURCES_PATH, TEST_SOP_CLASS, tag


def test_deidentify_files(tmp_path: Path) -> None:  # noqa
    deidentifier = DicomDeidentifier(
        procedure={
            "sopClass": {
                TEST_SOP_CLASS: {
                    "tag": {
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
        output=str(anonmynized),
    )

    # Sanity: read the original and check the tags
    original_ds = pydicom.dcmread(original)
    assert getattr(original_ds, "PatientName", None) == "Test^Patient"
    assert getattr(original_ds, "Modality", None) == "CT"

    # Read the processed file and check de-identification
    processed_ds = pydicom.dcmread(str(anonmynized))
    assert not getattr(processed_ds, "PatientName", None)  # Should be removed
    assert getattr(processed_ds, "Modality", None) == "CT"  # Should be kept


def test_grand_challenge_procedure(tmp_path: Path) -> None:  # noqa
    """Smoke test for the build-in Grand Challenge procedure."""
    deidentifier = DicomDeidentifier()

    original = RESOURCES_PATH / "ct_minimal.dcm"

    with io.BytesIO() as _:
        deidentifier.deidentify_file(
            original,
            output=_,
        )

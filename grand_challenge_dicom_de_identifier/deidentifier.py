import os
import struct
from collections import defaultdict
from datetime import datetime
from functools import partial
from typing import Any, AnyStr, BinaryIO, Dict

import pydicom
from pydicom import DataElement, Dataset
from pydicom.filebase import ReadableBuffer, WriteableBuffer
from pydicom.fileutil import PathType

from grand_challenge_dicom_de_identifier.exceptions import (
    RejectedDICOMFileError,
)
from grand_challenge_dicom_de_identifier.models import ActionKind
from grand_challenge_dicom_de_identifier.typing import Action

# Requested via http://www.medicalconnections.co.uk/
GRAND_CHALLENGE_ROOT_UID: str = "1.2.826.0.1.3680043.10.1666."

VR_DUMMY_VALUES: Dict[str, Any] = {
    # Application Entity - up to 16 characters, no leading/trailing spaces
    "AE": "DUMMY_AE",
    # Age String - 4 characters (nnnD, nnnW, nnnM, nnnY), here 30 years
    "AS": "030Y",
    # Attribute Tag - 4 bytes as hex pairs (0000,0000)
    "AT": b"\x00\x00\x00\x00",
    # Code String - up to 16 characters, uppercase
    "CS": "DUMMY",
    # Date - YYYYMMDD format (January 1, 2000)
    "DA": "20000101",
    # Decimal String - floating point as string, up to 16 chars
    "DS": "0.0",
    # Date Time - YYYYMMDDHHMMSS.FFFFFF&ZZXX format
    "DT": "20000101120000.000000",
    # Floating Point Single - 4 bytes
    "FL": 0.0,
    # Floating Point Double - 8 bytes
    "FD": 0.0,
    # Integer String - integer as string, up to 12 chars
    "IS": "0",
    # Long String - up to 64 characters
    "LO": "DUMMY_LONG_STRING",
    # Long Text - up to 10240 characters
    "LT": "DUMMY LONG TEXT",
    # Other Byte - sequence of bytes (single zero byte)
    "OB": bytes([0x00]),
    # Other Double - sequence of 64-bit floating point values
    "OD": struct.pack("d", 0.0),
    # Other Float - sequence of 32-bit floating point values
    "OF": struct.pack("f", 0.0),
    # Other Long - sequence of 32-bit words
    "OL": struct.pack("I", 0x00000000),
    # Other Very Long - sequence of 64-bit words
    "OV": struct.pack("Q", 0),
    # Other Word - sequence of 16-bit words
    "OW": struct.pack("H", 0x0000),
    # Person Name - Family^Given^Middle^Prefix^Suffix
    "PN": "DUMMY^PATIENT^^^",
    # Short String - up to 16 characters
    "SH": "DUMMY",
    # Signed Long - 32-bit signed integer
    "SL": 0,
    # Sequence - sequence of items (empty)
    "SQ": [],
    # Signed Short - 16-bit signed integer
    "SS": 0,
    # Short Text - up to 1024 characters
    "ST": "DUMMY SHORT TEXT",
    # Signed Very Long - 64-bit signed integer
    "SV": 0,
    # Time - HHMMSS.FFFFFF format (12:00:00.000000)
    "TM": "120000.000000",
    # Unlimited Characters - unlimited length
    "UC": "DUMMY UNLIMITED CHARACTERS",
    # Unique Identifier (UID format)
    "UI": "1.2.3.4.5.6.7.8.9.0.1.2.3.4.5.6.7.8.9.0",
    # Unsigned Long - 32-bit unsigned integer
    "UL": 0,
    # Unknown - sequence of bytes (single zero byte buffer)
    "UN": b"\x00",
    # Universal Resource Identifier/Locator - URI/URL
    "UR": "http://dummy.example.test",
    # Unsigned Short - 16-bit unsigned integer
    "US": 0,
    # Unlimited Text - unlimited length text
    "UT": "DUMMY UNLIMITED TEXT",
    # Unsigned Very Long - 64-bit unsigned integer
    "UV": 0,
}


class DicomDeidentifier:
    """

    A class to handle DICOM de-identification based on a de-identifaction procedure.

    Example of a procedure:
    {
        "default": "R",  # Default action for unknown SOP Classes
        "version": "2024a",  # Version of the procedure
        "sopClass": {
            "1.2.840.10008.xx": {  # SOP Class UID
                "default": "X",  # Default action for unknown tags
                "tags": {
                    "(0010,0010)": {"default": "X"},  # PatientName
                    "(0008,0060)": {"default": "K"},  # Modality
                    "(0008,0016)": {"default": "K"},  # SOPClassUID
            }
    }

    """

    def __init__(
        self,
        procedure: None | Dict[str, Any] = None,
    ) -> None:
        """Initialize the DicomDeidentifier.

        Parameters
        ----------
        procedure : optional
            De-identification procedure to apply, by default the
            grand-challenge procedure is used.
        """
        self.procedure: Dict[str, Any] = procedure or {}

        self.uid_map: Dict[str, pydicom.uid.UID] = defaultdict(
            lambda: pydicom.uid.generate_uid(prefix=GRAND_CHALLENGE_ROOT_UID)
        )

    def deidentify_file(
        self,
        /,
        file: PathType | BinaryIO | ReadableBuffer,
        *,
        output: str | os.PathLike[AnyStr] | BinaryIO | WriteableBuffer,
    ) -> None:
        """Process a DICOM file and save the de-identified result in output."""
        with pydicom.dcmread(fp=file, force=True) as dataset:
            self.deidentify_dataset(dataset)
            dataset.save_as(output)

    def deidentify_dataset(self, dataset: pydicom.Dataset) -> None:
        """Process a DICOM dataset in place."""
        sop_class_procedure = self._get_sop_class_procedure(dataset)

        dataset.walk(
            partial(
                self._handle_element,
                action_lookup=sop_class_procedure["tags"],
                default_action={
                    "default": sop_class_procedure.get(
                        "default", ActionKind.REMOVE
                    ),
                    "justification": sop_class_procedure.get(
                        "justification", ""
                    ),
                },
            )
        )

        self.set_deidentification_method_tag(dataset)

    def _get_sop_class_procedure(self, dataset: Dataset) -> Any:
        try:
            sop_procedure = self.procedure["sopClass"][dataset.SOPClassUID]
        except KeyError:
            default = self.procedure.get("default", ActionKind.REJECT)
            if default == ActionKind.REJECT:
                raise RejectedDICOMFileError(
                    justification=self.procedure.get(
                        "justification",
                        f"SOP Class {dataset.SOPClassUID} is not supported",
                    )
                ) from None
            elif default == ActionKind.KEEP:
                sop_procedure = {"default": ActionKind.KEEP, "tags": {}}
            else:
                raise NotImplementedError(
                    f"Default action {default} not implemented"
                ) from None

        return sop_procedure

    def _handle_element(
        self,
        dataset: Dataset,
        elem: DataElement,
        action_lookup: Dict[str, Action],
        default_action: Action,
    ) -> None:
        try:
            action_desc = action_lookup[str(elem.tag)]
        except KeyError:
            action = default_action["default"]
            justification = default_action["justification"]
        else:
            action = action_desc["default"]
            justification = action_desc.get("justification", "")

        if action == ActionKind.REMOVE:
            del dataset[elem.tag]
        elif action == ActionKind.KEEP:
            pass
        elif action == ActionKind.REJECT:
            raise RejectedDICOMFileError(justification=justification) from None
        elif action == ActionKind.UID:
            elem.value = self.uid_map[elem.value]
        elif action in (ActionKind.REPLACE, ActionKind.REPLACE_0):
            elem.value = self._get_dummy_value(vr=elem.VR)
        else:
            raise NotImplementedError(f"Action {action} not implemented")

    def _get_dummy_value(self, vr: str) -> Any:
        if vr not in VR_DUMMY_VALUES:
            raise NotImplementedError(f"Unsupported DICOM VR: {vr}")
        return VR_DUMMY_VALUES[vr]

    def set_deidentification_method_tag(self, dataset: Dataset) -> None:
        """
        Add or update the de-identification method tag.

        Args:
            dataset: DICOM dataset to modify
        """
        version = self.procedure.get("version", "unknown")
        timestamp = datetime.now().isoformat()
        method = (
            f"De-identified by Python DICOM de-identifier using procedure "
            f"version {version} on {timestamp}."
        )

        existing_method = dataset.get("DeidentificationMethod", "")
        if existing_method:
            new_method = f"{existing_method}; {method}"
        else:
            new_method = method

        # DICOM tag (0012,0063) - De-identification Method
        dataset.add_new(
            tag=pydicom.tag.Tag(0x0012, 0x0063),
            VR="LO",
            value=new_method,
        )

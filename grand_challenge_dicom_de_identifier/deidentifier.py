import os
import struct
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, AnyStr, BinaryIO, Callable, Collection, Dict, cast

import pydicom
from grand_challenge_dicom_de_id_procedure import (
    procedure as grand_challenge_procedure,
)
from pydicom import DataElement, Dataset
from pydicom.filebase import ReadableBuffer, WriteableBuffer
from pydicom.fileutil import PathType

from grand_challenge_dicom_de_identifier.exceptions import (
    RejectedDICOMFileError,
)
from grand_challenge_dicom_de_identifier.models import ActionKind
from grand_challenge_dicom_de_identifier.typing import Action

# Requested via https://www.medicalconnections.co.uk/FreeUID.html
GRAND_CHALLENGE_ROOT_UID: str = "1.2.826.0.1.3680043.10.1666."

# VRs (Value Representations) that should be blanked when using "Z" action
VR_TO_BLANK: set[str] = {
    "CS",  # Code String
    "LO",  # Long String
    "LT",  # Long Text
    "SH",  # Short String
    "ST",  # Short Text
    "UC",  # Unlimited Characters
    "UT",  # Unlimited Text
}

# Dummy values for different VRs when "Z" or "D" action is used
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


@dataclass
class ActionContext:
    """Context object for passing information during action handling."""

    dataset: Dataset
    elem: DataElement
    action_lookup: Dict[str, Action]
    default_action: Action
    action: str
    justification: str


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
                "tag": {
                    "(0010,0010)": {"default": "X"},  # PatientName
                    "(0008,0060)": {"default": "K"},  # Modality
                    "(0008,0016)": {"default": "K"},  # SOPClassUID
            }
    }

    """

    _overwrite_study_instance_uid: None | str = None
    _overwrite_series_instance_uid: None | str = None

    def __init__(
        self,
        procedure: None | Dict[str, Any] = None,
        assert_unique_value_for: None | Collection[str] = None,
        study_instance_uid_suffix: str = "",
        series_instance_uid_suffix: str = "",
    ) -> None:
        """Initialize the DicomDeidentifier.

        Parameters
        ----------
        procedure : optional
            De-identification procedure to apply. By default the
            installed grand-challenge procedure is used.

        assert_unique_value_for : optional
            A collection of element keywords (e.g. ["PatientName"]) that
            ensures input files all have the same value for these
            elements. If a file has a different value for any of these
            elements compared to previous files, a RejectedDICOMFileError
            is raised. By default no such check is performed.

        study_instance_uid_suffix : optional
            Suffix to append to the root uid for StudyInstanceUIDs.

        series_instance_uid_suffix : optional
            Suffix to append to root uid for SeriesInstanceUIDs.
        """
        self.procedure: Dict[str, Any] = procedure or grand_challenge_procedure

        self._assert_unique_values_for: Collection[str] = (
            assert_unique_value_for or set()
        )
        for keyword in self._assert_unique_values_for:
            self._assert_valid_keyword(keyword)
        self._unique_value_lookup: Dict[str, Any] = {}

        # Setup UID handling
        self.uid_map: Dict[str, pydicom.uid.UID] = defaultdict(
            lambda: pydicom.uid.generate_uid(prefix=GRAND_CHALLENGE_ROOT_UID)
        )
        if study_instance_uid_suffix:
            self._overwrite_study_instance_uid = (
                GRAND_CHALLENGE_ROOT_UID + study_instance_uid_suffix
            )
            self._assert_valid_value(
                "StudyInstanceUID", self._overwrite_study_instance_uid
            )
        if series_instance_uid_suffix:
            self._overwrite_series_instance_uid = (
                GRAND_CHALLENGE_ROOT_UID + series_instance_uid_suffix
            )
            self._assert_valid_value(
                "SeriesInstanceUID", self._overwrite_series_instance_uid
            )

        self._action_map: Dict[str, Callable[[ActionContext], None]] = {
            ActionKind.REMOVE: self._handle_remove_action,
            ActionKind.KEEP: self._handle_keep_action,
            ActionKind.REJECT: self._handle_reject_action,
            ActionKind.UID: self._handle_uid_action,
            ActionKind.REPLACE: self._handle_replace_action,
            ActionKind.REPLACE_0: self._handle_replace_0,
        }

    @staticmethod
    def _assert_valid_keyword(keyword: str) -> None:
        if keyword not in pydicom.datadict.keyword_dict:
            raise ValueError(f"Keyword {keyword!r} is not valid")

    @staticmethod
    def _assert_valid_value(keyword: str, value: Any) -> None:
        vr = pydicom.datadict.dictionary_VR(keyword)
        pydicom.dataelem.validate_value(
            vr=vr, value=value, validation_mode=pydicom.config.RAISE
        )

    def deidentify_file(
        self,
        /,
        file: PathType | BinaryIO | ReadableBuffer,
        *,
        output: str | os.PathLike[AnyStr] | BinaryIO | WriteableBuffer,
    ) -> None:
        """Process a DICOM file and save the de-identified result in output."""
        with pydicom.dcmread(
            fp=file,
            force=True,
            defer_size=1024 * 2,  # Defer loading elements larger than 2KB
        ) as dataset:
            self.deidentify_dataset(dataset)
            dataset.save_as(
                output,
                enforce_file_format=True,
            )

    @staticmethod
    def _check_burned_in_annotations(dataset: pydicom.Dataset) -> None:
        burned_in = getattr(dataset, "BurnedInAnnotation", "").casefold()
        if burned_in == "yes":
            raise RejectedDICOMFileError(
                justification="DICOM file contains burned in annotations"
            )

    def deidentify_dataset(self, dataset: pydicom.Dataset) -> None:
        """Process a DICOM dataset in place."""
        self._check_burned_in_annotations(dataset)
        sop_class_procedure = self._get_sop_class_procedure(dataset)

        for elem in dataset:
            self._handle_element(
                elem=elem,
                dataset=dataset,
                action_lookup=sop_class_procedure["tag"],
                default_action={
                    "default": sop_class_procedure.get(
                        "default", ActionKind.REMOVE
                    ),
                    "justification": sop_class_procedure.get(
                        "justification", ""
                    ),
                },
            )

        # Some post-processing steps
        self.set_deidentification_method_tag(dataset)
        self.set_patient_identity_removed_tag(dataset)
        self.set_overwrites(dataset)

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
                sop_procedure = {"default": ActionKind.KEEP, "tag": {}}
            else:
                raise NotImplementedError(
                    f"Default action {default} not implemented"
                ) from None

        return sop_procedure

    @staticmethod
    def set_patient_identity_removed_tag(dataset: Dataset) -> None:
        """
        Add or update the Patient Identity Removed tag (0012,0062) with value 'YES'.

        Args:
            dataset: DICOM dataset to modify
        """
        # DICOM tag (0012,0062) - Patient Identity Removed
        dataset.add_new(
            tag=pydicom.tag.Tag(0x0012, 0x0062),
            VR="CS",
            value="YES",
        )

    def set_deidentification_method_tag(self, dataset: Dataset) -> None:
        """
        Add the de-identification method tag.

        Args:
            dataset: DICOM dataset to modify
        """
        version = self.procedure.get("version", "unknown")

        description = (
            f"grand-challenge-dicom-de-identifier:procedure:{version}"
        )

        if "DeidentificationMethod" in dataset:
            elem = cast(DataElement, dataset["DeidentificationMethod"])
            if elem.VM == 0:
                methods = []
            if elem.VM == 1:
                methods = [elem.value]
            else:
                methods = elem.value
            methods.append(description)
            dataset.DeidentificationMethod = methods
        else:
            dataset.DeidentificationMethod = description

    def set_overwrites(self, dataset: Dataset) -> None:
        """
        Add or overwrite elements in the dataset.

        Args:
            dataset: DICOM dataset to modify
        """
        if self._overwrite_study_instance_uid:
            dataset.add_new(
                "StudyInstanceUID",
                "UI",
                self._overwrite_study_instance_uid,
            )
        if self._overwrite_series_instance_uid:
            dataset.add_new(
                "SeriesInstanceUID",
                "UI",
                self._overwrite_series_instance_uid,
            )

    def _handle_element(
        self,
        elem: DataElement,
        dataset: Dataset,
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

        self._check_unique_value(elem=elem)

        try:
            handler = self._action_map[action]
        except KeyError:
            raise NotImplementedError(
                f"Action {action} not implemented"
            ) from None

        handler(
            ActionContext(
                dataset=dataset,
                elem=elem,
                action_lookup=action_lookup,
                default_action=default_action,
                action=action,
                justification=justification,
            )
        )

    def _check_unique_value(self, elem: DataElement) -> None:
        if elem.keyword in self._assert_unique_values_for:
            if elem.keyword not in self._unique_value_lookup:
                self._unique_value_lookup[elem.keyword] = elem.value
            elif self._unique_value_lookup[elem.keyword] != elem.value:
                raise RejectedDICOMFileError(
                    justification=f"Element {elem.keyword!r} has differing values "
                    "across files: these must be identical."
                )

    def _handle_remove_action(self, context: ActionContext, /) -> None:
        del context.dataset[context.elem.tag]

    def _handle_keep_action(self, context: ActionContext, /) -> None:
        if context.elem.VR == "SQ":  # Sequence
            for dataset in context.elem.value:
                for elem in dataset:
                    self._handle_element(
                        elem=elem,
                        dataset=dataset,
                        action_lookup=context.action_lookup,
                        default_action=context.default_action,
                    )
        else:
            pass  # No action needed, keep as is

    def _handle_reject_action(self, context: ActionContext, /) -> None:
        raise RejectedDICOMFileError(
            justification=context.justification
        ) from None

    def _handle_uid_action(self, context: ActionContext, /) -> None:
        context.elem.value = self.uid_map[context.elem.value]

    def _handle_replace_action(self, context: ActionContext, /) -> None:
        if context.elem.VR == "SQ":  # Sequence
            for dataset in context.elem.value:
                for elem in dataset:
                    self._handle_element(
                        elem=elem,
                        dataset=dataset,
                        action_lookup={},  # Always defer to the default
                        default_action={
                            "default": ActionKind.REPLACE,
                            "justification": "Parent sequence was replaced",
                        },
                    )
        else:
            context.elem.value = self._get_dummy_value(vr=context.elem.VR)

    def _handle_replace_0(self, context: ActionContext, /) -> None:
        if context.elem.VR == "SQ":  # Sequence
            for dataset in context.elem.value:
                for elem in dataset:
                    self._handle_element(
                        elem=elem,
                        dataset=dataset,
                        action_lookup={},  # Always defer to the default
                        default_action={
                            "default": ActionKind.REPLACE_0,
                            "justification": "Parent sequence was replaced (0)",
                        },
                    )
        elif context.elem.VR in VR_TO_BLANK:
            context.elem.value = ""
        else:
            context.elem.value = self._get_dummy_value(vr=context.elem.VR)

    def _get_dummy_value(self, vr: str) -> Any:
        if vr not in VR_DUMMY_VALUES:
            raise NotImplementedError(f"Unsupported DICOM VR: {vr}")
        return VR_DUMMY_VALUES[vr]

import os
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
        else:
            raise NotImplementedError(f"Action {action} not implemented")

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

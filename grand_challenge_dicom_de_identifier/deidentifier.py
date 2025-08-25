from enum import Enum
from functools import partial
import os
from typing import AnyStr, BinaryIO, Dict, Any
from pathlib import Path
from pydicom import DataElement, Dataset
from pydicom.filebase import ReadableBuffer, WriteableBuffer
from pydicom.fileutil import PathType

import pydicom

from grand_challenge_dicom_de_identifier.exceptions import (
    RejectedDICOMFileError,
)


class ActionKind(str, Enum):
    REMOVE = "X"
    KEEP = "K"

    REPLACE = "D"
    REPLACE_0 = "Z"
    UID = "U"

    REJECT = "R"


class DeIdentifier:
    """A class to handle DICOM de-identification based on a DE-ID procedure."""

    def __init__(
        self,
        procedure: None | Dict[str, Any] = None,
    ) -> None:
        """Initialize the DeIdentifier.

        Parameters
        ----------
        procedure : None | Procedure, optional
            De-identification procedure to apply, by default the
            grand-challenge procedure is used
        """
        self.procedure = procedure or {}

    def process_file(
        self,
        /,
        file: PathType | BinaryIO | ReadableBuffer,
        *,
        output: str | os.PathLike[AnyStr] | BinaryIO | WriteableBuffer,
    ) -> None:
        with pydicom.dcmread(fp=file, force=True) as dataset:
            self.process_dataset(dataset)
            dataset.save_as(output)

    def process_dataset(self, dataset: pydicom.Dataset) -> None:
        """Processes a DICOM dataset in place."""

        try:
            sop_procedure = self.procedure["sopClass"][dataset.SOPClassUID]
        except KeyError:
            default = self.procedure["default"]
            if default == ActionKind.REJECT:
                raise RejectedDICOMFileError
            elif default == ActionKind.KEEP:
                sop_procedure = {"default": ActionKind.KEEP}
            else:
                raise NotImplementedError(
                    f"Default action {default} not implemented"
                )

        dataset.walk(
            partial(
                self._process_element,
                default_action=sop_procedure["default"],
                action_lookup=sop_procedure["tags"],
            )
        )

    def _process_element(
        self,
        dataset: Dataset,
        elem: DataElement,
        default_action: ActionKind,
        action_lookup: Dict[str, Any],
    ) -> None:
        try:
            action = action_lookup[str(elem.tag)]
        except KeyError:
            action = default_action
        else:
            action = action["default"]

        if action == ActionKind.REMOVE:
            del dataset[elem.tag]
        elif action == ActionKind.KEEP:
            pass
        else:
            raise NotImplementedError(f"Action {action} not implemented")

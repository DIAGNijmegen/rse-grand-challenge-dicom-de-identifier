from typing import Optional


class RejectedDICOMFileError(Exception):
    """Raised when a DICOM file is rejected."""

    def __init__(self, justification: Optional[str] = None) -> None:
        """
        Initialize the exception with an optional justification message.

        Args:
            justification (Optional[str]): The reason or explanation for raising
            the exception.
        """
        super().__init__(justification)
        self.justification = justification or "no justification provided"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}: {self.justification}"

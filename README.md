# Grand-Challenge DICOM De-Identifier
[![CI](https://github.com/DIAGNijmegen/rse-grand-challenge-dicom-de-identifier/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/DIAGNijmegen/rse-grand-challenge-dicom-de-identifier/actions/workflows/ci.yml?query=branch%3Amain)
![PyPI - Version](https://img.shields.io/pypi/v/grand-challenge-dicom-de-identifier)

This Python-based package uses [Grand-Challenge De-Identification Procedure](https://github.com/DIAGNijmegen/rse-grand-challenge-dicom-de-id-procedure) to de-identify DICOM files.

It follows the procedure's prescribed actions of keeping, replacing, rejecting, or replacing elements in the files.


## Basic Usage

Install via:


    $ pip install grand-challenge-dicom-de-identifier

In your Python script then initiate the deidentifier and use either the `deidentify_file` or `deidentify_file` methods to process data:

```Python
from grand_challenge_dicom_de_identifier.deidentifier import DicomDeidentifier

deidentifier = DicomDeidentifier()

# Deidentify a single file
deidentifier.deidentify_file(
    "input.dcm",
    output="anom/output.dcm"
)
```

Or by providing a `pydicom.Dataset` directly:

```Python
from grand_challenge_dicom_de_identifier.deidentifier import DicomDeidentifier
import pydicom

deidentifier = DicomDeidentifier()
dataset = pydicom.Dataset()

# Deidentify a pydicom Dataset
deidentifier.deidentify_dataset(
    dataset
)

```

## Advanced Usage

The following arguments can be provided to the deidentifier:

### `assert_unique_value_for`

> A collection of element keywords (e.g. ["PatientName"]) that ensures input files all have the same value for these  elements. If a file has a different value for any of these elements compared to previous files, a RejectedDICOMFileError is raised. By default no such check is performed.

## `study_instance_uid_suffix` / `series_instance_uid_suffix`

> A specific suffix to overwrite the respective `StudyInstanceUID` and `SeriesInstanceUID` with. These will be prefixed with the ROOT uid of Grand Challenge: `"1.2.826.0.1.3680043.10.1666."`.

from typing import Dict

from grand_challenge_dicom_de_identifier.models import ActionKind

Action = Dict[str, ActionKind | str]

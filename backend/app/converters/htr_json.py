"""
Natív (belső) JSON → Page.

A frontend ezt a formátumot termeli/fogadja. Itt csak validálunk
és átengedjük, hogy ugyanúgy lehessen kezelni a többi formátummal.
"""
from __future__ import annotations

import json
from ..schema import Page


def parse(data: bytes) -> Page:
    obj = json.loads(data.decode("utf-8"))
    # Pydantic validálja a struktúrát; ha hibás, ValidationError-t dob
    return Page.model_validate(obj)

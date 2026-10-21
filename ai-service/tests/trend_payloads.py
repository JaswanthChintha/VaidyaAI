from __future__ import annotations

from typing import Any, Dict, List, Optional

CREATININE_UMOL_CONVERSION: Dict[str, Any] = {
    "from_unit": "umol/l",
    "to_unit": "mg/dl",
    "factor": 0.011312,
    "offset": 0.0,
    "formula": "mg/dl = umol/l x 0.011312",
    "basis": "MW creatinine 113.12 g/mol; 1 mg/dL = 88.4017 umol/L",
}


def vf(
    name: str,
    value: Any,
    unit: Optional[str] = None,
    *,
    questionable: bool = False,
    clinically_extreme: bool = False,
    flags: Optional[List[Dict[str, Any]]] = None,
    **provenance: Any,
) -> Dict[str, Any]:
    prov: Dict[str, Any] = {"source": "lab_report"}
    prov.update(provenance)
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "canonical_unit": True,
        "source": "lab_report",
        "provenance": prov,
        "status": "questionable" if questionable else "valid",
        "questionable": questionable,
        "clinically_extreme": clinically_extreme,
        "flags": flags or [],
    }


def rejection(
    name: str,
    reason_code: str = "IMPLAUSIBLE_VALUE_HIGH",
    reason: str = "Outside the physiologically possible range.",
) -> Dict[str, Any]:
    return {"name": name, "reason_code": reason_code, "reason": reason}


def report(
    report_id: str,
    chrono_date: str,
    features: Optional[Dict[str, Any]] = None,
    *,
    rejected: Optional[Dict[str, Any]] = None,
    sequence: Optional[int] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "report_id": report_id,
        "chrono_date": chrono_date,
        "validated": {"valid": features or {}, "rejected": rejected or {}},
    }
    if sequence is not None:
        body["sequence"] = sequence
    return body


def series_reports(
    feature: str,
    values: List[Any],
    unit: Optional[str],
    **provenance: Any,
) -> List[Dict[str, Any]]:
    return [
        report(
            f"r{index + 1}",
            f"2024-{index + 1:02d}-01T00:00:00Z",
            {feature: vf(feature, value, unit, **provenance)},
        )
        for index, value in enumerate(values)
    ]

# incidents/annex_e.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from django.utils import timezone
from .models import Incident

# -----------------------------------------------------------------------------
# JSON Schema (draft-07) for your current JSON export.  We keep this compatible
# with your existing keys (contact_info, org_details, incident_times, ...).
# Additional convenience keys (like "organisation" with nested site info) are
# included in the payload but are not required by this schema.
# -----------------------------------------------------------------------------
ANNEX_E_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Annex E – NIS Incident Reporting (Ofgem)",
    "type": "object",
    "required": ["contact_info", "org_details", "incident_times"],
    "properties": {
        "contact_info": {
            "type": "object",
            "required": ["name", "email"],
            "properties": {
                "name": {"type": "string"},
                "role": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string", "format": "email"},
            },
        },
        "org_details": {
            "type": "object",
            "required": ["organisation", "essential_service"],
            "properties": {
                "organisation": {"type": "string"},
                "essential_service": {"type": "string"},
                "sites_assets": {"type": "array", "items": {"type": "string"}},
                "internal_incident_id": {"type": "string"},
            },
        },
        "incident_times": {
            "type": "object",
            "properties": {
                "detected_at": {"type": "string", "format": "date-time"},
                "occurred_at": {"type": "string", "format": "date-time"},
                "reported_internally_at": {"type": "string", "format": "date-time"},
            },
        },
        "type_of_incident": {"type": "string"},
        "status": {"type": "string", "enum": ["detected", "suspected", ""]},
        "stage": {"type": "string", "enum": ["ongoing", "ended", "ongoing_but_managed", ""]},
        "description": {
            "type": "object",
            "properties": {
                "incident_types": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "discovery": {"type": "string"},
                "duration": {"type": "string"},  # free text (e.g., "18h", "2 days")
                "locations": {"type": "array", "items": {"type": "string"}},
                "services_systems_affected": {"type": "array", "items": {"type": "string"}},
                "impact_on_services_users": {"type": "string"},
                "impact_on_safety": {"type": "string"},
                "suspected_cause": {"type": "string"},
                "cross_border_impact": {"type": "string"},
                "other_relevant_info": {"type": "string"},
            },
        },
        "root_cause": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "system_failure",
                        "natural_phenomena",
                        "human_error",
                        "malicious_actions",
                        "third_party_failure",
                        "other",
                        "",
                    ],
                },
                "other_text": {"type": "string"},
            },
        },
        "categorisation": {"type": "string"},  # e.g., intrusion, DoS
        "severity": {"type": "string", "enum": ["major", "high", "medium", "low", ""]},
        "mitigations": {"type": "string"},
        "who_else_informed": {"type": "array", "items": {"type": "string"}},  # e.g., ["CSIRT/NCSC", "NCA"]
        # Convenience extension (not required by schema):
        # "organisation": {... nested org/site/contact details ...}
    },
}


def _fmt(dt):
    """Return local ISO 8601 (minute precision) or None."""
    return None if not dt else timezone.localtime(dt).isoformat(timespec="minutes")


def _site_block(inc: Incident) -> Dict[str, Any]:
    """
    Build a rich organisation/site block from inc.site (if any), falling back
    to inc.org and sensible defaults. This is used by HTML exports and is included
    in the JSON for convenience, but not required by ANNEX_E_JSON_SCHEMA.
    """
    site = getattr(inc, "site", None)
    org = getattr(site, "org", None) or getattr(inc, "org", None)

    # Pull fields if your Site model has them (all access via getattr for safety).
    site_name = getattr(site, "name", "") or ""
    essential_service = getattr(site, "essential_service", "") or ""
    network_role = getattr(site, "network_role", "") or ""
    eic_code = getattr(site, "eic_code", "") or ""
    tz = getattr(site, "timezone", "") or "Europe/London"

    address = {
        "line1": getattr(site, "address_line1", "") or "",
        "line2": getattr(site, "address_line2", "") or "",
        "city": getattr(site, "city", "") or "",
        "postcode": getattr(site, "postcode", "") or "",
        "country_code": getattr(site, "country_code", "") or "GB",
    }

    contact = {
        "name": getattr(site, "contact_name", "") or "",
        "role": getattr(site, "contact_role", "") or "",
        "email": getattr(site, "contact_email", "") or "",
        "phone": getattr(site, "contact_phone", "") or "",
        "ooh_phone": getattr(site, "ooh_phone", "") or "",
        "dpo_email": getattr(site, "dpo_email", "") or "",
    }

    return {
        "name": getattr(org, "name", "") or "",
        "site": {
            "name": site_name,
            "essential_service": essential_service,
            "network_role": network_role,
            "eic_code": eic_code,
            "timezone": tz,
            "address": address,
            "contact": contact,
        },
    }


def incident_to_annex_e(
    inc: Incident,
    *,
    # Reporter (caller/user); any missing values will fall back to Site contact
    reporter_name: str,
    reporter_email: str,
    reporter_role: Optional[str] = None,
    reporter_phone: Optional[str] = None,
    # Optional overrides (UI-supplied). If omitted, we try to infer from Site.
    essential_service: Optional[str] = None,
    occurred_at=None,
    reported_internally_at=None,
    status: Optional[str] = None,       # "detected" | "suspected"
    stage: Optional[str] = None,        # "ongoing" | "ended" | "ongoing_but_managed"
    description: Optional[Dict[str, Any]] = None,
    root_cause: Optional[Dict[str, Any]] = None,
    categorisation: Optional[str] = None,
    severity: Optional[str] = None,
    mitigations: Optional[str] = None,
    who_else_informed: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build an Annex E payload from an Incident plus any extra fields you collect.
    - Pulls organisation/site/contact/address defaults from inc.site when present.
    - Keeps your existing "org_details" section for backwards compatibility.
    - Also includes a richer "organisation" block used by the HTML export.
    """
    site = getattr(inc, "site", None)
    org = getattr(site, "org", None) or getattr(inc, "org", None)

    # Sites list for legacy "org_details.sites_assets"
    site_name = getattr(site, "name", None)
    sites_assets = [s for s in [site_name] if s]

    # Prefer explicit reporter fields; fall back to site contact if blank
    site_contact_name = getattr(site, "contact_name", "") if site else ""
    site_contact_email = getattr(site, "contact_email", "") if site else ""
    site_contact_role = getattr(site, "contact_role", "") if site else ""
    site_contact_phone = getattr(site, "contact_phone", "") if site else ""

    resolved_reporter_name = reporter_name or site_contact_name
    resolved_reporter_email = reporter_email or site_contact_email
    resolved_reporter_role = (reporter_role or site_contact_role or "").strip()
    resolved_reporter_phone = (reporter_phone or site_contact_phone or "").strip()

    # Essential service default: explicit arg > site field > ""
    resolved_essential_service = (
        essential_service
        or (getattr(site, "essential_service", "") if site else "")
        or ""
    )

    # Duration is free text in your schema. If you'd like, you could compute
    # a simple duration string when reported (e.g., "18h") — left blank here.
    desc = {
        "incident_types": [],
        "summary": (inc.title or "").strip(),
        "discovery": "",
        "duration": "",
        "locations": sites_assets,
        "services_systems_affected": [],
        "impact_on_services_users": "",
        "impact_on_safety": "",
        "suspected_cause": "",
        "cross_border_impact": "",
        "other_relevant_info": (inc.report_notes or "").strip(),
    }
    if isinstance(description, dict):
        # Merge any provided description fields over defaults
        desc.update({k: v for k, v in description.items() if v is not None})

    # Root cause default
    root = {"category": "other", "other_text": ""}
    if isinstance(root_cause, dict):
        root.update({k: v for k, v in root_cause.items() if v is not None})

    payload: Dict[str, Any] = {
        # ---- Required by your schema ----
        "contact_info": {
            "name": resolved_reporter_name,
            "role": resolved_reporter_role,
            "phone": resolved_reporter_phone,
            "email": resolved_reporter_email,
        },
        "org_details": {
            "organisation": getattr(org, "name", "") or "",
            "essential_service": resolved_essential_service,
            "sites_assets": sites_assets,
            "internal_incident_id": f"{inc.id}",
        },
        "incident_times": {
            "detected_at": _fmt(getattr(inc, "aware_at", None)),
            "occurred_at": _fmt(occurred_at),
            "reported_internally_at": _fmt(reported_internally_at),
        },
        "type_of_incident": "",  # free text (e.g., "ransomware", "power failure")
        "status": status or "",  # keep empty string if not provided to satisfy schema enum
        "stage": stage or "",
        "description": desc,
        "root_cause": root,
        "categorisation": (categorisation or ""),
        "severity": (severity or ""),
        "mitigations": (mitigations or ""),
        "who_else_informed": who_else_informed or [],
        # ---- Convenience (used by HTML export; safe to include in JSON) ----
        "organisation": _site_block(inc),
    }

    return payload

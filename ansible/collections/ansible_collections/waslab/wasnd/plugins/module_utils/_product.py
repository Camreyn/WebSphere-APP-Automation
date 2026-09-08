# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re


def _field(block, label, version=False):
    suffix = r"([0-9][^\s]*)" if version else r"(.+?)"
    match = re.search(
        r"(?im)^\s*%s\s*:?\s+%s\s*$" % (re.escape(label), suffix),
        block,
    )
    return match.group(1).strip() if match else ""


def installed_products(version_info):
    """Extract Installed Product records from IBM versionInfo.sh output."""
    sections = re.split(r"(?im)^\s*Installed Product\s*$", version_info or "")
    candidates = sections[1:] if len(sections) > 1 else [version_info or ""]
    products = []
    seen = set()
    for block in candidates:
        product = {
            "name": _field(block, "Name"),
            "id": _field(block, "ID"),
            "version": _field(block, "Version", version=True),
        }
        if not any(product.values()):
            continue
        key = (product["name"], product["id"], product["version"])
        if key not in seen:
            seen.add(key)
            products.append(product)
    return products


def _is_was(product):
    name = product.get("name", "").lower()
    identifier = product.get("id", "").upper()
    return (
        "websphere application server" in name
        or identifier in ("ND", "BASE", "ILAN")
    )


def _workflow_kind(product):
    name = product.get("name", "").lower()
    identifier = product.get("id", "").upper()
    if "business automation workflow" in name or identifier.startswith("BAW"):
        return "baw"
    if (
        "business process manager" in name
        or re.search(r"\bibm\s+bpm\b", name)
        or identifier.startswith("BPM")
    ):
        return "bpm"
    return ""


def product_facts(version_info):
    """Classify the underlying WAS edition and optional workflow product."""
    products = installed_products(version_info)
    was_product = next((item for item in products if _is_was(item)), {})
    workflow_product = next(
        (item for item in products if _workflow_kind(item)),
        {},
    )

    raw = version_info or ""
    raw_lower = raw.lower()
    workflow_kind = _workflow_kind(workflow_product)
    if not workflow_kind and "business automation workflow" in raw_lower:
        workflow_kind = "baw"
    if not workflow_kind and (
        "business process manager" in raw_lower
        or re.search(r"\bibm\s+bpm\b", raw_lower)
        or "com.ibm.bpm." in raw_lower
    ):
        workflow_kind = "bpm"

    was_name = was_product.get("name", "")
    was_id = was_product.get("id", "").upper()
    if was_id == "ND" or "network deployment" in was_name.lower():
        edition = "Network Deployment"
    elif was_id in ("BASE", "ILAN") or re.search(
        r"(?im)^\s*ID\s*:?[ \t]+(?:BASE|ILAN)\s*$",
        raw,
    ):
        edition = "Base"
    elif "network deployment" in raw_lower or re.search(
        r"(?im)^\s*ID\s*:?[ \t]+ND\s*$",
        raw,
    ):
        edition = "Network Deployment"
    else:
        edition = "unknown"

    versions = re.findall(r"(?im)^\s*Version\s*:?[ \t]+([0-9][^\s]*)", raw)
    was_version = was_product.get("version", "")
    if not was_version and versions:
        was_version = versions[-1]

    was_detected = bool(
        was_product
        or "websphere application server" in raw_lower
        or "com.ibm.websphere." in raw_lower
    )
    family = workflow_kind or ("was" if was_detected else "unknown")
    family_names = {
        "was": "WebSphere Application Server",
        "bpm": "IBM Business Process Manager",
        "baw": "IBM Business Automation Workflow",
        "unknown": "Unknown IBM product",
    }
    return {
        "edition": edition,
        "version": was_version or "unknown",
        "family": family,
        "family_name": workflow_product.get("name", "") or family_names[family],
        "workflow_version": workflow_product.get("version", "") or "",
        "products": products,
    }

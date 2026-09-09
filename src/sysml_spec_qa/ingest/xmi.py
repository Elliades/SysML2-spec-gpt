from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

@dataclass
class MetaItem:
    name: str
    kind: str  # class | property | constraint | other
    extra: dict


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _attrs(elem: ET.Element) -> dict[str, str]:
    return {_local(k): v for k, v in elem.attrib.items()}


def parse_metamodel(path: Path) -> list[MetaItem]:
    if path.suffix.lower() == ".json":
        return parse_json_schema(path)
    return parse_xmi(path)


def parse_json_schema(path: Path) -> list[MetaItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[MetaItem] = []
    defs = data.get("$defs") or data.get("definitions") or {}
    if isinstance(defs, dict):
        for name, body in defs.items():
            if not isinstance(name, str) or not name[:1].isalpha():
                continue
            kind = "class"
            if "constraint" in str(body).lower()[:80]:
                kind = "constraint"
            items.append(MetaItem(name=name, kind=kind, extra={"source": "json"}))
            if isinstance(body, dict):
                props = body.get("properties") or {}
                if isinstance(props, dict):
                    for prop in props:
                        if isinstance(prop, str) and prop[:1].isalpha():
                            items.append(
                                MetaItem(name=prop, kind="property", extra={"owner": name})
                            )
    return _dedupe(items)


def parse_xmi(path: Path) -> list[MetaItem]:
    items: list[MetaItem] = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        return []

    for elem in root.iter():
        attrs = _attrs(elem)
        name = attrs.get("name")
        if not name or not re.match(r"^[A-Za-z_][A-Za-z0-9_]+$", name):
            continue
        type_name = (attrs.get("type") or attrs.get("type") or "").lower()
        tag = _local(elem.tag).lower()
        blob = f"{tag} {type_name}"
        if "constraint" in blob or name.startswith(("check", "validate", "derive")):
            kind = "constraint"
        elif "class" in blob or tag in {"packagedelement", "eclassifiers"}:
            # packagedElement without type is too noisy; require class-like type when present.
            if type_name and "class" not in type_name and "constraint" not in type_name:
                if "property" in blob or "attribute" in blob:
                    kind = "property"
                else:
                    continue
            else:
                kind = "class" if (not type_name or "class" in type_name) else "other"
        elif "property" in blob or "attribute" in blob or "ereference" in blob:
            kind = "property"
        else:
            if tag in {"ownedrule"}:
                kind = "constraint"
            elif tag in {"ownedattribute", "ownedend", "eattributes", "ereferences"}:
                kind = "property"
            else:
                continue
        if kind == "class" and not name[0].isupper():
            continue
        items.append(MetaItem(name=name, kind=kind, extra={"tag": tag, "type": type_name}))
    return _dedupe(items)


def _dedupe(items: list[MetaItem]) -> list[MetaItem]:
    seen: set[tuple[str, str]] = set()
    out: list[MetaItem] = []
    for item in items:
        key = (item.name, item.kind)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

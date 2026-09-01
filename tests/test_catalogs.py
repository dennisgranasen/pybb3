from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_json(name: str):
    return json.loads((ROOT / "docs" / name).read_text(encoding="utf-8"))


def literal_client_request_pairs() -> set[tuple[str, str]]:
    tree = ast.parse((ROOT / "src/bb3/client.py").read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "request" or len(node.args) < 2:
            continue
        request, response = node.args[:2]
        if isinstance(request, ast.Constant) and isinstance(response, ast.Constant):
            if isinstance(request.value, str) and isinstance(response.value, str):
                result.add((request.value, response.value))
    return result


def test_message_catalog_covers_literal_client_requests():
    catalog = load_json("messages.json")
    catalog_pairs = {(request, data["response"]) for request, data in catalog.items()}
    assert literal_client_request_pairs() <= catalog_pairs


def test_message_catalog_schema_and_order():
    catalog = load_json("messages.json")
    assert list(catalog) == sorted(catalog)
    for request, data in catalog.items():
        assert request.startswith("Request")
        assert data["response"].startswith("Response")
        assert data["direction"] == "client_to_server"
        assert data["status"] in {"verified", "observed", "inferred", "unknown"}
        assert isinstance(data["body_fields"], list)
        assert isinstance(data["base64_fields"], list)


def test_unknown_enum_catalog_never_assigns_meaning_without_evidence():
    catalog = load_json("unknown-enums.json")
    for enum in catalog.values():
        assert enum["status"] in {"verified", "partial", "unknown"}
        for value in enum["values"]:
            assert value["evidence"] in {
                "observed",
                "observed_and_live_verified",
                "rules_data_and_live_verified",
            }

"""Compare archived evidence without inventing prices, identities or removals."""

import json

import pytest

from comparison import compare_observations
from tests.test_history import manifest, product
from tests.test_run_inspector import invoke


@pytest.mark.parametrize(
    "old_price,new_price,currency,delta,percent",
    [
        (10, 12, "EUR", 2, 20),
        (0, 12, "EUR", 12, None),
        (12, 0, "EUR", -12, -100),
        (12, None, "EUR", None, None),
        (None, 12, "EUR", None, None),
        (12, 12, "USD", None, None),
        (0.1, 0.3, "EUR", 0.2, 200),
    ],
)
def test_price_transitions(old_price, new_price, currency, delta, percent):
    result = compare_observations(
        manifest(),
        manifest("new"),
        [product(price=old_price)],
        [product(price=new_price, currency=currency)],
    )
    change = result["changes"][0]["changes"]["price"]
    assert change["old"]["value"] == old_price
    assert change["new"]["value"] == new_price
    assert change["delta"] == delta and change["percent"] == percent


def test_partial_runs_compare_common_keys_and_keep_one_sided_observations(db_manager):
    old = [
        product(),
        product(source_id="only-old"),
        product(source_id=None, product_url=None),
    ]
    new = [
        product("new", name="Renamed", availability="Unknown", price=None),
        product("new", source_id="only-new"),
        product(
            "new",
            source_id=None,
            product_url=None,
            source_key="legacy:7",
            identity_kind="legacy",
        ),
    ]
    db_manager.save_collection(old, manifest(products_accepted=3))
    db_manager.save_collection(
        new, manifest("new", status="partial", products_accepted=3)
    )
    response = invoke(db_manager, ["compare-runs", "run-1", "new"])
    assert response.exit_code == 0, response.output
    result = json.loads(response.stdout)
    assert result["summary"] == {
        "matched": 1,
        "changed": 1,
        "unchanged": 0,
        "only_in_old": 1,
        "only_in_new": 1,
        "excluded_old": 1,
        "excluded_new": 1,
    }
    assert result["new_run"]["status"] == "partial"
    assert any("incomplete" in message for message in result["warnings"])
    changes = result["changes"][0]["changes"]
    assert changes["name"] == {"old": "Original title", "new": "Renamed"}
    assert changes["availability"] == {"old": "In Stock", "new": "Unknown"}
    assert changes["price"]["delta"] is None
    assert result["only_in_old"][0]["availability"] == "In Stock"
    assert len(db_manager.get_all_products()) == 5


def test_identical_run_is_unchanged_and_missing_history_is_an_error(db_manager):
    db_manager.save_collection([product()], manifest())
    result = invoke(db_manager, ["compare-runs", "run-1", "run-1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["summary"]["unchanged"] == 1
    db_manager.save_run(manifest("legacy"))
    for missing in ("legacy", "missing"):
        result = invoke(db_manager, ["compare-runs", "run-1", missing])
        assert result.exit_code == 1
        assert "history" in result.output or "not found" in result.output


def test_empty_different_scope_and_unknown_evidence_remain_explicit():
    result = compare_observations(
        manifest(scope={"description": "page 1"}),
        manifest("new", status="empty", scope={"description": "page 2"}),
        [product()],
        [],
    )
    assert result["changes"] == []
    assert result["summary"]["only_in_old"] == 1
    assert any(
        "different collection scopes" in message for message in result["warnings"]
    )
    result = compare_observations(
        manifest(),
        manifest("new"),
        [product(price=None, price_status="missing")],
        [product(price=None, price_status="unsupported")],
    )
    assert result["changes"][0]["changes"]["price"]["delta"] is None


def test_equal_names_do_not_match_different_sources_and_url_identities_do_match():
    result = compare_observations(
        manifest(),
        manifest("new"),
        [product()],
        [product(source_url="https://another.test/products")],
    )
    assert result["summary"]["matched"] == 0
    old = product(source_id=None)
    new = product(source_id=None, price=15)
    result = compare_observations(manifest(), manifest("new"), [old], [new])
    assert result["summary"]["changed"] == 1

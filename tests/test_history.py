"""Immutable collection evidence and transactional catalog/history persistence."""

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database import DatabaseManager
from models import CollectionRun, Product, ProductObservation


def manifest(run_id="run-1", **overrides):
    return {
        "run_id": run_id,
        "started_at": "2026-09-08T10:00:00Z",
        "status": "complete",
        "products_accepted": 1,
        **overrides,
    }


def product(run_id="run-1", **overrides):
    return Product(
        **{
            "name": "Original title",
            "source_id": "same",
            "source_url": "https://source.test/products?page=1",
            "product_url": "https://source.test/products/same",
            "price": 12.5,
            "price_raw": "12,50 €",
            "availability": "In Stock",
            "availability_raw": "Available now",
            "availability_reason": "dedicated_signal",
            "image_url": "https://source.test/image.png",
            "category": "Games",
            "rating": 4.5,
            "last_run_id": run_id,
            "scraped_at": datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
            **overrides,
        }
    )


def test_later_catalog_updates_preserve_full_original_evidence(db_manager):
    first = product()
    second = product(
        "run-2",
        name="Renamed title",
        price=None,
        price_raw="Ask for price",
        price_status="unsupported",
        availability="Out of Stock",
        availability_raw="Sold out",
        source_url="https://source.test/products?page=2",
        scraped_at=datetime(2026, 9, 9, 10, tzinfo=timezone.utc),
    )
    db_manager.save_collection([first], manifest())
    db_manager.save_collection(
        [second], manifest("run-2", started_at="2026-09-09T10:00:00Z")
    )

    current = db_manager.get_all_products()
    assert len(current) == 1
    assert current[0].name == second.name
    assert current[0].price is None
    for run_id, expected in [("run-1", first), ("run-2", second)]:
        saved = db_manager.get_run_products(run_id)
        assert len(saved) == 1
        assert saved[0].model_dump(mode="json") == expected.model_dump(mode="json")
        assert saved[0].scraped_at.utcoffset().total_seconds() == 0
    assert db_manager.get_run("run-1")["history_version"] == 1


def test_archive_preserves_input_order_and_distinct_unknown_and_free_prices(db_manager):
    products = [
        product(source_id="z", price=None, price_status="missing", price_raw=None),
        product(source_id="a", price=0, price_raw="0,00 €"),
    ]
    db_manager.save_collection(products, manifest(products_accepted=2))
    saved = db_manager.get_run_products("run-1")
    assert [item.source_id for item in saved] == ["z", "a"]
    assert [item.price for item in saved] == [None, 0]
    assert [item.price_status for item in saved] == ["missing", "known"]


def test_identical_old_retry_never_rewinds_current_catalog(db_manager):
    first = product()
    first_manifest = manifest()
    db_manager.save_collection([first], first_manifest)
    second = product("run-2", name="Latest title", price=50)
    db_manager.save_collection(
        [second], manifest("run-2", started_at="2026-09-09T10:00:00Z")
    )

    # Key ordering is irrelevant, and callers can pass the archived manifest back.
    archived = db_manager.get_run("run-1")
    db_manager.save_collection([first], dict(reversed(list(archived.items()))))
    db_manager.save_run(archived)
    assert db_manager.get_all_products()[0].name == "Latest title"
    assert len(db_manager.list_runs()) == 2
    assert db_manager.get_run_products("run-1")[0].price == 12.5
    assert "history_version" not in first_manifest


@pytest.mark.parametrize(
    "newer_time, older_time",
    [
        ("2026-09-08T10:30:00+00:00", "2026-09-08T12:00:00+02:00"),
        ("2026-09-08T09:30:00-02:00", "2026-09-08T10:30:00+00:00"),
    ],
)
def test_older_collection_finishing_later_archives_without_rewinding_catalog(
    db_manager, newer_time, older_time
):
    newer = product(
        "newer",
        name="Current title",
        price=50,
        scraped_at=datetime.fromisoformat(newer_time),
    )
    older = product("older", scraped_at=datetime.fromisoformat(older_time))
    previously_unseen = product(
        "older", source_id="only-in-older", scraped_at=older.scraped_at
    )
    db_manager.save_collection([newer], manifest("newer", started_at=newer_time))
    db_manager.save_collection(
        [older, previously_unseen],
        manifest("older", started_at=older_time, products_accepted=2),
    )

    catalog = {item.source_id: item for item in db_manager.get_all_products()}
    assert len(catalog) == 2
    assert catalog["same"].name == newer.name
    assert catalog["same"].price == 50
    assert catalog["same"].last_run_id == "newer"
    assert catalog["same"].scraped_at == newer.scraped_at.astimezone(timezone.utc)
    assert catalog["same"].scraped_at.tzinfo == timezone.utc
    assert catalog["only-in-older"].last_run_id == "older"
    assert db_manager.get_latest_run()["run_id"] == "newer"
    assert db_manager.get_run("older")["products_accepted"] == 2
    assert [
        item.model_dump(mode="json") for item in db_manager.get_run_products("older")
    ] == [
        older.model_dump(mode="json"),
        previously_unseen.model_dump(mode="json"),
    ]
    assert newer.scraped_at.isoformat() == newer_time


def test_equal_observation_instants_keep_last_write_wins_across_offsets(db_manager):
    first = product(scraped_at=datetime.fromisoformat("2026-09-08T10:00:00+00:00"))
    second = product(
        "run-2",
        price=99,
        scraped_at=datetime.fromisoformat("2026-09-08T12:00:00+02:00"),
    )
    db_manager.save_collection([first], manifest())
    db_manager.save_collection([second], manifest("run-2"))
    saved = db_manager.get_all_products()[0]
    assert saved.price == 99
    assert saved.last_run_id == "run-2"
    assert saved.scraped_at == first.scraped_at
    assert db_manager.get_run_products("run-1")[0].price == 12.5
    assert (
        db_manager.get_run_products("run-2")[0]
        .scraped_at.isoformat()
        .endswith("+02:00")
    )


@pytest.mark.parametrize("count", [0, 2, True])
def test_archive_cannot_claim_an_incorrect_accepted_count(db_manager, count):
    with pytest.raises(ValueError, match="products_accepted"):
        db_manager.save_collection([product()], manifest(products_accepted=count))
    assert db_manager.get_run("run-1") is None
    assert db_manager.get_all_products() == []


@pytest.mark.parametrize("changed", ["product", "manifest", "omitted_product"])
def test_conflicting_retry_rejected_without_changing_evidence(db_manager, changed):
    original = product()
    db_manager.save_collection([original], manifest())
    products = [product(price=99)] if changed == "product" else [original]
    if changed == "omitted_product":
        products = []
    attempted_manifest = (
        manifest(status="partial") if changed == "manifest" else manifest()
    )

    with pytest.raises(ValueError, match="immutable"):
        db_manager.save_collection(products, attempted_manifest)

    assert db_manager.get_all_products()[0].price == 12.5
    assert db_manager.get_run_products("run-1")[0].price == 12.5
    assert db_manager.get_run("run-1")["status"] == "complete"
    assert len(db_manager.list_runs()) == 1


def test_database_failure_rolls_back_catalog_run_and_observations(db_manager):
    db_manager.save_collection([product()], manifest())
    with db_manager.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER reject_new_observation BEFORE INSERT ON productobservation "
            "WHEN NEW.source_key = 'source.test:id:reject' "
            "BEGIN SELECT RAISE(ABORT, 'injected observation failure'); END"
        )
    attempted = [
        product("run-2", name="Changed", price=99),
        product("run-2", source_id="reject", name="Never saved"),
    ]
    with pytest.raises(IntegrityError, match="injected observation failure"):
        db_manager.save_collection(attempted, manifest("run-2", products_accepted=2))

    assert db_manager.get_run("run-2") is None
    assert [item.name for item in db_manager.get_all_products()] == ["Original title"]
    with Session(db_manager.engine) as session:
        observations = session.exec(select(ProductObservation)).all()
        assert [row.run_id for row in observations] == ["run-1"]
    assert db_manager.get_run_products("run-1")[0].price == 12.5


def test_invalid_json_and_duplicate_identities_cannot_partially_save(db_manager):
    db_manager.save_collection([product()], manifest())
    with pytest.raises(ValueError, match="JSON"):
        db_manager.save_collection(
            [product(price=99)], manifest("run-2", score=float("nan"))
        )
    with pytest.raises(ValueError, match="duplicate source keys"):
        db_manager.save_collection(
            [product(price=99), product(price=100)], manifest("run-2")
        )
    assert db_manager.get_run("run-2") is None
    assert db_manager.get_all_products()[0].price == 12.5


def test_empty_history_is_distinguishable_from_missing_and_legacy_runs(db_manager):
    assert db_manager.get_run("missing") is None
    with pytest.raises(ValueError, match="not found"):
        db_manager.get_run_products("missing")
    db_manager.save_run(manifest("legacy", status="empty", products_accepted=0))
    with pytest.raises(ValueError, match="no supported observation history"):
        db_manager.get_run_products("legacy")
    db_manager.save_collection(
        [], manifest("empty", status="empty", products_accepted=0)
    )
    assert db_manager.get_run_products("empty") == []
    db_manager.save_collection(
        [], manifest("empty", status="empty", products_accepted=0)
    )
    assert db_manager.get_all_products() == []
    with pytest.raises(ValueError, match="immutable"):
        db_manager.save_collection(
            [], manifest("legacy", status="empty", products_accepted=0)
        )


def test_manifest_only_api_cannot_mutate_or_falsely_mark_archives(db_manager):
    archived = manifest(history_version=1)
    with pytest.raises(ValueError, match="save_collection"):
        db_manager.save_run(archived)
    db_manager.save_collection([product()], manifest())
    with pytest.raises(ValueError, match="immutable"):
        db_manager.save_run(manifest(status="failed"))
    assert db_manager.get_run("run-1") == archived
    db_manager.save_run(manifest("legacy"))
    with pytest.raises(ValueError, match="immutable"):
        db_manager.save_run(manifest("legacy", status="failed"))


def test_conflicting_product_provenance_is_rejected_before_writes(db_manager):
    with pytest.raises(ValueError, match="last_run_id"):
        db_manager.save_collection([product("other-run")], manifest())
    assert db_manager.list_runs() == []
    assert db_manager.get_all_products() == []


def test_unstamped_product_retains_original_snapshot_and_run_link(db_manager):
    original = product(last_run_id=None)
    db_manager.save_collection([original], manifest())
    assert db_manager.get_run_products("run-1")[0].last_run_id is None
    assert original.last_run_id is None


def test_list_runs_is_bounded_newest_first_and_uses_utc_instants(db_manager):
    db_manager.save_collection(
        [],
        manifest("older", started_at="2026-09-08T12:00:00+02:00", products_accepted=0),
    )
    db_manager.save_collection(
        [], manifest("newer", started_at="2026-09-08T11:00:00Z", products_accepted=0)
    )
    assert [run["run_id"] for run in db_manager.list_runs()] == ["newer", "older"]
    assert db_manager.list_runs(limit=1) == [db_manager.get_run("newer")]
    assert db_manager.get_latest_run() == db_manager.get_run("newer")
    with pytest.raises(ValueError, match="at least 1"):
        db_manager.list_runs(limit=0)


def test_existing_database_gets_additive_history_without_fabricated_snapshots(tmp_path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'pre-history.db'}")
    try:
        getattr(Product, "__table__").create(db.engine)
        getattr(CollectionRun, "__table__").create(db.engine)
        db.save_products([product()])
        db.save_run(manifest("legacy"))
        with db.engine.connect() as connection:
            old_catalog = connection.execute(text("SELECT * FROM product")).all()
            old_runs = connection.execute(text("SELECT * FROM collectionrun")).all()
        assert not inspect(db.engine).has_table("productobservation")

        db.init_db()
        db.init_db()

        assert inspect(db.engine).has_table("productobservation")
        with db.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT * FROM product")).all() == old_catalog
            )
            assert (
                connection.execute(text("SELECT * FROM collectionrun")).all()
                == old_runs
            )
            assert (
                connection.execute(text("SELECT * FROM productobservation")).all() == []
            )
        with pytest.raises(ValueError, match="no supported observation history"):
            db.get_run_products("legacy")
        db.save_collection([product("new", price=20)], manifest("new"))
        assert db.get_run_products("new")[0].price == 20
    finally:
        db.close()


def test_concurrent_identical_retries_archive_only_once(tmp_path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'concurrent-history.db'}")
    try:
        db.init_db()
        observed = product()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(db.save_collection, [observed], manifest())
                for _ in range(2)
            ]
            for future in futures:
                future.result()
        assert len(db.list_runs()) == 1
        assert len(db.get_all_products()) == 1
        assert len(db.get_run_products("run-1")) == 1
        with Session(db.engine) as session:
            stored = session.exec(select(ProductObservation)).one()
            assert json.loads(stored.snapshot_json) == observed.model_dump(mode="json")
    finally:
        db.close()


@pytest.mark.parametrize("consumer", ["snapshot", "export"])
def test_catalog_and_metadata_share_snapshot_during_concurrent_collection(
    tmp_path, consumer
):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'snapshot.db'}")
    first_read = Event()
    writer_finished = Event()
    try:
        db.init_db()
        with db.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        db.save_collection([product()], manifest())

        def save_newer_collection():
            try:
                assert first_read.wait(timeout=30), "Catalog reader never started"
                db.save_collection(
                    [product("run-2", name="New title", price=99)],
                    manifest("run-2", started_at="2026-09-09T10:00:00Z"),
                )
            finally:
                writer_finished.set()

        def after_query(
            connection, cursor, statement, parameters, context, executemany
        ):
            if statement.startswith("SELECT product.") and not first_read.is_set():
                first_read.set()
                assert writer_finished.wait(
                    timeout=30
                ), "Concurrent writer did not finish"

        with ThreadPoolExecutor(max_workers=1) as pool:
            writer = pool.submit(save_newer_collection)
            event.listen(db.engine, "after_cursor_execute", after_query)
            try:
                if consumer == "snapshot":
                    saved_products, saved_manifest = db.get_catalog_snapshot()
                    assert [item.name for item in saved_products] == ["Original title"]
                    assert saved_manifest["run_id"] == "run-1"
                else:
                    destination = tmp_path / "catalog.csv"
                    assert db.export_for_powerbi(str(destination)) is True
                    with destination.open(encoding="utf-8-sig", newline="") as stream:
                        rows = list(csv.DictReader(stream))
                    assert [row["name"] for row in rows] == ["Original title"]
                    metadata = json.loads(
                        destination.with_suffix(".manifest.json").read_text()
                    )
                    assert metadata["latest_collection"]["run_id"] == "run-1"
            finally:
                first_read.set()
                event.remove(db.engine, "after_cursor_execute", after_query)
            writer.result()
        assert db.get_all_products()[0].name == "New title"
        assert db.get_latest_run()["run_id"] == "run-2"
    finally:
        db.close()

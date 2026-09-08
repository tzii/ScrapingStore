"""SQLite persistence for the current catalog and immutable collection evidence."""

import json
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import Connection, inspect, text
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, SQLModel, create_engine, select, col

from config import DB_URL, CSV_POWERBI_PATH
from models import Product, CollectionRun, ProductObservation
from logger import get_logger

logger = get_logger(__name__)

HISTORY_VERSION = 1


def _json(value: Any) -> str:
    """Stable serialization makes identical retries independent of dictionary order."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


class DatabaseManager:
    def __init__(self, db_url: str = DB_URL):
        self.engine = create_engine(db_url)

    def init_db(self):
        inspector = inspect(self.engine)
        if inspector.has_table("product"):
            columns = {
                column["name"]: column for column in inspector.get_columns("product")
            }
            if "source_key" not in columns or not columns["price"]["nullable"]:
                self._migrate_legacy_catalog()
        SQLModel.metadata.create_all(self.engine)

    def _migrate_legacy_catalog(self) -> None:
        """Keep the original table intact as a backup; migrate atomically in SQLite."""
        if self.engine.dialect.name != "sqlite":
            raise RuntimeError(
                "Automatic legacy migration is supported only for SQLite"
            )
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            if inspect(connection).has_table("product_legacy_v1"):
                raise RuntimeError(
                    "Legacy backup already exists; refusing to overwrite it"
                )
            rows = connection.execute(text("SELECT * FROM product")).mappings().all()
            products = []
            for row in rows:
                values = dict(row)
                # Historical zero may mean a failed extraction. Its meaning is unknown.
                if not values.get("price"):
                    values["price"] = None
                    values["price_status"] = "legacy_unknown"
                values.update(
                    source_key=f"legacy:{values['id']}",
                    identity_kind="legacy",
                    parser_version="legacy",
                )
                products.append(Product.model_validate(values).model_dump())
            connection.exec_driver_sql(
                "ALTER TABLE product RENAME TO product_legacy_v1"
            )
            SQLModel.metadata.create_all(connection)
            if products:
                connection.execute(getattr(Product, "__table__").insert(), products)
        logger.info("Migrated catalog; original rows retained in product_legacy_v1")

    def save_products(self, products: List[Product]):
        if not products:
            return
        with self.engine.begin() as connection:
            self._upsert_products(connection, products)
        logger.info(f"Saved {len(products)} product observations by source identity")

    @staticmethod
    def _upsert_products(connection: Connection, products: List[Product]) -> None:
        for product in products:
            values = product.model_dump(exclude={"id"})
            # Compare instants in UTC because SQLite discards datetime offsets.
            values["scraped_at"] = (
                product.scraped_at.replace(tzinfo=timezone.utc)
                if product.scraped_at.tzinfo is None
                else product.scraped_at.astimezone(timezone.utc)
            )
            statement = insert(Product).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["source_key"],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in values
                    if key != "source_key"
                },
                # Late collection completion must not overwrite a newer observation.
                # Equal timestamps retain last-write-wins behavior.
                where=col(Product.scraped_at) <= statement.excluded.scraped_at,
            )
            connection.execute(statement)

    @staticmethod
    def _run_record(manifest: Dict[str, Any]) -> CollectionRun:
        record = CollectionRun.model_validate(
            {
                "id": manifest["run_id"],
                "started_at": manifest["started_at"],
                "manifest_json": _json(manifest),
            }
        )
        # SQLite drops timezone offsets; store the UTC instant for chronological reads.
        record.started_at = (
            record.started_at.replace(tzinfo=timezone.utc)
            if record.started_at.tzinfo is None
            else record.started_at.astimezone(timezone.utc)
        )
        return record

    def _lock_collection_write(self, connection: Connection) -> None:
        if self.engine.dialect.name == "sqlite":
            # Serialize the immutable-run check with its writes, including concurrent retries.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    def save_collection(
        self, products: List[Product], manifest: Dict[str, Any]
    ) -> None:
        """Atomically archive a run and its products, then update the current catalog.

        An identical retry is a no-op, even after a later run changed the catalog.
        Reusing a run ID with different evidence is rejected without any writes.
        All accepted products are archived; only observations at least as recent as
        the current product update the catalog. products_accepted counts the archive.
        """
        version = manifest.get("history_version", HISTORY_VERSION)
        if type(version) is not int or version != HISTORY_VERSION:
            raise ValueError(f"Unsupported observation history version: {version!r}")
        archived_manifest = {**manifest, "history_version": HISTORY_VERSION}
        record = self._run_record(archived_manifest)
        observations = [
            {
                "run_id": record.id,
                "source_key": product.source_key,
                "position": position,
                "snapshot_json": _json(product.model_dump(mode="json")),
            }
            for position, product in enumerate(products)
        ]
        if len({row["source_key"] for row in observations}) != len(observations):
            raise ValueError("A collection cannot contain duplicate source keys")
        if any(product.last_run_id not in (None, record.id) for product in products):
            raise ValueError("Product last_run_id does not match the collection run")

        run_table = getattr(CollectionRun, "__table__")
        observation_table = getattr(ProductObservation, "__table__")
        with self.engine.begin() as connection:
            self._lock_collection_write(connection)
            existing = connection.execute(
                select(run_table.c.manifest_json).where(run_table.c.id == record.id)
            ).scalar_one_or_none()
            if existing is not None:
                saved_observations = (
                    connection.execute(
                        select(observation_table)
                        .where(observation_table.c.run_id == record.id)
                        .order_by(observation_table.c.position)
                    )
                    .mappings()
                    .all()
                )
                if (
                    _json(json.loads(existing)) != record.manifest_json
                    or [dict(row) for row in saved_observations] != observations
                ):
                    raise ValueError(f"Collection run {record.id!r} is immutable")
                return

            if "products_accepted" in manifest and (
                type(manifest["products_accepted"]) is not int
                or manifest["products_accepted"] != len(observations)
            ):
                raise ValueError(
                    "products_accepted must equal the number of archived observations"
                )
            connection.execute(run_table.insert(), record.model_dump())
            self._upsert_products(connection, products)
            if observations:
                connection.execute(observation_table.insert(), observations)
        logger.info(
            f"Archived collection {record.id} with {len(products)} observations"
        )

    def save_run(self, manifest: Dict[str, Any]) -> None:
        """Save legacy manifest-only evidence without modifying an existing run."""
        record = self._run_record(manifest)
        run_table = getattr(CollectionRun, "__table__")
        with self.engine.begin() as connection:
            self._lock_collection_write(connection)
            existing = connection.execute(
                select(run_table.c.manifest_json).where(run_table.c.id == record.id)
            ).scalar_one_or_none()
            if existing is not None:
                if _json(json.loads(existing)) != record.manifest_json:
                    raise ValueError(f"Collection run {record.id!r} is immutable")
                return
            if "history_version" in manifest:
                raise ValueError("Use save_collection to archive observation history")
            connection.execute(run_table.insert(), record.model_dump())

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with Session(self.engine) as session:
            record = session.get(CollectionRun, run_id)
            return json.loads(record.manifest_json) if record else None

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        if limit < 1:
            raise ValueError("Run limit must be at least 1")
        with Session(self.engine) as session:
            records = session.exec(
                select(CollectionRun)
                .order_by(
                    col(CollectionRun.started_at).desc(), col(CollectionRun.id).desc()
                )
                .limit(limit)
            ).all()
            return [json.loads(record.manifest_json) for record in records]

    def get_run_products(self, run_id: str) -> List[Product]:
        with Session(self.engine) as session:
            record = session.get(CollectionRun, run_id)
            if record is None:
                raise ValueError(f"Collection run {run_id!r} was not found")
            manifest = json.loads(record.manifest_json)
            if manifest.get("history_version") != HISTORY_VERSION:
                raise ValueError(
                    f"Collection run {run_id!r} has no supported observation history"
                )
            observations = session.exec(
                select(ProductObservation)
                .where(ProductObservation.run_id == run_id)
                .order_by(col(ProductObservation.position))
            ).all()
            return [
                Product.model_validate(json.loads(row.snapshot_json))
                for row in observations
            ]

    def get_latest_run(self) -> Optional[Dict[str, Any]]:
        runs = self.list_runs(limit=1)
        return runs[0] if runs else None

    def get_all_products(self) -> List[Product]:
        with Session(self.engine) as session:
            return self._read_products(session)

    @staticmethod
    def _read_products(session: Session) -> List[Product]:
        products = list(session.exec(select(Product).order_by(col(Product.id))).all())
        for product in products:
            if product.scraped_at.tzinfo is None:
                product.scraped_at = product.scraped_at.replace(tzinfo=timezone.utc)
        return products

    def get_catalog_snapshot(
        self,
    ) -> Tuple[List[Product], Optional[Dict[str, Any]]]:
        """Read catalog data and its latest run metadata from one database snapshot."""
        with Session(self.engine) as session, session.begin():
            if self.engine.dialect.name == "sqlite":
                # Pysqlite does not begin a physical transaction for SELECT alone.
                session.connection().exec_driver_sql("BEGIN")
            products = self._read_products(session)
            # UTC restoration is for readers; never flush it back during the next
            # SELECT, and keep products readable after the read transaction closes.
            for product in products:
                session.expunge(product)
            record = session.exec(
                select(CollectionRun)
                .order_by(
                    col(CollectionRun.started_at).desc(), col(CollectionRun.id).desc()
                )
                .limit(1)
            ).first()
            latest_run = json.loads(record.manifest_json) if record else None
            return products, latest_run

    def get_products_df(self) -> pd.DataFrame:
        return pd.DataFrame([p.model_dump() for p in self.get_all_products()])

    def export_for_powerbi(self, output_path: str = str(CSV_POWERBI_PATH)) -> bool:
        products, latest_run = self.get_catalog_snapshot()
        df = pd.DataFrame([product.model_dump() for product in products])
        if df.empty:
            logger.warning("No data to export")
            return False
        df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True).dt.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(destination, index=False, encoding="utf-8-sig", na_rep="")
        metadata = {
            "scope": "Current stored catalog",
            "latest_collection": latest_run,
        }
        destination.with_suffix(".manifest.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        return True

    def close(self) -> None:
        self.engine.dispose()

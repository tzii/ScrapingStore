"""SQLite ledger persistence for catalog state, immutable runs, pages, and raw HTML blobs."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import Connection, inspect, text
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, SQLModel, col, create_engine, select

from scrapingstore.config import get_settings
from scrapingstore.io_utils import (
    as_utc,
    atomic_write_text,
    escape_csv_cell,
    stable_json,
)
from scrapingstore.ledger.models import (
    CollectionRun,
    PageRecord,
    Product,
    ProductObservation,
    RawPageBlob,
    price_to_minor,
)
from scrapingstore.logger import get_logger

logger = get_logger(__name__)

HISTORY_VERSION = 1

_EXPORT_COLUMNS = (
    "id",
    "name",
    "price",
    "price_minor",
    "price_raw",
    "price_status",
    "currency",
    "availability",
    "availability_raw",
    "availability_reason",
    "image_url",
    "source_url",
    "source_id",
    "product_url",
    "source_key",
    "identity_kind",
    "parser_version",
    "last_run_id",
    "scraped_at",
    "category",
    "rating",
)


def _table(model: Any) -> Any:
    return model.__table__


def _short_run_id(run_id: str) -> str:
    clean = run_id.replace("-", "")
    return clean[:8] if len(clean) >= 8 else clean


def _parse_iso_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return as_utc(raw)
    text_val = str(raw).strip()
    if not text_val:
        return None
    if text_val.endswith("Z"):
        text_val = text_val[:-1] + "+00:00"
    return as_utc(datetime.fromisoformat(text_val))


class DatabaseManager:
    """Transactional SQLite manager for ScrapingStore's observation ledger."""

    def __init__(self, db_url: Optional[str] = None):
        if db_url is None:
            settings = get_settings()
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            db_url = settings.db_url
        elif db_url.startswith("sqlite:///") and db_url != "sqlite://":
            db_file = Path(db_url.removeprefix("sqlite:///"))
            if str(db_file) != ":memory:":
                db_file.parent.mkdir(parents=True, exist_ok=True)
        self.db_url = db_url
        self.engine = create_engine(db_url)

    def init_db(self) -> None:
        inspector = inspect(self.engine)
        if inspector.has_table("product"):
            columns = {c["name"]: c for c in inspector.get_columns("product")}
            if "source_key" not in columns or not columns["price"]["nullable"]:
                self._migrate_legacy_catalog()
            else:
                self._ensure_additive_columns()
        SQLModel.metadata.create_all(self.engine)
        self._ensure_additive_columns()

    def _ensure_additive_columns(self) -> None:
        """Add new v3 typed columns to existing v2 SQLite tables without losing data."""
        if self.engine.dialect.name != "sqlite":
            return
        additions: Dict[str, List[Tuple[str, str]]] = {
            "product": [("price_minor", "INTEGER")],
            "collectionrun": [
                ("short_id", "VARCHAR DEFAULT ''"),
                ("finished_at", "DATETIME"),
                ("status", "VARCHAR DEFAULT 'unknown'"),
                ("source_name", "VARCHAR DEFAULT 'oxylabs'"),
                ("scraper_type", "VARCHAR DEFAULT 'unknown'"),
                ("stop_reason", "VARCHAR DEFAULT 'unknown'"),
                ("pages_attempted", "INTEGER DEFAULT 0"),
                ("pages_succeeded", "INTEGER DEFAULT 0"),
                ("pages_failed", "INTEGER DEFAULT 0"),
                ("products_accepted", "INTEGER DEFAULT 0"),
                ("parser_version", "VARCHAR DEFAULT '2.0'"),
                ("history_version", "INTEGER DEFAULT 0"),
            ],
            "productobservation": [
                ("name", "VARCHAR DEFAULT ''"),
                ("price_minor", "INTEGER"),
                ("currency", "VARCHAR DEFAULT 'EUR'"),
                ("price_status", "VARCHAR DEFAULT 'missing'"),
                ("availability", "VARCHAR DEFAULT 'Unknown'"),
                ("category", "VARCHAR"),
                ("rating", "FLOAT"),
                ("image_url", "VARCHAR"),
                ("product_url", "VARCHAR"),
                ("identity_kind", "VARCHAR DEFAULT 'weak'"),
                ("parser_version", "VARCHAR DEFAULT '2.0'"),
                ("scraped_at", "DATETIME"),
            ],
        }
        with self.engine.begin() as connection:
            inspector = inspect(connection)
            for table, cols in additions.items():
                if not inspector.has_table(table):
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                for col_name, col_type in cols:
                    if col_name not in existing:
                        connection.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                        )
            # Backfill price_minor on migrated v2 product rows if NULL where price exists
            if inspector.has_table("product"):
                rows = connection.execute(
                    text(
                        "SELECT id, price FROM product "
                        "WHERE price IS NOT NULL AND price_minor IS NULL"
                    )
                ).all()
                for row_id, price in rows:
                    connection.execute(
                        text("UPDATE product SET price_minor = :m WHERE id = :i"),
                        {"m": price_to_minor(price), "i": row_id},
                    )
            if inspector.has_table("collectionrun"):
                run_rows = connection.execute(
                    text(
                        "SELECT id, manifest_json FROM collectionrun "
                        "WHERE short_id IS NULL OR short_id = ''"
                    )
                ).all()
                for run_id, manifest_json in run_rows:
                    manifest = json.loads(manifest_json)
                    connection.execute(
                        text(
                            "UPDATE collectionrun SET short_id = :sid, status = :st, "
                            "scraper_type = :sc, stop_reason = :sr, "
                            "products_accepted = :pa, history_version = :hv "
                            "WHERE id = :id"
                        ),
                        {
                            "sid": _short_run_id(run_id),
                            "st": manifest.get("status", "unknown"),
                            "sc": manifest.get("scraper_type", "unknown"),
                            "sr": manifest.get("stop_reason", "unknown"),
                            "pa": int(manifest.get("products_accepted", 0) or 0),
                            "hv": int(manifest.get("history_version", 0) or 0),
                            "id": run_id,
                        },
                    )

    def _migrate_legacy_catalog(self) -> None:
        """Keep the original v1 table intact as product_legacy_v1; migrate atomically."""
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
                if not values.get("price"):
                    values["price"] = None
                    values["price_minor"] = None
                    values["price_status"] = "legacy_unknown"
                values.update(
                    source_key=f"legacy:{values['id']}",
                    identity_kind="legacy",
                    parser_version="legacy",
                )
                product = Product.model_validate(values).model_dump()
                product["scraped_at"] = as_utc(product["scraped_at"])
                products.append(product)
            connection.exec_driver_sql(
                "ALTER TABLE product RENAME TO product_legacy_v1"
            )
            SQLModel.metadata.create_all(connection)
            if products:
                connection.execute(_table(Product).insert(), products)
        logger.info("Migrated catalog; original rows retained in product_legacy_v1")

    def save_products(self, products: List[Product]) -> None:
        if not products:
            return
        with self.engine.begin() as connection:
            self._upsert_products(connection, products)
        logger.info("Saved %d product observations by source identity", len(products))

    @staticmethod
    def _upsert_products(connection: Connection, products: Sequence[Product]) -> None:
        for product in products:
            values = product.model_dump(exclude={"id"})
            values["scraped_at"] = as_utc(product.scraped_at)
            statement = insert(Product).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["source_key"],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in values
                    if key != "source_key"
                },
                where=col(Product.scraped_at) <= statement.excluded.scraped_at,
            )
            connection.execute(statement)

    @staticmethod
    def _run_record(manifest: Dict[str, Any]) -> CollectionRun:
        run_id = str(manifest["run_id"])
        started = _parse_iso_dt(manifest["started_at"])
        if started is None:
            raise ValueError("Manifest missing valid started_at timestamp")
        finished = _parse_iso_dt(manifest.get("finished_at"))
        return CollectionRun(
            id=run_id,
            short_id=_short_run_id(run_id),
            started_at=started,
            finished_at=finished,
            status=str(manifest.get("status", "unknown")),
            source_name=str(manifest.get("source_name", "oxylabs")),
            scraper_type=str(manifest.get("scraper_type", "unknown")),
            stop_reason=str(manifest.get("stop_reason", "unknown")),
            pages_attempted=int(manifest.get("pages_attempted", 0) or 0),
            pages_succeeded=int(manifest.get("pages_succeeded", 0) or 0),
            pages_failed=int(manifest.get("pages_failed", 0) or 0),
            products_accepted=int(manifest.get("products_accepted", 0) or 0),
            parser_version=str(manifest.get("parser_version", "3.0")),
            history_version=int(manifest.get("history_version", 0) or 0),
            manifest_json=stable_json(manifest),
        )

    def _lock_collection_write(self, connection: Connection) -> None:
        if self.engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    def save_collection(
        self,
        products: List[Product],
        manifest: Dict[str, Any],
        *,
        raw_pages: Optional[Dict[int, bytes]] = None,
    ) -> None:
        """Atomically archive a run, its observations, typed pages, and raw HTML blobs."""
        version = manifest.get("history_version", HISTORY_VERSION)
        if type(version) is not int or version != HISTORY_VERSION:
            raise ValueError(f"Unsupported observation history version: {version!r}")
        archived_manifest = {**manifest, "history_version": HISTORY_VERSION}
        record = self._run_record(archived_manifest)

        observations = []
        for position, product in enumerate(products):
            observations.append(
                {
                    "run_id": record.id,
                    "source_key": product.source_key,
                    "position": position,
                    "name": product.name,
                    "price_minor": product.price_minor,
                    "currency": product.currency,
                    "price_status": product.price_status,
                    "availability": product.availability,
                    "category": product.category,
                    "rating": product.rating,
                    "image_url": product.image_url,
                    "product_url": product.product_url,
                    "identity_kind": product.identity_kind,
                    "parser_version": product.parser_version,
                    "scraped_at": as_utc(product.scraped_at),
                    "snapshot_json": stable_json(product.model_dump(mode="json")),
                }
            )

        if len({row["source_key"] for row in observations}) != len(observations):
            raise ValueError("A collection cannot contain duplicate source keys")
        if any(product.last_run_id not in (None, record.id) for product in products):
            raise ValueError("Product last_run_id does not match the collection run")

        # Prepare optional raw HTML blobs + typed PageRecord rows
        blobs_to_store: Dict[str, Tuple[bytes, int]] = {}
        page_sha_map: Dict[int, str] = {}
        if raw_pages:
            for page_num, raw_html in raw_pages.items():
                sha = hashlib.sha256(raw_html).hexdigest()
                page_sha_map[page_num] = sha
                if sha not in blobs_to_store:
                    blobs_to_store[sha] = (gzip.compress(raw_html, compresslevel=6), len(raw_html))

        page_rows = []
        for page_dict in archived_manifest.get("pages", []) or []:
            page_num = int(page_dict["page"])
            blob_sha = page_sha_map.get(page_num) or page_dict.get("raw_blob_sha256")
            page_rows.append(
                {
                    "run_id": record.id,
                    "page_number": page_num,
                    "url": str(page_dict.get("url", "")),
                    "status": str(page_dict.get("status", "failed")),
                    "http_status": page_dict.get("http_status"),
                    "attempts": int(page_dict.get("attempts", 1) or 1),
                    "products_count": int(page_dict.get("products", 0) or 0),
                    "rejected_cards": int(page_dict.get("rejected_cards", 0) or 0),
                    "elapsed_ms": page_dict.get("elapsed_ms"),
                    "bytes_received": page_dict.get("bytes_received"),
                    "source_end": bool(page_dict.get("source_end", False)),
                    "outside_scope": bool(page_dict.get("outside_scope", False)),
                    "fingerprint": page_dict.get("fingerprint"),
                    "raw_blob_sha256": blob_sha,
                    "errors_json": stable_json(page_dict.get("errors", [])),
                }
            )

        run_table = _table(CollectionRun)
        observation_table = _table(ProductObservation)
        page_table = _table(PageRecord)

        with self.engine.begin() as connection:
            self._lock_collection_write(connection)
            existing = connection.execute(
                select(run_table.c.manifest_json).where(run_table.c.id == record.id)
            ).scalar_one_or_none()
            if existing is not None:
                saved_observations = (
                    connection.execute(
                        select(
                            observation_table.c.run_id,
                            observation_table.c.source_key,
                            observation_table.c.position,
                            observation_table.c.snapshot_json,
                        )
                        .where(observation_table.c.run_id == record.id)
                        .order_by(observation_table.c.position)
                    )
                    .mappings()
                    .all()
                )
                expected_core = [
                    {
                        "run_id": row["run_id"],
                        "source_key": row["source_key"],
                        "position": row["position"],
                        "snapshot_json": row["snapshot_json"],
                    }
                    for row in observations
                ]
                if (
                    stable_json(json.loads(existing)) != record.manifest_json
                    or [dict(row) for row in saved_observations] != expected_core
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

            for sha, (gz_bytes, raw_len) in blobs_to_store.items():
                stmt = insert(RawPageBlob).values(
                    sha256=sha,
                    content_gz=gz_bytes,
                    byte_length=raw_len,
                    created_at=as_utc(datetime.now(timezone.utc)),
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["sha256"])
                connection.execute(stmt)

            connection.execute(run_table.insert(), record.model_dump())
            self._upsert_products(connection, products)
            if observations:
                connection.execute(observation_table.insert(), observations)
            if page_rows:
                connection.execute(page_table.insert(), page_rows)

        logger.info(
            "Archived collection %s (%s) with %d observations",
            record.short_id,
            record.status,
            len(products),
        )

    def save_run(self, manifest: Dict[str, Any]) -> None:
        """Save legacy manifest-only evidence without modifying an existing run."""
        record = self._run_record(manifest)
        run_table = _table(CollectionRun)
        with self.engine.begin() as connection:
            self._lock_collection_write(connection)
            existing = connection.execute(
                select(run_table.c.manifest_json).where(run_table.c.id == record.id)
            ).scalar_one_or_none()
            if existing is not None:
                if stable_json(json.loads(existing)) != record.manifest_json:
                    raise ValueError(f"Collection run {record.id!r} is immutable")
                return
            if "history_version" in manifest:
                raise ValueError("Use save_collection to archive observation history")
            connection.execute(run_table.insert(), record.model_dump())

    def resolve_run_id(self, ref: str) -> str:
        """Resolve @latest, @prev, @~N, exact ID, or unique short prefix to a run_id."""
        ref = ref.strip()
        if not ref:
            raise ValueError("Run reference must not be empty")
        if ref in ("@latest", "latest", "@0", "HEAD"):
            runs = self.list_runs(limit=1)
            if not runs:
                raise ValueError("No saved collections available for @latest")
            return str(runs[0]["run_id"])
        if ref in ("@prev", "prev", "HEAD~1", "@~1"):
            runs = self.list_runs(limit=2)
            if len(runs) < 2:
                raise ValueError("Fewer than 2 saved collections available for @prev")
            return str(runs[1]["run_id"])
        if ref.startswith("@~") and ref[2:].isdigit():
            offset = int(ref[2:])
            runs = self.list_runs(limit=offset + 1)
            if len(runs) <= offset:
                raise ValueError(f"Collection {ref} does not exist")
            return str(runs[offset]["run_id"])

        with Session(self.engine) as session:
            exact = session.get(CollectionRun, ref)
            if exact is not None:
                return exact.id
            matches = session.exec(
                select(CollectionRun.id).where(
                    col(CollectionRun.id).startswith(ref)
                    | col(CollectionRun.short_id).startswith(ref)
                )
            ).all()
            if len(matches) == 1:
                return str(matches[0])
            if len(matches) > 1:
                raise ValueError(
                    f"Ambiguous run prefix {ref!r}; matches {', '.join(matches[:5])}"
                )
            raise ValueError(f"Collection run {ref!r} was not found")

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

    def get_run_pages(self, run_id: str) -> List[PageRecord]:
        with Session(self.engine) as session:
            return list(
                session.exec(
                    select(PageRecord)
                    .where(PageRecord.run_id == run_id)
                    .order_by(col(PageRecord.page_number))
                ).all()
            )

    def get_raw_blob(self, sha256: str) -> Optional[bytes]:
        with Session(self.engine) as session:
            blob = session.get(RawPageBlob, sha256)
            return gzip.decompress(blob.content_gz) if blob else None

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
                session.connection().exec_driver_sql("BEGIN")
            products = self._read_products(session)
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

    def get_multi_run_history(
        self, limit: int = 12
    ) -> List[Tuple[Dict[str, Any], List[Product]]]:
        """Return chronological (oldest -> newest) archived runs with their observations."""
        manifests = self.list_runs(limit=limit)
        archived = [m for m in manifests if m.get("history_version") == HISTORY_VERSION]
        archived.reverse()
        return [(m, self.get_run_products(m["run_id"])) for m in archived]

    def get_product_timeline(self, source_key: str) -> List[Dict[str, Any]]:
        """SQL-backed longitudinal timeline for one product key across all runs."""
        with Session(self.engine) as session:
            stmt = (
                select(ProductObservation, CollectionRun)
                .join(
                    CollectionRun,
                    col(ProductObservation.run_id) == col(CollectionRun.id),
                )
                .where(ProductObservation.source_key == source_key)
                .order_by(col(CollectionRun.started_at), col(CollectionRun.id))
            )
            rows = session.exec(stmt).all()
            timeline = []
            for obs, run in rows:
                data = json.loads(obs.snapshot_json)
                timeline.append(
                    {
                        "run_id": run.id,
                        "short_id": run.short_id or _short_run_id(run.id),
                        "run_status": run.status,
                        "started_at": as_utc(run.started_at).isoformat(),
                        "name": data.get("name", obs.name),
                        "price": data.get("price"),
                        "price_minor": obs.price_minor,
                        "price_status": data.get("price_status", obs.price_status),
                        "price_raw": data.get("price_raw"),
                        "currency": data.get("currency", obs.currency),
                        "availability": data.get("availability", obs.availability),
                        "availability_reason": data.get("availability_reason"),
                        "category": data.get("category", obs.category),
                        "image_url": data.get("image_url", obs.image_url),
                        "parser_version": data.get(
                            "parser_version", obs.parser_version
                        ),
                        "scraped_at": data.get("scraped_at"),
                    }
                )
            return timeline

    def blame_product(self, query: str) -> Dict[str, Any]:
        """Git-blame style provenance: find which run last changed each field of a SKU."""
        with Session(self.engine) as session:
            product = session.exec(
                select(Product).where(Product.source_key == query)
            ).first()
            if product is None:
                product = session.exec(
                    select(Product).where(col(Product.name).ilike(f"%{query}%"))
                ).first()
            if product is None:
                raise ValueError(f"No product matching {query!r} found in catalog")
            source_key = product.source_key

        timeline = self.get_product_timeline(source_key)
        fields = ("name", "price", "availability", "category", "image_url")
        blame: Dict[str, Dict[str, Any]] = {}
        for field in fields:
            last_entry = None
            prev_val = object()
            for entry in timeline:
                val = entry.get(field)
                if val != prev_val:
                    last_entry = {
                        "value": val,
                        "changed_in_run": entry["run_id"],
                        "short_id": entry["short_id"],
                        "observed_at": entry["scraped_at"] or entry["started_at"],
                        "parser_version": entry["parser_version"],
                    }
                    prev_val = val
            if last_entry is not None:
                blame[field] = last_entry
        return {
            "source_key": source_key,
            "name": product.name,
            "observations_count": len(timeline),
            "fields": blame,
            "timeline": timeline,
        }

    def get_products_df(self) -> Any:
        """Optional Pandas DataFrame helper for backwards compatibility."""
        import pandas as pd

        return pd.DataFrame([p.model_dump() for p in self.get_all_products()])

    def export_for_powerbi(self, output_path: Optional[str] = None) -> bool:
        """Export catalog to UTF-8 BOM CSV with formula-injection protection & atomic writes."""
        products, latest_run = self.get_catalog_snapshot()
        if not products:
            logger.warning("No data to export")
            return False

        destination = (
            Path(output_path) if output_path else get_settings().csv_powerbi_path
        )
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(_EXPORT_COLUMNS)
        for p in products:
            dumped = p.model_dump()
            dumped["scraped_at"] = as_utc(p.scraped_at).strftime("%Y-%m-%dT%H:%M:%SZ")
            row = []
            for col_name in _EXPORT_COLUMNS:
                val = dumped.get(col_name)
                if val is None:
                    row.append("")
                elif col_name in ("id", "price", "price_minor", "rating"):
                    row.append(str(val))
                else:
                    row.append(escape_csv_cell(val))
            writer.writerow(row)

        atomic_write_text(destination, "\ufeff" + buf.getvalue(), encoding="utf-8")
        metadata = {
            "scope": "Current stored catalog",
            "latest_collection": latest_run,
            "exported_rows": len(products),
        }
        atomic_write_text(
            destination.with_suffix(".manifest.json"),
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return True

    def close(self) -> None:
        self.engine.dispose()

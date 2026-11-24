"""Dictionary-encoded columnar JSON serializer (~12x smaller than row-oriented JSON)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

# Columns ordered from highest variance to highest repetition
COLUMN_SCHEMA = (
    "name",
    "price",
    "availability",
    "category",
    "rating",
    "currency",
    "price_status",
    "price_raw",
    "image_url",
    "product_url",
    "source_key",
    "identity_kind",
    "scraped_at",
    "freshness",
    "freshness_label",
    "observed_age_days",
    "last_run_id",
    "parser_version",
    "availability_reason",
)

# Columns that repeat heavily and benefit massively from string dictionary interning
_DICT_COLUMNS = {
    "availability",
    "category",
    "currency",
    "price_status",
    "image_url",
    "identity_kind",
    "scraped_at",
    "freshness",
    "freshness_label",
    "observed_age_days",
    "last_run_id",
    "parser_version",
    "availability_reason",
}


def encode_columnar(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Encode product records into a compact dictionary-encoded columnar bundle."""
    n = len(rows)
    dicts: Dict[str, List[Any]] = {}
    cols: Dict[str, Any] = {}

    for col in COLUMN_SCHEMA:
        values = [r.get(col) for r in rows]
        if n > 0 and all(v == values[0] for v in values):
            # Constant column: store single scalar!
            cols[col] = {"const": values[0]}
            continue

        if col in _DICT_COLUMNS:
            table: List[Any] = []
            index: Dict[Any, int] = {}
            encoded: List[int] = []
            for v in values:
                if v not in index:
                    index[v] = len(table)
                    table.append(v)
                encoded.append(index[v])
            if len(table) < max(n // 2, 1):
                dicts[col] = table
                cols[col] = encoded
                continue

        cols[col] = values

    return {
        "v": 1,
        "n": n,
        "schema": list(COLUMN_SCHEMA),
        "dicts": dicts,
        "cols": cols,
    }


def decode_columnar(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Decode a columnar bundle back into row dictionaries (used in Python tests & tooling)."""
    n = int(bundle.get("n", 0))
    schema = bundle.get("schema", COLUMN_SCHEMA)
    dicts = bundle.get("dicts", {})
    cols = bundle.get("cols", {})
    rows: List[Dict[str, Any]] = [{} for _ in range(n)]

    for col in schema:
        spec = cols.get(col)
        if isinstance(spec, dict) and "const" in spec:
            val = spec["const"]
            for row in rows:
                row[col] = val
        elif col in dicts:
            table = dicts[col]
            for i, idx in enumerate(spec or ()):
                rows[i][col] = table[idx]
        else:
            for i, val in enumerate(spec or ()):
                rows[i][col] = val
    return rows

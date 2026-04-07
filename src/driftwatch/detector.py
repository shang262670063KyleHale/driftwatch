"""Core schema drift detection logic for driftwatch.

This module compares database schema definitions extracted from migration files
against ORM model definitions to identify discrepancies (drift).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class DriftType(str, Enum):
    """Categories of schema drift that can be detected."""

    MISSING_TABLE = "missing_table"
    EXTRA_TABLE = "extra_table"
    MISSING_COLUMN = "missing_column"
    EXTRA_COLUMN = "extra_column"
    COLUMN_TYPE_MISMATCH = "column_type_mismatch"
    MISSING_INDEX = "missing_index"
    EXTRA_INDEX = "extra_index"


@dataclass
class ColumnDef:
    """Represents a column definition from either a migration or ORM model."""

    name: str
    col_type: str
    nullable: bool = True
    primary_key: bool = False
    default: Optional[str] = None

    def type_compatible(self, other: "ColumnDef") -> bool:
        """Check if two column types are considered compatible."""
        # Normalize types for comparison (e.g., VARCHAR vs String)
        return _normalize_type(self.col_type) == _normalize_type(other.col_type)


@dataclass
class TableDef:
    """Represents a table definition with its columns and indexes."""

    name: str
    columns: Dict[str, ColumnDef] = field(default_factory=dict)
    indexes: Set[str] = field(default_factory=set)


@dataclass
class DriftIssue:
    """Describes a single detected drift issue between migration and model."""

    drift_type: DriftType
    table: str
    detail: str
    column: Optional[str] = None

    def __str__(self) -> str:
        location = f"{self.table}.{self.column}" if self.column else self.table
        return f"[{self.drift_type.value}] {location}: {self.detail}"


def detect_drift(
    migration_schema: Dict[str, TableDef],
    model_schema: Dict[str, TableDef],
) -> List[DriftIssue]:
    """Compare migration-derived schema against ORM model schema.

    Args:
        migration_schema: Tables and columns as defined by migration files.
        model_schema: Tables and columns as defined by ORM models.

    Returns:
        A list of DriftIssue objects describing each detected discrepancy.
    """
    issues: List[DriftIssue] = []

    migration_tables = set(migration_schema.keys())
    model_tables = set(model_schema.keys())

    # Tables present in migrations but missing from ORM models
    for table in migration_tables - model_tables:
        issues.append(
            DriftIssue(
                drift_type=DriftType.MISSING_TABLE,
                table=table,
                detail="Table exists in migrations but has no corresponding ORM model.",
            )
        )

    # Tables present in ORM models but missing from migrations
    for table in model_tables - migration_tables:
        issues.append(
            DriftIssue(
                drift_type=DriftType.EXTRA_TABLE,
                table=table,
                detail="Table defined in ORM model but not found in migrations.",
            )
        )

    # Compare columns for tables present in both
    for table_name in migration_tables & model_tables:
        migration_table = migration_schema[table_name]
        model_table = model_schema[table_name]

        migration_cols = set(migration_table.columns.keys())
        model_cols = set(model_table.columns.keys())

        for col in migration_cols - model_cols:
            issues.append(
                DriftIssue(
                    drift_type=DriftType.MISSING_COLUMN,
                    table=table_name,
                    column=col,
                    detail="Column exists in migration but is absent from ORM model.",
                )
            )

        for col in model_cols - migration_cols:
            issues.append(
                DriftIssue(
                    drift_type=DriftType.EXTRA_COLUMN,
                    table=table_name,
                    column=col,
                    detail="Column defined in ORM model but not found in migration.",
                )
            )

        for col in migration_cols & model_cols:
            m_col = migration_table.columns[col]
            o_col = model_table.columns[col]
            if not m_col.type_compatible(o_col):
                issues.append(
                    DriftIssue(
                        drift_type=DriftType.COLUMN_TYPE_MISMATCH,
                        table=table_name,
                        column=col,
                        detail=(
                            f"Type mismatch: migration has '{m_col.col_type}', "
                            f"model has '{o_col.col_type}'."
                        ),
                    )
                )

    return issues


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TYPE_ALIASES: Dict[str, str] = {
    "varchar": "string",
    "character varying": "string",
    "text": "string",
    "int": "integer",
    "int4": "integer",
    "int8": "biginteger",
    "bigint": "biginteger",
    "bool": "boolean",
    "float": "float",
    "double precision": "float",
    "numeric": "numeric",
    "decimal": "numeric",
    "timestamp": "datetime",
    "timestamptz": "datetime",
}


def _normalize_type(col_type: str) -> str:
    """Normalize a column type string for comparison across dialects."""
    normalized = col_type.lower().split("(")[0].strip()
    return _TYPE_ALIASES.get(normalized, normalized)

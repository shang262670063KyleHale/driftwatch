"""Tests for the drift detector core logic."""

import pytest
from driftwatch.detector import (
    ColumnDef,
    DriftIssue,
    DriftType,
    TableDef,
    compare_schemas,
    type_compatible,
)


# ---------------------------------------------------------------------------
# type_compatible
# ---------------------------------------------------------------------------

class TestTypeCompatible:
    def test_identical_types_are_compatible(self):
        assert type_compatible("VARCHAR", "VARCHAR") is True

    def test_case_insensitive(self):
        assert type_compatible("varchar", "VARCHAR") is True

    def test_integer_aliases(self):
        assert type_compatible("INT", "INTEGER") is True
        assert type_compatible("INTEGER", "INT") is True

    def test_text_aliases(self):
        assert type_compatible("TEXT", "VARCHAR") is True
        assert type_compatible("VARCHAR", "TEXT") is True

    def test_incompatible_types(self):
        assert type_compatible("INTEGER", "BOOLEAN") is False
        assert type_compatible("TEXT", "FLOAT") is False

    def test_numeric_aliases(self):
        assert type_compatible("NUMERIC", "DECIMAL") is True
        assert type_compatible("FLOAT", "REAL") is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col(name, col_type="VARCHAR", nullable=True, primary_key=False, default=None):
    return ColumnDef(
        name=name,
        col_type=col_type,
        nullable=nullable,
        primary_key=primary_key,
        default=default,
    )


def _make_table(name, columns):
    return TableDef(name=name, columns={col.name: col for col in columns})


# ---------------------------------------------------------------------------
# compare_schemas
# ---------------------------------------------------------------------------

class TestCompareSchemas:
    def test_no_drift_identical_schemas(self):
        migration = {"users": _make_table("users", [_make_col("id", "INTEGER")])}
        model = {"users": _make_table("users", [_make_col("id", "INTEGER")])}
        issues = compare_schemas(migration, model)
        assert issues == []

    def test_missing_table_in_model(self):
        migration = {"users": _make_table("users", [_make_col("id", "INTEGER")])}
        model = {}
        issues = compare_schemas(migration, model)
        assert len(issues) == 1
        assert issues[0].drift_type == DriftType.MISSING_TABLE
        assert issues[0].table == "users"

    def test_extra_table_in_model(self):
        migration = {}
        model = {"orders": _make_table("orders", [_make_col("id", "INTEGER")])}
        issues = compare_schemas(migration, model)
        assert len(issues) == 1
        assert issues[0].drift_type == DriftType.EXTRA_TABLE
        assert issues[0].table == "orders"

    def test_missing_column_in_model(self):
        migration = {
            "users": _make_table("users", [_make_col("id"), _make_col("email")])
        }
        model = {"users": _make_table("users", [_make_col("id")])}
        issues = compare_schemas(migration, model)
        assert any(
            i.drift_type == DriftType.MISSING_COLUMN and i.column == "email"
            for i in issues
        )

    def test_extra_column_in_model(self):
        migration = {"users": _make_table("users", [_make_col("id")])}
        model = {
            "users": _make_table("users", [_make_col("id"), _make_col("phone")])
        }
        issues = compare_schemas(migration, model)
        assert any(
            i.drift_type == DriftType.EXTRA_COLUMN and i.column == "phone"
            for i in issues
        )

    def test_type_mismatch(self):
        migration = {"users": _make_table("users", [_make_col("age", "INTEGER")])}
        model = {"users": _make_table("users", [_make_col("age", "VARCHAR")])}
        issues = compare_schemas(migration, model)
        assert any(
            i.drift_type == DriftType.TYPE_MISMATCH and i.column == "age"
            for i in issues
        )

    def test_nullable_mismatch(self):
        migration = {
            "users": _make_table("users", [_make_col("name", nullable=False)])
        }
        model = {
            "users": _make_table("users", [_make_col("name", nullable=True)])
        }
        issues = compare_schemas(migration, model)
        assert any(
            i.drift_type == DriftType.NULLABLE_MISMATCH and i.column == "name"
            for i in issues
        )

    def test_multiple_issues_reported(self):
        migration = {
            "users": _make_table(
                "users",
                [_make_col("id", "INTEGER"), _make_col("email", "TEXT")],
            ),
            "products": _make_table("products", [_make_col("sku")]),
        }
        model = {
            "users": _make_table(
                "users",
                [_make_col("id", "VARCHAR")],  # type mismatch + missing email
            )
            # products table missing entirely
        }
        issues = compare_schemas(migration, model)
        drift_types = {i.drift_type for i in issues}
        assert DriftType.TYPE_MISMATCH in drift_types
        assert DriftType.MISSING_COLUMN in drift_types
        assert DriftType.MISSING_TABLE in drift_types

"""Parser for SQLAlchemy ORM model definitions.

Extracts table and column definitions from SQLAlchemy declarative models
by inspecting the Python AST without importing the target module.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Iterator

from driftwatch.detector import ColumnDef, TableDef


# SQLAlchemy type aliases we recognize and normalize
_TYPE_MAP: dict[str, str] = {
    "String": "VARCHAR",
    "Text": "TEXT",
    "Integer": "INTEGER",
    "BigInteger": "BIGINT",
    "SmallInteger": "SMALLINT",
    "Float": "FLOAT",
    "Numeric": "NUMERIC",
    "Boolean": "BOOLEAN",
    "Date": "DATE",
    "DateTime": "DATETIME",
    "Time": "TIME",
    "LargeBinary": "BLOB",
    "JSON": "JSON",
    "UUID": "UUID",
    "Enum": "ENUM",
}


def _normalize_col_type(node: ast.expr) -> str:
    """Convert an AST node representing a SQLAlchemy type to a normalized string."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else None
        )
        if name:
            return _TYPE_MAP.get(name, name.upper())
    elif isinstance(node, ast.Attribute):
        return _TYPE_MAP.get(node.attr, node.attr.upper())
    elif isinstance(node, ast.Name):
        return _TYPE_MAP.get(node.id, node.id.upper())
    return "UNKNOWN"


def _parse_column_call(call: ast.Call) -> ColumnDef | None:
    """Parse a SQLAlchemy Column(...) call and return a ColumnDef, or None if unparseable."""
    col_type = "UNKNOWN"
    nullable = True
    primary_key = False

    # Positional args: Column(String), Column('name', String), etc.
    for arg in call.args:
        if isinstance(arg, (ast.Call, ast.Attribute, ast.Name)):
            candidate = _normalize_col_type(arg)
            if candidate != "UNKNOWN":
                col_type = candidate
                break

    # Keyword args
    for kw in call.keywords:
        if kw.arg == "nullable":
            if isinstance(kw.value, ast.Constant):
                nullable = bool(kw.value.value)
        elif kw.arg == "primary_key":
            if isinstance(kw.value, ast.Constant):
                primary_key = bool(kw.value.value)
        elif kw.arg == "type_":
            col_type = _normalize_col_type(kw.value)

    # primary_key columns are implicitly not nullable
    if primary_key:
        nullable = False

    # name is filled in by the caller
    return ColumnDef(name="", col_type=col_type, nullable=nullable, primary_key=primary_key)


def _is_column_assignment(value: ast.expr) -> bool:
    """Return True if the expression looks like a Column(...) call."""
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    name = func.attr if isinstance(func, ast.Attribute) else (
        func.id if isinstance(func, ast.Name) else None
    )
    return name == "Column"


def _table_name_from_class(class_node: ast.ClassDef) -> str | None:
    """Extract __tablename__ from a class body, returning None if absent."""
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__tablename__":
                    if isinstance(node.value, ast.Constant):
                        return str(node.value.value)
    return None


def _extract_tables_from_ast(tree: ast.Module) -> Iterator[TableDef]:
    """Walk module-level classes and yield TableDef for each ORM model found."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        table_name = _table_name_from_class(node)
        if table_name is None:
            continue

        columns: list[ColumnDef] = []
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    attr_name = target.id
                    if _is_column_assignment(item.value):
                        col = _parse_column_call(item.value)  # type: ignore[arg-type]
                        if col is not None:
                            col = ColumnDef(
                                name=attr_name,
                                col_type=col.col_type,
                                nullable=col.nullable,
                                primary_key=col.primary_key,
                            )
                            columns.append(col)
            elif isinstance(item, ast.AnnAssign):
                # Mapped[...] style (SQLAlchemy 2.x)
                if isinstance(item.target, ast.Name) and item.value is not None:
                    if _is_column_assignment(item.value):
                        col = _parse_column_call(item.value)  # type: ignore[arg-type]
                        if col is not None:
                            col = ColumnDef(
                                name=item.target.id,
                                col_type=col.col_type,
                                nullable=col.nullable,
                                primary_key=col.primary_key,
                            )
                            columns.append(col)

        if columns:
            yield TableDef(table_name=table_name, columns=columns)


def parse_models_file(path: str | os.PathLike) -> list[TableDef]:
    """Parse a single Python file and return all ORM-defined tables found."""
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return list(_extract_tables_from_ast(tree))


def parse_models_directory(directory: str | os.PathLike) -> list[TableDef]:
    """Recursively scan *directory* for .py files and collect all ORM table definitions."""
    tables: list[TableDef] = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = Path(root) / fname
            try:
                tables.extend(parse_models_file(filepath))
            except SyntaxError:
                # Skip files that cannot be parsed
                pass
    return tables

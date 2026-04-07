"""Parser for Alembic migration files.

Extracts table and column definitions from Alembic migration scripts
by statically analyzing the Python AST rather than executing migrations.
"""

import ast
import os
import re
from pathlib import Path
from typing import Optional

from driftwatch.detector import ColumnDef, TableDef


def find_migrations_dir(path: str) -> Path:
    """Locate the Alembic migrations directory.

    Searches for a versions/ subdirectory or alembic.ini to identify
    the migrations root.

    Args:
        path: Starting directory or direct path to migrations folder.

    Returns:
        Resolved Path to the migrations directory.

    Raises:
        FileNotFoundError: If no migrations directory can be found.
    """
    p = Path(path).resolve()
    if p.is_dir():
        # Direct path to versions/ or migrations/
        if (p / "versions").is_dir():
            return p / "versions"
        if p.name == "versions":
            return p
        # Walk up looking for alembic structure
        for candidate in p.rglob("versions"):
            if candidate.is_dir():
                return candidate
    raise FileNotFoundError(
        f"Could not locate an Alembic 'versions' directory under '{path}'"
    )


def _extract_op_calls(tree: ast.AST) -> list[ast.Call]:
    """Return all op.* Call nodes found in the AST."""
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ):
            calls.append(node)
    return calls


def _str_value(node: ast.expr) -> Optional[str]:
    """Safely extract a string constant from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _parse_column_node(node: ast.Call) -> Optional[ColumnDef]:
    """Parse a sa.Column(...) call into a ColumnDef.

    Handles positional args: Column(name, Type, nullable=..., primary_key=...)
    """
    args = node.args
    if len(args) < 2:
        return None

    name = _str_value(args[0])
    if name is None:
        return None

    # Type is the second positional arg; grab its name
    type_node = args[1]
    if isinstance(type_node, ast.Call):
        col_type = getattr(type_node.func, "attr", None) or getattr(
            type_node.func, "id", "UNKNOWN"
        )
    elif isinstance(type_node, ast.Attribute):
        col_type = type_node.attr
    elif isinstance(type_node, ast.Name):
        col_type = type_node.id
    else:
        col_type = "UNKNOWN"

    nullable = True
    primary_key = False
    for kw in node.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable = bool(kw.value.value)
        if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
            primary_key = bool(kw.value.value)

    return ColumnDef(
        name=name,
        col_type=col_type.upper(),
        nullable=nullable,
        primary_key=primary_key,
    )


def parse_migration_file(filepath: Path) -> dict[str, TableDef]:
    """Parse a single Alembic migration file and return table definitions.

    Only processes the upgrade() function body to capture the intended
    forward-migration schema state.

    Args:
        filepath: Path to the .py migration file.

    Returns:
        Mapping of table name -> TableDef extracted from op.create_table calls.
    """
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return {}

    tables: dict[str, TableDef] = {}

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "create_table":
            continue

        if not node.args:
            continue
        table_name = _str_value(node.args[0])
        if table_name is None:
            continue

        columns: dict[str, ColumnDef] = {}
        for arg in node.args[1:]:
            if isinstance(arg, ast.Call):
                col = _parse_column_node(arg)
                if col:
                    columns[col.name] = col

        tables[table_name] = TableDef(name=table_name, columns=columns)

    return tables


def parse_migrations(path: str) -> dict[str, TableDef]:
    """Parse all Alembic migration files in the given directory.

    Files are processed in lexicographic order (matching Alembic's revision
    ordering convention). Later create_table definitions overwrite earlier ones
    for the same table name.

    Args:
        path: Path to the migrations directory (or its parent).

    Returns:
        Aggregated mapping of table name -> TableDef across all migrations.
    """
    versions_dir = find_migrations_dir(path)
    migration_files = sorted(versions_dir.glob("*.py"))

    all_tables: dict[str, TableDef] = {}
    for mf in migration_files:
        if mf.name.startswith("__"):
            continue
        tables = parse_migration_file(mf)
        all_tables.update(tables)

    return all_tables

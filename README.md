# driftwatch

A lightweight CLI tool that detects schema drift between database migrations and ORM models.

---

## Installation

```bash
pip install driftwatch
```

Or install from source:

```bash
git clone https://github.com/yourname/driftwatch.git
cd driftwatch && pip install -e .
```

---

## Usage

Point `driftwatch` at your migrations directory and ORM models to check for drift:

```bash
driftwatch check --migrations ./migrations --models ./app/models.py
```

Example output:

```
[✓] users         — in sync
[✗] products      — drift detected: column 'discount_price' missing in migration
[✗] orders        — drift detected: field type mismatch on 'status' (VARCHAR vs INTEGER)

2 drift(s) found.
```

### Options

| Flag | Description |
|------|-------------|
| `--migrations` | Path to your migrations directory |
| `--models` | Path to your ORM models file or package |
| `--format` | Output format: `text` (default) or `json` |
| `--strict` | Exit with code 1 if any drift is detected |

```bash
# Output results as JSON
driftwatch check --migrations ./migrations --models ./app/models.py --format json

# Use in CI pipelines
driftwatch check --migrations ./migrations --models ./app/models.py --strict
```

---

## Supported ORMs

- SQLAlchemy
- Django ORM *(coming soon)*
- Tortoise ORM *(coming soon)*

---

## License

MIT © 2024 [yourname](https://github.com/yourname)
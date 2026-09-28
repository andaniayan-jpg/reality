# Contributing

Thanks for improving `reality`. This project uses Python 3.11+ and a `src/` layout.

## Setup

```bash
git clone https://github.com/reality-python/reality.git
cd reality
python -m pip install -e ".[dev]"
```

Before opening a pull request, run:

```bash
ruff format --check .
ruff check .
python -m mypy src/reality
pytest
```

Keep public APIs typed and documented. Add focused tests for changes in geometric semantics, including result measurements and evidence. Preserve the backend-neutral public model: imports of a backend belong in an adapter, not `World` or the value objects.

By contributing, you agree that contributions are provided under the Apache-2.0 license.

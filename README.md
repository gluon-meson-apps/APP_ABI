## Setup

Requires at least Python3.9.0

## start service in local

install poetry, make sure poetry is installed, poetry related commands https://python-poetry.org/docs/cli/
```bash
pip install poetry
```

use python3.9
```bash
poetry env use python3.9
```
install dependencies
```bash
poetry install
```

start service
```bash
poetry run python src/app.py
```

run lint and test
```bash
poetry run make lint
poetry run make test
```

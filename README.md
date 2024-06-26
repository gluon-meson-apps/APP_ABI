## Setup

Requires at least Python3.9.0

## start service in local

install poetry and virtualenv, make sure poetry and virtualenv is installed, poetry related commands https://python-poetry.org/docs/cli/
```bash
pip install poetry
pip install virtualenv
```

specify python3.9
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

install pre-commit hook
```bash
pre-commit install
```


intent example init
```bash
poetry run python  src/nlu/llm/intent_examples.py
```

## add HSBC_CONNECT_API_ENDPOINT in .env for HSBC
```
HSBC_CONNECT_API_ENDPOINT=https://hkl20146575.hc.cloud.hk.hsbc:25000/PaymentRulesValidator/Report
```

## add grapi api endpoint in .env

### for HSBC
```
GRAPH_API_LOGIN_ENDPOINT=http://130.51.102.48:18030
GRAPH_API_MAIL_ENDPOINT=http://130.51.102.48:18030
```

### for local env
```
GRAPH_API_LOGIN_ENDPOINT=https://login.microsoftonline.com
GRAPH_API_MAIL_ENDPOINT=https://graph.microsoft.com
```

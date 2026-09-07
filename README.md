# School Finder

[![CI](https://github.com/c-wilkinson/school-finder/actions/workflows/ci.yml/badge.svg)](https://github.com/c-wilkinson/school-finder/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/c-wilkinson/school-finder/branch/main/graph/badge.svg)](https://codecov.io/gh/c-wilkinson/school-finder)

School Finder builds a local, queryable dataset of English schools and exposes a
presentation-independent search service.

The project currently combines:

- Get Information About Schools (GIAS)
- ONS Postcode Directory (ONSPD)
- Ofsted inspection outcomes
- DfE Key Stage 4 performance data

## Architecture

```text
src/school_finder/
├── cli.py                 # command-line presentation adapter
├── config.py
├── errors.py
├── data/
│   ├── build.py           # build orchestration
│   ├── manifest.py
│   ├── parquet.py
│   └── sources/           # upstream-data adapters
├── models/
│   ├── school.py          # application-facing school contract
│   └── search.py          # search request/response contracts
└── services/
    ├── postcode.py
    └── search.py          # reusable search use-case
```

## Development setup

```powershell
python -m pip install -e ".[dev]"
```

## Build or refresh data

```powershell
school-finder build
```

To force a complete rebuild:

```powershell
school-finder build --force
```

## Search

```powershell
school-finder lookup "SW1A 2AA"
```

Flat JSON (legacy CLI contract):

```powershell
school-finder lookup "SW1A 2AA" --json
```

Application-facing nested models:

```powershell
school-finder lookup "SW1A 2AA" --structured-json
```

You can also run the package without the installed console-script name:

```powershell
python -m school_finder lookup "SW1A 2AA"
```

## Use from Python

```python
from pathlib import Path

from school_finder import SchoolSearchRequest, search_schools

result = search_schools(
    Path("data"),
    SchoolSearchRequest(postcode="SW1A 2AA", limit=20),
)

for school in result.schools:
    print(school.identity.name, school.travel.distance_miles)
```

## Tests

The test suite covers the public-data adapters, dataset build orchestration,
manifest and Parquet helpers, application models, postcode/search services and
the CLI. External HTTP calls are mocked so the suite is deterministic and does
not depend on publisher availability.

Run all tests:

```powershell
python -m pytest
```

Coverage is collected automatically and the test run fails if total coverage
falls below 95%. Continuous integration runs the same suite on every push, every
pull request and once per day at 06:30 Europe/London. The badges at the top of
this README show the current CI state and coverage for `main`.

For verbose test names:

```powershell
python -m pytest -v
```

## Continuous integration

GitHub Actions runs the test suite on every push and pull request, and once per
day at 06:30 Europe/London. Coverage is uploaded to Codecov from the same run.


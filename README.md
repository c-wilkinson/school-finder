# School Finder

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

```powershell
python -m pytest -v
```

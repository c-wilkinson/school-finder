# School Finder

[![CI](https://github.com/c-wilkinson/school-finder/actions/workflows/ci.yml/badge.svg)](https://github.com/c-wilkinson/school-finder/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/c-wilkinson/school-finder/branch/main/graph/badge.svg)](https://codecov.io/gh/c-wilkinson/school-finder)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Find, compare and rank secondary schools in England by postcode**, using official DfE, Ofsted and ONS data.

School Finder combines several public datasets into one structured local dataset, with reusable search and scoring logic that can be consumed from the CLI or directly from Python.

**Try the live web app:** [https://school-finder.streamlit.app/](https://school-finder.streamlit.app/)

The longer-term aim is for the same core to power a Streamlit web app, public API and MCP server.

## Why this exists

When we were looking at secondary schools for my son, I ended up building a spreadsheet combining information from several different sources.

I shared it with a few other parents and several said they wished they'd had something similar when choosing schools.

The information is available publicly, but it's spread across a number of different places. School Finder is an attempt to bring the useful bits together and make it easier to answer questions such as:

- Which secondary schools are within 3 miles of this postcode?
- Which nearby schools have the strongest academic results?
- How do Ofsted outcomes and KS4 performance compare?
- Which schools best match the things that matter most to me?
- Can I consume the same information from another application?

## Data sources

School Finder currently uses:

- **GIAS** — Get Information About Schools (DfE)
- **ONSPD** — ONS Postcode Directory
- **Ofsted** — school inspection outcomes and judgements
- **DfE KS4** — Attainment 8, Progress 8, English & Maths, EBacc and related measures

The build process downloads and normalises the source data into local Parquet datasets.

## Quick start

```bash
git clone https://github.com/c-wilkinson/school-finder.git
cd school-finder

python -m pip install -e ".[dev]"

school-finder build
school-finder lookup "SW1A 2AA"
```

### Streamlit web app

Install the optional web dependency and start the app:

```bash
python -m pip install -e ".[web]"
school-finder build
python -m streamlit run streamlit_app.py
```

### Output formats

Human-readable output is the default:

```bash
school-finder lookup "SW1A 2AA"
```

Flat JSON:

```bash
school-finder lookup "SW1A 2AA" --json
```

Structured application models:

```bash
school-finder lookup "SW1A 2AA" --structured-json
```

## Search filters

Searches can be restricted using a number of hard filters:

```bash
school-finder lookup "SW1A 2AA"
    --radius 5
    --phase secondary
    --sector state-funded
    --gender mixed
    --faith non-faith
    --minimum-ofsted good
    --minimum-attainment8 45
```

Filters determine which schools are acceptable. Preference scoring is then used to rank the schools that remain.

## Preference scoring

Schools can be ranked according to configurable priorities:

```bash
school-finder lookup "SW1A 2AA"
    --radius 5
    --weight-distance 30
    --weight-ofsted 25
    --weight-attainment8 20
    --weight-progress8 15
    --weight-grade5-english-maths 10
```

Built-in presets are also available:

```bash
school-finder lookup "SW1A 2AA" --preference-preset balanced
school-finder lookup "SW1A 2AA" --preference-preset academic
school-finder lookup "SW1A 2AA" --preference-preset closest
school-finder lookup "SW1A 2AA" --preference-preset ofsted-focused
```

Scores are broken down by component rather than being treated as an unexplained single number.

Missing metrics are not treated as zero; available weights are redistributed and the result includes a coverage percentage showing how much of the requested scoring data was available.

## Ofsted handling

Older Ofsted inspections included an overall effectiveness grade, while newer inspection frameworks use individual judgements instead.

Where an official overall grade exists, School Finder uses it unchanged.

Where it does not, School Finder derives a clearly labelled **equivalent Ofsted rating** from the available judgements using a limiting-judgement approach. A weak key judgement therefore cannot simply be averaged away by stronger scores elsewhere.

School Finder can also follow unambiguous GIAS predecessor relationships where a school has changed URN, retaining the original school and URN as provenance for inherited historical inspection data.

## Use as a Python library

```python
from pathlib import Path

from school_finder import (
    PreferencePreset,
    SchoolPreferences,
    SchoolSearchRequest,
    search_schools,
)

result = search_schools(
    Path("data"),
    SchoolSearchRequest(
        postcode="SW1A 2AA",
        radius_miles=5,
        preferences=SchoolPreferences.from_preset(
            PreferencePreset.BALANCED
        ),
    ),
)

for school in result.schools:
    print(
        school.identity.name,
        school.preference_score.overall,
        school.travel.distance_miles,
    )
```

## Architecture

The project is deliberately structured so that the same core functionality can be consumed by different interfaces:

```text
Public datasets
      ↓
Data adapters / cleaning
      ↓
Canonical application models
      ↓
Search / filtering / scoring services
      ↓
┌───────────┬───────────┬───────────┬───────────┐
│    CLI    │ Streamlit │    API    │    MCP    │
└───────────┴───────────┴───────────┴───────────┘
```


## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

External HTTP calls are mocked by the test suite.

Coverage is enforced in CI and the build fails if total coverage drops below 95%.

GitHub Actions runs the tests on pushes, pull requests and on a daily schedule.

## License

School Finder is licensed under the [GNU Affero General Public License v3.0](LICENSE).

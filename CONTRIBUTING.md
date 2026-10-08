# Contributing to School Finder

Thanks for your interest in improving School Finder!

School Finder started as a personal project to make comparing secondary schools in England easier, bringing together publicly available education data that would otherwise require visiting several different sources.

The project is designed around reusable core logic, independent of how that logic is presented. Today, it supports a command-line interface and Streamlit application, with an API and MCP server planned for the future.

Contributions are welcome, particularly those that improve reliability, maintainability, data quality and the usefulness of the information presented.

## Ways to contribute

There are plenty of ways to help:

- **Bug reports:** Identify problems and provide reproducible examples.
- **Data quality:** Improve ingestion, cleaning, normalisation and validation of public datasets.
- **Testing:** Add tests, improve edge-case coverage or identify regressions.
- **Documentation:** Fix errors, clarify behaviour or improve examples.
- **Features:** Implement focused improvements consistent with the existing architecture.
- **Performance:** Optimise data loading, filtering, scoring and Parquet processing.
- **Accessibility:** Improve the usability and accessibility of the Streamlit application.

For significant new features or architectural changes, please open an issue before starting work. This helps avoid duplicated effort and ensures proposed changes fit the project's direction.

## Development setup

### Requirements

- Python 3.11 or later
- Git
- An internet connection for downloading source datasets

### Installation

Clone the repository:

```bash
git clone https://github.com/c-wilkinson/school-finder.git
cd school-finder
```

Creating a virtual environment is recommended:

```bash
python -m venv .venv
```

Activate it:

**Windows (PowerShell)**

```powershell
.venv\Scripts\Activate.ps1
```

**Linux / macOS**

```bash
source .venv/bin/activate
```

Install the project with development and web dependencies:

```bash
python -m pip install -e ".[dev,web]"
```

### Running the tests

```bash
python -m pytest
```

The test suite includes coverage reporting and enforces a minimum overall coverage of 95%.

### Building the datasets

```bash
school-finder build
```

This downloads and normalises public datasets from sources including GIAS, Ofsted, DfE KS4 and the ONS Postcode Directory.

The initial build requires internet access and may take several minutes.

### Running a search

```bash
school-finder lookup "SW1A 2AA"
```

Structured output is also available:

```bash
school-finder lookup "SW1A 2AA" --structured-json
```

### Running the web application

```bash
python -m streamlit run streamlit_app.py
```

## Project architecture

School Finder deliberately separates data processing, domain models, business logic and presentation.

The high-level flow is:

```text
Public datasets
       |
       v
Data ingestion and normalisation
       |
       v
Canonical domain models
       |
       v
Search, filtering and scoring services
       |
       +---- CLI
       |
       +---- Streamlit
       |
       +---- API (planned)
       |
       +---- MCP server (planned)
```

### Core principles

**1. Keep presentation separate from business logic**

Core services should not depend on Streamlit or CLI-specific functionality.

New functionality should ideally be reusable by every interface.

**2. Preserve data provenance**

Prefer explicit models and traceable source information over implicit assumptions.

Where information originates from different datasets, preserve enough context to explain where values came from.

**3. Treat missing data correctly**

Missing data is not the same as zero.

Do not replace missing values with zero unless there is a documented reason for doing so.

Scoring and filtering changes must preserve the distinction between unavailable information and a genuinely poor result.

**4. Distinguish official and derived information**

Derived values must be clearly distinguishable from official published values.

For example, an equivalent Ofsted rating calculated from individual judgements must never be represented as an officially awarded overall grade.

**5. Keep behaviour deterministic and testable**

Prefer small, focused functions that can be tested without network access or presentation-layer dependencies.

## Coding standards

School Finder targets **Python 3.11+**.

Contributions should:

- Follow the existing style and conventions.
- Use type hints on public functions and methods.
- Prefer explicit, descriptive names.
- Use dataclasses and enums for well-defined domain concepts where appropriate.
- Prefer `frozen=True` and `slots=True` for immutable models where practical.
- Keep functions focused and responsibilities clearly separated.
- Avoid adding dependencies without a clear justification.
- Preserve backwards compatibility where reasonably possible.

Avoid introducing unnecessary abstraction or complexity for functionality that can be expressed clearly using existing patterns.

## Testing requirements

All changes should be accompanied by appropriate tests.

Before opening a pull request, run:

```bash
python -m pytest
```

### Coverage

The project enforces a minimum of **95% total coverage**, with branch coverage enabled.

Contributions should maintain this threshold. However, coverage alone is not sufficient: tests should verify meaningful behaviour and important edge cases.

### External dependencies

Automated tests must not rely on live HTTP requests.

Mock external services and dataset downloads to ensure tests remain reliable, reproducible and suitable for CI.

### Data-related changes

When modifying ingestion, normalisation or scoring logic, consider tests for:

- Missing or incomplete fields
- Unexpected source formats
- Duplicate records
- Invalid postcodes or identifiers
- Changes in source data schemas
- Edge cases in filtering and scoring

Where possible, use small synthetic fixtures rather than full production datasets.

## Working with data

School Finder uses publicly available datasets, including information from the Department for Education, Ofsted and the Office for National Statistics.

When changing data processing logic:

- Preserve original identifiers where possible.
- Do not silently discard data without justification.
- Avoid assumptions that only hold for a particular dataset release.
- Document transformations that materially affect reported values.
- Consider the impact on downstream consumers.

Do not commit large generated datasets, temporary downloads, local caches or credentials unless explicitly agreed.

Changes affecting generated dataset schemas should consider compatibility with existing consumers.

## Pull requests

### Before starting

For anything beyond a small bug fix or documentation update, please open an issue to discuss the proposed change.

Check existing issues and pull requests to avoid duplicating work.

### Preparing your change

1. Fork the repository.
2. Keep changes focused on one logical improvement.
3. Follow the existing architectural patterns.
4. Add or update tests.
5. Update relevant documentation.
6. Run the test suite locally.

### Submitting your PR

Include a short description covering:

- **Problem:** What issue or limitation does this address?
- **Approach:** How does your change solve it?
- **Testing:** How was the change verified?
- **Trade-offs:** Are there limitations or follow-up improvements?

Link any relevant issues.

Please keep pull requests reasonably small and focused. Smaller changes are easier to understand, review and maintain.

All automated checks should pass before a pull request is merged.

## Reporting bugs

Found something that doesn't work as expected?

Please [open an issue](https://github.com/c-wilkinson/school-finder/issues) and include:

- What you were trying to do
- What you expected to happen
- What actually happened
- Steps to reproduce the problem
- Relevant commands, postcodes or search filters
- Python version and operating system, where relevant
- Any useful error messages or tracebacks

Please avoid including personal information or other sensitive data in bug reports.

## Feature requests

Feature suggestions are welcome.

When proposing a feature, explain the problem it would solve and how it would help users.

For larger changes, a brief description of the proposed implementation is useful, but a fully developed design is not required.

Features that improve the reusable core are generally preferable to functionality tied exclusively to one interface.

## Licensing

School Finder is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

By submitting a contribution, you agree to make your contribution available under the project's existing licence.

Please ensure any third-party code, data or other materials you introduce are compatible with the project's licensing requirements.

## Questions

If you're unsure where to start, have a question about the architecture or want to discuss an idea, feel free to [open an issue](https://github.com/c-wilkinson/school-finder/issues).

You don't need to have everything figured out before starting a discussion.

Thanks for helping make School Finder better!
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev,web]"
& .\.venv\Scripts\python.exe -m school_finder build
& .\.venv\Scripts\python.exe -m streamlit run streamlit_app.py

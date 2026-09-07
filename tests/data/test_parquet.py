import hashlib
from types import SimpleNamespace

import pandas as pd
import pytest

from school_finder.data import parquet
from school_finder.errors import SchoolFinderError


def test_require_pyarrow_errors_when_dependency_unavailable(monkeypatch):
    monkeypatch.setattr(parquet, "pa", None)
    monkeypatch.setattr(parquet, "pq", None)
    with pytest.raises(SchoolFinderError, match="PyArrow is required"):
        parquet.require_pyarrow()


def test_write_parquet_file_delegates_with_expected_options(tmp_path, monkeypatch):
    calls = {}
    table_obj = object()
    fake_pa = SimpleNamespace(Table=SimpleNamespace(from_pandas=lambda frame, preserve_index: table_obj))
    fake_pq = SimpleNamespace(write_table=lambda table, destination, **kwargs: calls.update(table=table, destination=destination, kwargs=kwargs))
    monkeypatch.setattr(parquet, "pa", fake_pa)
    monkeypatch.setattr(parquet, "pq", fake_pq)
    dest = tmp_path / "x.parquet"
    parquet.write_parquet_file(pd.DataFrame({"a":[1]}), dest)
    assert calls["table"] is table_obj
    assert calls["kwargs"]["compression"] == "zstd"
    assert calls["kwargs"]["row_group_size"] == parquet.PARQUET_ROW_GROUP_SIZE


def test_parquet_columns_returns_schema_names(monkeypatch):
    fake = SimpleNamespace(schema_arrow=SimpleNamespace(names=["a", "b"]))
    monkeypatch.setattr(parquet, "pa", object())
    monkeypatch.setattr(parquet, "pq", SimpleNamespace(ParquetFile=lambda path: fake))
    assert parquet.parquet_columns("x") == {"a", "b"}


def test_sha256_file(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    assert parquet.sha256_file(path) == hashlib.sha256(b"abc").hexdigest()


def test_parquet_metadata_combines_file_and_parquet_metadata(tmp_path, monkeypatch):
    path = tmp_path / "x.parquet"
    path.write_bytes(b"data")
    fake = SimpleNamespace(metadata=SimpleNamespace(num_rows=3), schema_arrow=SimpleNamespace(names=["a"]))
    monkeypatch.setattr(parquet, "pa", object())
    monkeypatch.setattr(parquet, "pq", SimpleNamespace(ParquetFile=lambda p: fake))
    metadata = parquet.parquet_metadata(path)
    assert metadata["rows"] == 3
    assert metadata["bytes"] == 4
    assert metadata["columns"] == ["a"]


def test_parquet_module_imports_pyarrow_components_when_available(monkeypatch):
    import importlib
    import sys
    import types

    fake_pa = types.ModuleType("pyarrow")
    fake_pa.__version__ = "99.0.0"
    fake_pq = types.ModuleType("pyarrow.parquet")
    fake_pa.parquet = fake_pq

    with monkeypatch.context() as context:
        context.setitem(sys.modules, "pyarrow", fake_pa)
        context.setitem(sys.modules, "pyarrow.parquet", fake_pq)
        reloaded = importlib.reload(parquet)
        assert reloaded.pa is fake_pa
        assert reloaded.pq is fake_pq

    sys.modules.pop("pyarrow", None)
    sys.modules.pop("pyarrow.parquet", None)
    importlib.reload(parquet)

import importlib


def test_packages_import() -> None:
    for name in ("pipeline", "tracing", "forensics", "evals", "api"):
        importlib.import_module(name)

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://duckdb.org/images/logo-dl/DuckDB_Logo-horizontal.svg">
    <source media="(prefers-color-scheme: dark)" srcset="https://duckdb.org/images/logo-dl/DuckDB_Logo-horizontal-dark-mode.svg">
    <img alt="DuckDB logo" src="https://duckdb.org/images/logo-dl/DuckDB_Logo-horizontal.svg" height="100">
  </picture>
</div>
<br/>
<p align="center">
  <a href="https://discord.gg/tcvwpjfnZx"><img src="https://shields.io/discord/909674491309850675" alt="Discord" /></a>
  <a href="https://pypi.org/project/duckdb/"><img src="https://img.shields.io/pypi/v/duckdb.svg" alt="PyPI Latest Release"/></a>
</p>

## DuckDB CLI

This package distributes the [DuckDB Command Line Interface](https://duckdb.org/docs/clients/cli/overview) as a Python package.

## Installation

```bash
pip install duckdb-cli
```

## Usage

After installation, the `duckdb` command is available:

```bash
duckdb
```

## Extensions

Extension packages such as `duckdb-core-ext-httpfs` install an extension binary into `site-packages/.duckdb_extensions`, and `duckdb` adds that directory to DuckDB's extension search path, so `LOAD httpfs` finds it without a download:

```bash
pip install "duckdb-cli[httpfs]==2.0.0"
duckdb -c "LOAD httpfs"
```

The directory comes after the directories DuckDB already searches. DuckDB's automatic loading checks only the first directory before downloading, so a query that autoloads an extension may download it again, and offline that autoload fails; an explicit `LOAD` always works. This holds until the bundled engine treats an extension found in any configured directory as installed.

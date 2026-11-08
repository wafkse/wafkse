set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

# The version is shared by local installs and CI. Edit .mirage-version to upgrade.
install-mirage:
    cargo install --locked --git https://github.com/wafkse/mirage --tag "$(cat .mirage-version)" mirage

# Generate all SVG outputs using Mirage.
build:
    mirage --oneshot --configure .

# Exercise API discovery, aggregation, and serialization without network access.
test:
    uv run python -m unittest discover -s tests -v

# Verify committed rendered outputs.
check: test build
    git diff --exit-code -- README.md assets/rhythm-mocha.svg assets/rhythm-latte.svg assets/source-mocha.svg assets/source-latte.svg

# Collect public repository metrics, then rebuild the README artwork.
refresh: test
    uv run python tool/metric.py
    just build

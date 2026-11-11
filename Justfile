set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

# The version is shared by local installs and CI. Edit .mirage.tag to upgrade.
install-mirage:
    cargo install --locked --git https://github.com/wafkse/mirage --tag "$(cat .mirage.tag)" mirage

# Generate all SVG outputs using Mirage.
build:
    mirage --oneshot --configure .
    uv run python tool/font.py

# Exercise API discovery, aggregation, and serialization without network access.
test:
    uv run pytest

# Verify committed rendered outputs.
check: test build
    git diff --exit-code -- README.md assets/rhythm-mocha.svg assets/rhythm-latte.svg assets/language-mocha.svg assets/language-latte.svg assets/website-mocha.svg assets/website-latte.svg

# Collect public repository metrics, then rebuild the README artwork.
refresh: test
    uv run python tool/metric.py
    just build

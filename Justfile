set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

# Render README.md and both light/dark SVG pairs.
build:
    mirage --oneshot --configure .

# Tests are deliberately network-free.
test:
    python3 -m unittest discover -s tests -v

# Deterministic generated-output check for pull requests.
check: test build
    git diff --exit-code -- README.md assets/banner-dark.svg assets/banner-light.svg assets/signal-dark.svg assets/signal-light.svg

# Fetch fresh public data and regenerate the profile.
refresh:
    python3 tool/snapshot.py
    just build

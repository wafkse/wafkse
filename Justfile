set shell := ["sh", "-eu", "-c"]

default:
    @just --list

build:
    mirage --oneshot --configure .

test:
    python3 -m unittest discover -s tests -v

check: test build
    git diff --exit-code -- README.md assets/rhythm-mocha.svg assets/rhythm-latte.svg assets/source-mocha.svg assets/source-latte.svg

refresh: test
    python3 tool/metrics.py
    just build

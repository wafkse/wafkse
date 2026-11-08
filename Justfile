set shell := ["sh", "-eu", "-c"]

default:
    @just --list

build:
    mirage --oneshot --configure .

check: build
    git diff --exit-code -- README.md

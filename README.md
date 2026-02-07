# Love Letter (Console)

A minimal, console-based implementation of the Love Letter tabletop game. The rules engine is intentionally isolated from I/O so we can later add a browser UI without rewriting game logic.

## Requirements

- Python 3.11+

## Installation (venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Installation (conda)

```bash
conda env create -f environment.yml
conda activate love-letter
pip install -e .
```

## Run

```bash
python -m love_letter
```

Quick run without installing the package:

```bash
PYTHONPATH=src python -m love_letter
```

## Tests

```bash
pytest
```

## Notes

This implementation assumes the standard Love Letter deck and rules (Guard–Princess, 16 cards). If your `ll_rules.pdf` differs (edition/variant), tell me and I will adjust the ruleset accordingly.

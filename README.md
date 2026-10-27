# Avispria

**Canopy structure and change, seen from above.**

Avispria is an offline-first toolkit for planning drone survey missions,
checking capture quality and orchestrating photogrammetry processing for
forestry and environmental research. It works with consumer **RGB-only**
drones: no multispectral sensor required, and no claims beyond what visible
light can support.

*Name:* from *avis* (Latin, "bird") and the osprey, a raptor that surveys
from height.

**Status:** pre-alpha scaffold (v0.0.1). Nothing is flight-ready.
Read [DISCLAIMER.md](DISCLAIMER.md) before using any output near an aircraft.

## Develop

    uv sync --locked
    uv run pre-commit install
    uv run python scripts/check.py

## Run

    uv run avispria --help
    uv run avispria version

## License
AGPL-3.0-or-later (provisional). See [LICENSE](LICENSE) and
[docs/LICENSING.md](docs/LICENSING.md).

<p align="center"><img src="branding/logo.png" alt="Avispria logo" width="140" /></p>

# Avispria

**Canopy structure and change, seen from above.**

Avispria is a free, open-source toolkit for researchers who map with consumer **RGB drones** (no
special sensor needed). It runs on your own computer, works without internet once installed, and has
four parts:

- **Plan a flight**: describe the area you want to map and get DJI Fly missions, with a prediction of
  the resolution and overlap you will really get over your terrain, hills and trees included.
- **Check your photos**: find out from their metadata whether they overlap enough to make a good map,
  and where the weak spots are, before you spend hours processing them.
- **Make maps**: turn the photos into an orthophoto, a surface model and a point cloud with
  [WebODM](https://webodm.org), on your computer, with a record of exactly what was done.
- **A field page for your phone**: checklists, calculators and a flight log that work with no signal.

> **Status: early version, not yet flight-tested.** Planning and checking are tested against real DJI
> Fly files and public datasets, but no mission made by Avispria has been flown yet. Start with a small
> test in open, flat terrain ([first test flight guide](docs/field/first-test-flight.md)) and read the
> [disclaimer](DISCLAIMER.md) before using any output near an aircraft. It is built and checked
> for the **DJI Lito X1** (a Mini 4 Pro profile exists but its numbers are not verified); other DJI drones
> can be added from one original photo.

---

## Install and run

You need two free programs. **Git** downloads Avispria from GitHub. **uv** sets up everything else,
including the right version of Python (3.12), by itself, so you do not need to install Python.
Pick your system:

### Windows 10 or 11

1. Open **PowerShell** (Start menu, type `PowerShell`).
2. Install Git (skip this if `git --version` already works):

       winget install --id Git.Git -e

3. Install uv:

       powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

4. **Close PowerShell and open a new one**, so that it finds the new programs.
5. Download Avispria:

       git clone https://github.com/Mraz11/Avispria.git
       cd Avispria

6. Set it up (once; it downloads the packages and takes a minute or two):

       uv sync --locked

7. Run it: double-click **`Start-Avispria.bat`** in the Avispria folder, or type `uv run avispria ui`.
   Your web browser opens with Avispria.

### macOS

1. Open **Terminal** (press Cmd+Space, type `Terminal`).
2. Install Git. Type `git --version`: if it is missing, macOS offers to install the developer tools,
   say yes (or use `brew install git` if you use Homebrew).
3. Install uv:

       curl -LsSf https://astral.sh/uv/install.sh | sh

4. **Close Terminal and open a new window**, so that it finds uv.
5. Download Avispria:

       git clone https://github.com/Mraz11/Avispria.git
       cd Avispria

6. Set it up (once; takes a minute or two):

       uv sync --locked

7. Run it: type `./start-avispria.sh`, or double-click **`Start-Avispria.command`** in Finder. (If macOS
   refuses the double-click, use the Terminal command.) Your web browser opens with Avispria.

### Linux (Debian or Ubuntu; other systems are similar)

1. Open a terminal and install Git and curl (on Fedora use `dnf` instead of `apt`):

       sudo apt update && sudo apt install -y git curl

2. Install uv, then **open a new terminal window**:

       curl -LsSf https://astral.sh/uv/install.sh | sh

3. Download Avispria and set it up (once; takes a minute or two):

       git clone https://github.com/Mraz11/Avispria.git
       cd Avispria
       uv sync --locked

4. Run it: `./start-avispria.sh`. Your web browser opens with Avispria. On a computer with no screen
   (a server), use `uv run avispria ui --no-browser`. Avispria only listens on the computer it runs on,
   so forward its port to your own computer with `ssh -L 8080:127.0.0.1:8080 you@server` and open
   **http://127.0.0.1:8080** there.

### Check that it works

    uv run avispria version
    uv run avispria doctor

`doctor` reports your computer's memory, disk space and whether WebODM is running.

### Update to a newer version later

    git pull
    uv sync --locked

### If something goes wrong

| What you see | What to do |
|---|---|
| `uv` or `git` "is not recognized" / "command not found" | Close the terminal and open a new one; the install only takes effect in new windows. |
| The browser did not open | Open **http://127.0.0.1:8080** yourself. The terminal shows the exact address (it uses the next free port if 8080 is taken). |
| First start is slow | Normal: the packages are downloaded once. |
| Nothing happens when double-clicking | Run `uv run avispria ui` from a terminal in the Avispria folder to see the message. |

### WebODM, needed only for "Make maps"

Planning flights and checking photos work without it. To make maps, install **WebODM** from
[webodm.org/download](https://webodm.org/download) and start it before using "Make maps".

- **Windows:** use the WebODM for Windows installer. Avispria finds its processing engine by itself.
  This is the setup Avispria has been tested with.
- **macOS and Linux:** the processing engine usually runs in Docker. The simplest way is to run just
  the engine, which is all Avispria needs:

      docker run -d -p 3000:3000 opendronemap/nodeodm

  Avispria looks for it at `http://localhost:3000`. If yours is somewhere else, type its address
  under *Make maps, Advanced*, or add `--url http://host:port` on the command line. This route has not
  been tested by the project yet; please report what you find (Apple Silicon Macs may need an engine
  image built for ARM: see the OpenDroneMap documentation).

---

## Using Avispria

### The window interface (no terminal needed)

Start it as described above. It has four screens and a light/dark switch in the top corner:

| Screen | What it does |
|---|---|
| **Start** | Shows what your computer can do and whether WebODM is running. |
| **Check my photos** | A verdict, the key numbers, a map of where each photo was taken, and every warning explained in plain words ("what it means" and "what to do"). Optionally uses an elevation model so results are right over hills. |
| **Plan a flight** | Describe the area (by numbers or a map file), your drone and what you need; get DJI Fly mission files, the route on a map, and the prediction of what you will really get. |
| **Make maps** | Pick the photos and a quality level; Avispria checks that your computer can handle the job, follows the progress (you can cancel), and gives you the orthophoto, surface model and point cloud. |

Everything stays on your computer. The interface listens on `127.0.0.1` only, so nothing is sent
anywhere and nothing is reachable from the network.

To plan a flight you need **your own DJI Fly sample mission** (a two-point waypoint mission saved in DJI
Fly and copied to the computer): Avispria copies the exact file format your DJI Fly uses from it. The
*Plan a flight* screen explains how to get it.

### The field page for your phone

Open **https://mraz11.github.io/Avispria/** on your phone. Then, on Android (Chrome), use the menu and
choose *Install app*; on iPhone (Safari), use Share, then *Add to Home Screen*. After the first visit it
works with no signal. It has pre-flight, in-air and after-landing checklists, calculators that follow the
planner (resolution, spacing, speed, survey time, what trees do to a plan made for flat ground), and a
flight log that records the takeoff coordinates Avispria asks for. Everything stays on the phone.

### The command line

The same features are available as commands. `uv run avispria --help` lists them, and
`uv run avispria <command> --help` shows every option.

| Command | What it does |
|---|---|
| `plan` | Plan a survey and write DJI Fly mission files, an RC spot-check sheet and a report. |
| `qa` | Check overlap, coverage, blur, gimbal angle, altitude and timing of survey photos. |
| `process` | Check, upload and process a photo folder with WebODM; download the results with a provenance record. |
| `doctor` | Check this computer, and whether it can process a given photo folder. |
| `engine` | Find WebODM's processing engine and show what it supports. |
| `ui` | Open the window interface. |
| `drones` | List the known aircraft and camera modes. |
| `camera-from-photo` | Print a camera profile derived from one original photo. |
| `inspect`, `lint`, `sheet`, `prepare-copy` | Look inside, check, summarise and install a DJI Fly mission file. |

Examples (on Windows write paths with backslashes):

    uv run avispria plan area.geojson --template my_dummy.kmz --takeoff 23.8290,90.4170 \
        --gsd-cm 2 --dem dem.tif --out out/survey
    uv run avispria qa photos/ --recursive
    uv run avispria doctor photos/
    uv run avispria process photos/ --out results/ --preset standard

Planning over trees on flat ground: add `--flat --surface-height 25` (the canopy height in metres), so
the treetops, not the ground, get the height you asked for.

---

## Develop

    uv run pre-commit install
    uv run python scripts/check.py       # formatting, lint, types, tests; the same checks as CI

Continuous integration runs the same checks on Linux, Windows and macOS. [HANDOFF.md](HANDOFF.md) is the
developer's guide to the design and the decisions made so far. Two things are generated and must be
refreshed after changes: run `python scripts/field_page.py` after changing the phone page or
`src/avispria/data/drones.toml`, and `python scripts/make_branding.py` after changing the logo (the
tests fail if they are out of date).

The colours, light and dark, come from one place, `src/avispria/app/ui/theme.py`, which both the window
interface and the phone page use; a test measures the contrast of every pairing. See
[branding/README.md](branding/README.md) about the logo.

## License

AGPL-3.0-or-later (provisional). See [LICENSE](LICENSE) and [docs/LICENSING.md](docs/LICENSING.md). The
licence of the logo is still to be decided ([branding/README.md](branding/README.md)).

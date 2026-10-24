# QLab-python Copilot Instructions

## Project Overview

A Python wrapper for the QLab OSC API designed for theatrical productions. This project bridges theater tech workflows by:

- Controlling QLab (lighting/sound cue software) via OSC over TCP
- Parsing Fountain screenplay format scripts to generate audio cue lists
- Synchronizing CSV-exported cue lists from external tools back into QLab
- Managing character-based microphone muting/unmuting based on script dialogue flow

## Architecture

### Core Components

- **`qlab/osc.py`**: Low-level OSC 1.1 TCP/SLIP protocol implementation with `Client` and `Server` classes
- **`qlab/qlab.py`**: High-level `QLab` API wrapper providing convenient methods like `go()`, `cue()`, `get_cue_property()`
- **`qlab/cues.py`**: Cuelist synchronization engine that maps CSV exports to QLab network cues with layer-specific routing

### Key Data Flow

1. **Script Analysis** (`mutes.ipynb`): Fountain script → character dialogue tracking → CSV of mute/unmute cues
2. **Cuelist Sync** (`cues.ipynb`): CSV cue list → QLab network cues with OSC routing per layer (Lights/Sound/Video)
3. **Real-time Control** (`qlab.ipynb`): Direct QLab manipulation via OSC for show operation

## Development Workflows

### Environment Setup

```bash
uv sync  # Install dependencies (uses uv for fast resolution)
```

### Running Notebooks

All primary workflows are Jupyter notebooks - run cells sequentially:

- **`mutes.ipynb`**: Generate character muting cues from Fountain script
- **`cues.ipynb`**: Sync CSV cue list to QLab (requires QLab running locally)
- **`qlab.ipynb`**: Interactive QLab control

### Dependencies

- **`fountain`**: Installed from git (`git+https://github.com/Tagirijus/fountain`) - parses Fountain screenplay format
- **`python-osc`**: OSC protocol library (we implement custom TCP SLIP encoding on top)
- **`pydantic`**: Data modeling for `Cue` and `QLabCue` types

## Project-Specific Conventions

### OSC Protocol Quirks

- QLab uses **OSC 1.1 over TCP with SLIP encoding** (RFC 1055), not standard UDP OSC
- Messages must be SLIP-encoded via `slip()` function before sending
- Responses are JSON-like dicts parsed from OSC replies via `tcpParse()`
- Always call `/alwaysReply 1` before operations to ensure QLab responds

### Cue Numbering System

Layer-specific prefixes identify cue types:

- `s{number}` = Sound layer (blue, routes to network patch 2)
- `v{number}` = Video layer (purple)
- `a{number}` = Audio layer (cyan)
- `{number}` = Lights layer (orange, routes to network patch 1 for EOS console)

Example: `s42` is Sound cue 42, sends OSC `/jump 42` to sound playback system.

### Cuelist Synchronization Pattern

When syncing CSV to QLab (`Cues.sync_cuelist()`):

1. Reads CSV with columns: `Page Number`, `Layer Title`, `Cue Number`, `Label`, `Work Note`
2. Converts to `QLabCue` models with layer-specific properties
3. Updates existing cues by number OR creates new cues after previous UUID
4. Sets `colorName`, `customString` (OSC routing), and `networkPatchNumber` per layer

### Character Microphone Management

The `mutes.ipynb` workflow (`speaks_within()` function):

- Tracks active characters in a set as script is parsed
- Generates "unmute" cue when character first speaks
- Generates "mute" cue when character won't speak for next 7 dialogue blocks OR scene changes
- Character names from `characters.py` map to MIDI/OSC channels for mixer control

## Integration Points

### QLab Connection

- Default: `localhost:53000` (QLab's standard OSC port)
- Must have QLab workspace open before running cue operations
- Connection is persistent TCP - reuse `QLab()` instance across operations

### External Systems

- **EOS Lighting Console**: Network cues on patch 1 send `/eos/cue/{number}/fire`
- **Sound Playback**: Network cues on patch 2 send `/jump {number}`
- **Character Mixer**: MIDI channels defined in `characters.py` (DCA and channel assignments)

### File Dependencies

- Fountain scripts expected in `../seussical/scripts/` relative path
- CSV exports manually generated from external cuelist software (e.g., CueList app)
- Generated `cues.csv` contains character mute/unmute cues for import

## Common Patterns

### Querying QLab Properties

```python
q = QLab()
text = q.get_cue_property('42', 'text')  # Get specific property
uuid = q.get_cue_property('42', 'uniqueID')  # UUIDs for cue_id operations
```

### Creating Cues Programmatically

```python
cue = QLabCue(number='s100', name='Music Start', type='Network', layer='Sound')
cues.create_cue(cue, previous_uuid)  # Inserts after previous cue
```

### Parsing Scripts

```python
import fountain
with open('script.fountain', 'r') as f:
    f = fountain.Fountain(f.read())
    f.parse()
    # f.elements is list of Character/Dialogue/Scene Heading elements
```

## Notes

- This is production code for "Seussical" at El Camino High School (Fall 2025)
- Notebook-first development: Most functionality lives in `.ipynb` files, not `.py` modules
- Error handling is minimal - assumes QLab is running and responsive
- UUIDs are strings but represent QLab's unique cue identifiers for `cue_id` operations

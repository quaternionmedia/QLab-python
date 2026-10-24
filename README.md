# QLab-python

A Python wrapper for the QLab OSC API with SQLite database integration for theatrical production cue management.

## Features

- **OSC Control**: Low-level OSC 1.1 TCP/SLIP protocol implementation
- **QLab API**: High-level wrapper for QLab operations (go, stop, cue manipulation)
- **Script Parsing**: Parse Fountain screenplay format to generate audio cue lists
- **Database Integration**: Store and manage cues in SQLite databases compatible with theatre mixing applications
- **Character Management**: Automatic character microphone muting/unmuting based on dialogue flow
- **Cuelist Sync**: Synchronize CSV-exported cue lists back into QLab

## Quick Start

### Installation

```bash
uv sync
```

### Basic QLab Control

```python
from qlab.qlab import QLab

q = QLab()
q.go()  # Trigger next cue
text = q.get_cue_property('42', 'text')
```

### Database Integration

```python
from qlab.database import CueDatabase

# Create or open a database
with CueDatabase('my_show.sqlite') as db:
    # Add a cue with DCA assignments
    point = db.add_cue(
        name="Scene 1 Opening",
        dca_channels={1: "1,2,3"},
        dca_labels={1: "Principals"},
        qlab_cue="s100",
    )
    
    # Add character mute/unmute cues
    db.add_unmute_cue("Hamlet", channels="1", line_preview="To be...")
```

See [Database Integration Documentation](docs/database_integration.md) for details.

### Script-Based Cue Generation

Use the `mutes_db.ipynb` notebook to:
1. Parse Fountain screenplay scripts
2. Generate character mute/unmute cues automatically
3. Store cues in SQLite database
4. Export to CSV for compatibility

## Project Structure

- `qlab/osc.py` - OSC 1.1 TCP/SLIP protocol implementation
- `qlab/qlab.py` - High-level QLab API wrapper
- `qlab/cues.py` - Cuelist synchronization engine
- `qlab/database.py` - SQLite database integration
- `mutes.ipynb` - Script parsing for character muting (CSV export)
- `mutes_db.ipynb` - Script parsing with database storage
- `cues.ipynb` - Cuelist synchronization to QLab
- `qlab.ipynb` - Interactive QLab control

## Documentation

- [Database Integration Guide](docs/database_integration.md)
- [Example Database](mix/SheKillsMonsters.sqlite)
- [Standalone Example](examples/database_example.py)

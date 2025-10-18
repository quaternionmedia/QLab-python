# SQLite Database Integration for QLab Cue Management

This module provides SQLite database integration for managing theatre production cues, compatible with mixing console applications.

## Overview

The `qlab.database` module allows you to:
- Store and manage cues in a SQLite database
- Generate character mute/unmute cues from Fountain scripts
- Integrate with existing theatre mixing databases
- Link QLab cues with channel/DCA assignments

## Database Schema

The system uses a SQLite database with the following key tables:

### `cues` Table
- `number` (INTEGER): Cue number
- `point` (INTEGER): Cue point (auto-increments by 10)
- `name` (TEXT): Cue description
- `dca01Channels` through `dca12Channels` (TEXT): Channel assignments for DCAs 1-12
- `dca01Label` through `dca12Label` (TEXT): Labels for DCAs 1-12
- `qLabCue` (TEXT): Reference to QLab cue
- `colour` (INTEGER): Color code
- `channelFX`, `fxMutes`, `snippets` (TEXT): Additional configuration

### `profiles` Table
- `id` (INTEGER): Profile ID
- `channel` (INTEGER): Channel number
- `name` (TEXT): Character/profile name
- `label` (TEXT): Display label
- `default` (INTEGER): Default status

## Quick Start

### Basic Usage

```python
from qlab.database import CueDatabase

# Create or open a database
with CueDatabase('my_show.sqlite') as db:
    # Add a basic cue
    point = db.add_cue(
        name="Scene 1 Opening",
        dca_channels={1: "1,2,3"},  # DCA 1 controls channels 1, 2, and 3
        dca_labels={1: "Principals"},
        colour=5,
    )
    print(f"Created cue at point {point}")
```

### Character Mute/Unmute Cues

```python
# Add unmute cue for a character
point = db.add_unmute_cue(
    character="Hamlet",
    channels="1",
    line_preview="To be, or not to be...",
    dca=1,
)

# Add mute cue
point = db.add_mute_cue(
    character="Hamlet",
    channels="1",
    line_preview="...that is the question.",
    dca=1,
)
```

### Querying Cues

```python
# Get all cues
all_cues = db.get_all_cues()

# Get specific cue
cue = db.get_cue(point=10)

# Update a cue
db.update_cue(point=10, name="Updated Name", colour=7)

# Delete a cue
db.delete_cue(point=10)
```

### Working with Profiles

```python
# Get character's channel number
channel = db.get_channel_for_character("Hamlet")

# Get all profiles
profiles = db.get_profiles()
```

## Script Integration Workflow

The `mutes_db.ipynb` notebook demonstrates the complete workflow:

1. **Parse Fountain Script**: Load screenplay and extract character dialogue
2. **Generate Cue List**: Automatically create mute/unmute cues based on dialogue flow
3. **Store in Database**: Save cues to SQLite with proper channel assignments
4. **Export to CSV**: Legacy CSV export for compatibility

### Notebook Cells Overview

```python
# 1. Load script
from fountain import fountain
from qlab.database import CueDatabase

with open('script.fountain', 'r') as file:
    f = fountain.Fountain(file.read())
    f.parse()

# 2. Generate cues
cues = []
active = set()
for element in f.elements:
    if element.element_type == 'Character':
        # Generate unmute/mute cues
        # (see notebook for full logic)

# 3. Save to database
with CueDatabase('show.sqlite') as db:
    for cue_type, character, line in cues:
        if cue_type == 'mute':
            db.add_mute_cue(character, channels, line)
        else:
            db.add_unmute_cue(character, channels, line)
```

## Example Database

An example database is included at `mix/SheKillsMonsters.sqlite` showing:
- Multi-DCA cue assignments
- Character profiles with channel mappings
- QLab cue references
- Color coding system

## API Reference

### CueDatabase Class

#### `__init__(db_path: str)`
Initialize database connection.

#### `add_cue(name, dca_channels=None, dca_labels=None, qlab_cue=None, colour=0, ...) -> int`
Add a new cue to the database. Returns the cue point number.

**Parameters:**
- `name` (str): Cue name/description
- `dca_channels` (dict): Dict mapping DCA number (1-12) to channel list string
- `dca_labels` (dict): Dict mapping DCA number (1-12) to label string
- `qlab_cue` (str): QLab cue reference
- `colour` (int): Color code
- `number` (int): Cue number (auto-generated if None)
- `point` (int): Cue point (auto-generated if None)

#### `add_mute_cue(character, channels, line_preview, qlab_cue=None, dca=None) -> int`
Add a character mute cue.

#### `add_unmute_cue(character, channels, line_preview, qlab_cue=None, dca=None) -> int`
Add a character unmute cue.

#### `get_cue(point: int) -> dict`
Get a cue by its point number.

#### `get_all_cues() -> List[dict]`
Get all cues ordered by point.

#### `update_cue(point: int, **kwargs)`
Update a cue's fields.

#### `delete_cue(point: int)`
Delete a cue by point number.

#### `get_channel_for_character(character: str) -> int`
Get the channel number for a character from profiles.

## Integration with QLab

Cues can reference QLab cues using the `qlab_cue` parameter:

```python
# Create cue linked to QLab sound cue
db.add_cue(
    name="Music Underscore",
    qlab_cue="s42",  # QLab sound cue 42
    dca_channels={8: "8"},
)

# Link character unmute to QLab network cue
db.add_unmute_cue(
    character="Hero",
    channels="1",
    line_preview="I'm ready!",
    qlab_cue="a10",  # QLab audio cue 10
)
```

The QLab system can then trigger these cues via OSC when the corresponding QLab cue fires.

## Best Practices

1. **Use Context Manager**: Always use `with CueDatabase(path) as db:` to ensure proper connection handling
2. **Auto-increment Points**: Let the system auto-generate cue points (increments by 10) for easy insertion of cues between existing ones
3. **Character Profiles**: Populate the `profiles` table first to enable automatic channel lookup
4. **Color Coding**: Use consistent color codes across your production (e.g., 0=default, 5=important, 7=warning)
5. **QLab References**: Use the same cue numbering convention (s=sound, v=video, a=audio, etc.) for consistency

## Files

- `qlab/database.py`: Main database module
- `mutes_db.ipynb`: Notebook for script-to-database workflow
- `examples/database_example.py`: Standalone example script
- `mix/SheKillsMonsters.sqlite`: Example database

## Requirements

- Python 3.7+
- sqlite3 (included in Python standard library)
- fountain (for script parsing)

## See Also

- [QLab OSC Documentation](qlab/osc.py)
- [Cue Synchronization](qlab/cues.py)
- [Character Definitions](characters.py)

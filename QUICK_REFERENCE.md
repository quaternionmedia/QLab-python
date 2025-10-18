# Quick Reference: Database Integration

## Import

```python
from qlab import CueDatabase
# or
from qlab.database import CueDatabase
```

## Basic Usage

### Create/Open Database
```python
# Context manager (recommended)
with CueDatabase('show.sqlite') as db:
    # Do work
    pass

# Manual
db = CueDatabase('show.sqlite')
# Do work
db.close()
```

### Add Cues

```python
# Basic cue
point = db.add_cue(
    name="Scene 1 Opening",
    colour=5
)

# Cue with DCA assignments
point = db.add_cue(
    name="Multi-channel scene",
    dca_channels={1: "1,2,3", 8: "8"},
    dca_labels={1: "Principals"},
    qlab_cue="s100",
    colour=5
)

# Character unmute
point = db.add_unmute_cue(
    character="Hamlet",
    channels="1",
    line_preview="To be...",
    dca=1
)

# Character mute
point = db.add_mute_cue(
    character="Hamlet",
    channels="1",
    line_preview="...question",
    dca=1
)
```

### Query Cues

```python
# Get specific cue
cue = db.get_cue(point=10)

# Get all cues
all_cues = db.get_all_cues()

# Get next available cue number
num, point = db.get_next_cue_number()
```

### Update/Delete

```python
# Update cue
db.update_cue(point=10, name="New Name", colour=7)

# Delete cue
db.delete_cue(point=10)
```

### Profiles

```python
# Get all profiles
profiles = db.get_profiles()

# Get channel for character
channel = db.get_channel_for_character("Hamlet")
```

## Script Workflow (Jupyter)

```python
# Cell 1: Imports
from fountain import fountain
from qlab import CueDatabase

# Cell 2: Parse script
with open('../seussical/scripts/seussical.fountain', 'r') as f:
    script = fountain.Fountain(f.read())
    script.parse()

# Cell 3: Generate cues
cues = []
# ... generate cue list from script ...

# Cell 4: Save to database
with CueDatabase('show.sqlite') as db:
    for cue_type, character, line in cues:
        channel = db.get_channel_for_character(character)
        if cue_type == 'mute':
            db.add_mute_cue(character, str(channel), line)
        else:
            db.add_unmute_cue(character, str(channel), line)
```

## Common Patterns

### Pattern: Auto-assign channels from profiles
```python
with CueDatabase('show.sqlite') as db:
    for character in characters:
        channel = db.get_channel_for_character(character)
        if channel:
            db.add_unmute_cue(character, str(channel), line_preview)
```

### Pattern: Batch cue creation
```python
cue_list = [
    {"name": "Cue 1", "colour": 5},
    {"name": "Cue 2", "colour": 7},
]

with CueDatabase('show.sqlite') as db:
    for cue_data in cue_list:
        db.add_cue(**cue_data)
```

### Pattern: QLab integration
```python
# Link cue to QLab sound cue
db.add_cue(
    name="Music starts",
    qlab_cue="s42",  # Sound cue 42
    dca_channels={8: "8"}
)
```

## DCA Channel Format

- String of comma-separated channel numbers
- Examples: `"1"`, `"1,2,3"`, `"8,9,10,11,12"`
- DCA numbers: 1-12
- Assign via dict: `{1: "1,2", 3: "5,6"}`

## Color Codes

Standard convention:
- `0` - Default/normal
- `5` - Important/highlight
- `7` - Warning/special
- `9` - Testing/temporary

## File Locations

- Database module: `qlab/database.py`
- Example database: `mix/SheKillsMonsters.sqlite`
- Full docs: `docs/database_integration.md`
- Examples: `examples/database_example.py`
- Tests: `tests/test_database_integration.py`
- Enhanced notebook: `mutes_db.ipynb`

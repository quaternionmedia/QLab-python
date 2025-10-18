# SQLite Database Integration - Summary

## What Was Created

### Core Module: `qlab/database.py`
A comprehensive database integration module that provides:
- `CueDatabase` class for managing cues in SQLite
- Automatic schema creation for new databases
- Methods for adding, querying, updating, and deleting cues
- Support for character mute/unmute cues
- DCA (Digital Control Assignment) channel management
- Profile/character channel lookup

### Enhanced Notebook: `mutes_db.ipynb`
An updated version of the mutes notebook that:
- Parses Fountain screenplay scripts
- Generates character mute/unmute cues
- Saves cues to SQLite database (not just CSV)
- Looks up channel numbers from profiles
- Provides both legacy CSV export and modern database storage

### Documentation: `docs/database_integration.md`
Complete documentation including:
- Database schema reference
- API documentation
- Usage examples
- Integration patterns with QLab
- Best practices

### Examples
1. `examples/database_example.py` - Standalone Python script demonstrating:
   - Creating databases
   - Adding cues with DCA assignments
   - Querying and updating cues
   - Character mute/unmute workflow

2. `tests/test_database_integration.py` - Integration tests covering:
   - Basic CRUD operations
   - Character profile integration
   - DCA channel assignments

### Updated Files
- `README.md` - Added database integration section

## Key Features

### 1. Automatic Schema Creation
When creating a new database, the schema is automatically initialized with all required tables:
- `cues` - Main cue storage with 12 DCA channels
- `profiles` - Character/channel mappings
- `config`, `positions`, `ensembles`, `actors`, etc. - Supporting tables

### 2. Character Profile Integration
The system can look up channel numbers from the profiles table:
```python
channel = db.get_channel_for_character("Hamlet")
# Automatically assigns correct channel when creating mute/unmute cues
```

### 3. DCA Channel Management
Supports up to 12 DCAs with flexible channel assignments:
```python
db.add_cue(
    name="Multi-channel scene",
    dca_channels={
        1: "1,2,3",      # DCA 1 controls channels 1, 2, 3
        8: "8",          # DCA 8 controls channel 8
        12: "11,12",     # DCA 12 controls channels 11, 12
    },
    dca_labels={1: "Principals"},
)
```

### 4. QLab Integration
Cues can reference QLab cues for synchronized control:
```python
db.add_cue(
    name="Music underscore",
    qlab_cue="s100",  # References QLab sound cue 100
)
```

### 5. Script-to-Database Workflow
The enhanced `mutes_db.ipynb` notebook provides a complete workflow:
1. Load Fountain script
2. Parse character dialogue
3. Generate mute/unmute cues automatically
4. Look up channel numbers from profiles
5. Save to database with proper assignments

## Database Schema Compatibility

The database schema is compatible with the example `SheKillsMonsters.sqlite` database, which represents a real theatre mixing application. This means:
- Existing databases can be used directly
- Cues integrate seamlessly with existing workflows
- No migration needed for existing projects

## Usage Patterns

### Pattern 1: Script-Based Cue Generation
```python
from fountain import fountain
from qlab.database import CueDatabase

# Parse script
with open('script.fountain') as f:
    script = fountain.Fountain(f.read())
    script.parse()

# Generate and save cues
with CueDatabase('show.sqlite') as db:
    for character, line in dialogue_cues:
        db.add_unmute_cue(character, channels, line)
```

### Pattern 2: Manual Cue Creation
```python
with CueDatabase('show.sqlite') as db:
    db.add_cue(
        name="Act 1 Opening",
        dca_channels={1: "1,2,3,4"},
        qlab_cue="s10",
        colour=5,
    )
```

### Pattern 3: Batch Operations
```python
with CueDatabase('show.sqlite') as db:
    for i, cue_data in enumerate(cue_list):
        db.add_cue(**cue_data)
    
    # All cues committed in one transaction
```

## Next Steps

To use this integration in your production:

1. **Review the example database**: Open `mix/SheKillsMonsters.sqlite` to understand the schema
2. **Run the example script**: Execute `examples/database_example.py` to see basic usage
3. **Try the notebook**: Open `mutes_db.ipynb` and run through the workflow
4. **Populate profiles**: Add your character/channel mappings to the profiles table
5. **Generate cues**: Use the script parsing workflow to build your cue list

## Testing

All integration tests pass:
```
Testing basic database operations... ✓
Testing character profile integration... ✓
Testing DCA assignments... ✓

Results: 3 passed, 0 failed
```

Run tests with:
```bash
python tests/test_database_integration.py
```

## Files Added

```
qlab/database.py                    - Core database module
mutes_db.ipynb                      - Enhanced script parsing notebook
docs/database_integration.md        - Complete documentation
examples/database_example.py        - Usage examples
tests/test_database_integration.py  - Integration tests
```

## Files Modified

```
README.md  - Added database integration section
```

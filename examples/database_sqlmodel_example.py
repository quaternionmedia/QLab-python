#!/usr/bin/env python3
"""Example of using SQLModel-based CueDatabase for script-based cue generation."""

from qlab.database_sqlmodel import CueDatabase
from qlab.models import Cue, Profile
from pathlib import Path


def main():
    # Example 1: Create a new database with SQLModel
    print("Example 1: Basic cue creation with SQLModel")
    print("-" * 50)
    
    db_path = "example_sqlmodel_cues.sqlite"
    
    with CueDatabase(db_path, init_config=True) as db:
        # Add some basic cues
        point1 = db.add_cue(
            name="Opening Scene",
            dca_channels={1: "1,2,3"},
            dca_labels={1: "Principals"},
            colour=5,
        )
        print(f"Created cue at point {point1}")
        
        point2 = db.add_unmute_cue(
            character="Hero",
            channels="1",
            line_preview="I am the hero of this story...",
            dca=1,
        )
        print(f"Created unmute cue at point {point2}")
        
        point3 = db.add_mute_cue(
            character="Hero",
            channels="1",
            line_preview="...and that's the end of my tale.",
            dca=1,
        )
        print(f"Created mute cue at point {point3}")
    
    # Example 2: Query the database with SQLModel objects
    print("\n\nExample 2: Querying cues (returns SQLModel objects)")
    print("-" * 50)
    
    with CueDatabase(db_path, create_schema=False) as db:
        all_cues = db.get_all_cues()
        print(f"Total cues in database: {len(all_cues)}")
        
        for cue in all_cues:
            # cue is a Cue SQLModel object with full type hints
            print(f"  Cue {cue.number}.{cue.point}: {cue.name}")
            
            # Can convert to dict
            cue_dict = cue.model_dump()
            print(f"    Color: {cue.colour}, QLab: {cue.qLabCue}")
    
    # Example 3: Update and work with SQLModel objects
    print("\n\nExample 3: Working with SQLModel objects")
    print("-" * 50)
    
    with CueDatabase(db_path, create_schema=False) as db:
        # Get cue as SQLModel object
        cue = db.get_cue(point1)
        print(f"Retrieved cue: {cue.name}")
        print(f"  Type: {type(cue)}")
        print(f"  Point: {cue.point}")
        print(f"  DCA 1 Channels: {cue.dca01Channels}")
        print(f"  DCA 1 Label: {cue.dca01Label}")
        
        # Update the cue
        db.update_cue(point1, name="UPDATED: Opening Scene", colour=7)
        updated = db.get_cue(point1)
        print(f"\nUpdated cue: {updated.name} (colour: {updated.colour})")
    
    # Example 4: Configuration management
    print("\n\nExample 4: Configuration management")
    print("-" * 50)
    
    with CueDatabase(db_path, create_schema=False) as db:
        # Get config values
        designer = db.get_config("designer")
        console = db.get_config("targetConsole")
        print(f"Designer: {designer}")
        print(f"Console: {console}")
        
        # Update config
        db.set_config("designer", "My Name")
        db.set_config("venue", "My Theatre")
        
        # Get all config
        all_config = db.get_all_config()
        print(f"\nTotal config entries: {len(all_config)}")
        print(f"Designer is now: {all_config['designer']}")
        print(f"Venue is now: {all_config['venue']}")
    
    print(f"\n\nExample database saved to: {db_path}")
    print("\nSQLModel Benefits:")
    print("  ✓ Type-safe database operations")
    print("  ✓ Returns Python objects instead of dicts")
    print("  ✓ Automatic validation")
    print("  ✓ IDE autocomplete support")
    print("  ✓ Easy conversion to/from JSON")


if __name__ == "__main__":
    main()

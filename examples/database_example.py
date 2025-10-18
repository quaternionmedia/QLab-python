#!/usr/bin/env python3
"""Example of using the CueDatabase for script-based cue generation."""

from qlab.database import CueDatabase
from pathlib import Path


def main():
    # Example 1: Create a new database and add basic cues
    print("Example 1: Basic cue creation")
    print("-" * 50)

    db_path = "example_cues.sqlite"

    with CueDatabase(db_path) as db:
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

    # Example 2: Query the database
    print("\n\nExample 2: Querying cues")
    print("-" * 50)

    with CueDatabase(db_path) as db:
        all_cues = db.get_all_cues()
        print(f"Total cues in database: {len(all_cues)}")

        for cue in all_cues:
            print(f"  Cue {cue['number']}.{cue['point']}: {cue['name']}")

    # Example 3: Update existing cue
    print("\n\nExample 3: Updating a cue")
    print("-" * 50)

    with CueDatabase(db_path) as db:
        db.update_cue(point1, name="UPDATED: Opening Scene", colour=7)
        updated = db.get_cue(point1)
        print(f"Updated cue {point1}: {updated['name']} (colour: {updated['colour']})")

    print(f"\n\nExample database saved to: {db_path}")


if __name__ == "__main__":
    main()

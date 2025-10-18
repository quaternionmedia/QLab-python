"""SQLite database integration for QLab cue management."""

import sqlite3
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path


class CueDatabase:
    """Manages cue data in SQLite database compatible with theatre mixing applications."""

    def __init__(self, db_path: str, create_schema: bool = True):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
            create_schema: If True, create schema if it doesn't exist
        """
        self.db_path = Path(db_path)
        is_new = not self.db_path.exists()

        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        if create_schema and is_new:
            self._create_schema()

    def _create_schema(self):
        """Create database schema for a new database."""
        # Create config table
        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS config (
                param TEXT PRIMARY KEY,
                value TEXT
            )
        '''
        )

        # Create cues table
        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS cues (
                number INTEGER,
                point INTEGER PRIMARY KEY,
                name TEXT,
                dca01Channels TEXT,
                dca02Channels TEXT,
                dca03Channels TEXT,
                dca04Channels TEXT,
                dca05Channels TEXT,
                dca06Channels TEXT,
                dca07Channels TEXT,
                dca08Channels TEXT,
                dca01Label TEXT,
                dca02Label TEXT,
                dca03Label TEXT,
                dca04Label TEXT,
                dca05Label TEXT,
                dca06Label TEXT,
                dca07Label TEXT,
                dca08Label TEXT,
                channelPositions TEXT,
                channelProfiles TEXT,
                fxMutes TEXT,
                channelFX TEXT,
                snippets TEXT,
                qLabCue TEXT,
                channelLevels TEXT,
                scenes TEXT,
                colour INTEGER DEFAULT 0,
                scenePoints TEXT,
                dca09Channels TEXT,
                dca09Label TEXT,
                dca10Channels TEXT,
                dca10Label TEXT,
                dca11Channels TEXT,
                dca11Label TEXT,
                dca12Channels TEXT,
                dca12Label TEXT
            )
        '''
        )

        # Create profiles table
        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel INTEGER,
                name TEXT,
                label TEXT,
                "default" INTEGER DEFAULT 1,
                data TEXT
            )
        '''
        )

        # Create other supporting tables
        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                shortName TEXT,
                delay NUMERIC,
                pan NUMERIC,
                buses TEXT
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS ensembles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                channels TEXT,
                channelProfiles TEXT
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS actors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel INTEGER,
                name TEXT,
                "order" INTEGER,
                active INTEGER DEFAULT 1
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS actorProfiles (
                actor INTEGER,
                profile INTEGER,
                data TEXT
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS actorGroups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                data TEXT
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS snippetCache (
                snippet INTEGER,
                name TEXT
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS fxCache (
                fx INTEGER,
                name TEXT
            )
        '''
        )

        self.cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS sceneCache (
                scene INTEGER,
                point INTEGER,
                name TEXT
            )
        '''
        )

        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def get_next_cue_number(self) -> Tuple[int, int]:
        """Get the next available cue number and point.

        Returns:
            Tuple of (number, point) where point is incremented by 10
        """
        self.cursor.execute(
            "SELECT MAX(number) as max_num, MAX(point) as max_point FROM cues"
        )
        row = self.cursor.fetchone()

        max_num = row['max_num'] if row['max_num'] is not None else 0
        # max_point = row['max_point'] if row['max_point'] is not None else 0

        return (max_num + 1, 0)

    def add_cue(
        self,
        name: str,
        dca_channels: Optional[Dict[int, str]] = None,
        dca_labels: Optional[Dict[int, str]] = None,
        qlab_cue: Optional[str] = None,
        colour: int = 0,
        channel_fx: Optional[str] = None,
        fx_mutes: Optional[str] = None,
        snippets: Optional[str] = None,
        number: Optional[int] = None,
        point: Optional[int] = None,
    ) -> int:
        """Add a new cue to the database.

        Args:
            name: Cue name/description
            dca_channels: Dict mapping DCA number (1-12) to channel list string (e.g., "1,2,3")
            dca_labels: Dict mapping DCA number (1-12) to label string
            qlab_cue: QLab cue reference
            colour: Color code (integer)
            channel_fx: Channel FX configuration string
            fx_mutes: FX mute configuration string
            snippets: Snippet configuration string
            number: Cue number (auto-generated if None)
            point: Cue point (auto-generated if None, increments by 10)

        Returns:
            The cue point that was inserted
        """
        if number is None or point is None:
            auto_num, auto_point = self.get_next_cue_number()
            if number is None:
                number = auto_num
            if point is None:
                point = 0  # auto_point

        # Build DCA channel columns
        dca_channel_cols = {}
        for i in range(1, 13):
            col_name = f'dca{i:02d}Channels'
            dca_channel_cols[col_name] = dca_channels.get(i, '') if dca_channels else ''

        # Build DCA label columns
        dca_label_cols = {}
        for i in range(1, 13):
            col_name = f'dca{i:02d}Label'
            dca_label_cols[col_name] = dca_labels.get(i) if dca_labels else None

        columns = [
            'number',
            'point',
            'name',
            'colour',
            'qLabCue',
            'channelFX',
            'fxMutes',
            'snippets',
        ]
        values = [number, point, name, colour, qlab_cue, channel_fx, fx_mutes, snippets]

        # Add DCA columns
        for col, val in dca_channel_cols.items():
            columns.append(col)
            values.append(val)
        for col, val in dca_label_cols.items():
            columns.append(col)
            values.append(val)

        placeholders = ','.join(['?' for _ in values])
        sql = f"INSERT INTO cues ({','.join(columns)}) VALUES ({placeholders})"

        self.cursor.execute(sql, values)
        self.conn.commit()

        return point

    def add_mute_cue(
        self,
        character: str,
        channels: str,
        line_preview: str,
        qlab_cue: Optional[str] = None,
        dca: Optional[int] = None,
    ) -> int:
        """Add a character mute cue.

        Args:
            character: Character name to mute
            channels: Comma-separated channel numbers (e.g., "1,2,3")
            line_preview: Preview of dialogue line
            qlab_cue: Associated QLab cue reference
            dca: DCA number to assign channels to (1-12), if any

        Returns:
            The cue point that was inserted
        """
        name = f"mute {character}"
        dca_channels = {dca: channels} if dca else None

        return self.add_cue(
            name=name,
            dca_channels=dca_channels,
            qlab_cue=qlab_cue,
            colour=0,  # Default color
        )

    def add_unmute_cue(
        self,
        character: str,
        channels: str,
        line_preview: str,
        qlab_cue: Optional[str] = None,
        dca: Optional[int] = None,
    ) -> int:
        """Add a character unmute cue.

        Args:
            character: Character name to unmute
            channels: Comma-separated channel numbers (e.g., "1,2,3")
            line_preview: Preview of dialogue line
            qlab_cue: Associated QLab cue reference
            dca: DCA number to assign channels to (1-12), if any

        Returns:
            The cue point that was inserted
        """
        name = f"unmute {character}"
        dca_channels = {dca: channels} if dca else None

        return self.add_cue(
            name=name,
            dca_channels=dca_channels,
            qlab_cue=qlab_cue,
            colour=0,  # Default color
        )

    def get_cue(self, point: int) -> Optional[Dict[str, Any]]:
        """Get a cue by its point number.

        Args:
            point: Cue point number

        Returns:
            Dictionary of cue data or None if not found
        """
        self.cursor.execute("SELECT * FROM cues WHERE point = ?", (point,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_all_cues(self) -> List[Dict[str, Any]]:
        """Get all cues ordered by point.

        Returns:
            List of cue dictionaries
        """
        self.cursor.execute("SELECT * FROM cues ORDER BY point")
        return [dict(row) for row in self.cursor.fetchall()]

    def update_cue(self, point: int, **kwargs):
        """Update a cue's fields.

        Args:
            point: Cue point to update
            **kwargs: Field names and values to update
        """
        set_clause = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [point]

        sql = f"UPDATE cues SET {set_clause} WHERE point = ?"
        self.cursor.execute(sql, values)
        self.conn.commit()

    def delete_cue(self, point: int):
        """Delete a cue by point number.

        Args:
            point: Cue point to delete
        """
        self.cursor.execute("DELETE FROM cues WHERE point = ?", (point,))
        self.conn.commit()

    def get_profiles(self) -> List[Dict[str, Any]]:
        """Get all channel profiles.

        Returns:
            List of profile dictionaries with id, channel, name, label
        """
        self.cursor.execute("SELECT * FROM profiles ORDER BY channel")
        return [dict(row) for row in self.cursor.fetchall()]

    def get_profile_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a profile by character name.

        Args:
            name: Character/profile name

        Returns:
            Profile dictionary or None if not found
        """
        self.cursor.execute("SELECT * FROM profiles WHERE name = ?", (name,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_channel_for_character(self, character: str) -> Optional[int]:
        """Get the channel number for a character.

        Args:
            character: Character name

        Returns:
            Channel number or None if not found
        """
        profile = self.get_profile_by_name(character)
        return profile['channel'] if profile else None

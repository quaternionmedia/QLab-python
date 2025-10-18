"""SQLModel models for QLab cue database schema."""

from typing import Optional
from sqlmodel import Field, SQLModel


class Config(SQLModel, table=True):
    """Configuration key-value store."""

    param: str = Field(primary_key=True)
    value: Optional[str] = None


class Cue(SQLModel, table=True):
    """Main cue table with DCA assignments and metadata.

    Note: The actual SQLite table has no PRIMARY KEY constraint, but SQLModel
    requires one for ORM operations. We use (number, point) as a composite key.
    """

    __tablename__ = "cues"

    number: int = Field(default=999, primary_key=True)
    point: int = Field(default=0, primary_key=True)
    name: Optional[str] = None

    # DCA channel assignments (comma-separated channel numbers)
    dca01Channels: Optional[str] = None
    dca02Channels: Optional[str] = None
    dca03Channels: Optional[str] = None
    dca04Channels: Optional[str] = None
    dca05Channels: Optional[str] = None
    dca06Channels: Optional[str] = None
    dca07Channels: Optional[str] = None
    dca08Channels: Optional[str] = None
    dca09Channels: Optional[str] = None
    dca10Channels: Optional[str] = None
    dca11Channels: Optional[str] = None
    dca12Channels: Optional[str] = None

    # DCA labels
    dca01Label: Optional[str] = None
    dca02Label: Optional[str] = None
    dca03Label: Optional[str] = None
    dca04Label: Optional[str] = None
    dca05Label: Optional[str] = None
    dca06Label: Optional[str] = None
    dca07Label: Optional[str] = None
    dca08Label: Optional[str] = None
    dca09Label: Optional[str] = None
    dca10Label: Optional[str] = None
    dca11Label: Optional[str] = None
    dca12Label: Optional[str] = None

    # Additional configuration
    channelPositions: Optional[str] = None
    channelProfiles: Optional[str] = None
    fxMutes: Optional[str] = None
    channelFX: Optional[str] = None
    snippets: Optional[str] = None
    qLabCue: Optional[str] = None
    channelLevels: Optional[str] = None
    scenes: Optional[str] = None
    colour: Optional[int] = None
    scenePoints: Optional[str] = None

    # DCA 9-12 (added to match actual schema)
    dca09Channels: Optional[str] = None
    dca09Label: Optional[str] = None
    dca10Channels: Optional[str] = None
    dca10Label: Optional[str] = None
    dca11Channels: Optional[str] = None
    dca11Label: Optional[str] = None
    dca12Channels: Optional[str] = None
    dca12Label: Optional[str] = None


class Profile(SQLModel, table=True):
    """Channel profiles for characters/actors."""

    __tablename__ = "profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel: Optional[int] = None
    name: Optional[str] = None
    label: Optional[str] = None
    default: int = Field(default=0, sa_column_kwargs={"name": "default"})
    data: Optional[str] = None


class Position(SQLModel, table=True):
    """Stage positions with acoustic properties."""

    __tablename__ = "positions"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    shortName: Optional[str] = None
    delay: Optional[float] = None
    pan: Optional[float] = None
    buses: Optional[str] = None


class Ensemble(SQLModel, table=True):
    """Ensemble/group definitions with channel assignments."""

    __tablename__ = "ensembles"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    channels: Optional[str] = None
    channelProfiles: Optional[str] = None


class Actor(SQLModel, table=True):
    """Actor/performer definitions."""

    __tablename__ = "actors"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel: Optional[int] = None
    name: Optional[str] = None
    order: int = Field(default=0, sa_column_kwargs={"name": "order"})
    active: int = Field(default=0)


class ActorProfile(SQLModel, table=True):
    """Actor-to-profile associations.

    Note: The actual SQLite table has no PRIMARY KEY constraint, but SQLModel
    requires one for ORM operations. We use (actor, profile) as a composite key.
    """

    __tablename__ = "actorProfiles"

    actor: Optional[int] = Field(default=None, primary_key=True)
    profile: Optional[int] = Field(default=None, primary_key=True)
    data: Optional[str] = None


class ActorGroup(SQLModel, table=True):
    """Actor group definitions."""

    __tablename__ = "actorGroups"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    data: Optional[str] = None


class SnippetCache(SQLModel, table=True):
    """Cache for mixer snippets."""

    __tablename__ = "snippetCache"

    snippet: int = Field(primary_key=True)
    name: Optional[str] = None


class FXCache(SQLModel, table=True):
    """Cache for effects."""

    __tablename__ = "fxCache"

    fx: int = Field(primary_key=True)
    name: Optional[str] = None


class SceneCache(SQLModel, table=True):
    """Cache for mixer scenes."""

    __tablename__ = "sceneCache"

    scene: int = Field(primary_key=True)
    point: int = Field(default=0)
    name: Optional[str] = None

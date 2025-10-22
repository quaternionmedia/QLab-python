from sqlmodel import Session, select
from fountain import fountain
import re

from qlab.models import Cue, Profile, Ensemble
from qlab.database_sqlmodel import CueDatabase

# from rich import print

DATABASE = 'mix/seuss7.tmix'


def open_script(
    file_path: str = '../seussical/scripts/seussical.fountain',
) -> fountain.Fountain:
    """Open and parse a Fountain script from a file path."""
    with open(file_path, 'r') as file:
        f = fountain.Fountain(file.read())
        f.parse()
    return f


def split_characters(characters: str) -> list[str]:
    """Clean and split character headings"""
    # Remove parenthesis
    characters = re.sub(r'\([^)]*\)', '', characters)
    # split the characters by '&'
    return characters.split(' & ')


def speaks_within(book, character, n: int = 7):
    """Check if character speaks within next n dialogue blocks or before scene change.

    Args:
        book: List of script elements to search
        character: Character name to look for
        n: Number of dialogue blocks to look ahead

    Returns:
        True if character speaks within window, False otherwise
    """
    dialogues = 0
    for i, element in enumerate(book):
        if dialogues >= n:
            return False
        if element.element_type == 'Scene Heading':
            return False
        if element.element_type == 'Character':
            characters = split_characters(element.element_text)
            if character in characters:
                return True
            dialogues += 1
    return False


def get_characters(script):
    characters = set()
    for element in script.elements:
        if element.element_type == 'Character':
            chars = split_characters(element.element_text)
            for char in chars:
                characters.add(char.strip())
    characters = sorted(list(characters))
    return characters


def get_line_preview_start(script, length=40):
    """Get a starting preview of the dialogue line following the character element"""
    # look for the next Dialogue element
    for i in range(len(script)):
        if script[i].element_type == 'Dialogue':
            line = script[i].element_text
            if len(line) > length:
                return line[:length] + '...'
            else:
                return line


def get_line_preview_end(script, length=40):
    """Get an ending preview of the dialogue line following the character element"""
    # look for the next Dialogue element from the end
    for i in range(len(script) - 1, -1, -1):
        if script[i].element_type == 'Dialogue':
            line = script[i].element_text
            if len(line) > length:
                return '...' + line[-length:]
            else:
                return line


def get_character_channels(db_path: str = DATABASE) -> dict[str, str]:
    """Load character to channel mapping from database.

    For individual characters, returns their single channel number.
    For ensemble groups, returns comma-separated list of all member channels.

    Args:
        db_path: Path to the .tmix database file

    Returns:
        Dictionary mapping character names to channel numbers (as strings)
    """
    db = CueDatabase(db_path, create_schema=False, init_config=False)
    character_channels = {}

    with Session(db.engine) as session:
        # Load characters from Profile table
        profiles = session.exec(select(Profile)).all()
        for profile in profiles:
            character_channels[profile.name.upper()] = str(profile.channel)

    return character_channels


def generate_dca_cues(script: fountain.Fountain, db_path: str = DATABASE) -> list[Cue]:
    """Generate the list of cues for DCA muting.

    This function parses a Fountain script and creates a list of Cue objects
    with DCA (Digital Control Assignment) assignments for character microphones.

    Logic:
    - Characters are unmuted when they first speak in a scene
    - Characters are muted when they won't speak within the next 7 dialogue blocks
    - Scene transitions mute all active characters (unless they speak first in new scene)
    - DCAs 1-12 are dynamically assigned and reused as characters are muted

    Args:
        script: Parsed Fountain script object
        db_path: Path to database file with character/channel mappings

    Returns:
        List of Cue objects with DCA assignments for muting/unmuting
    """
    # Load character to channel mapping from database
    character_channels = get_character_channels(db_path)

    cues = []
    active_mics = set()  # Characters currently unmuted
    # NOTE: DCA assignment strategy - currently dynamic reuse of available DCAs.
    # To implement consistent DCA per character, replace this with a character->DCA mapping dict
    dca_assignments = {}  # Maps character name -> DCA number (1-12)
    available_dcas = set(range(1, 13))  # DCAs 1-12 available for assignment
    page = 0
    cue_number = 1

    for i, element in enumerate(script.elements):
        # Track page numbers from comments
        if element.element_type == 'Comment':
            if re.match(r'^Page \d+$', element.element_text):
                page = int(re.search(r'\d+', element.element_text).group())
                continue

        # Handle scene transitions - mute all active characters
        if element.element_type == 'Scene Heading':
            # Check if any current active character speaks first in this scene
            first_speakers = set()
            remaining_script = script.elements[i + 1 :]
            for future_elem in remaining_script:
                if future_elem.element_type == 'Character':
                    chars = split_characters(future_elem.element_text)
                    first_speakers.update(char.strip() for char in chars)
                    break
                elif future_elem.element_type == 'Scene Heading':
                    break

            # Mute characters who won't speak first in new scene
            characters_to_mute = active_mics - first_speakers
            for character in characters_to_mute:
                dca_num = dca_assignments[character]

                # Get channel for this character
                channel = character_channels.get(character, '')

                # Create mute cue
                cue = Cue(
                    number=cue_number,
                    point=0,
                    name=f"p{page} - Scene Change - {get_line_preview_end(script.elements[:i], 30)}",
                )
                # Set the DCA channels and/or label
                # If character has channels, set them; if not (ensemble), set label only
                if channel:
                    setattr(cue, f'dca{dca_num:02d}Channels', str(channel))
                else:
                    setattr(cue, f'dca{dca_num:02d}Label', character)
                cues.append(cue)
                cue_number += 1

                # Free up the DCA and remove from active
                available_dcas.add(dca_num)
                del dca_assignments[character]
                active_mics.discard(character)

            continue

        # Handle character dialogue
        if element.element_type == 'Character':
            characters = split_characters(element.element_text)
            remaining_script = script.elements[i + 1 :]

            # Process each character in this dialogue block
            for character in characters:
                character = character.strip()

                # Unmute character if not already active
                if character not in active_mics:
                    # Assign an available DCA
                    if available_dcas:
                        dca_num = min(available_dcas)  # Use lowest available DCA
                        available_dcas.remove(dca_num)
                    else:
                        # All DCAs in use - reuse DCA 1 (fallback)
                        # This shouldn't happen with proper lookahead muting
                        dca_num = 1

                    dca_assignments[character] = dca_num

                    # Get channel for this character
                    channel = character_channels.get(character)

                    # Create unmute cue
                    cue = Cue(
                        number=cue_number,
                        point=0,
                        name=f"p{page} - unmute {character} {get_line_preview_start(remaining_script, 30)}",
                    )
                    # Set the DCA channels and/or label
                    # If character has channels, set them; if not (ensemble), set label only
                    if channel:
                        setattr(cue, f'dca{dca_num:02d}Channels', channel)
                    else:
                        setattr(cue, f'dca{dca_num:02d}Label', character)
                    cues.append(cue)
                    cue_number += 1

                    active_mics.add(character)

            # Check all currently active characters to see if they should be muted
            characters_to_mute = []
            for active_character in active_mics:
                # Check if this character speaks within the next 7 dialogue blocks
                if not speaks_within(remaining_script, active_character, n=7):
                    characters_to_mute.append(active_character)

            # Create mute cues for characters who won't speak soon
            for character in characters_to_mute:
                dca_num = dca_assignments[character]

                # Get channel for this character
                channel = character_channels.get(character, '')

                # Create mute cue
                cue = Cue(
                    number=cue_number,
                    point=0,
                    name=f"{page} - mute {character} {get_line_preview_end(remaining_script[:7], 30)}",
                )
                # Set the DCA channels and/or label (None clears the channels)
                # If character has channels, clear them; if not (ensemble), set label only
                if channel:
                    setattr(cue, f'dca{dca_num:02d}Channels', None)
                else:
                    setattr(cue, f'dca{dca_num:02d}Label', character)
                cues.append(cue)
                cue_number += 1

                # Free up the DCA and remove from active
                available_dcas.add(dca_num)
                del dca_assignments[character]
                active_mics.discard(character)

    return cues


if __name__ == '__main__':
    from rich import print

    script = open_script()
    cues = generate_dca_cues(script)
    print(f"Generated {len(cues)} DCA cues\n")
    # # Print first 10 cues as sample with DCA assignments
    for cue in cues[:10]:
        # Find which DCA is assigned
        dca_info = ""
        for dca_num in range(1, 13):
            channels = getattr(cue, f'dca{dca_num:02d}Channels', None)
            label = getattr(cue, f'dca{dca_num:02d}Label', None)
            if channels or label:
                dca_info = f"DCA{dca_num} Ch{channels}: {label}"
                break
        # print(f"Cue {cue.number}: {cue.name:40s} {dca_info}")
        print(cue)
    with Session(CueDatabase(DATABASE).engine) as session:
        session.add_all(cues)
        session.commit()

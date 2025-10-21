from fountain import fountain
import re

# from rich import print

from qlab.models import Cue


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
    for element in script:
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


def generate_dca_cues(script):
    """Generate the list of cues for DCA muting."""
    cues = []
    active_mics = set()
    page = 1

    for i, element in enumerate(script):
        # Get the page number
        if element.element_type == 'Comment':
            if re.match(r'^Page \d+$', element.element_text):
                page = int(re.search(r'\d+', element.element_text).group())
                # print(f"Page changed to {page}")
                continue
        # For every Character element
        if element.element_type == 'Character':
            characters = split_characters(element.element_text)
            for character in characters:
                character = character.strip()
                # If the character is not already active
                if character not in active_mics:

if __name__ == '__main__':
    script = open_script()
    characters = get_characters(script)
    for character in characters:
        print(character)

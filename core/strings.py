import random

COMMAND_PREFIX = "music "

STATUS_SEARCHING = "🔍"
ERROR_PREFIX = "❌ Error: "
ERROR_LONG_AUDIO = "Track is longer than 15 minutes."
ERROR_SEARCH_ALL_TOO_LONG = "All found tracks are longer than 15 minutes."
ERROR_TOO_LARGE = "File is larger than {} MB.".format(50)
ERROR_NO_RESULTS = "No results found."

TOO_FAST_CALLBACK = ""

BUTTON_REQUESTER = "🎵{}"
BUTTON_NOT_RIGHT = "🔎 Not the right song?"
BUTTON_CANCEL = "❌ Cancel"
UNTITLED_SONG = "Untitled Song"
UNKNOWN_VALUE = "unknown"
NOT_FOR_YOU = "❌ This button is not for you 💅"
SONG_UPDATED = "Song updated."
INFO_EXPIRED = "Information expired."
FAILED_TO_UPDATE = "Failed to update message: {}"


def get_song_info_message(data, views, likes, dislikes):
    """Generates the formatted song information message."""

    tagline = random.choice([
        "The oldest song found is a 3400-year-old hymn from Ugarit.",
        "A 40,000-year-old bird bone flute is considered the first instrument."
    ])

    year = data.get("upload_date", "")
    year = year[:4] if year else UNKNOWN_VALUE

    return (
        f"👤 Artist: {data.get('artist', UNKNOWN_VALUE)}\n"
        f"📅 Year: {year}\n"
        f"──────────────────\n"
        f"📈 Views: {views}\n"
        f" \n"
        f"👍 {likes}  👎 {dislikes}\n"
        f"──────────────────\n"
        f"{tagline}"
    )

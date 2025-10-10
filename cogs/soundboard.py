import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

#-----------------------
# soundboard.json format
#-----------------------
# guild id
#       title = ?
#           triggers = []
#           soundfile = filename
#           description = string
#           added by = discord mamber
#           added date = date
#           number of times played
#               week = int
#               month = int
#               total  = int
#-----------------------

#-----------------------
# To Add:
# load soundboard json
# view sounds and trigger Descriptions
# edit triggers (record transcribed word and text entry plus word removal)
# add triggers  (record transcribed word and text entry)
# upload sound
# remove sounds (admin)
# play sound
#-----------------------
from discord.ext import commands
import traceback

from base_cog import BaseCog, logger
@dataclass
class PlayStats:
    week: int = 0
    month: int = 0
    total: int = 0
    guild_play_count: Dict[str, int] = field(default_factory=dict)
    last_played: Optional[str] = None
    played_by: List[str] = field(default_factory=list)


@dataclass
class AudioMetadata:
    duration: Optional[float] = None
    format: Optional[str] = None
    bitrate: Optional[int] = None
    volume_adjust: float = 1.0


@dataclass
class SearchMetadata:
    tags: List[str] = field(default_factory=list)
    category: Optional[str] = None
    nsfw: bool = False
    aliases: List[str] = field(default_factory=list)
    emoji: Optional[str] = None


@dataclass
class SoundSettings:
    cooldown: int = 0
    autoplay: bool = False


@dataclass
class SoundEntry:
    title: str
    triggers: List[str]
    soundfile: str
    description: str
    added_by: str
    added_by_id: str
    added_date: str
    last_edited_by: Optional[str] = None
    is_private: bool = False
    is_disabled: bool = False
    approved: bool = True
    play_stats: PlayStats = field(default_factory=PlayStats)
    audio_metadata: AudioMetadata = field(default_factory=AudioMetadata)
    search_metadata: SearchMetadata = field(default_factory=SearchMetadata)
    settings: SoundSettings = field(default_factory=SoundSettings)


@dataclass
class GuildSoundboard:
    guild_id: str
    sounds: Dict[str, SoundEntry] = field(default_factory=dict)


# -------- Utility Functions --------

def load_soundboard(file_path: str) -> Dict[str, GuildSoundboard]:
    """Load the soundboard JSON into structured dataclasses."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    guilds = {}
    for guild_id, sounds in data.items():
        entries = {k: SoundEntry(**v) for k, v in sounds.items()}
        guilds[guild_id] = GuildSoundboard(guild_id, entries)
    return guilds


def save_soundboard(file_path: str, soundboard: Dict[str, GuildSoundboard]):
    """Save dataclasses back to JSON."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({gid: {k: asdict(v) for k, v in g.sounds.items()}
                   for gid, g in soundboard.items()}, f, indent=2, ensure_ascii=False)




class Soundboard(BaseCog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help="lets you add a sound to the soundboard!!")
    async def upload(self, ctx):
        await ctx.send("To be implemented!")

async def setup(bot):
    try:
        await bot.add_cog(Soundboard(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception:
        logger.error("Failed to load cog %s:\n%s", __name__, traceback.format_exc())
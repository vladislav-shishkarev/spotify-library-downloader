# spotify-library-downloader

**English** | [Русский](README.ru.md)

Downloads your Spotify library (liked songs and whole albums) as `.opus` files with tags and cover art.
**No Spotify API key or developer app needed**: the track list comes from a CSV exported with [exportify.net](https://exportify.net), the audio comes from YouTube Music.

## Features

- **Accurate matching on YouTube Music.** Compares duration, title, artist and album.
  Rejects remixes, sped up / slowed, covers and live versions that aren't in the original title.
  Handles Cyrillic transliteration: «Дора» on Spotify matches the "Dora" channel.
- **Falls back to the artist's own channel.** If a song is missing from YouTube Music songs
  (regional label restrictions), it takes a video from the artist's own channel, and only if the duration matches almost exactly.
- **No re-encoding:** Opus ~160 kbps as served by YouTube. Album art comes from Spotify, downscaled to 1200px.
  The track number within the album is set too.
- **Syncs the folder with your likes:** unlike a song and the file goes to the recycle bin; like one and it gets downloaded.
- **Downloads an album by link**, even if it doesn't show up in search.
- **Optional Telegram bot fallback** for whatever YouTube Music doesn't have (slow, with a daily limit).

## Installation

Requires Python 3.10+. ffmpeg and the JS runtime for yt-dlp are installed along with the dependencies.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
copy config.example.ini config.ini                   # Linux/macOS: cp
```

Run all commands below with the Python from `.venv` (`.venv\Scripts\python sync.py`, or activate the venv first).

## Setup

Personal files live in the `data/` folder, which is created on first run.

1. **Track list.** Go to [exportify.net](https://exportify.net), export "Liked Songs"
   (or any playlist) and save it as `data/liked_songs.csv`.
2. **YouTube cookies.** Without them YouTube soon starts answering "Sign in to confirm you're not a bot".
   Sign in to YouTube (preferably in a private window), export cookies in Netscape format
   with any extension such as "Get cookies.txt LOCALLY", and save them as `data/cookies.txt`.
3. **Telegram bot only:** get an `api_id` and `api_hash` at [my.telegram.org](https://my.telegram.org)
   and put them into `config.ini`. On first run Telegram asks for your phone number and a login code.

## Usage

```
python ytm_download.py --limit 5          # test on five tracks
python ytm_download.py                    # download everything from YouTube Music
python ytm_download.py --retry-failed     # retry tracks that weren't found

python sync.py --dry-run                  # show what changed in your likes
python sync.py                            # move removed songs to the recycle bin, download new ones

python album.py https://open.spotify.com/album/... --dry-run   # show the album tracklist
python album.py https://open.spotify.com/album/...             # download the album
python album.py https://open.spotify.com/album/... --bot       # download the rest via the bot

python download.py                        # download via the bot what YouTube Music doesn't have
python download.py --from-history         # pick up files the bot already sent from the chat history
```

Every command supports `--help`. Every command can be interrupted: progress is saved,
and the next run continues where it left off.

Tracks marked `<-- check` in the output have a score below 75, so give them a listen: it may be the wrong version.

## Where the data comes from

Nothing is downloaded from Spotify itself: only public metadata and covers, with no API key and no login.

| What | Source | How |
|---|---|---|
| **Liked songs** (id, title, artists, album, year, duration, explicit) | Spotify Web API via [exportify.net](https://exportify.net) | You sign in on exportify and it exports a CSV. The project itself doesn't use the API |
| **Album tracklist** (title, year, tracks, numbers) | Public album page `open.spotify.com/album/…` | Open Graph meta tags: `og:title`, `music:release_date`, `music:song`, `music:song:track` |
| **Album track data** (title, artists, duration) | Public track pages `open.spotify.com/track/…` | Meta tags `og:title`, `og:description`, `music:duration` |
| **Track number in the album** | Public track page | Meta tag `music:album:track` |
| **Cover art** | Spotify oEmbed (`open.spotify.com/oembed`) → image on `i.scdn.co` | The size id in the image URL is swapped from 300px to the original or 640px, then ffmpeg resizes it to 1200px |
| **Fallback cover** | YouTube Music | Thumbnail from the search result at 1200×1200. Not used for videos: their thumbnails are 16:9 |
| **Track search** | YouTube Music | Unofficial `ytmusicapi` library, no key: songs first, then videos from the artist's channel |
| **Audio** | YouTube Music (`music.youtube.com/watch?v=…`) | `yt-dlp`, format 251 (Opus ~160k), no re-encoding, with your YouTube cookies |
| **Audio for tracks missing on YTM** | Telegram bot | Through your Telegram account (Telethon). Where the bot gets its audio is unknown. The file is converted to Opus 144k; tags and cover come from Spotify as above |
| **Tags in the file** | All of the above | Written with `mutagen`, plus a custom `spotify_track_id` tag that lets `sync` find a file even after it was renamed |

## How it works

```
spotlib/
  config.py, state.py       settings and progress files in data/
  library.py                Track, reading CSV / .txt
  matching.py               scoring YouTube Music candidates
  ytmusic.py                search and download (ytmusicapi + yt-dlp)
  spotify.py, tagging.py    covers, track numbers, albums; tags
  bot/                      downloading via a Telegram bot (Telethon)
  commands/                 the commands; the scripts in the root are thin wrappers
```

## Disclaimer

For personal use only. Respect copyright and the terms of the services you use.
Streaming music where artists get paid is the better option.

## License

[MIT](LICENSE)

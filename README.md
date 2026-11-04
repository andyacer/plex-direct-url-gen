# plex-direct-url-gen

Builds a direct-play URL for a Plex item from the XML that Plex Web shows under **Get Info → View XML**. The URL points at the original media file on your server, so a player like VLC or mpv can stream it with no transcoding. This is handy when you want player-side controls such as audio sync offset, which Plex Web doesn't offer.

Single file, Python 3 standard library only, no dependencies.

## Quick start

1. In Plex Web, open the movie or episode, click **⋯ → Get Info → View XML**.
2. Copy the full XML page URL from the address bar. It contains `X-Plex-Token=...`.
3. Copy the XML text itself (select all on the page, copy).
4. Run:

```
python3 plex-direct-link.py --clipboard "<XML page URL>"
```

The script prints one URL. Paste it into VLC (`Cmd+N` / File → Open Network...) or add `--open` to launch VLC directly.

## Usage

```
python3 plex-direct-link.py [xml] [url] [--token TOKEN] [--clipboard] [--all] [--open]
```

| Argument | Meaning |
|---|---|
| `xml` | Path to a saved XML file, or `-` to read stdin. Omit it to be prompted to paste (end with Ctrl-D). |
| `url` | The XML page URL, or just the server base URL. Omit it to be prompted. |
| `--token TOKEN` | X-Plex-Token. Needed only if the URL doesn't contain one. Overrides the token in the URL. |
| `--clipboard` | Read the XML from the clipboard (macOS `pbpaste`). |
| `--all` | Print a link for every version of the item instead of choosing one. |
| `--open` | Open the resulting link in VLC (macOS `open -a VLC`). |

### Examples

```
# Saved file, full XML page URL (token included)
python3 plex-direct-link.py inputs/xmldata.xml "$URL"

# Base URL only, token supplied separately
python3 plex-direct-link.py --clipboard "https://1-2-3-4.<hash>.plex.direct:32400/" --token abc123

# Pipe it in
pbpaste | python3 plex-direct-link.py - "$URL"

# Every version (1080p, 4K, ...)
python3 plex-direct-link.py movie.xml "$URL" --all
```

### Output

```
https://<host>:<port>/library/parts/<part-id>/<timestamp>/file.mkv?X-Plex-Token=<token>
```

If the item has more than one version, the script lists them (resolution, codecs, container, size, file path) and asks which one to use.

## Architecture

```
 XML text ──► read_xml ──► parse_parts ─────────────┐
 (file / stdin /            │  strict ElementTree    │  list of
  clipboard / paste)        │  └─ fail: escape bare  │  {title, key, file,
                            │     "&", retry         │   desc, size}
                            │     └─ fail: ────────► parse_parts_regex
                                                     │
 URL ────────► parse_server_url ──► (base, token) ───┤
                                                     ▼
                                            choose (if >1 part)
                                                     ▼
                                             build_link ──► stdout
                                                     ▼
                                           optional: open in VLC
```

### Components

| Function | Responsibility |
|---|---|
| `read_xml` | Gets the XML text from the clipboard, stdin, a file, or an interactive paste. |
| `parse_parts` | Parses the XML and collects every `Media/Part` under each `Video` or `Track`. Trims anything before the first `<` so stray text from copy/paste doesn't matter. |
| `parse_parts_regex` | Fallback when the XML is malformed. Scans for `<Part ...>` tags directly and pulls `key`, `file`, `size` and `container` from their attributes. The title comes from the nearest preceding `<Video>` or `<Track>`. |
| `parse_server_url` | Splits the URL into `scheme://host:port` and extracts `X-Plex-Token` from the query string. `--token` takes precedence. |
| `build_link` | Joins base + part `key` and appends the token. Percent-encodes the path (keeping `/` and existing `%` escapes) and the token. |
| `choose` | Prompts when there are multiple versions; returns the only part otherwise. |
| `main` | Argument parsing, orchestration, error reporting, optional VLC launch. |

### Design decisions

- **The `key` is all that matters.** Plex's `<Part key="/library/parts/ID/TIMESTAMP/file.ext">` is the direct file path on the server. Everything else in the XML is only used for display when choosing between versions. This is why the regex fallback is safe: it needs one attribute from one tag.
- **Host and port come from your URL, not the XML.** The XML doesn't say how you reach the server. Using the URL you pasted preserves the `plex.direct` hostname and its TLS certificate, so HTTPS works without warnings.
- **The token comes from the URL.** The XML body does not contain it, but the address bar URL does.
- **Tolerant parsing, in three tiers.** Strict parse first, then a bare-`&` repair (common in titles and filenames like "Tom & Jerry"), then the regex scan. A warning goes to stderr only when the last tier is used.
- **Output goes to stdout, diagnostics to stderr**, so `LINK=$(python3 plex-direct-link.py ...)` captures only the URL.

## Error handling

| Message | Cause | Fix |
|---|---|---|
| `Error: No XML found in the input.` | Input has no `<`. Clipboard or file is empty or wrong. | Recopy the XML. |
| `Error: No <Part key=...> found ...` | The XML isn't for a playable item (e.g. it's a library or section listing). | Open the movie/episode itself and use its **View XML**. |
| `Error: Server URL needs a scheme and host` | URL lacks `https://` or a host. | Paste the full URL. |
| `Warning: no X-Plex-Token found` | URL had no token and `--token` wasn't given. | Pass the full XML page URL or `--token`. |
| `Warning: XML is malformed ... falling back to regex scan` | Strict and repaired parses both failed. | Usually harmless; check the link works. |

## Security

The generated link embeds your Plex token, which grants access to your server. Treat it like a password: don't paste it in public places, screenshots, or shared logs. Rotate it by signing out of Plex devices if it leaks.

## Limitations

- `--clipboard` and `--open` assume macOS (`pbpaste`, `open -a VLC`). On Linux or Windows, use a file or stdin and paste the link manually.
- Only the first `Part` per `Media` is needed for normal files; multi-part movies (CD1/CD2) are listed as separate choices.
- The link goes to the server's original file. If your player can't reach the server address in the URL (for example you're off the home network and remote access is off), it won't play.

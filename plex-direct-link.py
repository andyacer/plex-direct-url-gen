#!/usr/bin/env python3
"""Build a direct-play URL for a Plex item from its "View XML" output.

Inputs:
  1. The XML data (Plex Web > item > ... > Get Info > View XML).
  2. The URL of that XML page (or just your server's base URL).
     If the URL contains X-Plex-Token, it is picked up automatically.

Usage examples:
  python3 plex_direct_link.py                       # interactive prompts
  python3 plex_direct_link.py movie.xml "https://1-2-3-4.hash.plex.direct:32400/library/metadata/123?X-Plex-Token=abc"
  python3 plex_direct_link.py --clipboard "https://1-2-3-4.hash.plex.direct:32400/" --token abc
  python3 plex_direct_link.py movie.xml "<url>" --open   # launch in VLC (macOS)
"""

import argparse
import html
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote, urlparse


def read_xml(source, clipboard):
    if clipboard:
        return subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout
    if source == "-":
        return sys.stdin.read()
    if source:
        with open(source, "r", encoding="utf-8") as f:
            return f.read()
    print("Paste the XML, then press Ctrl-D (Ctrl-Z + Enter on Windows):", file=sys.stderr)
    return sys.stdin.read()


AMP_FIX = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
ATTR = re.compile(r'([\w:.-]+)\s*=\s*"([^"]*)"')


def parse_parts_regex(text):
    """Fallback for XML that won't parse: scan for <Part ...> tags directly."""
    parts = []
    for m in re.finditer(r"<Part\b[^>]*>", text):
        attrs = {k: html.unescape(v) for k, v in ATTR.findall(m.group(0))}
        if not attrs.get("key"):
            continue
        # Nearest preceding Video/Track tag supplies the title.
        title = "Untitled"
        for v in re.finditer(r"<(?:Video|Track)\b[^>]*>", text[: m.start()]):
            t = dict(ATTR.findall(v.group(0))).get("title")
            if t:
                title = html.unescape(t)
        parts.append({
            "title": title,
            "key": attrs["key"],
            "file": attrs.get("file", ""),
            "desc": attrs.get("container", ""),
            "size": attrs.get("size"),
        })
    if not parts:
        raise ValueError("No <Part key=...> found in the XML, even with the fallback scan. "
                         "Make sure you copied the XML for the movie/episode itself.")
    return parts


def parse_parts(xml_text):
    """Return a list of dicts, one per Media/Part in the XML."""
    start = xml_text.find("<")
    if start == -1:
        raise ValueError("No XML found in the input.")
    text = xml_text[start:].strip()

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        try:
            # Common cause: bare & in a title or filename.
            root = ET.fromstring(AMP_FIX.sub("&amp;", text))
        except ET.ParseError as e:
            print(f"Warning: XML is malformed ({e}); falling back to regex scan.", file=sys.stderr)
            return parse_parts_regex(text)

    parts = []
    for item in root.iter():
        if item.tag not in ("Video", "Track"):
            continue
        title = item.get("title", "Untitled")
        for media in item.findall("Media"):
            desc = " ".join(
                x for x in (
                    media.get("videoResolution") and media.get("videoResolution") + "p",
                    media.get("videoCodec"),
                    media.get("audioCodec"),
                    media.get("container"),
                ) if x
            )
            for part in media.findall("Part"):
                if part.get("key"):
                    parts.append({
                        "title": title,
                        "key": part.get("key"),
                        "file": part.get("file", ""),
                        "desc": desc,
                        "size": part.get("size"),
                    })
    if not parts:
        raise ValueError("No <Part key=...> found. Is this the XML for a movie/episode?")
    return parts


def parse_server_url(url, token_arg):
    u = urlparse(url.strip())
    if not u.scheme or not u.netloc:
        raise ValueError("Server URL needs a scheme and host, e.g. https://host:32400/")
    base = f"{u.scheme}://{u.netloc}"
    token = token_arg or parse_qs(u.query).get("X-Plex-Token", [None])[0]
    return base, token


def build_link(base, token, key):
    # key looks like /library/parts/12345/1700000000/file.mkv
    path = quote(key, safe="/%")
    link = base + path
    if token:
        link += "?X-Plex-Token=" + quote(token, safe="")
    return link


def choose(parts):
    if len(parts) == 1:
        return parts[0]
    print("Multiple versions found:", file=sys.stderr)
    for i, p in enumerate(parts, 1):
        size = f", {int(p['size']) / 1e9:.2f} GB" if p["size"] else ""
        print(f"  {i}. {p['title']} [{p['desc']}{size}] {p['file']}", file=sys.stderr)
    while True:
        raw = input("Pick one [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(parts):
            return parts[int(raw) - 1]


def main():
    ap = argparse.ArgumentParser(description="Build a Plex direct-play URL from View XML output.")
    ap.add_argument("xml", nargs="?", help="XML file path, or - for stdin (omit to paste)")
    ap.add_argument("url", nargs="?", help="XML page URL or server base URL")
    ap.add_argument("--token", help="X-Plex-Token (if not in the URL)")
    ap.add_argument("--clipboard", action="store_true", help="read XML from clipboard (macOS pbpaste)")
    ap.add_argument("--all", action="store_true", help="print links for every version")
    ap.add_argument("--open", action="store_true", help="open the link in VLC (macOS)")
    args = ap.parse_args()

    xml_text = read_xml(args.xml, args.clipboard)
    url = args.url or input("Server / XML page URL: ").strip()

    try:
        parts = parse_parts(xml_text)
        base, token = parse_server_url(url, args.token)
    except (ValueError, ET.ParseError) as e:
        sys.exit(f"Error: {e}")

    if not token:
        print("Warning: no X-Plex-Token found; the link will likely be rejected. "
              "Pass --token or use the full XML page URL.", file=sys.stderr)

    if args.all:
        for p in parts:
            print(f"# {p['title']} [{p['desc']}]\n{build_link(base, token, p['key'])}")
        return

    part = choose(parts)
    link = build_link(base, token, part["key"])
    print(link)

    if args.open:
        subprocess.run(["open", "-a", "VLC", link], check=False)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["praw>=7.7", "Pillow>=10"]
# ///
"""Re-download full-resolution versions of Reddit gallery previews.

Some images were saved from Reddit gallery posts via the preview URL
(preview.redd.it?width=...), which caps the width. This finds those images
(title advertises a much larger resolution than the actual file), searches
r/WidescreenWallpaper for the source post, and overwrites the preview with the
original full-resolution file.

After running this, re-run fix-resolutions.py to re-categorise images, rebuild
thumbnails and regenerate docs/wallpapers.json.

Usage:
    REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=*** uv run re-scrape.py --dry-run
    REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=*** uv run re-scrape.py
    REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=*** uv run re-scrape.py --delete-missing
"""

import os
import re
import sys

import praw
import requests
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.join(ROOT, "images")

USER_AGENT = "wallpaper-repair-script/1.0"

# Resolution token inside a filename title, e.g. "7680_x_2160", "3440x1440".
RES_RE = re.compile(r"(\d{3,5})_?[xX×]_?(\d{3,5})")

# Must match the backend's sanitize_text exactly (order matters).
special_characters = [
    "#", "'", ":", "?", "!", "(", ")", "[", "]", "{", "}", "<", ">", "|", "/",
    "\\", ".", ",", " ", "__", "-", '"', "'",
]


def sanitize_text(text):
    for char in special_characters:
        text = text.replace(char, "_")
    return text.strip("_").strip()


def split_filename(filename):
    """'Mixed_3_7680_x_2160_10.jpg' -> ('Mixed_3_7680_x_2160', 10)."""
    stem = os.path.splitext(filename)[0]
    m = re.match(r"^(.*)_(\d+)$", stem)
    if m:
        return m.group(1), int(m.group(2))
    return stem, None


def full_res_url(media_id, mime, s):
    if mime == "image/gif":
        return s.get("gif") or s.get("u")
    if mime == "image/png":
        return f"https://i.redd.it/{media_id}.png"
    if mime in ("image/jpg", "image/jpeg"):
        return f"https://i.redd.it/{media_id}.jpg"
    return s.get("u")


def find_affected():
    affected = []
    for res_dir in sorted(os.listdir(IMAGES)):
        d = os.path.join(IMAGES, res_dir)
        if not os.path.isdir(d):
            continue
        try:
            aw, ah = map(int, res_dir.lower().split("x"))
        except ValueError:
            continue
        for fname in sorted(os.listdir(d)):
            path = os.path.join(d, fname)
            if not os.path.isfile(path):
                continue
            title_stem, idx = split_filename(fname)
            if idx is None or idx >= 100:
                continue  # not a gallery item (trailing number is part of the title)
            m = RES_RE.search(title_stem)
            if not m:
                continue
            tw, th = int(m.group(1)), int(m.group(2))
            if tw <= aw * 2:
                continue  # not dramatically smaller -> not a Reddit preview
            # same aspect ratio (~5%) but much wider -> Reddit preview
            if abs((tw / th) - (aw / ah)) > 0.05:
                continue
            affected.append((path, fname, title_stem, idx, aw, ah, tw, th))
    return affected


def main():
    if not os.environ.get("REDDIT_CLIENT_ID") or not os.environ.get("REDDIT_CLIENT_SECRET"):
        print("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars.")
        sys.exit(1)

    dry = "--dry-run" in sys.argv
    delete_missing = "--delete-missing" in sys.argv

    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=USER_AGENT,
    )
    subreddit = reddit.subreddit("WidescreenWallpaper")

    affected = find_affected()
    print(f"candidate preview images: {len(affected)}\n")

    matched = 0
    missed = []
    for path, fname, title_stem, idx, aw, ah, tw, th in affected:
        query = title_stem.replace("_", " ")
        found = None
        for post in subreddit.search(query, limit=20):
            if sanitize_text(post.title) == title_stem:
                found = post
                break
        if found is None:
            print(f"  MISS   {fname}  (no post matched '{query}')")
            missed.append(path)
            continue

        try:
            items = found.gallery_data["items"]
            media_id = items[idx]["media_id"]
            mm = found.media_metadata[media_id]
            url = full_res_url(media_id, mm.get("m", ""), mm["s"])
        except (IndexError, KeyError, TypeError) as e:
            print(f"  ERR    {fname}  ({e})")
            continue

        if dry:
            print(f"  FOUND  {fname}  {aw}x{ah} -> expect {tw}x{th}")
            matched += 1
            continue

        tmp = path + ".full"
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            with open(tmp, "wb") as f:
                f.write(r.content)
            im = Image.open(tmp)
            w, h = im.size
            im.close()
            if w < aw:
                os.remove(tmp)
                print(f"  SKIP   {fname}  (full-res {w}x{h} smaller than preview)")
                continue
            os.replace(tmp, path)
            print(f"  DONE   {fname}  {aw}x{ah} -> {w}x{h}")
            matched += 1
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            print(f"  FAIL   {fname}  ({e})")

    print(f"\nmatched {matched}/{len(affected)}")

    if missed:
        with open(os.path.join(ROOT, "missed.txt"), "w") as f:
            for p in missed:
                f.write(p + "\n")
        if delete_missing:
            for p in missed:
                os.remove(p)
            print(f"deleted {len(missed)} missed previews (listed in missed.txt)")
        else:
            print(f"{len(missed)} missed (listed in missed.txt). Re-run with --delete-missing to remove them.")

    if dry:
        print("dry-run: nothing changed. Re-run without --dry-run to download.")
    else:
        print("Done. Now run:  uv run fix-resolutions.py")


if __name__ == "__main__":
    main()

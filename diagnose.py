#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["praw>=7.7", "Pillow>=10"]
# ///
"""Verify the full-resolution URL for Reddit gallery images.

For matched gallery posts, dump the media_metadata, construct the candidate
i.redd.it original URL, download it, and compare the actual size against the
declared source dimensions (s.x / s.y).

Usage:
    REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=*** uv run diagnose.py
"""

import io
import os

import praw
import requests
from PIL import Image


def full_res_url(media_id, mime, s):
    if mime == "image/gif":
        return s.get("gif") or s.get("u")
    if mime == "image/png":
        return f"https://i.redd.it/{media_id}.png"
    if mime in ("image/jpg", "image/jpeg"):
        return f"https://i.redd.it/{media_id}.jpg"
    return s.get("u")


reddit = praw.Reddit(
    client_id=os.environ["REDDIT_CLIENT_ID"],
    client_secret=os.environ["REDDIT_CLIENT_SECRET"],
    user_agent="wallpaper-diagnose/1.0",
)
sub = reddit.subreddit("WidescreenWallpaper")

for query in ["Cyber Steam Girl 7830x2160", "Star Wars Star Destroyer Bridge 7680x2160"]:
    for post in sub.search(query, limit=5):
        print("=" * 60)
        print("POST TITLE:", post.title)
        items = (post.gallery_data or {}).get("items", [])[:3]
        for item in items:
            media_id = item["media_id"]
            mm = post.media_metadata[media_id]
            s = mm.get("s", {})
            mime = mm.get("m", "")
            declared = (s.get("x"), s.get("y"))
            url = full_res_url(media_id, mime, s)
            print(f"  media_id={media_id}  mime={mime}  declared={declared}")
            print(f"    URL: {url}")
            try:
                r = requests.get(url, timeout=60, headers={"User-Agent": "wallpaper-diagnose/1.0"})
                r.raise_for_status()
                im = Image.open(io.BytesIO(r.content))
                actual = im.size
                im.close()
                if actual == declared:
                    verdict = "FULL-RES (matches declared)"
                elif actual[0] > declared[0]:
                    verdict = "LARGER than declared"
                else:
                    verdict = "SMALLER than declared (still preview)"
                print(f"    ACTUAL: {actual} -> {verdict}")
            except Exception as e:
                print(f"    DOWNLOAD ERROR: {e}")
        break

#!/usr/bin/env python3
"""Read a public Quark share's bounded directory listing; never download or save it."""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib import error, parse, request

API_BASE = "https://drive-pc.quark.cn/1/clouddrive"
PAGE_SIZE = 100
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
WALLPAPER_SUFFIXES = {".mp4", ".mov", ".m4v"}
ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}


class ShareReadError(Exception):
    """Safe to display: contains no request URL, access token, or raw response."""


def share_id(value):
    value = value.strip()
    if "://" in value:
        url = parse.urlsplit(value)
        if url.scheme != "https" or url.netloc.lower() != "pan.quark.cn":
            raise ValueError("expected an https://pan.quark.cn/s/... share")
        value = url.path.removeprefix("/s/").rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9]{6,64}", value):
        raise ValueError("invalid public share ID")
    return value


def positive_number(value, integer=False):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    if integer:
        return int(number) if number.is_integer() else None
    return number


def timestamp(value):
    number = positive_number(value)
    if number is None:
        return None
    if number > 100_000_000_000:
        number /= 1000
    try:
        return datetime.fromtimestamp(number, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def request_json(endpoint, query, body=None, timeout=15):
    url = API_BASE + endpoint + "?" + parse.urlencode(query)
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=payload, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://pan.quark.cn/",
        "Content-Type": "application/json",
    })
    try:
        with request.urlopen(req, timeout=timeout) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        exc.close()
        raise ShareReadError(f"http_error_{exc.code}") from None
    except (error.URLError, TimeoutError, OSError):
        raise ShareReadError("network_error") from None
    except (ValueError, UnicodeError):
        raise ShareReadError("invalid_json") from None
    if not isinstance(result, dict):
        raise ShareReadError("invalid_response")
    if result.get("code", 0) not in (0, "0") or result.get("status", 200) not in (200, "200"):
        raise ShareReadError("api_rejected") from None
    return result


def file_record(raw, parent, min_width, min_height):
    name = raw["file_name"]
    directory = bool(raw.get("dir", False))
    suffix = Path(name).suffix.lower()
    kind = "other"
    if directory:
        kind = "directory"
    elif suffix in VIDEO_SUFFIXES:
        kind = "video"
    elif suffix in ARCHIVE_SUFFIXES:
        kind = "archive"
    width = positive_number(raw.get("video_width"), integer=True)
    height = positive_number(raw.get("video_height"), integer=True)
    resolution = "not_video"
    if kind == "video":
        if width is None or height is None:
            resolution = "unknown"
        elif width >= min_width and height >= min_height:
            resolution = "meets_minimum"
        else:
            resolution = "below_minimum"
    record = {
        "relative_path": "/".join(part for part in (parent, name) if part),
        "file_name": name,
        "kind": kind,
        "size_bytes": positive_number(raw.get("size"), integer=True),
        "width": width,
        "height": height,
        "fps": positive_number(raw.get("fps")),
        "duration_seconds": positive_number(raw.get("duration")),
        "cloud_created_at": timestamp(raw.get("created_at")),
        "cloud_modified_at": timestamp(raw.get("updated_at")),
        "resolution_status": resolution,
    }
    if directory:
        record["folder_id"] = str(raw.get("fid") or "")
    return record


def inspect_share(value, *, passcode="", folder_id="0", max_depth=2,
                  max_entries=300, min_width=3840, min_height=2160, timeout=15):
    identifier = share_id(value)
    result = {
        "share_url": "https://pan.quark.cn/s/" + identifier,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "unavailable",
        "evidence_level": "lead",
        "metadata_source": "quark_share_metadata",
        "download_status": "not_attempted",
        "start_folder_id": folder_id,
        "criteria": {
            "min_width": min_width, "min_height": min_height,
            "extensions": sorted(WALLPAPER_SUFFIXES),
        },
        "listing_complete": False,
        "entries_scanned": 0,
        "entries": [],
        "eligible_media": [],
        "unvisited_folders": [],
        "errors": [],
    }
    common = {"pr": "ucpro", "fr": "pc"}
    try:
        token_result = request_json("/share/sharepage/token", common, {
            "pwd_id": identifier, "passcode": passcode,
        }, timeout=timeout)
        token_data = token_result.get("data")
        token = token_data.get("stoken") if isinstance(token_data, dict) else None
        if not isinstance(token, str) or not token:
            raise ShareReadError("missing_share_token")
    except ShareReadError as exc:
        result["errors"].append({"path": "", "reason": str(exc)})
        return result

    folders = deque([(folder_id, "", 0)])
    visited = set()
    pages_read = 0
    while folders and result["entries_scanned"] < max_entries:
        current_id, parent, depth = folders.popleft()
        if current_id in visited:
            continue
        visited.add(current_id)
        page = 1
        folder_total = None
        folder_entries_read = 0
        while result["entries_scanned"] < max_entries:
            query = {
                **common, "pwd_id": identifier, "stoken": token,
                "pdir_fid": current_id, "_page": page, "_size": PAGE_SIZE,
                "_sort": "file_type:asc,file_name:asc",
            }
            try:
                response = request_json("/share/sharepage/detail", query, timeout=timeout)
                data = response.get("data")
                if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                    raise ShareReadError("invalid_listing")
            except ShareReadError as exc:
                result["errors"].append({"path": parent, "reason": str(exc)})
                break
            pages_read += 1
            rows = data["list"]
            metadata = response.get("metadata")
            if isinstance(metadata, dict):
                folder_total = positive_number(metadata.get("_total"), integer=True) or folder_total
            folder_entries_read += len(rows)
            if folder_total is None:
                more = len(rows) >= PAGE_SIZE
            else:
                more = folder_entries_read < folder_total
            if more and not rows:
                result["errors"].append({"path": parent, "reason": "incomplete_listing"})
                break
            remaining = max_entries - result["entries_scanned"]
            batch = rows[:remaining]
            result["entries_scanned"] += len(batch)
            for raw in batch:
                if not isinstance(raw, dict) or not isinstance(raw.get("file_name"), str):
                    result["errors"].append({"path": parent, "reason": "invalid_entry"})
                    continue
                record = file_record(raw, parent, min_width, min_height)
                result["entries"].append(record)
                if record["kind"] == "directory":
                    child = {"path": record["relative_path"], "folder_id": record["folder_id"]}
                    if not record["folder_id"]:
                        result["errors"].append({**child, "reason": "missing_folder_id"})
                    elif depth >= max_depth:
                        result["unvisited_folders"].append({**child, "reason": "depth_limit"})
                    else:
                        folders.append((record["folder_id"], record["relative_path"], depth + 1))
                elif (Path(record["file_name"]).suffix.lower() in WALLPAPER_SUFFIXES
                      and record["resolution_status"] == "meets_minimum"):
                    result["eligible_media"].append(record)
            if len(rows) > remaining or (more and result["entries_scanned"] >= max_entries):
                result["unvisited_folders"].append({
                    "path": parent, "folder_id": current_id, "reason": "entry_limit",
                })
                break
            if not more:
                break
            page += 1
    result["unvisited_folders"].extend(
        {"path": path, "folder_id": fid, "reason": "entry_limit"}
        for fid, path, _depth in folders if fid not in visited
    )
    result["listing_complete"] = not result["errors"] and not result["unvisited_folders"]
    if pages_read:
        result["evidence_level"] = "cloud_metadata"
        result["status"] = "listed" if result["listing_complete"] else "partial"
    return result


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("share", help="public Quark share URL or share ID")
    parser.add_argument("--output", type=Path, help="write JSON here; otherwise use stdout")
    parser.add_argument("--folder-id", default="0", help="start at this public folder ID")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-entries", type=positive_int, default=300)
    parser.add_argument("--min-width", type=positive_int, default=3840)
    parser.add_argument("--min-height", type=positive_int, default=2160)
    parser.add_argument("--timeout", type=positive_int, default=15, help="seconds per request")
    parser.add_argument("--passcode-env", help="environment variable containing a share code")
    args = parser.parse_args()
    if args.max_depth < 0:
        parser.error("--max-depth cannot be negative")
    if args.passcode_env and args.passcode_env not in os.environ:
        parser.error("the requested passcode environment variable is unset")
    try:
        result = inspect_share(
            args.share, passcode=os.environ.get(args.passcode_env, "") if args.passcode_env else "",
            folder_id=args.folder_id, max_depth=args.max_depth, max_entries=args.max_entries,
            min_width=args.min_width, min_height=args.min_height, timeout=args.timeout,
        )
    except ValueError as exc:
        parser.error(str(exc))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 1 if result["status"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Install the latest Lightpanda Linux x86-64 release using Python's stdlib only."""

import argparse
import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RELEASE_API = "https://api.github.com/repos/lightpanda-io/browser/releases/latest"
ASSET_NAME = "lightpanda-x86_64-linux"


def api_latest_release():
    request = urllib.request.Request(RELEASE_API, headers={"User-Agent": "outgram"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download(url, destination, progress):
    request = urllib.request.Request(url, headers={"User-Agent": "outgram"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0"))
        downloaded = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            output.write(block)
            downloaded += len(block)
            if progress:
                if total:
                    print(
                        f"\rDownloading {downloaded / 2**20:.1f}/{total / 2**20:.1f} MiB ({downloaded * 100 / total:.0f}%)",
                        end="",
                        flush=True,
                    )
                else:
                    print(f"\rDownloading {downloaded / 2**20:.1f} MiB", end="", flush=True)
    if progress:
        print()


def unpack_or_copy(asset, output_dir):
    """Return the executable extracted from a raw asset, ZIP, or tar archive."""
    if zipfile.is_zipfile(asset):
        with zipfile.ZipFile(asset) as archive:
            names = [name for name in archive.namelist() if Path(name).name == "lightpanda"]
            if len(names) != 1:
                raise RuntimeError("ZIP does not contain exactly one lightpanda binary")
            # Do not use extract(): archive paths must not escape the temp directory.
            with archive.open(names[0]) as source, (output_dir / "lightpanda").open("wb") as output:
                shutil.copyfileobj(source, output)
            return output_dir / "lightpanda"
    if tarfile.is_tarfile(asset):
        with tarfile.open(asset) as archive:
            members = [
                member for member in archive.getmembers() if Path(member.name).name == "lightpanda" and member.isfile()
            ]
            if len(members) != 1:
                raise RuntimeError("tar archive does not contain exactly one lightpanda binary")
            member = members[0]
            # Do not use extract(): archive paths must not escape the temp directory.
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("cannot read lightpanda from archive")
            target = output_dir / "lightpanda"
            with target.open("wb") as output:
                shutil.copyfileobj(source, output)
            return target
    target = output_dir / "lightpanda"
    shutil.copyfile(asset, target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("/usr/local/bin/lightpanda"),
        help="installed binary path (default: /usr/local/bin/lightpanda)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Do not show progress bar")
    args = parser.parse_args()
    output_filename = args.output
    quiet = args.quiet

    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise SystemExit("This installer supports Linux x86-64 only.")

    release = api_latest_release()
    asset = next((item for item in release.get("assets", []) if item.get("name") == ASSET_NAME), None)
    if asset is None:
        raise SystemExit(f"Asset {ASSET_NAME!r} was not found in GitHub release {release.get('tag_name')!r}.")

    output_filename.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lightpanda-") as temporary:
        temporary = Path(temporary)
        downloaded = temporary / asset["name"]
        print(f"Installing Lightpanda {release.get('tag_name', 'latest')} from {asset['browser_download_url']}")
        download(asset["browser_download_url"], downloaded, progress=not quiet)
        binary = unpack_or_copy(downloaded, temporary)
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        staged = output_filename.with_name(output_filename.name + ".new")
        shutil.copy2(binary, staged)
        staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(staged, output_filename)

    if not quiet:
        print(f"Installed: {output_filename}")


if __name__ == "__main__":
    main()

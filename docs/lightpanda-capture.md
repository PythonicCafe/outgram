# Lightpanda installation and public-profile capture

These utilities use only Python's standard library and are intended for public Instagram profiles that you are authorized to inspect.

## Install Lightpanda

Run as a user allowed to write the destination directory. `/usr/local/bin` is the default because it is normally on `PATH` and avoids replacing distribution-managed files in `/usr/bin`.

```shell
python scripts/install_lightpanda.py
# or:
python scripts/install_lightpanda.py --output /usr/bin/lightpanda
```

The installer calls GitHub's `releases/latest` API, selects the `lightpanda-x86_64-linux` asset, streams it to a temporary file with progress, accepts a raw binary, ZIP, or tar archive, and atomically installs the executable. It supports Linux x86-64 only.

## Capture a HAR through CDP

```shell
python scripts/capture_instagram_lightpanda.py \
  govbr another_public_profile \
  --scrolls 2 \
  --output data/instagram.har
```

For every supplied username the script starts `lightpanda serve` via `subprocess`, connects to its localhost CDP WebSocket, enables the `Page` and `Network` domains, opens the public profile, waits for a random interval and scrolls. It creates a HAR 1.2 file from `Network.requestWillBeSent`, `Network.responseReceived` and `Network.loadingFinished` events.

GraphQL response bodies are saved when available, up to 5 MiB per response. The currently tested Lightpanda CDP build does not expose POST request bodies, but its timeline query exposes `doc_id` and variables in the GET query string. Use a full browser HAR if the query being diagnosed sends those values only in a POST form body. The capture is sufficient to inspect the current GET timeline `doc_id` and response schema with `scripts/analyze_har.py`:

```shell
python scripts/analyze_har.py data/instagram.har --profile govbr
```

The output removes `Cookie`, `Set-Cookie` and `Authorization` headers by default. `--keep-cookies` exists only for local diagnostics; HARs produced with it must never be committed or shared. Do not add login automation, private-profile handling, challenge solving or rate-limit bypassing to either script.

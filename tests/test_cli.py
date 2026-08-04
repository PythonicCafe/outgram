import csv
from pathlib import Path

import pytest

from outgram import cli


class EmptyClient:
    def __init__(self, min_wait, max_wait):
        pass

    def profile(self, username):
        raise AssertionError("profile must not be called")


def test_parser_exposes_navigation_and_export_positionals():
    parser = cli._create_parser()

    help_text = parser.format_help()
    assert "NETWORK" in help_text
    assert "instagram" in help_text
    assert "threads" in help_text

    args = parser.parse_args(
        ["threads", "export", "posts.csv", "collected.profile", "2026-08-01 UTC", "catalog"]
    )
    assert args.username == "collected.profile"
    assert args.output == Path("catalog")
    assert args.output_format is None

    markdown = parser.parse_args(
        ["instagram", "export", "-f", "md", "posts.csv", "profile", "timestamp", "catalog.md"]
    )
    assert markdown.output_format == "md"

    with pytest.raises(SystemExit):
        parser.parse_args(["instagram", "export", "-f", "both", "posts.csv", "profile", "timestamp", "catalog"])


def test_parser_scopes_transcription_and_pacing_short_options():
    parser = cli._create_parser()

    export = parser.parse_args(
        ["threads", "export", "-t", "vtt", "posts.csv", "profile", "timestamp", "catalog"]
    )
    assert export.transcriptions_dir == Path("vtt")

    collection = parser.parse_args(["threads", "profile", "-t", "1", "profile", "profiles.csv"])
    assert collection.min_wait == 1


def test_main_dispatches_threads_export_without_network(monkeypatch, temp_dir):
    input_csv = temp_dir / "posts.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=("id", "username", "code", "published_at", "media", "text"))
        writer.writeheader()
    calls = []

    def export(**kwargs):
        calls.append(kwargs)
        return [kwargs["output"]]

    monkeypatch.setattr(cli, "export_threads_catalog", export)
    result = cli.main(["threads", "export", str(input_csv), "profile", "timestamp", str(temp_dir / "catalog")])

    assert result == [temp_dir / "catalog"]
    assert calls[0]["profile"] == "profile"


def test_progress_uses_stderr_and_quiet_collection_is_silent(capsys, temp_dir):
    progress = cli.ProgressBar(total=1)
    progress.update(1, done=True)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "001/001" in captured.err

    output = temp_dir / "profiles.csv"
    result = cli.collect_profile(EmptyClient, [], output, min_wait=0, max_wait=0, quiet=True)
    captured = capsys.readouterr()
    assert result == output
    assert captured.out == ""
    assert captured.err == ""


def test_archive_without_profiles_writes_csv_members_without_progress(capsys, temp_dir):
    output = temp_dir / "nested" / "archive.zip"

    result = cli.archive(EmptyClient, [], output, min_wait=0, max_wait=0, quiet=True)

    assert result == output
    assert output.exists()
    assert capsys.readouterr().out == ""
    assert capsys.readouterr().err == ""

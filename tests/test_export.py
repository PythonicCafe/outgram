import csv

from outgram.export import export_instagram_catalog


def write_posts(path):
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=(
                "id",
                "code",
                "type",
                "published_at",
                "media",
                "pinned",
                "text",
                "author_username",
                "author_full_name",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "123",
                "code": "VideoCode",
                "type": "video",
                "published_at": "2026-07-28 12:51:09+00:00",
                "media": "https://cdn.example.invalid/video.mp4",
                "pinned": "true",
                "text": "Caption <with markup>",
                "author_username": "example.person",
                "author_full_name": "Example Person",
            }
        )


def test_export_instagram_catalog_writes_markdown_and_html(temp_dir):
    input_csv = temp_dir / "post.csv"
    transcriptions_dir = temp_dir / "transcription"
    transcriptions_dir.mkdir()
    (transcriptions_dir / "post_123_en.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello world\n",
        encoding="utf-8",
    )
    write_posts(input_csv)

    written = export_instagram_catalog(
        input_csv=input_csv,
        output=temp_dir / "catalog",
        profile="example.person",
        collected_at="2026-07-31 09:16 UTC",
        transcriptions_dir=transcriptions_dir,
        output_format="both",
    )

    assert written == [temp_dir / "catalog.md", temp_dir / "catalog.html"]
    markdown = written[0].read_text(encoding="utf-8")
    assert "https://www.instagram.com/reel/VideoCode/" in markdown
    assert "**Transcription:**" in markdown
    assert "Hello world" in markdown

    html = written[1].read_text(encoding="utf-8")
    assert "<!doctype html>" in html
    assert "Caption &lt;with markup&gt;" in html
    assert "Hello world" in html


def test_export_instagram_catalog_writes_selected_format_to_requested_path(temp_dir):
    input_csv = temp_dir / "post.csv"
    write_posts(input_csv)
    output = temp_dir / "nested" / "catalog.html"

    written = export_instagram_catalog(
        input_csv=input_csv,
        output=output,
        profile="example.person",
        collected_at="2026-07-31 09:16 UTC",
        transcriptions_dir=None,
        output_format="html",
    )

    assert written == [output]
    assert output.exists()
    assert not (temp_dir / "nested" / "catalog.md").exists()

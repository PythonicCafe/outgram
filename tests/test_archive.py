import datetime
from zipfile import ZipFile

from outgram.cli import archive


class FakeMedia:
    content = b"media"
    content_type = "image/jpeg"


class FakeProfile:
    id = 1
    username = "example"

    def __init__(self):
        self.picture = FakeMedia()

    def get_media(self):
        return [self.picture]

    def serialize(self):
        return {"id": self.id, "username": self.username}


class FakePost:
    id = "post-1"

    def __init__(self):
        self.media = [FakeMedia()]

    def get_media(self):
        return self.media

    def serialize(self):
        return {"id": self.id}


class FakeClient:
    def __init__(self, min_wait, max_wait):
        self.profile_data = FakeProfile()
        self.post_data = FakePost()

    def profile(self, username):
        return self.profile_data

    def profile_posts(self, username):
        yield self.post_data

    @staticmethod
    def download_many(objects):
        for obj in objects:
            yield from obj.get_media()


def test_archive_members_use_archive_generation_date(temp_dir):
    output = temp_dir / "nested" / "archive.zip"

    archive(
        client_class=FakeClient,
        usernames_or_ids=["example"],
        output_zip=output,
        min_wait=0,
        max_wait=0,
        quiet=True,
    )

    assert output.exists()
    today = datetime.date.today()
    with ZipFile(output) as zip_file:
        assert zip_file.namelist() == [
            "profile.csv",
            "media/profile_1.jpg",
            "post.csv",
            "media/post_post-1_001.jpg",
        ]
        assert all(
            datetime.datetime(*member.date_time).date() == today
            for member in zip_file.infolist()
        )

import datetime
import io
import json
import subprocess
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Type, Union


def flatten(row: Dict[str, Any], nested_fields: Dict[str, Any]):
    """Flatten row inner dictionaries inline"""
    for field_name, FieldClass in nested_fields.items():
        inner_values = row.pop(field_name)
        if not inner_values:
            row.update(
                {
                    f"{field_name}_{inner_field.name}": None
                    for inner_field in fields(FieldClass)
                    if inner_field.name != "content"
                }
            )
        else:
            for key, value in inner_values.items():
                if key != "content":
                    row[f"{field_name}_{key}"] = value


class BaseModel:
    def serialize(self) -> Dict[str, Any]:
        """Converts dataclass values into a `dict` (`content` won't be serialized!)"""
        row = asdict(self)
        if "content" in row:
            del row["content"]
        return row


class BaseMedia(BaseModel):

    def get_media(self) -> List[Type["BaseMedia"]]:
        """Return all media objects of this object"""
        raise NotImplementedError("BaseMedia child class must implement `get_media` method")

    def save(self, filename: Union[Path, str]):
        if self.content is None:
            raise ValueError("Object has no content (download first)")
        filename = Path(filename)
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_bytes(self.content)


class BaseProfile(BaseModel):

    def get_media(self) -> List[Type[BaseMedia]]:
        """Return all media objects of this profile (not from its posts)"""
        raise NotImplementedError("Profile child class must implement `get_media` method")


class BasePost(BaseModel):

    def get_media(self) -> List[Type[BaseMedia]]:
        """Return all media objects of this post"""
        raise NotImplementedError("Post child class must implement `get_media` method")


# Generic classes used by both sites


@dataclass
class Picture(BaseMedia):
    url: str = field(repr=False)
    width: Optional[int] = None  # InstagramProfile doesn't have it
    height: Optional[int] = None  # InstagramProfile doesn't have it
    content: Optional[bytes] = field(repr=False, default=None)
    content_type: Optional[str] = None

    def get_media(self) -> List[Type[BaseMedia]]:
        """Return all media objects related to this picture (just itself)"""
        return [self]

    def calculate_size(self):
        """Fill `width` and `height` fields by reading image content. Requires a pre-downloaded picture and `Pillow`"""
        from PIL import Image  # noqa

        if self.content is None:
            raise ValueError(
                "Cannot calculate size for an image without content - download it first with `<ClientClass>.download(picture)`"
            )
        img = Image.open(io.BytesIO(self.content))
        self.width, self.height = img.size


@dataclass
class Video(BaseMedia):
    url: str = field(repr=False)
    type: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail: Optional[Picture] = None
    duration: Optional[float] = None
    content: Optional[bytes] = field(repr=False, default=None)
    content_type: Optional[str] = None

    def serialize(self) -> Dict[str, Any]:
        row = super().serialize()
        flatten(row, {"thumbnail": Picture})
        return row

    def get_media(self) -> List[Type[BaseMedia]]:
        """Return all media objects related to this video (itself and the thumbnail, if avaiable)"""
        result = [self]
        if self.thumbnail:
            result.append(self.thumbnail)
        return result

    def calculate_duration(self):
        """Fill `duration` field by reading video content. Requires a pre-downloaded video and `ffmpeg`"""
        if self.content is None:
            raise ValueError(
                "Cannot calculate duration for a video without content - download it first with `<ClientClass>.download(video)`"
            )
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-",
        ]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=self.content)
        if stderr:
            raise RuntimeError(f"Error: checking video duration {stderr.decode('utf-8')}")
        data = json.loads(stdout)
        streams_duration = [float(stream["duration"]) for stream in data["streams"]]
        if streams_duration:
            self.duration = max(streams_duration)
        else:
            value = data["format"].get("duration", None)
            if value is None:
                raise RuntimeError("Cannot get duration from ffprobe: data not found")
            self.duration = float(value)


@dataclass
class Link(BaseModel):
    url: str
    title: str = None  # Used in InstagramProfile
    is_verified: bool = None  # Used in Threads
    id: int = None  # Used in Threads
    display_text: str = None  # Used in Threads


@dataclass
class Location(BaseModel):
    id: int
    name: str
    slug: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    has_public_page: Optional[bool] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None


# Threads-related dataclasses


@dataclass
class ThreadsProfile(BaseProfile):
    id: int
    username: str
    full_name: str
    biography: str
    is_verified: bool
    followers: int
    pictures: List[Picture]
    is_private: bool
    bio_links: Optional[List[Link]] = None
    is_threads_only_user: Optional[bool] = None

    @property
    def picture(self) -> Picture:
        return self.pictures[0]

    def serialize(self) -> Dict[str, Any]:
        row = super().serialize()
        row["bio_links"] = "\n".join(link["url"] for link in row["bio_links"])
        pictures = row.pop("pictures")
        pictures.sort(key=lambda obj: obj["width"], reverse=True)
        if not pictures:
            row["picture_url"] = row["picture_width"] = row["picture_height"] = None
        else:
            row["picture_url"] = pictures[0]["url"]
            row["picture_width"] = pictures[0]["width"]
            row["picture_height"] = pictures[0]["height"]
        return row

    @property
    def url(self):
        return f"https://www.threads.net/@{self.userame}"

    def get_media(self) -> List[Picture]:
        """Return all media objects of this profile (not from its posts)"""
        return self.pictures


@dataclass
class ThreadsPost(BasePost):
    id: str
    user_id: str
    username: str
    is_verified: bool
    text: str
    links: List[Link]
    published_at: datetime.datetime
    likes: int
    replies: int
    reposts: int
    quotes: int
    is_private: bool
    media: List[Union[Picture, Video]] = field(default_factory=list)
    reply_control: Optional[str] = None
    media_type: Optional[int] = None
    accessibility_caption: Optional[str] = None
    is_paid_partnership: Optional[bool] = None
    like_and_view_counts_disabled: Optional[bool] = None
    has_audio: Optional[bool] = None
    original_width: Optional[int] = None
    original_height: Optional[int] = None
    code: Optional[str] = None
    reshares: Optional[int] = None

    def serialize(self) -> Dict[str, Any]:
        row = super().serialize()
        for key in ("links", "media"):
            row[key] = "\n".join(link["url"] for link in row[key])
        return row

    @property
    def url(self):
        return f"https://www.threads.net/@{self.userame}/post/{self.code}"

    def get_media(self) -> List[Type[BaseMedia]]:
        """Return all media objects of this post"""
        return self.media or []


# Instagram-related dataclasses


@dataclass
class InstagramProfile(BaseProfile):
    id: int
    username: str
    full_name: str
    picture: Picture
    is_verified: Optional[bool] = None
    followers: Optional[int] = None
    followees: Optional[int] = None
    posts: Optional[int] = None
    is_private: Optional[bool] = None
    biography: Optional[str] = None
    bio_links: Optional[List[Link]] = None

    def serialize(self) -> Dict[str, Any]:
        row = super().serialize()
        flatten(row, {"picture": Picture})
        row["bio_links"] = "\n".join(link["url"] for link in row["bio_links"])
        return row

    @property
    def url(self):
        return f"https://www.instagram.com/{self.userame}/"

    def get_media(self) -> List[Picture]:
        """Return all media objects of this profile (not from its posts)"""
        return [self.picture]


@dataclass
class InstagramPost(BasePost):
    id: str
    pk: int
    code: str
    type: Union[Literal["photo"], Literal["video"], Literal["carousel"]]
    published_at: datetime.datetime
    author: InstagramProfile
    media: List[Union[Picture, Video]]
    pinned: Optional[bool] = None
    comments: Optional[int] = None
    likes: Optional[int] = None
    views: Optional[int] = None
    plays: Optional[int] = None
    thumbnail: Optional[Picture] = None
    text: Optional[str] = None
    author_full_name: Optional[str] = None
    accessibility_caption: Optional[str] = None
    location: Optional[Location] = None

    @property
    def url(self):
        return f"https://www.instagram.com/{self.author_username}/{self.code}/"

    def serialize(self) -> Dict[str, Any]:
        row = super().serialize()
        flatten(row, {"author": InstagramProfile, "thumbnail": Picture, "location": Location})
        row["media"] = "\n".join(obj["url"] for obj in row["media"])
        row["author_picture_url"] = row.pop("author_picture")["url"]
        return row

    def get_media(self) -> List[Type[BaseMedia]]:
        """Return all media objects of this post"""
        return ([self.thumbnail] if self.thumbnail else []) + (self.media or [])

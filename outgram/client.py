import time
from multiprocessing.pool import ThreadPool
from typing import Generator, List, Optional, Type, Union

import requests

from .models import BaseMedia, BasePost, BaseProfile
from .utils import default_browser_headers, random_user_agent, random_waiter


class BaseClient:

    def __init__(self, user_agent: Optional[str] = None, min_wait: float = 3.5, max_wait: float = 5.0):
        if user_agent is None:
            user_agent = random_user_agent()
        self._last_request_time = None
        self._wait = random_waiter(min_wait, max_wait)
        self.session = requests.Session()
        self.session.headers.update(default_browser_headers(user_agent))
        self.__post_init__()

    def __post_init__(self):
        raise NotImplementedError("Child classes must implement `__post_init__` method")

    def request(self, method, url, params=None, headers=None, data=None):
        if self._last_request_time is not None:  # Do not wait before the first request
            self._wait(self._last_request_time)
        response = self.session.request(method=method, url=url, params=params, headers=headers, data=data)
        self._last_request_time = time.time()  # TODO: this may not be thread safe
        return response

    def _download_media(self, media: Type[BaseMedia]) -> Type[BaseMedia]:
        """Download from the main URL of a media object (picture or video)"""
        response = self.request("GET", media.url)
        media.content = response.content
        media.content_type = response.headers["Content-Type"]
        return media

    def download_many(
        self, objects: List[Union[Type[BaseMedia], Type[BaseProfile], Type[BasePost]]], parallel: int = 8
    ) -> Generator[Type[BaseMedia], None, None]:
        """Download related media (skips already downloaded). Yields each one when download is finished and also updates inline"""
        to_download = []
        for obj in objects:
            to_download.extend([media for media in obj.get_media() if media.content is None])
        if len(to_download) == 1:  # Do not use threads
            yield self._download_media(to_download[0])
        else:
            with ThreadPool(processes=parallel) as pool:
                for media in pool.imap_unordered(self._download_media, to_download):
                    yield media

    def download(
        self, obj: Union[Type[BaseMedia], Type[BaseProfile], Type[BasePost]], parallel: int = 4
    ) -> Generator[Type[BaseMedia], None, None]:
        """Download related media (skips already downloaded). Yields each one when download is finished and also updates inline"""
        yield from self.download_many(objects=[obj], parallel=parallel)

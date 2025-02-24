# outgram

Python client library and command-line interface to access Threads and Instagram public GraphQL APIs. Useful to get
your own data out of Instagram and Threads for backup/archiving purposes. The concepts like profile, post, picture,
video are represented as dataclasses and all information is converted to high-level Python objects, making it easy to
use.

> **Note**: this project is developed for research purposes. It's your responsability the way you use it.


## License

`outgram` is licensed under the [GNU Lesser General Public License version 3 (LGPL
v3)](https://www.gnu.org/licenses/lgpl-3.0.pt-br.html). In short:

**✅ What you can do:**
- Use the library in proprietary or free/open source software projects
- Modify the library's source code
- Distribute the original or modified library along with another program, provided that:
  - You notify your users that the library is used in your program and is licensed under LGPL v3
  - You include a copy of the LGPL v3 with the distribution of your program

**🚫 What you cannot do:**
- Restrict your user's freedom to modify the library
- Distribute the library (original or modified) without providing the source code
- Incorporate significant parts of the library into your code without informing and providing the license


## Installation

Install [outgram from Python Package Index](https://pypi.org/project/outgram/):

```shell
pip install outgram
```


## Usage as a Library


### Threads Profile

```python
from pprint import pprint
from outgram import Threads

client = Threads()
username = "wsj"
simple_profile = client.simple_profile(username)  # Used to get user ID
user_id = simple_profile.id
profile = client.profile_from_user_id(user_id)
# or: profile = client.profile_from_username(username)
pprint(profile)

# Result:
# ThreadsProfile(id=787132,
#                username='natgeo',
#                full_name='National Geographic',
#                biography='Inspiring the explorer in everyone 🌎',
#                is_verified=True,
#                followers=15594746,
#                pictures=[Picture(width=150, height=150, content_type=None),
#                          Picture(width=320, height=320, content_type=None)],
#                is_private=False,
#                bio_links=[Link(url='https://on.natgeo.com/instagram',
#                                title=None,
#                                is_verified=False,
#                                id=17953782509778540,
#                                display_text=None)],
#                is_threads_only_user=False)
```


### Threads Profile Posts

```python
# NOTES:
# 1- Run the last example before running the code below
# 2- Since the client is not logged-in, only the last 25 posts are returned

for index, post in enumerate(client.profile_posts(user_id), start=1):
    print(f"Got post {index:02d}:")
    pprint(post)

# Result:
# Got post 01:
# ThreadsPost(id='3574333699320466889_787132',
#             user_id=787132,
#             username='natgeo',
#             is_verified=True,
#             text="Three-toed sloths can hang onto trees even when they're "
#                  "asleep 🦥 What's your favorite tree-climbing animal?",
#             links=[],
#             published_at=datetime.datetime(2025, 2, 23, 9, 30, 20, tzinfo=datetime.timezone.utc),
#             likes=761,
#             replies=17,
#             reposts=24,
#             quotes=3,
#             is_private=False,
#             media=[Picture(width=1439, height=1873, content_type=None)],
#             reply_control='everyone',
#             media_type=1,
#             accessibility_caption='Photo by National Geographic on February '
#                                   '23, 2025. May be an image of slow loris, '
#                                   "sloth and text that says 'ロ BRUCE BRUCEDALE "
#                                   "DALE'.",
#             is_paid_partnership=None,
#             like_and_view_counts_disabled=False,
#             has_audio=None,
#             original_width=1439,
#             original_height=1873,
#             code='DGalY_YtE3J',
#             reshares=6)
# [...]
```

### Instagram Profile

```python
from pprint import pprint
from outgram import Instagram

client = Instagram()
username = "crio.cafe"
user_id = client.user_id(username)
profile = client.profile_from_user_id(user_id)
# or: profile = client.profile_from_username(username)
pprint(profile)

# Result:
# InstagramProfile(id=21057648761,
#                  username='crio.cafe',
#                  full_name='CRIO',
#                  picture=Picture(width=None, height=None, content_type=None),
#                  is_verified=False,
#                  followers=20392,
#                  followees=3168,
#                  posts=145,
#                  is_private=False,
#                  biography='Melhor forma de começar o dia.\n'
#                            'Entregamos qualidade para todo o Brasil!\n'
#                            'Conheça nossa loja em SP\n'
#                            'R Cubatão 641 (2ª-Sáb) e Alameda Santos 1470 '
#                            '(2ª-6ª)',
#                  bio_links=[Link(url='http://delivery.crio.cafe',
#                                  title='Enviamos para todo Brasil',
#                                  is_verified=None,
#                                  id=None,
#                                  display_text=None)])
```

### Instagram Profile Posts

```python
# NOTE: run the last example before running the code below

posts = []
for index, post in enumerate(client.profile_posts(username), start=1):
    snippet = post.text[:35].replace("\n", " ")
    print(f"Got post {index:02} from @{post.author.username} ({post.published_at}): {snippet}...")
    posts.append(post)
    if index == 36:  # 3 pages, each with 12 posts
        break

# Result:
# Got post 01 from @crio.cafe (2024-01-19 18:54:50+00:00): Você ama queijo e pão de queijo com...
# Got post 02 from @crio.cafe (2023-12-11 15:00:25+00:00): Delicado, Equilibrado, Intenso, Aze...
# [...]
# Got post 35 from @crio.cafe (2023-12-22 14:02:57+00:00): DELICADO: café suave, para beber de...
# Got post 36 from @crio.cafe (2023-12-21 15:55:01+00:00): DOCE DE LEITE: sabor de fundo de pa...
```

> Note that not always `post.author.username` will be the same as the username passed to `.profile_posts`, since the
> user could be sharing a post from somebody else.

### Instagram Post

```python
post_codes = ("DEhf2uTJUs0", "DF-rojvO4g-", "C2SuqhGv3U0")
for index, post_code in enumerate(post_codes, start=1):
    post = client.post(post_code)
    snippet = post.text[:35].replace("\n", " ")
    print(f"Got specific post {index:02} from @{post.author.username} ({post.published_at}): {snippet}...")

# Result:
# Got specific post 01 from @zuck (2025-01-07 11:57:11+00:00): ⁠It's time to get back to our roots...
# Got specific post 02 from @oficialfernandatorres (2025-02-12 16:25:51+00:00): @goodmorningamerica at @abc   #fern...
# Got specific post 03 from @crio.cafe (2024-01-19 18:54:50+00:00): Você ama queijo e pão de queijo com...
```

### Download Media

Instead of looking at `.url` attributes on all `Picture` and `Video` objects, you can use the client object to
automatically download all media from posts in parallel, reusing the HTTPS session. The `download` method will work the
same way for both `Instagram` and `Threads` clients and will download all available media for any object of the types
`Picture`, `Video`, `InstagramProfile`, `InstagramPost`, `ThreadsProfile` and `ThreadsPost`:

```python
# NOTES:
# 1- Run the last example before running the code below
# 2- Since the media will be downloaded in parallel (using threads), the filenames ordering (like `xxx_001.jpg`,
#    `xxx_002.jpg` etc.) won't be the original order for each post (it's the finish order).

from pathlib import Path

for index, post in enumerate(posts, start=1):
    print(f"Downloading media for post {index:02d}")
    for media_index, downloaded in enumerate(client.download(post, parallel=4), start=1):
        extension = downloaded.content_type.split("/")[-1].lower()
        if extension == "jpeg":
            extension = "jpg"
        filename = Path("data") / f"{post.id}_{media_index:03d}.{extension}"
        downloaded.save(filename)
        print(f"  Saved in: {filename}")

# Result:
# Downloading media for post 01
#   Saved in: data/3283892310210737460_21057648761_001.jpg
#   Saved in: data/3283892310210737460_21057648761_002.jpg
#   Saved in: data/3283892310210737460_21057648761_003.jpg
#   Saved in: data/3283892310210737460_21057648761_004.jpg
#   Saved in: data/3283892310210737460_21057648761_005.jpg
#   Saved in: data/3283892310210737460_21057648761_006.jpg
#   Saved in: data/3283892310210737460_21057648761_007.jpg
#   Saved in: data/3283892310210737460_21057648761_008.jpg
# Downloading media for post 02
#   Saved in: data/3255507578954636322_21057648761_001.mp4
# [...]
```

> Note: if you need to download media to many different objects (profiles, posts etc.), better use `download_many`
> method.


## Usage via Command-Line Interface

The command-line interface (CLI) comprises many sub-commands, one for each action. They receive parameters and save
files (like CSV) with the results. The examples shown here will only cover some features - run `outgram --help` or
`outgram <subcommand> --help` for more details/options.


### Threads Profile

Get general information regarding one or more Threads user profiles. Profiles can be passed as usernames or user IDs.
User IDs are preferred since finding them based on username requires one more request. Example:

```shell
outgram threads profile \
    ayubionet diogocortiz wsj 42799100757 6828796459 \
    data/threads-profile.csv
```

The `data/threads-profile.csv` CSV file will be created with the following columns:

- `id`
- `username`
- `full_name`
- `biography`
- `is_verified`
- `followers`
- `is_private`
- `bio_links`
- `is_threads_only_user`
- `picture_url`
- `picture_width`
- `picture_height`


### Threads Profile Posts

Get list of posts from one or more Threads user profiles. Profiles can be passed as usernames or user IDs.
Different from Threads Profile, in this command usernames are preferred since finding them based on user ID requires
one more request. Example:

```shell
outgram threads profile-posts \
    --max-posts-per-user=10 \
    --max-posts=50 \
    ayubionet diogocortiz wsj 42799100757 6828796459 \
    data/threads-profile-posts.csv
```

The `data/threads-profile-posts.csv` CSV file will be created with the following columns:

- `id`
- `user_id`
- `username`
- `is_verified`
- `text`
- `links`
- `published_at`
- `likes`
- `replies`
- `reposts`
- `quotes`
- `is_private`
- `media`
- `reply_control`
- `media_type`
- `accessibility_caption`
- `is_paid_partnership`
- `like_and_view_counts_disabled`
- `has_audio`
- `original_width`
- `original_height`
- `code`
- `reshares`


### Threads Archive

Get all posts and media metadata for a list of Thredas profiles, export it to CSV, download all the media and save
everything into a ZIP file. Profiles can be passed as usernames or user IDs. Example:

```shell
outgram threads archive \
    wsj ayubionet \
    threads-archive.zip
```


### Instagram Profile

Get general information regarding one or more Instagram user profiles. Profiles can be passed as usernames or user IDs.
User IDs are preferred since finding them based on username requires one more request. Example:

```shell
outgram instagram profile \
    crio.cafe pythonbrasil 23456103 \
    data/instagram-profile.csv
```

The `data/instagram-profile.csv` CSV file will be created with the following columns:

- `id`
- `username`
- `full_name`
- `is_verified`
- `followers`
- `followees`
- `posts`
- `is_private`
- `biography`
- `bio_links`
- `picture_url`
- `picture_width`
- `picture_height`
- `picture_content_type`


### Instagram Profile Posts

Get list of posts from one or more Instagram user profiles. Profiles can be passed as usernames or user IDs. Different
from Instagram Profile, in this command usernames are preferred since finding them based on user ID requires one more
request. Example:

```shell
outgram instagram profile-posts \
    --max-posts-per-user=20 \
    --max-posts=50 \
    crio.cafe pythonbrasil 23456103 \
    data/instagram-profile-posts.csv
```

The `data/instagram-profile-posts.csv` CSV file will be created with the following columns:

- `id`
- `pk`
- `code`
- `type`
- `published_at`
- `media`
- `pinned`
- `comments`
- `likes`
- `views`
- `plays`
- `text`
- `accessibility_caption`
- `author_id`
- `author_bio_links`
- `author_biography`
- `author_followees`
- `author_followers`
- `author_full_name`
- `author_is_private`
- `author_is_verified`
- `author_picture_url`
- `author_posts`
- `author_username`
- `thumbnail_url`
- `thumbnail_width`
- `thumbnail_height`
- `thumbnail_content_type`
- `location_id`
- `location_name`
- `location_slug`
- `location_lat`
- `location_lng`
- `location_has_public_page`
- `location_address`
- `location_zip_code`
- `location_city`
- `location_country_code`


> Note: not all information will be filled. Check "Data Completion" section for more details.


### Instagram Post

Get list of posts from one or more post codes. You can get the post code from the URL: the code for
`https://www.instagram.com/p/C2SuqhGv3U0/` is `C2SuqhGv3U0`. Example:

```shell
outgram instagram post \
    --max-posts=3 \
    DEhf2uTJUs0 DF-rojvO4g- C_gVusByAQH DGLQHNhOoke COWY0ydHUrI DFWFT4LyfSJ \
    data/instagram-post.csv
```

The `data/instagram-post.csv` CSV file will be created with the columns as listed in the section "Instagram Profile
Posts".

> Note: not all information will be filled (and this is different from "Instagram Profile Posts"). Check "Data
> Completion" section for more details.


### Instagram Archive

Get all posts and media metadata for a list of Instagram profiles, export it to CSV, download all the media and save
everything into a ZIP file. Profiles can be passed as usernames or user IDs. Example:

```shell
outgram instagram archive \
    crio.cafe pythonbrasil \
    instagram-archive.zip
```


## Data Completion

It's important to note that the API may send you incomplete information depending on how you get that information, for example:
- The `InstagramPost` objects yielded by `Instagram.profile_posts` won't have full profile information from the author
  (like follower count), but the objects returned by `Instagram.post` will have it.
- Some resolutions (of thumbnails, for example) can be different depending on how you got your `*Post` object

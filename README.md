# outgram

Python client library and command-line interface to access Threads and Instagram public GraphQL APIs. Useful to get
your own data out of Instagram and Threads for backup/archiving purposes. The concepts like profile, post, picture,
video are represented as dataclasses and all information is converted to high-level Python objects, making it easy to
use.

> **Note**: this project is developed for research purposes. It's your responsability the way you use it.

## Maintenance

Instagram and Threads public Web responses can change without notice. When an endpoint or response parser stops working, follow the [Instagram scraper maintenance guide](docs/instagram-maintenance.md) or the [Threads scraper maintenance guide](docs/threads-maintenance.md). Threads profile collection uses the public page SSR payload for usernames and derives the public cursor-pagination bootstrap from that same page; numeric IDs remain unavailable. Threads live coverage is opt-in: `OUTGRAM_RUN_THREADS_SMOKE=1 pytest -m threads_smoke tests/test_threads.py`. For the stdlib-only Lightpanda installer and CDP capture utility, see [Lightpanda capture](docs/lightpanda-capture.md).


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
username = "lulaoficial"
profile = client.profile_from_username(username)
pprint(profile)

# Result:
# ThreadsProfile(id=63269934954,
#                username='lulaoficial',
#                full_name='Luiz Inácio Lula da Silva',
#                biography='Presidente do Brasil',
#                is_verified=True,
#                followers=3056469,
#                pictures=[Picture(width=150, height=150, content_type=None),
#                          Picture(width=320, height=320, content_type=None),
#                          Picture(width=640, height=640, content_type=None)],
#                is_private=False,
#                bio_links=[Link(url='https://lula.com.br',
#                                title=None,
#                                is_verified=False,
#                                id=17974322726518654,
#                                display_text=None)],
#                is_threads_only_user=None)
```


### Threads Profile Posts

```python
# Since the client is not logged in, public availability can vary.

for index, post in enumerate(client.profile_posts(username), start=1):
    print(f"Got post {index:02d}:")
    pprint(post)

# Result:
# Got post 01:
# ThreadsPost(id='3686828385308525791_63269934954',
#             user_id=63269934954,
#             username='lulaoficial',
#             is_verified=True,
#             text='Minhas amigas e meus amigos. É com grande orgulho e imensa alegria que informo: O Brasil está fora '
#                  'do mapa da fome, mais uma vez.\n\nO anúncio foi feito hoje (28) pela FAO/ONU. Isso significa que '
#                  'reduzimos a insegurança alimentar grave e a subnutrição para menos de 2,5% da população. Uma '
#                  'conquista histórica que mostra que com políticas públicas sérias e compromisso com o povo, é possível '
#                  'combater a fome e construir um país mais justo e solidário.',
#             links=[],
#             published_at=datetime.datetime(2025, 7, 28, 17, 36, 54, tzinfo=datetime.timezone.utc),
#             likes=16519,
#             replies=2172,
#             reposts=808,
#             quotes=97,
#             is_private=False,
#             media=[Picture(width=1080, height=1350, content_type=None)],
#             reply_control='everyone',
#             media_type=1,
#             accessibility_caption=None,
#             is_paid_partnership=None,
#             like_and_view_counts_disabled=False,
#             has_audio=None,
#             original_width=1080,
#             original_height=1350,
#             code='DMqPuH-JETf',
#             reshares=396)
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
#                  followers=27301,
#                  followees=3371,
#                  posts=209,
#                  is_private=False,
#                  biography='Cafés especiais, pão de queijo e doces autorais.\n'
#                            'Produzidos com cuidado em São Paulo.\n'
#                            'Lojas em SP + entrega para todo o Brasil.\n'
#                            '⬇️ Peça pelo site',
#                  bio_links=[Link(url='http://crio.cafe',
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
# Got post 35 from @luiz.mastropietro (2026-02-24 12:30:43+00:00): Café com água de Coco é bom??  Aqui...
# Got post 36 from @crio.cafe (2026-02-20 13:01:05+00:00): Um café diferente por dia!!  Aqui n...
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


### Catalog Export

Export a collected Instagram or Threads post CSV as Markdown and HTML. The required `USERNAME` identifies the profile whose collection produced the CSV; each post keeps its own author when shared posts have a different author. When `--format` is omitted, `OUTPUT` is a prefix and the command creates both `.md` and `.html` files.

```shell
outgram instagram export \
    data/instagram-profile-posts.csv \
    crio.cafe \
    "2026-07-31 09:16 UTC" \
    docs/instagram-catalog

outgram threads export \
    data/threads-profile-posts.csv \
    wsj \
    "2026-07-31 09:16 UTC" \
    docs/threads-catalog
```

Use `--format markdown` (or `md`) or `--format html` to generate one format; in that case `OUTPUT` is used unchanged. `--transcriptions-dir DIRECTORY` is optional and only reads existing external WebVTT (`.vtt`) files named `post_<id>_*.vtt`; outgram does not download, generate or transcribe audio or video.

### Public collection smoke tests

Network smoke tests are opt-in and validate public collection, media download and archive controllers directly. They do not test `argparse` parsing:

```shell
OUTGRAM_RUN_THREADS_SMOKE=1 pytest -m threads_smoke
OUTGRAM_RUN_SMOKE=1 pytest -m instagram_smoke
```


## Data Completion

It's important to note that the API may send you incomplete information depending on how you get that information, for example:
- The `InstagramPost` objects yielded by `Instagram.profile_posts` won't have full profile information from the author
  (like follower count), but the objects returned by `Instagram.post` will have it.
- Some resolutions (of thumbnails, for example) can be different depending on how you got your `*Post` object

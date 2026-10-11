# spotify-library-downloader

[English](README.md) | **Русский**

Скачивает твою библиотеку Spotify (лайки и целые альбомы) в `.opus` с тегами и обложками.
**Spotify API и своё приложение в Spotify не нужны**: список треков берётся из CSV с [exportify.net](https://exportify.net), звук — с YouTube Music.

## Что умеет

- **Точно находит треки на YouTube Music.** Сверяет длительность, название, исполнителя и альбом.
  Отсекает ремиксы, sped up, slowed, каверы и live, которых нет в оригинальном названии.
  Понимает транслитерацию: «Дора» в Spotify найдёт канал «Dora».
- **Если трека нет среди песен YouTube Music** (так бывает из-за региональных ограничений), берёт видео
  с канала самого исполнителя, но только при почти точном совпадении длительности.
- **Качает без перекодирования:** Opus ~160 kbps как есть. Обложка альбома из Spotify уменьшается до 1200px,
  номер трека в альбоме проставляется.
- **Синхронизирует папку с лайками:** убрал лайк — файл уходит в корзину, добавил — докачивается.
- **Качает альбом по ссылке**, даже если его нет в поиске.
- **Что не нашлось на YouTube Music, докачивает через телеграм-бота** (опционально, медленно, с дневным лимитом).

## Установка

Нужен Python 3.10+. ffmpeg и JS-рантайм для yt-dlp ставятся вместе с зависимостями.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
copy config.example.ini config.ini                   # Linux/macOS: cp
```

Все команды ниже запускаются Python'ом из `.venv` (`.venv\Scripts\python sync.py` или после активации venv).

## Подготовка

Личные файлы лежат в папке `data/`, она создаётся при первом запуске.

1. **Список треков.** Зайди на [exportify.net](https://exportify.net), экспортируй «Liked Songs»
   (или любой плейлист) и сохрани как `data/liked_songs.csv`.
2. **Куки YouTube.** Без них YouTube быстро начинает отвечать «Sign in to confirm you're not a bot».
   Залогинься в YouTube (лучше в приватном окне), выгрузи куки в формате Netscape любым расширением
   вроде «Get cookies.txt LOCALLY» и сохрани как `data/cookies.txt`.
3. **Только для бота:** получи `api_id` и `api_hash` на [my.telegram.org](https://my.telegram.org)
   и впиши их в `config.ini`. При первом запуске Telegram попросит номер телефона и код.

## Использование

```
python ytm_download.py --limit 5          # тест на пяти треках
python ytm_download.py                    # скачать всё с YouTube Music
python ytm_download.py --retry-failed     # повторить то, что не нашлось

python sync.py --dry-run                  # показать, что изменилось в лайках
python sync.py                            # убрать лишнее в корзину и докачать новое

python album.py https://open.spotify.com/album/... --dry-run   # треклист альбома
python album.py https://open.spotify.com/album/...             # скачать альбом
python album.py https://open.spotify.com/album/... --bot       # докачать альбом ботом

python download.py                        # докачать ботом то, чего нет на YouTube Music
python download.py --from-history         # забрать уже присланное ботом из истории чата
```

Флаги каждой команды — `--help`. Все команды можно прерывать: прогресс сохраняется,
и следующий запуск продолжит с того же места.

Треки, у которых в выводе стоит `<-- проверь` (score ниже 75), стоит послушать: возможно, нашлась не та версия.

## Как устроено

```
spotlib/
  config.py, state.py       настройки и файлы прогресса в data/
  library.py                Track, чтение CSV / .txt
  matching.py               оценка кандидатов с YouTube Music
  ytmusic.py                поиск и скачивание (ytmusicapi + yt-dlp)
  spotify.py, tagging.py    обложки, номера треков, альбомы; теги
  bot/                      скачивание через телеграм-бота (Telethon)
  commands/                 сами команды; файлы в корне — обёртки над ними
```

## Дисклеймер

Проект для личного использования. Соблюдай авторские права и правила сервисов,
которыми пользуешься. Слушать музыку лучше там, где за неё платят исполнителям.

## Лицензия

[MIT](LICENSE)

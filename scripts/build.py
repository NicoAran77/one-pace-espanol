#!/usr/bin/env python3
"""Genera el addon estatico de One Pace con subtitulos en espanol.

Uso: python -I scripts/build.py <repo-subtitulos> <carpeta-salida>

Fuentes:
  - onepace.arl.sh y fedew04: lista de episodios y torrents.
  - onepace.net: torrents actuales y listas de Pixeldrain en espanol.
  - one-pace/one-pace-public-subtitles: subtitulos .ass oficiales.
Solo usa la biblioteca estandar. Si una fuente falla, termina con error
y la version publicada anteriormente sigue intacta.
"""
import bisect
import concurrent.futures as cf
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request

BASE_URL = "https://nicoaran77.github.io/one-pace-espanol"
PREFIX = "opes_"
SERIES_ID = PREFIX + "onepace"
UA = {"User-Agent": "one-pace-espanol-addon"}
ARL = ("https://onepace.arl.sh", "onepace")
FEDEW = ("https://fedew04.github.io/OnePaceStremio", "pp_onepace")
# Bloqueo sano: si las fuentes devuelven mucho menos que esto, no se publica.
MIN_EPISODES = 400
MIN_SPANISH = 300

ARCS = {
    "Romance Dawn": "RO", "Orange Town": "OR", "Syrup Village": "SY",
    "Gaimon": "GA", "Baratie": "BA", "Arlong Park": "AR",
    "The Adventures of Buggy's Crew": "BUGGYS_CREW", "Loguetown": "LO",
    "Reverse Mountain": "RM", "Whisky Peak": "WH",
    "The Trials of Koby-Meppo": "COVER_KOBYMEPPO", "Little Garden": "LI",
    "Drum Island": "DI", "Arabasta": "AL", "Alabasta": "AL", "Jaya": "JA",
    "Skypiea": "SK", "Long Ring Long Land": "LR", "Water Seven": "WS",
    "Enies Lobby": "EN", "Post-Enies Lobby": "PEN", "Thriller Bark": "TB",
    "Sabaody Archipelago": "SAB", "Amazon Lily": "AM", "Impel Down": "IM",
    "The Adventures of the Straw Hats": "COVER_SHSS",
    "If You Could Go Anywhere... The Adventures of the Straw Hats": "COVER_SHSS",
    "Marineford": "MA", "Post-War": "PW", "Post War": "PW",
    "Return to Sabaody": "RTS", "Fishman Island": "FI", "Punk Hazard": "PH",
    "Dressrosa": "DR", "Zou": "ZO", "Whole Cake Island": "WC",
    "Reverie": "REV", "Wano": "WA", "Egghead": "EH", "Specials": "SP",
}


SAGAS = [
    ("East Blue", ["RO", "OR", "SY", "GA", "BA", "AR", "BUGGYS_CREW", "LO"]),
    ("Alabasta", ["RM", "WH", "COVER_KOBYMEPPO", "LI", "DI", "AL"]),
    ("Skypiea", ["JA", "SK"]),
    ("Water 7", ["LR", "WS", "EN", "PEN"]),
    ("Thriller Bark", ["TB"]),
    ("Guerra de Marineford", ["SAB", "AM", "IM", "COVER_SHSS", "MA", "PW"]),
    ("Isla Gyojin", ["RTS", "FI"]),
    ("Dressrosa", ["PH", "DR"]),
    ("Cuatro Emperadores", ["ZO", "WC", "REV", "WA"]),
    ("Saga Final", ["EH"]),
]
NOISE_STYLE = re.compile(r"credit|warning|kara|romaji|rom$|kanji|furigana|^ndt", re.I)
VECTOR = re.compile(r"[mnlbsc\d\s.\-]+")
ARL_RENUMBER = {
    # arl numera Long Ring Long Land desde 1; onepace.net desde 0.
    **{f"LR_{n}": f"LR_{n - 1}" for n in range(1, 8)},
    # onepace.net dividio Post-Enies Lobby: el antiguo 3 ahora es el 4, y asi sucesivamente.
    "PEN_3": "PEN_4", "PEN_4": "PEN_5", "PEN_5": "PEN_6",
}
FEDEW_RENUMBER = {"PEN_3": "PEN_4", "PEN_4": "PEN_5", "PEN_5": "PEN_6"}
OLD_PEN_BATCH = "59497fc3"


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


ARC_BY_NORM = {norm(k): v for k, v in ARCS.items()}
ARC_BY_NORM["thetrialsofkobymeppo"] = "COVER_KOBYMEPPO"
ARC_BY_NORM["whiskeypeak"] = "WH"


def fetch(url, attempts=3):
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            error = e
        except Exception as e:  # red inestable: se reintenta
            error = e
        time.sleep(2 * (attempt + 1))
    raise error


def fetch_json(url):
    return json.loads(fetch(url))


def load_addon(base, meta_id):
    meta = fetch_json(f"{base}/meta/series/{meta_id}.json")["meta"]

    def one(video):
        url = f"{base}/stream/series/{urllib.parse.quote(video['id'])}.json"
        try:
            return video["id"], fetch_json(url).get("streams", [])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return video["id"], []
            raise

    with cf.ThreadPoolExecutor(16) as pool:
        return meta, dict(pool.map(one, meta["videos"]))


def release_id(name):
    """'[One Pace][1] Romance Dawn 01 [1080p]...' -> 'RO_1'."""
    m = re.search(r"\[One Pace\](?:\[[^\]]*\])?\s*(.+?)\s+(\d+)\s*(?:\[|\.|$)", name)
    if not m:
        return None
    prefix = ARC_BY_NORM.get(norm(m.group(1)))
    return f"{prefix}_{int(m.group(2))}" if prefix else None


def parse_site():
    page = fetch("https://onepace.net/es-419/watch").decode("utf-8", "replace")
    current = {}  # hash -> nombre publicado
    for ih, dn in re.findall(r'btih:([0-9a-fA-F]{40})(?:&amp;|&)dn=([^"]+)"', page):
        current[ih.lower()] = urllib.parse.unquote_plus(html.unescape(dn))
    lists = {"sub": [], "dub": []}
    groups = re.findall(
        r'<span id="[^"]*"[^>]*>(Subtitulos|Subtítulos|Doblaje) en espa[^<]*</span><ul role="list"[^>]*>(.*?)</ul>',
        page, re.S)
    for label, body in groups:
        kind = "dub" if label == "Doblaje" else "sub"
        options = {}
        for list_id, res in re.findall(
                r'pixeldrain\.[a-z]+/l/([A-Za-z0-9]+)".*?<span[^>]*>(\d+)p</span>', body, re.S):
            options[int(res)] = list_id
        if options:
            res = 1080 if 1080 in options else max(options)
            lists[kind].append((res, options[res]))
    # Listas en ingles, para los episodios que aun no tienen espanol.
    english = fetch("https://onepace.net/en/watch").decode("utf-8", "replace")
    lists["en"] = []
    for body in re.findall(r'<span id="[^"]*"[^>]*>English Subtitles</span><ul role="list"[^>]*>(.*?)</ul>', english, re.S):
        options = {}
        for list_id, res in re.findall(
                r'pixeldrain\.[a-z]+/l/([A-Za-z0-9]+)".*?<span[^>]*>(\d+)p</span>', body, re.S):
            options[int(res)] = list_id
        if options:
            res = 1080 if 1080 in options else max(options)
            lists["en"].append((res, options[res]))
    return current, lists


def parse_pixeldrain(lists):
    found = {"sub": {}, "dub": {}, "en": {}}

    def one(item):
        kind, (res, list_id) = item
        return kind, res, fetch_json(f"https://pixeldrain.net/api/list/{list_id}")

    items = [(k, x) for k, values in lists.items() for x in values]
    with cf.ThreadPoolExecutor(6) as pool:
        for kind, res, data in pool.map(one, items):
            for f in data.get("files", []):
                vid = release_id(f["name"])
                if vid and f.get("mime_type", "").startswith("video/"):
                    found[kind][vid] = {"id": f["id"], "res": res}
    return found


def ass_time(value):
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def srt_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def parse_ass(path):
    """Devuelve [(inicio, fin, texto)] sin etiquetas ni dibujos."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().splitlines()
    fmt, rows, seen = None, [], set()
    lengths = {}
    for line in lines:
        if line.startswith("Format:") and "Text" in line:
            fmt = [x.strip() for x in line[7:].split(",")]
        elif line.startswith("Dialogue:") and fmt:
            parts = line[9:].split(",", len(fmt) - 1)
            if len(parts) != len(fmt):
                continue
            row = dict(zip(fmt, parts))
            raw, style = row["Text"], row.get("Style", "").strip()
            if re.search(r"\\p[1-9]", raw) or re.search(r"\\[kK][fo]?\d", raw) or "mpv.io" in raw:
                continue
            if NOISE_STYLE.search(style):
                continue
            text = re.sub(r"\{[^}]*\}", "", raw)
            text = text.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
            text = "\n".join(x.strip() for x in text.split("\n") if x.strip())
            if not text or VECTOR.fullmatch(text):
                continue
            start, end = ass_time(row["Start"]), ass_time(row["End"])
            if end <= start or (start, end, text) in seen:
                continue
            seen.add((start, end, text))
            rows.append((start, end, text, style))
            lengths.setdefault(style, []).append(len(text))
    # Estilos con casi solo silabas sueltas son efectos de karaoke, no dialogo.
    fragments = {s for s, v in lengths.items() if len(v) >= 20 and sum(v) / len(v) <= 3}
    rows = sorted((r for r in rows if r[3] not in fragments), key=lambda r: (r[0], r[1]))
    # Une repeticiones cuadro a cuadro del mismo texto en una sola linea.
    events, last = [], {}
    for start, end, text, _ in rows:
        i = last.get(text)
        if i is not None and start <= events[i][1] + 0.1:
            events[i] = (events[i][0], max(events[i][1], end), text)
        else:
            last[text] = len(events)
            events.append((start, end, text))
    return [e for e in events if e[1] - e[0] >= 0.2]


def to_srt(events):
    return "\n".join(
        f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{t}\n" for i, (s, e, t) in enumerate(events, 1))


def english_starts(subs_repo):
    """Inicios de linea de los subtitulos ingleses, para detectar episodios cambiados."""
    folder = os.path.join(subs_repo, "main", "Release", "Final Subs")
    starts = {}
    for name in os.listdir(folder):
        if re.search(r"\[(?:720|1080)p\]\.ass$", name):
            vid = release_id(name)
            if vid:
                events = parse_ass(os.path.join(folder, name))
                if events:
                    starts[vid] = sorted(e[0] for e in events)
    return starts


def alignment(reference, events):
    """Fraccion de lineas de referencia con una linea propia a menos de 0,5 s."""
    own = sorted(e[0] for e in events)
    hits = 0
    for t in reference:
        i = bisect.bisect(own, t)
        if any(0 <= j < len(own) and abs(t - own[j]) < 0.5 for j in (i - 1, i)):
            hits += 1
    return hits / len(reference)


def spanish_files(subs_repo):
    """{id: {'es-419': ruta, 'es': ruta}} leyendo main/NN Arco/EE/*.ass."""
    found = {}
    main = os.path.join(subs_repo, "main")
    for arc in sorted(os.listdir(main)):
        m = re.match(r"\d\d (.+)$", arc)
        arc_dir = os.path.join(main, arc)
        if not m or not os.path.isdir(arc_dir):
            continue
        for ep in sorted(os.listdir(arc_dir)):
            ep_dir = os.path.join(arc_dir, ep)
            if not os.path.isdir(ep_dir) or not ep.isdigit():
                continue
            for name in os.listdir(ep_dir):
                if re.search(r"\bdub\b", name, re.I):
                    continue
                lang = re.search(r" (es-419|es|en)\.ass$", name)
                if not lang:
                    continue
                if m.group(1).startswith("Cover Stories"):
                    prefix = ARC_BY_NORM.get(norm(name[: lang.start()]))
                    vid = f"{prefix}_1" if prefix else None
                else:
                    prefix = ARC_BY_NORM.get(norm(m.group(1)))
                    vid = f"{prefix}_{int(ep)}" if prefix else None
                if vid:
                    found.setdefault(vid, {})[lang.group(1)] = os.path.join(ep_dir, name)
    return found


def read_site_page(locale, duration, anime, manga):
    """Devuelve (titulos por id en orden, arcos en orden) de una pagina de onepace.net."""
    page = fetch(f"https://onepace.net/{locale}/watch").decode("utf-8", "replace")
    page = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", page, flags=re.S)
    found = [(html.unescape(m.group(1)).strip(), m.start()) for m in re.finditer(r">([^<]+)<", page)]
    found = [x for x in found if x[0] and x[0] not in ("·", "•")]
    tokens = [x[0] for x in found]
    titles, arcs, current_arc = {}, [], None
    for i, token in enumerate(tokens):
        if token != duration:
            continue
        k = i - 1
        while k > 0 and i - k < 12 and tokens[k] != anime:
            k -= 1
        start = k if tokens[k] == anime else i
        if tokens[start - 2] == manga:
            start -= 2
        elif tokens[start - 3] == manga:
            start -= 3
        title = tokens[start - 1]
        if tokens[start - 2] == ":" and tokens[start - 3].isdigit():
            titles[(len(arcs) - 1, int(tokens[start - 3]))] = title
        elif tokens[start - 2] != "Special:" and tokens[start - 2] != "Especial:":
            images = re.findall(r"url=%2F_next%2Fstatic%2Fmedia%2F([^&\"]+?\.(?:jpe?g|png|webp))", page[:found[i][1]])
            image = f"https://onepace.net/_next/static/media/{urllib.parse.unquote(images[-1])}" if images else None
            arcs.append({"name": title, "description": tokens[i + 2], "image": image})
    return titles, arcs


def site_arcs():
    """Titulos oficiales por id y arcos con nombre, imagen y descripcion en espanol."""
    english, arcs = read_site_page("en", "Duration", "Covered anime episodes", "Covered manga chapters")
    _, spanish = read_site_page("es-419", "Duración", "Episodios del anime incluidos", "Episodios del manga incluidos")
    if len(spanish) == len(arcs):
        for arc, translated in zip(arcs, spanish):
            arc["description"] = translated["description"]
    titles = {}
    for (index, number), title in english.items():
        prefix = ARC_BY_NORM.get(norm(arcs[index]["name"]))
        if prefix and title != "Untitled":
            titles[f"{prefix}_{number}"] = title
    for arc in arcs:
        arc["prefix"] = ARC_BY_NORM.get(norm(arc["name"]))
    return titles, arcs


def renumber(meta, streams, mapping):
    """Pasa los ids de una fuente a la numeracion actual de onepace.net."""
    if not all(old in streams for old in mapping):
        return meta["videos"], streams  # la fuente ya cambio: no tocar
    videos, moved = [], {}
    for video in meta["videos"]:
        video = dict(video)
        new = mapping.get(video["id"], video["id"])
        if new != video["id"]:
            video.pop("overview", None)
            if new.startswith("PEN_"):
                video["episode"] = int(new.rsplit("_", 1)[1])
        moved[new] = streams.get(video["id"], [])
        video["id"] = new
        videos.append(video)
    for vid in ("PEN_1", "PEN_2"):  # el lote antiguo no coincide con el corte actual
        moved[vid] = [s for s in moved.get(vid, []) if not s["infoHash"].startswith(OLD_PEN_BATCH)]
    return videos, moved


def merge_videos(arl_meta, arl_streams, fedew_meta, fedew_streams, current, titles):
    """Une episodios. Si un mismo id sigue con otro titulo, no es el mismo episodio."""
    arl_videos, arl_streams = renumber(arl_meta, arl_streams, ARL_RENUMBER)
    fedew_videos, fedew_streams = renumber(fedew_meta, fedew_streams, FEDEW_RENUMBER)
    for video in arl_videos + fedew_videos:
        video["title"] = titles.get(video["id"], video.get("title", ""))
    videos = {v["id"]: dict(v) for v in arl_videos}
    torrents = {k: list(v) for k, v in arl_streams.items()}
    # fedew numera las temporadas distinto: se usa la de arl para cada arco.
    arc_season = {v["id"].rsplit("_", 1)[0]: v["season"] for v in arl_videos}
    for video in fedew_videos:
        vid, known = video["id"], videos.get(video["id"])
        video["season"] = arc_season.get(vid.rsplit("_", 1)[0], video["season"])
        if known and vid in titles or not known:
            videos.setdefault(vid, dict(video))
            torrents.setdefault(vid, []).extend(fedew_streams.get(vid, []))
        elif norm(known.get("title", "")) == norm(video.get("title", "")):
            torrents.setdefault(vid, []).extend(fedew_streams.get(vid, []))
    # La lista de arl arrastra titulos desplazados en Long Ring Long Land.
    if "LR_0" in videos and "LR_0" not in titles:
        videos["LR_0"]["title"] = "Prologue"
    # Torrents publicados en onepace.net de un solo episodio.
    for ih, name in current.items():
        vid = release_id(name)
        if not vid or "1080p" not in name:
            continue
        if vid not in videos:
            prefix, number = vid.rsplit("_", 1)
            seasons = [v["season"] for k, v in videos.items() if k.rsplit("_", 1)[0] == prefix]
            if not seasons:
                continue
            title = re.sub(r"^\[One Pace\](\[[^\]]*\])?\s*|\s*\[.*$", "", name)
            videos[vid] = {"id": vid, "season": seasons[0], "episode": int(number), "title": titles.get(vid, title)}
        torrents.setdefault(vid, []).append({"infoHash": ih})
    return videos, torrents


def torrent_streams(entries, current, spanish, english):
    """Los subtitulos propios siguen la edicion actual: solo van con torrents actuales."""
    unique = {}
    for s in entries:
        unique.setdefault((s["infoHash"].lower(), s.get("fileIdx")), s)
    fresh = {k: v for k, v in unique.items() if k[0] in current}
    # Con una edicion actual disponible, las antiguas solo causarian desincronia.
    chosen = fresh or unique
    result = []
    for (ih, idx), s in chosen.items():
        name = current.get(ih, "")
        res = re.search(r"(\d{3,4})p", name)
        quality = f"Torrent {res.group(1)}p" if res else "Torrent"
        subs = [x for x in s.get("subtitles", []) if x.get("lang") == "eng"]
        if ih in current:
            if spanish:
                note = "Español: elige «Español» en subtítulos"
                subs = spanish + subs
            else:
                subs = english or subs
                note = "Aún sin español: subtítulos en inglés" if subs else "Aún sin español"
        else:
            note = "Edición antigua: subtítulos en inglés" if subs else "Edición antigua"
        stream = {
            "name": "One Pace\nTorrent",
            "title": f"{quality}\n{note}",
            "infoHash": ih,
            "subtitles": subs,
            "behaviorHints": {"bingeGroup": "onepace-torrent"},
        }
        if idx is not None:
            stream["fileIdx"] = idx
        result.append(stream)
    return result


def http_stream(item, label, group):
    return {
        "name": f"One Pace\n{item['res']}p",
        "title": f"{label}\nPixeldrain, puede tener límite diario",
        "url": f"https://pixeldrain.net/api/file/{item['id']}",
        "behaviorHints": {"bingeGroup": group},
    }


def write_json(root, rel, data):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def main(subs_repo, out):
    arl_meta, arl_streams = load_addon(*ARL)
    fedew_meta, fedew_streams = load_addon(*FEDEW)
    current, lists = parse_site()
    pixeldrain = parse_pixeldrain(lists)
    es_files = spanish_files(subs_repo)
    english = english_starts(subs_repo)
    titles, site_arc_list = site_arcs()
    videos, torrents = merge_videos(arl_meta, arl_streams, fedew_meta, fedew_streams, current, titles)

    for folder in ("meta", "stream", "subs", "catalog"):
        shutil.rmtree(os.path.join(out, folder), ignore_errors=True)
    os.makedirs(os.path.join(out, "subs"))

    published, report = [], {"desincronizados": [], "sin_referencia": [], "sin_video": [], "solo_ingles": [], "sin_ingles": []}
    with_es = with_pixeldrain = 0
    for vid, video in videos.items():
        subtitles = []
        for lang in ("es-419", "es"):
            path = es_files.get(vid, {}).get(lang)
            if not path:
                continue
            events = parse_ass(path)
            if not events:
                continue
            reference = english.get(vid)
            if reference is None:
                report["sin_referencia"].append(f"{vid} {lang}")
            else:
                score = alignment(reference, events)
                if score < 0.4:
                    report["desincronizados"].append(f"{vid} {lang}: {score:.2f}")
            with open(os.path.join(out, "subs", f"{vid}_{lang}.srt"), "w", encoding="utf-8", newline="\n") as f:
                f.write(to_srt(events))
            subtitles.append({"id": f"{vid}_{lang}", "lang": "spa", "url": f"{BASE_URL}/subs/{vid}_{lang}.srt"})
            break  # una sola opcion: la latina si existe, si no la de Espana

        # Los subtitulos propios solo se ofrecen con un torrent de la edicion actual.
        fresh_torrent = any(s["infoHash"].lower() in current for s in torrents.get(vid, []))
        has_spanish = (bool(subtitles) and fresh_torrent) or vid in pixeldrain["sub"]
        english_subs = []
        en_path = es_files.get(vid, {}).get("en")
        if not has_spanish and en_path:
            events = parse_ass(en_path)
            if events:
                with open(os.path.join(out, "subs", f"{vid}_en.srt"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(to_srt(events))
                english_subs = [{"id": f"{vid}_en", "lang": "eng", "url": f"{BASE_URL}/subs/{vid}_en.srt"}]

        streams = torrent_streams(torrents.get(vid, []), current, subtitles, english_subs)
        if vid in pixeldrain["sub"]:
            streams.append(http_stream(pixeldrain["sub"][vid], "Subtítulos latinos incluidos en el video", "onepace-es-sub"))
        if vid in pixeldrain["dub"]:
            streams.append(http_stream(pixeldrain["dub"][vid], "Doblaje latino", "onepace-es-dub"))
        if not has_spanish and vid in pixeldrain["en"]:
            streams.append(http_stream(pixeldrain["en"][vid], "Aún sin español: subtítulos en inglés incluidos en el video", "onepace-en-sub"))
        if streams and not has_spanish:
            report["solo_ingles"].append(vid)
            if not english_subs and vid not in pixeldrain["en"] and not any(
                    x.get("lang") == "eng" for s in streams for x in s.get("subtitles", [])):
                report["sin_ingles"].append(vid)
        if not streams:
            report["sin_video"].append(vid)
            continue
        if any(x.get("lang") == "spa" for st in streams for x in st.get("subtitles", [])) or vid in pixeldrain["sub"]:
            with_es += 1
        if vid in pixeldrain["sub"] or vid in pixeldrain["dub"]:
            with_pixeldrain += 1

        write_json(out, f"stream/series/{PREFIX}{vid}.json", {"streams": streams})
        entry = {k: video[k] for k in ("season", "episode", "title", "overview", "thumbnail", "released") if k in video}
        entry["id"] = PREFIX + vid
        entry.setdefault("released", "2013-01-01T00:00:00.000Z")
        published.append(entry)

    if len(published) < MIN_EPISODES or with_es < MIN_SPANISH:
        sys.exit(f"Resultado sospechoso ({len(published)} episodios, {with_es} en espanol): no se publica.")

    # Stremio solo muestra "Season N": cada temporada es una saga y cada titulo nombra su arco.
    by_arc = {}
    for video in published:
        by_arc.setdefault(video["id"][len(PREFIX):].rsplit("_", 1)[0], []).append(video)
    season_of = {prefix: i for i, (_, arcs) in enumerate(SAGAS, 1) for prefix in arcs}
    position, videos_by_saga = {}, []
    for arc in site_arc_list:
        episodes = by_arc.pop(arc["prefix"], None)
        if not episodes:
            continue
        season = season_of.get(arc["prefix"], len(SAGAS))  # un arco nuevo va en la ultima saga
        episodes = sorted(episodes, key=lambda v: v["episode"])
        for video in episodes:
            position[season] = position.get(season, 0) + 1
            number = int(video["id"].rsplit("_", 1)[1])
            title = video["title"] if len(episodes) == 1 else f"{arc['name']} {number:02}: {video['title']}"
            videos_by_saga.append({**video, "season": season, "episode": position[season], "title": title})
    if by_arc:
        sys.exit(f"Episodios sin arco en onepace.net: {sorted(by_arc)}")
    guide = "\n".join(f"Temporada {i}: {name}" for i, (name, _) in enumerate(SAGAS, 1))
    meta = {
        "id": SERIES_ID, "type": "series", "name": "One Pace (español)",
        "poster": arl_meta.get("poster"), "background": arl_meta.get("background"),
        "logo": arl_meta.get("logo"), "website": "https://onepace.net",
        "genres": arl_meta.get("genres"),
        "description": "One Pace recorta el anime de One Piece para acercarlo al ritmo del manga, "
                       "con subtítulos oficiales en español y doblaje latino cuando existen.\n" + guide,
        "videos": videos_by_saga,
    }
    write_json(out, f"meta/series/{SERIES_ID}.json", {"meta": meta})
    write_json(out, "catalog/series/onepace-es.json", {"metas": [
        {k: meta[k] for k in ("id", "type", "name", "poster", "background", "logo", "description", "genres")}]})
    write_json(out, "manifest.json", {
        "id": "io.github.nicoaran77.onepace.es", "version": "1.3.1",
        "name": "One Pace en español",
        "description": "One Pace por sagas, con subtítulos oficiales en español y doblaje latino cuando existen. "
                       "Ve a Descubrir → Series → One Pace en español.",
        "logo": arl_meta.get("logo"),
        "resources": [{"name": "meta", "types": ["series"], "idPrefixes": [PREFIX]},
                      {"name": "stream", "types": ["series"], "idPrefixes": [PREFIX]}, "catalog"],
        "types": ["series"], "idPrefixes": [PREFIX],
        "catalogs": [{"type": "series", "id": "onepace-es", "name": "One Pace en español"}],
    })

    summary = {
        "episodios": len(published), "con_espanol": with_es, "con_pixeldrain": with_pixeldrain,
        "pixeldrain_sub": len(pixeldrain["sub"]), "pixeldrain_dub": len(pixeldrain["dub"]),
        "listas_sub": len(lists["sub"]), "listas_dub": len(lists["dub"]),
        "torrents_site": len(current), **report,
    }
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

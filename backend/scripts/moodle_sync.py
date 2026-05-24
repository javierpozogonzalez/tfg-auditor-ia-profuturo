"""
Sincronizacion incremental Moodle → Neo4j.

Descarga posts nuevos de los foros de ProFuturo via Moodle REST API
e inserta Author, Discussion, Community y Post en Neo4j.

Uso manual:  python scripts/moodle_sync.py --once
Scheduler:   importar moodle_sync_job() en main.py (ya configurado)
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from scripts.clean_data import clean_html, analyze_sentiment

# ── Config ────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
MOODLE_URL     = os.getenv("MOODLE_URL", "").rstrip("/")
MOODLE_TOKEN   = os.getenv("MOODLE_API_TOKEN", "")
# CSV de IDs de cursos ProFuturo a sincronizar (ej: "101,102,103")
COURSE_IDS_RAW = os.getenv("MOODLE_SYNC_COURSE_IDS", "")

_log_file = Path(__file__).resolve().parent.parent / "moodle_sync.log"
logging.basicConfig(
    filename=str(_log_file),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("moodle_sync")

# ── Moodle REST helpers ───────────────────────────────────────────────────────
_WSURL = "{moodle}/webservice/rest/server.php"

def _ws(function: str, **params) -> dict | list:
    url = _WSURL.format(moodle=MOODLE_URL)
    payload = {
        "wstoken": MOODLE_TOKEN,
        "moodlewsrestformat": "json",
        "wsfunction": function,
        **params,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("exception"):
        raise RuntimeError(f"Moodle error [{function}]: {data.get('message')}")
    return data


def get_forums_for_course(course_id: int) -> list[dict]:
    return _ws("mod_forum_get_forums_by_courses", **{"courseids[0]": course_id})


def get_discussions(forum_id: int, page: int = 0, per_page: int = 50) -> list[dict]:
    data = _ws(
        "mod_forum_get_forum_discussions",
        forumid=forum_id,
        sortby="timemodified",
        sortdirection="DESC",
        page=page,
        perpage=per_page,
    )
    return data.get("discussions", []) if isinstance(data, dict) else data


def get_posts(discussion_id: int) -> list[dict]:
    data = _ws("mod_forum_get_forum_discussion_posts", discussionid=discussion_id)
    return data.get("posts", []) if isinstance(data, dict) else data


# ── Neo4j upsert ──────────────────────────────────────────────────────────────
_MERGE_POST = """
MERGE (c:Community {name: $community})
MERGE (a:Author    {name: $author})
MERGE (d:Discussion {id: $disc_id})
  ON CREATE SET d.topic = $topic, d.created = $disc_created
MERGE (d)-[:PERTAINS_TO]->(c)
MERGE (p:Post {id: $post_id})
  ON CREATE SET
    p.content   = $content,
    p.date      = datetime($date_iso),
    p.sentiment = $sentiment
MERGE (a)-[:WROTE]->(p)
MERGE (p)-[:IN_DISCUSSION]->(d)
"""


def _upsert_post(session, *, community: str, author: str, disc_id: str,
                 topic: str, disc_created: str, post_id: str, content: str,
                 date_iso: str, sentiment: str = "neutral") -> None:
    session.run(
        _MERGE_POST,
        community=community, author=author, disc_id=disc_id, topic=topic,
        disc_created=disc_created, post_id=post_id, content=content,
        date_iso=date_iso, sentiment=sentiment,
    )


def _get_last_sync(session) -> datetime:
    row = session.run(
        "MATCH (s:SyncMeta {id: 'moodle_sync'}) RETURN s.last_sync AS ts"
    ).single()
    if row and row["ts"]:
        return datetime.fromisoformat(str(row["ts"]))
    return datetime.now() - timedelta(days=90)


def _set_last_sync(session, ts: datetime) -> None:
    session.run(
        "MERGE (s:SyncMeta {id: 'moodle_sync'}) SET s.last_sync = $ts",
        ts=ts.isoformat(),
    )


# ── Main sync logic ───────────────────────────────────────────────────────────
def run_sync(course_ids: list[int], full: bool = False) -> dict:
    if not MOODLE_TOKEN:
        logger.warning("MOODLE_API_TOKEN no configurado — sync omitido")
        return {"status": "skipped", "reason": "no token"}
    if not course_ids:
        logger.warning("MOODLE_SYNC_COURSE_IDS vacío — sync omitido")
        return {"status": "skipped", "reason": "no course ids"}

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    inserted = 0
    skipped  = 0

    try:
        with driver.session() as session:
            last_sync = datetime(2000, 1, 1) if full else _get_last_sync(session)
            logger.info("Sync desde %s | cursos=%s", last_sync.isoformat(), course_ids)

            for course_id in course_ids:
                try:
                    forums = get_forums_for_course(course_id)
                except Exception as exc:
                    logger.error("Error obteniendo foros del curso %s: %s", course_id, exc)
                    continue

                for forum in forums:
                    forum_id    = forum.get("id")
                    community   = forum.get("name", f"curso_{course_id}")
                    page = 0

                    while True:
                        try:
                            discussions = get_discussions(forum_id, page=page)
                        except Exception as exc:
                            logger.error("Error discussions forum %s: %s", forum_id, exc)
                            break

                        if not discussions:
                            break

                        new_in_page = 0
                        for disc in discussions:
                            disc_modified = datetime.fromtimestamp(disc.get("timemodified", 0))
                            if disc_modified <= last_sync:
                                # Discusiones ordenadas por timemodified DESC
                                # Si esta ya la tenemos, las siguientes también
                                break

                            disc_id      = str(disc.get("id"))
                            disc_topic   = disc.get("name", "sin tema")
                            disc_created = datetime.fromtimestamp(
                                disc.get("timecreated", 0)
                            ).isoformat()

                            try:
                                posts = get_posts(disc.get("id"))
                            except Exception as exc:
                                logger.error("Error posts disc %s: %s", disc_id, exc)
                                continue

                            for post in posts:
                                post_ts = datetime.fromtimestamp(post.get("timecreated", 0))
                                if post_ts <= last_sync:
                                    skipped += 1
                                    continue

                                raw_content   = post.get("message", "")
                                clean_content = clean_html(raw_content)
                                if len(clean_content.strip()) < 10:
                                    skipped += 1
                                    continue
                                post_sentiment = analyze_sentiment(clean_content)
                                logger.info(
                                    "Post %s limpiado: %d → %d chars, sentimiento: %s",
                                    post.get("id"),
                                    len(raw_content),
                                    len(clean_content),
                                    post_sentiment,
                                )

                                _upsert_post(
                                    session,
                                    community   = community,
                                    author      = post.get("userfullname", "Desconocido"),
                                    disc_id     = disc_id,
                                    topic       = disc_topic,
                                    disc_created= disc_created,
                                    post_id     = str(post.get("id")),
                                    content     = clean_content,
                                    date_iso    = post_ts.isoformat(),
                                    sentiment   = post_sentiment,
                                )
                                inserted += 1
                                new_in_page += 1

                        if new_in_page == 0:
                            break
                        page += 1

            _set_last_sync(session, datetime.now())

    finally:
        driver.close()

    logger.info("Sync completado — insertados=%d omitidos=%d", inserted, skipped)
    return {"status": "ok", "inserted": inserted, "skipped": skipped}


def moodle_sync_job() -> dict:
    ids = [int(x.strip()) for x in COURSE_IDS_RAW.split(",") if x.strip().isdigit()]
    return run_sync(ids)


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once",  action="store_true", help="Ejecutar una vez y salir")
    parser.add_argument("--full",  action="store_true", help="Sync completo (ignora last_sync)")
    parser.add_argument("--courses", default=COURSE_IDS_RAW, help="IDs separados por coma")
    args = parser.parse_args()

    ids = [int(x.strip()) for x in args.courses.split(",") if x.strip().isdigit()]
    result = run_sync(ids, full=args.full)
    print(result)

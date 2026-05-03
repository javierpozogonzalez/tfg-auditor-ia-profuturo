import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MOODLE_URL       = os.getenv("MOODLE_URL", "")
MOODLE_API_TOKEN = os.getenv("MOODLE_API_TOKEN", "")
SIMULATION_MODE  = os.getenv("MOODLE_SIMULATION_MODE", "true").lower() == "true"

_sim_counter = 0


def _moodle_request(function: str, params: dict) -> dict:
    """Ejecuta una llamada autenticada a la REST API de Moodle."""
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    payload = {
        "wstoken": MOODLE_API_TOKEN,
        "wsfunction": function,
        "moodlewsrestformat": "json",
        **params,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("exception"):
        raise RuntimeError(f"Moodle API error [{function}]: {data.get('message', data)}")
    return data


def post_to_forum(discussion_id: int, subject: str, message: str) -> dict:
    """
    Publica una respuesta en una discusion existente de Moodle.

    Usa mod_forum_add_discussion_post de la REST API.

    En MOODLE_SIMULATION_MODE=true no hace ninguna peticion real.

    Retorna: {
        "success": bool,
        "post_id": int | None,
        "url": str | None,
        "simulated": bool
    }
    """
    global _sim_counter

    if SIMULATION_MODE:
        _sim_counter += 1
        sim_id = 900000 + _sim_counter
        logger.info(
            "[SIMULACION] post_to_forum — discussion_id=%s subject='%s...' post_id_simulado=%s",
            discussion_id, subject[:60], sim_id,
        )
        return {"success": True, "post_id": sim_id, "url": None, "simulated": True}

    if not MOODLE_URL or not MOODLE_API_TOKEN:
        logger.error("post_to_forum: MOODLE_URL o MOODLE_API_TOKEN no configurados")
        return {"success": False, "post_id": None, "url": None, "simulated": False}

    try:
        result  = _moodle_request("mod_forum_add_discussion_post", {
            "postid":        discussion_id,
            "subject":       subject,
            "message":       message,
            "messageformat": 1,
        })
        post_id = result.get("postid") or result.get("id")
        url     = f"{MOODLE_URL}/mod/forum/discuss.php?d={discussion_id}#p{post_id}"
        logger.info("Post publicado en Moodle — discussion=%s post=%s", discussion_id, post_id)
        return {"success": True, "post_id": post_id, "url": url, "simulated": False}
    except Exception as exc:
        logger.error("Error en post_to_forum (discussion=%s): %s", discussion_id, exc)
        return {"success": False, "post_id": None, "url": None, "simulated": False}


def create_forum_discussion(forum_id: int, subject: str, message: str) -> dict:
    """
    Crea una nueva discusion en un foro de Moodle.

    Usa mod_forum_add_discussion de la REST API.

    En MOODLE_SIMULATION_MODE=true no hace ninguna peticion real.

    Retorna: {
        "success": bool,
        "discussion_id": int | None,
        "url": str | None,
        "simulated": bool
    }
    """
    global _sim_counter

    if SIMULATION_MODE:
        _sim_counter += 1
        sim_id = 800000 + _sim_counter
        logger.info(
            "[SIMULACION] create_forum_discussion — forum_id=%s subject='%s...' discussion_id_simulado=%s",
            forum_id, subject[:60], sim_id,
        )
        return {"success": True, "discussion_id": sim_id, "url": None, "simulated": True}

    if not MOODLE_URL or not MOODLE_API_TOKEN:
        logger.error("create_forum_discussion: MOODLE_URL o MOODLE_API_TOKEN no configurados")
        return {"success": False, "discussion_id": None, "url": None, "simulated": False}

    try:
        result  = _moodle_request("mod_forum_add_discussion", {
            "forumid":       forum_id,
            "subject":       subject,
            "message":       message,
            "messageformat": 1,
        })
        disc_id = result.get("discussionid") or result.get("id")
        url     = f"{MOODLE_URL}/mod/forum/discuss.php?d={disc_id}"
        logger.info("Discusion creada en Moodle — forum=%s discussion=%s", forum_id, disc_id)
        return {"success": True, "discussion_id": disc_id, "url": url, "simulated": False}
    except Exception as exc:
        logger.error("Error en create_forum_discussion (forum=%s): %s", forum_id, exc)
        return {"success": False, "discussion_id": None, "url": None, "simulated": False}

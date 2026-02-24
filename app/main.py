import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import os
import asyncio
import requests
import json
import subprocess
import sys
import time
from datetime import datetime
import secrets
import hashlib

from fastapi import FastAPI, HTTPException, Request, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .ffmpeg_runner import FFmpegManager
from .logger import logger
from .core.database import Database
from .tasks.monitor import monitor_models_task
from .tasks.convert import auto_convert_recordings_task
from .services.flaresolverr import FlareSolverrClient
from .services.chaturbate_auth import ChaturbateAuthService
from .services.chaturbate_api import ChaturbateAPI
from .api import auth as auth_router
from .api import discover as discover_router
from .api import following as following_router

# Environment
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "data")))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
HLS_TIME = int(os.getenv("HLS_TIME", "4"))
HLS_LIST_SIZE = int(os.getenv("HLS_LIST_SIZE", "6"))
CB_RESOLVER_ENABLED = os.getenv("CB_RESOLVER_ENABLED", "false").lower() in {"1", "true", "yes"}
PASSWORD = os.getenv("PASSWORD", "")  # Mot de passe optionnel
CHATURBATE_USERNAME = os.getenv("CHATURBATE_USERNAME", "")
CHATURBATE_PASSWORD = os.getenv("CHATURBATE_PASSWORD", "")
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191")

# Ensure dirs
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger.info("Répertoire de sortie", path=str(OUTPUT_DIR))
logger.info("FFmpeg path", path=FFMPEG_PATH)
logger.info("HLS Configuration", hls_time=HLS_TIME, hls_list_size=HLS_LIST_SIZE)
logger.info("Chaturbate Resolver", enabled=CB_RESOLVER_ENABLED)
if PASSWORD:
    logger.info("Authentification activée", protected=True)
else:
    logger.info("Authentification désactivée", protected=False)

app = FastAPI(title="P-StreamRec", version="0.1.0")

# Gestionnaire de sessions simples (en mémoire)
active_sessions = set()

def generate_session_token() -> str:
    """Génère un token de session sécurisé"""
    return secrets.token_urlsafe(32)

def verify_password(provided_password: str) -> bool:
    """Vérifie si le mot de passe fourni correspond"""
    return provided_password == PASSWORD

def is_authenticated(session_token: Optional[str]) -> bool:
    """Vérifie si la session est valide"""
    if not PASSWORD:
        return True  # Pas d'authentification requise
    return session_token in active_sessions

# Middleware d'authentification
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Routes publiques (pas besoin d'authentification)
    public_paths = ["/login", "/api/login", "/favicon.ico"]
    public_prefixes = ["/static/", "/api/chaturbate/status"]

    if request.url.path in public_paths or any(
        request.url.path.startswith(p) for p in public_prefixes
    ):
        return await call_next(request)
    
    # Si pas de mot de passe configuré, laisser passer
    if not PASSWORD:
        return await call_next(request)
    
    # Vérifier le token de session
    session_token = request.cookies.get("session_token")
    
    if not is_authenticated(session_token):
        # Rediriger vers la page de login
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Non authentifié"}
            )
        return RedirectResponse(url="/login", status_code=303)
    
    return await call_next(request)

# Middleware pour logger toutes les requêtes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log requête
    logger.api_request(request.method, request.url.path)
    
    # Traiter requête
    response = await call_next(request)
    
    # Log réponse
    duration_ms = (time.time() - start_time) * 1000
    logger.api_response(response.status_code, request.url.path, duration_ms)
    
    return response

# Configuration CORS permissive pour Umbrel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Autoriser toutes les origines
    allow_credentials=False,  # Pas de credentials avec wildcard origin
    allow_methods=["*"],  # Autoriser toutes les méthodes (GET, POST, etc.)
    allow_headers=["*"],  # Autoriser tous les headers
)

# Register API routers
app.include_router(auth_router.router)
app.include_router(discover_router.router)
app.include_router(following_router.router)

# Static mounts
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Route protégée pour les enregistrements
@app.get("/streams/records/{username}/{filename}")
async def serve_recording_protected(username: str, filename: str):
    """Sert un enregistrement (TS ou MP4) avec vérification qu'il n'est pas en cours"""
    from fastapi.responses import FileResponse
    
    logger.api_request("GET", f"/streams/records/{username}/{filename}")
    
    # Sécurité: vérifier le nom de fichier
    if ".." in filename or "/" in filename or not (filename.endswith(".ts") or filename.endswith(".mp4")):
        logger.warning("Tentative d'accès fichier invalide", username=username, filename=filename)
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    
    # Pour les fichiers TS, vérifier que ce n'est pas l'enregistrement en cours
    if filename.endswith(".ts"):
        today = datetime.now().strftime("%Y-%m-%d")
        recording_date = filename.replace(".ts", "")
        
        # Vérifier si une session est active pour cet utilisateur
        active_sessions = manager.list_status()
        is_recording = any(s.get('person') == username and s.get('running') for s in active_sessions)
        
        if is_recording and recording_date == today:
            logger.warning("Accès bloqué à enregistrement en cours", username=username, filename=filename, date=today)
            raise HTTPException(
                status_code=403, 
                detail="Cet enregistrement est en cours. Regardez le live à la place."
            )
    
    # Servir le fichier
    file_path = OUTPUT_DIR / "records" / username / filename
    
    if not file_path.exists():
        logger.error("Fichier introuvable", username=username, filename=filename, path=str(file_path))
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    
    file_size = file_path.stat().st_size
    logger.file_operation("Lecture", str(file_path), size=file_size)
    
    return FileResponse(
        path=str(file_path),
        media_type="video/mp2t",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes"  # Important pour la lecture vidéo
        }
    )

# Mount pour les sessions HLS live uniquement
app.mount("/streams/sessions", StaticFiles(directory=str(OUTPUT_DIR / "sessions")), name="streams_sessions")
app.mount("/streams/thumbnails", StaticFiles(directory=str(OUTPUT_DIR / "thumbnails")), name="streams_thumbnails")

manager = FFmpegManager(str(OUTPUT_DIR), ffmpeg_path=FFMPEG_PATH, hls_time=HLS_TIME, hls_list_size=HLS_LIST_SIZE)

# Database SQLite
DB_FILE = OUTPUT_DIR / "streamrec.db"
db = Database(DB_FILE)

# Chaturbate API (initialized at startup)
chaturbate_api: Optional[ChaturbateAPI] = None

# Fichier de sauvegarde des modèles (côté serveur)
MODELS_FILE = OUTPUT_DIR / "models.json"

def load_models():
    """Charge la liste des modèles depuis le fichier JSON"""
    if MODELS_FILE.exists():
        try:
            with open(MODELS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_models_to_file(models):
    """Sauvegarde la liste des modèles dans le fichier JSON"""
    try:
        with open(MODELS_FILE, 'w') as f:
            json.dump(models, f, indent=2)
        return True
    except Exception as e:
        logger.error("Erreur sauvegarde modèles", exc_info=True, error=str(e))
        return False


class StartBody(BaseModel):
    target: str  # Either an m3u8 URL or a username (if resolver enabled)
    source_type: Optional[str] = None  # "m3u8" or "chaturbate" or None for auto
    name: Optional[str] = None  # display name
    person: Optional[str] = None  # recording bucket (per person)
    auto_start: Optional[bool] = False  # True si démarrage automatique


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "session"


@app.get("/")
async def index():
    """Root now serves Discover page"""
    return FileResponse(str(STATIC_DIR / "discover.html"))


@app.get("/discover")
async def discover_page():
    """Discover page - browse live models"""
    return FileResponse(str(STATIC_DIR / "discover.html"))


@app.get("/following")
async def following_page():
    """Following page - tracked models from Chaturbate"""
    return FileResponse(str(STATIC_DIR / "following.html"))


@app.get("/recordings")
async def recordings_page():
    """Recordings page - all recordings across models"""
    return FileResponse(str(STATIC_DIR / "recordings.html"))


@app.get("/settings")
async def settings_page():
    """Settings page"""
    return FileResponse(str(STATIC_DIR / "settings.html"))


@app.get("/watch/{username}")
async def watch_page(username: str):
    """Watch page - view live stream or recording for a model"""
    return FileResponse(str(STATIC_DIR / "watch.html"))


@app.get("/dashboard")
async def dashboard_page():
    """Legacy dashboard (old index.html)"""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/login")
async def login_page():
    """Page de connexion"""
    return FileResponse(str(STATIC_DIR / "login.html"))


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
async def api_login(body: LoginBody, response: Response):
    """Endpoint de connexion"""
    if not PASSWORD:
        raise HTTPException(status_code=400, detail="Authentification non configurée")
    
    if not verify_password(body.password):
        logger.warning("Tentative de connexion échouée")
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    
    # Créer une session
    session_token = generate_session_token()
    active_sessions.add(session_token)
    
    # Définir le cookie de session
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400 * 30,  # 30 jours
        samesite="lax"
    )
    
    logger.info("Connexion réussie")
    return {"success": True, "message": "Connecté"}


@app.post("/api/logout")
async def api_logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Endpoint de déconnexion"""
    if session_token and session_token in active_sessions:
        active_sessions.remove(session_token)
    
    response.delete_cookie(key="session_token")
    logger.info("Déconnexion")
    return {"success": True, "message": "Déconnecté"}


@app.get("/favicon.ico")
async def favicon():
    """Retourne un favicon SVG simple"""
    from fastapi.responses import Response
    svg_favicon = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#6366f1"/>
        <circle cx="50" cy="35" r="8" fill="white"/>
        <rect x="35" y="45" width="30" height="35" rx="5" fill="white"/>
        <rect x="42" y="52" width="16" height="20" fill="#6366f1"/>
    </svg>'''
    return Response(content=svg_favicon, media_type="image/svg+xml")


@app.get("/api/version")
async def get_version():
    """Retourne les informations de version"""
    version_file = BASE_DIR / "version.json"
    if version_file.exists():
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error("Erreur lecture version.json", error=str(e))
    else:
        logger.warning("Fichier version.json introuvable", path=str(version_file))
    return {"version": "1.0.0", "releaseDate": "2025-10-05"}


# ============================================
# GitOps Endpoints
# ============================================

@app.get("/api/git/status")
async def git_status():
    """Vérifie s'il y a des mises à jour disponibles depuis Git"""
    try:
        # Vérifier si on est dans un repo Git
        is_git = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).returncode == 0
        
        if not is_git:
            return {
                "isGitRepo": False,
                "message": "Not a Git repository"
            }
        
        # Récupérer le commit actuel
        current_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Récupérer la branche actuelle
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Fetch pour vérifier les updates
        subprocess.run(
            ["git", "fetch"],
            cwd=BASE_DIR,
            capture_output=True
        )
        
        # Vérifier s'il y a des commits en avance sur origin
        remote_commit = subprocess.run(
            ["git", "rev-parse", f"origin/{current_branch}"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        has_updates = current_commit != remote_commit
        
        # Compter les commits en retard
        if has_updates:
            behind_count = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..origin/{current_branch}"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True
            ).stdout.strip()
        else:
            behind_count = "0"
        
        return {
            "isGitRepo": True,
            "currentBranch": current_branch,
            "currentCommit": current_commit[:8],
            "remoteCommit": remote_commit[:8],
            "hasUpdates": has_updates,
            "behindBy": int(behind_count),
            "canUpdate": has_updates
        }
        
    except Exception as e:
        return {
            "isGitRepo": False,
            "error": str(e)
        }


@app.post("/api/git/update")
async def git_update():
    """Effectue un git pull et redémarre l'application"""
    try:
        # Vérifier si on est dans un repo Git
        is_git = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).returncode == 0
        
        if not is_git:
            raise HTTPException(status_code=400, detail="Not a Git repository")
        
        # Sauvegarder le commit actuel
        old_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # Git pull
        pull_result = subprocess.run(
            ["git", "pull"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        )
        
        if pull_result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Git pull failed: {pull_result.stderr}"
            )
        
        # Nouveau commit
        new_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        updated = old_commit != new_commit
        
        # Si des changements ont été appliqués, redémarrer
        if updated:
            # Planifier le redémarrage dans 2 secondes
            asyncio.create_task(restart_application())
            
            return {
                "success": True,
                "updated": True,
                "oldCommit": old_commit[:8],
                "newCommit": new_commit[:8],
                "message": "Update applied. Application will restart in 2 seconds...",
                "output": pull_result.stdout
            }
        else:
            return {
                "success": True,
                "updated": False,
                "commit": new_commit[:8],
                "message": "Already up to date",
                "output": pull_result.stdout
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def restart_application():
    """Redémarre l'application après un délai"""
    await asyncio.sleep(2)
    logger.info("Redémarrage application après GitOps update", task="gitops")
    
    # Si on utilise uvicorn avec --reload, toucher un fichier Python suffit
    try:
        # Toucher main.py pour déclencher le reload
        Path(__file__).touch()
    except:
        # Sinon, exit et laisser le processus manager redémarrer
        os.execv(sys.executable, [sys.executable] + sys.argv)


@app.get("/model.html")
async def model_page():
    return FileResponse(str(STATIC_DIR / "model.html"))


@app.post("/api/start")
async def api_start(body: StartBody):
    start_time = time.time()
    logger.section("API /api/start - Démarrage Enregistrement")
    logger.debug("Requête reçue", 
                target=body.target, 
                source_type=body.source_type,
                person=body.person,
                name=body.name,
                auto_start=body.auto_start)
    
    target = (body.target or "").strip()
    if not target:
        logger.error("Champ 'target' vide dans la requête")
        raise HTTPException(status_code=400, detail="Champ 'target' requis")
    
    # Si c'est un auto-start, vérifier que auto_record est activé dans la DB
    if body.auto_start:
        username = body.person or target
        model = await db.get_model(username)
        if model:
            auto_record = bool(model.get('auto_record', True))
            if not auto_record:
                logger.warning("Auto-record désactivé pour ce modèle", username=username)
                raise HTTPException(status_code=403, detail=f"Auto-record désactivé pour {username}")
        else:
            logger.warning("Modèle non trouvé en DB, auto-start refusé", username=username)
            raise HTTPException(status_code=404, detail=f"Modèle {username} non trouvé")

    logger.info("Paramètres validés", target=target, source_type=body.source_type)

    m3u8_url: Optional[str] = None
    person: Optional[str] = (body.person or "").strip() or None

    # Determine source type
    stype = (body.source_type or "").lower().strip()
    logger.debug("Détermination type source", source_type=stype or 'auto', target=target)

    if stype == "m3u8" or target.startswith("http://") or target.startswith("https://"):
        logger.info("URL M3U8 directe détectée", url=target[:80])
        m3u8_url = target
    else:
        logger.subsection("Résolution Chaturbate")
        # Try chaturbate if allowed or explicit
        if stype in ("", "chaturbate"):
            if not CB_RESOLVER_ENABLED:
                logger.error("Chaturbate Resolver désactivé", CB_RESOLVER_ENABLED=False)
                raise HTTPException(status_code=400, detail="Résolution Chaturbate désactivée. Fournissez une URL m3u8 directe ou activez CB_RESOLVER_ENABLED.")
            try:
                logger.progress("Appel Chaturbate Resolver", username=target)
                from .resolvers.chaturbate import resolve_m3u8_async, resolve_m3u8 as resolve_chaturbate
                # Try async resolver first (authenticated)
                try:
                    m3u8_url = await resolve_m3u8_async(target)
                except Exception:
                    m3u8_url = resolve_chaturbate(target)
                if not m3u8_url:
                    logger.error("Resolver retourné None", username=target)
                    raise HTTPException(status_code=400, detail=f"Impossible de trouver le flux pour {target}")
                logger.success("M3U8 résolu", username=target, url=m3u8_url[:80])
                if not person:
                    person = target  # username
                    logger.debug("Person défini depuis target", person=person)
            except HTTPException:
                raise
            except Exception as e:
                error_detail = f"Échec résolution Chaturbate pour {target}: {str(e)}"
                logger.error(error_detail, exc_info=True, username=target)
                raise HTTPException(status_code=400, detail=error_detail)
        else:
            logger.error("Source type invalide", source_type=stype)
            raise HTTPException(status_code=400, detail="source_type invalide. Utilisez 'm3u8' ou 'chaturbate'.")

    # If person still not set (direct m3u8), infer from URL
    if not person:
        try:
            pu = urlparse(m3u8_url)
            # try last non-empty path part without extension
            parts = [p for p in pu.path.split('/') if p]
            base = parts[-2] if len(parts) >= 2 else (parts[-1] if parts else pu.hostname or "session")
            base = base.split('.')[0]
            person = base or (pu.hostname or "session")
        except Exception:
            person = "session"

    person = slugify(person)
    logger.info("Identifiant slugifié", person=person, display_name=body.name)

    logger.subsection("Démarrage Session FFmpeg")
    try:
        sess = manager.start_session(m3u8_url, person=person, display_name=body.name)
        duration_ms = (time.time() - start_time) * 1000
        logger.success("Session créée avec succès", 
                      session_id=sess.id,
                      person=person,
                      duration_ms=f"{duration_ms:.2f}")
    except RuntimeError as e:
        logger.error("Session déjà en cours", person=person, error=str(e))
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.critical("Erreur création session", exc_info=True, person=person, error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

    return {
        "id": sess.id,
        "person": person,
        "name": sess.name,
        "playback_url": sess.playback_url,
        "record_path": sess.record_path_today(),
        "created_at": sess.created_at,
        "running": True,
    }


@app.get("/api/status")
async def api_status():
    return manager.list_status()


@app.post("/api/stop/{session_id}")
async def api_stop(session_id: str):
    ok = manager.stop_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session introuvable")
    return {"stopped": True, "id": session_id}


@app.get("/api/model/{username}/status")
async def get_model_status(username: str):
    """Récupère le statut et les infos d'un modèle depuis le cache SQLite"""
    # Lire directement depuis le cache SQLite (mis à jour par la tâche de monitoring)
    model = await db.get_model(username)
    
    if model:
        return {
            "username": username,
            "isOnline": bool(model.get('is_online')),
            "thumbnail": f"/api/thumbnail/{username}",
            "viewers": model.get('viewers', 0)
        }
    else:
        # Modèle non trouvé dans le cache
        return {
            "username": username,
            "isOnline": False,
            "thumbnail": f"/api/thumbnail/{username}",
            "viewers": 0
        }


@app.get("/api/model/{username}/stream")
async def get_model_stream(username: str):
    """Récupère l'URL du stream live pour un modèle (même sans enregistrement)"""
    try:
        # Vérifier si le modèle est en ligne
        model = await db.get_model(username)
        if not model or not model.get('is_online'):
            raise HTTPException(status_code=404, detail=f"Modèle {username} n'est pas en ligne")
        
        # Résoudre l'URL du stream via Chaturbate
        if not CB_RESOLVER_ENABLED:
            raise HTTPException(status_code=400, detail="Chaturbate Resolver désactivé")

        from .resolvers.chaturbate import resolve_m3u8_async
        try:
            m3u8_url = await resolve_m3u8_async(username)
        except Exception:
            from .resolvers.chaturbate import resolve_m3u8 as resolve_chaturbate
            m3u8_url = resolve_chaturbate(username)
        
        if not m3u8_url:
            raise HTTPException(status_code=404, detail=f"Impossible de trouver le flux pour {username}")
        
        return {
            "username": username,
            "streamUrl": m3u8_url,
            "isOnline": True
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erreur récupération stream", username=username, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/thumbnail/{username}")
async def get_thumbnail(username: str):
    """Sert la miniature depuis le cache (générée par la tâche de monitoring)"""
    from fastapi.responses import FileResponse, Response
    
    # Récupérer le chemin de la miniature depuis SQLite
    model = await db.get_model(username)
    
    if model and model.get('thumbnail_path'):
        thumb_path = Path(model['thumbnail_path'])
        
        if thumb_path.exists():
            return FileResponse(
                path=str(thumb_path),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=60"}
            )
    
    # Chercher manuellement dans les dossiers si pas en cache
    # Ordre de préférence: live > chaturbate > offline
    for subdir in ["live", "chaturbate", "offline"]:
        thumb_path = OUTPUT_DIR / "thumbnails" / subdir / f"{username}.jpg"
        if thumb_path.exists():
            return FileResponse(
                path=str(thumb_path),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=60"}
            )
    
    # SVG placeholder si aucune miniature trouvée
    svg_placeholder = f'''<svg xmlns="http://www.w3.org/2000/svg" width="280" height="200">
        <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#6366f1;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#a855f7;stop-opacity:1" />
            </linearGradient>
        </defs>
        <rect fill="url(#grad)" width="280" height="200"/>
        <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="system-ui" font-size="18" font-weight="600">{username}</text>
        <text x="50%" y="70%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="system-ui" font-size="12" opacity="0.8">📷 Loading...</text>
    </svg>'''
    
    return Response(
        content=svg_placeholder,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=10"}
    )


@app.get("/api/dashboard")
async def get_dashboard():
    """
    Endpoint optimisé qui retourne TOUTES les données depuis le cache SQLite
    Ultra-rapide car tout est pré-calculé par la tâche de monitoring
    """
    try:
        # Récupérer tous les modèles depuis SQLite (déjà avec statut à jour)
        models = await db.get_all_models()
        
        # Récupérer les sessions actives
        active_sessions = manager.list_status()
        
        # Formater les données pour le frontend
        models_info = []
        
        for model in models:
            username = model['username']
            
            # Récupérer le nombre d'enregistrements depuis SQLite
            recordings_count = await db.get_recordings_count(username)
            
            model_info = {
                "username": username,
                "isOnline": bool(model.get('is_online', False)),
                "isRecording": bool(model.get('is_recording', False)),
                "viewers": model.get('viewers', 0),
                "thumbnail": f"/api/thumbnail/{username}",
                "recordingsCount": recordings_count,
                "recordQuality": model.get('record_quality', 'best'),
                "retentionDays": model.get('retention_days', 30),
                "autoRecord": bool(model.get('auto_record', True))
            }
            
            models_info.append(model_info)
        
        # Retourner tout d'un coup
        return {
            "models": models_info,
            "sessions": active_sessions,
            "timestamp": int(time.time() * 1000)
        }
    
    except Exception as e:
        logger.error("Erreur dashboard", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings/{username}")
async def list_recordings(username: str):
    """Liste uniquement les enregistrements MP4 convertis"""
    from datetime import datetime
    from .core.utils import format_bytes
    
    # Récupérer depuis SQLite
    recordings_db = await db.get_recordings(username)
    
    recordings = []
    thumbnails_dir = OUTPUT_DIR / "thumbnails" / username
    
    for rec in recordings_db:
        # FILTRER: Ne retourner que les enregistrements convertis avec MP4
        if not rec.get('is_converted') or not rec.get('mp4_path'):
            continue
        
        mp4_path = Path(rec['mp4_path'])
        
        # Vérifier que le fichier MP4 existe
        if not mp4_path.exists():
            continue
        
        stat = mp4_path.stat()
        
        # Miniature
        thumb_path = thumbnails_dir / f"{mp4_path.stem}.jpg"
        thumb_url = f"/api/recording-thumbnail/{username}/{mp4_path.stem}.jpg"
        
        # Formater la durée
        duration_seconds = rec.get('duration_seconds', 0)
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        if hours > 0:
            duration_str = f"{hours}h{minutes:02d}m"
        else:
            duration_str = f"{minutes}m{seconds:02d}s"
        
        # Calculer la taille en MB ou GB
        mp4_size = rec.get('mp4_size', 0)
        if mp4_size >= 1000 * 1024 * 1024:  # >= 1000 MB
            size_display = f"{mp4_size / 1024 / 1024 / 1024:.2f} GB"
        else:
            size_display = f"{mp4_size / 1024 / 1024:.0f} MB"
        
        recordings.append({
            "recordingId": rec.get('recording_id', mp4_path.stem),
            "filename": mp4_path.name,
            "date": mp4_path.stem,
            "size": mp4_size,
            "size_formatted": format_bytes(mp4_size),
            "size_mb": round(mp4_size / 1024 / 1024, 2),
            "size_display": size_display,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"/streams/records/{username}/{mp4_path.name}",
            "thumbnail": thumb_url if thumb_path.exists() else None,
            "duration": duration_seconds,
            "duration_str": duration_str,
            "isConverted": True,
            "mp4": {
                "filename": mp4_path.name,
                "size": mp4_size,
                "size_formatted": format_bytes(mp4_size),
                "url": f"/streams/records/{username}/{mp4_path.name}"
            }
        })
    
    return {"recordings": recordings}


@app.get("/api/all-recordings")
async def get_all_recordings(
    page: int = 1,
    limit: int = 20,
    username: str = None
):
    """Get all recordings across all models with pagination"""
    from .core.utils import format_bytes

    result = await db.get_all_recordings_paginated(
        page=page,
        limit=limit,
        username_filter=username
    )

    recordings = []
    for rec in result["recordings"]:
        mp4_path = rec.get("mp4_path")
        if not mp4_path:
            continue

        mp4_file = Path(mp4_path)
        file_stem = mp4_file.stem
        rec_username = rec.get("username", "")

        # Format duration
        duration_seconds = rec.get("duration_seconds", 0)
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        if hours > 0:
            duration_str = f"{hours}h{minutes:02d}m"
        else:
            duration_str = f"{minutes}m{seconds:02d}s"

        # Format size
        mp4_size = rec.get("mp4_size") or rec.get("file_size", 0)

        # Thumbnail
        thumb_path = OUTPUT_DIR / "thumbnails" / rec_username / f"{file_stem}.jpg"

        recordings.append({
            "recordingId": rec.get("recording_id", file_stem),
            "username": rec_username,
            "filename": mp4_file.name,
            "date": file_stem,
            "size": mp4_size,
            "size_formatted": format_bytes(mp4_size),
            "duration": duration_seconds,
            "duration_str": duration_str,
            "url": f"/streams/records/{rec_username}/{mp4_file.name}",
            "thumbnail": f"/api/recording-thumbnail/{rec_username}/{file_stem}.jpg" if thumb_path.exists() else None,
            "createdAt": rec.get("created_at"),
        })

    # Get distinct usernames for filter dropdown
    usernames = await db.get_distinct_recording_usernames()

    return {
        "recordings": recordings,
        "total": result["total"],
        "totalSize": result["total_size"],
        "totalSizeFormatted": format_bytes(result["total_size"]),
        "page": result["page"],
        "limit": result["limit"],
        "totalPages": result["total_pages"],
        "usernames": usernames,
    }


@app.get("/api/recording-thumbnail/{username}/{filename}")
async def get_recording_thumbnail(username: str, filename: str):
    """Récupère la miniature d'un enregistrement"""
    from fastapi.responses import FileResponse, Response
    
    # Sécurité
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nom invalide")
    
    thumb_path = OUTPUT_DIR / "thumbnails" / username / filename
    
    if thumb_path.exists():
        return FileResponse(
            path=str(thumb_path),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )
    
    # Placeholder SVG si pas de miniature
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">
        <rect fill="#1a1f3a" width="320" height="180"/>
        <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#a0aec0" font-size="16">📹 Génération...</text>
    </svg>'''
    
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/models")
async def get_models():
    """Récupère la liste des modèles depuis SQLite"""
    models = await db.get_all_models()
    
    # Formater pour compatibilité avec le frontend
    formatted_models = []
    for model in models:
        formatted_models.append({
            "username": model['username'],
            "autoRecord": bool(model.get('auto_record', True)),
            "recordQuality": model.get('record_quality', 'best'),
            "retentionDays": model.get('retention_days', 30)
        })
    
    return {"models": formatted_models}


@app.post("/api/models")
async def add_model(model: dict):
    """Ajoute un modèle dans SQLite"""
    username = model.get('username')
    if not username:
        raise HTTPException(status_code=400, detail="Username requis")
    
    # Vérifier si le modèle existe déjà
    existing = await db.get_model(username)
    if existing:
        raise HTTPException(status_code=409, detail="Modèle déjà existant")
    
    # Ajouter dans SQLite
    await db.add_or_update_model(
        username=username,
        auto_record=model.get('autoRecord', True),
        record_quality=model.get('recordQuality', 'best'),
        retention_days=model.get('retentionDays', 30)
    )
    
    # Récupérer tous les modèles pour retourner
    all_models = await db.get_all_models()
    formatted = [{
        "username": m['username'],
        "autoRecord": bool(m.get('auto_record', True)),
        "recordQuality": m.get('record_quality', 'best'),
        "retentionDays": m.get('retention_days', 30)
    } for m in all_models]
    
    return {"success": True, "models": formatted}


@app.put("/api/models/{username}")
async def update_model(username: str, model_data: dict):
    """Met à jour les paramètres d'un modèle dans SQLite"""
    # Vérifier si le modèle existe
    existing = await db.get_model(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    
    # Mettre à jour dans SQLite
    await db.add_or_update_model(
        username=username,
        auto_record=model_data.get('autoRecord', existing.get('auto_record', True)),
        record_quality=model_data.get('recordQuality', existing.get('record_quality', 'best')),
        retention_days=model_data.get('retentionDays', existing.get('retention_days', 30))
    )
    
    # Récupérer le modèle mis à jour
    updated = await db.get_model(username)
    
    return {
        "success": True,
        "model": {
            "username": updated['username'],
            "autoRecord": bool(updated.get('auto_record', True)),
            "recordQuality": updated.get('record_quality', 'best'),
            "retentionDays": updated.get('retention_days', 30)
        }
    }


@app.delete("/api/models/{username}")
async def delete_model(username: str):
    """Supprime un modèle de SQLite"""
    # Vérifier si le modèle existe
    existing = await db.get_model(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    
    # Supprimer de SQLite
    await db.delete_model(username)
    
    # Récupérer la liste mise à jour
    all_models = await db.get_all_models()
    formatted = [{
        "username": m['username'],
        "autoRecord": bool(m.get('auto_record', True)),
        "recordQuality": m.get('record_quality', 'best'),
        "retentionDays": m.get('retention_days', 30)
    } for m in all_models]
    
    return {"success": True, "models": formatted}


@app.delete("/api/recordings/{username}/{filename}")
async def delete_recording(username: str, filename: str):
    """Supprime un enregistrement (TS + MP4 + miniature + DB)"""
    from fastapi.responses import Response
    from datetime import datetime
    
    # Sécurité
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nom invalide")
    
    if not (filename.endswith(".ts") or filename.endswith(".mp4")):
        raise HTTPException(status_code=400, detail="Format invalide")
    
    # Vérifier que ce n'est pas l'enregistrement en cours
    file_stem = Path(filename).stem
    
    # Vérifier si CE FICHIER SPÉCIFIQUE est en cours d'enregistrement
    active_sessions = manager.list_status()
    for session in active_sessions:
        if session.get('person') == username and session.get('running'):
            # Récupérer le chemin du fichier en cours d'enregistrement
            record_path = session.get('record_path', '')
            if record_path and file_stem in record_path:
                raise HTTPException(
                    status_code=403, 
                    detail="Impossible de supprimer l'enregistrement en cours."
                )
    
    # Chemins des fichiers
    records_dir = OUTPUT_DIR / "records" / username
    ts_path = records_dir / f"{file_stem}.ts"
    mp4_path = records_dir / f"{file_stem}.mp4"
    thumb_path = OUTPUT_DIR / "thumbnails" / username / f"{file_stem}.jpg"
    
    # Vérifier qu'au moins un fichier existe
    if not ts_path.exists() and not mp4_path.exists():
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    
    # Supprimer tous les fichiers associés
    try:
        files_deleted = []
        
        # Supprimer TS
        if ts_path.exists():
            ts_path.unlink()
            files_deleted.append("TS")
            logger.info("Fichier TS supprimé", username=username, file=ts_path.name)
        
        # Supprimer MP4
        if mp4_path.exists():
            mp4_path.unlink()
            files_deleted.append("MP4")
            logger.info("Fichier MP4 supprimé", username=username, file=mp4_path.name)
        
        # Supprimer miniature
        if thumb_path.exists():
            thumb_path.unlink()
            files_deleted.append("Miniature")
        
        # Supprimer de la base de données
        await db.delete_recording(username, f"{file_stem}.ts")
        logger.info("Enregistrement supprimé de la DB", username=username, filename=filename)
        
        return {
            "success": True, 
            "message": f"Supprimé: {', '.join(files_deleted)}",
            "deleted_files": files_deleted
        }
    except Exception as e:
        logger.error("Erreur suppression enregistrement", 
                    username=username, 
                    filename=filename,
                    error=str(e),
                    exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Settings / Blacklisted Tags Endpoints
# ============================================

@app.get("/api/settings/blacklisted-tags")
async def get_blacklisted_tags():
    """Get the list of blacklisted tags"""
    tags = await db.get_blacklisted_tags()
    return {"tags": tags}


@app.post("/api/settings/blacklisted-tags")
async def set_blacklisted_tags(body: dict):
    """Set the list of blacklisted tags"""
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list")
    # Normalize: lowercase, strip, deduplicate
    tags = list(set(t.strip().lower() for t in tags if t.strip()))
    await db.set_blacklisted_tags(tags)
    return {"tags": tags}


# ============================================
# Follow/Unfollow on Chaturbate
# ============================================

@app.post("/api/chaturbate/follow/{username}")
async def follow_model_on_chaturbate(username: str):
    """Follow a model on Chaturbate"""
    if not chaturbate_api:
        raise HTTPException(status_code=503, detail="Chaturbate API not initialized")
    success = await chaturbate_api.follow_model(username)
    if success:
        return {"success": True, "message": f"Now following {username}"}
    raise HTTPException(status_code=400, detail=f"Failed to follow {username}")


@app.post("/api/chaturbate/unfollow/{username}")
async def unfollow_model_on_chaturbate(username: str):
    """Unfollow a model on Chaturbate"""
    if not chaturbate_api:
        raise HTTPException(status_code=503, detail="Chaturbate API not initialized")
    success = await chaturbate_api.unfollow_model(username)
    if success:
        return {"success": True, "message": f"Unfollowed {username}"}
    raise HTTPException(status_code=400, detail=f"Failed to unfollow {username}")


@app.get("/api/chaturbate/is-following/{username}")
async def is_following_model(username: str):
    """Check if following a model on Chaturbate"""
    if not chaturbate_api:
        return {"isFollowing": False}
    is_following = await chaturbate_api.is_following(username)
    return {"isFollowing": is_following}


# ============================================
# Auto-record Toggle
# ============================================

@app.patch("/api/models/{username}/auto-record")
async def toggle_auto_record(username: str, body: dict):
    """Toggle auto-record for a model"""
    existing = await db.get_model(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    auto_record = body.get("autoRecord")
    if auto_record is None:
        raise HTTPException(status_code=400, detail="autoRecord field required")

    await db.add_or_update_model(
        username=username,
        auto_record=bool(auto_record),
        record_quality=existing.get("record_quality", "best"),
        retention_days=existing.get("retention_days", 30)
    )
    return {"success": True, "autoRecord": bool(auto_record)}


# ============================================
# Playback Position Endpoints
# ============================================

@app.get("/api/playback-position/{recording_id}")
async def get_playback_position(recording_id: str):
    """Get saved playback position for a recording"""
    pos = await db.get_playback_position(recording_id)
    if pos:
        return {
            "recordingId": recording_id,
            "position": pos["position_seconds"],
            "duration": pos["duration_seconds"],
        }
    return {"recordingId": recording_id, "position": 0, "duration": 0}


@app.post("/api/playback-position/{recording_id}")
async def save_playback_position(recording_id: str, body: dict):
    """Save playback position for a recording"""
    position = body.get("position", 0)
    duration = body.get("duration", 0)
    username = body.get("username", "")
    await db.save_playback_position(recording_id, username, position, duration)
    return {"success": True}


# ============================================
# Recordings grouped by model
# ============================================

@app.get("/api/recordings-by-model")
async def get_recordings_by_model():
    """Get recordings grouped by model with stats"""
    groups = await db.get_recordings_grouped_by_model()

    # Add thumbnail info for each model
    result = []
    for group in groups:
        username = group["username"]
        thumb_url = f"/api/thumbnail/{username}"
        result.append({
            "username": username,
            "recordingCount": group["recording_count"],
            "totalSize": group["total_size"],
            "lastRecordingAt": group["last_recording_at"],
            "totalDuration": group["total_duration"],
            "thumbnail": thumb_url,
        })

    return {"models": result}


@app.post("/api/recordings/recalculate-durations")
async def recalculate_all_durations():
    """Recalcule les durées de tous les enregistrements"""
    from app.tasks.monitor import get_video_duration, generate_recording_thumbnail
    
    logger.info("API: Demande de recalcul des durées", endpoint="/api/recordings/recalculate-durations")
    
    try:
        # Créer une tâche en arrière-plan
        asyncio.create_task(_recalculate_durations_task())
        
        return {
            "success": True,
            "message": "Recalcul des durées démarré en arrière-plan"
        }
    except Exception as e:
        logger.error("Erreur lancement recalcul durées", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _recalculate_durations_task():
    """Tâche de recalcul des durées en arrière-plan"""
    from app.tasks.monitor import get_video_duration, generate_recording_thumbnail
    
    logger.background_task("recalculate-durations", "Démarrage du recalcul")
    
    try:
        # Récupérer tous les modèles
        models = await db.get_all_models()
        
        total_processed = 0
        total_updated = 0
        
        for model in models:
            username = model['username']
            records_dir = OUTPUT_DIR / "records" / username
            
            if not records_dir.exists():
                continue
            
            logger.info("Recalcul durées", username=username, task="recalculate-durations")
            
            ts_files = list(records_dir.glob("*.ts"))
            
            for ts_file in ts_files:
                try:
                    total_processed += 1
                    
                    # Récupérer l'enregistrement depuis la DB
                    recordings = await db.get_recordings(username)
                    existing_rec = next((r for r in recordings if r['filename'] == ts_file.name), None)
                    
                    current_duration = 0
                    if existing_rec:
                        current_duration = existing_rec.get('duration_seconds', 0)
                    
                    # Calculer la durée si elle est à 0
                    if current_duration == 0:
                        duration = await get_video_duration(ts_file, FFMPEG_PATH)
                        
                        if duration > 0:
                            # Générer aussi la miniature
                            thumbnail_path = await generate_recording_thumbnail(
                                ts_file, OUTPUT_DIR, username, FFMPEG_PATH
                            )
                            
                            # Mettre à jour dans la DB
                            await db.add_or_update_recording(
                                username=username,
                                filename=ts_file.name,
                                file_path=str(ts_file),
                                file_size=ts_file.stat().st_size,
                                duration_seconds=duration,
                                thumbnail_path=thumbnail_path
                            )
                            
                            total_updated += 1
                            
                            logger.success("Durée calculée", 
                                         username=username,
                                         filename=ts_file.name,
                                         duration=duration)
                        
                except Exception as e:
                    logger.error("Erreur recalcul fichier", 
                               username=username,
                               filename=ts_file.name,
                               error=str(e))
                    continue
        
        logger.success("Recalcul terminé",
                      task="recalculate-durations",
                      updated=total_updated,
                      total=total_processed)
        
    except Exception as e:
        logger.error("Erreur tâche recalcul durées", 
                    task="recalculate-durations", 
                    error=str(e), 
                    exc_info=True)


# ============================================
# Background Task - Auto-enregistrement
# ============================================

async def auto_record_task():
    """Vérifie automatiquement les modèles et lance les enregistrements (utilise SQLite)"""
    while True:
        try:
            await asyncio.sleep(120)  # Vérifier toutes les 2 minutes
            
            # Charger les modèles depuis SQLite avec auto_record activé
            models = await db.get_models_for_auto_record()
            if not models:
                continue
            
            # Récupérer les sessions actives
            active_sessions = manager.list_status()
            
            for model in models:
                username = model.get('username')
                
                if not username:
                    continue
                
                # Vérifier si déjà en enregistrement
                is_recording = any(
                    s.get('person') == username and s.get('running')
                    for s in active_sessions
                )
                
                if is_recording:
                    continue  # Déjà en cours
                
                # Vérifier le statut depuis le cache SQLite (mis à jour par monitor)
                cached_status = await db.get_model(username)
                
                if cached_status and cached_status.get('is_online'):
                    # Modèle en ligne selon le cache, résoudre le flux HLS
                    try:
                        hls_source = None

                        # Try async resolver first (uses authenticated API)
                        try:
                            from .resolvers.chaturbate import resolve_m3u8_async
                            hls_source = await resolve_m3u8_async(username)
                        except Exception:
                            pass

                        # Fallback to direct API
                        if not hls_source:
                            api_url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "Referer": "https://chaturbate.com/",
                            }
                            resp = requests.get(api_url, headers=headers, timeout=10)
                            if resp.status_code == 200:
                                data = resp.json()
                                hls_source = data.get('hls_source')

                        if hls_source:
                            # Lancer l'enregistrement
                            logger.background_task("auto-record", "Modèle en ligne détecté", username=username)

                            try:
                                sess = manager.start_session(
                                    input_url=hls_source,
                                    display_name=username,
                                    person=username
                                )

                                if sess:
                                    logger.success("Auto-enregistrement démarré",
                                                 task="auto-record",
                                                 username=username,
                                                 session_id=sess.id)
                            except RuntimeError as e:
                                logger.warning("Impossible démarrer enregistrement",
                                             task="auto-record",
                                             username=username,
                                             error=str(e))
                                continue

                    except Exception as e:
                        logger.error("Erreur vérification modèle",
                                   task="auto-record",
                                   username=username,
                                   error=str(e))
                        continue
                
        except Exception as e:
            logger.error("Erreur auto-record task", task="auto-record", exc_info=True, error=str(e))
            await asyncio.sleep(60)


async def cleanup_old_recordings_task():
    """Nettoie automatiquement les anciennes rediffusions selon la rétention configurée"""
    from datetime import datetime, timedelta
    
    while True:
        try:
            await asyncio.sleep(3600)  # Vérifier toutes les heures
            
            logger.background_task("cleanup", "Début nettoyage anciennes rediffusions")
            
            # Charger les modèles depuis SQLite avec leurs paramètres de rétention
            models = await db.get_all_models()
            
            for model in models:
                username = model.get('username')
                retention_days = model.get('retention_days', 30)  # Défaut 30 jours
                
                if not username:
                    continue
                
                records_dir = OUTPUT_DIR / "records" / username
                thumbnails_dir = OUTPUT_DIR / "thumbnails" / username
                
                if not records_dir.exists():
                    continue
                
                # Date limite (aujourd'hui - rétention)
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                
                # Parcourir les fichiers .ts
                for ts_file in records_dir.glob("*.ts"):
                    try:
                        # Le nom du fichier est au format YYYY-MM-DD.ts
                        date_str = ts_file.stem  # Enlève .ts
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        
                        # Si le fichier est plus vieux que la limite
                        if file_date < cutoff_date:
                            # Supprimer le fichier TS
                            file_size = ts_file.stat().st_size
                            ts_file.unlink()
                            logger.info("Fichier supprimé (rétention)",
                                      task="cleanup",
                                      username=username,
                                      filename=ts_file.name,
                                      retention_days=retention_days,
                                      size_mb=f"{file_size / 1024 / 1024:.1f}")
                            
                            # Supprimer la miniature associée
                            thumb_file = thumbnails_dir / f"{ts_file.stem}.jpg"
                            if thumb_file.exists():
                                thumb_file.unlink()
                            
                            # Supprimer l'entrée du cache
                            cache_file = records_dir / ".metadata_cache.json"
                            if cache_file.exists():
                                try:
                                    with open(cache_file, 'r') as f:
                                        cache = json.load(f)
                                    if ts_file.name in cache:
                                        del cache[ts_file.name]
                                        with open(cache_file, 'w') as f:
                                            json.dump(cache, f)
                                except:
                                    pass
                                    
                    except Exception as e:
                        logger.error("Erreur nettoyage fichier",
                                   task="cleanup",
                                   filename=ts_file.name,
                                   error=str(e))
                        continue
                        
        except Exception as e:
            logger.error("Erreur cleanup task", task="cleanup", exc_info=True, error=str(e))
            await asyncio.sleep(3600)


async def sync_following_task(chaturbate_api, auth_service):
    """Background task: sync followed models every 5 minutes"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes

            status = auth_service.get_status()
            if not status.get("isLoggedIn"):
                continue

            models = await chaturbate_api.get_followed_models()
            if models:
                for model in models:
                    await db.upsert_followed_model(
                        username=model["username"],
                        display_name=model.get("display_name"),
                        is_online=model.get("is_online", False),
                        viewers=model.get("viewers", 0),
                        thumbnail_url=model.get("thumbnail_url"),
                    )
                logger.debug("Following synced", count=len(models), task="following-sync")
        except Exception as e:
            logger.error("Following sync error", task="following-sync", error=str(e))
            await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    """Démarre les background tasks au démarrage de l'application"""
    # Initialiser la base de données
    await db.initialize()

    # Migrer les données depuis le JSON si nécessaire
    await db.migrate_from_json(MODELS_FILE)

    # Initialize FlareSolverr client
    flaresolverr = FlareSolverrClient(FLARESOLVERR_URL)
    fs_available = await flaresolverr.is_available()
    if fs_available:
        logger.info("FlareSolverr connecté", url=FLARESOLVERR_URL)
    else:
        logger.info("FlareSolverr non disponible (optionnel)", url=FLARESOLVERR_URL)

    # Initialize Chaturbate auth service
    cb_auth = ChaturbateAuthService(db, flaresolverr)
    await cb_auth.initialize()

    # Initialize Chaturbate API client
    global chaturbate_api
    cb_api = ChaturbateAPI(cb_auth, flaresolverr)
    chaturbate_api = cb_api

    # Wire up API routers
    auth_router.init(cb_auth, flaresolverr)
    discover_router.init(cb_api, db)
    following_router.init(cb_api, cb_auth, db)

    # Set authenticated resolver for chaturbate
    from .resolvers.chaturbate import set_chaturbate_api
    set_chaturbate_api(cb_api)

    # Auto-login if env vars are set
    if CHATURBATE_USERNAME and CHATURBATE_PASSWORD:
        logger.info("Auto-login Chaturbate", username=CHATURBATE_USERNAME)
        result = await cb_auth.login(CHATURBATE_USERNAME, CHATURBATE_PASSWORD)
        if result.get("success"):
            logger.success("Chaturbate auto-login successful")
        else:
            logger.warning("Chaturbate auto-login failed", error=result.get("error"))

    # Démarrer les tâches de fond
    asyncio.create_task(monitor_models_task(db, manager, FFMPEG_PATH))
    asyncio.create_task(auto_record_task())
    asyncio.create_task(cleanup_old_recordings_task())
    asyncio.create_task(auto_convert_recordings_task(db, OUTPUT_DIR, manager, FFMPEG_PATH))
    asyncio.create_task(sync_following_task(cb_api, cb_auth))
    logger.info("Background tasks démarrés",
                tasks=["monitor", "auto-record", "cleanup", "convert", "following-sync"])

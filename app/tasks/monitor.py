"""
Tâche background: Monitoring continu des modèles
Vérifie l'état en ligne, génère les miniatures et met à jour SQLite
"""
import asyncio
import aiohttp
import subprocess
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from datetime import datetime

if TYPE_CHECKING:
    from ..ffmpeg_runner import FFmpegManager
    from ..core.database import Database
    from ..services.chaturbate_api import ChaturbateAPI

from ..logger import logger
from ..core.config import OUTPUT_DIR

# Intervalle de vérification (en secondes)
try:
    MONITOR_INTERVAL = max(5, int(os.getenv("MONITOR_INTERVAL", "10")))
except ValueError:
    MONITOR_INTERVAL = 10

try:
    THUMBNAIL_UPDATE_INTERVAL = max(15, int(os.getenv("THUMBNAIL_UPDATE_INTERVAL", "60")))
except ValueError:
    THUMBNAIL_UPDATE_INTERVAL = 60

try:
    MONITOR_RECORDING_STALL_SECONDS = max(20, int(os.getenv("MONITOR_RECORDING_STALL_SECONDS", "45")))
except ValueError:
    MONITOR_RECORDING_STALL_SECONDS = 45

try:
    MONITOR_OFFLINE_HLS_PROBE_SECONDS = max(10, int(os.getenv("MONITOR_OFFLINE_HLS_PROBE_SECONDS", "20")))
except ValueError:
    MONITOR_OFFLINE_HLS_PROBE_SECONDS = 20

async def check_model_status(
    session: aiohttp.ClientSession,
    username: str,
    csrftoken: Optional[str] = None,
) -> dict:
    """Vérifie le statut d'un modèle via l'API Chaturbate"""
    try:
        url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://chaturbate.com/",
            "Origin": "https://chaturbate.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        
        # Ajouter les cookies si disponibles
        cookies = []
        if csrftoken:
            cookies.append(f"csrftoken={csrftoken}")
        
        # Récupérer les autres cookies depuis les variables d'environnement
        affkey = os.getenv("CHATURBATE_AFFKEY")
        sessionid = os.getenv("CHATURBATE_SESSIONID")
        
        if affkey:
            cookies.append(f"affkey={affkey}")
        if sessionid:
            cookies.append(f"sessionid={sessionid}")
        
        if cookies:
            headers["Cookie"] = "; ".join(cookies)
        
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15), ssl=False) as response:
            if response.status == 200:
                data = await response.json()
                
                # Log les données de l'API pour débogage
                logger.debug("Réponse API Chaturbate", 
                           username=username,
                           room_status=data.get("room_status"),
                           has_hls=bool(data.get("hls_source")),
                           num_users=data.get("num_users", 0))
                
                # Détection améliorée du statut en ligne
                room_status = data.get("room_status", "")
                hls_source = data.get("hls_source")
                
                # Un modèle est en ligne si :
                # 1. Il a un flux HLS disponible OU
                # 2. Le room_status est "public" OU
                # 3. Le room_status est "away" (temporairement absent mais toujours en ligne)
                is_online = (
                    bool(hls_source) or 
                    room_status in ["public", "away"]
                )
                
                viewers = data.get("num_users", 0)
                
                return {
                    "is_online": is_online,
                    "is_recordable": bool(hls_source),
                    "viewers": viewers,
                    "hls_source": hls_source,
                    "room_status": room_status,
                    "request_ok": True,
                }
    except Exception as e:
        logger.debug("Erreur vérification statut modèle", username=username, error=str(e))
    
    return {
        "is_online": False,
        "is_recordable": False,
        "viewers": 0,
        "hls_source": None,
        "room_status": "",
        "request_ok": False,
    }

async def generate_thumbnail_from_stream(
    username: str,
    session_id: str,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg"
) -> str | None:
    """Génère une miniature depuis le stream HLS en cours"""
    try:
        session_dir = output_dir / "sessions" / session_id
        m3u8_file = session_dir / "stream.m3u8"
        
        if not m3u8_file.exists():
            return None
        
        # Dossier pour les miniatures live
        live_thumbs_dir = output_dir / "thumbnails" / "live"
        live_thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = live_thumbs_dir / f"{username}.jpg"
        
        # Générer la miniature
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-i", str(m3u8_file),
            "-vframes", "1",
            "-vf", "scale=280:-1",
            "-y",
            str(thumb_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await asyncio.wait_for(process.wait(), timeout=10)
        
        if thumb_path.exists():
            return str(thumb_path)
    
    except Exception as e:
        logger.debug("Erreur génération miniature stream", username=username, error=str(e))
    
    return None

async def generate_thumbnail_from_recording(
    username: str,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg"
) -> str | None:
    """Génère une miniature depuis la dernière rediffusion"""
    try:
        records_dir = output_dir / "records" / username
        
        if not records_dir.exists():
            return None
        
        # Trouver la dernière rediffusion
        ts_files = sorted(records_dir.glob("*.ts"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not ts_files:
            return None
        
        latest_recording = ts_files[0]
        
        # Dossier pour les miniatures offline
        offline_thumbs_dir = output_dir / "thumbnails" / "offline"
        offline_thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = offline_thumbs_dir / f"{username}.jpg"
        
        # Ne régénérer que si la miniature n'existe pas ou est plus ancienne que l'enregistrement
        if thumb_path.exists() and thumb_path.stat().st_mtime > latest_recording.stat().st_mtime:
            return str(thumb_path)
        
        # Extraire une frame au milieu de la vidéo
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-ss", "00:00:30",
            "-i", str(latest_recording),
            "-vframes", "1",
            "-vf", "scale=280:-1",
            "-y",
            str(thumb_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await asyncio.wait_for(process.wait(), timeout=15)
        
        if thumb_path.exists():
            return str(thumb_path)
    
    except Exception as e:
        logger.debug("Erreur génération miniature offline", username=username, error=str(e))
    
    return None

async def download_thumbnail_from_chaturbate(
    session: aiohttp.ClientSession,
    username: str,
    output_dir: Path
) -> str | None:
    """Télécharge la miniature depuis Chaturbate"""
    try:
        img_urls = [
            f"https://roomimg.stream.highwebmedia.com/ri/{username}.jpg",
            f"https://cbjpeg.stream.highwebmedia.com/stream?room={username}&f=.jpg",
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://chaturbate.com/",
        }
        
        for img_url in img_urls:
            try:
                async with session.get(img_url, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        if len(content) > 1000:
                            # Sauvegarder la miniature
                            cb_thumbs_dir = output_dir / "thumbnails" / "chaturbate"
                            cb_thumbs_dir.mkdir(parents=True, exist_ok=True)
                            thumb_path = cb_thumbs_dir / f"{username}.jpg"
                            
                            with open(thumb_path, 'wb') as f:
                                f.write(content)
                            
                            return str(thumb_path)
            except:
                continue
    
    except Exception as e:
        logger.debug("Erreur téléchargement miniature Chaturbate", username=username, error=str(e))
    
    return None

async def get_video_duration(file_path: Path, ffmpeg_path: str = "ffmpeg") -> int:
    """Récupère la durée d'une vidéo avec ffprobe"""
    try:
        # Utiliser ffprobe pour récupérer la durée
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        
        process = await asyncio.create_subprocess_exec(
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        
        if process.returncode == 0 and stdout:
            duration_str = stdout.decode().strip()
            if duration_str:
                return int(float(duration_str))
    
    except Exception as e:
        logger.debug("Erreur récupération durée vidéo", file_path=str(file_path), error=str(e))
    
    return 0


async def generate_recording_thumbnail(
    ts_file: Path,
    output_dir: Path,
    username: str,
    ffmpeg_path: str = "ffmpeg"
) -> str | None:
    """Génère une miniature pour un enregistrement"""
    try:
        # Dossier pour les miniatures d'enregistrements
        thumbs_dir = output_dir / "thumbnails" / username
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumbs_dir / f"{ts_file.stem}.jpg"
        
        # Ne pas régénérer si existe déjà
        if thumb_path.exists():
            return str(thumb_path)
        
        # Extraire une frame à 30 secondes du début
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-ss", "00:00:30",
            "-i", str(ts_file),
            "-vframes", "1",
            "-vf", "scale=320:-1",
            "-y",
            str(thumb_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await asyncio.wait_for(process.wait(), timeout=15)
        
        if thumb_path.exists():
            return str(thumb_path)
    
    except Exception as e:
        logger.debug("Erreur génération miniature enregistrement", 
                    username=username, 
                    filename=ts_file.name, 
                    error=str(e))
    
    return None


async def update_recordings_cache(db: 'Database', username: str, output_dir: Path, ffmpeg_path: str = "ffmpeg"):
    """Met à jour le cache des enregistrements dans SQLite"""
    try:
        import time
        records_dir = output_dir / "records" / username
        
        if not records_dir.exists():
            return
        
        for ts_file in records_dir.glob("*.ts"):
            stat = ts_file.stat()
            
            # Récupérer la durée actuelle depuis la DB
            existing_recordings = await db.get_recordings(username)
            existing_rec = next((r for r in existing_recordings if r['filename'] == ts_file.name), None)
            
            # Calculer la durée uniquement si elle n'est pas déjà en cache ou est à 0
            duration_seconds = 0
            if existing_rec:
                duration_seconds = existing_rec.get('duration_seconds', 0)
            
            if duration_seconds == 0:
                # Vérifier que le fichier est stable (pas modifié depuis 120s)
                # pour éviter de calculer la durée sur un fichier en cours d'écriture
                last_modified = ts_file.stat().st_mtime
                seconds_since_modification = time.time() - last_modified
                
                if seconds_since_modification >= 120:
                    # Calculer la durée avec ffprobe
                    duration_seconds = await get_video_duration(ts_file, ffmpeg_path)
                    logger.debug("Durée calculée", username=username, filename=ts_file.name, duration=duration_seconds)
                else:
                    logger.debug("Fichier pas encore stable, skip calcul durée", 
                               username=username, 
                               filename=ts_file.name,
                               seconds_since_modification=int(seconds_since_modification))
            
            # Générer la miniature si elle n'existe pas
            thumbnail_path = None
            if existing_rec:
                thumbnail_path = existing_rec.get('thumbnail_path')
            
            if not thumbnail_path or not Path(thumbnail_path).exists():
                thumbnail_path = await generate_recording_thumbnail(ts_file, output_dir, username, ffmpeg_path)
                if thumbnail_path:
                    logger.debug("Miniature générée", username=username, filename=ts_file.name, thumb=thumbnail_path)
            
            # Générer recording_id si c'est un nouvel enregistrement
            recording_id = None
            if existing_rec:
                recording_id = existing_rec.get('recording_id')
            
            if not recording_id:
                # Extraire le timestamp du nom de fichier (format: YYYYMMDD_HHMMSS_xxx.ts)
                # Sinon générer un nouveau recording_id
                recording_id = f"{username}_{ts_file.stem}"
            
            await db.add_or_update_recording(
                username=username,
                filename=ts_file.name,
                file_path=str(ts_file),
                file_size=stat.st_size,
                recording_id=recording_id,
                duration_seconds=duration_seconds,
                thumbnail_path=thumbnail_path
            )
    
    except Exception as e:
        logger.debug("Erreur mise à jour cache enregistrements", username=username, error=str(e))

async def monitor_models_task(
    db: 'Database',
    manager: 'FFmpegManager',
    ffmpeg_path: str = "ffmpeg",
    chaturbate_api: Optional['ChaturbateAPI'] = None,
    offline_failure_threshold: int = 3,
):
    """
    Tâche de monitoring en arrière-plan
    Vérifie continuellement l'état des modèles et génère les miniatures
    """
    logger.background_task("monitor", "Démarrage du monitoring continu")
    
    # Récupérer le csrftoken depuis les variables d'environnement
    csrftoken = os.getenv("CHATURBATE_CSRFTOKEN")
    if csrftoken:
        logger.info("CSRF token détecté", has_token=True)
    
    # Initialiser la base de données
    await db.initialize()

    # Allow runtime tuning for anti-flapping behavior.
    try:
        offline_failure_threshold = max(
            1,
            int(os.getenv("MONITOR_OFFLINE_FAILURE_THRESHOLD", str(offline_failure_threshold)))
        )
    except ValueError:
        offline_failure_threshold = max(1, offline_failure_threshold)
    
    # Créer une session HTTP persistante
    async with aiohttp.ClientSession() as session:
        # Track transient request failures to avoid online/offline flicker.
        consecutive_status_failures = {}
        # Track restart attempts to avoid start storms when upstream is unstable.
        restart_attempts = {}
        # Track recording file growth to detect stalled ffmpeg sessions.
        recording_progress = {}
        # Throttle expensive HLS probes when API status reports offline.
        offline_hls_probe_at = {}

        try:
            restart_cooldown_seconds = max(
                5,
                int(os.getenv("MONITOR_AUTORECORD_RESTART_COOLDOWN", "10"))
            )
        except ValueError:
            restart_cooldown_seconds = 10

        while True:
            try:
                # Récupérer tous les modèles depuis la DB
                models = await db.get_all_models()
                
                if not models:
                    await asyncio.sleep(MONITOR_INTERVAL)
                    continue
                
                logger.debug("Checking models", count=len(models))
                
                # Récupérer les sessions actives
                active_sessions = manager.list_status()
                running_session_ids = {
                    s.get("id") for s in active_sessions if s.get("running") and s.get("id")
                }

                # Drop stale progress entries for sessions that are no longer running.
                for stale_id in list(recording_progress.keys()):
                    if stale_id not in running_session_ids:
                        recording_progress.pop(stale_id, None)
                
                # Vérifier chaque modèle
                for model in models:
                    username = model['username']
                    
                    try:
                        # Vérifier le statut en ligne
                        if chaturbate_api:
                            status = await chaturbate_api.get_model_status(username)
                        else:
                            status = await check_model_status(session, username, csrftoken)

                        status_request_ok = bool(status.get('request_ok', True))
                        effective_online = bool(status.get('is_online', False))
                        effective_recordable = bool(status.get('is_recordable', bool(status.get('hls_source'))))
                        previous_online = bool(model.get('is_online', False))

                        if status_request_ok:
                            consecutive_status_failures[username] = 0
                        else:
                            failures = consecutive_status_failures.get(username, 0) + 1
                            consecutive_status_failures[username] = failures

                            # Keep previous online state for transient failures.
                            if previous_online and failures < offline_failure_threshold:
                                effective_online = True
                                status['viewers'] = int(model.get('viewers', 0) or 0)
                                logger.debug(
                                    "Status kept during transient failure",
                                    username=username,
                                    failures=failures,
                                    threshold=offline_failure_threshold,
                                )
                        
                        # Vérifier si en cours d'enregistrement
                        active_session = next(
                            (s for s in active_sessions if s.get('person') == username and s.get('running')),
                            None
                        )
                        is_recording = active_session is not None
                        auto_record_enabled = bool(model.get('auto_record', True))

                        # chatvideocontext can occasionally return false negatives (online stream but is_online=False).
                        # Probe HLS directly in a throttled manner so auto-record can still start promptly.
                        if (
                            auto_record_enabled
                            and not is_recording
                            and not effective_online
                            and chaturbate_api
                        ):
                            now = time.time()
                            last_probe = offline_hls_probe_at.get(username, 0)
                            if now - last_probe >= MONITOR_OFFLINE_HLS_PROBE_SECONDS:
                                offline_hls_probe_at[username] = now
                                probe_hls = None

                                try:
                                    from ..resolvers.chaturbate import resolve_m3u8_async
                                    probe_hls = await resolve_m3u8_async(username)
                                except Exception as e:
                                    logger.debug(
                                        "Offline probe async resolver failed",
                                        task="monitor",
                                        username=username,
                                        error=str(e),
                                    )

                                if not probe_hls:
                                    try:
                                        probe_hls = await chaturbate_api.get_edge_hls_url(username)
                                    except Exception as e:
                                        logger.debug(
                                            "Offline probe edge HLS failed",
                                            task="monitor",
                                            username=username,
                                            error=str(e),
                                        )

                                if probe_hls:
                                    status["hls_source"] = probe_hls
                                    status["request_ok"] = True
                                    effective_online = True
                                    effective_recordable = True
                                    logger.info(
                                        "Offline status corrected by HLS probe",
                                        task="monitor",
                                        username=username,
                                    )
                                else:
                                    logger.debug(
                                        "Offline HLS probe found no stream",
                                        task="monitor",
                                        username=username,
                                    )

                        # If a recording session stops producing bytes for too long,
                        # restart it to reduce silent data loss periods.
                        if is_recording and active_session:
                            session_id = active_session.get("id")
                            record_path = active_session.get("record_path")
                            log_path = active_session.get("log_path")
                            if session_id and record_path:
                                try:
                                    current_size = Path(record_path).stat().st_size
                                except Exception:
                                    current_size = -1

                                try:
                                    current_log_size = Path(log_path).stat().st_size if log_path else -1
                                except Exception:
                                    current_log_size = -1

                                now = time.time()
                                progress = recording_progress.get(session_id)
                                # Reset baseline when the recording file path changes (segment rotation)
                                # or when file size is lower than the previous baseline.
                                if (
                                    not progress
                                    or progress.get("path") != record_path
                                    or current_size < progress.get("size", -1)
                                ):
                                    recording_progress[session_id] = {
                                        "path": record_path,
                                        "size": current_size,
                                        "updated_at": now,
                                        "log_size": current_log_size,
                                        "log_updated_at": now,
                                    }
                                elif current_size > progress.get("size", -1):
                                    recording_progress[session_id] = {
                                        "path": record_path,
                                        "size": current_size,
                                        "updated_at": now,
                                        "log_size": current_log_size,
                                        "log_updated_at": now,
                                    }
                                elif current_size >= 0:
                                    previous_log_size = progress.get("log_size", -1)
                                    if current_log_size > previous_log_size:
                                        progress["log_size"] = current_log_size
                                        progress["log_updated_at"] = now

                                    stalled_for = now - float(progress.get("updated_at", now))
                                    log_idle_for = now - float(progress.get("log_updated_at", now))

                                    # If ffmpeg keeps producing log output (e.g. transient 503 retry loop),
                                    # allow a longer grace period before forcing a restart.
                                    hard_restart_after = MONITOR_RECORDING_STALL_SECONDS * 3
                                    should_restart = (
                                        (stalled_for >= MONITOR_RECORDING_STALL_SECONDS and log_idle_for >= MONITOR_RECORDING_STALL_SECONDS)
                                        or stalled_for >= hard_restart_after
                                    )

                                    if should_restart:
                                        logger.warning(
                                            "Recording stalled, restarting session",
                                            task="monitor",
                                            username=username,
                                            session_id=session_id,
                                            stalled_for_seconds=f"{stalled_for:.0f}",
                                            log_idle_for_seconds=f"{log_idle_for:.0f}",
                                            file_size=current_size,
                                        )
                                        manager.stop_session(session_id)
                                        recording_progress.pop(session_id, None)
                                        is_recording = False
                                        active_session = None

                        # Fast recovery path: if auto-record is enabled and model appears online,
                        # try to restart a dropped recording without waiting for the slower auto-record task.
                        if (
                            auto_record_enabled
                            and not is_recording
                            and effective_online
                            and chaturbate_api
                        ):
                            now = time.time()
                            last_try = restart_attempts.get(username, 0)

                            if now - last_try >= restart_cooldown_seconds:
                                restart_attempts[username] = now
                                recovered_hls = status.get("hls_source")

                                if not recovered_hls:
                                    try:
                                        from ..resolvers.chaturbate import resolve_m3u8_async
                                        recovered_hls = await resolve_m3u8_async(username)
                                    except Exception as e:
                                        logger.debug(
                                            "Recovery async resolver failed",
                                            username=username,
                                            error=str(e),
                                        )

                                if not recovered_hls:
                                    try:
                                        recovered_hls = await chaturbate_api.get_edge_hls_url(username)
                                    except Exception as e:
                                        logger.debug(
                                            "Recovery edge HLS fetch failed",
                                            username=username,
                                            error=str(e),
                                        )

                                if recovered_hls:
                                    try:
                                        sess = manager.start_session(
                                            input_url=recovered_hls,
                                            person=username,
                                            display_name=username,
                                        )
                                        if sess:
                                            is_recording = True
                                            logger.success(
                                                "Recovery auto-record started",
                                                task="monitor",
                                                username=username,
                                                session_id=sess.id,
                                            )
                                    except RuntimeError as e:
                                        logger.debug(
                                            "Recovery skipped (session already active)",
                                            username=username,
                                            error=str(e),
                                        )
                                    except Exception as e:
                                        logger.warning(
                                            "Recovery auto-record failed",
                                            task="monitor",
                                            username=username,
                                            error=str(e),
                                        )
                                else:
                                    logger.debug(
                                        "Recovery: no HLS available yet",
                                        task="monitor",
                                        username=username,
                                        room_status=status.get("room_status"),
                                        is_recordable=effective_recordable,
                                    )
                        else:
                            # Reset attempt timer when model is offline or already recording.
                            if is_recording or not effective_online:
                                restart_attempts.pop(username, None)
                        
                        # Générer/mettre à jour la miniature
                        thumbnail_path = None
                        last_thumbnail_update = model.get('thumbnail_updated_at') or 0
                        needs_thumbnail_update = (
                            datetime.now().timestamp() - last_thumbnail_update > THUMBNAIL_UPDATE_INTERVAL
                        )
                        
                        if needs_thumbnail_update:
                            if is_recording and active_session:
                                # Miniature depuis le stream en cours
                                thumbnail_path = await generate_thumbnail_from_stream(
                                    username,
                                    active_session['id'],
                                    OUTPUT_DIR,
                                    ffmpeg_path
                                )
                            
                            if not thumbnail_path and effective_online:
                                # Miniature depuis Chaturbate
                                thumbnail_path = await download_thumbnail_from_chaturbate(
                                    session,
                                    username,
                                    OUTPUT_DIR
                                )
                            
                            if not thumbnail_path:
                                # Miniature depuis la dernière rediffusion
                                thumbnail_path = await generate_thumbnail_from_recording(
                                    username,
                                    OUTPUT_DIR,
                                    ffmpeg_path
                                )
                        
                        # Mettre à jour le statut dans la DB
                        await db.update_model_status(
                            username=username,
                            is_online=effective_online,
                            is_recordable=effective_recordable,
                            viewers=status['viewers'],
                            is_recording=is_recording,
                            thumbnail_path=thumbnail_path
                        )
                        
                        # Mettre à jour le cache des enregistrements
                        await update_recordings_cache(db, username, OUTPUT_DIR, ffmpeg_path)
                        
                        logger.debug("Model status updated",
                                   username=username,
                                   is_online=effective_online,
                                   is_recordable=effective_recordable,
                                   request_ok=status_request_ok,
                                   is_recording=is_recording,
                                   viewers=status['viewers'])
                    
                    except Exception as e:
                        logger.error("Model monitoring error",
                                   username=username,
                                   error=str(e),
                                   exc_info=True)
                        continue
                
                # Attendre avant la prochaine vérification
                await asyncio.sleep(MONITOR_INTERVAL)
            
            except Exception as e:
                logger.error("Erreur dans monitor task",
                           error=str(e),
                           exc_info=True)
                await asyncio.sleep(60)

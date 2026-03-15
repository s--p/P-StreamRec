"""
Tâche de conversion automatique des enregistrements TS -> MP4
"""
import asyncio
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from ..logger import logger
from ..core.config import (
    AUTO_CONVERT,
    KEEP_TS,
    AUTO_CONVERT_WHILE_RECORDING,
    CONVERT_MODE,
    CONVERT_PRESET,
    CONVERT_CRF,
    CONVERT_AUDIO_BITRATE,
    CONVERT_COPY_AUDIO,
    CONVERT_QSV_DEVICE,
    CONVERT_MIN_TS_BYTES,
    CONVERT_STALE_TS_SECONDS,
    CONVERT_FAILED_RETRY_SECONDS,
)


def _build_mp4_path_from_ts(ts_path: Path) -> Path:
    """Generate MP4 name as <username><date>_recorded.mp4 in the same folder."""
    username = ts_path.parent.name or "recording"
    stem = ts_path.stem

    # Prefer timestamp found in TS filename: YYYYMMDD_HHMMSS
    match = re.search(r"(\d{8}_\d{6}|\d{8})", stem)
    if match:
        date_token = match.group(1)
    else:
        date_token = datetime.fromtimestamp(ts_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")

    return ts_path.parent / f"{username}{date_token}_recorded.mp4"


def _build_convert_cmd(
    ts_path: Path,
    mp4_path: Path,
    ffmpeg_path: str,
    mode: str,
) -> list[str]:
    if mode == "qsv":
        base = [ffmpeg_path, "-qsv_device", CONVERT_QSV_DEVICE, "-i", str(ts_path)]
    elif mode == "vaapi":
        base = [ffmpeg_path, "-vaapi_device", CONVERT_QSV_DEVICE, "-i", str(ts_path)]
    else:
        base = [ffmpeg_path, "-i", str(ts_path)]

    if mode == "copy":
        # Remux only: no video/audio re-encoding, minimal CPU usage.
        return base + [
            "-c", "copy",
            "-movflags", "+faststart",
            "-y",
            str(mp4_path),
        ]

    if mode == "qsv":
        cmd = base + [
            "-c:v", "h264_qsv",
            "-preset", CONVERT_PRESET,
        ]
        if CONVERT_COPY_AUDIO:
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", CONVERT_AUDIO_BITRATE]
        cmd += ["-movflags", "+faststart", "-y", str(mp4_path)]
        return cmd

    if mode == "vaapi":
        cmd = base + [
            "-vf", "format=nv12,hwupload",
            "-c:v", "h264_vaapi",
            "-qp", str(CONVERT_CRF),
        ]
        if CONVERT_COPY_AUDIO:
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", CONVERT_AUDIO_BITRATE]
        cmd += ["-movflags", "+faststart", "-y", str(mp4_path)]
        return cmd

    # Default software re-encode profile.
    cmd = base + [
        "-c:v", "libx264",
        "-crf", str(CONVERT_CRF),
        "-preset", CONVERT_PRESET,
    ]
    if CONVERT_COPY_AUDIO:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", CONVERT_AUDIO_BITRATE]
    cmd += ["-movflags", "+faststart", "-y", str(mp4_path)]
    return cmd


async def _run_ffmpeg_command(cmd: list[str]) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout, stderr


async def convert_ts_to_mp4(
    ts_path: Path, 
    mp4_path: Optional[Path] = None,
    ffmpeg_path: str = "ffmpeg"
) -> tuple[bool, Optional[Path], Optional[int]]:
    """
    Convertit un fichier TS en MP4 avec compression optimisée
    
    Returns:
        (success, mp4_path, mp4_size)
    """
    if not ts_path.exists():
        logger.error("TS file not found", ts_path=str(ts_path))
        return False, None, None
    
    # Générer le nom du fichier MP4 si non fourni
    if mp4_path is None:
        mp4_path = _build_mp4_path_from_ts(ts_path)
    
    logger.info("TS->MP4 conversion started", 
               ts_file=ts_path.name, 
               mp4_file=mp4_path.name)
    
    mode = CONVERT_MODE if CONVERT_MODE in {"reencode", "copy", "qsv", "vaapi"} else "reencode"
    cmd = _build_convert_cmd(ts_path, mp4_path, ffmpeg_path, mode)
    
    try:
        logger.debug("FFmpeg command", command=" ".join(cmd[:10]) + "...", mode=mode)

        returncode, stdout, stderr = await _run_ffmpeg_command(cmd)

        # Hardware fallback chain to keep CPU lower when possible.
        if returncode != 0 and mode == "qsv":
            logger.warning(
                    "QSV failed, falling back to VAAPI",
                ts_file=ts_path.name,
            )
            fallback_cmd = _build_convert_cmd(ts_path, mp4_path, ffmpeg_path, "vaapi")
            returncode, stdout, stderr = await _run_ffmpeg_command(fallback_cmd)

            if returncode != 0:
                logger.warning(
                    "VAAPI failed, falling back to libx264",
                    ts_file=ts_path.name,
                )
                fallback_cmd = _build_convert_cmd(ts_path, mp4_path, ffmpeg_path, "reencode")
                returncode, stdout, stderr = await _run_ffmpeg_command(fallback_cmd)

        if returncode != 0 and mode == "vaapi":
            logger.warning(
                "VAAPI failed, falling back to libx264",
                ts_file=ts_path.name,
            )
            fallback_cmd = _build_convert_cmd(ts_path, mp4_path, ffmpeg_path, "reencode")
            returncode, stdout, stderr = await _run_ffmpeg_command(fallback_cmd)

        if returncode == 0:
            mp4_size = mp4_path.stat().st_size
            ts_size = ts_path.stat().st_size
            reduction = ((ts_size - mp4_size) / ts_size) * 100
            
            logger.success("Conversion succeeded",
                         ts_file=ts_path.name,
                         mp4_file=mp4_path.name,
                         ts_size_mb=f"{ts_size / 1024 / 1024:.1f}",
                         mp4_size_mb=f"{mp4_size / 1024 / 1024:.1f}",
                         reduction_percent=f"{reduction:.1f}%",
                         mode=mode)
            
            return True, mp4_path, mp4_size
        else:
            error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
            logger.error("FFmpeg conversion failed",
                        ts_file=ts_path.name,
                        mode=mode,
                        error=error_msg[:500])
            return False, None, None
            
    except Exception as e:
        logger.error("Conversion exception",
                    ts_file=ts_path.name,
                    error=str(e),
                    exc_info=True)
        return False, None, None


async def _get_recording_settings(db) -> tuple[bool, bool]:
    """Read auto_convert and keep_ts settings from DB, falling back to env var defaults."""
    auto_convert_val = await db.get_setting("auto_convert")
    keep_ts_val = await db.get_setting("keep_ts")

    if auto_convert_val is not None:
        auto_convert = auto_convert_val.lower() in {"1", "true", "yes"}
    else:
        auto_convert = AUTO_CONVERT

    if keep_ts_val is not None:
        keep_ts = keep_ts_val.lower() in {"1", "true", "yes"}
    else:
        keep_ts = KEEP_TS

    return auto_convert, keep_ts


async def auto_convert_recordings_task(db, output_dir: Path, ffmpeg_manager, ffmpeg_path: str = "ffmpeg"):
    """
    Scan all .ts files and convert stable files that are not currently recording.
    Respects auto_convert and keep_ts settings from DB.
    """
    logger.info("Automatic conversion task started", task="auto-convert")

    # Initial scan: index existing TS files into DB at startup.
    logger.info("Initial scan of existing TS files", task="auto-convert")
    try:
        records_root = output_dir / "records"
        if records_root.exists():
            for user_dir in records_root.iterdir():
                if user_dir.is_dir():
                    username = user_dir.name
                    for ts_file in user_dir.glob("*.ts"):
                        # Skip files already present in DB.
                        recordings = await db.get_recordings(username)
                        existing = next((r for r in recordings if r['filename'] == ts_file.name), None)

                        if not existing:
                            logger.info("Indexing existing file", username=username, file=ts_file.name)
                            recording_id = f"{username}_{ts_file.stem}"
                            await db.add_or_update_recording(
                                username=username,
                                filename=ts_file.name,
                                file_path=str(ts_file),
                                file_size=ts_file.stat().st_size,
                                recording_id=recording_id,
                                duration_seconds=0,
                                is_converted=False
                            )
        logger.success("Initial scan completed", task="auto-convert")
    except Exception as e:
        logger.error("Initial scan failed", error=str(e), exc_info=True)

    # Backoff per TS file to avoid retry loops on permanently broken inputs.
    retry_after: dict[str, float] = {}
    failure_count: dict[str, int] = {}

    while True:
        try:
            await asyncio.sleep(30)
            converted_this_cycle = False
            pause_queue_this_cycle = False

            # Read runtime settings each cycle.
            auto_convert, keep_ts = await _get_recording_settings(db)

            records_root = output_dir / "records"
            if not records_root.exists():
                continue

            active_sessions = ffmpeg_manager.list_status()
            active_recordings = {}  # {username: recording_filename}
            active_count = 0
            for session in active_sessions:
                if session.get('running'):
                    active_count += 1
                    username = session.get('person')
                    record_path = session.get('record_path', '')
                    if username and record_path:
                        filename = Path(record_path).name
                        active_recordings[username] = filename

            logger.debug("Active sessions", active_count=active_count, active_users=list(active_recordings.keys()))

            if active_count > 0 and not AUTO_CONVERT_WHILE_RECORDING:
                logger.debug(
                    "Conversion deferred (active recordings)",
                    active_count=active_count,
                )
                continue

            # Build a global queue sorted by oldest TS first across all users.
            ts_queue: list[tuple[float, str, Path]] = []
            for user_dir in records_root.iterdir():
                if not user_dir.is_dir():
                    continue
                username = user_dir.name
                for ts_file in user_dir.glob("*.ts"):
                    ts_path = Path(ts_file)
                    try:
                        ts_mtime = ts_path.stat().st_mtime
                    except FileNotFoundError:
                        continue
                    ts_queue.append((ts_mtime, username, ts_path))

            ts_queue.sort(key=lambda item: item[0])

            for _, username, ts_path in ts_queue:
                if converted_this_cycle or pause_queue_this_cycle:
                    break

                ts_file = ts_path.name

                # Re-check active recordings before each file so queued conversions
                # pause quickly when a model goes live again.
                if not AUTO_CONVERT_WHILE_RECORDING:
                    current_active_count = sum(
                        1 for s in ffmpeg_manager.list_status() if s.get("running")
                    )
                    if current_active_count > 0:
                        logger.debug(
                            "Conversion queue paused (new active session)",
                            active_count=current_active_count,
                        )
                        pause_queue_this_cycle = True
                        break

                ts_key = str(ts_path)
                now = time.time()

                # Respect retry backoff for recently failed conversions.
                next_retry = retry_after.get(ts_key)
                if next_retry and now < next_retry:
                    continue

                try:
                    ts_stat = ts_path.stat()
                except FileNotFoundError:
                    retry_after.pop(ts_key, None)
                    failure_count.pop(ts_key, None)
                    continue

                # Skip currently active recording file.
                if username in active_recordings and active_recordings[username] == ts_file:
                    logger.debug(
                        "File is currently being recorded, skipping",
                        username=username,
                        file=ts_file,
                    )
                    continue

                mp4_path = _build_mp4_path_from_ts(ts_path)
                if mp4_path.exists():
                    logger.debug(
                        "MP4 already exists, skipping conversion",
                        username=username,
                        file=ts_file,
                    )

                    recordings = await db.get_recordings(username)
                    existing = next((r for r in recordings if r['filename'] == ts_file), None)

                    if existing and not existing.get('is_converted'):
                        await db.add_or_update_recording(
                            username=username,
                            filename=ts_file,
                            file_path=str(ts_path),
                            file_size=ts_stat.st_size,
                            recording_id=existing.get('recording_id'),
                            duration_seconds=existing.get('duration_seconds', 0),
                            thumbnail_path=existing.get('thumbnail_path'),
                            mp4_path=str(mp4_path),
                            mp4_size=mp4_path.stat().st_size,
                            is_converted=True
                        )
                        logger.info("DB updated for existing MP4", username=username, file=ts_file)

                    if not keep_ts and ts_path.exists():
                        try:
                            ts_path.unlink()
                            retry_after.pop(ts_key, None)
                            failure_count.pop(ts_key, None)
                            logger.success("TS file deleted (MP4 already existed)", username=username, ts_file=ts_file, mp4_file=mp4_path.name)
                        except Exception as e:
                            logger.error("TS delete failed", ts_file=ts_file, error=str(e))
                    continue

                last_modified = ts_stat.st_mtime
                age_seconds = now - last_modified
                if age_seconds < 60:
                    logger.debug("File modified recently, waiting for stability", file=ts_file, last_modified_ago=f"{age_seconds:.0f}s")
                    continue

                # Skip tiny stale TS files; they are usually aborted sessions and can starve the queue.
                if ts_stat.st_size < CONVERT_MIN_TS_BYTES and age_seconds >= CONVERT_STALE_TS_SECONDS:
                    failure_count[ts_key] = failure_count.get(ts_key, 0) + 1
                    cooldown = min(
                        1800,
                        CONVERT_FAILED_RETRY_SECONDS * failure_count[ts_key],
                    )
                    retry_after[ts_key] = now + cooldown
                    logger.warning(
                        "TS too small for conversion, retry deferred",
                        username=username,
                        filename=ts_file,
                        ts_size=ts_stat.st_size,
                        min_ts_size=CONVERT_MIN_TS_BYTES,
                        retry_in_seconds=cooldown,
                        failures=failure_count[ts_key],
                    )
                    continue

                # If auto_convert is disabled, only index TS in DB.
                if not auto_convert:
                    recordings = await db.get_recordings(username)
                    existing = next((r for r in recordings if r['filename'] == ts_file), None)
                    if not existing:
                        recording_id = f"{username}_{ts_path.stem}"
                        from .monitor import get_video_duration
                        duration = await get_video_duration(ts_path, ffmpeg_path)
                        await db.add_or_update_recording(
                            username=username,
                            filename=ts_file,
                            file_path=str(ts_path),
                            file_size=ts_stat.st_size,
                            recording_id=recording_id,
                            duration_seconds=duration if duration > 0 else 0,
                            is_converted=False
                        )
                        logger.info("TS indexed (auto-convert disabled)", username=username, filename=ts_file)
                    continue

                logger.info("Automatic conversion started", username=username, filename=ts_file, task="auto-convert")

                success, mp4_path_result, mp4_size = await convert_ts_to_mp4(
                    ts_path,
                    mp4_path,
                    ffmpeg_path
                )

                if success and mp4_path_result:
                    recordings = await db.get_recordings(username)
                    existing = next((r for r in recordings if r['filename'] == ts_file), None)

                    recording_id = existing.get('recording_id') if existing else f"{username}_{ts_path.stem}"

                    from .monitor import get_video_duration
                    final_duration = await get_video_duration(mp4_path_result, ffmpeg_path)

                    if final_duration > 0:
                        duration_to_use = final_duration
                        logger.info("Duration recalculated after conversion", username=username, filename=ts_file, duration=final_duration)
                    else:
                        duration_to_use = existing.get('duration_seconds', 0) if existing else 0

                    await db.add_or_update_recording(
                        username=username,
                        filename=ts_file,
                        file_path=str(ts_path),
                        file_size=ts_path.stat().st_size if ts_path.exists() else 0,
                        recording_id=recording_id,
                        duration_seconds=duration_to_use,
                        thumbnail_path=existing.get('thumbnail_path') if existing else None,
                        mp4_path=str(mp4_path_result),
                        mp4_size=mp4_size,
                        is_converted=True
                    )

                    if not keep_ts:
                        try:
                            if ts_path.exists():
                                ts_path.unlink()
                                retry_after.pop(ts_key, None)
                                failure_count.pop(ts_key, None)
                                logger.success("TS file deleted after conversion", username=username, ts_file=ts_file, mp4_file=mp4_path_result.name)
                        except Exception as e:
                            logger.error("TS delete failed", ts_file=ts_file, error=str(e))
                    else:
                        logger.info("TS file kept (keep_ts enabled)", username=username, ts_file=ts_file)

                    logger.success("Recording converted and indexed", username=username, filename=ts_file, mp4_file=mp4_path_result.name)
                    retry_after.pop(ts_key, None)
                    failure_count.pop(ts_key, None)

                    # Process one successful conversion at a time.
                    converted_this_cycle = True

                    # Small pause between conversions to avoid spikes.
                    await asyncio.sleep(5)
                else:
                    failure_count[ts_key] = failure_count.get(ts_key, 0) + 1
                    cooldown = min(
                        1800,
                        CONVERT_FAILED_RETRY_SECONDS * failure_count[ts_key],
                    )
                    retry_after[ts_key] = time.time() + cooldown
                    logger.error("Conversion failed", username=username, filename=ts_file, retry_in_seconds=cooldown, failures=failure_count[ts_key])

        except Exception as e:
            logger.error("Conversion task failed",
                        error=str(e),
                        exc_info=True)
            await asyncio.sleep(60)

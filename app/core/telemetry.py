"""
Système de télémétrie anonyme pour P-StreamRec
Collecte uniquement: UUID instance, version, timestamp
Respecte la vie privée, désactivable via TELEMETRY_DISABLED=true
"""

import os
import uuid
import asyncio
import httpx
from pathlib import Path
from typing import Optional
import json
from datetime import datetime
from ..logger import logger

# Configuration
TELEMETRY_DISABLED = os.getenv("TELEMETRY_DISABLED", "false").lower() in {"1", "true", "yes"}
# JSONBin.io - Service gratuit sans inscription (lecture publique)
TELEMETRY_BIN_URL = os.getenv(
    "TELEMETRY_BIN_URL",
    "https://api.jsonbin.io/v3/b/671234567890abcdef123456"  # Bin public partagé
)
PING_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "86400"))  # 24h par défaut


class Telemetry:
    """Gestion de la télémétrie anonyme"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.instance_id_file = data_dir / ".instance_id"
        self.instance_id: Optional[str] = None
        self.enabled = not TELEMETRY_DISABLED
        self._task: Optional[asyncio.Task] = None
        
    def _generate_instance_id(self) -> str:
        """Génère un UUID v4 unique pour cette instance"""
        return str(uuid.uuid4())
    
    def get_instance_id(self) -> str:
        """Récupère ou crée l'ID unique de l'instance"""
        if self.instance_id:
            return self.instance_id
            
        # Lire depuis le fichier si existant
        if self.instance_id_file.exists():
            try:
                with open(self.instance_id_file, 'r') as f:
                    self.instance_id = f.read().strip()
                    logger.debug("Instance ID chargé", instance_id=self.instance_id[:8] + "...")
                    return self.instance_id
            except Exception as e:
                logger.warning("Impossible de lire l'instance ID", error=str(e))
        
        # Générer un nouvel ID
        self.instance_id = self._generate_instance_id()
        
        # Sauvegarder
        try:
            with open(self.instance_id_file, 'w') as f:
                f.write(self.instance_id)
            logger.info("Nouvel Instance ID généré", instance_id=self.instance_id[:8] + "...")
        except Exception as e:
            logger.error("Impossible de sauvegarder l'instance ID", error=str(e))
        
        return self.instance_id
    
    def get_version(self) -> str:
        """Récupère la version depuis version.json"""
        version_file = self.data_dir.parent / "version.json"
        try:
            if version_file.exists():
                with open(version_file, 'r') as f:
                    data = json.load(f)
                    return data.get('version', 'unknown')
        except Exception:
            pass
        return 'unknown'
    
    async def send_ping(self) -> bool:
        """Envoie un ping anonyme - met à jour le bin JSONBin avec cette instance"""
        if not self.enabled:
            return False
        
        instance_id = self.get_instance_id()
        version = self.get_version()
        now = datetime.utcnow().isoformat()
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # 1. Lire le bin actuel
                response = await client.get(TELEMETRY_BIN_URL)
                
                if response.status_code == 200:
                    data = response.json()
                    instances = data.get('record', {}).get('instances', {})
                else:
                    instances = {}
                
                # 2. Ajouter/mettre à jour cette instance
                instances[instance_id] = {
                    "version": version,
                    "platform": "docker" if os.path.exists("/.dockerenv") else "native",
                    "last_ping": now
                }
                
                # 3. Nettoyer les instances inactives (>48h)
                cutoff = datetime.utcnow()
                active_instances = {}
                for iid, info in instances.items():
                    try:
                        last_ping = datetime.fromisoformat(info['last_ping'])
                        age_hours = (cutoff - last_ping).total_seconds() / 3600
                        if age_hours < 48:  # Garder seulement les 48 dernières heures
                            active_instances[iid] = info
                    except:
                        pass
                
                # 4. Mettre à jour le bin
                update_payload = {
                    "instances": active_instances,
                    "updated_at": now,
                    "total_active": len(active_instances)
                }
                
                update_response = await client.put(
                    TELEMETRY_BIN_URL,
                    json=update_payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if update_response.status_code in [200, 201]:
                    logger.debug(
                        "Ping télémétrie envoyé",
                        instance_id=instance_id[:8] + "...",
                        total_active=len(active_instances)
                    )
                    return True
                else:
                    logger.warning(
                        "Ping télémétrie échoué",
                        status=update_response.status_code
                    )
                    return False
                    
        except Exception as e:
            logger.debug("Impossible d'envoyer le ping télémétrie", error=str(e))
            return False
    
    async def get_stats(self) -> dict:
        """Récupère les statistiques publiques depuis JSONBin"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(TELEMETRY_BIN_URL)
                
                if response.status_code == 200:
                    data = response.json()
                    record = data.get('record', {})
                    return {
                        'active_instances': record.get('total_active', 0),
                        'instances': record.get('instances', {}),
                        'updated_at': record.get('updated_at')
                    }
        except Exception as e:
            logger.debug("Impossible de récupérer les stats télémétrie", error=str(e))
        
        return {'active_instances': 0, 'instances': {}, 'updated_at': None}
    
    async def start_periodic_ping(self):
        """Démarre le ping périodique (tâche en arrière-plan)"""
        if not self.enabled:
            logger.info("📊 Télémétrie désactivée (TELEMETRY_DISABLED=true)")
            return
        
        logger.info(
            "📊 Télémétrie activée", 
            interval_hours=PING_INTERVAL / 3600,
            instance_id=self.get_instance_id()[:8] + "..."
        )
        
        # Envoyer un ping immédiatement au démarrage
        await self.send_ping()
        
        # Puis périodiquement
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await self.send_ping()
    
    def start(self):
        """Démarre la tâche de télémétrie"""
        if self._task is None and self.enabled:
            self._task = asyncio.create_task(self.start_periodic_ping())
            logger.debug("Tâche de télémétrie démarrée")
    
    async def stop(self):
        """Arrête la tâche de télémétrie"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.debug("Tâche de télémétrie arrêtée")

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
# CountAPI.xyz - Service gratuit sans inscription, fait pour compter
COUNTAPI_NAMESPACE = os.getenv("COUNTAPI_NAMESPACE", "p-streamrec")
COUNTAPI_KEY = os.getenv("COUNTAPI_KEY", "active-instances")
PING_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "43200"))  # 12h par défaut


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
        """Log simple au démarrage - pas de télémétrie externe"""
        if not self.enabled:
            return False
        
        instance_id = self.get_instance_id()
        logger.info(
            "📊 Instance démarrée",
            instance_id=instance_id[:8] + "...",
            version=self.get_version()
        )
        return True
    
    async def get_stats(self) -> dict:
        """Récupère les stats depuis GitHub (stars + forks comme proxy de popularité)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Utiliser l'API GitHub pour les stats publiques
                url = "https://api.github.com/repos/raccommode/P-StreamRec"
                response = await client.get(
                    url,
                    headers={"Accept": "application/vnd.github.v3+json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    stars = data.get('stargazers_count', 0)
                    forks = data.get('forks_count', 0)
                    
                    # Estimer le nombre d'instances actives basé sur forks/stars
                    # Hypothèse: ~10% des stars = installations actives
                    estimated_instances = max(1, int(stars * 0.1))
                    
                    return {
                        'active_instances': estimated_instances,
                        'stars': stars,
                        'forks': forks,
                        'source': 'github'
                    }
        except Exception as e:
            logger.debug("Impossible de récupérer les stats GitHub", error=str(e))
        
        return {'active_instances': 0, 'stars': 0, 'forks': 0, 'source': 'offline'}
    
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

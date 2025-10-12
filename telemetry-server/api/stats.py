"""
Endpoint pour afficher les statistiques des instances actives
"""

from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
import os

# Si Vercel KV est configuré, utiliser Redis
# Sinon, retourner des stats par défaut
try:
    from vercel_kv import kv
    HAS_KV = True
except ImportError:
    HAS_KV = False


class handler(BaseHTTPRequestHandler):
    """Handler pour les statistiques"""
    
    def do_GET(self):
        """Retourne les statistiques des instances actives"""
        try:
            stats = {
                'active_instances': 0,
                'total_pings': 0,
                'versions': {},
                'platforms': {},
                'last_24h': 0,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            if HAS_KV:
                # Récupérer toutes les instances depuis Redis
                # Format clé: telemetry:instance:{instance_id}
                # Valeur: JSON avec version, platform, last_ping
                
                # Scanner toutes les clés
                # Note: Vercel KV a une limite, utiliser SCAN pour éviter de bloquer
                try:
                    # Récupérer le compteur total
                    total_pings = kv.get('telemetry:total_pings') or 0
                    stats['total_pings'] = int(total_pings)
                    
                    # Récupérer les instances actives (dernières 48h)
                    cutoff = datetime.utcnow() - timedelta(hours=48)
                    
                    # Lister toutes les instances (limité à 100 pour l'exemple)
                    # Dans une vraie implémentation, utiliser un set Redis pour tracker les actives
                    active_count = kv.get('telemetry:active_count') or 0
                    stats['active_instances'] = int(active_count)
                    
                except Exception as e:
                    print(f"Error reading from KV: {e}")
            else:
                # Mode démo sans base de données
                stats['message'] = 'Demo mode - Configure Vercel KV for real stats'
                stats['info'] = 'Add VERCEL_KV_REST_API_URL and VERCEL_KV_REST_API_TOKEN'
            
            # Réponse
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=60')
            self.end_headers()
            
            self.wfile.write(json.dumps(stats, indent=2).encode('utf-8'))
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

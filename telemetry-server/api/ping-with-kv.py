"""
Version améliorée avec Vercel KV (Redis)
Renommer ce fichier en ping.py pour l'utiliser
"""

from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
import os

try:
    from vercel_kv import kv
    HAS_KV = True
except ImportError:
    HAS_KV = False
    print("Warning: vercel-kv not installed, running in demo mode")


class handler(BaseHTTPRequestHandler):
    """Handler pour les pings de télémétrie avec stockage Redis"""
    
    def do_POST(self):
        """Reçoit un ping et met à jour Redis"""
        try:
            # Lire le body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            instance_id = data.get('instance_id')
            version = data.get('version', 'unknown')
            timestamp = data.get('timestamp')
            platform = data.get('platform', 'unknown')
            
            if not instance_id:
                self.send_error(400, "Missing instance_id")
                return
            
            # Log
            print(f"[PING] {instance_id[:8]}... v{version} ({platform}) @ {timestamp}")
            
            if HAS_KV:
                # Stocker dans Redis avec expiration de 48h
                instance_key = f"telemetry:instance:{instance_id}"
                instance_data = {
                    'version': version,
                    'platform': platform,
                    'last_ping': timestamp,
                    'first_seen': kv.get(f"{instance_key}:first_seen") or timestamp
                }
                
                # Sauvegarder avec TTL de 48h (172800 secondes)
                kv.setex(instance_key, 172800, json.dumps(instance_data))
                
                # Incrémenter le compteur total de pings
                kv.incr('telemetry:total_pings')
                
                # Mettre à jour le compteur d'instances actives
                # Compter toutes les clés qui matchent telemetry:instance:*
                # (Note: approche simplifiée, dans un vrai système utiliser un Set Redis)
                all_instances = kv.keys('telemetry:instance:*')
                active_count = len([k for k in all_instances if k != f"{instance_key}:first_seen"])
                kv.set('telemetry:active_count', active_count)
                
                # Tracker par version
                version_key = f"telemetry:version:{version}"
                kv.incr(version_key)
                kv.expire(version_key, 2592000)  # 30 jours
            
            # Réponse succès
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                'success': True,
                'message': 'Ping received and stored',
                'instance_id': instance_id[:8] + '...',
                'kv_enabled': HAS_KV
            }
            
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            print(f"Error: {e}")
            self.send_error(500, str(e))
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Retourne le statut"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {
            'service': 'P-StreamRec Telemetry (KV Edition)',
            'status': 'online',
            'kv_enabled': HAS_KV,
            'message': 'Send POST with instance_id, version, timestamp, platform'
        }
        
        self.wfile.write(json.dumps(response).encode('utf-8'))

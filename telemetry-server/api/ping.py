"""
Endpoint serverless pour recevoir les pings de télémétrie
Déployer sur Vercel: https://vercel.com
"""

from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
import os

# Utiliser Vercel KV (Redis) pour stocker les instances
# Ou simplement un fichier JSON (moins fiable mais gratuit)


class handler(BaseHTTPRequestHandler):
    """Handler pour les pings de télémétrie"""
    
    def do_POST(self):
        """Reçoit un ping et met à jour le compteur"""
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
            
            # Dans une vraie implémentation, stocker dans une base de données
            # Pour Vercel, utiliser Vercel KV (Redis) ou une base comme Supabase
            # Ici on fait juste un log
            print(f"[PING] {instance_id[:8]}... v{version} ({platform}) @ {timestamp}")
            
            # Réponse succès
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                'success': True,
                'message': 'Ping received',
                'instance_id': instance_id[:8] + '...'
            }
            
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Retourne le statut (pour monitoring)"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {
            'service': 'P-StreamRec Telemetry',
            'status': 'online',
            'message': 'Send POST with instance_id, version, timestamp'
        }
        
        self.wfile.write(json.dumps(response).encode('utf-8'))

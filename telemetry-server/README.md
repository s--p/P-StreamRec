# P-StreamRec Telemetry Server

Serveur de télémétrie anonyme pour compter les instances actives de P-StreamRec.

## 🎯 Fonctionnalités

- **Comptage anonyme** des instances actives
- **Sans clé API publique** (endpoint public)
- **Gratuit** avec Vercel
- **Respectueux de la vie privée** (uniquement UUID, version, timestamp)

## 📊 Données collectées

- `instance_id` : UUID v4 généré localement (anonyme)
- `version` : Version de P-StreamRec
- `timestamp` : Date/heure du ping
- `platform` : "docker" ou "native"

**Aucune donnée personnelle, IP ou nom d'utilisateur n'est collectée.**

## 🚀 Déploiement sur Vercel

### Option 1: Version simple (sans base de données)

1. Créer un compte sur [Vercel](https://vercel.com)
2. Installer Vercel CLI:
   ```bash
   npm install -g vercel
   ```
3. Déployer:
   ```bash
   cd telemetry-server
   vercel
   ```
4. Suivre les instructions
5. Votre endpoint sera: `https://votre-projet.vercel.app/api/ping`

### Option 2: Avec Vercel KV (Redis) pour stats persistantes

1. Activer **Vercel KV** dans votre projet Vercel (Storage > Create Database > KV)
2. Renommer `api/ping-with-kv.py` → `api/ping.py`
3. Ajouter au `requirements.txt`:
   ```
   vercel-kv==0.6.0
   ```
4. Déployer:
   ```bash
   vercel
   ```
5. Les variables d'environnement KV seront automatiquement configurées

## 📈 Endpoints disponibles

### `POST /api/ping`
Reçoit un ping d'une instance.

**Body:**
```json
{
  "instance_id": "uuid-v4-here",
  "version": "2025.41.D",
  "timestamp": "2025-10-11T20:53:00Z",
  "platform": "docker"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Ping received",
  "instance_id": "abc12345..."
}
```

### `GET /api/stats`
Retourne les statistiques (nécessite Vercel KV).

**Response:**
```json
{
  "active_instances": 42,
  "total_pings": 1337,
  "versions": {
    "2025.41.D": 25,
    "2025.40.C": 17
  },
  "platforms": {
    "docker": 35,
    "native": 7
  },
  "last_24h": 38,
  "timestamp": "2025-10-11T20:53:00Z"
}
```

## 🔧 Configuration dans P-StreamRec

Mettre à jour l'URL dans `.env` ou `docker-compose.yml`:

```bash
TELEMETRY_ENDPOINT=https://votre-projet.vercel.app/api/ping
```

Ou désactiver complètement:

```bash
TELEMETRY_DISABLED=true
```

## 💰 Coûts

- **Vercel Free Tier**: 
  - ✅ Serverless Functions illimitées
  - ✅ 100GB bandwidth/mois
  - ✅ KV: 30,000 commandes/jour gratuit
  
**Pour un projet open-source avec ~1000 instances:**
- 1000 instances × 1 ping/jour = 1000 requêtes/jour
- **100% gratuit** sur Vercel Free Tier

## 🔐 Vie privée

Ce système est conçu pour respecter la vie privée :

1. **UUID anonyme** généré localement (pas d'IP, pas de tracking)
2. **Opt-out facile** via `TELEMETRY_DISABLED=true`
3. **Transparent** : code source ouvert
4. **Minimal** : seulement version + timestamp
5. **Pas de tracking inter-sessions** : juste un compteur d'instances actives

## 📊 Dashboard (optionnel)

Créer une page publique pour afficher les stats :

```bash
cd telemetry-server
mkdir public
# Créer public/index.html avec un dashboard simple
```

## 🛠 Développement local

```bash
cd telemetry-server
vercel dev
```

Tester :
```bash
curl -X POST http://localhost:3000/api/ping \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-123",
    "version": "2025.41.D",
    "timestamp": "2025-10-11T20:53:00Z",
    "platform": "docker"
  }'
```

## 🔄 Alternatives

Si vous ne voulez pas utiliser Vercel :

1. **Netlify Functions** (même principe)
2. **Cloudflare Workers** (edge computing)
3. **Railway.app** (serveur Node.js/Python simple)
4. **Supabase** (PostgreSQL + Functions)
5. **Self-hosted** (votre propre serveur)

## 📝 License

MIT - Même license que P-StreamRec

# 🚫 Fix Discovery - HTTP 403 Forbidden

## Problème

Chaturbate retourne **HTTP 403 Forbidden** car il détecte que les requêtes proviennent d'un serveur/bot et non d'un vrai navigateur. C'est une protection anti-scraping.

```
❌ [ERROR] HTTP error
└─ {"status_code": 403}
```

## Solutions

### Solution 1 : Ajouter un Cookie de Session (RECOMMANDÉ)

Chaturbate nécessite un cookie de session valide pour autoriser l'accès.

#### Étape 1 : Obtenir votre cookie

1. Ouvrez Chrome/Firefox
2. Allez sur https://chaturbate.com
3. Ouvrez la console (F12) → Onglet **Application** / **Storage**
4. Cliquez sur **Cookies** → `https://chaturbate.com`
5. Copiez la valeur du cookie `csrftoken` et autres cookies importants

Exemple de cookies à copier :
```
csrftoken=abc123...;
sessionid=xyz789...;
```

#### Étape 2 : Ajouter le cookie dans votre configuration

**Avec Docker :**

Éditez votre `docker-compose.yml` :

```yaml
version: "3.8"
services:
  p-streamrec:
    image: ghcr.io/raccommode/p-streamrec:latest
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - CB_RESOLVER_ENABLED=true
      - CB_COOKIE=csrftoken=VOTRE_TOKEN_ICI;sessionid=VOTRE_SESSION_ICI
    restart: unless-stopped
```

**Sans Docker :**

```bash
# Linux/Mac
export CB_COOKIE="csrftoken=VOTRE_TOKEN_ICI;sessionid=VOTRE_SESSION_ICI"

# Windows PowerShell
$env:CB_COOKIE="csrftoken=VOTRE_TOKEN_ICI;sessionid=VOTRE_SESSION_ICI"

# Puis redémarrer le serveur
uvicorn app.main:app --reload --port 8080
```

#### Étape 3 : Redémarrer

```bash
# Docker
docker-compose down
docker-compose up -d

# Sans Docker
# Ctrl+C puis relancer uvicorn
```

### Solution 2 : Utiliser un Proxy

Si vous avez accès à un proxy résidentiel, ajoutez-le dans la configuration :

```python
# À ajouter dans app/resolvers/discover.py

proxies = {
    'http': 'http://votre-proxy:port',
    'https': 'http://votre-proxy:port'
}

response = session.get(url, proxies=proxies, ...)
```

### Solution 3 : VPN / Changer d'IP

Si vous êtes sur un VPS/serveur cloud, l'IP peut être bloquée par Chaturbate.

- Utilisez un VPN
- Ou changez de serveur/hébergeur

### Solution 4 : Attendre et Réessayer

Parfois, le 403 est temporaire. Attendez quelques minutes et réessayez.

## Vérifier que ça fonctionne

1. Ajoutez le cookie comme indiqué ci-dessus
2. Redémarrez le serveur
3. Allez sur http://localhost:8080/discovery.html
4. Ouvrez la console (F12)
5. Vous devriez voir :

```
Fetching streams with params: page=1&limit=90
Response status: 200  ✅ (au lieu de 403)
Response data: {streams: Array(90), ...}
Rendering 90 streams
```

## Alternative : API Chaturbate Officielle

Si le scraping ne fonctionne pas, vous pouvez utiliser l'API officielle de Chaturbate (nécessite un compte affilié) :

1. Créez un compte affilié sur https://chaturbate.com/affiliates/
2. Obtenez votre clé API
3. Modifiez `app/resolvers/discover.py` pour utiliser l'API au lieu du scraping

## Pourquoi ce problème ?

- **Protection anti-bot** : Chaturbate détecte les scrapers
- **IP suspecte** : Certaines IP de data centers sont bloquées
- **Absence de cookies** : Les vraies visites ont des cookies de session
- **Headers suspects** : Les headers doivent ressembler à ceux d'un navigateur réel

## Contact

Si aucune solution ne fonctionne, le problème vient probablement de votre hébergement ou réseau. Essayez de :

1. Tester depuis votre ordinateur personnel (pas un serveur)
2. Utiliser un VPN
3. Contacter Chaturbate pour obtenir un accès API officiel

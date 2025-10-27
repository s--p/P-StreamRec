# 🔍 Installation du menu Discovery

## Étape 1 : Installer les nouvelles dépendances

Les nouvelles librairies sont nécessaires pour le web scraping :

```bash
pip install beautifulsoup4==4.12.3 lxml==5.1.0
```

Ou installez toutes les dépendances depuis requirements.txt :

```bash
pip install -r requirements.txt
```

## Étape 2 : Tester le scraping

Exécutez le script de test pour vérifier que tout fonctionne :

```bash
python3 test_discover.py
```

Vous devriez voir :
```
✓ BeautifulSoup4 is installed
✓ Requests is installed

🔍 Testing Discovery scraper...
--------------------------------------------------

1️⃣ Testing basic scraping (no filters)...
   ✓ Streams found: 10
   ✓ Total: 100
   ✓ Page: 1
   ✓ Has more: True
```

## Étape 3 : Démarrer le serveur

```bash
# Avec uvicorn
uvicorn app.main:app --reload --port 8080

# Ou avec Docker (rebuild nécessaire)
docker-compose down
docker-compose build
docker-compose up -d
```

## Étape 4 : Accéder à Discovery

1. Ouvrez votre navigateur : `http://localhost:8080`
2. Cliquez sur **🔍 Discovery** dans le menu
3. Profitez des milliers de streams en direct !

## Dépannage

### Erreur "No module named 'bs4'"
```bash
pip install beautifulsoup4
```

### Erreur "No streams found"
- Vérifiez votre connexion internet
- Chaturbate peut avoir modifié sa structure HTML
- Ouvrez la console du navigateur (F12) pour voir les logs

### Erreur "Network Error"
- Vérifiez que le serveur est démarré
- Vérifiez que le port 8080 est disponible

### Docker : Rebuild après modifications
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Fonctionnalités

✅ **Filtres avancés**
- Genre : Female, Male, Couple, Trans
- Région : North America, South America, Europe, Asia, Other  
- Tags : 60+ tags populaires
- Recherche par username

✅ **Actions rapides**
- Regarder le stream directement
- Ajouter à vos modèles en 1 clic

✅ **Pagination**
- 90 streams par page
- Navigation entre les pages

✅ **Stats en temps réel**
- Nombre total de streams
- Nombre total de viewers

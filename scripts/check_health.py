#!/usr/bin/env python3
"""
Script de vérification de santé pour P-StreamRec
Vérifie que toutes les dépendances et configurations sont correctes
"""

import sys
import os
import subprocess
from pathlib import Path

def check_python_version():
    """Vérifie que Python 3.8+ est installé"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ requis")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_dependencies():
    """Vérifie que toutes les dépendances Python sont installées"""
    try:
        import fastapi
        import uvicorn
        import requests
        import aiohttp
        import pydantic
        print("✅ Toutes les dépendances Python sont installées")
        return True
    except ImportError as e:
        print(f"❌ Dépendance manquante: {e}")
        print("   Exécutez: pip install -r requirements.txt")
        return False

def check_ffmpeg():
    """Vérifie que FFmpeg est installé et accessible"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg installé: {version_line}")
            return True
        else:
            print("❌ FFmpeg n'a pas pu être exécuté")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg non trouvé dans le PATH")
        print("   Installation: brew install ffmpeg (macOS)")
        return False
    except Exception as e:
        print(f"❌ Erreur lors de la vérification FFmpeg: {e}")
        return False

def check_ffprobe():
    """Vérifie que FFprobe est installé (généralement avec FFmpeg)"""
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ FFprobe installé")
            return True
        else:
            print("⚠️ FFprobe n'a pas pu être exécuté")
            return False
    except FileNotFoundError:
        print("⚠️ FFprobe non trouvé (métadonnées vidéo non disponibles)")
        return False
    except Exception as e:
        print(f"⚠️ Erreur lors de la vérification FFprobe: {e}")
        return False

def check_structure():
    """Vérifie la structure des dossiers"""
    base_dir = Path(__file__).parent
    required_files = [
        "app/main.py",
        "app/ffmpeg_runner.py",
        "app/resolvers/chaturbate.py",
        "static/index.html",
        "requirements.txt"
    ]
    
    all_ok = True
    for file_path in required_files:
        full_path = base_dir / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} manquant")
            all_ok = False
    
    return all_ok

def check_syntax():
    """Vérifie la syntaxe Python de tous les fichiers"""
    base_dir = Path(__file__).parent
    app_dir = base_dir / "app"
    
    python_files = list(app_dir.rglob("*.py"))
    errors = []
    
    for py_file in python_files:
        try:
            with open(py_file, 'r') as f:
                compile(f.read(), str(py_file), 'exec')
        except SyntaxError as e:
            errors.append(f"{py_file}: {e}")
    
    if errors:
        print("❌ Erreurs de syntaxe détectées:")
        for error in errors:
            print(f"   {error}")
        return False
    else:
        print(f"✅ Syntaxe Python valide ({len(python_files)} fichiers)")
        return True

def check_env_example():
    """Vérifie que .env.example existe"""
    base_dir = Path(__file__).parent
    env_example = base_dir / ".env.example"
    
    if env_example.exists():
        print("✅ .env.example présent")
        return True
    else:
        print("⚠️ .env.example manquant (optionnel)")
        return True

def main():
    print("=" * 60)
    print("🔍 P-StreamRec - Vérification de santé")
    print("=" * 60)
    print()
    
    checks = [
        ("Version Python", check_python_version),
        ("Dépendances Python", check_dependencies),
        ("FFmpeg", check_ffmpeg),
        ("FFprobe", check_ffprobe),
        ("Structure du projet", check_structure),
        ("Syntaxe Python", check_syntax),
        ("Fichiers de configuration", check_env_example),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n--- {name} ---")
        result = check_func()
        results.append(result)
        print()
    
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ Tous les tests sont passés ({passed}/{total})")
        print("\n🚀 Le système est prêt à démarrer!")
        print("   Lancez: uvicorn app.main:app --reload")
        return 0
    else:
        print(f"⚠️ {passed}/{total} tests passés")
        print("\n❌ Veuillez corriger les problèmes avant de démarrer")
        return 1

if __name__ == "__main__":
    sys.exit(main())

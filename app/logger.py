"""
Système de logging centralisé pour P-StreamRec
Fournit des logs détaillés, structurés et colorisés pour faciliter le debugging
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

# Codes couleur ANSI
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Couleurs de base
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Couleurs brillantes
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    
    # Backgrounds
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


class DetailedFormatter(logging.Formatter):
    """Formatter personnalisé avec couleurs et emojis"""
    
    EMOJI_MAP = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🔥'
    }
    
    COLOR_MAP = {
        'DEBUG': Colors.CYAN,
        'INFO': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'CRITICAL': Colors.BRIGHT_RED + Colors.BOLD
    }
    
    def format(self, record):
        # Timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Emoji et couleur selon le niveau
        emoji = self.EMOJI_MAP.get(record.levelname, '•')
        color = self.COLOR_MAP.get(record.levelname, Colors.RESET)
        
        # Nom du module
        module = record.name.split('.')[-1]
        
        # Message de base
        message = record.getMessage()
        
        # Construire le log
        log_line = f"{Colors.BRIGHT_BLUE}{timestamp}{Colors.RESET} {emoji} {color}[{record.levelname:8}]{Colors.RESET} {Colors.MAGENTA}{module:15}{Colors.RESET} │ {message}"
        
        # Ajouter les infos supplémentaires si disponibles
        if hasattr(record, 'extra_data') and record.extra_data:
            log_line += f"\n{Colors.CYAN}{'  ' * 10}└─ {json.dumps(record.extra_data, indent=2, ensure_ascii=False)}{Colors.RESET}"
        
        # Ajouter l'exception si présente
        if record.exc_info:
            log_line += f"\n{self.formatException(record.exc_info)}"
        
        return log_line


class AppLogger:
    """Logger principal de l'application"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # Configuration du logger principal
        self.logger = logging.getLogger('p-streamrec')
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        # Handler console avec couleurs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(DetailedFormatter())
        
        # Nettoyer les handlers existants
        self.logger.handlers.clear()
        self.logger.addHandler(console_handler)
        
        self._initialized = True
        
        # Log de démarrage
        self.startup()
    
    def startup(self):
        """Log de démarrage de l'application"""
        self.logger.info("=" * 80)
        self.logger.info(f"{Colors.BRIGHT_CYAN}{Colors.BOLD}P-STREAMREC - Démarrage de l'application{Colors.RESET}")
        self.logger.info("=" * 80)
    
    def get_logger(self, name: str):
        """Obtenir un logger pour un module spécifique"""
        return logging.getLogger(f'p-streamrec.{name}')
    
    def debug(self, message: str, **extra):
        """Log DEBUG avec données supplémentaires"""
        self.logger.debug(message, extra={'extra_data': extra} if extra else {})
    
    def info(self, message: str, **extra):
        """Log INFO avec données supplémentaires"""
        self.logger.info(message, extra={'extra_data': extra} if extra else {})
    
    def warning(self, message: str, **extra):
        """Log WARNING avec données supplémentaires"""
        self.logger.warning(message, extra={'extra_data': extra} if extra else {})
    
    def error(self, message: str, exc_info: bool = False, **extra):
        """Log ERROR avec données supplémentaires"""
        self.logger.error(message, exc_info=exc_info, extra={'extra_data': extra} if extra else {})
    
    def critical(self, message: str, exc_info: bool = False, **extra):
        """Log CRITICAL avec données supplémentaires"""
        self.logger.critical(message, exc_info=exc_info, extra={'extra_data': extra} if extra else {})
    
    def section(self, title: str, char: str = '='):
        """Afficher une section"""
        line = char * 80
        self.logger.info(line)
        self.logger.info(f"{Colors.BOLD}{title}{Colors.RESET}")
        self.logger.info(line)
    
    def subsection(self, title: str):
        """Afficher une sous-section"""
        self.logger.info(f"\n{Colors.BRIGHT_CYAN}{'─' * 40}{Colors.RESET}")
        self.logger.info(f"{Colors.BRIGHT_CYAN}{title}{Colors.RESET}")
        self.logger.info(f"{Colors.BRIGHT_CYAN}{'─' * 40}{Colors.RESET}")
    
    def success(self, message: str, **extra):
        """Log de succès (vert)"""
        self.logger.info(f"{Colors.BRIGHT_GREEN}{message}{Colors.RESET}", extra={'extra_data': extra} if extra else {})
    
    def failure(self, message: str, **extra):
        """Log d'échec (rouge)"""
        self.logger.error(f"{Colors.BRIGHT_RED}{message}{Colors.RESET}", extra={'extra_data': extra} if extra else {})
    
    def progress(self, message: str, **extra):
        """Log de progression"""
        self.logger.info(f"{Colors.BRIGHT_YELLOW}{message}{Colors.RESET}", extra={'extra_data': extra} if extra else {})
    
    def api_request(self, method: str, path: str, **extra):
        """Log d'une requête API"""
        self.logger.info(f"{Colors.BRIGHT_BLUE}{method:6} {path}{Colors.RESET}", extra={'extra_data': extra} if extra else {})
    
    def api_response(self, status: int, path: str, duration_ms: Optional[float] = None, **extra):
        """Log d'une réponse API"""
        color = Colors.BRIGHT_GREEN if status < 400 else Colors.BRIGHT_RED
        duration_str = f" ({duration_ms:.2f}ms)" if duration_ms else ""
        self.logger.info(f"{color}[{status}] {path}{duration_str}{Colors.RESET}", extra={'extra_data': extra} if extra else {})
    
    def ffmpeg_start(self, session_id: str, person: str, url: str):
        """Log démarrage FFmpeg"""
        self.section(f"DÉMARRAGE ENREGISTREMENT - {person}")
        self.logger.info(f"Session ID: {session_id}")
        self.logger.info(f"Personne: {person}")
        self.logger.info(f"URL: {url[:80]}...")
    
    def ffmpeg_stop(self, session_id: str, person: str, duration: Optional[float] = None):
        """Log arrêt FFmpeg"""
        duration_str = f" ({duration:.1f}s)" if duration else ""
        self.logger.info(f"ARRÊT ENREGISTREMENT - {person}{duration_str}")
        self.logger.info(f"Session ID: {session_id}")
    
    def ffmpeg_error(self, session_id: str, error: str):
        """Log erreur FFmpeg"""
        self.logger.error(f"ERREUR FFMPEG - Session {session_id}")
        self.logger.error(f"   {error}")
    
    def file_operation(self, operation: str, path: str, size: Optional[int] = None, **extra):
        """Log opération fichier"""
        size_str = f" ({size / 1024 / 1024:.2f} MB)" if size else ""
        self.logger.info(f"{operation}: {path}{size_str}", extra={'extra_data': extra} if extra else {})
    
    def git_operation(self, operation: str, **extra):
        """Log opération Git"""
        self.logger.info(f"GIT: {operation}", extra={'extra_data': extra} if extra else {})
    
    def background_task(self, task_name: str, action: str, **extra):
        """Log tâche en arrière-plan"""
        self.logger.info(f"BACKGROUND [{task_name}]: {action}", extra={'extra_data': extra} if extra else {})
    
    def model_operation(self, operation: str, username: str, **extra):
        """Log opération sur un modèle"""
        self.logger.info(f"MODEL [{operation}]: {username}", extra={'extra_data': extra} if extra else {})


# Instance globale
logger = AppLogger()

# Export du logger
__all__ = ['logger', 'Colors']

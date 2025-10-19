import logging
import logging.config
import os
from pathlib import Path
from datetime import datetime


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    app_name: str = "healthy-mcp"
) -> logging.Logger:
    """
    Configure et initialise le système de logging pour l'application.
    
    Args:
        log_level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Répertoire où stocker les fichiers de log
        app_name: Nom de l'application pour les fichiers de log
    
    Returns:
        Logger configuré pour l'application
    """
    # Créer le répertoire de logs s'il n'existe pas
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Configuration du logging
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "simple": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "json": {
                "()": "logging.Formatter",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "simple",
                "stream": "ext://sys.stdout"
            },
            "file_detailed": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": f"{log_dir}/{app_name}.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8"
            },
            "file_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "detailed",
                "filename": f"{log_dir}/{app_name}_error.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8"
            },
            "file_access": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "simple",
                "filename": f"{log_dir}/{app_name}_access.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8"
            }
        },
        "loggers": {
            "": {  # Root logger
                "level": log_level,
                "handlers": ["console", "file_detailed", "file_error"]
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["file_access"],
                "propagate": False
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["file_error"],
                "propagate": False
            },
            "fastapi": {
                "level": "INFO",
                "handlers": ["console", "file_detailed"],
                "propagate": False
            },
            "websockets": {
                "level": "WARNING",
                "handlers": ["file_detailed"],
                "propagate": False
            },
            f"{app_name}": {
                "level": log_level,
                "handlers": ["console", "file_detailed", "file_error"],
                "propagate": False
            }
        }
    }
    
    # Appliquer la configuration
    logging.config.dictConfig(logging_config)
    
    # Créer et retourner le logger principal de l'application
    logger = logging.getLogger(app_name)
    
    # Log de démarrage
    logger.info(f"Système de logging initialisé - Niveau: {log_level}")
    logger.info(f"Fichiers de log stockés dans: {log_path.absolute()}")
    
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Récupère un logger avec le nom spécifié.
    
    Args:
        name: Nom du logger (par défaut: nom du module appelant)
    
    Returns:
        Instance du logger
    """
    if name is None:
        # Utiliser le nom du module appelant
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get('__name__', 'healthy-mcp')
        else:
            name = 'healthy-mcp'
    
    return logging.getLogger(name)


# Décorateur pour logger automatiquement les appels de fonction
def log_function_call(logger: logging.Logger | None = None):
    """
    Décorateur pour logger automatiquement les appels de fonction.
    
    Args:
        logger: Instance du logger à utiliser (optionnel)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)
            
            logger.debug(f"Appel de fonction: {func.__name__} avec args={args}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Fonction {func.__name__} terminée avec succès")
                return result
            except Exception as e:
                logger.error(f"Erreur dans la fonction {func.__name__}: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator


# Configuration par défaut depuis les variables d'environnement
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_DIR = os.getenv("LOG_DIR", "logs")
DEFAULT_APP_NAME = os.getenv("APP_NAME", "healthy-mcp")
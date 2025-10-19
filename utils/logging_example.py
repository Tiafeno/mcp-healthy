"""
Exemple d'utilisation du système de logging pour healthy-mcp

Ce fichier montre comment utiliser le système de logging dans votre application.
"""

from utils.logging_config import setup_logging, get_logger, log_function_call

# Configuration initiale du logging (à faire au démarrage de l'application)
app_logger = setup_logging(
    log_level="INFO",
    log_dir="logs",
    app_name="healthy-mcp"
)

# Récupération d'un logger pour un module spécifique
module_logger = get_logger("example_module")

# Exemple d'utilisation basique
def example_basic_logging():
    """Exemple d'utilisation basique du logging"""
    logger = get_logger()
    
    logger.debug("Message de débogage - très détaillé")
    logger.info("Information générale sur le fonctionnement")
    logger.warning("Avertissement - quelque chose d'inhabituel")
    logger.error("Erreur - quelque chose a mal tourné")
    logger.critical("Critique - erreur grave nécessitant une attention immédiate")

# Exemple avec décorateur
@log_function_call()
def exemple_fonction_avec_logging(param1: str, param2: int = 10):
    """Fonction avec logging automatique des appels"""
    logger = get_logger()
    logger.info(f"Traitement avec param1={param1}, param2={param2}")
    
    if param2 < 0:
        raise ValueError("param2 ne peut pas être négatif")
    
    return f"Résultat: {param1} * {param2}"

# Exemple de gestion d'erreur avec logging
def exemple_gestion_erreur():
    """Exemple de gestion d'erreur avec logging détaillé"""
    logger = get_logger()
    
    try:
        # Simulation d'une opération qui peut échouer
        result = 10 / 0
    except ZeroDivisionError as e:
        logger.error("Division par zéro détectée", exc_info=True)
        logger.info("Utilisation de la valeur par défaut")
        result = 0
    except Exception as e:
        logger.critical(f"Erreur inattendue: {e}", exc_info=True)
        raise
    
    return result

# Exemple pour les opérations WebSocket
def exemple_websocket_logging(websocket_id: str, action: str):
    """Exemple de logging pour les opérations WebSocket"""
    logger = get_logger("websocket")
    
    logger.info(f"WebSocket {websocket_id}: {action}")
    
    if action == "connect":
        logger.debug(f"Nouvelle connexion WebSocket établie: {websocket_id}")
    elif action == "disconnect":
        logger.debug(f"Connexion WebSocket fermée: {websocket_id}")
    elif action == "message":
        logger.debug(f"Message reçu sur WebSocket: {websocket_id}")
    else:
        logger.warning(f"Action WebSocket inconnue: {action} pour {websocket_id}")

# Exemple pour les requêtes HTTP
def exemple_http_logging(method: str, endpoint: str, status_code: int, duration: float):
    """Exemple de logging pour les requêtes HTTP"""
    logger = get_logger("http")
    
    log_message = f"{method} {endpoint} - {status_code} - {duration:.3f}s"
    
    if status_code >= 500:
        logger.error(log_message)
    elif status_code >= 400:
        logger.warning(log_message)
    else:
        logger.info(log_message)

if __name__ == "__main__":
    # Test du système de logging
    print("Test du système de logging...")
    
    example_basic_logging()
    
    try:
        result = exemple_fonction_avec_logging("test", 5)
        print(f"Résultat: {result}")
    except Exception as e:
        print(f"Erreur: {e}")
    
    exemple_gestion_erreur()
    exemple_websocket_logging("ws-123", "connect")
    exemple_http_logging("GET", "/api/health", 200, 0.045)
    
    print("Test terminé. Vérifiez les fichiers de log dans le dossier 'logs'.")
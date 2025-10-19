"""
Middleware FastAPI pour le logging automatique des requêtes HTTP

Ce middleware capture automatiquement les informations sur toutes les requêtes
HTTP et les responses pour les logger de manière cohérente.
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from utils.logging_config import get_logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware qui log automatiquement toutes les requêtes HTTP.
    
    Capture:
    - Méthode HTTP et URL
    - Headers importants 
    - Temps de traitement
    - Code de statut de la réponse
    - Taille de la réponse
    - ID unique de requête pour le traçage
    """
    
    def __init__(self, app, logger_name: str = "healthy-mcp.api"):
        super().__init__(app)
        self.logger = get_logger(logger_name)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Générer un ID unique pour cette requête
        request_id = str(uuid.uuid4())[:8]
        
        # Enregistrer le début de la requête
        start_time = time.time()
        
        # Extraire les informations de la requête
        method = request.method
        url = str(request.url)
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "Unknown")
        content_length = request.headers.get("content-length", "0")
        
        # Logger le début de la requête
        self.logger.info(
            f"[{request_id}] {method} {url} - IP: {client_ip} - "
            f"User-Agent: {user_agent} - Content-Length: {content_length}"
        )
        
        # Ajouter l'ID de requête aux headers pour le traçage
        request.state.request_id = request_id
        
        try:
            # Traiter la requête
            response = await call_next(request)
            
            # Calculer le temps de traitement
            process_time = time.time() - start_time
            
            # Extraire les informations de la réponse
            status_code = response.status_code
            response_size = response.headers.get("content-length", "Unknown")
            
            # Déterminer le niveau de log selon le code de statut
            if status_code >= 500:
                log_level = "error"
            elif status_code >= 400:
                log_level = "warning" 
            else:
                log_level = "info"
            
            # Logger la fin de la requête
            log_message = (
                f"[{request_id}] {method} {url} - {status_code} - "
                f"{process_time:.3f}s - {response_size} bytes"
            )
            
            getattr(self.logger, log_level)(log_message)
            
            # Ajouter l'ID de requête aux headers de réponse
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Logger les erreurs non gérées
            process_time = time.time() - start_time
            self.logger.error(
                f"[{request_id}] {method} {url} - ERROR - "
                f"{process_time:.3f}s - Exception: {str(e)}",
                exc_info=True
            )
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extraire l'adresse IP du client en gérant les proxies"""
        # Vérifier les headers de proxy communs
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Prendre la première IP si plusieurs sont présentes
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback sur l'IP directe du client
        client_host = request.client.host if request.client else "Unknown"
        return client_host


class WebSocketLoggingMiddleware:
    """
    Classe utilitaire pour logger les événements WebSocket.
    
    Comme FastAPI n'a pas de middleware WebSocket natif, cette classe
    fournit des méthodes pour logger manuellement les événements WebSocket.
    """
    
    def __init__(self, logger_name: str = "healthy-mcp.websocket"):
        self.logger = get_logger(logger_name)
    
    def log_connection(self, websocket_id: str, client_ip: str = "Unknown"):
        """Logger une nouvelle connexion WebSocket"""
        self.logger.info(f"WebSocket connected - ID: {websocket_id} - IP: {client_ip}")
    
    def log_disconnection(self, websocket_id: str, reason: str = "Unknown"):
        """Logger une déconnexion WebSocket"""
        self.logger.info(f"WebSocket disconnected - ID: {websocket_id} - Reason: {reason}")
    
    def log_message_received(self, websocket_id: str, message_type: str, message_size: int = 0):
        """Logger un message reçu via WebSocket"""
        self.logger.debug(
            f"WebSocket message received - ID: {websocket_id} - "
            f"Type: {message_type} - Size: {message_size} bytes"
        )
    
    def log_message_sent(self, websocket_id: str, message_type: str, message_size: int = 0):
        """Logger un message envoyé via WebSocket"""
        self.logger.debug(
            f"WebSocket message sent - ID: {websocket_id} - "
            f"Type: {message_type} - Size: {message_size} bytes"
        )
    
    def log_error(self, websocket_id: str, error: Exception):
        """Logger une erreur WebSocket"""
        self.logger.error(
            f"WebSocket error - ID: {websocket_id} - Error: {str(error)}",
            exc_info=True
        )


# Instance globale du middleware WebSocket pour faciliter l'utilisation
websocket_logger = WebSocketLoggingMiddleware()
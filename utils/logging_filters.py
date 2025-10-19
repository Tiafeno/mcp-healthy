"""
Filtres personnalisés pour le système de logging de healthy-mcp

Ces filtres permettent de contrôler finement quels messages sont loggés
selon différents critères.
"""

import logging
import re
from typing import Pattern


class InfoFilter(logging.Filter):
    """Filtre qui ne laisse passer que les messages de niveau INFO et plus élevé"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO


class DebugOnlyFilter(logging.Filter):
    """Filtre qui ne laisse passer que les messages de niveau DEBUG"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == logging.DEBUG


class ExcludeHealthCheckFilter(logging.Filter):
    """Filtre qui exclut les messages des health checks pour éviter le spam"""
    
    def __init__(self, health_check_patterns: list[str] | None = None):
        super().__init__()
        if health_check_patterns is None:
            health_check_patterns = [
                r"/health",
                r"/status",
                r"/ping",
                r"health_check",
                r"heartbeat"
            ]
        
        self.patterns: list[Pattern] = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in health_check_patterns
        ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(pattern.search(message) for pattern in self.patterns)


class SensitiveDataFilter(logging.Filter):
    """Filtre qui masque les données sensibles dans les logs"""
    
    def __init__(self):
        super().__init__()
        # Patterns pour détecter les données sensibles
        self.sensitive_patterns = [
            (re.compile(r'password["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE), 'password="***"'),
            (re.compile(r'token["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE), 'token="***"'),
            (re.compile(r'api_key["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE), 'api_key="***"'),
            (re.compile(r'secret["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE), 'secret="***"'),
            (re.compile(r'authorization["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE), 'authorization="***"'),
            # Pattern pour les emails (optionnel, peut être trop restrictif)
            # (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '***@***.***'),
        ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Masquer les données sensibles dans le message
        message = record.getMessage()
        for pattern, replacement in self.sensitive_patterns:
            message = pattern.sub(replacement, message)
        
        # Mettre à jour le message dans le record
        record.msg = message
        record.args = ()
        
        return True


class RateLimitFilter(logging.Filter):
    """Filtre qui limite le taux de certains messages pour éviter le spam"""
    
    def __init__(self, max_per_minute: int = 60):
        super().__init__()
        self.max_per_minute = max_per_minute
        self.message_counts = {}
        self.last_reset = {}
    
    def filter(self, record: logging.LogRecord) -> bool:
        import time
        
        current_time = time.time()
        message_key = f"{record.name}:{record.levelname}:{record.funcName}"
        
        # Reset du compteur si plus d'une minute s'est écoulée
        if (message_key not in self.last_reset or 
            current_time - self.last_reset[message_key] >= 60):
            self.message_counts[message_key] = 0
            self.last_reset[message_key] = current_time
        
        # Incrémenter le compteur
        self.message_counts[message_key] = self.message_counts.get(message_key, 0) + 1
        
        # Permettre le message s'il n'a pas dépassé la limite
        if self.message_counts[message_key] <= self.max_per_minute:
            return True
        elif self.message_counts[message_key] == self.max_per_minute + 1:
            # Ajouter un message indiquant que les messages suivants seront supprimés
            record.msg = f"[RATE LIMITED] {record.msg} (messages suivants supprimés pour 1 minute)"
            return True
        else:
            return False


class WebSocketFilter(logging.Filter):
    """Filtre spécialisé pour les logs WebSocket"""
    
    def __init__(self, log_connections: bool = True, log_messages: bool = False):
        super().__init__()
        self.log_connections = log_connections
        self.log_messages = log_messages
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        
        # Logs de connexion/déconnexion
        if any(keyword in message for keyword in ['connect', 'disconnect', 'close']):
            return self.log_connections
        
        # Logs de messages
        if any(keyword in message for keyword in ['message', 'send', 'receive']):
            return self.log_messages
        
        # Autres logs WebSocket
        return True


class DatabaseFilter(logging.Filter):
    """Filtre spécialisé pour les logs de base de données"""
    
    def __init__(self, log_queries: bool = False, log_slow_queries_only: bool = True, slow_query_threshold: float = 1.0):
        super().__init__()
        self.log_queries = log_queries
        self.log_slow_queries_only = log_slow_queries_only
        self.slow_query_threshold = slow_query_threshold
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        
        # Ne pas logger les requêtes sauf si explicitement demandé
        if 'query' in message or 'sql' in message:
            if not self.log_queries:
                return False
            
            # Si on ne veut que les requêtes lentes, vérifier le temps
            if self.log_slow_queries_only:
                # Chercher un pattern de temps dans le message
                import re
                time_match = re.search(r'(\d+\.?\d*)\s*s', message)
                if time_match:
                    query_time = float(time_match.group(1))
                    return query_time >= self.slow_query_threshold
        
        return True
"""
Service Redis pour le cache des conversations dans Healthy MCP

Ce service gère le stockage des derniers messages par conversation
pour optimiser les requêtes et maintenir le contexte conversationnel.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any
import redis.asyncio as redis
from utils.logging_config import get_logger


class RedisService:
    """
    Service Redis pour gérer le cache des conversations.
    
    Fonctionnalités:
    - Stockage/récupération du dernier message par conversation
    - TTL configurable pour expiration automatique
    - Gestion des erreurs avec fallback
    - Logging complet des opérations
    """
    
    def __init__(
        self,
        redis_url: str | None = None,
        default_ttl: int = 2592000,  # 1 month
        key_prefix: str = "healthy_mcp"
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self.redis: Optional[redis.Redis] = None
        self.logger = get_logger("healthy-mcp.redis")
        
    async def connect(self) -> bool:
        """
        Établit la connexion à Redis.
        
        Returns:
            bool: True si la connexion est établie, False sinon
        """
        try:
            self.logger.info(f"Connecting to Redis at {self.redis_url}")
            self.redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            
            # Test de la connexion
            await self.redis.ping()
            self.logger.info("Redis connection established successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
            self.redis = None
            return False
    
    async def disconnect(self):
        """Ferme la connexion Redis proprement."""
        if self.redis:
            try:
                await self.redis.aclose()
                self.logger.debug("Redis connection closed")
            except Exception as e:
                self.logger.error(f"Error closing Redis connection: {e}")
            finally:
                self.redis = None
    
    def _make_key(self, conversation_id: str, key_type: str = "last_message") -> str:
        """
        Génère une clé Redis standardisée.
        
        Args:
            conversation_id: ID de la conversation
            key_type: Type de données (last_message, metadata, etc.)
            
        Returns:
            str: Clé Redis formatée
        """
        return f"{self.key_prefix}:{key_type}:{conversation_id}"
    
    async def store_last_message(
        self, 
        conversation_id: str, 
        message_content: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Stocke le dernier message d'une conversation.
        
        Args:
            conversation_id: ID unique de la conversation
            message_content: Contenu du dernier message
            ttl: Temps de vie en secondes (optionnel)
            
        Returns:
            bool: True si stocké avec succès, False sinon
        """
        if not self.redis:
            self.logger.warning("Redis not connected, cannot store last message")
            return False
        
        try:
            key = self._make_key(conversation_id, "last_message")
            ttl_to_use = ttl or self.default_ttl
            
            # Données à stocker avec metadata
            data = {
                "content": message_content,
                "timestamp": self._get_current_timestamp(),
                "conversation_id": conversation_id
            }
            
            # Stockage avec TTL
            await self.redis.setex(
                key,
                ttl_to_use,
                json.dumps(data, ensure_ascii=False)
            )
            
            self.logger.debug(
                f"Stored last message for conversation {conversation_id} "
                f"(length: {len(message_content)}, TTL: {ttl_to_use}s)"
            )
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failed to store last message for conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False
    
    async def get_last_message(self, conversation_id: str) -> Optional[str]:
        """
        Récupère le dernier message d'une conversation.
        
        Args:
            conversation_id: ID unique de la conversation
            
        Returns:
            Optional[str]: Contenu du dernier message ou None si non trouvé
        """
        if not self.redis:
            self.logger.warning("Redis not connected, cannot get last message")
            return None
        
        try:
            key = self._make_key(conversation_id, "last_message")
            data_str = await self.redis.get(key)
            
            if not data_str:
                self.logger.debug(f"No last message found for conversation {conversation_id}")
                return None
            
            data = json.loads(data_str)
            content = data.get("content")
            
            if content:
                self.logger.debug(
                    f"Retrieved last message for conversation {conversation_id} "
                    f"(length: {len(content)})"
                )
            
            return content
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON data for conversation {conversation_id}: {e}")
            # Nettoyer la clé corrompue
            await self.delete_last_message(conversation_id)
            return None
            
        except Exception as e:
            self.logger.error(
                f"Failed to get last message for conversation {conversation_id}: {e}",
                exc_info=True
            )
            return None
    
    async def delete_last_message(self, conversation_id: str) -> bool:
        """
        Supprime le dernier message d'une conversation du cache.
        
        Args:
            conversation_id: ID unique de la conversation
            
        Returns:
            bool: True si supprimé avec succès, False sinon
        """
        if not self.redis:
            self.logger.warning("Redis not connected, cannot delete last message")
            return False
        
        try:
            key = self._make_key(conversation_id, "last_message")
            deleted = await self.redis.delete(key)
            
            if deleted:
                self.logger.debug(f"Deleted last message for conversation {conversation_id}")
            else:
                self.logger.debug(f"No last message to delete for conversation {conversation_id}")
            
            return bool(deleted)
            
        except Exception as e:
            self.logger.error(
                f"Failed to delete last message for conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False
    
    async def get_conversation_metadata(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les métadonnées d'une conversation.
        
        Args:
            conversation_id: ID unique de la conversation
            
        Returns:
            Optional[Dict[str, Any]]: Métadonnées ou None si non trouvées
        """
        if not self.redis:
            return None
        
        try:
            key = self._make_key(conversation_id, "last_message")
            data_str = await self.redis.get(key)
            
            if not data_str:
                return None
            
            data = json.loads(data_str)
            # Retourner toutes les métadonnées sauf le contenu
            metadata = {k: v for k, v in data.items() if k != "content"}
            
            return metadata
            
        except Exception as e:
            self.logger.error(
                f"Failed to get metadata for conversation {conversation_id}: {e}",
                exc_info=True
            )
            return None
    
    async def update_last_message_ttl(self, conversation_id: str, ttl: int) -> bool:
        """
        Met à jour le TTL du dernier message d'une conversation.
        
        Args:
            conversation_id: ID unique de la conversation
            ttl: Nouveau temps de vie en secondes
            
        Returns:
            bool: True si mis à jour avec succès, False sinon
        """
        if not self.redis:
            return False
        
        try:
            key = self._make_key(conversation_id, "last_message")
            updated = await self.redis.expire(key, ttl)
            
            if updated:
                self.logger.debug(f"Updated TTL for conversation {conversation_id} to {ttl}s")
            else:
                self.logger.debug(f"No last message found to update TTL for conversation {conversation_id}")
            
            return bool(updated)
            
        except Exception as e:
            self.logger.error(
                f"Failed to update TTL for conversation {conversation_id}: {e}",
                exc_info=True
            )
            return False
    
    async def clear_all_conversations(self) -> int:
        """
        Supprime tous les derniers messages du cache.
        
        Returns:
            int: Nombre de clés supprimées
        """
        if not self.redis:
            self.logger.warning("Redis not connected, cannot clear conversations")
            return 0
        
        try:
            pattern = self._make_key("*", "last_message")
            keys = await self.redis.keys(pattern)
            
            if not keys:
                self.logger.debug("No conversations to clear")
                return 0
            
            deleted = await self.redis.delete(*keys)
            self.logger.info(f"Cleared {deleted} conversations from cache")
            
            return deleted
            
        except Exception as e:
            self.logger.error(f"Failed to clear conversations: {e}", exc_info=True)
            return 0
    
    async def get_active_conversations(self) -> list[str]:
        """
        Récupère la liste des conversations actives (ayant un dernier message en cache).
        
        Returns:
            list[str]: Liste des IDs de conversation
        """
        if not self.redis:
            return []
        
        try:
            pattern = self._make_key("*", "last_message")
            keys = await self.redis.keys(pattern)
            
            # Extraire les conversation_id des clés
            conversation_ids = []
            prefix_len = len(f"{self.key_prefix}:last_message:")
            
            for key in keys:
                if key.startswith(f"{self.key_prefix}:last_message:"):
                    conversation_id = key[prefix_len:]
                    conversation_ids.append(conversation_id)
            
            self.logger.debug(f"Found {len(conversation_ids)} active conversations")
            return conversation_ids
            
        except Exception as e:
            self.logger.error(f"Failed to get active conversations: {e}", exc_info=True)
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie l'état de santé du service Redis.
        
        Returns:
            Dict[str, Any]: Informations sur l'état du service
        """
        health_info = {
            "connected": False,
            "ping_successful": False,
            "active_conversations": 0,
            "error": None
        }
        
        try:
            if not self.redis:
                health_info["error"] = "Redis not initialized"
                return health_info
            
            health_info["connected"] = True
            
            # Test ping
            await self.redis.ping()
            health_info["ping_successful"] = True
            
            # Compter les conversations actives
            active_conversations = await self.get_active_conversations()
            health_info["active_conversations"] = len(active_conversations)
            
            self.logger.debug("Redis health check passed")
            
        except Exception as e:
            health_info["error"] = str(e)
            self.logger.error(f"Redis health check failed: {e}")
        
        return health_info
    
    def _get_current_timestamp(self) -> int:
        """Retourne le timestamp Unix actuel."""
        import time
        return int(time.time())


# Instance globale du service Redis
redis_service = RedisService()
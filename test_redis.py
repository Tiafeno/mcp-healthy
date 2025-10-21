#!/usr/bin/env python3
"""
Script de test pour le service Redis

Ce script teste toutes les fonctionnalités du service Redis
indépendamment de l'application principale.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()
load_dotenv('.env.redis')

# Ajouter le répertoire parent au path pour importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.redis_service import RedisService
from utils.logging_config import setup_logging, get_logger


async def test_redis_service():
    """Test complet du service Redis"""
    
    # Configuration du logging pour les tests
    setup_logging(log_level="DEBUG", log_dir="logs", app_name="redis-test")
    logger = get_logger("redis_test")
    
    print("=== Test du Service Redis ===\n")
    
    # Initialisation du service
    redis_service = RedisService(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        default_ttl=int(os.getenv("REDIS_DEFAULT_TTL", "3600")),
        key_prefix=os.getenv("REDIS_KEY_PREFIX", "healthy_mcp_test")
    )
    
    try:
        # Test 1: Connexion
        print("1. Test de connexion...")
        connected = await redis_service.connect()
        if connected:
            print("✅ Connexion Redis établie")
        else:
            print("❌ Échec de la connexion Redis")
            return False
        
        # Test 2: Health check
        print("\n2. Test de santé...")
        health = await redis_service.health_check()
        print(f"   État: {health}")
        
        # Test 3: Stockage et récupération
        print("\n3. Test stockage/récupération...")
        test_conversation_id = "test_conv_123"
        test_message = "Ceci est un message de test pour Redis"
        
        stored = await redis_service.store_last_message(test_conversation_id, test_message)
        if stored:
            print("✅ Message stocké avec succès")
        else:
            print("❌ Échec du stockage")
            return False
        
        retrieved = await redis_service.get_last_message(test_conversation_id)
        if retrieved == test_message:
            print("✅ Message récupéré avec succès")
        else:
            print(f"❌ Échec de récupération. Attendu: '{test_message}', Reçu: '{retrieved}'")
            return False
        
        # Test 4: Métadonnées
        print("\n4. Test des métadonnées...")
        metadata = await redis_service.get_conversation_metadata(test_conversation_id)
        if metadata:
            print(f"✅ Métadonnées récupérées: {metadata}")
        else:
            print("❌ Échec de récupération des métadonnées")
        
        # Test 5: Conversations actives
        print("\n5. Test des conversations actives...")
        # Ajouter quelques conversations de test
        test_conversations = ["conv_1", "conv_2", "conv_3"]
        for conv_id in test_conversations:
            await redis_service.store_last_message(conv_id, f"Message pour {conv_id}")
        
        active_conversations = await redis_service.get_active_conversations()
        print(f"   Conversations actives: {active_conversations}")
        
        if len(active_conversations) >= 4:  # test_conversation_id + 3 nouvelles
            print("✅ Test des conversations actives réussi")
        else:
            print("❌ Nombre de conversations actives incorrect")
        
        # Test 6: TTL
        print("\n6. Test du TTL...")
        ttl_updated = await redis_service.update_last_message_ttl(test_conversation_id, 60)
        if ttl_updated:
            print("✅ TTL mis à jour avec succès")
        else:
            print("❌ Échec de mise à jour du TTL")
        
        # Test 7: Suppression
        print("\n7. Test de suppression...")
        deleted = await redis_service.delete_last_message(test_conversation_id)
        if deleted:
            print("✅ Message supprimé avec succès")
        else:
            print("❌ Échec de suppression")
        
        # Vérifier que le message a été supprimé
        retrieved_after_delete = await redis_service.get_last_message(test_conversation_id)
        if retrieved_after_delete is None:
            print("✅ Vérification de suppression réussie")
        else:
            print("❌ Le message n'a pas été supprimé correctement")
        
        # Test 8: Nettoyage complet
        print("\n8. Test de nettoyage complet...")
        cleared_count = await redis_service.clear_all_conversations()
        print(f"   {cleared_count} conversations supprimées")
        
        if cleared_count >= 3:  # Les 3 conversations de test
            print("✅ Nettoyage complet réussi")
        else:
            print("❌ Nettoyage complet incomplet")
        
        print("\n🎉 Tous les tests Redis ont réussi!")
        return True
        
    except Exception as e:
        logger.error(f"Erreur durant les tests Redis: {e}", exc_info=True)
        print(f"\n❌ Erreur durant les tests: {e}")
        return False
        
    finally:
        # Nettoyage final
        await redis_service.disconnect()
        print("\n📡 Connexion Redis fermée")


async def test_redis_performance():
    """Test de performance du service Redis"""
    
    print("\n=== Test de Performance Redis ===\n")
    
    redis_service = RedisService(key_prefix="perf_test")
    
    try:
        await redis_service.connect()
        
        import time
        
        # Test d'écriture
        print("Test d'écriture (100 messages)...")
        start_time = time.time()
        
        for i in range(100):
            await redis_service.store_last_message(f"perf_conv_{i}", f"Message de performance #{i}")
        
        write_time = time.time() - start_time
        print(f"   Temps d'écriture: {write_time:.3f}s ({100/write_time:.1f} ops/s)")
        
        # Test de lecture
        print("\nTest de lecture (100 messages)...")
        start_time = time.time()
        
        for i in range(100):
            await redis_service.get_last_message(f"perf_conv_{i}")
        
        read_time = time.time() - start_time
        print(f"   Temps de lecture: {read_time:.3f}s ({100/read_time:.1f} ops/s)")
        
        # Nettoyage
        await redis_service.clear_all_conversations()
        
    finally:
        await redis_service.disconnect()


if __name__ == "__main__":
    print("🚀 Démarrage des tests Redis...\n")
    
    # Test de base
    success = asyncio.run(test_redis_service())
    
    if success:
        # Test de performance si les tests de base réussissent
        asyncio.run(test_redis_performance())
    
    print("\n✨ Tests terminés!")
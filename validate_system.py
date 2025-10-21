#!/usr/bin/env python3
"""
Script de validation complète pour Healthy MCP avec Redis

Valide que toutes les fonctionnalités fonctionnent correctement
avec redis-py et Python 3.13.
"""

import asyncio
import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.append(str(Path(__file__).parent))

from utils.logging_config import setup_logging, get_logger
from utils.redis_service import RedisService


async def validate_system():
    """Validation complète du système"""
    
    print("🔍 Validation Système Healthy MCP")
    print("=" * 50)
    
    # Setup logging
    setup_logging(log_level="INFO", log_dir="logs", app_name="validation")
    logger = get_logger("validation")
    
    validation_results = []
    
    # 1. Test import des modules principaux
    print("\n1. 📦 Test des imports...")
    try:
        from main import app, redis_service
        print("   ✅ main.py - OK")
        validation_results.append(("Imports", True, "Tous les modules importés"))
    except Exception as e:
        print(f"   ❌ main.py - ERREUR: {e}")
        validation_results.append(("Imports", False, str(e)))
        return validation_results
    
    # 2. Test Redis
    print("\n2. 🔄 Test du service Redis...")
    try:
        # Test de connexion
        connected = await redis_service.connect()
        if connected:
            print("   ✅ Connexion Redis - OK")
            
            # Test opérations de base
            test_conv_id = "validation_test_123"
            test_message = "Message de validation système"
            
            stored = await redis_service.store_last_message(test_conv_id, test_message)
            retrieved = await redis_service.get_last_message(test_conv_id)
            deleted = await redis_service.delete_last_message(test_conv_id)
            
            if stored and retrieved == test_message and deleted:
                print("   ✅ Opérations Redis - OK")
                validation_results.append(("Redis", True, "Toutes les opérations fonctionnent"))
            else:
                print("   ❌ Opérations Redis - ERREUR")
                validation_results.append(("Redis", False, "Erreur dans les opérations CRUD"))
            
            await redis_service.disconnect()
        else:
            print("   ⚠️  Redis indisponible (mode dégradé)")
            validation_results.append(("Redis", False, "Connexion impossible - mode dégradé"))
    except Exception as e:
        print(f"   ❌ Redis - ERREUR: {e}")
        validation_results.append(("Redis", False, str(e)))
    
    # 3. Test logging
    print("\n3. 📝 Test du système de logging...")
    try:
        test_logger = get_logger("validation.test")
        test_logger.info("Test log info")
        test_logger.warning("Test log warning") 
        test_logger.error("Test log error")
        
        # Vérifier que les fichiers de log existent
        log_files = ["healthy-mcp.log", "healthy-mcp_error.log"]
        logs_exist = all(os.path.exists(f"logs/{log_file}") for log_file in log_files)
        
        if logs_exist:
            print("   ✅ Système de logging - OK")
            validation_results.append(("Logging", True, "Fichiers de log créés"))
        else:
            print("   ❌ Fichiers de log manquants")
            validation_results.append(("Logging", False, "Fichiers de log non créés"))
    except Exception as e:
        print(f"   ❌ Logging - ERREUR: {e}")
        validation_results.append(("Logging", False, str(e)))
    
    # 4. Test health check (simulation)
    print("\n4. 🏥 Test des endpoints de santé...")
    try:
        # Test que les fonctions de santé sont disponibles
        from main import health_check, redis_stats
        print("   ✅ Endpoints de santé - OK")
        validation_results.append(("Health Endpoints", True, "Fonctions disponibles"))
    except Exception as e:
        print(f"   ❌ Health Endpoints - ERREUR: {e}")
        validation_results.append(("Health Endpoints", False, str(e)))
    
    # 5. Test compatibilité Python 3.13
    print("\n5. 🐍 Test compatibilité Python 3.13...")
    try:
        import redis.asyncio as redis
        import sys
        python_version = sys.version_info
        
        if python_version >= (3, 13):
            print(f"   ✅ Python {python_version.major}.{python_version.minor} - OK")
            print("   ✅ redis-py asyncio - OK")
            validation_results.append(("Python 3.13", True, f"Version {python_version.major}.{python_version.minor}"))
        else:
            print(f"   ⚠️  Python {python_version.major}.{python_version.minor} (< 3.13)")
            validation_results.append(("Python 3.13", False, f"Version {python_version.major}.{python_version.minor}"))
    except Exception as e:
        print(f"   ❌ Compatibilité - ERREUR: {e}")
        validation_results.append(("Python 3.13", False, str(e)))
    
    return validation_results


def print_summary(results):
    """Afficher le résumé des résultats"""
    
    print("\n" + "=" * 50)
    print("📊 RÉSUMÉ DE LA VALIDATION")
    print("=" * 50)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, message in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:<8} {test_name:<20} - {message}")
    
    print("-" * 50)
    print(f"📈 Résultat: {passed}/{total} tests réussis")
    
    if passed == total:
        print("🎉 VALIDATION COMPLÈTE RÉUSSIE!")
        print("\n🚀 Le système Healthy MCP est prêt à fonctionner avec:")
        print("   • Redis-py compatible Python 3.13")
        print("   • Système de logging complet")
        print("   • Cache Redis avec fallback DB")
        print("   • Endpoints de monitoring")
        return True
    else:
        print("⚠️  VALIDATION PARTIELLE")
        print("\nℹ️  Certains composants peuvent ne pas fonctionner correctement.")
        return False


async def main():
    """Point d'entrée principal"""
    
    try:
        results = await validate_system()
        success = print_summary(results)
        
        if success:
            print("\n💡 Pour démarrer l'application:")
            print("   python main.py")
            print("\n💡 Pour tester Redis:")
            print("   python test_redis.py")
            return 0
        else:
            print("\n🔧 Vérifiez la configuration et relancez la validation")
            return 1
            
    except Exception as e:
        print(f"\n💥 ERREUR CRITIQUE: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
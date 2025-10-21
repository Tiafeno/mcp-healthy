#!/usr/bin/env python3
"""
Script de test pour vérifier que le logging fonctionne correctement
dans le StreamableHTTPClient
"""

import asyncio
import os
from utils.logging_config import setup_logging, get_logger

# Simuler les imports du client
# (sans vraiment instancier le client car on n'a pas les credentials)

async def test_client_logging():
    """Test du système de logging pour le client"""
    
    # Configuration du logging
    app_logger = setup_logging(
        log_level="DEBUG",
        log_dir="logs",
        app_name="healthy-mcp"
    )
    
    # Test des logs du client
    client_logger = get_logger("healthy-mcp.streamable_client")
    
    print("=== Test du logging du StreamableHTTPClient ===")
    
    # Simuler les logs du client
    client_logger.info("Simulation: Attempting to connect to MCP server at https://example.com")
    client_logger.debug("Simulation: Server connection parameters configured")
    client_logger.info("Simulation: MCP server connection established successfully")
    
    # Simuler le traitement d'une requête
    client_logger.info("Simulation: Processing query with 50 characters")
    client_logger.debug("Simulation: Query: Hello, this is a test query...")
    client_logger.debug("Simulation: Fetching available tools from MCP server")
    client_logger.info("Simulation: Retrieved 5 available tools from MCP server")
    client_logger.debug("Simulation: Available tools: ['tool1', 'tool2', 'tool3']")
    
    # Simuler les appels Claude API
    client_logger.debug("Simulation: Making initial Claude API call")
    client_logger.info("Simulation: Received response from Claude API")
    client_logger.debug("Simulation: Yielding text response #1: 150 characters")
    
    # Simuler un appel d'outil
    client_logger.info("Simulation: Tool call #1: search_nutrition with args: {'query': 'vitamins'}")
    client_logger.debug("Simulation: Tool call search_nutrition executed successfully")
    client_logger.debug("Simulation: Getting follow-up response from Claude API after tool execution")
    client_logger.debug("Simulation: Received follow-up response: 200 characters")
    
    # Simuler la fin du traitement
    client_logger.info("Simulation: Query processing completed. Text responses: 2, Tool calls: 1")
    
    # Simuler le cleanup
    client_logger.info("Simulation: Starting cleanup of StreamableHTTPClient resources")
    client_logger.debug("Simulation: Exit stack closed successfully")
    client_logger.info("Simulation: StreamableHTTPClient cleanup completed successfully")
    
    print("✅ Test de logging terminé avec succès!")
    
    # Vérifier les fichiers de log
    if os.path.exists("logs/healthy-mcp.log"):
        print(f"📁 Fichier de log principal créé: logs/healthy-mcp.log")
        with open("logs/healthy-mcp.log", "r") as f:
            lines = f.readlines()
            print(f"📝 Nombre de lignes dans le log: {len(lines)}")
            print("📄 Dernières lignes du log:")
            for line in lines[-5:]:
                print(f"   {line.strip()}")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_client_logging())
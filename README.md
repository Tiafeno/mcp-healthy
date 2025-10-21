# Healthy MCP

Application FastAPI avec intégration MCP (Model Context Protocol) et cache Redis pour les conversations de santé.

## 🚀 Fonctionnalités

- **WebSocket** pour communications temps réel
- **Cache Redis** pour optimiser les performances des conversations
- **Logging complet** avec rotation automatique
- **Base de données** pour persistance des données
- **Intégration Claude AI** via MCP

## 📋 Prérequis

- Python 3.13+
- Redis Server
- PostgreSQL/SQLite

## 🛠️ Installation

1. **Cloner le projet**
   ```bash
   git clone <repo>
   cd healthy-mcp
   ```

2. **Environnement virtuel**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # ou .venv\Scripts\activate  # Windows
   ```

3. **Dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration**
   ```bash
   cp .env.example .env
   # Éditer .env avec vos paramètres
   ```

5. **Redis (avec Docker)**
   ```bash
   ./redis-manager.sh start
   ```

## 🏃‍♂️ Utilisation

### Démarrer l'application

```bash
python main.py
```

L'application sera disponible sur `http://localhost:8001`

### Endpoints disponibles

- `GET /health` - Santé du système
- `GET /redis/stats` - Statistiques Redis
- `DELETE /redis/conversation/{id}` - Supprimer cache conversation
- `WS /ws/{user_id}/conversations/{conversation_id}` - WebSocket

### Tests

```bash
# Test Redis
python test_redis.py

# Test système de logging
python test_logging.py
```

## 📁 Structure du Projet

```
healthy-mcp/
├── main.py                 # Application principale
├── models/                 # Modèles de données
├── utils/                  # Utilitaires
│   ├── logging_config.py   # Configuration logging
│   ├── redis_service.py    # Service Redis
│   └── logging_middleware.py
├── logs/                   # Fichiers de log
├── requirements.txt        # Dépendances Python
└── docker-compose.redis.yml # Redis Docker
```

## 🔧 Configuration

### Variables d'environnement

```bash
# Application
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./healthy.db
MCP_STREAMING_HTTP_URL=https://your-mcp-server.com

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_DEFAULT_TTL=3600

# API
ANTHROPIC_API_KEY=your-key-here
API_BASE_URL=https://your-api.com
```

## 📊 Redis Cache

Le service Redis stocke automatiquement :
- Derniers messages par conversation (TTL: 1h)
- Métadonnées des conversations
- Fallback automatique vers la base de données

**Compatible Python 3.13** avec [redis-py](https://github.com/redis/redis-py)

## 📝 Logging

Logs automatiques dans `logs/` :
- `healthy-mcp.log` - Logs généraux
- `healthy-mcp_error.log` - Erreurs uniquement
- `healthy-mcp_access.log` - Accès HTTP

## 🐳 Docker Redis

```bash
# Démarrer Redis + Interface Web
./redis-manager.sh start

# Interface Redis : http://localhost:8081
# Redis Server : localhost:6379
```

## 🚨 Dépannage

### Redis non disponible
L'application fonctionne sans Redis (mode dégradé avec base de données uniquement).

### Logs d'erreur
```bash
tail -f logs/healthy-mcp_error.log
```

### Test de santé
```bash
curl http://localhost:8001/health
```

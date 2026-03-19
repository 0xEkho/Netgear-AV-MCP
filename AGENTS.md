# AGENTS.md — NETGEAR AV MCP Server

> **INSTRUCTION OBLIGATOIRE** : Pour **tout prompt** dans ce projet, Copilot doit invoquer
> les **4 agents en parallèle**, sans exception. Chaque agent audite et agit sur son domaine.
> Ne jamais implémenter directement sans passer par les agents.

Ce fichier décrit les agents Copilot disponibles pour ce projet et leurs règles de collaboration.

## Vue d'ensemble du projet

Ce repo est un **serveur MCP pour switches NETGEAR Pro AV** (M4250, M4300, M4350).
- Stack : Python ≥3.10 (runtime recommandé : 3.12), `uv`, `FastMCP` (mcp>=1.2.0), `asyncssh`
- Transport : `streamable-http` (par défaut), `sse`, `stdio`
- Structure : `src/mcp_server/{server.py, tools/, ssh/}` + `tests/`
- Connectivité : SSH vers les switches NETGEAR, authentification par zone ou globale
- Sécurité : Bearer token + IP allowlist (CIDR)

## Agents disponibles

| Agent | Fichier | Responsabilité |
|-------|---------|----------------|
| `mcp-scaffolder` | `.github/agents/mcp-scaffolder.agent.md` | Configuration projet (pyproject.toml, .gitignore, .env, Dockerfile) |
| `mcp-developer` | `.github/agents/mcp-developer.agent.md` | Code source (tools, SSH client, auth, middleware) |
| `mcp-tester` | `.github/agents/mcp-tester.agent.md` | Tests pytest-asyncio |
| `mcp-documenter` | `.github/agents/mcp-documenter.agent.md` | README, docstrings, documentation |

## Règle d'or : invocation parallèle des 4 agents à chaque prompt

```
Chaque prompt → mcp-scaffolder + mcp-developer + mcp-tester + mcp-documenter (en parallèle)
```

Chaque agent vérifie son domaine même si la tâche ne le concerne pas directement.
Si rien à faire → l'agent répond "RAS" mais **doit être invoqué**.

## Flux de travail pour une nouvelle fonctionnalité

1. **mcp-scaffolder** : ajoute la dépendance si nécessaire (ex: asyncssh)
2. **mcp-developer** : implémente le tool/SSH client dans `src/`
3. **mcp-tester** : écrit les tests correspondants dans `tests/`
4. **mcp-documenter** : met à jour README.md (tableau des tools, config) et vérifie les docstrings

## Best practices MCP — règles non négociables

1. ⛔ **Jamais de `print()` sans `file=sys.stderr`** pour les serveurs STDIO
2. ⛔ **Jamais lever d'exception** depuis un outil pour signaler une erreur métier → retourner un string d'erreur
3. ✅ **Type hints** sur tous les paramètres d'outils → schéma généré automatiquement
4. ✅ **Docstrings** sur chaque primitive → description MCP générée automatiquement
5. ✅ **Variables d'environnement** pour tous les secrets (`.env`, jamais hardcodé)
6. ✅ **Tester avec MCP Inspector** : `npx @modelcontextprotocol/inspector uv run mcp-server`

## Règles spécifiques NETGEAR

- **Read-only** : aucun outil ne doit modifier la configuration du switch
- **Commandes autorisées** : uniquement `show ...` (vérification côté tool)
- **SSH** : utiliser `asyncssh`, gestion interactive du shell (enable mode, pager bypass)
- **Credentials** : résolution par zone (`NETGEAR_ZONE{X}_*`) avec fallback global

## Commandes de référence

```bash
uv sync                              # installer les dépendances
uv run mcp-server                    # lancer le serveur (streamable-http)
MCP_TRANSPORT=sse uv run mcp-server  # transport SSE
MCP_TRANSPORT=stdio uv run mcp-server # transport STDIO
uv run pytest                        # lancer les tests
uv run pytest --cov=mcp_server       # avec couverture
npx @modelcontextprotocol/inspector uv run mcp-server  # MCP Inspector
```

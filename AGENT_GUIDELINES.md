# 🤖 Guide pour les Agents de Code - Cave à Vin

Ce document décrit les conventions, procédures et bonnes pratiques à suivre lors de modifications du projet **Cave à Vin**.

---

## 📋 Table des matières

1. [Structure du projet](#structure-du-projet)
2. [Modèles de données](#modèles-de-données)
3. [API REST](#api-rest)
4. [Migrations de base de données](#migrations-de-base-de-données)
5. [Procédure de test avec Docker](#procédure-de-test-avec-docker)
6. [Vérification des fonctionnalités](#vérification-des-fonctionnalités)
7. [Conventions de code](#conventions-de-code)
8. [Checklist avant commit](#checklist-avant-commit)

---

## 📁 Structure du projet

```
cave_vin/
├── models.py              # Modèles SQLAlchemy (User, Wine, Cellar, APIToken, etc.)
├── app/
│   ├── __init__.py        # Factory Flask et configuration
│   ├── database_init.py   # Initialisation et migrations de la BDD
│   ├── exceptions.py      # Exceptions personnalisées
│   ├── field_config.py    # Configuration des champs dynamiques
│   ├── blueprints/        # Routes organisées par domaine
│   │   ├── admin.py       # Administration utilisateurs
│   │   ├── api.py         # API REST (authentification par token)
│   │   ├── api_tokens.py  # Gestion des tokens API (UI)
│   │   ├── auth.py        # Authentification
│   │   ├── categories.py  # Gestion des catégories d'alcool
│   │   ├── cellar_categories.py  # Gestion des catégories de caves
│   │   ├── cellars.py     # Gestion des caves
│   │   ├── main.py        # Routes principales (index, stats)
│   │   ├── search.py      # Recherche de bouteilles
│   │   └── wines.py       # CRUD des bouteilles
│   └── utils/             # Utilitaires (décorateurs, formatters)
├── services/
│   └── wine_info_service.py  # Service d'enrichissement IA
├── templates/             # Templates Jinja2
│   └── api_tokens/        # Templates pour la gestion des tokens API
├── static/                # CSS, JS, images
├── Dockerfile             # Image Docker de production
├── entrypoint.sh          # Script d'entrée Docker
└── requirements.txt       # Dépendances Python
```

---

## 📊 Modèles de données

### Modèles principaux

| Modèle | Description | Fichier |
|--------|-------------|---------|
| `User` | Utilisateur avec support des sous-comptes | [`models.py`](models.py:13) |
| `Cellar` | Cave de stockage avec étages | [`models.py`](models.py:90) |
| `CellarCategory` | Catégorie de cave (ex: Cave principale) | [`models.py`](models.py:76) |
| `Wine` | Bouteille avec attributs dynamiques | [`models.py`](models.py:183) |
| `AlcoholCategory` | Catégorie d'alcool (ex: Vins, Spiritueux) | [`models.py`](models.py:140) |
| `AlcoholSubcategory` | Sous-catégorie (ex: Vin rouge, Rhum) | [`models.py`](models.py:160) |
| `WineConsumption` | Historique de consommation | [`models.py`](models.py:323) |
| `WineInsight` | Informations enrichies (IA) | [`models.py`](models.py:294) |
| `APIToken` | Token d'authentification API | [`models.py`](models.py:348) |
| `APITokenUsage` | Log d'utilisation des tokens | [`models.py`](models.py:413) |

### Système de sous-comptes

Le modèle `User` supporte les sous-comptes via la colonne `parent_id`. Un sous-compte :
- Partage les ressources (caves, bouteilles) de son compte parent
- Utilise `user.owner_id` pour accéder à l'ID du propriétaire effectif
- Utilise `user.owner_account` pour accéder au compte propriétaire

```python
# Exemple d'utilisation dans un blueprint
user = current_user
owner_id = user.owner_id  # ID du parent si sous-compte, sinon propre ID
wines = Wine.query.filter_by(user_id=owner_id).all()
```

---

## 🔌 API REST

### Authentification

L'API utilise des tokens Bearer pour l'authentification. Les tokens sont générés via l'interface web dans `/api-tokens/`.

```bash
# Exemple d'appel API
curl -H "Authorization: Bearer cv_votre_token_ici" \
     http://localhost:8000/api/wines
```

### Endpoints disponibles

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/wines` | Liste des bouteilles (paginé) |
| `GET` | `/api/wines/<id>` | Détails d'une bouteille |
| `POST` | `/api/wines` | Créer une bouteille |
| `PUT/PATCH` | `/api/wines/<id>` | Modifier une bouteille |
| `DELETE` | `/api/wines/<id>` | Supprimer une bouteille |
| `POST` | `/api/wines/<id>/consume` | Consommer une bouteille |
| `GET` | `/api/cellars` | Liste des caves |
| `GET` | `/api/cellars/<id>` | Détails d'une cave avec ses bouteilles |
| `GET` | `/api/categories` | Catégories d'alcool |
| `GET` | `/api/cellar-categories` | Catégories de caves |
| `GET` | `/api/search` | Recherche multi-critères |
| `GET` | `/api/statistics` | Statistiques de la cave |
| `GET` | `/api/consumptions` | Historique des consommations |
| `GET` | `/api/collection` | Vue d'ensemble par cave |

### Paramètres de pagination

La plupart des endpoints de liste supportent :
- `limit` : Nombre max de résultats (défaut: 50-100, max: 200-500)
- `offset` : Décalage pour pagination

### Rate limiting

Chaque token a une limite de requêtes par heure (défaut: 100). Configurable par l'admin via l'interface.

### Décorateur d'authentification

Pour protéger un endpoint API, utiliser le décorateur [`@api_token_required`](app/utils/decorators.py) :

```python
from app.utils.decorators import api_token_required

@api_bp.route("/mon-endpoint")
@api_token_required
def mon_endpoint():
    user = g.api_user  # Utilisateur authentifié via le token
    owner_id = user.owner_id  # ID du propriétaire des ressources
    # ...
```

---

## 🗄️ Migrations de base de données

### Principe général

Ce projet **n'utilise pas Alembic** pour les migrations. Les migrations sont gérées manuellement dans le fichier [`app/database_init.py`](app/database_init.py) via la fonction [`apply_schema_updates()`](app/database_init.py:24).

### Ajouter une nouvelle colonne à une table existante

1. **Modifier le modèle** dans [`models.py`](models.py) :
   ```python
   class MaTable(db.Model):
       # ... colonnes existantes ...
       nouvelle_colonne = db.Column(db.String(100), nullable=True)
   ```

2. **Ajouter la migration** dans [`app/database_init.py`](app/database_init.py) dans la fonction `apply_schema_updates()` :
   ```python
   def apply_schema_updates() -> None:
       """Apply idempotent schema tweaks required by recent releases."""
       
       engine = db.engine
       inspector = inspect(engine)
       
       # Migration existante...
       
       # Migration: Add nouvelle_colonne to ma_table
       if "ma_table" in inspector.get_table_names():
           columns = {column["name"] for column in inspector.get_columns("ma_table")}
           if "nouvelle_colonne" not in columns:
               with engine.begin() as connection:
                   connection.execute(text("ALTER TABLE ma_table ADD COLUMN nouvelle_colonne VARCHAR(100)"))
   ```

### Ajouter une nouvelle table

1. **Créer le modèle** dans [`models.py`](models.py)
2. La table sera créée automatiquement par SQLAlchemy via `db.create_all()` dans [`app/__init__.py`](app/__init__.py)
3. Si des données par défaut sont nécessaires, les ajouter dans [`app/database_init.py`](app/database_init.py) dans `initialize_database()`

### Règles importantes pour les migrations

- ✅ Les migrations doivent être **idempotentes** (peuvent être exécutées plusieurs fois sans erreur)
- ✅ Toujours vérifier l'existence de la table/colonne avant modification
- ✅ Utiliser `nullable=True` pour les nouvelles colonnes sur tables existantes (évite les erreurs sur données existantes)
- ✅ Ajouter un commentaire explicatif au-dessus de chaque migration
- ❌ Ne jamais supprimer de colonnes sans migration de données préalable
- ❌ Ne pas modifier le type d'une colonne existante sans précaution

### Exemple de migration complète

```python
# Migration: Add rating column to wine table
if "wine" in inspector.get_table_names():
    columns = {column["name"] for column in inspector.get_columns("wine")}
    if "rating" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE wine ADD COLUMN rating INTEGER"))
```

---

## 🐳 Procédure de test avec Docker

### Étape 1 : Build de l'image Docker

Chaque modification doit être testée en construisant l'image Docker :

```bash
docker build --network=host -t macave:debug .
```

**Options importantes :**
- `--network=host` : Permet l'accès au réseau de l'hôte pendant le build (utile pour pip)
- `-t macave:debug` : Tag l'image pour les tests

### Étape 2 : Lancement du conteneur

```bash
docker run --rm -it \
  --name macave \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  -e DATABASE_URL=sqlite:////data/wine.db \
  -e SECRET_KEY=VotreCleSecrete \
  macave:debug
```

**Paramètres expliqués :**
| Paramètre | Description |
|-----------|-------------|
| `--rm` | Supprime le conteneur à l'arrêt |
| `-it` | Mode interactif avec terminal |
| `--name macave` | Nom du conteneur |
| `-p 8000:8000` | Expose le port 8000 |
| `-v $(pwd)/data:/data` | Monte le dossier data local |
| `-e DATABASE_URL=...` | URL de la base SQLite |
| `-e SECRET_KEY=...` | Clé secrète Flask |

### Étape 3 : Variables d'environnement optionnelles

Pour tester l'enrichissement IA :
```bash
docker run --rm -it \
  --name macave \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  -e DATABASE_URL=sqlite:////data/wine.db \
  -e SECRET_KEY=VotreCleSecrete \
  -e OPENAI_API_KEY=sk-votre-cle \
  -e OPENAI_MODEL=gpt-4o-mini \
  macave:debug
```

### Commandes utiles pendant le debug

```bash
# Voir les logs en temps réel
docker logs -f macave

# Accéder au shell du conteneur
docker exec -it macave /bin/bash

# Arrêter le conteneur
docker stop macave

# Supprimer l'image pour rebuild complet
docker rmi macave:debug
```

---

## ✅ Vérification des fonctionnalités

### Checklist de vérification obligatoire

Après chaque modification, vérifier les points suivants :

#### 1. Page d'accueil
- [ ] Accéder à `http://localhost:8000/`
- [ ] Vérifier que la page se charge sans erreur 500
- [ ] Vérifier l'affichage des statistiques (si connecté)

#### 2. Authentification
- [ ] Connexion avec admin (mot de passe affiché dans les logs au premier lancement)
- [ ] Déconnexion fonctionnelle
- [ ] Redirection vers login si non authentifié

#### 3. Fonctionnalité modifiée
- [ ] Tester le cas nominal (happy path)
- [ ] Tester les cas d'erreur (données invalides, champs manquants)
- [ ] Vérifier les messages flash (succès/erreur)
- [ ] Vérifier la persistance en base de données

#### 4. Navigation
- [ ] Tous les liens de la navbar fonctionnent
- [ ] Pas d'erreur 404 sur les routes existantes
- [ ] Retour arrière du navigateur fonctionne

### Tests spécifiques par domaine

#### Modifications sur les caves ([`app/blueprints/cellars.py`](app/blueprints/cellars.py))
- [ ] Création d'une nouvelle cave
- [ ] Modification d'une cave existante
- [ ] Suppression d'une cave (vérifier cascade sur les vins)
- [ ] Affichage de la liste des caves

#### Modifications sur les vins ([`app/blueprints/wines.py`](app/blueprints/wines.py))
- [ ] Ajout d'une bouteille
- [ ] Modification d'une bouteille
- [ ] Suppression d'une bouteille
- [ ] Consommation d'une bouteille
- [ ] Affichage du détail d'une bouteille

#### Modifications sur les catégories d'alcool ([`app/blueprints/categories.py`](app/blueprints/categories.py))
- [ ] Création de catégorie/sous-catégorie
- [ ] Modification des couleurs de badge
- [ ] Suppression (vérifier les contraintes)

#### Modifications sur les catégories de caves ([`app/blueprints/cellar_categories.py`](app/blueprints/cellar_categories.py))
- [ ] Création d'une catégorie de cave
- [ ] Modification d'une catégorie existante
- [ ] Suppression (vérifier qu'aucune cave ne l'utilise)

#### Modifications sur la recherche ([`app/blueprints/search.py`](app/blueprints/search.py))
- [ ] Recherche par type d'alcool
- [ ] Recherche par accords mets-vins
- [ ] Recherche combinée
- [ ] Affichage des résultats

#### Modifications sur l'API REST ([`app/blueprints/api.py`](app/blueprints/api.py))
- [ ] Authentification par token fonctionne
- [ ] Endpoints CRUD bouteilles (GET, POST, PUT, DELETE)
- [ ] Endpoint consommation
- [ ] Endpoints caves et catégories
- [ ] Pagination et filtres fonctionnels
- [ ] Rate limiting respecté

#### Modifications sur les tokens API ([`app/blueprints/api_tokens.py`](app/blueprints/api_tokens.py))
- [ ] Création d'un token
- [ ] Affichage du token une seule fois après création
- [ ] Révocation/réactivation d'un token
- [ ] Suppression définitive
- [ ] Vue admin : liste de tous les tokens
- [ ] Vue admin : détails d'utilisation d'un token

---

## 📝 Conventions de code

### Python

- **Style** : PEP 8
- **Type hints** : Obligatoires pour les fonctions publiques
- **Docstrings** : Format Google pour les fonctions complexes
- **Imports** : Groupés (stdlib, third-party, local) et triés alphabétiquement

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import Blueprint, render_template
from flask_login import login_required

from models import Wine, db
```

### Templates Jinja2

- **Héritage** : Tous les templates héritent de [`templates/base.html`](templates/base.html)
- **Blocs** : `title`, `content`, `scripts`
- **Macros** : Utiliser [`templates/_macros.html`](templates/_macros.html) pour les composants réutilisables

### JavaScript

- **Vanilla JS** : Pas de framework (jQuery, React, etc.)
- **Fichier principal** : [`static/js/main.js`](static/js/main.js)
- **Bootstrap 5** : Utiliser les composants Bootstrap natifs

### CSS

- **Framework** : Bootstrap 5.3
- **Personnalisations** : [`static/css/styles.css`](static/css/styles.css)
- **Classes utilitaires** : Préférer les classes Bootstrap aux CSS custom

---

## ✔️ Checklist avant commit

Avant de soumettre une modification, vérifier :

### Code
- [ ] Le code respecte les conventions PEP 8
- [ ] Les type hints sont présents
- [ ] Pas de `print()` de debug oubliés
- [ ] Les imports inutilisés sont supprimés

### Base de données
- [ ] Si nouvelle colonne : migration ajoutée dans `apply_schema_updates()`
- [ ] Si nouveau modèle : vérifié que `db.create_all()` le crée
- [ ] Migration testée sur base existante ET nouvelle base

### Docker
- [ ] `docker build --network=host -t macave:debug .` réussit
- [ ] Le conteneur démarre sans erreur
- [ ] La page d'accueil est accessible
- [ ] La fonctionnalité modifiée fonctionne

### Tests manuels
- [ ] Cas nominal testé
- [ ] Cas d'erreur testés
- [ ] Pas de régression sur les fonctionnalités existantes

---

## 🔗 Ressources utiles

- **Flask Documentation** : https://flask.palletsprojects.com/
- **SQLAlchemy Documentation** : https://docs.sqlalchemy.org/
- **Bootstrap 5** : https://getbootstrap.com/docs/5.3/
- **Jinja2** : https://jinja.palletsprojects.com/

---

## 📞 En cas de problème

### Erreur de migration
1. Vérifier la syntaxe SQL dans `apply_schema_updates()`
2. Tester sur une base vierge (supprimer `data/wine.db`)
3. Vérifier les logs Docker pour l'erreur exacte

### Erreur 500 au démarrage
1. Vérifier les imports dans les blueprints
2. Vérifier la syntaxe des modèles
3. Consulter les logs : `docker logs macave`

### Template non trouvé
1. Vérifier le nom du fichier dans `templates/`
2. Vérifier l'appel `render_template()` dans le blueprint
3. Vérifier l'héritage `{% extends "base.html" %}`

---

*Document généré pour les agents de code travaillant sur le projet Cave à Vin.*

# 🍷 Cave à Vin - Gestionnaire de Cave Personnel

Une application web Flask moderne pour gérer votre cave à vin personnelle avec enrichissement automatique des informations via IA.

## 📋 Description

**Cave à Vin** est une application web complète qui vous permet de cataloguer, organiser et gérer votre collection de vins et spiritueux. L'application utilise l'intelligence artificielle pour enrichir automatiquement les fiches de vos bouteilles avec des informations détaillées sur les domaines, les accords mets-vins, le potentiel de garde, et bien plus encore.

### ✨ Fonctionnalités principales

#### 🏠 Gestion de cave
- **Création de caves multiples** : Organisez vos bouteilles dans différentes caves
- **Configuration par étages** : Définissez la capacité de chaque étage de vos caves
- **Visualisation organisée** : Affichage des vins groupés par cave et par type d'alcool

#### 🍾 Catalogage des bouteilles
- **Ajout facile** : Interface intuitive pour ajouter vos bouteilles
- **Scanner de codes-barres** : Reconnaissance automatique via caméra (QuaggaJS)
- **Recherche automatique** : Récupération d'informations via OpenFoodFacts
- **Catégorisation avancée** : Système de catégories et sous-catégories personnalisables
- **Badges colorés** : Identification visuelle rapide par type d'alcool

#### 🤖 Enrichissement automatique par IA
- **Informations détaillées** : Génération automatique d'insights via OpenAI
- **Contenu personnalisé** : Histoire du domaine, profil aromatique, accords mets-vins
- **Potentiel de garde** : Analyse du vieillissement et recommandations de consommation
- **Estimation de prix** : Évaluation de la valeur actuelle
- **Étiquettes stylisées** : Génération d'une illustration de l'étiquette pour enrichir les fiches
- **Mise à jour** : Rafraîchissement des données à la demande

#### 🔍 Recherche et filtrage
- **Recherche multi-critères** : Par type d'alcool et accords mets-vins
- **Filtrage intelligent** : Recherche dans les informations enrichies
- **Résultats détaillés** : Aperçu des insights correspondants

#### ⏰ Gestion de la consommation
- **Vins à consommer** : Algorithme intelligent de priorisation
- **Score d'urgence** : Calcul basé sur l'âge et le potentiel de garde
- **Historique** : Suivi des bouteilles consommées avec snapshots
- **Recommandations** : Suggestions basées sur les informations d'élevage

#### 👤 Système d'authentification
- **Connexion sécurisée** : Authentification par nom d'utilisateur/mot de passe
- **Compte admin** : Création automatique avec mot de passe temporaire
- **Changement de mot de passe** : Interface dédiée pour la sécurité

## 🚀 Installation

### Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)

### Installation rapide

1. **Cloner le repository**
```bash
git clone <url-du-repository>
cd cave_vin
```

2. **Créer un environnement virtuel**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
```

3. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

4. **Lancer l'application**
```bash
python app.py
```

L'application sera accessible sur `http://localhost:5000`

### Configuration avancée

#### Variables d'environnement

Créez un fichier `.env` à la racine du projet :

```bash
# Base de données
DATABASE_URL=sqlite:///wines.db

# Sécurité
SECRET_KEY=votre_clé_secrète_très_longue_et_complexe

# Mot de passe admin par défaut (optionnel)
DEFAULT_ADMIN_PASSWORD=votre_mot_de_passe_admin

# Configuration OpenAI pour l'enrichissement IA
OPENAI_API_KEY=sk-votre_clé_api_openai
OPENAI_MODEL=gpt-4o-mini
OPENAI_SOURCE_NAME=OpenAI

# Configuration pour API compatible OpenAI (optionnel)
OPENAI_BASE_URL=https://api.openai.com/v1
```

#### Configuration de la base de données

L'application utilise SQLite par défaut, mais peut être configurée pour PostgreSQL ou MySQL :

```bash
# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost/cave_vin

# MySQL
DATABASE_URL=mysql://user:password@localhost/cave_vin
```

## 📖 Utilisation

### Premier démarrage

1. **Connexion initiale**
   - Nom d'utilisateur : `admin`
   - Mot de passe : affiché dans la console au premier lancement
   - Changez immédiatement le mot de passe temporaire

2. **Créer votre première cave**
   - Accédez à "Mes caves" → "Ajouter une cave"
   - Définissez le type (naturelle/électrique) et les capacités par étage

3. **Configurer les catégories**
   - Les catégories par défaut sont créées automatiquement
   - Personnalisez les couleurs et ajoutez vos propres sous-catégories

### Ajouter des bouteilles

#### Méthode manuelle
1. Cliquez sur "+ Ajouter" dans la navigation
2. Remplissez les informations (nom, région, cépage, année...)
3. Sélectionnez la cave et la catégorie
4. Validez pour déclencher l'enrichissement automatique

#### Avec scanner de codes-barres
1. Utilisez le bouton "Scanner" sur la page d'ajout
2. Pointez la caméra vers le code-barres
3. Les informations de base sont récupérées automatiquement
4. Complétez si nécessaire et validez

### Fonctionnalités avancées

#### Recherche intelligente
- **Par type** : Filtrez par catégorie d'alcool (vin rouge, whisky, etc.)
- **Par accords** : Recherchez "viande rouge", "poisson", "fromage"...
- **Combinée** : Utilisez les deux critères simultanément

#### Gestion de la consommation
- **Page "À consommer"** : Consultez les recommandations de dégustation
- **Score d'urgence** : Rouge (urgent), orange (prioritaire), vert (optimal)
- **Marquer comme consommé** : Bouton sur chaque fiche de vin

#### Enrichissement des données
- **Automatique** : Lancé à chaque ajout de bouteille
- **Manuel** : Bouton "Rafraîchir" sur chaque fiche
- **Contenu** : Insights sur le domaine, les accords, le potentiel de garde

## 🛠️ Architecture technique

### Stack technologique

- **Backend** : Flask 3.0+ (Python)
- **Base de données** : SQLAlchemy avec SQLite/PostgreSQL/MySQL
- **Frontend** : Bootstrap 5.3, JavaScript vanilla
- **IA** : OpenAI API (GPT-4o-mini par défaut)
- **Scanner** : QuaggaJS pour la reconnaissance de codes-barres
- **APIs externes** : OpenFoodFacts pour les données produits

### Structure du projet

```
cave_vin/
├── app.py                 # Application Flask principale
├── models.py              # Modèles de données SQLAlchemy
├── config.py              # Configuration de l'application
├── tasks.py               # Tâches d'enrichissement en arrière-plan
├── migrations.py          # Migrations de base de données
├── requirements.txt       # Dépendances Python
├── services/
│   └── wine_info_service.py  # Service d'enrichissement IA
├── templates/             # Templates Jinja2
│   ├── base.html
│   ├── index.html
│   ├── add_wine.html
│   ├── wine_detail.html
│   ├── search.html
│   ├── wines_to_consume.html
│   └── ...
├── static/
│   ├── css/
│   │   └── styles.css     # Styles personnalisés
│   └── js/
│       └── main.js        # JavaScript frontend
└── logs/                  # Logs de l'application (auto-créé)
```

### Modèles de données

#### Entités principales
- **User** : Utilisateurs de l'application
- **Cellar** : Caves avec configuration multi-étages
- **Wine** : Bouteilles avec métadonnées complètes
- **AlcoholCategory/Subcategory** : Système de catégorisation
- **WineInsight** : Informations enrichies par IA
- **WineConsumption** : Historique de consommation

#### Relations
- Une cave contient plusieurs bouteilles
- Une bouteille appartient à une sous-catégorie
- Une bouteille peut avoir plusieurs insights
- Chaque consommation garde un snapshot de la bouteille

### Système d'enrichissement

#### Processus automatique
1. **Déclenchement** : À l'ajout ou au rafraîchissement d'une bouteille
2. **Collecte** : Agrégation des métadonnées (nom, région, cépage, année...)
3. **Requête IA** : Appel à l'API OpenAI avec prompt structuré
4. **Parsing** : Extraction des insights au format JSON
5. **Stockage** : Sauvegarde en base avec pondération

#### Types d'insights générés
- **Histoire du domaine** : Informations sur le producteur
- **Profil aromatique** : Notes de dégustation et caractéristiques
- **Accords mets-vins** : Suggestions d'associations culinaires
- **Potentiel de garde** : Recommandations de vieillissement
- **Estimation de prix** : Évaluation de la valeur marchande

## 🔧 Configuration avancée

### Personnalisation des catégories

Les catégories sont entièrement personnalisables :

1. **Accès** : Menu "Catégories"
2. **Ajout** : Créez vos propres catégories et sous-catégories
3. **Couleurs** : Personnalisez les badges avec des codes couleur hexadécimaux
4. **Organisation** : Définissez l'ordre d'affichage

### Configuration OpenAI

#### Modèles supportés
- **gpt-4o-mini** (par défaut, économique)
- **gpt-4o** (plus performant)
- **gpt-3.5-turbo** (compatible)

#### APIs compatibles
L'application supporte toute API compatible OpenAI :
- OpenAI officiel
- Azure OpenAI
- APIs locales (Ollama, etc.)

#### Optimisation des coûts
- Limitation à 900 tokens par requête
- Déduplication automatique des insights
- Cache des réponses dans les logs

### Déploiement en production

#### Variables d'environnement recommandées
```bash
# Production
FLASK_ENV=production
SECRET_KEY=clé_très_sécurisée_générée_aléatoirement

# Base de données
DATABASE_URL=postgresql://user:pass@host:5432/cave_vin

# OpenAI
OPENAI_API_KEY=sk-votre_clé_production
OPENAI_MODEL=gpt-4o-mini

# Admin
DEFAULT_ADMIN_PASSWORD=mot_de_passe_sécurisé
```

#### Serveur web
```bash
# Avec Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app

# Avec uWSGI
pip install uwsgi
uwsgi --http :8000 --wsgi-file app.py --callable app
```

## 📊 Fonctionnalités détaillées

### Algorithme de recommandation de consommation

L'application calcule un **score d'urgence** pour chaque bouteille :

#### Critères d'évaluation
1. **Âge de la bouteille** : Différence entre l'année actuelle et le millésime
2. **Potentiel de garde** : Extraction depuis les insights IA (ex: "5 à 10 ans")
3. **Mots-clés d'urgence** : Détection de termes comme "maintenant", "apogée"
4. **Heuristiques par âge** : Règles par défaut selon l'ancienneté

#### Calcul du score
- **100** : À boire immédiatement (dépassé ou mots-clés urgents)
- **50-99** : Dans la fenêtre optimale de garde
- **30-49** : Approche de la maturité
- **0-29** : Peut encore attendre

#### Affichage visuel
- 🔴 **Rouge** : Score ≥ 80 (urgent)
- 🟠 **Orange** : Score 50-79 (prioritaire)  
- 🟢 **Vert** : Score 30-49 (optimal)
- ⚫ **Gris** : Score < 30 (patience)

### Scanner de codes-barres

#### Technologies utilisées
- **QuaggaJS** : Bibliothèque de reconnaissance en JavaScript
- **Formats supportés** : EAN-13, EAN-8, UPC-A, UPC-E, Code 128
- **Caméra** : Accès via WebRTC (navigateurs modernes)

#### Processus de scan
1. **Activation** : Bouton "Scanner" sur la page d'ajout
2. **Permissions** : Demande d'accès à la caméra
3. **Reconnaissance** : Détection automatique du code-barres
4. **Recherche** : Requête vers OpenFoodFacts
5. **Pré-remplissage** : Insertion automatique des données trouvées

### Système de migrations

L'application inclut un système de migrations automatiques :

#### Migrations disponibles
- **0001** : Population des étages de caves existantes
- **0002** : Création de la table des insights
- **0003** : Création de l'historique de consommation
- **0004** : Création des tables de catégories
- **0005** : Population des catégories par défaut
- **0006** : Ajout des couleurs de badges

#### Exécution
Les migrations s'exécutent automatiquement au démarrage de l'application.

## 🐛 Dépannage

### Problèmes courants

#### L'enrichissement IA ne fonctionne pas
1. Vérifiez la clé API OpenAI dans les variables d'environnement
2. Consultez les logs dans `logs/openai_responses/`
3. Testez la connectivité réseau vers l'API

#### Le scanner de codes-barres ne démarre pas
1. Vérifiez les permissions de caméra dans le navigateur
2. Utilisez HTTPS en production (requis pour WebRTC)
3. Testez sur un navigateur compatible (Chrome, Firefox, Safari)

#### Erreurs de base de données
1. Vérifiez les permissions d'écriture sur le fichier SQLite
2. Contrôlez la syntaxe de `DATABASE_URL` pour PostgreSQL/MySQL
3. Assurez-vous que les migrations ont été appliquées

### Logs et debugging

#### Activation du mode debug
```bash
export FLASK_ENV=development
python app.py
```

#### Logs OpenAI
Les requêtes et réponses sont automatiquement sauvegardées dans `logs/openai_responses/` au format JSON.

#### Logs applicatifs
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Contribution

### Structure de développement

#### Installation pour le développement
```bash
git clone <repository>
cd cave_vin
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_ENV=development
python app.py
```

#### Tests
```bash
# Tests unitaires (à implémenter)
python -m pytest tests/

# Tests d'intégration
python -m pytest tests/integration/
```

### Ajout de fonctionnalités

#### Nouveaux types d'insights
1. Modifiez le prompt dans `services/wine_info_service.py`
2. Ajustez le schéma JSON de validation
3. Mettez à jour les templates d'affichage

#### Nouvelles catégories d'alcool
1. Ajoutez les données dans `migrations.py`
2. Définissez les couleurs de badges associées
3. Créez une nouvelle migration

#### Intégrations externes
1. Créez un nouveau service dans `services/`
2. Ajoutez les appels dans `wine_info_service.py`
3. Configurez les variables d'environnement nécessaires

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 🙏 Remerciements

- **OpenAI** pour l'API de génération d'insights
- **OpenFoodFacts** pour la base de données produits
- **QuaggaJS** pour la reconnaissance de codes-barres
- **Bootstrap** pour l'interface utilisateur
- **Flask** et l'écosystème Python pour le framework

---

**Développé avec ❤️ pour les passionnés de vin et de technologie**
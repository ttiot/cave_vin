# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.4.8] - 2026-02-02

### Ajouté
- Optimisation de la minification CSS avec options mises à jour
- Amélioration de la minification JavaScript et CSS avec options avancées
- Étapes de minification JavaScript et CSS dans le workflow Docker
- Sélection de couleur de badge avec prévisualisation en direct dans les formulaires de sous-catégorie
- Menu latéral mobile avec overlay et fonctionnalité de navigation
- Fonctionnalité de mise à jour de mot de passe pour les administrateurs et amélioration de la gestion des sessions
- Gestionnaire de clic sur les cartes de vin pour naviguer vers la vue détaillée
- Gestion et validation du schéma de réponse JSON dans l'édition des prompts
- Refactorisation du processus d'import et d'enrichissement des vins avec amélioration des logs et gestion des erreurs
- Amélioration des recommandations de consommation avec scoring d'urgence et rapports détaillés
- Styles thématiques vin pour la page d'import photo

## [v2.4.7] - 2026-02-02

### Modifié
- Refactorisation de la mise en page et des styles de l'aperçu des vins pour une meilleure compacité et utilisabilité

## [v2.4.6] - 2026-02-02

### Ajouté
- Refonte de l'interface de consommation des vins avec disposition compacte des cartes et légende d'urgence améliorée
- Optimisation de la minification CSS
- Amélioration de la minification JavaScript et CSS avec options avancées
- Étapes de minification dans le workflow Docker

## [v2.4.5] - 2026-02-02

### Ajouté
- Sélection de couleur de badge avec prévisualisation en direct dans les formulaires d'ajout et d'édition de sous-catégorie
- Menu latéral mobile avec overlay et fonctionnalité de navigation
- Fonctionnalité de mise à jour de mot de passe pour les administrateurs et amélioration de la gestion des sessions

## [v2.4.4] - 2026-01-30

### Ajouté
- Gestionnaire de clic sur les cartes de vin pour naviguer vers la vue détaillée

## [v2.4.3] - 2026-01-30

### Ajouté
- Gestion et validation du schéma de réponse JSON dans l'édition des prompts

## [v2.4.2] - 2026-01-30

### Modifié
- Refactorisation du processus d'import et d'enrichissement des vins avec amélioration des logs et gestion des erreurs

## [v2.4.1] - 2026-01-30

### Ajouté
- Amélioration des recommandations de consommation avec scoring d'urgence et rapports détaillés
- Styles thématiques vin pour la page d'import photo et composants

## [v2.4.0] - 2026-01-30

### Ajouté
- Templates pour les logs utilisateur, consommation et paramètres OpenAI
- Amélioration de la fonctionnalité de filtrage des vins avec chips interactifs et boutons de réinitialisation
- Service de détection de bouteilles et fonctionnalité d'analyse d'images
- Refactorisation des imports de modèles pour plus de clarté

## [v2.3.0] - 2026-01-28

### Ajouté
- Fonctionnalité d'accord mets-vins (wine pairing)
- Tâches planifiées pour les rapports hebdomadaires

## [v2.2.0] - 2026-01-28

### Ajouté
- Fonctionnalité email et configuration SMTP

## [v2.1.0] - 2026-01-28

### Ajouté
- Amélioration du design général et de l'UI/UX
- Bouton de notification compact dans la barre de navigation
- Protection CSRF pour le formulaire de notification
- Notifications push pour les actions sur la cave
- Service worker pour la fonctionnalité PWA
- Amélioration de la gestion des abonnements push

### Modifié
- Suppression de l'exemption CSRF pour la connexion
- Configuration du niveau de protection de session
- Amélioration de la protection CSRF et des logs
- Amélioration du support proxy et de la sécurité des cookies
- Amélioration de la stratégie de cache du service worker
- Amélioration de la gestion et fiabilité des notifications push

## [v2.0.1] - 2026-01-27

### Corrigé
- Erreurs de contenu mixte dans Swagger UI

## [v2.0.0] - 2026-01-27

### Ajouté
- Notifications push et documentation API
- API, webhooks, fonctionnalités d'administration
- Fonctionnalité de sous-comptes
- Blueprint API avec authentification par token
- Barre de recherche responsive
- Amélioration de la gestion des vins et de l'UI

### Modifié
- Optimisation de la construction de l'image Docker
- Correction du cache apt pour les builds Docker
- Optimisation du cache des couches Docker

## [v1.0.5] - 2025-11-14

### Ajouté
- Commentaires pour la sortie de stock des vins
- Mise à jour CSP pour inclure unpkg.com
- Gestion des valeurs décimales pour les champs personnalisés

### Corrigé
- Assurance de l'existence de la colonne de commentaire de consommation

## [v1.0.4] - 2025-10-20

### Ajouté
- Protection CSRF pour les formulaires

### Corrigé
- Autorisation des scripts

## [v1.0.3] - 2025-10-20

### Modifié
- Mise à jour du workflow de build de l'image Docker
- Autorisation des pushes vers les branches feat dans le workflow Docker
- Remplacement du runner de migration par l'initialiseur de base de données
- Mise à jour des workflows

## [v1.0.2] - 2025-10-20

### Corrigé
- Migration des catégories par défaut avec couleurs de badge

## [v1.0.1] - 2025-10-20

### Corrigé
- Ordre des migrations
- Erreur dans les migrations tentant d'insérer une colonne existante

## [v1.0.0] - 2025-10-20

### Ajouté
- Support multi-utilisateurs avec contrôles administrateur
- Possibilité pour les administrateurs de supprimer des utilisateurs
- Dockerfile
- Gestion des images d'étiquettes de vin
- Tokens CSRF pour les formulaires d'action sur les vins
- Génération et stockage d'étiquettes de vin stylisées
- Aperçu moderne de la cave pour tous les alcools
- Coordonnées de pays supplémentaires
- Tableau de bord statistiques complet
- Gestion flexible des champs avec stockage JSON
- Champs de bouteille dynamiques configurables par catégorie
- Interface de gestion des exigences de champs d'alcool
- Champs de bouteille configurables et exigence de volume
- Protection CSRF et sécurisation des redirections
- Fonctionnalité d'édition de cave
- Badges de catégorie contextuels
- Fonctionnalité d'urgence de consommation des vins
- Recherche multi-critères des vins
- Catégories et sous-catégories d'alcool
- Amélioration de la récupération d'informations sur les vins avec OpenAI
- Actions de cycle de vie des bouteilles et suivi de l'historique
- Enrichissement automatique des vins et vues détaillées
- Runner de migration de schéma au démarrage
- Configuration de la capacité des bouteilles par étage de cave
- Gestion des caves et liaison des vins aux caves
- Fonctionnalités de base initiales

### Modifié
- Assouplissement CSP pour les assets CDN
- Atténuation des principales découvertes de sécurité
- Refactorisation du type de cave pour utiliser les catégories
- Gestion des couleurs de badge des sous-catégories en base de données
- Amélioration de l'affichage des vins par cave et sous-catégorie
- Refactorisation du stockage des insights de vin pour assurer la cohérence des données
- Simplification de l'intégration OpenAI
- Passage au client Python OpenAI officiel

### Corrigé
- Correction de la redirection de connexion et de la persistance de session
- Hashes SRI pour les assets du tableau de bord statistiques
- Migration SQLite pour les timestamps des vins
- wsgi.py manquant
- Entrypoint manquant

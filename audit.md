# Introduction

Objectif confirmé : auditer l’application Flask afin d’identifier les vulnérabilités critiques et proposer un plan de durcissement conforme aux bonnes pratiques OWASP. Revue statique ciblée des blueprints, configuration Flask, templates et services pour établir un plan d’action priorisé.

# Méthodologie

- Cartographie rapide de la structure (blueprints, modèles, configuration, tâches asynchrones).
- Lecture ciblée des points sensibles : authentification, gestion des sessions, rendu des templates, intégrations externes et hooks d’initialisation.
- Analyse croisée avec les risques OWASP (A01–A10) pour classifier criticité et impacts.
- Consolidation des écarts en mesures correctives ordonnées par priorité.

# Résultats

- **Critique – XSS stockée via contenus d’insights externes** : les textes d’`insight.content` sont rendus avec `|safe`, permettant l’injection de HTML/JS depuis OpenAI ou toute source distante, menant à une compromission complète de session (OWASP A03).
- **Critique – Mode debug activé par défaut** : `app.run(debug=True)` expose le debugger Werkzeug en production, ouvrant la porte à l’exécution de code arbitraire (OWASP A05).
- **Élevée – Mot de passe administrateur généré/loggé en clair** : lors de l’initialisation, le mot de passe est affiché dans les logs applicatifs et console, facilitant la compromission du compte root (OWASP A02).
- **Élevée – Cookies de session non durcis** : la configuration ne force aucun flag `Secure`, `HttpOnly` ni `SameSite`, laissant les cookies Flask/remember accessibles ou interceptables (OWASP A02/A07).
- **Élevée – Session persistante imposée** : `login_user(..., remember=True)` active systématiquement un cookie longue durée sans consentement ni rotation, augmentant la surface de vol de session (OWASP A07).
- **Élevée – Journalisation intégrale des prompts OpenAI** : le service écrit sur disque prompts et réponses potentiellement sensibles, sans contrôle d’accès ni purge, exposant des données réglementées (OWASP A09).
- **Moyenne – Jetons CSRF sans expiration** : `WTF_CSRF_TIME_LIMIT = None` laisse des tokens utilisables indéfiniment, augmentant l’impact d’une fuite (OWASP A05).
- **Moyenne – Absence de mécanismes anti brute-force/monitoring** : la route `/login` n’implémente ni limitation de débit, ni journalisation de tentatives suspectes (OWASP A07).
- **Moyenne – Liens de sources externes non filtrés** : les URLs d’insights sont rendues directement en attribut `href`, ouvrant le champ à des liens malveillants (`javascript:`, phishing) (OWASP A03/A04).

# Plan d’action priorisé

## Critique (≤24 h)

1. **Neutraliser la XSS stockée**
   - Supprimer `|safe` dans `wine_detail.html` et encoder systématiquement les contenus d’insights.
   - Ajouter une étape de normalisation côté serveur : nettoyer/filtrer `insight.content` avant stockage (HTML sanitizer whitelist).
2. **Désactiver le mode debug en production**
   - Paramétrer `FLASK_ENV`/`DEBUG` via variables d’environnement et faire dépendre `app.run` de cette configuration.
   - Valider que le serveur de production utilise un WSGI (gunicorn/uwsgi) sans debugger.

## Élevée (≤1 semaine)

3. **Sécuriser la création du compte administrateur**
   - Retirer toute impression du mot de passe, remplacer par une journalisation chiffrée ou un canal de provisionnement sécurisé.
   - Forcer le changement de mot de passe à la première connexion via workflow contrôlé et alertes de conformité.
4. **Durcir les cookies et la configuration de session**
   - Définir explicitement `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE='Lax/Strict'`, ainsi que les équivalents pour le cookie remember.
   - Activer la rotation périodique des cookies et la régénération de session après authentification.
5. **Rendre l’option “Se souvenir de moi” explicite et sécurisée**
   - Retirer `remember=True` par défaut, ajouter une case à cocher contrôlée par l’utilisateur et appliquer un TTL court.
   - Régénérer la session lors de la déconnexion pour invalider le token remember existant.
6. **Protéger les logs sensibles**
   - Supprimer tous les logs openAI

## Moyenne (≤4 semaines)

7. **Renforcer la protection CSRF et l’anti-automatisation**
   - Réintroduire une durée de vie raisonnable pour les tokens CSRF et régénération après authentification sensible.
   - Mettre en place Flask-Limiter (ou équivalent reverse proxy) sur `/login`, `/change_password` et routes critiques avec alerting SIEM.
8. **Valider et filtrer les URLs externes affichées**
   - Mettre en place un validateur côté serveur pour n’autoriser que les schémas `https/http` et réécrire les liens suspects (safe redirect).
   - Ajouter une bannière de mise en garde et l’attribut `rel="noopener noreferrer nofollow"` systématique.
9. **Durcir la posture globale**
   - Ajouter des en-têtes de sécurité (CSP stricte, HSTS, X-Frame-Options) via un middleware (Flask-Talisman).
   - Étendre la surveillance : journalisation structurée des tentatives d’accès, alertes sur échecs répétés, intégration SOC.

# Hypothèses

- L’application est déployée sur Internet et accessible par des utilisateurs externes ; aucune protection périmétrique additionnelle n’est présumée.
- Les journaux applicatifs (stdout, fichiers `logs/`) sont consultables par plusieurs opérateurs ; la fuite d’un secret dans ces canaux est considérée comme compromettante.
- L’environnement cible supporte les dépendances supplémentaires nécessaires (Flask-Talisman, Flask-Limiter ou équivalent) pour le durcissement recommandé.

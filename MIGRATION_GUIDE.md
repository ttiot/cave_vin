# Guide de Migration - Gestion Flexible des Champs

## Vue d'ensemble

Cette migration permet de modifier les champs de bouteilles (`BottleFieldDefinition`) après leur création, en stockant toutes les données dans le champ JSON `extra_attributes` au lieu de colonnes dédiées.

## Changements principaux

### 1. Stockage unifié des données

**Avant :** Les champs par défaut (region, grape, year, volume_ml, description) étaient stockés dans des colonnes dédiées de la table `Wine`, tandis que les champs personnalisés étaient dans `extra_attributes`.

**Après :** Tous les champs sont maintenant stockés dans `extra_attributes` (JSON), offrant une flexibilité totale.

### 2. Nouvelles fonctionnalités

- ✅ **Édition des champs** : Vous pouvez maintenant modifier n'importe quel champ (label, type, placeholder, etc.)
- ✅ **Suppression des champs personnalisés** : Les champs non-builtin peuvent être supprimés
- ✅ **Renommage des champs** : Le changement de libellé met à jour automatiquement les données existantes
- ✅ **Cohérence** : Tous les champs sont traités de la même manière

## Étapes de migration

### 1. Sauvegarder la base de données

```bash
# Créer une sauvegarde avant toute migration
cp cave_vin.db cave_vin.db.backup
```

### 2. Exécuter le script de migration

```bash
python migrate_to_json_fields.py
```

Ce script va :
- Copier toutes les valeurs des colonnes dédiées vers `extra_attributes`
- Afficher un résumé des données migrées
- Conserver les anciennes colonnes (pour rollback si nécessaire)

### 3. Vérifier la migration

Après la migration, vérifiez que :
- Toutes les bouteilles affichent correctement leurs informations
- Les formulaires d'ajout/édition fonctionnent
- La recherche fonctionne toujours

### 4. (Optionnel) Supprimer les anciennes colonnes

Une fois la migration validée, vous pouvez supprimer les colonnes obsolètes :

```python
# Dans migrations.py ou via Alembic
def upgrade():
    with op.batch_alter_table('wine') as batch_op:
        batch_op.drop_column('region')
        batch_op.drop_column('grape')
        batch_op.drop_column('year')
        batch_op.drop_column('volume_ml')
        batch_op.drop_column('description')
```

## Utilisation des nouvelles fonctionnalités

### Modifier un champ

1. Aller dans **Catégories** → **Configuration des champs**
2. Cliquer sur l'icône ✏️ à côté du champ à modifier
3. Modifier les propriétés souhaitées
4. Enregistrer

### Supprimer un champ personnalisé

1. Éditer le champ
2. Descendre jusqu'à la "Zone dangereuse"
3. Confirmer la suppression

⚠️ **Attention** : La suppression d'un champ supprime toutes les données associées dans les bouteilles existantes.

### Ajouter un nouveau champ

1. Aller dans **Catégories** → **Configuration des champs**
2. Utiliser le formulaire "Ajouter un nouveau champ"
3. Définir le libellé, type, portée, etc.
4. Le champ sera immédiatement disponible

## Fichiers modifiés

- [`app/field_config.py`](app/field_config.py) : Suppression du mapping FIELD_STORAGE_MAP
- [`app/blueprints/wines.py`](app/blueprints/wines.py) : Utilisation exclusive de extra_attributes
- [`app/blueprints/categories.py`](app/blueprints/categories.py) : Ajout des routes edit_field et delete_field
- [`templates/field_requirements.html`](templates/field_requirements.html) : Ajout des boutons d'édition
- [`templates/edit_field.html`](templates/edit_field.html) : Nouveau template pour l'édition
- [`migrate_to_json_fields.py`](migrate_to_json_fields.py) : Script de migration

## Rollback

Si vous devez revenir en arrière :

1. Restaurer la sauvegarde de la base de données
2. Restaurer les fichiers depuis Git :
   ```bash
   git checkout HEAD -- app/field_config.py app/blueprints/wines.py app/blueprints/categories.py
   ```

## Notes techniques

### Compatibilité

- Les champs `is_builtin=True` (region, grape, year, volume_ml, description) ne peuvent pas être supprimés
- Le renommage d'un champ builtin ne change que le label, pas le nom interne
- Les champs personnalisés peuvent être renommés, ce qui met à jour automatiquement toutes les bouteilles

### Performance

- L'utilisation de JSON pour le stockage n'impacte pas significativement les performances
- Les index sur les colonnes dédiées ne sont plus nécessaires
- La recherche full-text fonctionne toujours via le champ JSON

## Support

En cas de problème, vérifiez :
1. Les logs de l'application
2. Que la migration s'est bien exécutée
3. Que vous avez une sauvegarde de la base de données
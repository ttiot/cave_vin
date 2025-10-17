"""
Script de migration pour déplacer tous les champs de Wine vers extra_attributes.
Ce script migre les colonnes region, grape, year, volume_ml, et description
vers le champ JSON extra_attributes pour une gestion unifiée.
"""

import sqlite3
import json

def migrate_fields_to_json():
    """Migrer tous les champs vers extra_attributes."""
    
    # Connexion à la base de données
    db_path = 'instance/wines.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Connexion à la base de données : {db_path}")
    print("Début de la migration des champs vers JSON...\n")
    
    # Champs à migrer
    fields_to_migrate = ['region', 'grape', 'year', 'volume_ml', 'description']
    
    # Récupérer toutes les bouteilles
    cursor.execute('SELECT id, region, grape, year, volume_ml, description, extra_attributes FROM wine')
    wines = cursor.fetchall()
    
    migrated_count = 0
    updated_count = 0
    
    for wine in wines:
        wine_id, region, grape, year, volume_ml, description, extra_attributes_json = wine
        
        # Parser les extra_attributes existants
        try:
            extra_attributes = json.loads(extra_attributes_json) if extra_attributes_json else {}
        except (json.JSONDecodeError, TypeError):
            extra_attributes = {}
        
        # Migrer chaque champ s'il a une valeur
        has_changes = False
        for field_name, value in zip(fields_to_migrate, [region, grape, year, volume_ml, description]):
            if value is not None and field_name not in extra_attributes:
                extra_attributes[field_name] = value
                print(f"  Wine {wine_id}: {field_name} = {value}")
                has_changes = True
        
        # Mettre à jour la base de données si nécessaire
        if has_changes:
            cursor.execute(
                'UPDATE wine SET extra_attributes = ? WHERE id = ?',
                (json.dumps(extra_attributes), wine_id)
            )
            updated_count += 1
        
        migrated_count += 1
    
    # Sauvegarder les changements
    conn.commit()
    conn.close()
    
    print(f"\n=== Résumé de la migration ===")
    print(f"Bouteilles analysées : {migrated_count}")
    print(f"Bouteilles mises à jour : {updated_count}")
    print(f"\nLes anciennes colonnes peuvent maintenant être supprimées de la base de données.")
    print(f"\nATTENTION : Avant de supprimer les colonnes, assurez-vous que :")
    print(f"  1. La migration s'est bien déroulée")
    print(f"  2. Vous avez une sauvegarde de la base de données")
    print(f"  3. Le code a été mis à jour pour utiliser extra_attributes")

if __name__ == '__main__':
    migrate_fields_to_json()
"""
Script pour supprimer les anciennes colonnes de la table Wine.
ATTENTION : Ce script modifie définitivement la structure de la base de données.
Assurez-vous d'avoir une sauvegarde avant de l'exécuter.
"""

import sqlite3
import shutil
from datetime import datetime

def backup_database(db_path):
    """Créer une sauvegarde de la base de données."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"✓ Sauvegarde créée : {backup_path}")
    return backup_path

def drop_old_columns():
    """Supprimer les anciennes colonnes de la table Wine."""
    
    db_path = 'instance/wines.db'
    
    # Créer une sauvegarde
    print("Création d'une sauvegarde de la base de données...")
    backup_path = backup_database(db_path)
    
    # Connexion à la base de données
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\nSuppression des anciennes colonnes...")
    
    try:
        # SQLite ne supporte pas DROP COLUMN directement
        # Il faut recréer la table sans ces colonnes
        
        # 1. Créer une nouvelle table sans les colonnes obsolètes
        cursor.execute('''
            CREATE TABLE wine_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                barcode VARCHAR(20) UNIQUE,
                extra_attributes JSON NOT NULL DEFAULT '{}',
                image_url VARCHAR(255),
                label_image TEXT,
                quantity INTEGER DEFAULT 1,
                cellar_id INTEGER NOT NULL,
                subcategory_id INTEGER,
                FOREIGN KEY (cellar_id) REFERENCES cellar(id),
                FOREIGN KEY (subcategory_id) REFERENCES alcohol_subcategory(id)
            )
        ''')
        print("✓ Nouvelle table créée")
        
        # 2. Copier les données
        cursor.execute('''
            INSERT INTO wine_new (id, name, barcode, extra_attributes, image_url, label_image, quantity, cellar_id, subcategory_id)
            SELECT id, name, barcode, extra_attributes, image_url, label_image, quantity, cellar_id, subcategory_id
            FROM wine
        ''')
        print("✓ Données copiées")
        
        # 3. Supprimer l'ancienne table
        cursor.execute('DROP TABLE wine')
        print("✓ Ancienne table supprimée")
        
        # 4. Renommer la nouvelle table
        cursor.execute('ALTER TABLE wine_new RENAME TO wine')
        print("✓ Nouvelle table renommée")
        
        # Sauvegarder les changements
        conn.commit()
        
        print("\n=== Suppression réussie ===")
        print("Les colonnes suivantes ont été supprimées :")
        print("  - region")
        print("  - grape")
        print("  - year")
        print("  - volume_ml")
        print("  - description")
        print(f"\nSauvegarde disponible : {backup_path}")
        
    except Exception as e:
        print(f"\n❌ Erreur lors de la suppression : {e}")
        print(f"La base de données n'a pas été modifiée.")
        print(f"Vous pouvez restaurer depuis : {backup_path}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 70)
    print("SUPPRESSION DES ANCIENNES COLONNES DE LA TABLE WINE")
    print("=" * 70)
    print("\nCe script va supprimer définitivement les colonnes :")
    print("  - region, grape, year, volume_ml, description")
    print("\nUne sauvegarde sera créée automatiquement.")
    
    response = input("\nVoulez-vous continuer ? (oui/non) : ").strip().lower()
    
    if response in ['oui', 'o', 'yes', 'y']:
        drop_old_columns()
    else:
        print("\nOpération annulée.")
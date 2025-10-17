"""
Script pour vérifier l'état de la migration des champs vers extra_attributes.
"""

from models import db, Wine
from app import create_app

def check_migration_status():
    """Vérifier l'état de la migration."""
    app = create_app()
    
    with app.app_context():
        print("=== Vérification de la migration ===\n")
        
        wines = Wine.query.limit(10).all()
        
        if not wines:
            print("Aucune bouteille trouvée dans la base de données.")
            return
        
        print(f"Nombre de bouteilles à vérifier : {len(wines)}\n")
        
        for wine in wines:
            print(f"--- Bouteille ID {wine.id}: {wine.name} ---")
            print(f"  Colonnes dédiées:")
            print(f"    - region: {wine.region}")
            print(f"    - grape: {wine.grape}")
            print(f"    - year: {wine.year}")
            print(f"    - volume_ml: {wine.volume_ml}")
            print(f"    - description: {wine.description[:50] if wine.description else None}...")
            
            print(f"  extra_attributes: {wine.extra_attributes}")
            print()
        
        # Statistiques
        total_wines = Wine.query.count()
        wines_with_extras = Wine.query.filter(Wine.extra_attributes != None).filter(Wine.extra_attributes != {}).count()
        
        print(f"\n=== Statistiques ===")
        print(f"Total de bouteilles : {total_wines}")
        print(f"Bouteilles avec extra_attributes : {wines_with_extras}")
        print(f"Bouteilles sans extra_attributes : {total_wines - wines_with_extras}")

if __name__ == '__main__':
    check_migration_status()
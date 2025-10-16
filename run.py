"""Point d'entrée principal de l'application Cave à Vin."""

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
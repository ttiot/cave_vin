"""Point d'entrée principal de l'application Cave à Vin."""

import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    debug_env = os.environ.get('FLASK_DEBUG', '')
    debug = debug_env.lower() in {'1', 'true', 'yes', 'on'}
    app.run(debug=debug)

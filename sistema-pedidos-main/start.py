from app import app
from db import inicializar_db

if __name__ == "__main__":
    inicializar_db()
    app.run()
"""Repo-root entrypoint for the Ring CAD Flask app (RNG-2)."""
from ringcad.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()

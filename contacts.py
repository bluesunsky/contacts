"""Point d'entrée du carnet de contacts.

    python contacts.py            ouvre la fenêtre (PyQt6)
    python contacts.py --console  utilise le terminal

Le code est dans le paquet carnet : voir carnet/__init__.py pour son
organisation.
"""

import sys
from pathlib import Path

# Rend le paquet carnet importable même quand Python n'ajoute pas le dossier
# du script au chemin d'import (mode isolé -I, lancement via un raccourci...).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carnet import lancer  # noqa: E402

if __name__ == "__main__":
    sys.exit(lancer())

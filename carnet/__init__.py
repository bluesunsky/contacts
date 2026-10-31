"""Carnet de contacts.

Organisation en couches, de la plus basse à la plus haute :

- modele   : structure des fiches, validation, vue d'affichage (aucune E/S)
- stockage : lecture et écriture du fichier JSON
- service  : classe Carnet, point d'entrée unique pour toute interface
- cli      : interface en ligne de commande
- gui      : interface graphique PyQt6
- lanceur  : choix de l'interface selon l'option --console

Les interfaces utilisent uniquement Carnet et les types du module modele.
Le mode terminal fonctionne sans PyQt6. phonenumbers est nécessaire dans
tous les modes, pour valider et mettre au format les numéros de téléphone.

Les noms exportés ci-dessous sont chargés à la demande : importer le paquet
ne requiert aucune dépendance, ce qui permet à lancer() d'expliquer
l'absence de phonenumbers au lieu d'afficher une trace d'erreur.
"""

from __future__ import annotations

import importlib
import sys

MESSAGE_PHONENUMBERS_ABSENT = (
    "Le carnet nécessite le paquet phonenumbers, qui n'est pas installé.\n"
    "Installez les dépendances avec : pip install -r requirements.txt"
)

_EXPORTS = {
    "Email": "modele",
    "SaisieContact": "modele",
    "Telephone": "modele",
    "VueContact": "modele",
    "Carnet": "service",
    "ContactExistant": "service",
    "ContactIntrouvable": "service",
    "DonneesInvalides": "service",
    "ErreurCarnet": "service",
    "FICHIER_CONTACTS": "stockage",
    "ErreurChargement": "stockage",
}

__all__ = sorted(_EXPORTS) + ["lancer"]


def __getattr__(nom: str):
    if nom in _EXPORTS:
        module = importlib.import_module(f".{_EXPORTS[nom]}", __name__)
        return getattr(module, nom)
    raise AttributeError(f"module {__name__!r} has no attribute {nom!r}")


def lancer(argv: list[str] | None = None) -> int:
    """Point d'entrée commun de contacts.py et de python -m carnet."""
    try:
        from .lanceur import main
    except ModuleNotFoundError as e:
        if e.name != "phonenumbers":
            raise
        if sys.stderr is not None:
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            print(MESSAGE_PHONENUMBERS_ABSENT, file=sys.stderr)
        return 1
    return main(argv)

"""Choix de l'interface au lancement : fenêtre par défaut, terminal avec --console."""

from __future__ import annotations

import argparse
import importlib.util
import sys

from .cli import forcer_utf8

MESSAGE_PYQT_ABSENT = (
    "L'interface graphique nécessite PyQt6, qui n'est pas installé.\n"
    "Installez-le avec : pip install -r requirements.txt\n"
    "ou lancez le mode terminal avec l'option --console."
)
MESSAGE_PYQT_INUTILISABLE = (
    "PyQt6 est installé mais n'a pas pu être chargé : {erreur}\n"
    "Réinstallez-le avec : pip install --force-reinstall -r requirements.txt\n"
    "ou lancez le mode terminal avec l'option --console."
)


def analyser_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="contacts",
        description="Gestionnaire de contacts. Ouvre une fenêtre par défaut.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="utiliser l'interface en ligne de commande au lieu de la fenêtre",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Avant tout message, y compris celui d'argparse ou de PyQt6 absent.
    forcer_utf8()
    arguments = analyser_arguments(argv)

    if arguments.console:
        from .cli import main as lancer
    else:
        try:
            from .gui import main as lancer
        except ImportError as e:
            module = e.name or ""
            if module != "PyQt6" and not module.startswith("PyQt6."):
                raise  # erreur dans notre propre code : ne pas la masquer
            message = (
                MESSAGE_PYQT_ABSENT if importlib.util.find_spec("PyQt6") is None
                else MESSAGE_PYQT_INUTILISABLE.format(erreur=e)
            )
            print(message, file=sys.stderr)
            return 1

    return lancer()

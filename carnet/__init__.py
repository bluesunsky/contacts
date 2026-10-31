"""Carnet de contacts.

Organisation en couches, de la plus basse à la plus haute :

- modele   : structure des fiches, validation, vue d'affichage (aucune E/S)
- stockage : lecture et écriture du fichier JSON
- service  : classe Carnet, point d'entrée unique pour toute interface
- cli      : interface en ligne de commande
- gui      : interface graphique PyQt6
- lanceur  : choix de l'interface selon l'option --console

Les interfaces utilisent uniquement Carnet et les types du module modele.
Ce paquet n'importe pas PyQt6 : le mode terminal fonctionne sans lui.
"""

from .modele import Email, SaisieContact, Telephone, VueContact
from .service import (
    Carnet,
    ContactExistant,
    ContactIntrouvable,
    DonneesInvalides,
    ErreurCarnet,
)
from .stockage import FICHIER_CONTACTS, ErreurChargement

__all__ = [
    "Carnet",
    "ContactExistant",
    "ContactIntrouvable",
    "DonneesInvalides",
    "Email",
    "ErreurCarnet",
    "ErreurChargement",
    "FICHIER_CONTACTS",
    "SaisieContact",
    "Telephone",
    "VueContact",
]

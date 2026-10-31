"""Carnet de contacts.

Organisation en couches, de la plus basse à la plus haute :

- modele   : structure des fiches, validation, vue d'affichage (aucune E/S)
- stockage : lecture et écriture du fichier JSON
- service  : classe Carnet, point d'entrée unique pour toute interface
- cli      : interface en ligne de commande

Une interface graphique doit utiliser uniquement Carnet et les types du
module modele, jamais cli.
"""

from .modele import Email, NouveauContact, Telephone, VueContact
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
    "NouveauContact",
    "Telephone",
    "VueContact",
]

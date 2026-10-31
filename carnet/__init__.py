"""Carnet de contacts.

Organisation en couches, de la plus basse à la plus haute :

- modele   : structure des fiches, validation, vue d'affichage (aucune E/S)
- stockage : lecture et écriture du fichier JSON
- service  : classe Carnet, point d'entrée unique pour toute interface
- cli      : interface en ligne de commande
- gui      : interface graphique PyQt6
- lanceur  : choix de l'interface selon l'option --console

Les interfaces utilisent uniquement Carnet et les types du module modele.
Ce paquet n'importe pas PyQt6 : le mode terminal fonctionne sans lui. Il
nécessite en revanche phonenumbers pour valider et mettre au format les
numéros de téléphone.
"""

MESSAGE_PHONENUMBERS_ABSENT = (
    "Le carnet nécessite le paquet phonenumbers, qui n'est pas installé.\n"
    "Installez les dépendances avec : pip install -r requirements.txt"
)

try:
    import phonenumbers  # noqa: F401
except ModuleNotFoundError as e:
    if e.name != "phonenumbers":
        raise
    raise ModuleNotFoundError(MESSAGE_PHONENUMBERS_ABSENT, name="phonenumbers") from None

from .modele import Email, SaisieContact, Telephone, VueContact  # noqa: E402
from .service import (  # noqa: E402
    Carnet,
    ContactExistant,
    ContactIntrouvable,
    DonneesInvalides,
    ErreurCarnet,
)
from .stockage import FICHIER_CONTACTS, ErreurChargement  # noqa: E402

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

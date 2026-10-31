"""Lecture et écriture du carnet dans un fichier JSON."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .modele import Contacts

# Le fichier est ancré sur le dossier du projet, pas sur le répertoire
# courant, pour que le même carnet soit utilisé d'où que l'on lance le
# programme.
FICHIER_CONTACTS = Path(__file__).resolve().parent.parent / "contacts.json"


class ErreurChargement(Exception):
    """Le fichier de contacts est du JSON valide mais n'a pas la forme attendue."""


@dataclass(frozen=True)
class ResultatChargement:
    contacts: Contacts
    # Renseignés si le fichier était illisible et a été renommé.
    fichier_mis_de_cote: Path | None = None
    detail_erreur: str | None = None


def charger_contacts(chemin: Path = FICHIER_CONTACTS) -> ResultatChargement:
    """Charge le carnet depuis le fichier JSON.

    Un fichier absent donne un carnet vide. Un fichier illisible est renommé
    en copie horodatée avant de repartir d'un carnet vide, afin de ne jamais
    l'écraser. Un fichier de mauvaise forme lève ErreurChargement sans être
    modifié.
    """
    if not chemin.exists():
        return ResultatChargement({})

    try:
        with open(chemin, "r", encoding="utf-8") as f:
            donnees = json.load(f)
    except json.JSONDecodeError as e:
        return ResultatChargement(
            {},
            fichier_mis_de_cote=_mettre_de_cote(chemin),
            detail_erreur=f"{e.msg}, ligne {e.lineno}",
        )

    _verifier_forme(donnees, chemin)
    return ResultatChargement(donnees)


def _mettre_de_cote(chemin: Path) -> Path:
    """Renomme un fichier abîmé en copie horodatée et retourne son chemin."""
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    sauvegarde = chemin.with_name(f"{chemin.stem}.{horodatage}.bak")
    os.replace(chemin, sauvegarde)
    return sauvegarde


def _verifier_forme(donnees: object, chemin: Path) -> None:
    if not isinstance(donnees, dict):
        raise ErreurChargement(
            f"{chemin.name} doit contenir un objet JSON (dictionnaire nom -> fiche), "
            f"pas {type(donnees).__name__}."
        )
    for nom, fiche in donnees.items():
        if not isinstance(fiche, dict):
            raise ErreurChargement(
                f"La fiche '{nom}' dans {chemin.name} doit être un objet JSON, "
                f"pas {type(fiche).__name__}."
            )


def sauvegarder_contacts(contacts: Contacts, chemin: Path = FICHIER_CONTACTS) -> None:
    """Écrit le carnet de façon atomique.

    Le contenu est écrit dans un fichier temporaire du même dossier, puis
    renommé par-dessus la cible : une interruption ne laisse jamais un
    fichier tronqué.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".contacts-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(contacts, f, ensure_ascii=False, indent=4)
            f.write("\n")
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

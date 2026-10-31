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
    """Le fichier existe mais ne peut pas être utilisé ; il n'a pas été modifié."""


@dataclass(frozen=True)
class ResultatChargement:
    contacts: Contacts
    # Renseignés si le fichier n'était pas du JSON valide et a été renommé.
    fichier_mis_de_cote: Path | None = None
    detail_erreur: str | None = None


def charger_contacts(chemin: Path = FICHIER_CONTACTS) -> ResultatChargement:
    """Charge le carnet depuis le fichier JSON.

    - Fichier absent : carnet vide.
    - JSON invalide : le fichier est renommé en copie horodatée, jamais
      écrasé, et le carnet repart vide.
    - Fichier illisible, mal encodé ou de mauvaise forme : ErreurChargement,
      sans toucher au fichier.

    Un fichier UTF-8 avec BOM, comme en produit le Bloc-notes, est accepté.
    """
    if not chemin.exists():
        return ResultatChargement({})

    try:
        with open(chemin, "r", encoding="utf-8-sig") as f:
            donnees = json.load(f)
    except json.JSONDecodeError as e:
        return ResultatChargement(
            {},
            fichier_mis_de_cote=_mettre_de_cote(chemin),
            detail_erreur=f"{e.msg}, ligne {e.lineno}",
        )
    except UnicodeDecodeError as e:
        raise ErreurChargement(
            f"{chemin.name} n'est pas encodé en UTF-8 (octet invalide en position {e.start}). "
            "Réenregistrez-le en UTF-8."
        ) from e
    except OSError as e:
        raise ErreurChargement(f"Impossible de lire {chemin.name} : {e.strerror or e}.") from e

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
                f"La fiche « {nom} » dans {chemin.name} doit être un objet JSON, "
                f"pas {type(fiche).__name__}."
            )


def _serialiser(contacts: Contacts) -> str:
    texte = json.dumps(contacts, ensure_ascii=False, indent=4) + "\n"
    try:
        texte.encode("utf-8")
    except UnicodeEncodeError:
        # Un fichier importé peut contenir un caractère isolé non encodable
        # en UTF-8 (demi-paire « \ud83d »). Échappé en \uXXXX, il reste du
        # JSON valide et relisible, au prix d'accents échappés eux aussi.
        texte = json.dumps(contacts, ensure_ascii=True, indent=4) + "\n"
    return texte


def sauvegarder_contacts(contacts: Contacts, chemin: Path = FICHIER_CONTACTS) -> None:
    """Écrit le carnet de façon atomique. Lève OSError en cas d'échec.

    Le contenu est écrit dans un fichier temporaire du même dossier, puis
    renommé par-dessus la cible : une interruption ne laisse jamais un
    fichier tronqué.
    """
    texte = _serialiser(contacts)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".contacts-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

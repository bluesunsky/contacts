"""Lecture et écriture du carnet, dans une base SQLite ou un fichier JSON.

Le format est choisi selon l'extension : « .json » pour un fichier JSON,
toute autre extension pour une base SQLite. Le carnet par défaut est une
base SQLite ; à sa première ouverture, le fichier JSON de même nom qui
l'a précédé est importé, sans être modifié.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .modele import Contacts, Fiche

# Le fichier est ancré sur le dossier du projet, pas sur le répertoire
# courant, pour que le même carnet soit utilisé d'où que l'on lance le
# programme.
FICHIER_CONTACTS = Path(__file__).resolve().parent.parent / "contacts.db"
EXTENSION_JSON = ".json"


class ErreurChargement(Exception):
    """Le fichier existe mais ne peut pas être utilisé ; il n'a pas été modifié."""


@dataclass(frozen=True)
class ResultatChargement:
    contacts: Contacts
    # Renseignés si le fichier n'était pas du JSON valide et a été renommé.
    fichier_mis_de_cote: Path | None = None
    detail_erreur: str | None = None


def charger_contacts(chemin: Path = FICHIER_CONTACTS) -> ResultatChargement:
    """Charge le carnet depuis un fichier JSON ou une base SQLite, selon l'extension."""
    if chemin.suffix == EXTENSION_JSON:
        return _charger_json(chemin)
    contacts = _lire_sqlite(chemin) if chemin.exists() else None
    if contacts is None:
        # Base absente, ou créée sans carnet (fichier vide) : l'ancien JSON
        # reste la source des contacts tant qu'il n'a pas été importé.
        ancien = chemin.with_suffix(EXTENSION_JSON)
        if ancien.exists():
            return ResultatChargement(_importer_json(ancien, chemin))
        return ResultatChargement({})
    return ResultatChargement(contacts)


def sauvegarder_contacts(contacts: Contacts, chemin: Path = FICHIER_CONTACTS) -> None:
    """Écrit le carnet de façon atomique. Lève OSError en cas d'échec.

    Une interruption ne laisse jamais un carnet à moitié écrit : l'ancien
    contenu reste en place tant que le nouveau n'est pas complet.
    """
    if chemin.suffix == EXTENSION_JSON:
        _sauvegarder_json(contacts, chemin)
    else:
        _sauvegarder_sqlite(contacts, chemin)


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def _charger_json(chemin: Path) -> ResultatChargement:
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
        return ResultatChargement(_lire_json(chemin))
    except json.JSONDecodeError as e:
        return ResultatChargement(
            {},
            fichier_mis_de_cote=_mettre_de_cote(chemin),
            detail_erreur=f"{e.msg}, ligne {e.lineno}",
        )


def _lire_json(chemin: Path) -> Contacts:
    """Lit et vérifie le fichier. Lève json.JSONDecodeError ou ErreurChargement."""
    try:
        with open(chemin, "r", encoding="utf-8-sig") as f:
            donnees = json.load(f)
    except UnicodeDecodeError as e:
        raise ErreurChargement(
            f"{chemin.name} n'est pas encodé en UTF-8 (octet invalide en position {e.start}). "
            "Réenregistrez-le en UTF-8."
        ) from e
    except OSError as e:
        raise ErreurChargement(f"Impossible de lire {chemin.name} : {e.strerror or e}.") from e

    _verifier_forme(donnees, chemin)
    return donnees


def _chemin_sauvegarde(chemin: Path) -> Path:
    """Nom horodaté libre à côté du fichier : contacts.20261031-140501.bak."""
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    sauvegarde = chemin.with_name(f"{chemin.stem}.{horodatage}.bak")
    numero = 1
    while sauvegarde.exists():  # deux sauvegardes dans la même seconde
        sauvegarde = chemin.with_name(f"{chemin.stem}.{horodatage}-{numero}.bak")
        numero += 1
    return sauvegarde


def _mettre_de_cote(chemin: Path) -> Path:
    """Renomme un fichier abîmé en copie horodatée et retourne son chemin."""
    sauvegarde = _chemin_sauvegarde(chemin)
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


def _sauvegarder_json(contacts: Contacts, chemin: Path) -> None:
    """Écrit dans un fichier temporaire du même dossier, puis le renomme
    par-dessus la cible : une interruption ne laisse jamais un fichier tronqué.
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


# --------------------------------------------------------------------------
# SQLite
#
# Chaque champ de fiche a sa place :
# - contacts      : une colonne par champ simple (prénom, notes...) ;
# - telephones,
#   emails        : une ligne par numéro de champ multiple (« Phone 2 - ... ») ;
# - autres_champs : une ligne (clé, valeur) pour toute autre clé, afin de
#                   conserver les champs d'un export Google non gérés ici.
#
# Une colonne NULL correspond à un champ absent de la fiche. L'identifiant
# d'un contact est sa position dans le carnet.
# --------------------------------------------------------------------------

VERSION_SCHEMA = 1
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE,
    prenom TEXT,
    nom_famille TEXT,
    entreprise TEXT,
    poste TEXT,
    adresse TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS telephones (
    contact_id INTEGER NOT NULL REFERENCES contacts (id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    libelle TEXT,
    valeur TEXT,
    PRIMARY KEY (contact_id, numero)
);
CREATE TABLE IF NOT EXISTS emails (
    contact_id INTEGER NOT NULL REFERENCES contacts (id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    libelle TEXT,
    valeur TEXT,
    PRIMARY KEY (contact_id, numero)
);
CREATE TABLE IF NOT EXISTS autres_champs (
    contact_id INTEGER NOT NULL REFERENCES contacts (id) ON DELETE CASCADE,
    cle TEXT NOT NULL,
    valeur TEXT NOT NULL,
    PRIMARY KEY (contact_id, cle)
);
"""

# Clé de la fiche -> colonne de la table contacts.
COLONNES = {
    "First Name": "prenom",
    "Last Name": "nom_famille",
    "Organization Name": "entreprise",
    "Organization Title": "poste",
    "Address 1 - Formatted": "adresse",
    "Notes": "notes",
}
# Type de champ multiple Google -> table. Un numéro à zéro initial
# (« Phone 01 ») n'est pas reconnu : il ne se relirait pas à l'identique.
TABLES_MULTIPLES = {"Phone": "telephones", "E-mail": "emails"}
MOTIF_CHAMP_MULTIPLE = re.compile(r"^(Phone|E-mail) ([1-9]\d*) - (Label|Value)$")
# Demi-paire UTF-16 isolée : SQLite ne stocke que de l'UTF-8 valide.
MOTIF_DEMI_PAIRE = re.compile("[\ud800-\udfff]")
CARACTERE_REMPLACEMENT = "�"


def _importer_json(ancien: Path, chemin: Path) -> Contacts:
    """Crée la base à partir de l'ancien fichier JSON, laissé intact.

    Un JSON invalide n'est pas mis de côté comme à l'ordinaire : partir
    d'une base vide masquerait les contacts qu'il contient encore.
    """
    try:
        contacts = _lire_json(ancien)
    except json.JSONDecodeError as e:
        raise ErreurChargement(
            f"Import de {ancien.name} impossible : JSON invalide ({e.msg}, ligne {e.lineno}). "
            f"Corrigez-le, ou supprimez-le pour démarrer un carnet vide."
        ) from e
    _verifier_valeurs_simples(contacts, ancien)
    try:
        _sauvegarder_sqlite(contacts, chemin)
    except OSError as e:
        raise ErreurChargement(f"Import de {ancien.name} impossible : {e.strerror or e}.") from e
    # Relu depuis la base : le carnet est exactement ce qui a été enregistré.
    return _lire_sqlite(chemin) or {}


def _verifier_valeurs_simples(contacts: Contacts, chemin: Path) -> None:
    """Chaque champ doit tenir dans une colonne : texte, nombre ou vide."""
    for nom, fiche in contacts.items():
        for cle, valeur in fiche.items():
            if isinstance(valeur, (dict, list)):
                raise ErreurChargement(
                    f"Le champ « {cle} » de « {nom} » dans {chemin.name} doit être un texte, "
                    f"pas {type(valeur).__name__}."
                )


def _texte_sqlite(valeur: object) -> str:
    """Texte enregistrable : nombre converti, demi-paire isolée remplacée par « � »."""
    texte = valeur if isinstance(valeur, str) else str(valeur)
    return MOTIF_DEMI_PAIRE.sub(CARACTERE_REMPLACEMENT, texte)


def _lire_sqlite(chemin: Path) -> Contacts | None:
    """Lit la base en lecture seule ; None si elle ne contient pas encore de carnet.

    Lève ErreurChargement, sans toucher au fichier.
    """
    # mode=ro : une base absente ou abîmée n'est jamais créée ni modifiée ici.
    adresse = f"{chemin.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(adresse, uri=True)) as base:
            table = base.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'contacts'"
            ).fetchone()
            if table is None:  # base vide : les tables seront créées au premier enregistrement
                return None
            version = base.execute("PRAGMA user_version").fetchone()[0]
            if version != VERSION_SCHEMA:
                raise ErreurChargement(
                    f"La base {chemin.name} n'a pas le format attendu "
                    f"(version {version} au lieu de {VERSION_SCHEMA})."
                )
            return _assembler_fiches(base)
    except sqlite3.Error as e:
        raise ErreurChargement(f"Impossible de lire la base {chemin.name} : {e}.") from e


def _assembler_fiches(base: sqlite3.Connection) -> Contacts:
    """Reconstitue les fiches au format Google à partir des tables."""
    noms: dict[int, str] = {}
    fiches: dict[int, Fiche] = {}
    requete = f"SELECT id, nom, {', '.join(COLONNES.values())} FROM contacts ORDER BY id"
    for identifiant, nom, *valeurs in base.execute(requete):
        noms[identifiant] = nom
        fiches[identifiant] = {
            cle: valeur for cle, valeur in zip(COLONNES, valeurs) if valeur is not None
        }

    for type_champ, table in TABLES_MULTIPLES.items():
        lignes = base.execute(
            f"SELECT contact_id, numero, libelle, valeur FROM {table} ORDER BY contact_id, numero"
        )
        for identifiant, numero, libelle, valeur in lignes:
            fiche = fiches.get(identifiant)
            if fiche is None:  # ligne orpheline d'une base modifiée à la main
                continue
            if libelle is not None:
                fiche[f"{type_champ} {numero} - Label"] = libelle
            if valeur is not None:
                fiche[f"{type_champ} {numero} - Value"] = valeur

    for identifiant, cle, valeur in base.execute(
        "SELECT contact_id, cle, valeur FROM autres_champs ORDER BY contact_id, rowid"
    ):
        if identifiant in fiches:
            fiches[identifiant][cle] = valeur

    return {noms[identifiant]: fiche for identifiant, fiche in fiches.items()}


@dataclass
class _LignesSqlite:
    """Lignes à insérer dans chaque table pour enregistrer un carnet."""

    contacts: list[tuple] = field(default_factory=list)
    multiples: dict[str, list[tuple]] = field(
        default_factory=lambda: {table: [] for table in TABLES_MULTIPLES.values()}
    )
    autres: list[tuple] = field(default_factory=list)

    def ajouter(self, identifiant: int, nom: str, fiche: Fiche) -> None:
        """Répartit les champs d'une fiche ; un champ à None est traité comme absent."""
        colonnes: dict[str, str | None] = dict.fromkeys(COLONNES.values())
        multiples: dict[tuple[str, int], dict[str, str | None]] = {}
        for cle, valeur in fiche.items():
            if valeur is None:
                continue
            texte = _texte_sqlite(valeur)
            if cle in COLONNES:
                colonnes[COLONNES[cle]] = texte
            elif champ := MOTIF_CHAMP_MULTIPLE.match(cle):
                type_champ, numero, partie = champ.groups()
                ligne = multiples.setdefault((TABLES_MULTIPLES[type_champ], int(numero)), {})
                ligne[partie] = texte
            else:
                self.autres.append((identifiant, _texte_sqlite(cle), texte))

        self.contacts.append((identifiant, _texte_sqlite(nom), *colonnes.values()))
        for (table, numero), ligne in multiples.items():
            self.multiples[table].append((identifiant, numero, ligne.get("Label"), ligne.get("Value")))


def _sauvegarder_sqlite(contacts: Contacts, chemin: Path) -> None:
    """Remplace tout le contenu de la base en une seule transaction."""
    lignes = _LignesSqlite()
    for identifiant, (nom, fiche) in enumerate(contacts.items(), start=1):
        lignes.ajouter(identifiant, nom, fiche)

    colonnes = ", ".join(["id", "nom", *COLONNES.values()])
    marques = ", ".join("?" * (len(COLONNES) + 2))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(chemin)) as base:
            base.execute("PRAGMA foreign_keys = ON")
            base.executescript(SCHEMA_SQLITE)
            with base:  # validée en bloc, ou annulée en cas d'erreur
                base.execute("DELETE FROM contacts")  # et, en cascade, leurs champs
                base.executemany(f"INSERT INTO contacts ({colonnes}) VALUES ({marques})", lignes.contacts)
                for table, lignes_table in lignes.multiples.items():
                    base.executemany(
                        f"INSERT INTO {table} (contact_id, numero, libelle, valeur) VALUES (?, ?, ?, ?)",
                        lignes_table,
                    )
                base.executemany(
                    "INSERT INTO autres_champs (contact_id, cle, valeur) VALUES (?, ?, ?)", lignes.autres
                )
                # Dans la transaction : une base existante n'est marquée à ce
                # format que si les données y ont bien été écrites.
                base.execute(f"PRAGMA user_version = {VERSION_SCHEMA}")
    except sqlite3.Error as e:
        # Converti en OSError, que les interfaces signalent déjà.
        raise OSError(f"écriture dans la base {chemin.name} impossible ({e})") from e

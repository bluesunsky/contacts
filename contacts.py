"""Gestionnaire de contacts en ligne de commande.

Les contacts sont stockés dans un fichier JSON, sous forme d'un dictionnaire
indexé par nom. Les clés de chaque fiche reprennent le format d'export CSV de
Google Contacts ("Phone 1 - Value", "E-mail 1 - Label", ...), ce qui permet
d'afficher indifféremment des contacts importés et des contacts saisis ici.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

# Le fichier est ancré sur l'emplacement du script, pas sur le répertoire
# courant, pour que le même carnet soit utilisé quel que soit le dossier
# d'où le script est lancé.
FICHIER_CONTACTS = Path(__file__).resolve().parent / "contacts.json"

Contacts = dict[str, dict[str, str]]

# Clés Google Contacts : "Phone 1 - Value", "E-mail 2 - Value", ...
MOTIF_TELEPHONE = re.compile(r"^Phone (\d+) - Value$")
MOTIF_EMAIL = re.compile(r"^E-mail (\d+) - Value$")
MOTIF_EMAIL_VALIDE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CARACTERES_TELEPHONE = re.compile(r"[\d\s().+\-]+")
MIN_CHIFFRES_TELEPHONE = 6


class ErreurChargement(Exception):
    """Le fichier de contacts existe mais n'a pas la forme attendue."""


# --------------------------------------------------------------------------
# Persistance
# --------------------------------------------------------------------------


def charger_contacts(chemin: Path = FICHIER_CONTACTS) -> Contacts:
    """Charge le carnet depuis le fichier JSON.

    Un fichier absent donne un carnet vide. Un fichier illisible (JSON
    invalide) est mis de côté dans une copie de sauvegarde avant de repartir
    d'un carnet vide, afin de ne jamais l'écraser silencieusement. Un fichier
    valide mais de mauvaise forme (liste, fiches non dictionnaires) lève
    ErreurChargement sans toucher au fichier.
    """
    if not chemin.exists():
        return {}

    try:
        with open(chemin, "r", encoding="utf-8") as f:
            donnees = json.load(f)
    except json.JSONDecodeError as e:
        sauvegarde = _mettre_de_cote(chemin)
        print(
            f"⚠️  Le fichier {chemin.name} est illisible ({e.msg}, ligne {e.lineno}). "
            f"Il a été conservé sous {sauvegarde.name} et un carnet vide est utilisé."
        )
        return {}

    _verifier_forme(donnees, chemin)
    return donnees


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

    Le contenu est d'abord écrit dans un fichier temporaire du même dossier,
    puis renommé par-dessus la cible. Une interruption en cours d'écriture ne
    peut donc jamais laisser un fichier tronqué.
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


# --------------------------------------------------------------------------
# Recherche de clé
# --------------------------------------------------------------------------


def trouver_cle(contacts: Contacts, nom: str) -> str | None:
    """Retourne la clé réelle correspondant à `nom`, sans tenir compte de la casse."""
    cible = nom.strip().casefold()
    for cle in contacts:
        if cle.casefold() == cible:
            return cle
    return None


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------


def _champs_numerotes(
    infos: dict[str, str], motif: re.Pattern[str], label_defaut: str
) -> list[tuple[int, str, str]]:
    """Extrait les champs multiples (téléphones, e-mails) avec leur label.

    Retourne des tuples (numero, label, valeur) triés par numéro, en ignorant
    les valeurs vides, fréquentes dans les exports Google.
    """
    resultats = []
    for cle, valeur in infos.items():
        m = motif.match(cle)
        if not m or not str(valeur).strip():
            continue
        label = infos.get(cle.replace("Value", "Label")) or label_defaut
        resultats.append((int(m.group(1)), label, valeur))
    return sorted(resultats)


def afficher_contact(nom: str, infos: dict[str, str]) -> None:
    """Affiche une fiche de contact."""
    print(f"\n👤 Nom : {nom}")

    telephones = _champs_numerotes(infos, MOTIF_TELEPHONE, "Téléphone")
    if telephones:
        for numero, label, valeur in telephones:
            print(f"  📞 {label} ({numero}) : {valeur}")
    elif infos.get("telephone"):  # rétrocompatibilité anciens contacts
        print(f"  📞 Téléphone : {infos['telephone']}")

    emails = _champs_numerotes(infos, MOTIF_EMAIL, "Email")
    if emails:
        for _, label, valeur in emails:
            print(f"  ✉️  {label} : {valeur}")
    elif infos.get("email"):  # rétrocompatibilité anciens contacts
        print(f"  ✉️  Email : {infos['email']}")

    # Seuls les champs renseignés sont affichés.
    if infos.get("Organization Name"):
        print(f"  🏢 Entreprise : {infos['Organization Name']}")
    if infos.get("Organization Title"):
        print(f"  💼 Poste : {infos['Organization Title']}")
    if infos.get("Address 1 - Formatted"):
        adresse = infos["Address 1 - Formatted"].replace(" ::: ", "\n      ")
        print(f"  📍 Adresse : {adresse}")
    if infos.get("Notes"):
        print(f"  📝 Notes : {infos['Notes']}")

    print("-" * 40)


def afficher_contacts(contacts: Contacts) -> None:
    """Affiche toutes les fiches du carnet."""
    if not contacts:
        print("📭 Aucun contact enregistré.")
        return

    print(f"\n--- Liste des contacts ({len(contacts)}) ---")
    for nom, infos in contacts.items():
        afficher_contact(nom, infos)


# --------------------------------------------------------------------------
# Saisie et validation
# --------------------------------------------------------------------------


def saisir(
    invite: str,
    valider: Callable[[str], bool] = lambda _: True,
    message_erreur: str = "Valeur invalide.",
    obligatoire: bool = False,
) -> str:
    """Demande une valeur jusqu'à ce qu'elle soit valide.

    Une valeur vide est acceptée sans validation, sauf si `obligatoire`.
    """
    while True:
        valeur = input(invite).strip()
        if not valeur:
            if obligatoire:
                print("⚠️  Ce champ est obligatoire.")
                continue
            return valeur
        if valider(valeur):
            return valeur
        print(f"⚠️  {message_erreur}")


def telephone_valide(valeur: str) -> bool:
    """Au moins six chiffres, et uniquement des caractères usuels de numéro."""
    assez_de_chiffres = len(re.sub(r"\D", "", valeur)) >= MIN_CHIFFRES_TELEPHONE
    return assez_de_chiffres and CARACTERES_TELEPHONE.fullmatch(valeur) is not None


def email_valide(valeur: str) -> bool:
    return MOTIF_EMAIL_VALIDE.match(valeur) is not None


# --------------------------------------------------------------------------
# Actions du menu
# --------------------------------------------------------------------------


def ajouter_contact(contacts: Contacts, chemin: Path = FICHIER_CONTACTS) -> None:
    nom = saisir("Nom du contact : ", obligatoire=True)
    existant = trouver_cle(contacts, nom)
    if existant is not None:
        print(f"⚠️  Le contact '{existant}' existe déjà.")
        return

    prenom = saisir("Prénom (optionnel) : ")
    nom_famille = saisir("Nom de famille (optionnel) : ")
    telephone = saisir(
        "Numéro de téléphone : ",
        telephone_valide,
        "Numéro invalide (au moins 6 chiffres ; caractères autorisés : chiffres, espaces, + - ( ) .).",
    )
    email = saisir(
        "Adresse email : ",
        email_valide,
        "Adresse e-mail invalide (attendu : nom@domaine.tld).",
    )
    notes = saisir("Notes / Commentaires : ")

    # Mêmes clés que Google Contacts pour garder une structure unifiée.
    contacts[nom] = {
        "First Name": prenom,
        "Last Name": nom_famille,
        "Phone 1 - Label": "Mobile",
        "Phone 1 - Value": telephone,
        "E-mail 1 - Label": "Home",
        "E-mail 1 - Value": email,
        "Notes": notes,
    }
    sauvegarder_contacts(contacts, chemin)
    print(f"✅ Contact '{nom}' ajouté avec succès !")


def rechercher_contact(contacts: Contacts) -> None:
    recherche = saisir("Entrez le nom du contact recherché : ", obligatoire=True).casefold()
    trouves = {nom: infos for nom, infos in contacts.items() if recherche in nom.casefold()}

    if not trouves:
        print("❌ Aucun contact trouvé.")
        return

    afficher_contacts(trouves)


def supprimer_contact(contacts: Contacts, chemin: Path = FICHIER_CONTACTS) -> None:
    nom = saisir("Nom du contact à supprimer : ", obligatoire=True)
    cle = trouver_cle(contacts, nom)
    if cle is None:
        print("❌ Contact introuvable.")
        return

    del contacts[cle]
    sauvegarder_contacts(contacts, chemin)
    print(f"🗑️  Contact '{cle}' supprimé avec succès.")


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------


def menu() -> None:
    contacts = charger_contacts()

    while True:
        print("\n=== GESTIONNAIRE DE CONTACTS ===")
        print("1. Afficher tous les contacts et détails")
        print("2. Ajouter un contact")
        print("3. Rechercher un contact")
        print("4. Supprimer un contact")
        print("5. Quitter")

        choix = input("Choisissez une option (1-5) : ").strip()

        if choix == "1":
            afficher_contacts(contacts)
        elif choix == "2":
            ajouter_contact(contacts)
        elif choix == "3":
            rechercher_contact(contacts)
        elif choix == "4":
            supprimer_contact(contacts)
        elif choix == "5":
            print("👋 Au revoir !")
            break
        else:
            print("⚠️  Option invalide, veuillez réessayer.")


def main() -> int:
    # Sous Windows, la console ou une redirection peut être en cp1252, qui ne
    # sait pas encoder les emojis : on force l'UTF-8 sur la sortie.
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")

    try:
        menu()
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Au revoir !")
    except ErreurChargement as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

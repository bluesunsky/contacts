"""Modèle de données du carnet, indépendant de toute interface.

Les fiches sont stockées telles quelles, avec les clés du format d'export
CSV de Google Contacts ("Phone 1 - Value", "E-mail 1 - Label", ...). Ce
module en extrait une vue structurée (VueContact) que chaque interface
présente à sa façon, et fournit les règles de validation des saisies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields

Fiche = dict[str, str]
Contacts = dict[str, Fiche]

# Clés Google Contacts : "Phone 1 - Value", "E-mail 2 - Value", ...
MOTIF_TELEPHONE = re.compile(r"^Phone (\d+) - Value$")
MOTIF_EMAIL = re.compile(r"^E-mail (\d+) - Value$")
MOTIF_EMAIL_VALIDE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CARACTERES_TELEPHONE = re.compile(r"[\d\s().+\-]+")
MIN_CHIFFRES_TELEPHONE = 6

SEPARATEUR_ADRESSE_GOOGLE = " ::: "

MESSAGE_OBLIGATOIRE = "Ce champ est obligatoire."
MESSAGE_TELEPHONE = (
    f"Numéro invalide (au moins {MIN_CHIFFRES_TELEPHONE} chiffres ; "
    "caractères autorisés : chiffres, espaces, + - ( ) .)."
)
MESSAGE_EMAIL = "Adresse e-mail invalide (attendu : nom@domaine.tld)."


# --------------------------------------------------------------------------
# Validation
#
# Chaque fonction retourne un message d'erreur, ou None si la valeur est
# acceptable. Une interface peut ainsi afficher le message à côté du champ.
# --------------------------------------------------------------------------


def erreur_obligatoire(valeur: str) -> str | None:
    return MESSAGE_OBLIGATOIRE if not valeur.strip() else None


def erreur_telephone(valeur: str) -> str | None:
    """Un téléphone vide est accepté, sinon il doit ressembler à un numéro."""
    valeur = valeur.strip()
    if not valeur:
        return None
    assez_de_chiffres = len(re.sub(r"\D", "", valeur)) >= MIN_CHIFFRES_TELEPHONE
    if assez_de_chiffres and CARACTERES_TELEPHONE.fullmatch(valeur):
        return None
    return MESSAGE_TELEPHONE


def erreur_email(valeur: str) -> str | None:
    """Un e-mail vide est accepté, sinon il doit avoir la forme nom@domaine.tld."""
    valeur = valeur.strip()
    if not valeur or MOTIF_EMAIL_VALIDE.match(valeur):
        return None
    return MESSAGE_EMAIL


# --------------------------------------------------------------------------
# Création d'un contact
# --------------------------------------------------------------------------


@dataclass
class NouveauContact:
    """Données saisies pour créer un contact. Les espaces superflus sont retirés."""

    nom: str
    prenom: str = ""
    nom_famille: str = ""
    telephone: str = ""
    email: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        for champ in fields(self):
            setattr(self, champ.name, getattr(self, champ.name).strip())

    def erreurs(self) -> dict[str, str]:
        """Retourne les erreurs de validation, indexées par nom de champ."""
        verifications = {
            "nom": erreur_obligatoire(self.nom),
            "telephone": erreur_telephone(self.telephone),
            "email": erreur_email(self.email),
        }
        return {champ: msg for champ, msg in verifications.items() if msg}

    def vers_fiche(self) -> Fiche:
        """Convertit en fiche au format Google Contacts."""
        return {
            "First Name": self.prenom,
            "Last Name": self.nom_famille,
            "Phone 1 - Label": "Mobile",
            "Phone 1 - Value": self.telephone,
            "E-mail 1 - Label": "Home",
            "E-mail 1 - Value": self.email,
            "Notes": self.notes,
        }


# --------------------------------------------------------------------------
# Vue d'affichage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Telephone:
    label: str
    valeur: str
    numero: int | None = None  # None pour l'ancien format sans numérotation


@dataclass(frozen=True)
class Email:
    label: str
    valeur: str


@dataclass(frozen=True)
class VueContact:
    """Informations d'un contact prêtes à afficher. Les champs vides sont omis."""

    nom: str
    telephones: tuple[Telephone, ...] = ()
    emails: tuple[Email, ...] = ()
    entreprise: str = ""
    poste: str = ""
    adresse: tuple[str, ...] = ()  # une entrée par ligne
    notes: str = ""


def _texte(fiche: Fiche, cle: str) -> str:
    return str(fiche.get(cle) or "").strip()


def _champs_numerotes(
    fiche: Fiche, motif: re.Pattern[str], label_defaut: str
) -> list[tuple[int, str, str]]:
    """Extrait les champs multiples triés par numéro, sans les valeurs vides."""
    resultats = []
    for cle in fiche:
        m = motif.match(cle)
        valeur = _texte(fiche, cle)
        if m and valeur:
            label = _texte(fiche, cle.replace("Value", "Label")) or label_defaut
            resultats.append((int(m.group(1)), label, valeur))
    return sorted(resultats)


def vue_contact(nom: str, fiche: Fiche) -> VueContact:
    """Construit la vue d'affichage d'une fiche, anciens formats compris."""
    telephones = tuple(
        Telephone(label, valeur, numero)
        for numero, label, valeur in _champs_numerotes(fiche, MOTIF_TELEPHONE, "Téléphone")
    )
    if not telephones and _texte(fiche, "telephone"):  # rétrocompatibilité
        telephones = (Telephone("Téléphone", _texte(fiche, "telephone")),)

    emails = tuple(
        Email(label, valeur)
        for _, label, valeur in _champs_numerotes(fiche, MOTIF_EMAIL, "Email")
    )
    if not emails and _texte(fiche, "email"):  # rétrocompatibilité
        emails = (Email("Email", _texte(fiche, "email")),)

    adresse_brute = _texte(fiche, "Address 1 - Formatted")
    adresse = tuple(
        ligne.strip() for ligne in adresse_brute.split(SEPARATEUR_ADRESSE_GOOGLE) if ligne.strip()
    )

    return VueContact(
        nom=nom,
        telephones=telephones,
        emails=emails,
        entreprise=_texte(fiche, "Organization Name"),
        poste=_texte(fiche, "Organization Title"),
        adresse=adresse,
        notes=_texte(fiche, "Notes"),
    )

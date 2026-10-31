"""Modèle de données du carnet, indépendant de toute interface.

Les fiches sont stockées telles quelles, avec les clés du format d'export
CSV de Google Contacts ("Phone 1 - Value", "E-mail 1 - Label", ...). Ce
module en extrait une vue structurée (VueContact) que chaque interface
présente à sa façon, et fournit la saisie éditable (SaisieContact) avec ses
règles de validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields

Fiche = dict[str, object]
Contacts = dict[str, Fiche]

# Clés Google Contacts : "Phone 1 - Value", "E-mail 2 - Value", ...
MOTIF_TELEPHONE = re.compile(r"^Phone (\d+) - Value$")
MOTIF_EMAIL = re.compile(r"^E-mail (\d+) - Value$")
MOTIF_EMAIL_VALIDE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CARACTERES_TELEPHONE = re.compile(r"[\d\s().+\-]+")
MIN_CHIFFRES_TELEPHONE = 6

SEPARATEUR_ADRESSE_GOOGLE = " ::: "

# Anciennes clés, antérieures à l'alignement sur le format Google.
ANCIENNE_CLE_TELEPHONE = "telephone"
ANCIENNE_CLE_EMAIL = "email"

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


def _texte(fiche: Fiche, cle: str) -> str:
    """Valeur d'un champ sous forme de texte ; les nombres sont conservés (0 compris)."""
    valeur = fiche.get(cle)
    return "" if valeur is None else str(valeur).strip()


# --------------------------------------------------------------------------
# Saisie d'un contact (création et modification)
# --------------------------------------------------------------------------


@dataclass
class SaisieContact:
    """Champs éditables d'un contact. Les espaces superflus sont retirés.

    Seuls le téléphone et l'e-mail principaux (n° 1) sont éditables ; les
    autres champs d'une fiche importée sont conservés lors d'une modification.
    """

    nom: str
    prenom: str = ""
    nom_famille: str = ""
    telephone: str = ""
    email: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        for champ in fields(self):
            setattr(self, champ.name, getattr(self, champ.name).strip())

    @classmethod
    def depuis_fiche(cls, nom: str, fiche: Fiche) -> SaisieContact:
        """Valeurs actuelles d'une fiche, anciens formats compris."""
        return cls(
            nom=nom,
            prenom=_texte(fiche, "First Name"),
            nom_famille=_texte(fiche, "Last Name"),
            telephone=_texte(fiche, "Phone 1 - Value") or _texte(fiche, ANCIENNE_CLE_TELEPHONE),
            email=_texte(fiche, "E-mail 1 - Value") or _texte(fiche, ANCIENNE_CLE_EMAIL),
            notes=_texte(fiche, "Notes"),
        )

    def erreurs(self, reference: SaisieContact | None = None) -> dict[str, str]:
        """Erreurs de validation, indexées par nom de champ.

        Avec `reference` (valeurs avant modification), un téléphone ou un
        e-mail inchangé n'est pas revalidé : une valeur importée qui ne suit
        pas nos règles ne bloque pas la modification des autres champs.
        """
        def inchange(champ: str) -> bool:
            return reference is not None and getattr(self, champ) == getattr(reference, champ)

        verifications = {
            "nom": erreur_obligatoire(self.nom),
            "telephone": None if inchange("telephone") else erreur_telephone(self.telephone),
            "email": None if inchange("email") else erreur_email(self.email),
        }
        return {champ: msg for champ, msg in verifications.items() if msg}

    def appliquer(self, fiche: Fiche | None = None) -> Fiche:
        """Retourne une nouvelle fiche au format Google avec ces valeurs.

        Partant d'une fiche existante, les autres champs et les libellés
        existants sont conservés, et les anciennes clés sont migrées.
        """
        resultat = dict(fiche or {})
        resultat.pop(ANCIENNE_CLE_TELEPHONE, None)
        resultat.pop(ANCIENNE_CLE_EMAIL, None)
        resultat["First Name"] = self.prenom
        resultat["Last Name"] = self.nom_famille
        resultat["Phone 1 - Label"] = _texte(resultat, "Phone 1 - Label") or "Mobile"
        resultat["Phone 1 - Value"] = self.telephone
        resultat["E-mail 1 - Label"] = _texte(resultat, "E-mail 1 - Label") or "Home"
        resultat["E-mail 1 - Value"] = self.email
        resultat["Notes"] = self.notes
        return resultat


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


# Libellés usuels de Google Contacts, traduits à l'affichage uniquement : le
# fichier conserve les libellés d'origine.
LIBELLES_FR = {
    "mobile": "Mobile",
    "home": "Domicile",
    "work": "Travail",
    "other": "Autre",
    "main": "Principal",
    "home fax": "Fax domicile",
    "work fax": "Fax travail",
    "pager": "Bipeur",
    "email": "E-mail",
}
LIBELLE_TELEPHONE = "Téléphone"
LIBELLE_EMAIL = "E-mail"


def traduire_libelle(libelle: str) -> str:
    """Traduit un libellé Google usuel ; un libellé personnalisé est gardé tel quel.

    Google préfixe le libellé du numéro principal par « * », retiré ici.
    """
    nettoye = libelle.strip().lstrip("*").strip()
    return LIBELLES_FR.get(nettoye.casefold(), nettoye)


def _champs_numerotes(
    fiche: Fiche, motif: re.Pattern[str], label_defaut: str
) -> list[tuple[int, str, str]]:
    """Extrait les champs multiples triés par numéro, sans les valeurs vides."""
    resultats = []
    for cle in fiche:
        m = motif.match(cle)
        valeur = _texte(fiche, cle)
        if m and valeur:
            label = traduire_libelle(_texte(fiche, cle.replace("Value", "Label"))) or label_defaut
            resultats.append((int(m.group(1)), label, valeur))
    return sorted(resultats)


def vue_contact(nom: str, fiche: Fiche) -> VueContact:
    """Construit la vue d'affichage d'une fiche, anciens formats compris."""
    telephones = tuple(
        Telephone(label, valeur, numero)
        for numero, label, valeur in _champs_numerotes(fiche, MOTIF_TELEPHONE, LIBELLE_TELEPHONE)
    )
    if not telephones and _texte(fiche, ANCIENNE_CLE_TELEPHONE):
        telephones = (Telephone(LIBELLE_TELEPHONE, _texte(fiche, ANCIENNE_CLE_TELEPHONE)),)

    emails = tuple(
        Email(label, valeur)
        for _, label, valeur in _champs_numerotes(fiche, MOTIF_EMAIL, LIBELLE_EMAIL)
    )
    if not emails and _texte(fiche, ANCIENNE_CLE_EMAIL):
        emails = (Email(LIBELLE_EMAIL, _texte(fiche, ANCIENNE_CLE_EMAIL)),)

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

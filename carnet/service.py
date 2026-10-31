"""Opérations sur le carnet, à utiliser par toute interface (terminal, graphique...).

Aucune fonction de ce module ne lit le clavier ni n'affiche quoi que ce
soit : les problèmes sont signalés par des exceptions dérivées de
ErreurCarnet, dont le message est prêt à être montré à l'utilisateur. Un
échec d'écriture du fichier remonte en OSError, et le carnet en mémoire
reste alors identique au fichier.
"""

from __future__ import annotations

from pathlib import Path

from .modele import (
    Contacts,
    Fiche,
    SaisieContact,
    VueContact,
    uniformiser_telephones_fiche,
    vue_contact,
)
from .stockage import FICHIER_CONTACTS, charger_contacts, sauvegarder_contacts


class ErreurCarnet(Exception):
    """Erreur métier dont le message peut être affiché tel quel."""


class ContactExistant(ErreurCarnet):
    def __init__(self, nom: str) -> None:
        super().__init__(f"Le contact « {nom} » existe déjà.")
        self.nom = nom


class ContactIntrouvable(ErreurCarnet):
    def __init__(self, nom: str) -> None:
        super().__init__(f"Contact « {nom} » introuvable.")
        self.nom = nom


class DonneesInvalides(ErreurCarnet):
    def __init__(self, erreurs: dict[str, str]) -> None:
        super().__init__(" ".join(erreurs.values()))
        self.erreurs = erreurs  # nom du champ -> message


def _normaliser(nom: str) -> str:
    return nom.strip().casefold()


class Carnet:
    """Carnet de contacts persistant. Chaque modification est enregistrée aussitôt.

    Un nom est d'abord cherché tel quel, puis sans tenir compte de la casse
    ni des espaces autour. Une interface qui affiche les noms enregistrés
    désigne donc toujours le bon contact, même si un fichier importé
    contient des noms qui ne diffèrent que par la casse.

    Les numéros de téléphone sont mis au format international dès le
    chargement : l'affichage est toujours uniforme, même après une
    modification manuelle du fichier, et la forme uniforme est écrite dans
    le fichier au prochain enregistrement. Un numéro non reconnu est gardé
    tel quel.

    Peut lever stockage.ErreurChargement à la construction.
    """

    def __init__(self, chemin: Path = FICHIER_CONTACTS) -> None:
        self.chemin = chemin
        resultat = charger_contacts(chemin)
        self._contacts: Contacts = {
            nom: uniformiser_telephones_fiche(fiche) for nom, fiche in resultat.contacts.items()
        }
        # Renseignés si le fichier était illisible : l'interface doit prévenir
        # l'utilisateur que l'original a été conservé sous ce nom.
        self.fichier_mis_de_cote = resultat.fichier_mis_de_cote
        self.detail_erreur_chargement = resultat.detail_erreur

    # -- Lecture ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._contacts)

    def __contains__(self, nom: object) -> bool:
        return isinstance(nom, str) and self.trouver_cle(nom) is not None

    @property
    def noms(self) -> list[str]:
        return list(self._contacts)

    def trouver_cle(self, nom: str) -> str | None:
        """Retourne le nom exact enregistré correspondant à `nom`, ou None."""
        if nom in self._contacts:
            return nom
        cible = _normaliser(nom)
        return next((cle for cle in self._contacts if _normaliser(cle) == cible), None)

    def fiche(self, nom: str) -> Fiche:
        """Retourne une copie de la fiche brute. Lève ContactIntrouvable."""
        return dict(self._contacts[self._cle_obligatoire(nom)])

    def saisie(self, nom: str) -> SaisieContact:
        """Valeurs éditables actuelles d'un contact. Lève ContactIntrouvable."""
        cle = self._cle_obligatoire(nom)
        return SaisieContact.depuis_fiche(cle, self._contacts[cle])

    def vue(self, nom: str) -> VueContact:
        """Retourne la vue d'affichage d'un contact. Lève ContactIntrouvable."""
        cle = self._cle_obligatoire(nom)
        return vue_contact(cle, self._contacts[cle])

    def vues(self) -> list[VueContact]:
        return [vue_contact(nom, fiche) for nom, fiche in self._contacts.items()]

    def rechercher(self, texte: str) -> list[VueContact]:
        """Contacts dont le nom contient `texte`, sans tenir compte de la casse."""
        motif = texte.strip().casefold()
        return [
            vue_contact(nom, fiche)
            for nom, fiche in self._contacts.items()
            if motif in nom.casefold()
        ]

    # -- Écriture --------------------------------------------------------

    def ajouter(self, saisie: SaisieContact) -> str:
        """Ajoute et enregistre un contact, retourne son nom.

        Lève DonneesInvalides, ContactExistant ou OSError.
        """
        erreurs = saisie.erreurs()
        if erreurs:
            raise DonneesInvalides(erreurs)
        existant = self.trouver_cle(saisie.nom)
        if existant is not None:
            raise ContactExistant(existant)

        nouveaux = dict(self._contacts)
        nouveaux[saisie.nom] = saisie.appliquer()
        self._remplacer(nouveaux)
        return saisie.nom

    def modifier(self, nom: str, saisie: SaisieContact) -> str:
        """Modifie et enregistre un contact, éventuellement renommé.

        Les champs de la fiche non couverts par la saisie sont conservés, et
        le contact garde sa place dans le carnet. Retourne le nom final.
        Lève ContactIntrouvable, DonneesInvalides, ContactExistant ou OSError.
        """
        cle = self._cle_obligatoire(nom)
        fiche = self._contacts[cle]
        erreurs = saisie.erreurs(reference=SaisieContact.depuis_fiche(cle, fiche))
        if erreurs:
            raise DonneesInvalides(erreurs)
        homonyme = self.trouver_cle(saisie.nom)
        if homonyme is not None and homonyme != cle:
            raise ContactExistant(homonyme)

        nouvelle_fiche = saisie.appliquer(fiche)
        nouveaux = {
            (saisie.nom if k == cle else k): (nouvelle_fiche if k == cle else v)
            for k, v in self._contacts.items()
        }
        self._remplacer(nouveaux)
        return saisie.nom

    def supprimer(self, nom: str) -> str:
        """Supprime et enregistre, retourne le nom exact supprimé.

        Lève ContactIntrouvable ou OSError.
        """
        cle = self._cle_obligatoire(nom)
        nouveaux = {k: v for k, v in self._contacts.items() if k != cle}
        self._remplacer(nouveaux)
        return cle

    # -- Interne ---------------------------------------------------------

    def _cle_obligatoire(self, nom: str) -> str:
        cle = self.trouver_cle(nom)
        if cle is None:
            raise ContactIntrouvable(nom.strip())
        return cle

    def _remplacer(self, nouveaux: Contacts) -> None:
        """Enregistre d'abord, puis adopte le nouvel état.

        Si l'écriture échoue, l'exception remonte et le carnet en mémoire
        reste celui du fichier : aucune modification fantôme.
        """
        sauvegarder_contacts(nouveaux, self.chemin)
        self._contacts = nouveaux

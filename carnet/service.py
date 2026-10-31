"""Opérations sur le carnet, à utiliser par toute interface (terminal, graphique...).

Aucune fonction de ce module ne lit le clavier ni n'affiche quoi que ce
soit : les problèmes sont signalés par des exceptions dérivées de
ErreurCarnet, dont le message est prêt à être montré à l'utilisateur.
"""

from __future__ import annotations

from pathlib import Path

from .modele import Contacts, Fiche, NouveauContact, VueContact, vue_contact
from .stockage import FICHIER_CONTACTS, charger_contacts, sauvegarder_contacts


class ErreurCarnet(Exception):
    """Erreur métier dont le message peut être affiché tel quel."""


class ContactExistant(ErreurCarnet):
    def __init__(self, nom: str) -> None:
        super().__init__(f"Le contact '{nom}' existe déjà.")
        self.nom = nom


class ContactIntrouvable(ErreurCarnet):
    def __init__(self, nom: str) -> None:
        super().__init__(f"Contact '{nom}' introuvable.")
        self.nom = nom


class DonneesInvalides(ErreurCarnet):
    def __init__(self, erreurs: dict[str, str]) -> None:
        super().__init__(" ".join(erreurs.values()))
        self.erreurs = erreurs  # nom du champ -> message


class Carnet:
    """Carnet de contacts persistant. Chaque modification est enregistrée aussitôt.

    Les noms sont comparés sans tenir compte de la casse.
    Peut lever stockage.ErreurChargement à la construction.
    """

    def __init__(self, chemin: Path = FICHIER_CONTACTS) -> None:
        self.chemin = chemin
        resultat = charger_contacts(chemin)
        self._contacts: Contacts = resultat.contacts
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
        cible = nom.strip().casefold()
        return next((cle for cle in self._contacts if cle.casefold() == cible), None)

    def fiche(self, nom: str) -> Fiche:
        """Retourne une copie de la fiche brute. Lève ContactIntrouvable."""
        return dict(self._contacts[self._cle_obligatoire(nom)])

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

    def ajouter(self, contact: NouveauContact) -> str:
        """Ajoute et enregistre un contact, retourne son nom.

        Lève DonneesInvalides ou ContactExistant.
        """
        erreurs = contact.erreurs()
        if erreurs:
            raise DonneesInvalides(erreurs)
        existant = self.trouver_cle(contact.nom)
        if existant is not None:
            raise ContactExistant(existant)

        self._contacts[contact.nom] = contact.vers_fiche()
        self._enregistrer()
        return contact.nom

    def supprimer(self, nom: str) -> str:
        """Supprime et enregistre, retourne le nom exact supprimé.

        Lève ContactIntrouvable.
        """
        cle = self._cle_obligatoire(nom)
        del self._contacts[cle]
        self._enregistrer()
        return cle

    # -- Interne ---------------------------------------------------------

    def _cle_obligatoire(self, nom: str) -> str:
        cle = self.trouver_cle(nom)
        if cle is None:
            raise ContactIntrouvable(nom.strip())
        return cle

    def _enregistrer(self) -> None:
        sauvegarder_contacts(self._contacts, self.chemin)

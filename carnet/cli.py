"""Interface en ligne de commande du carnet.

C'est le seul module qui lit le clavier et écrit dans le terminal. Toute la
logique passe par service.Carnet.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from .modele import (
    MESSAGE_OBLIGATOIRE,
    SaisieContact,
    VueContact,
    erreur_email,
    erreur_obligatoire,
    erreur_telephone,
)
from .service import Carnet, ContactIntrouvable, ErreurCarnet
from .stockage import FICHIER_CONTACTS, ErreurChargement

Verification = Callable[[str], "str | None"]

RETRAIT_ADRESSE = "\n      "
# En modification : réponse vide = conserver, ce symbole = effacer le champ.
EFFACER = "-"


# --------------------------------------------------------------------------
# Saisie
# --------------------------------------------------------------------------


def saisir(invite: str, verifier: Verification | None = None) -> str:
    """Demande une valeur jusqu'à ce que `verifier` ne retourne plus d'erreur."""
    while True:
        valeur = input(invite).strip()
        erreur = verifier(valeur) if verifier else None
        if erreur is None:
            return valeur
        print(f"⚠️ {erreur}")


def saisir_modification(
    invite: str,
    actuelle: str,
    verifier: Verification | None = None,
    obligatoire: bool = False,
) -> str:
    """Demande une nouvelle valeur ; vide conserve `actuelle`, EFFACER la vide."""
    def verifier_modification(valeur: str) -> str | None:
        if valeur == "":
            return None
        if valeur == EFFACER:
            return MESSAGE_OBLIGATOIRE if obligatoire else None
        return verifier(valeur) if verifier else None

    rappel = f" [{actuelle}]" if actuelle else ""
    reponse = saisir(f"{invite}{rappel} : ", verifier_modification)
    if reponse == "":
        return actuelle
    return "" if reponse == EFFACER else reponse


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------


def formater_contact(vue: VueContact) -> str:
    """Met en forme une fiche pour le terminal."""
    lignes = [f"\n👤 Nom : {vue.nom}"]
    for tel in vue.telephones:
        numero = f" ({tel.numero})" if tel.numero is not None else ""
        lignes.append(f"  📞 {tel.label}{numero} : {tel.valeur}")
    for email in vue.emails:
        lignes.append(f"  ✉️ {email.label} : {email.valeur}")
    if vue.entreprise:
        lignes.append(f"  🏢 Entreprise : {vue.entreprise}")
    if vue.poste:
        lignes.append(f"  💼 Poste : {vue.poste}")
    if vue.adresse:
        lignes.append(f"  📍 Adresse : {RETRAIT_ADRESSE.join(vue.adresse)}")
    if vue.notes:
        lignes.append(f"  📝 Notes : {vue.notes}")
    lignes.append("-" * 40)
    return "\n".join(lignes)


def afficher_liste(vues: list[VueContact]) -> None:
    print(f"\n--- Liste des contacts ({len(vues)}) ---")
    for vue in vues:
        print(formater_contact(vue))


def _echec_enregistrement(erreur: OSError) -> None:
    print(f"❌ Impossible d'enregistrer le carnet : {erreur.strerror or erreur}")


# --------------------------------------------------------------------------
# Actions du menu
# --------------------------------------------------------------------------


def action_afficher(carnet: Carnet) -> None:
    if not len(carnet):
        print("📭 Aucun contact enregistré.")
        return
    afficher_liste(carnet.vues())


def action_ajouter(carnet: Carnet) -> None:
    nom = saisir("Nom du contact : ", erreur_obligatoire)
    existant = carnet.trouver_cle(nom)
    if existant is not None:
        # Vérifié avant les autres saisies pour ne pas les faire taper pour rien.
        print(f"⚠️ Le contact « {existant} » existe déjà.")
        return

    saisie = SaisieContact(
        nom=nom,
        prenom=saisir("Prénom (optionnel) : "),
        nom_famille=saisir("Nom de famille (optionnel) : "),
        telephone=saisir("Numéro de téléphone : ", erreur_telephone),
        email=saisir("Adresse email : ", erreur_email),
        notes=saisir("Notes / Commentaires : "),
    )
    try:
        carnet.ajouter(saisie)
    except ErreurCarnet as e:
        print(f"⚠️ {e}")
        return
    except OSError as e:
        _echec_enregistrement(e)
        return
    print(f"✅ Contact « {saisie.nom} » ajouté avec succès !")


def action_rechercher(carnet: Carnet) -> None:
    texte = saisir("Entrez le nom du contact recherché : ", erreur_obligatoire)
    trouves = carnet.rechercher(texte)
    if not trouves:
        print("❌ Aucun contact trouvé.")
        return
    afficher_liste(trouves)


def action_modifier(carnet: Carnet) -> None:
    nom = saisir("Nom du contact à modifier : ", erreur_obligatoire)
    try:
        actuelle = carnet.saisie(nom)
    except ContactIntrouvable:
        print("❌ Contact introuvable.")
        return

    print(f"Modification de « {actuelle.nom} ». Entrée seule : conserver ; "
          f"« {EFFACER} » : effacer le champ.")
    nouvelle = SaisieContact(
        nom=saisir_modification("Nom", actuelle.nom, obligatoire=True),
        prenom=saisir_modification("Prénom", actuelle.prenom),
        nom_famille=saisir_modification("Nom de famille", actuelle.nom_famille),
        telephone=saisir_modification("Téléphone", actuelle.telephone, erreur_telephone),
        email=saisir_modification("Adresse email", actuelle.email, erreur_email),
        notes=saisir_modification("Notes", actuelle.notes),
    )
    try:
        enregistre = carnet.modifier(actuelle.nom, nouvelle)
    except ErreurCarnet as e:
        print(f"⚠️ {e}")
        return
    except OSError as e:
        _echec_enregistrement(e)
        return
    print(f"✏️ Contact « {enregistre} » modifié avec succès.")


def action_supprimer(carnet: Carnet) -> None:
    nom = saisir("Nom du contact à supprimer : ", erreur_obligatoire)
    try:
        supprime = carnet.supprimer(nom)
    except ContactIntrouvable:
        print("❌ Contact introuvable.")
        return
    except OSError as e:
        _echec_enregistrement(e)
        return
    print(f"🗑️ Contact « {supprime} » supprimé avec succès.")


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------

ACTIONS: dict[str, tuple[str, Callable[[Carnet], None]]] = {
    "1": ("Afficher tous les contacts et détails", action_afficher),
    "2": ("Ajouter un contact", action_ajouter),
    "3": ("Rechercher un contact", action_rechercher),
    "4": ("Modifier un contact", action_modifier),
    "5": ("Supprimer un contact", action_supprimer),
}
CHOIX_QUITTER = str(len(ACTIONS) + 1)


def menu(carnet: Carnet) -> None:
    while True:
        print("\n=== GESTIONNAIRE DE CONTACTS ===")
        for cle, (libelle, _) in ACTIONS.items():
            print(f"{cle}. {libelle}")
        print(f"{CHOIX_QUITTER}. Quitter")

        choix = input(f"Choisissez une option (1-{CHOIX_QUITTER}) : ").strip()

        if choix == CHOIX_QUITTER:
            print("👋 Au revoir !")
            return
        if choix in ACTIONS:
            ACTIONS[choix][1](carnet)
        else:
            print("⚠️ Option invalide, veuillez réessayer.")


def forcer_utf8() -> None:
    # Sous Windows, la console ou une redirection peut être en cp1252, qui ne
    # sait pas encoder les emojis.
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")


def main(chemin: Path = FICHIER_CONTACTS) -> int:
    forcer_utf8()
    try:
        carnet = Carnet(chemin)
    except ErreurChargement as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    if carnet.fichier_mis_de_cote is not None:
        print(
            f"⚠️ Le fichier {chemin.name} est illisible ({carnet.detail_erreur_chargement}). "
            f"Il a été conservé sous {carnet.fichier_mis_de_cote.name} et un carnet vide est utilisé."
        )

    try:
        menu(carnet)
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Au revoir !")
    return 0

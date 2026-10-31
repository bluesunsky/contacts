"""Interface graphique PyQt6 du carnet.

Comme l'interface terminal, elle passe uniquement par service.Carnet et les
types de modele : aucune règle métier n'est réécrite ici.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .modele import NouveauContact, VueContact
from .service import Carnet, ContactExistant, DonneesInvalides, ErreurCarnet
from .stockage import FICHIER_CONTACTS, ErreurChargement

TITRE_APPLICATION = "Carnet de contacts"
STYLE_ERREUR = "color: #c62828;"
HAUTEUR_NOTES = 80


# --------------------------------------------------------------------------
# Fiche détaillée
# --------------------------------------------------------------------------


def html_contact(vue: VueContact) -> str:
    """Met en forme une fiche en HTML. Toutes les valeurs sont échappées."""
    e = escape
    blocs = [f"<h2>{e(vue.nom)}</h2>"]

    def section(titre: str, lignes: list[str]) -> None:
        blocs.append(f"<p><b>{titre}</b><br>{'<br>'.join(lignes)}</p>")

    if vue.telephones:
        section("📞 Téléphone", [f"{e(t.label)} : {e(t.valeur)}" for t in vue.telephones])
    if vue.emails:
        section("✉️ E-mail", [
            f'{e(m.label)} : <a href="mailto:{e(m.valeur)}">{e(m.valeur)}</a>'
            for m in vue.emails
        ])
    if vue.entreprise or vue.poste:
        section("🏢 Entreprise", [e(x) for x in (vue.entreprise, vue.poste) if x])
    if vue.adresse:
        section("📍 Adresse", [e(ligne) for ligne in vue.adresse])
    if vue.notes:
        section("📝 Notes", e(vue.notes).splitlines())

    if len(blocs) == 1:
        blocs.append("<p><i>Aucune information supplémentaire.</i></p>")
    return "\n".join(blocs)


# --------------------------------------------------------------------------
# Formulaire d'ajout
# --------------------------------------------------------------------------


class DialogueContact(QDialog):
    """Formulaire de création d'un contact.

    La validation est celle du service : les erreurs renvoyées par
    Carnet.ajouter sont affichées sous les champs concernés, et le
    formulaire reste ouvert tant qu'elles ne sont pas corrigées.
    """

    CHAMPS = [
        ("nom", "Nom *", ""),
        ("prenom", "Prénom", ""),
        ("nom_famille", "Nom de famille", ""),
        ("telephone", "Téléphone", "+33 6 12 34 56 78"),
        ("email", "E-mail", "nom@domaine.fr"),
    ]

    def __init__(self, carnet: Carnet, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouveau contact")
        self.setMinimumWidth(380)
        self._carnet = carnet
        self.nom_ajoute: str | None = None
        self.champs: dict[str, QLineEdit] = {}
        self.erreurs: dict[str, QLabel] = {}

        formulaire = QFormLayout()
        for cle, libelle, exemple in self.CHAMPS:
            saisie = QLineEdit()
            saisie.setPlaceholderText(exemple)
            erreur = QLabel()
            erreur.setStyleSheet(STYLE_ERREUR)
            erreur.setWordWrap(True)
            erreur.hide()
            # L'erreur disparaît dès que l'utilisateur corrige le champ.
            saisie.textEdited.connect(lambda _texte, label=erreur: label.hide())

            bloc = QVBoxLayout()
            bloc.setSpacing(2)
            bloc.addWidget(saisie)
            bloc.addWidget(erreur)
            formulaire.addRow(libelle, bloc)
            self.champs[cle] = saisie
            self.erreurs[cle] = erreur

        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(HAUTEUR_NOTES)
        formulaire.addRow("Notes", self.notes)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText("Ajouter")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addLayout(formulaire)
        disposition.addWidget(boutons)

    def contact(self) -> NouveauContact:
        valeurs = {cle: saisie.text() for cle, saisie in self.champs.items()}
        return NouveauContact(**valeurs, notes=self.notes.toPlainText())

    def afficher_erreurs(self, erreurs: dict[str, str]) -> None:
        for cle, label in self.erreurs.items():
            label.setText(erreurs.get(cle, ""))
            label.setVisible(cle in erreurs)
        premier = next((cle for cle, _, _ in self.CHAMPS if cle in erreurs), None)
        if premier:
            self.champs[premier].setFocus()

    def accept(self) -> None:
        try:
            self.nom_ajoute = self._carnet.ajouter(self.contact())
        except DonneesInvalides as e:
            self.afficher_erreurs(e.erreurs)
            return
        except ContactExistant as e:
            self.afficher_erreurs({"nom": str(e)})
            return
        except (ErreurCarnet, OSError) as e:
            QMessageBox.critical(self, TITRE_APPLICATION, f"Impossible d'enregistrer le contact.\n\n{e}")
            return
        super().accept()


# --------------------------------------------------------------------------
# Fenêtre principale
# --------------------------------------------------------------------------


class FenetrePrincipale(QMainWindow):
    """Liste filtrable des contacts à gauche, fiche détaillée à droite."""

    def __init__(self, carnet: Carnet) -> None:
        super().__init__()
        self.carnet = carnet
        self.setWindowTitle(TITRE_APPLICATION)
        self.resize(820, 520)

        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher un nom…")
        self.recherche.setClearButtonEnabled(True)

        self.liste = QListWidget()
        self.liste.setSortingEnabled(True)

        self.bouton_ajouter = QPushButton("Ajouter…")
        self.bouton_ajouter.setToolTip("Ajouter un contact (Ctrl+N)")
        self.bouton_supprimer = QPushButton("Supprimer")
        self.bouton_supprimer.setToolTip("Supprimer le contact sélectionné (Suppr)")

        boutons = QHBoxLayout()
        boutons.addWidget(self.bouton_ajouter)
        boutons.addWidget(self.bouton_supprimer)

        gauche = QWidget()
        disposition_gauche = QVBoxLayout(gauche)
        disposition_gauche.setContentsMargins(0, 0, 0, 0)
        disposition_gauche.addWidget(self.recherche)
        disposition_gauche.addWidget(self.liste)
        disposition_gauche.addLayout(boutons)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)

        separateur = QSplitter(Qt.Orientation.Horizontal)
        separateur.addWidget(gauche)
        separateur.addWidget(self.detail)
        separateur.setStretchFactor(1, 1)
        separateur.setSizes([260, 560])
        self.setCentralWidget(separateur)

        self.compteur = QLabel()
        self.statusBar().addWidget(self.compteur)

        self.recherche.textChanged.connect(lambda _texte: self.rafraichir())
        self.liste.currentItemChanged.connect(lambda *_: self.afficher_selection())
        self.bouton_ajouter.clicked.connect(self.ajouter)
        self.bouton_supprimer.clicked.connect(self.supprimer)
        QShortcut(QKeySequence.StandardKey.New, self).activated.connect(self.ajouter)
        QShortcut(QKeySequence.StandardKey.Delete, self.liste).activated.connect(self.supprimer)
        QShortcut(QKeySequence.StandardKey.Find, self).activated.connect(self.recherche.setFocus)

        self.rafraichir()

    # -- Affichage -------------------------------------------------------

    def nom_selectionne(self) -> str | None:
        element = self.liste.currentItem()
        return element.text() if element else None

    def noms_affiches(self) -> list[str]:
        return [self.liste.item(i).text() for i in range(self.liste.count())]

    def rafraichir(self, selection: str | None = None) -> None:
        """Recharge la liste selon le filtre, en gardant la sélection si possible."""
        a_selectionner = selection or self.nom_selectionne()
        vues = self.carnet.rechercher(self.recherche.text())

        self.liste.blockSignals(True)
        self.liste.clear()
        self.liste.addItems([vue.nom for vue in vues])
        self.liste.blockSignals(False)

        trouves = self.liste.findItems(a_selectionner, Qt.MatchFlag.MatchExactly) if a_selectionner else []
        if trouves:
            self.liste.setCurrentItem(trouves[0])
        elif self.liste.count():
            self.liste.setCurrentRow(0)
        self.afficher_selection()
        self.compteur.setText(f"{len(vues)} contact(s) affiché(s) sur {len(self.carnet)}")

    def afficher_selection(self) -> None:
        nom = self.nom_selectionne()
        self.bouton_supprimer.setEnabled(nom is not None)
        if nom is None:
            message = "Aucun contact trouvé." if len(self.carnet) else "Aucun contact enregistré."
            self.detail.setHtml(f"<p><i>{message}</i></p>")
            return
        self.detail.setHtml(html_contact(self.carnet.vue(nom)))

    # -- Actions ---------------------------------------------------------

    def ajouter(self) -> None:
        dialogue = DialogueContact(self.carnet, self)
        if dialogue.exec() != QDialog.DialogCode.Accepted:
            return
        # Le nouveau contact pourrait être masqué par le filtre en cours.
        self.recherche.blockSignals(True)
        self.recherche.clear()
        self.recherche.blockSignals(False)
        self.rafraichir(selection=dialogue.nom_ajoute)
        self.statusBar().showMessage(f"Contact « {dialogue.nom_ajoute} » ajouté.", 4000)

    def supprimer(self) -> None:
        nom = self.nom_selectionne()
        if nom is None:
            return
        reponse = QMessageBox.question(
            self, TITRE_APPLICATION, f"Supprimer définitivement le contact « {nom} » ?"
        )
        if reponse != QMessageBox.StandardButton.Yes:
            return

        rang = self.liste.currentRow()
        try:
            self.carnet.supprimer(nom)
        except (ErreurCarnet, OSError) as e:
            QMessageBox.critical(self, TITRE_APPLICATION, f"Impossible de supprimer le contact.\n\n{e}")
            return
        self.rafraichir()
        if self.liste.count():
            # Sélectionne le voisin du contact supprimé plutôt que le premier.
            self.liste.setCurrentRow(min(rang, self.liste.count() - 1))
        self.statusBar().showMessage(f"Contact « {nom} » supprimé.", 4000)


# --------------------------------------------------------------------------
# Lancement
# --------------------------------------------------------------------------


def main(chemin: Path = FICHIER_CONTACTS) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(TITRE_APPLICATION)

    try:
        carnet = Carnet(chemin)
    except ErreurChargement as e:
        QMessageBox.critical(None, TITRE_APPLICATION, f"Le carnet ne peut pas être ouvert.\n\n{e}")
        return 1

    fenetre = FenetrePrincipale(carnet)
    fenetre.show()

    if carnet.fichier_mis_de_cote is not None:
        QMessageBox.warning(
            fenetre,
            TITRE_APPLICATION,
            f"Le fichier {chemin.name} était illisible ({carnet.detail_erreur_chargement}).\n\n"
            f"Il a été conservé sous {carnet.fichier_mis_de_cote.name} "
            "et un carnet vide est utilisé.",
        )

    return app.exec()

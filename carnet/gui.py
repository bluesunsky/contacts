"""Interface graphique PyQt6 du carnet.

Comme l'interface terminal, elle passe uniquement par service.Carnet et les
types de modele : aucune règle métier n'est réécrite ici.
"""

from __future__ import annotations

import sys
import traceback
from html import escape
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PyQt6.QtGui import QKeySequence, QPalette, QShortcut
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

from .modele import SaisieContact, VueContact
from .service import Carnet, ContactExistant, DonneesInvalides, ErreurCarnet
from .stockage import FICHIER_CONTACTS, ErreurChargement

TITRE_APPLICATION = "Carnet de contacts"
HAUTEUR_NOTES = 80
DUREE_MESSAGE_MS = 4000
# Contraste WCAG ≥ 4,5:1 : 5,6:1 sur fond blanc, 7,1:1 sur fond #202020.
COULEUR_ERREUR_CLAIR = "#c62828"
COULEUR_ERREUR_SOMBRE = "#ff8a80"


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------


def couleur_erreur(widget: QWidget) -> str:
    """Rouge lisible sur le fond du thème actuel, clair ou sombre."""
    sombre = widget.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return COULEUR_ERREUR_SOMBRE if sombre else COULEUR_ERREUR_CLAIR


def raccourci(
    touches: str | QKeySequence.StandardKey,
    parent: QWidget,
    action: Callable[[], object],
    contexte: Qt.ShortcutContext = Qt.ShortcutContext.WindowShortcut,
) -> QShortcut:
    r = QShortcut(QKeySequence(touches), parent)
    r.setContext(contexte)
    r.activated.connect(action)
    return r


def detail_erreur(erreur: Exception) -> str:
    if isinstance(erreur, OSError) and erreur.strerror:
        return erreur.strerror
    return str(erreur)


# Boîtes de message en texte brut : un nom de contact contenant des balises
# HTML est affiché tel quel, jamais interprété.


def _boite(parent: QWidget | None, icone: QMessageBox.Icon, texte: str) -> QMessageBox:
    boite = QMessageBox(icone, TITRE_APPLICATION, texte, QMessageBox.StandardButton.Ok, parent)
    boite.setTextFormat(Qt.TextFormat.PlainText)
    return boite


def signaler_erreur(parent: QWidget | None, texte: str) -> None:
    _boite(parent, QMessageBox.Icon.Critical, texte).exec()


def avertir(parent: QWidget | None, texte: str) -> None:
    _boite(parent, QMessageBox.Icon.Warning, texte).exec()


def confirmer_suppression(parent: QWidget | None, nom: str) -> bool:
    """Demande confirmation ; Entrée et Échap annulent, seul un choix explicite supprime."""
    boite = _boite(parent, QMessageBox.Icon.Question, f"Supprimer définitivement le contact « {nom} » ?")
    boite.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    supprimer = boite.button(QMessageBox.StandardButton.Yes)
    annuler = boite.button(QMessageBox.StandardButton.No)
    supprimer.setText("&Supprimer")
    annuler.setText("Annu&ler")
    boite.setDefaultButton(annuler)
    boite.setEscapeButton(annuler)
    boite.exec()
    return boite.clickedButton() is supprimer


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
        section("Téléphone", [f"{e(t.label)} : {e(t.valeur)}" for t in vue.telephones])
    if vue.emails:
        section("E-mail", [
            f'{e(m.label)} : <a href="mailto:{e(m.valeur)}">{e(m.valeur)}</a>'
            for m in vue.emails
        ])
    if vue.entreprise or vue.poste:
        section("Entreprise", [e(x) for x in (vue.entreprise, vue.poste) if x])
    if vue.adresse:
        section("Adresse", [e(ligne) for ligne in vue.adresse])
    if vue.notes:
        section("Notes", e(vue.notes).splitlines())

    if len(blocs) == 1:
        blocs.append("<p><i>Aucune information supplémentaire.</i></p>")
    return "\n".join(blocs)


# --------------------------------------------------------------------------
# Formulaire d'ajout et de modification
# --------------------------------------------------------------------------


class DialogueContact(QDialog):
    """Formulaire de création, ou de modification si `nom` est fourni.

    La validation est celle du service : les erreurs renvoyées par Carnet
    sont affichées sous les champs concernés, et le formulaire reste ouvert
    tant qu'elles ne sont pas corrigées.
    """

    CHAMPS = [
        ("nom", "&Nom affiché *", "Alice Martin"),
        ("prenom", "&Prénom", ""),
        ("nom_famille", "Nom de &famille", ""),
        ("telephone", "&Téléphone", "+33 6 12 34 56 78"),
        ("email", "E-&mail", "nom@domaine.fr"),
    ]
    AIDES = {
        "nom": "Nom sous lequel le contact apparaît dans la liste ; il doit être unique.",
        "telephone": "Téléphone principal. Les autres numéros d'un contact importé sont conservés.",
        "email": "Adresse principale. Les autres adresses d'un contact importé sont conservées.",
    }

    def __init__(self, carnet: Carnet, parent: QWidget | None = None, nom: str | None = None) -> None:
        super().__init__(parent)
        self._carnet = carnet
        actuelle = carnet.saisie(nom) if nom is not None else None
        self.nom_origine = actuelle.nom if actuelle else None
        self.nom_enregistre: str | None = None
        self.champs: dict[str, QLineEdit] = {}
        self.erreurs: dict[str, QLabel] = {}

        self.setWindowTitle("Modifier le contact" if actuelle else "Nouveau contact")
        self.setMinimumWidth(400)
        couleur = couleur_erreur(self)

        formulaire = QFormLayout()
        for cle, libelle, exemple in self.CHAMPS:
            saisie = QLineEdit(getattr(actuelle, cle) if actuelle else "")
            saisie.setPlaceholderText(exemple)
            saisie.setAccessibleName(libelle.replace("&", "").removesuffix(" *"))
            if cle in self.AIDES:
                saisie.setToolTip(self.AIDES[cle])
            etiquette = QLabel(libelle)
            etiquette.setBuddy(saisie)  # Alt+lettre et nom lu par les lecteurs d'écran

            erreur = QLabel()
            erreur.setTextFormat(Qt.TextFormat.PlainText)
            erreur.setStyleSheet(f"color: {couleur};")
            erreur.setWordWrap(True)
            erreur.hide()
            # L'erreur disparaît dès que l'utilisateur corrige le champ.
            saisie.textEdited.connect(lambda _texte, c=cle: self._effacer_erreur(c))

            bloc = QVBoxLayout()
            bloc.setSpacing(2)
            bloc.addWidget(saisie)
            bloc.addWidget(erreur)
            formulaire.addRow(etiquette, bloc)
            self.champs[cle] = saisie
            self.erreurs[cle] = erreur

        self.notes = QPlainTextEdit(actuelle.notes if actuelle else "")
        self.notes.setFixedHeight(HAUTEUR_NOTES)
        self.notes.setTabChangesFocus(True)  # Tab passe aux boutons au lieu d'insérer \t
        self.notes.setAccessibleName("Notes")
        self.notes.setToolTip("Ctrl+Entrée pour valider le formulaire.")
        etiquette_notes = QLabel("N&otes")
        etiquette_notes.setBuddy(self.notes)
        formulaire.addRow(etiquette_notes, self.notes)

        boutons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.bouton_valider = boutons.button(QDialogButtonBox.StandardButton.Ok)
        self.bouton_valider.setText("&Enregistrer" if actuelle else "&Ajouter")
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annu&ler")
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)

        disposition = QVBoxLayout(self)
        disposition.addLayout(formulaire)
        disposition.addWidget(QLabel("* champ obligatoire"))
        disposition.addWidget(boutons)

        for touches in ("Ctrl+Return", "Ctrl+Enter"):
            raccourci(touches, self, self.accept)
        self.champs["nom"].setFocus()

    def saisie(self) -> SaisieContact:
        valeurs = {cle: champ.text() for cle, champ in self.champs.items()}
        return SaisieContact(**valeurs, notes=self.notes.toPlainText())

    def _effacer_erreur(self, cle: str) -> None:
        self.erreurs[cle].hide()
        self.champs[cle].setAccessibleDescription("")

    def afficher_erreurs(self, erreurs: dict[str, str]) -> None:
        for cle, label in self.erreurs.items():
            message = erreurs.get(cle, "")
            label.setText(message)
            label.setVisible(bool(message))
            # Lu par les lecteurs d'écran quand le champ reçoit le focus.
            self.champs[cle].setAccessibleDescription(message)
        premier = next((cle for cle, _, _ in self.CHAMPS if cle in erreurs), None)
        if premier:
            self.champs[premier].setFocus()

    def accept(self) -> None:
        saisie = self.saisie()
        try:
            if self.nom_origine is None:
                self.nom_enregistre = self._carnet.ajouter(saisie)
            else:
                self.nom_enregistre = self._carnet.modifier(self.nom_origine, saisie)
        except DonneesInvalides as e:
            self.afficher_erreurs(e.erreurs)
            return
        except ContactExistant as e:
            self.afficher_erreurs({"nom": str(e)})
            return
        except (ErreurCarnet, OSError) as e:
            signaler_erreur(self, f"Impossible d'enregistrer le contact.\n\n{detail_erreur(e)}")
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
        self.recherche.setAccessibleName("Rechercher un contact")
        self.recherche.setToolTip("Ctrl+F. Flèche bas ou Entrée : aller à la liste. Échap : effacer.")

        self.liste = QListWidget()
        self.liste.setSortingEnabled(True)
        self.liste.setAccessibleName("Contacts")

        self.bouton_ajouter = QPushButton("&Ajouter…")
        self.bouton_ajouter.setToolTip("Ajouter un contact (Ctrl+N)")
        self.bouton_modifier = QPushButton("&Modifier…")
        self.bouton_modifier.setToolTip("Modifier le contact sélectionné (F2 ou double-clic)")
        self.bouton_supprimer = QPushButton("&Supprimer")
        self.bouton_supprimer.setToolTip("Supprimer le contact sélectionné (Suppr dans la liste)")

        boutons = QHBoxLayout()
        for bouton in (self.bouton_ajouter, self.bouton_modifier, self.bouton_supprimer):
            boutons.addWidget(bouton)

        gauche = QWidget()
        disposition_gauche = QVBoxLayout(gauche)
        disposition_gauche.setContentsMargins(0, 0, 0, 0)
        disposition_gauche.addWidget(self.recherche)
        disposition_gauche.addWidget(self.liste)
        disposition_gauche.addLayout(boutons)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        self.detail.setAccessibleName("Fiche du contact")

        separateur = QSplitter(Qt.Orientation.Horizontal)
        separateur.addWidget(gauche)
        separateur.addWidget(self.detail)
        separateur.setStretchFactor(1, 1)
        separateur.setSizes([300, 520])
        self.setCentralWidget(separateur)

        self.compteur = QLabel()
        self.statusBar().addWidget(self.compteur)

        self.recherche.textChanged.connect(lambda _texte: self.rafraichir())
        self.recherche.returnPressed.connect(self.aller_a_la_liste)
        self.liste.currentItemChanged.connect(lambda *_: self.afficher_selection())
        self.liste.itemActivated.connect(lambda _element: self.modifier())  # double-clic, Entrée
        self.bouton_ajouter.clicked.connect(self.ajouter)
        self.bouton_modifier.clicked.connect(self.modifier)
        self.bouton_supprimer.clicked.connect(self.supprimer)

        widget_seul = Qt.ShortcutContext.WidgetShortcut
        raccourci(QKeySequence.StandardKey.New, self, self.ajouter)
        raccourci("F2", self, self.modifier)
        raccourci(QKeySequence.StandardKey.Find, self, self.aller_a_la_recherche)
        # Suppr ne supprime un contact que depuis la liste, jamais depuis la
        # fiche ou un bouton, pour éviter une suppression par inadvertance.
        raccourci(QKeySequence.StandardKey.Delete, self.liste, self.supprimer, widget_seul)
        raccourci("Down", self.recherche, self.aller_a_la_liste, widget_seul)
        raccourci("Escape", self.recherche, self.recherche.clear, widget_seul)

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
        for bouton in (self.bouton_modifier, self.bouton_supprimer):
            bouton.setEnabled(nom is not None)
        if nom is None:
            message = "Aucun contact trouvé." if len(self.carnet) else "Aucun contact enregistré."
            self.detail.setHtml(f"<p><i>{message}</i></p>")
            return
        self.detail.setHtml(html_contact(self.carnet.vue(nom)))

    def aller_a_la_liste(self) -> None:
        if not self.liste.count():
            return
        if self.liste.currentRow() < 0:
            self.liste.setCurrentRow(0)
        self.liste.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def aller_a_la_recherche(self) -> None:
        self.recherche.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.recherche.selectAll()

    def montrer(self, nom: str) -> None:
        """Sélectionne `nom`, en vidant le filtre s'il le masque."""
        self.rafraichir(selection=nom)
        if self.nom_selectionne() != nom:
            self.recherche.blockSignals(True)
            self.recherche.clear()
            self.recherche.blockSignals(False)
            self.rafraichir(selection=nom)
        self.liste.setFocus()

    # -- Actions ---------------------------------------------------------

    def ajouter(self) -> None:
        self._ouvrir_formulaire(None)

    def modifier(self) -> None:
        nom = self.nom_selectionne()
        if nom is not None:
            self._ouvrir_formulaire(nom)

    def _ouvrir_formulaire(self, nom: str | None) -> None:
        dialogue = DialogueContact(self.carnet, self, nom)
        try:
            if dialogue.exec() != QDialog.DialogCode.Accepted:
                return
            enregistre = dialogue.nom_enregistre
        finally:
            dialogue.deleteLater()
        self.montrer(enregistre)
        action = "ajouté" if nom is None else "modifié"
        self.statusBar().showMessage(f"Contact « {enregistre} » {action}.", DUREE_MESSAGE_MS)

    def supprimer(self) -> None:
        nom = self.nom_selectionne()
        if nom is None or not confirmer_suppression(self, nom):
            return

        rang = self.liste.currentRow()
        try:
            self.carnet.supprimer(nom)
        except (ErreurCarnet, OSError) as e:
            signaler_erreur(self, f"Impossible de supprimer le contact.\n\n{detail_erreur(e)}")
            return
        self.rafraichir()
        if self.liste.count():
            # Sélectionne le voisin du contact supprimé plutôt que le premier.
            self.liste.setCurrentRow(min(rang, self.liste.count() - 1))
            self.liste.setFocus()
        else:
            self.recherche.setFocus()  # le bouton Supprimer, désactivé, perdrait le focus
        self.statusBar().showMessage(f"Contact « {nom} » supprimé.", DUREE_MESSAGE_MS)


# --------------------------------------------------------------------------
# Lancement
# --------------------------------------------------------------------------


def installer_traduction(app: QApplication) -> None:
    """Traduit les textes propres à Qt (menus contextuels, boutons standard)."""
    if app.property("carnet_traduction"):
        return
    traducteur = QTranslator(app)
    dossier = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if traducteur.load(QLocale(QLocale.Language.French, QLocale.Country.France), "qtbase", "_", dossier):
        app.installTranslator(traducteur)
        app.setProperty("carnet_traduction", True)


def gestionnaire_exceptions(precedent: Callable) -> Callable:
    """Affiche une exception imprévue au lieu de laisser Qt fermer l'application.

    Sans gestionnaire, PyQt6 arrête le processus sans message dès qu'une
    exception sort d'un slot.
    """
    def gerer(type_exc, valeur, trace) -> None:
        if sys.stderr is not None:
            traceback.print_exception(type_exc, valeur, trace)
        try:
            signaler_erreur(
                QApplication.activeWindow(),
                f"Erreur inattendue : {type_exc.__name__}: {valeur}\n\n"
                "L'opération en cours a été interrompue.",
            )
        except Exception:
            precedent(type_exc, valeur, trace)

    return gerer


def main(chemin: Path = FICHIER_CONTACTS) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(TITRE_APPLICATION)
    installer_traduction(app)

    precedent = sys.excepthook
    sys.excepthook = gestionnaire_exceptions(precedent)
    try:
        try:
            carnet = Carnet(chemin)
        except ErreurChargement as e:
            signaler_erreur(None, f"Le carnet ne peut pas être ouvert.\n\n{e}")
            return 1

        fenetre = FenetrePrincipale(carnet)
        fenetre.show()
        if carnet.fichier_mis_de_cote is not None:
            avertir(
                fenetre,
                f"Le fichier {chemin.name} était illisible ({carnet.detail_erreur_chargement}).\n\n"
                f"Il a été conservé sous {carnet.fichier_mis_de_cote.name} "
                "et un carnet vide est utilisé.",
            )
        return app.exec()
    finally:
        sys.excepthook = precedent

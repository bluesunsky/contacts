"""Tests de l'interface graphique, exécutés sans affichage (plateforme Qt offscreen).

Ignorés seulement si PyQt6 n'est pas installé : une erreur d'import dans
carnet.gui fait échouer la suite au lieu de passer inaperçue.
"""

import importlib.util
import os
import sys
import unittest
from unittest import mock

PYQT6 = importlib.util.find_spec("PyQt6") is not None

if PYQT6:
    # Forcé (pas setdefault) : aucun test ne doit ouvrir de vraie fenêtre.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtCore import QEvent, Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox

    from carnet import gui

from carnet import Carnet
from carnet.modele import MESSAGE_EMAIL, MESSAGE_OBLIGATOIRE, VueContact, vue_contact
from carnet.stockage import charger_contacts
from tests.aide import TestAvecDossier

CONTENU = """{
    "Marie Dupont": {"Phone 1 - Value": "0612345678", "Notes": "Note de Marie"},
    "Jean Martin": {"E-mail 1 - Value": "jean@example.com", "Phone 2 - Value": "0622",
                    "Organization Name": "ACME"},
    "Ancien": {"telephone": "0102030405"}
}"""

ECHEC_ECRITURE = mock.patch("carnet.service.sauvegarder_contacts", side_effect=OSError(28, "disque plein"))


@unittest.skipUnless(PYQT6, "PyQt6 n'est pas installé.")
class TestQt(TestAvecDossier):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def carnet(self, contenu: str = CONTENU) -> Carnet:
        self.ecrire(contenu)
        return Carnet(self.chemin)

    def disque(self) -> dict:
        return charger_contacts(self.chemin).contacts

    @staticmethod
    def quand_modal(action):
        """Exécute `action(fenêtre modale)` dès qu'une boîte modale est ouverte."""
        def essayer():
            modale = QApplication.activeModalWidget()
            if modale is None:
                QTimer.singleShot(10, essayer)
            else:
                action(modale)
        QTimer.singleShot(0, essayer)


class TestHtml(TestQt):
    def test_valeurs_echappees(self):
        html = gui.html_contact(vue_contact("<b>Pirate</b>", {"Notes": "<script>x</script>"}))

        self.assertIn("&lt;b&gt;Pirate&lt;/b&gt;", html)
        self.assertNotIn("<script>", html)

    def test_email_cliquable_et_libelle_traduit(self):
        html = gui.html_contact(vue_contact("Jean", {
            "E-mail 1 - Label": "Home", "E-mail 1 - Value": "jean@example.com",
        }))

        self.assertIn('href="mailto:jean@example.com"', html)
        self.assertIn("Domicile", html)

    def test_fiche_sans_information(self):
        self.assertIn("Aucune information", gui.html_contact(VueContact(nom="Vide")))


class TestConfirmation(TestQt):
    """La vraie boîte de confirmation, pilotée au clavier."""

    def test_entree_annule(self):
        self.quand_modal(lambda m: QTest.keyClick(m, Qt.Key.Key_Return))

        self.assertFalse(gui.confirmer_suppression(None, "Bob"))

    def test_echap_annule(self):
        self.quand_modal(lambda m: QTest.keyClick(m, Qt.Key.Key_Escape))

        self.assertFalse(gui.confirmer_suppression(None, "Bob"))

    def test_bouton_supprimer_confirme_et_nom_en_texte_brut(self):
        vus = {}

        def cliquer(boite):
            vus["texte"] = boite.text()
            vus["format"] = boite.textFormat()
            vus["boutons"] = [b.text() for b in boite.buttons()]
            boite.button(QMessageBox.StandardButton.Yes).click()

        self.quand_modal(cliquer)

        self.assertTrue(gui.confirmer_suppression(None, "<b>Bob</b>"))
        self.assertIn("<b>Bob</b>", vus["texte"])
        self.assertEqual(vus["format"], Qt.TextFormat.PlainText)
        self.assertCountEqual(vus["boutons"], ["&Supprimer", "Annu&ler"])


class TestFenetre(TestQt):
    def fenetre(self, contenu: str = CONTENU):
        fenetre = gui.FenetrePrincipale(self.carnet(contenu))
        self.addCleanup(fenetre.close)
        return fenetre

    def fenetre_active(self, contenu: str = CONTENU):
        """Fenêtre affichée et active, nécessaire pour les raccourcis clavier."""
        fenetre = self.fenetre(contenu)
        fenetre.show()
        fenetre.activateWindow()
        self.assertTrue(QTest.qWaitForWindowActive(fenetre))
        return fenetre

    # -- Liste et fiche ---------------------------------------------------

    def test_liste_triee_et_premier_contact_selectionne(self):
        fenetre = self.fenetre()

        self.assertEqual(fenetre.noms_affiches(), ["Ancien", "Jean Martin", "Marie Dupont"])
        self.assertEqual(fenetre.nom_selectionne(), "Ancien")
        self.assertIn("0102030405", fenetre.detail.toPlainText())

    def test_selection_affiche_la_fiche(self):
        fenetre = self.fenetre()

        fenetre.liste.setCurrentRow(2)

        self.assertIn("Note de Marie", fenetre.detail.toPlainText())

    def test_filtre_insensible_a_la_casse(self):
        fenetre = self.fenetre()

        fenetre.recherche.setText("MART")

        self.assertEqual(fenetre.noms_affiches(), ["Jean Martin"])
        self.assertIn("1 contact(s) affiché(s) sur 3", fenetre.compteur.text())

    def test_filtre_sans_resultat_desactive_les_actions(self):
        fenetre = self.fenetre()

        fenetre.recherche.setText("zzz")

        self.assertEqual(fenetre.noms_affiches(), [])
        self.assertFalse(fenetre.bouton_modifier.isEnabled())
        self.assertFalse(fenetre.bouton_supprimer.isEnabled())
        self.assertIn("Aucun contact trouvé", fenetre.detail.toPlainText())

    def test_carnet_vide(self):
        fenetre = self.fenetre("{}")

        self.assertIn("Aucun contact enregistré", fenetre.detail.toPlainText())

    def test_noms_differant_par_la_casse_affichent_chacun_leur_fiche(self):
        fenetre = self.fenetre('{"Alice": {"Notes": "MAJ"}, "alice": {"Notes": "min"}}')

        for rang in range(2):
            fenetre.liste.setCurrentRow(rang)
            attendu = "MAJ" if fenetre.nom_selectionne() == "Alice" else "min"
            self.assertIn(attendu, fenetre.detail.toPlainText())

    def test_noms_accessibles(self):
        fenetre = self.fenetre()

        self.assertEqual(fenetre.recherche.accessibleName(), "Rechercher un contact")
        self.assertEqual(fenetre.liste.accessibleName(), "Contacts")
        self.assertEqual(fenetre.detail.accessibleName(), "Fiche du contact")

    # -- Suppression ------------------------------------------------------

    def test_suppression_confirmee_selectionne_le_voisin(self):
        fenetre = self.fenetre()
        fenetre.liste.setCurrentRow(1)  # Jean Martin

        with mock.patch.object(gui, "confirmer_suppression", return_value=True) as confirmer:
            fenetre.supprimer()

        confirmer.assert_called_once_with(fenetre, "Jean Martin")
        self.assertEqual(fenetre.noms_affiches(), ["Ancien", "Marie Dupont"])
        self.assertEqual(fenetre.nom_selectionne(), "Marie Dupont")
        self.assertNotIn("Jean Martin", self.disque())

    def test_suppression_annulee(self):
        fenetre = self.fenetre()

        with mock.patch.object(gui, "confirmer_suppression", return_value=False) as confirmer:
            fenetre.supprimer()

        confirmer.assert_called_once_with(fenetre, "Ancien")
        self.assertEqual(len(fenetre.noms_affiches()), 3)
        self.assertEqual(len(self.disque()), 3)

    def test_suppression_du_dernier_contact_garde_un_focus(self):
        fenetre = self.fenetre_active('{"Seul": {}}')
        fenetre.bouton_supprimer.setFocus()

        with mock.patch.object(gui, "confirmer_suppression", return_value=True):
            fenetre.supprimer()

        self.assertIs(QApplication.focusWidget(), fenetre.recherche)

    def test_suppression_echec_ecriture_signale_et_reste_coherente(self):
        fenetre = self.fenetre()
        fenetre.liste.setCurrentRow(1)

        with ECHEC_ECRITURE, mock.patch.object(gui, "confirmer_suppression", return_value=True), \
                mock.patch.object(gui, "signaler_erreur") as erreur:
            fenetre.supprimer()

        erreur.assert_called_once()
        self.assertIn("disque plein", erreur.call_args.args[1])
        self.assertIn("Jean Martin", fenetre.carnet)
        fenetre.liste.setCurrentRow(1)  # ne doit rien lever
        self.assertIn("ACME", fenetre.detail.toPlainText())

    # -- Ajout et modification --------------------------------------------

    def test_ajout_par_la_vraie_boucle_modale_vide_le_filtre(self):
        fenetre = self.fenetre()
        fenetre.recherche.setText("Marie")

        def remplir(dialogue):
            dialogue.champs["nom"].setText("Zoé")
            dialogue.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()

        self.quand_modal(remplir)
        fenetre.ajouter()

        self.assertEqual(fenetre.recherche.text(), "")
        self.assertEqual(len(fenetre.noms_affiches()), 4)
        self.assertEqual(fenetre.nom_selectionne(), "Zoé")
        self.assertIn("Zoé", self.disque())

    def test_annulation_par_la_vraie_boucle_modale(self):
        fenetre = self.fenetre()
        fenetre.recherche.setText("Marie")

        def annuler(dialogue):
            dialogue.champs["nom"].setText("Zoé")
            dialogue.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).click()

        self.quand_modal(annuler)
        fenetre.ajouter()

        self.assertEqual(fenetre.recherche.text(), "Marie")
        self.assertNotIn("Zoé", self.disque())

    def test_formulaire_detruit_apres_usage(self):
        fenetre = self.fenetre()

        self.quand_modal(lambda d: d.reject())
        fenetre.ajouter()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)  # exécute deleteLater

        self.assertEqual(fenetre.findChildren(gui.DialogueContact), [])

    def test_modification_renomme_et_selectionne(self):
        fenetre = self.fenetre()
        fenetre.liste.setCurrentRow(1)  # Jean Martin

        def renommer(dialogue):
            self.assertEqual(dialogue.windowTitle(), "Modifier le contact")
            self.assertEqual(dialogue.champs["email"].text(), "jean@example.com")
            dialogue.champs["nom"].setText("Jean-Pierre Martin")
            dialogue.bouton_valider.click()

        self.quand_modal(renommer)
        fenetre.modifier()

        self.assertEqual(fenetre.nom_selectionne(), "Jean-Pierre Martin")
        fiche = self.disque()["Jean-Pierre Martin"]
        self.assertEqual(fiche["Organization Name"], "ACME")  # champ non éditable conservé
        self.assertEqual(fiche["Phone 2 - Value"], "0622")

    def test_double_clic_et_f2_ouvrent_la_modification(self):
        fenetre = self.fenetre_active()
        fenetre.liste.setFocus()

        with mock.patch.object(gui.FenetrePrincipale, "_ouvrir_formulaire") as ouvrir:
            QTest.keyClick(fenetre.liste, Qt.Key.Key_F2)
            fenetre.liste.itemActivated.emit(fenetre.liste.currentItem())

        self.assertEqual([c.args for c in ouvrir.call_args_list], [("Ancien",), ("Ancien",)])

    # -- Raccourcis clavier -----------------------------------------------

    def test_suppr_dans_la_liste_demande_confirmation(self):
        fenetre = self.fenetre_active()
        fenetre.liste.setFocus()

        with mock.patch.object(gui, "confirmer_suppression", return_value=False) as confirmer:
            QTest.keyClick(fenetre.liste, Qt.Key.Key_Delete)

        confirmer.assert_called_once()

    def test_suppr_hors_de_la_liste_ne_supprime_rien(self):
        fenetre = self.fenetre_active()
        fenetre.recherche.setText("Mar")
        fenetre.recherche.setCursorPosition(0)

        with mock.patch.object(gui, "confirmer_suppression") as confirmer:
            for widget in (fenetre.recherche, fenetre.detail, fenetre.bouton_ajouter):
                widget.setFocus()
                QTest.keyClick(widget, Qt.Key.Key_Delete)

        confirmer.assert_not_called()
        self.assertEqual(fenetre.recherche.text(), "ar")  # Suppr a effacé un caractère

    def test_ctrl_n_ouvre_l_ajout(self):
        fenetre = self.fenetre_active()

        with mock.patch.object(gui.FenetrePrincipale, "_ouvrir_formulaire") as ouvrir:
            QTest.keyClick(fenetre, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)

        ouvrir.assert_called_once_with(None)

    def test_ctrl_f_selectionne_la_recherche(self):
        fenetre = self.fenetre_active()
        fenetre.recherche.setText("Mar")
        fenetre.liste.setFocus()

        QTest.keyClick(fenetre.liste, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)

        self.assertIs(QApplication.focusWidget(), fenetre.recherche)
        self.assertEqual(fenetre.recherche.selectedText(), "Mar")

    def test_fleche_bas_et_entree_menent_a_la_liste_echap_vide(self):
        fenetre = self.fenetre_active()
        fenetre.recherche.setFocus()
        QTest.keyClick(fenetre.recherche, Qt.Key.Key_Down)
        self.assertIs(QApplication.focusWidget(), fenetre.liste)

        fenetre.recherche.setFocus()
        QTest.keyClick(fenetre.recherche, Qt.Key.Key_Return)
        self.assertIs(QApplication.focusWidget(), fenetre.liste)

        fenetre.recherche.setFocus()
        QTest.keyClicks(fenetre.recherche, "Mar")
        QTest.keyClick(fenetre.recherche, Qt.Key.Key_Escape)
        self.assertEqual(fenetre.recherche.text(), "")


class TestDialogue(TestQt):
    def dialogue(self, contenu: str = CONTENU, nom: str | None = None):
        carnet = self.carnet(contenu)
        dialogue = gui.DialogueContact(carnet, nom=nom)
        self.addCleanup(dialogue.close)
        return carnet, dialogue

    def test_contact_valide_est_ajoute(self):
        carnet, dialogue = self.dialogue()
        dialogue.champs["nom"].setText("  Zoé ")
        dialogue.champs["email"].setText("zoe@example.com")
        dialogue.notes.setPlainText("Ligne 1\nLigne 2")

        dialogue.accept()

        self.assertEqual(dialogue.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialogue.nom_enregistre, "Zoé")
        fiche = self.disque()["Zoé"]
        self.assertEqual(fiche["E-mail 1 - Value"], "zoe@example.com")
        self.assertEqual(fiche["Notes"], "Ligne 1\nLigne 2")

    def test_erreurs_affichees_annoncees_et_formulaire_reste_ouvert(self):
        carnet, dialogue = self.dialogue()
        dialogue.champs["email"].setText("pas-un-mail")

        dialogue.accept()

        self.assertNotEqual(dialogue.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialogue.erreurs["nom"].text(), MESSAGE_OBLIGATOIRE)
        self.assertEqual(dialogue.erreurs["email"].text(), MESSAGE_EMAIL)
        self.assertEqual(dialogue.champs["email"].accessibleDescription(), MESSAGE_EMAIL)
        self.assertFalse(dialogue.erreurs["nom"].isHidden())
        self.assertTrue(dialogue.erreurs["telephone"].isHidden())
        self.assertEqual(len(carnet), 3)

    def test_doublon_signale_sur_le_nom_en_texte_brut(self):
        carnet, dialogue = self.dialogue('{"<b>Bob</b>": {}}')
        dialogue.champs["nom"].setText("<B>bob</B>")

        dialogue.accept()

        self.assertIn("« <b>Bob</b> » existe déjà", dialogue.erreurs["nom"].text())
        self.assertEqual(dialogue.erreurs["nom"].textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(len(carnet), 1)

    def test_erreur_masquee_quand_le_champ_est_corrige(self):
        _, dialogue = self.dialogue()
        dialogue.accept()
        self.assertFalse(dialogue.erreurs["nom"].isHidden())

        dialogue.champs["nom"].textEdited.emit("Z")

        self.assertTrue(dialogue.erreurs["nom"].isHidden())
        self.assertEqual(dialogue.champs["nom"].accessibleDescription(), "")

    def test_echec_d_enregistrement_signale_sans_fermer(self):
        carnet, dialogue = self.dialogue()
        dialogue.champs["nom"].setText("Zoé")

        with ECHEC_ECRITURE, mock.patch.object(gui, "signaler_erreur") as erreur:
            dialogue.accept()

        erreur.assert_called_once()
        self.assertIn("disque plein", erreur.call_args.args[1])
        self.assertNotEqual(dialogue.result(), QDialog.DialogCode.Accepted)
        self.assertNotIn("Zoé", carnet)
        dialogue.accept()  # un nouvel essai fonctionne, sans « existe déjà »
        self.assertEqual(dialogue.result(), QDialog.DialogCode.Accepted)

    def test_libelles_relies_aux_champs(self):
        _, dialogue = self.dialogue()

        for cle, champ in dialogue.champs.items():
            with self.subTest(champ=cle):
                self.assertTrue(champ.accessibleName())
        relies = {label.buddy() for label in dialogue.findChildren(QLabel) if label.buddy()}
        self.assertEqual(relies, set(dialogue.champs.values()) | {dialogue.notes})

    def test_tab_dans_les_notes_passe_au_bouton(self):
        _, dialogue = self.dialogue()
        dialogue.show()
        dialogue.notes.setFocus()

        QTest.keyClick(dialogue.notes, Qt.Key.Key_Tab)

        self.assertNotEqual(QApplication.focusWidget(), dialogue.notes)
        self.assertEqual(dialogue.notes.toPlainText(), "")

    def test_modification_preremplie(self):
        _, dialogue = self.dialogue(nom="marie dupont")

        self.assertEqual(dialogue.windowTitle(), "Modifier le contact")
        self.assertEqual(dialogue.bouton_valider.text(), "&Enregistrer")
        self.assertEqual(dialogue.champs["nom"].text(), "Marie Dupont")
        self.assertEqual(dialogue.champs["telephone"].text(), "0612345678")
        self.assertEqual(dialogue.notes.toPlainText(), "Note de Marie")

    def test_modification_vers_un_nom_existant(self):
        carnet, dialogue = self.dialogue(nom="Marie Dupont")
        dialogue.champs["nom"].setText("jean martin")

        dialogue.accept()

        self.assertIn("« Jean Martin » existe déjà", dialogue.erreurs["nom"].text())
        self.assertIn("Marie Dupont", carnet)


class TestLancement(TestQt):
    """gui.main sans boucle d'événements bloquante."""

    def lancer(self):
        with mock.patch.object(gui.QApplication, "exec", return_value=0) as boucle, \
                mock.patch.object(gui, "signaler_erreur") as erreur, \
                mock.patch.object(gui, "avertir") as avertissement:
            code = gui.main(self.chemin)
        for fenetre in QApplication.topLevelWidgets():
            if isinstance(fenetre, gui.FenetrePrincipale):
                fenetre.close()
                fenetre.deleteLater()
        return code, boucle, erreur, avertissement

    def test_fichier_mal_forme_code_1_sans_ouvrir_la_fenetre(self):
        self.ecrire("[]")

        code, boucle, erreur, _ = self.lancer()

        self.assertEqual(code, 1)
        erreur.assert_called_once()
        boucle.assert_not_called()
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), "[]")

    def test_fichier_corrompu_averti_et_mis_de_cote(self):
        self.ecrire("{ corrompu")

        code, boucle, _, avertissement = self.lancer()

        self.assertEqual(code, 0)
        boucle.assert_called_once()
        avertissement.assert_called_once()
        self.assertIn("illisible", avertissement.call_args.args[1])
        self.assertEqual(len(list(self.dossier.glob("contacts.*.bak"))), 1)

    def test_gestionnaire_d_exceptions_restaure_apres_main(self):
        self.ecrire("{}")
        avant = sys.excepthook

        self.lancer()

        self.assertIs(sys.excepthook, avant)

    def test_exception_imprevue_affichee_au_lieu_de_fermer(self):
        precedent = mock.Mock()
        gerer = gui.gestionnaire_exceptions(precedent)

        with mock.patch.object(gui, "signaler_erreur") as erreur, \
                mock.patch("sys.stderr", None):
            gerer(ValueError, ValueError("boum"), None)

        self.assertIn("ValueError: boum", erreur.call_args.args[1])
        precedent.assert_not_called()


if __name__ == "__main__":
    unittest.main()

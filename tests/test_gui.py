"""Tests de l'interface graphique, exécutés sans affichage (plateforme Qt offscreen).

Ignorés si PyQt6 n'est pas installé.
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

    from carnet import gui
except ImportError:  # PyQt6 absent : le mode terminal reste utilisable
    gui = None

from carnet import Carnet
from carnet.modele import MESSAGE_EMAIL, MESSAGE_OBLIGATOIRE, VueContact, vue_contact
from carnet.stockage import charger_contacts
from tests.aide import TestAvecDossier

CONTENU = """{
    "Marie Dupont": {"Phone 1 - Value": "0612345678", "Notes": "Note de Marie"},
    "Jean Martin": {"E-mail 1 - Value": "jean@example.com"},
    "Ancien": {"telephone": "0102030405"}
}"""


@unittest.skipIf(gui is None, "PyQt6 n'est pas installé.")
class TestQt(TestAvecDossier):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def carnet(self, contenu: str = CONTENU) -> Carnet:
        self.ecrire(contenu)
        return Carnet(self.chemin)


class TestHtml(TestQt):
    def test_valeurs_echappees(self):
        html = gui.html_contact(vue_contact("<b>Pirate</b>", {"Notes": "<script>x</script>"}))

        self.assertIn("&lt;b&gt;Pirate&lt;/b&gt;", html)
        self.assertNotIn("<script>", html)

    def test_email_cliquable(self):
        html = gui.html_contact(vue_contact("Jean", {"E-mail 1 - Value": "jean@example.com"}))

        self.assertIn('href="mailto:jean@example.com"', html)

    def test_fiche_sans_information(self):
        self.assertIn("Aucune information", gui.html_contact(VueContact(nom="Vide")))


class TestFenetre(TestQt):
    def fenetre(self, contenu: str = CONTENU):
        fenetre = gui.FenetrePrincipale(self.carnet(contenu))
        self.addCleanup(fenetre.close)
        return fenetre

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

    def test_filtre_sans_resultat(self):
        fenetre = self.fenetre()

        fenetre.recherche.setText("zzz")

        self.assertEqual(fenetre.noms_affiches(), [])
        self.assertFalse(fenetre.bouton_supprimer.isEnabled())
        self.assertIn("Aucun contact trouvé", fenetre.detail.toPlainText())

    def test_carnet_vide(self):
        fenetre = self.fenetre("{}")

        self.assertIn("Aucun contact enregistré", fenetre.detail.toPlainText())

    def test_suppression_confirmee_selectionne_le_voisin(self):
        fenetre = self.fenetre()
        fenetre.liste.setCurrentRow(1)  # Jean Martin

        with mock.patch.object(gui.QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            fenetre.supprimer()

        self.assertEqual(fenetre.noms_affiches(), ["Ancien", "Marie Dupont"])
        self.assertEqual(fenetre.nom_selectionne(), "Marie Dupont")
        self.assertNotIn("Jean Martin", charger_contacts(self.chemin).contacts)

    def test_suppression_annulee(self):
        fenetre = self.fenetre()

        with mock.patch.object(gui.QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            fenetre.supprimer()

        self.assertEqual(len(fenetre.noms_affiches()), 3)
        self.assertEqual(len(charger_contacts(self.chemin).contacts), 3)

    def test_ajout_vide_le_filtre_et_selectionne_le_nouveau_contact(self):
        fenetre = self.fenetre()
        fenetre.recherche.setText("Marie")

        def remplir_et_valider(dialogue):
            dialogue.champs["nom"].setText("Zoé")
            dialogue.accept()
            return dialogue.result()

        with mock.patch.object(gui.DialogueContact, "exec", remplir_et_valider):
            fenetre.ajouter()

        self.assertEqual(fenetre.recherche.text(), "")
        self.assertEqual(len(fenetre.noms_affiches()), 4)
        self.assertEqual(fenetre.nom_selectionne(), "Zoé")


class TestDialogue(TestQt):
    def dialogue(self, contenu: str = CONTENU):
        carnet = self.carnet(contenu)
        dialogue = gui.DialogueContact(carnet)
        self.addCleanup(dialogue.close)
        return carnet, dialogue

    def test_contact_valide_est_ajoute(self):
        carnet, dialogue = self.dialogue()
        dialogue.champs["nom"].setText("  Zoé ")
        dialogue.champs["email"].setText("zoe@example.com")
        dialogue.notes.setPlainText("Ligne 1\nLigne 2")

        dialogue.accept()

        self.assertEqual(dialogue.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialogue.nom_ajoute, "Zoé")
        fiche = charger_contacts(self.chemin).contacts["Zoé"]
        self.assertEqual(fiche["E-mail 1 - Value"], "zoe@example.com")
        self.assertEqual(fiche["Notes"], "Ligne 1\nLigne 2")

    def test_erreurs_affichees_sous_les_champs_et_formulaire_reste_ouvert(self):
        carnet, dialogue = self.dialogue()
        dialogue.champs["email"].setText("pas-un-mail")

        dialogue.accept()

        self.assertNotEqual(dialogue.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialogue.erreurs["nom"].text(), MESSAGE_OBLIGATOIRE)
        self.assertEqual(dialogue.erreurs["email"].text(), MESSAGE_EMAIL)
        self.assertFalse(dialogue.erreurs["nom"].isHidden())
        self.assertTrue(dialogue.erreurs["telephone"].isHidden())
        self.assertEqual(len(carnet), 3)

    def test_doublon_signale_sur_le_nom(self):
        carnet, dialogue = self.dialogue()
        dialogue.champs["nom"].setText("marie dupont")

        dialogue.accept()

        self.assertIn("'Marie Dupont' existe déjà", dialogue.erreurs["nom"].text())
        self.assertEqual(len(carnet), 3)

    def test_erreur_masquee_quand_le_champ_est_corrige(self):
        _, dialogue = self.dialogue()
        dialogue.accept()
        self.assertFalse(dialogue.erreurs["nom"].isHidden())

        dialogue.champs["nom"].textEdited.emit("Z")

        self.assertTrue(dialogue.erreurs["nom"].isHidden())

    def test_echec_d_enregistrement_signale_sans_fermer(self):
        _, dialogue = self.dialogue()
        dialogue.champs["nom"].setText("Zoé")

        with mock.patch("carnet.service.sauvegarder_contacts", side_effect=OSError("disque plein")), \
                mock.patch.object(gui.QMessageBox, "critical") as critique:
            dialogue.accept()

        critique.assert_called_once()
        self.assertIn("disque plein", critique.call_args.args[2])
        self.assertNotEqual(dialogue.result(), QDialog.DialogCode.Accepted)


if __name__ == "__main__":
    unittest.main()

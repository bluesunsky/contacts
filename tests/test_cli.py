"""Tests de l'interface terminal : saisies simulées et lancement réel du programme."""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from carnet import Carnet
from carnet import cli
from carnet.stockage import FICHIER_CONTACTS, charger_contacts
from tests.aide import TestAvecDossier

SCRIPT = Path(__file__).resolve().parent.parent / "contacts.py"


class TestActions(TestAvecDossier):
    def executer(self, action, saisies=(), contenu=None):
        """Lance une action du menu avec des saisies simulées, retourne (carnet, sortie)."""
        if contenu is not None:
            self.ecrire(contenu)
        carnet = Carnet(self.chemin)
        sortie = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(saisies)), redirect_stdout(sortie):
            action(carnet)
        return carnet, sortie.getvalue()

    def test_nom_vide_est_redemande(self):
        carnet, sortie = self.executer(
            cli.action_ajouter, ["", "  ", "Alice", "", "", "", "", ""]
        )

        self.assertEqual(sortie.count("obligatoire"), 2)
        self.assertEqual(carnet.noms, ["Alice"])

    def test_doublon_signale_avant_les_autres_saisies(self):
        carnet, sortie = self.executer(cli.action_ajouter, ["dupont"], contenu='{"Dupont": {}}')

        self.assertIn("'Dupont' existe déjà", sortie)
        self.assertEqual(carnet.noms, ["Dupont"])

    def test_telephone_et_email_invalides_sont_redemandes(self):
        carnet, sortie = self.executer(
            cli.action_ajouter,
            ["Bob", "", "", "abc", "06 12 34 56 78", "pas-un-mail", "bob@example.com", ""],
        )

        self.assertIn("Numéro invalide", sortie)
        self.assertIn("Adresse e-mail invalide", sortie)
        self.assertIn("✅ Contact 'Bob' ajouté", sortie)
        fiche = charger_contacts(self.chemin).contacts["Bob"]
        self.assertEqual(fiche["Phone 1 - Value"], "06 12 34 56 78")
        self.assertEqual(fiche["E-mail 1 - Value"], "bob@example.com")

    def test_suppression(self):
        carnet, sortie = self.executer(cli.action_supprimer, ["DUPONT"], contenu='{"Dupont": {}}')

        self.assertIn("'Dupont' supprimé", sortie)
        self.assertEqual(carnet.noms, [])

    def test_suppression_contact_inconnu(self):
        _, sortie = self.executer(cli.action_supprimer, ["Inconnu"], contenu='{"Martin": {}}')

        self.assertIn("introuvable", sortie)

    def test_recherche(self):
        _, sortie = self.executer(
            cli.action_rechercher, ["MART"], contenu='{"Jean Martin": {}, "Marie Dupont": {}}'
        )

        self.assertIn("Jean Martin", sortie)
        self.assertNotIn("Marie Dupont", sortie)

    def test_carnet_vide(self):
        _, sortie = self.executer(cli.action_afficher)

        self.assertIn("Aucun contact", sortie)


class TestFormatage(unittest.TestCase):
    def test_fiche_complete(self):
        from carnet.modele import vue_contact

        texte = cli.formater_contact(vue_contact("Jean", {
            "Phone 1 - Label": "Mobile", "Phone 1 - Value": "111111",
            "E-mail 1 - Label": "Work", "E-mail 1 - Value": "j@ex.fr",
            "Organization Name": "ACME",
            "Address 1 - Formatted": "1 rue A ::: 75000 Paris",
            "telephone": "ignoré car Phone 1 existe",
        }))

        self.assertIn("👤 Nom : Jean", texte)
        self.assertIn("📞 Mobile (1) : 111111", texte)
        self.assertIn("✉️ Work : j@ex.fr", texte)
        self.assertIn("🏢 Entreprise : ACME", texte)
        self.assertIn("📍 Adresse : 1 rue A\n      75000 Paris", texte)
        self.assertNotIn("ignoré", texte)
        self.assertNotIn("Notes", texte)

    def test_ancien_format_sans_numero(self):
        from carnet.modele import vue_contact

        texte = cli.formater_contact(vue_contact("Ancien", {"telephone": "0102030405"}))

        self.assertIn("📞 Téléphone : 0102030405", texte)


class TestProgramme(TestAvecDossier):
    """Lance le vrai script dans un sous-processus."""

    def lancer(self, entree: str, *args: str):
        return subprocess.run(
            [sys.executable, "-I", *args],
            input=entree.encode("utf-8"),
            capture_output=True,
            cwd=self.dossier,
            timeout=30,
        )

    def test_fin_d_entree_quitte_proprement(self):
        resultat = self.lancer("", str(SCRIPT))

        self.assertEqual(resultat.returncode, 0)
        self.assertNotIn(b"Traceback", resultat.stderr)
        self.assertIn("Au revoir", resultat.stdout.decode("utf-8"))

    def test_sortie_redirigee_avec_emojis_ne_plante_pas(self):
        resultat = self.lancer("1\n5\n", str(SCRIPT))

        self.assertEqual(resultat.returncode, 0, resultat.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", resultat.stderr)

    def test_lance_depuis_un_autre_dossier_utilise_le_carnet_du_projet(self):
        if not FICHIER_CONTACTS.exists():
            self.skipTest("Aucun contacts.json à la racine du projet.")
        nb_contacts = len(json.loads(FICHIER_CONTACTS.read_text(encoding="utf-8")))

        resultat = self.lancer("1\n5\n", str(SCRIPT))

        self.assertIn(f"Liste des contacts ({nb_contacts})", resultat.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

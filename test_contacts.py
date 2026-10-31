"""Tests du gestionnaire de contacts (bibliothèque standard uniquement).

Lancement : python -m unittest -v
"""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import contacts as c

SCRIPT = Path(__file__).resolve().parent / "contacts.py"


class BaseTest(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        self.dossier = Path(self._dossier.name)
        self.chemin = self.dossier / "contacts.json"

    def tearDown(self):
        self._dossier.cleanup()

    def ecrire(self, contenu: str) -> None:
        self.chemin.write_text(contenu, encoding="utf-8")

    def executer(self, fonction, *args, saisies=()):
        """Appelle une fonction en simulant les saisies clavier, retourne la sortie."""
        sortie = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(saisies)), redirect_stdout(sortie):
            fonction(*args)
        return sortie.getvalue()


class TestChargement(BaseTest):
    def test_fichier_absent_donne_un_carnet_vide(self):
        self.assertEqual(c.charger_contacts(self.chemin), {})

    def test_json_corrompu_est_mis_de_cote_et_jamais_ecrase(self):
        self.ecrire("{ corrompu")

        with redirect_stdout(io.StringIO()):
            contacts = c.charger_contacts(self.chemin)

        self.assertEqual(contacts, {})
        self.assertFalse(self.chemin.exists())
        sauvegardes = list(self.dossier.glob("contacts.*.bak"))
        self.assertEqual(len(sauvegardes), 1)
        self.assertEqual(sauvegardes[0].read_text(encoding="utf-8"), "{ corrompu")

    def test_json_liste_leve_une_erreur_explicite_sans_toucher_au_fichier(self):
        self.ecrire('[{"First Name": "A"}]')

        with self.assertRaisesRegex(c.ErreurChargement, "list"):
            c.charger_contacts(self.chemin)
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), '[{"First Name": "A"}]')

    def test_fiche_non_dictionnaire_leve_une_erreur_explicite(self):
        self.ecrire('{"Dupont": "pas une fiche"}')

        with self.assertRaisesRegex(c.ErreurChargement, "Dupont"):
            c.charger_contacts(self.chemin)

    def test_chemin_par_defaut_est_a_cote_du_script(self):
        self.assertEqual(c.FICHIER_CONTACTS, SCRIPT.parent / "contacts.json")


class TestSauvegarde(BaseTest):
    def test_aller_retour_conserve_les_accents(self):
        donnees = {"Hélène": {"Notes": "Café ☕"}}

        c.sauvegarder_contacts(donnees, self.chemin)

        self.assertEqual(c.charger_contacts(self.chemin), donnees)
        self.assertIn("Hélène", self.chemin.read_text(encoding="utf-8"))

    def test_echec_d_ecriture_laisse_le_fichier_intact_et_sans_temporaire(self):
        self.ecrire('{"Ancien": {}}')

        with mock.patch("json.dump", side_effect=RuntimeError("coupure")):
            with self.assertRaises(RuntimeError):
                c.sauvegarder_contacts({"Nouveau": {}}, self.chemin)

        self.assertEqual(self.chemin.read_text(encoding="utf-8"), '{"Ancien": {}}')
        self.assertEqual(list(self.dossier.glob("*.tmp")), [])


class TestAjout(BaseTest):
    def test_nom_vide_est_redemande(self):
        contacts = {}

        sortie = self.executer(
            c.ajouter_contact, contacts, self.chemin,
            saisies=["", "  ", "Alice", "", "", "", "", ""],
        )

        self.assertEqual(sortie.count("obligatoire"), 2)
        self.assertEqual(list(contacts), ["Alice"])

    def test_doublon_detecte_sans_tenir_compte_de_la_casse(self):
        contacts = {"Dupont": {}}

        sortie = self.executer(c.ajouter_contact, contacts, self.chemin, saisies=["dupont"])

        self.assertIn("existe déjà", sortie)
        self.assertEqual(list(contacts), ["Dupont"])

    def test_telephone_et_email_invalides_sont_redemandes(self):
        contacts = {}

        sortie = self.executer(
            c.ajouter_contact, contacts, self.chemin,
            saisies=["Bob", "", "", "abc", "06 12 34 56 78", "pas-un-mail", "bob@example.com", ""],
        )

        self.assertIn("Numéro invalide", sortie)
        self.assertIn("Adresse e-mail invalide", sortie)
        self.assertEqual(contacts["Bob"]["Phone 1 - Value"], "06 12 34 56 78")
        self.assertEqual(contacts["Bob"]["E-mail 1 - Value"], "bob@example.com")

    def test_prenom_omis_reste_vide(self):
        contacts = {}

        self.executer(c.ajouter_contact, contacts, self.chemin, saisies=["Carole", "", "", "", "", ""])

        self.assertEqual(contacts["Carole"]["First Name"], "")

    def test_ajout_est_persiste(self):
        contacts = {}

        self.executer(c.ajouter_contact, contacts, self.chemin, saisies=["Denis", "", "", "", "", ""])

        self.assertIn("Denis", c.charger_contacts(self.chemin))


class TestSuppressionEtRecherche(BaseTest):
    def test_suppression_insensible_a_la_casse(self):
        contacts = {"Dupont": {}, "Martin": {}}

        sortie = self.executer(c.supprimer_contact, contacts, self.chemin, saisies=["DUPONT"])

        self.assertIn("'Dupont' supprimé", sortie)
        self.assertEqual(list(contacts), ["Martin"])
        self.assertEqual(list(c.charger_contacts(self.chemin)), ["Martin"])

    def test_suppression_contact_inconnu(self):
        contacts = {"Martin": {}}

        sortie = self.executer(c.supprimer_contact, contacts, self.chemin, saisies=["Inconnu"])

        self.assertIn("introuvable", sortie)
        self.assertFalse(self.chemin.exists())

    def test_recherche_partielle_insensible_a_la_casse(self):
        contacts = {"Jean Martin": {}, "Marie Dupont": {}}

        sortie = self.executer(c.rechercher_contact, contacts, saisies=["MART"])

        self.assertIn("Jean Martin", sortie)
        self.assertNotIn("Marie Dupont", sortie)


class TestAffichage(unittest.TestCase):
    def afficher(self, infos):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            c.afficher_contact("Test", infos)
        return sortie.getvalue()

    def test_champs_vides_ne_sont_pas_affiches(self):
        sortie = self.afficher({
            "E-mail 1 - Label": "Home", "E-mail 1 - Value": "",
            "Organization Name": "", "Notes": "",
        })

        self.assertNotIn("✉️", sortie)
        self.assertNotIn("Entreprise", sortie)
        self.assertNotIn("Notes", sortie)

    def test_telephones_tries_par_numero_avec_label(self):
        sortie = self.afficher({
            "Phone 2 - Label": "Work", "Phone 2 - Value": "222222",
            "Phone 1 - Label": "Mobile", "Phone 1 - Value": "111111",
        })

        self.assertLess(sortie.index("Mobile (1) : 111111"), sortie.index("Work (2) : 222222"))

    def test_cle_ressemblante_n_est_pas_prise_pour_un_telephone(self):
        sortie = self.afficher({"Phone Value Notes": "pas un numéro"})

        self.assertNotIn("📞", sortie)

    def test_retrocompatibilite_ancien_format(self):
        sortie = self.afficher({"telephone": "0102030405", "email": "a@b.fr"})

        self.assertIn("Téléphone : 0102030405", sortie)
        self.assertIn("Email : a@b.fr", sortie)

    def test_adresse_multiligne(self):
        sortie = self.afficher({"Address 1 - Formatted": "1 rue A ::: 75000 Paris"})

        self.assertIn("1 rue A\n      75000 Paris", sortie)


class TestProgramme(BaseTest):
    """Lance le vrai script dans un sous-processus."""

    def lancer(self, entree: str, dossier_courant: Path):
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT)],
            input=entree.encode("utf-8"),
            capture_output=True,
            cwd=dossier_courant,
            timeout=30,
        )

    def test_fin_d_entree_quitte_proprement(self):
        resultat = self.lancer("", self.dossier)

        self.assertEqual(resultat.returncode, 0)
        self.assertNotIn(b"Traceback", resultat.stderr)
        self.assertIn("Au revoir", resultat.stdout.decode("utf-8"))

    def test_sortie_redirigee_avec_emojis_ne_plante_pas(self):
        # Sous Windows, une sortie redirigée est en cp1252 par défaut.
        resultat = self.lancer("1\n5\n", self.dossier)

        self.assertEqual(resultat.returncode, 0, resultat.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", resultat.stderr)

    def test_lance_depuis_un_autre_dossier_utilise_le_carnet_du_script(self):
        if not c.FICHIER_CONTACTS.exists():
            self.skipTest("Aucun contacts.json à côté du script.")
        nb_contacts = len(json.loads(c.FICHIER_CONTACTS.read_text(encoding="utf-8")))

        resultat = self.lancer("1\n5\n", self.dossier)

        self.assertIn(f"Liste des contacts ({nb_contacts})", resultat.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

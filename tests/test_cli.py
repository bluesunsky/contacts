"""Tests de l'interface terminal : saisies simulées et lancement réel du programme."""

import io
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from carnet import Carnet, cli
from carnet.modele import vue_contact
from carnet.stockage import charger_contacts
from tests.aide import TestAvecDossier

RACINE = Path(__file__).resolve().parent.parent

ECHEC_ECRITURE = mock.patch("carnet.service.sauvegarder_contacts", side_effect=OSError("disque plein"))


def simuler(saisies, fonction, *args):
    """Exécute `fonction` avec des saisies clavier simulées, retourne (résultat, sortie).

    Comme un vrai terminal, la sortie contient les invites. Une exception
    dans `saisies` est levée à la place de la saisie (Ctrl+C par exemple).
    """
    reponses = iter(saisies)

    def faux_input(invite=""):
        print(invite, end="")
        reponse = next(reponses)
        if isinstance(reponse, BaseException):
            raise reponse
        return reponse

    sortie = io.StringIO()
    with mock.patch("builtins.input", faux_input), redirect_stdout(sortie):
        resultat = fonction(*args)
    return resultat, sortie.getvalue()


class TestActions(TestAvecDossier):
    def executer(self, action, saisies=(), contenu=None):
        """Lance une action du menu avec des saisies simulées, retourne (carnet, sortie)."""
        if contenu is not None:
            self.ecrire(contenu)
        carnet = Carnet(self.chemin)
        _, sortie = simuler(saisies, action, carnet)
        return carnet, sortie

    # -- Ajout -----------------------------------------------------------

    def test_nom_vide_est_redemande(self):
        carnet, sortie = self.executer(cli.action_ajouter, ["", "  ", "Alice", "", "", "", "", ""])

        self.assertEqual(sortie.count("obligatoire"), 2)
        self.assertEqual(carnet.noms, ["Alice"])

    def test_doublon_signale_avant_les_autres_saisies(self):
        carnet, sortie = self.executer(cli.action_ajouter, ["dupont"], contenu='{"Dupont": {}}')

        self.assertIn("« Dupont » existe déjà", sortie)
        self.assertEqual(carnet.noms, ["Dupont"])

    def test_telephone_et_email_invalides_sont_redemandes(self):
        _, sortie = self.executer(
            cli.action_ajouter,
            ["Bob", "", "", "abc", "06 12 34 56 78", "pas-un-mail", "bob@example.com", ""],
        )

        self.assertIn("Numéro invalide", sortie)
        self.assertIn("Adresse e-mail invalide", sortie)
        self.assertIn("✅ Contact « Bob » ajouté", sortie)
        fiche = charger_contacts(self.chemin).contacts["Bob"]
        self.assertEqual(fiche["Phone 1 - Value"], "+33 6 12 34 56 78")
        self.assertEqual(fiche["E-mail 1 - Value"], "bob@example.com")

    def test_ajout_echec_ecriture_signale_sans_planter(self):
        with ECHEC_ECRITURE:
            carnet, sortie = self.executer(cli.action_ajouter, ["Zoé", "", "", "", "", ""])

        self.assertIn("Impossible d'enregistrer", sortie)
        self.assertEqual(carnet.noms, [])

    # -- Modification ----------------------------------------------------

    def test_modification_entree_conserve_et_tiret_efface(self):
        contenu = '{"Bob": {"First Name": "Robert", "Phone 1 - Value": "0611111111", "Notes": "vieux"}}'

        carnet, sortie = self.executer(
            cli.action_modifier,
            ["bob", "", "", "Martin", "", "-", "-"],
            contenu=contenu,
        )

        self.assertIn("[Robert]", sortie)
        self.assertIn("✏️ Contact « Bob » modifié", sortie)
        fiche = charger_contacts(self.chemin).contacts["Bob"]
        self.assertEqual(fiche["First Name"], "Robert")
        self.assertEqual(fiche["Last Name"], "Martin")
        self.assertEqual(fiche["Phone 1 - Value"], "+33 6 11 11 11 11")
        self.assertEqual(fiche["E-mail 1 - Value"], "")
        self.assertEqual(fiche["Notes"], "")

    def test_modification_renommage(self):
        carnet, _ = self.executer(
            cli.action_modifier, ["Bob", "Robert", "", "", "", "", ""], contenu='{"Bob": {}}'
        )

        self.assertEqual(carnet.noms, ["Robert"])

    def test_modification_nom_efface_refuse_puis_conserve(self):
        carnet, sortie = self.executer(
            cli.action_modifier, ["Bob", "-", "", "", "", "", "", ""], contenu='{"Bob": {}}'
        )

        self.assertIn("obligatoire", sortie)
        self.assertEqual(carnet.noms, ["Bob"])

    def test_modification_valeur_invalide_redemandee(self):
        _, sortie = self.executer(
            cli.action_modifier, ["Bob", "", "", "", "abc", "", "", ""], contenu='{"Bob": {}}'
        )

        self.assertIn("Numéro invalide", sortie)

    def test_modification_vers_nom_existant(self):
        carnet, sortie = self.executer(
            cli.action_modifier,
            ["Bob", "alice", "", "", "", "", ""],
            contenu='{"Bob": {}, "Alice": {}}',
        )

        self.assertIn("« Alice » existe déjà", sortie)
        self.assertEqual(carnet.noms, ["Bob", "Alice"])

    def test_modification_contact_inconnu(self):
        _, sortie = self.executer(cli.action_modifier, ["Inconnu"], contenu="{}")

        self.assertIn("introuvable", sortie)

    # -- Suppression, recherche, affichage --------------------------------

    def test_suppression(self):
        carnet, sortie = self.executer(cli.action_supprimer, ["DUPONT"], contenu='{"Dupont": {}}')

        self.assertIn("« Dupont » supprimé", sortie)
        self.assertEqual(carnet.noms, [])

    def test_suppression_contact_inconnu(self):
        _, sortie = self.executer(cli.action_supprimer, ["Inconnu"], contenu='{"Martin": {}}')

        self.assertIn("introuvable", sortie)

    def test_suppression_echec_ecriture_signale_sans_planter(self):
        with ECHEC_ECRITURE:
            carnet, sortie = self.executer(cli.action_supprimer, ["Dupont"], contenu='{"Dupont": {}}')

        self.assertIn("Impossible d'enregistrer", sortie)
        self.assertEqual(carnet.noms, ["Dupont"])

    def test_recherche(self):
        _, sortie = self.executer(
            cli.action_rechercher, ["MART"], contenu='{"Jean Martin": {}, "Marie Dupont": {}}'
        )

        self.assertIn("Jean Martin", sortie)
        self.assertNotIn("Marie Dupont", sortie)

    def test_recherche_sans_resultat(self):
        _, sortie = self.executer(cli.action_rechercher, ["zzz"], contenu='{"Jean": {}}')

        self.assertIn("Aucun contact trouvé", sortie)

    def test_carnet_vide(self):
        _, sortie = self.executer(cli.action_afficher)

        self.assertIn("Aucun contact", sortie)


class TestMain(TestAvecDossier):
    """cli.main dans le processus des tests, sur un carnet temporaire."""

    def lancer(self, saisies):
        erreurs = io.StringIO()
        with mock.patch("carnet.cli.forcer_utf8"), redirect_stderr(erreurs):
            code, sortie = simuler(saisies, cli.main, self.chemin)
        return code, sortie, erreurs.getvalue()

    def test_option_invalide_puis_quitter(self):
        code, sortie, _ = self.lancer(["9", cli.CHOIX_QUITTER])

        self.assertEqual(code, 0)
        self.assertIn("Option invalide", sortie)
        self.assertIn("Au revoir", sortie)

    def test_ctrl_c_quitte_proprement(self):
        code, sortie, _ = self.lancer([KeyboardInterrupt()])

        self.assertEqual(code, 0)
        self.assertIn("Au revoir", sortie)

    def test_fichier_mal_forme_code_1_sans_modifier_le_fichier(self):
        self.ecrire("[]")

        code, _, erreurs = self.lancer([])

        self.assertEqual(code, 1)
        self.assertIn("list", erreurs)
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), "[]")

    def test_fichier_corrompu_signale_et_mis_de_cote(self):
        self.ecrire("{ corrompu")

        code, sortie, _ = self.lancer([cli.CHOIX_QUITTER])

        self.assertEqual(code, 0)
        self.assertIn("illisible", sortie)
        self.assertEqual(len(list(self.dossier.glob("contacts.*.bak"))), 1)


class TestFormatage(unittest.TestCase):
    def test_fiche_complete(self):
        texte = cli.formater_contact(vue_contact("Jean", {
            "Phone 1 - Label": "Mobile", "Phone 1 - Value": "111111",
            "E-mail 1 - Label": "Work", "E-mail 1 - Value": "j@ex.fr",
            "Organization Name": "ACME",
            "Address 1 - Formatted": "1 rue A ::: 75000 Paris",
            "telephone": "ignoré car Phone 1 existe",
        }))

        self.assertIn("👤 Nom : Jean", texte)
        self.assertIn("📞 Mobile (1) : 111111", texte)
        self.assertIn("✉️ Travail : j@ex.fr", texte)
        self.assertIn("🏢 Entreprise : ACME", texte)
        self.assertIn("📍 Adresse : 1 rue A\n      75000 Paris", texte)
        self.assertNotIn("ignoré", texte)
        self.assertNotIn("Notes", texte)

    def test_ancien_format_sans_numero(self):
        texte = cli.formater_contact(vue_contact("Ancien", {"telephone": "0102030405"}))

        self.assertIn("📞 Téléphone : 0102030405", texte)


class TestProgramme(TestAvecDossier):
    """Lance le vrai script dans un sous-processus, sur une copie du projet.

    Le carnet est cherché à côté du script : travailler sur une copie garantit
    que le vrai contacts.json n'est jamais lu ni modifié par les tests.
    """

    def setUp(self):
        super().setUp()
        self.projet = self.dossier / "projet"
        shutil.copytree(
            RACINE / "carnet", self.projet / "carnet",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copy(RACINE / "contacts.py", self.projet)
        self.carnet_copie = self.projet / "contacts.json"
        self.ailleurs = self.dossier / "ailleurs"
        self.ailleurs.mkdir()

    def lancer(self, entree: str, *options: str):
        resultat = subprocess.run(
            [sys.executable, "-I", str(self.projet / "contacts.py"), *options],
            input=entree.encode("utf-8"),
            capture_output=True,
            cwd=self.ailleurs,
            timeout=30,
        )
        return resultat, resultat.stdout.decode("utf-8"), resultat.stderr.decode("utf-8", "replace")

    def test_lance_depuis_un_autre_dossier_utilise_le_carnet_du_projet(self):
        self.carnet_copie.write_text('{"A": {}, "B": {}}', encoding="utf-8")

        resultat, sortie, erreurs = self.lancer(f"1\n{cli.CHOIX_QUITTER}\n", "--console")

        self.assertEqual(resultat.returncode, 0, erreurs)
        self.assertIn("Liste des contacts (2)", sortie)
        self.assertEqual(list(self.ailleurs.iterdir()), [])  # rien créé dans le dossier courant

    def test_fin_d_entree_quitte_proprement(self):
        resultat, sortie, erreurs = self.lancer("", "--console")

        self.assertEqual(resultat.returncode, 0)
        self.assertNotIn("Traceback", erreurs)
        self.assertIn("Au revoir", sortie)

    def test_sortie_redirigee_avec_emojis_ne_plante_pas(self):
        self.carnet_copie.write_text('{"Émile": {"Notes": "☕"}}', encoding="utf-8")

        resultat, sortie, erreurs = self.lancer(f"1\n{cli.CHOIX_QUITTER}\n", "--console")

        self.assertEqual(resultat.returncode, 0, erreurs)
        self.assertNotIn("UnicodeEncodeError", erreurs)
        self.assertIn("👤 Nom : Émile", sortie)

    def test_fichier_mal_forme_code_de_sortie_1(self):
        self.carnet_copie.write_text("[]", encoding="utf-8")

        resultat, _, erreurs = self.lancer("", "--console")

        self.assertEqual(resultat.returncode, 1)
        self.assertIn("list", erreurs)

    def test_phonenumbers_absent_message_sans_trace(self):
        """Par contacts.py comme par python -m carnet."""
        bloquer = "import sys, runpy; sys.modules['phonenumbers'] = None; "
        lancements = {
            "contacts.py": "sys.argv = ['contacts.py', '--console']; "
                           "runpy.run_path('contacts.py', run_name='__main__')",
            "-m carnet": "sys.path.insert(0, '.'); sys.argv = ['carnet', '--console']; "
                         "runpy.run_module('carnet', run_name='__main__', alter_sys=True)",
        }
        for nom, code in lancements.items():
            with self.subTest(lancement=nom):
                resultat = subprocess.run(
                    [sys.executable, "-I", "-c", bloquer + code],
                    capture_output=True, cwd=self.projet, timeout=30,
                )
                erreurs = resultat.stderr.decode("utf-8", "replace")
                self.assertEqual(resultat.returncode, 1, erreurs)
                self.assertIn("pip install -r requirements.txt", erreurs)
                self.assertNotIn("Traceback", erreurs)



if __name__ == "__main__":
    unittest.main()

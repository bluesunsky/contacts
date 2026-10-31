import unittest
from pathlib import Path
from unittest import mock

from carnet.stockage import (
    FICHIER_CONTACTS,
    ErreurChargement,
    charger_contacts,
    sauvegarder_contacts,
)
from tests.aide import TestAvecDossier

RACINE = Path(__file__).resolve().parent.parent


class TestChargement(TestAvecDossier):
    def test_fichier_absent_donne_un_carnet_vide(self):
        resultat = charger_contacts(self.chemin)

        self.assertEqual(resultat.contacts, {})
        self.assertIsNone(resultat.fichier_mis_de_cote)

    def test_json_corrompu_est_mis_de_cote_et_jamais_ecrase(self):
        self.ecrire("{ corrompu")

        resultat = charger_contacts(self.chemin)

        self.assertEqual(resultat.contacts, {})
        self.assertFalse(self.chemin.exists())
        self.assertTrue(resultat.fichier_mis_de_cote.name.endswith(".bak"))
        self.assertEqual(resultat.fichier_mis_de_cote.read_text(encoding="utf-8"), "{ corrompu")
        self.assertIn("ligne 1", resultat.detail_erreur)

    def test_json_liste_leve_une_erreur_sans_toucher_au_fichier(self):
        self.ecrire('[{"First Name": "A"}]')

        with self.assertRaisesRegex(ErreurChargement, "list"):
            charger_contacts(self.chemin)
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), '[{"First Name": "A"}]')

    def test_fiche_non_dictionnaire_leve_une_erreur(self):
        self.ecrire('{"Dupont": "pas une fiche"}')

        with self.assertRaisesRegex(ErreurChargement, "Dupont"):
            charger_contacts(self.chemin)

    def test_chemin_par_defaut_a_la_racine_du_projet(self):
        self.assertEqual(FICHIER_CONTACTS, RACINE / "contacts.json")


class TestSauvegarde(TestAvecDossier):
    def test_aller_retour_conserve_les_accents(self):
        donnees = {"Hélène": {"Notes": "Café ☕"}}

        sauvegarder_contacts(donnees, self.chemin)

        self.assertEqual(charger_contacts(self.chemin).contacts, donnees)
        self.assertIn("Hélène", self.chemin.read_text(encoding="utf-8"))

    def test_echec_d_ecriture_laisse_le_fichier_intact_et_sans_temporaire(self):
        self.ecrire('{"Ancien": {}}')

        with mock.patch("json.dump", side_effect=RuntimeError("coupure")):
            with self.assertRaises(RuntimeError):
                sauvegarder_contacts({"Nouveau": {}}, self.chemin)

        self.assertEqual(self.chemin.read_text(encoding="utf-8"), '{"Ancien": {}}')
        self.assertEqual(list(self.dossier.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

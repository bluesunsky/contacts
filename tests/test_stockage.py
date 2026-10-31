import json
import unittest
from datetime import datetime
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

    def test_deux_fichiers_corrompus_dans_la_meme_seconde_tous_deux_conserves(self):
        fige = mock.Mock(wraps=datetime)
        fige.now.return_value = datetime(2026, 10, 31, 14, 5, 1)

        with mock.patch("carnet.stockage.datetime", fige):
            self.ecrire("{ abîmé 1")
            charger_contacts(self.chemin)
            self.ecrire("{ abîmé 2")
            charger_contacts(self.chemin)

        contenus = sorted(p.read_text(encoding="utf-8") for p in self.dossier.glob("contacts.*.bak"))
        self.assertEqual(contenus, ["{ abîmé 1", "{ abîmé 2"])

    def test_bom_utf8_accepte(self):
        self.chemin.write_bytes('﻿{"Émile": {}}'.encode("utf-8"))

        resultat = charger_contacts(self.chemin)

        self.assertEqual(resultat.contacts, {"Émile": {}})
        self.assertIsNone(resultat.fichier_mis_de_cote)

    def test_fichier_cp1252_refuse_sans_le_modifier(self):
        contenu = '{"Émile": {}}'.encode("cp1252")
        self.chemin.write_bytes(contenu)

        with self.assertRaisesRegex(ErreurChargement, "UTF-8"):
            charger_contacts(self.chemin)
        self.assertEqual(self.chemin.read_bytes(), contenu)

    def test_fichier_inaccessible_leve_erreur_chargement(self):
        self.chemin.mkdir()  # un dossier à la place du fichier

        with self.assertRaisesRegex(ErreurChargement, "Impossible de lire"):
            charger_contacts(self.chemin)

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

    def test_caractere_isole_invalide_reste_enregistrable(self):
        self.ecrire('{"A": {"Notes": "\\ud83d"}}')  # demi-paire UTF-16 seule
        donnees = charger_contacts(self.chemin).contacts

        sauvegarder_contacts(donnees, self.chemin)

        self.assertEqual(charger_contacts(self.chemin).contacts, donnees)
        json.loads(self.chemin.read_text(encoding="utf-8"))  # JSON toujours valide

    def test_echec_d_ecriture_laisse_le_fichier_intact_et_sans_temporaire(self):
        self.ecrire('{"Ancien": {}}')

        with mock.patch("carnet.stockage.os.replace", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                sauvegarder_contacts({"Nouveau": {}}, self.chemin)

        self.assertEqual(self.chemin.read_text(encoding="utf-8"), '{"Ancien": {}}')
        self.assertEqual(list(self.dossier.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

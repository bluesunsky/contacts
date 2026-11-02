import json
import sqlite3
import unittest
from contextlib import closing
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
        self.assertEqual(FICHIER_CONTACTS, RACINE / "contacts.db")


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


class TestAvecBase(TestAvecDossier):
    def setUp(self):
        super().setUp()
        self.base = self.dossier / "contacts.db"

    def modifier_base(self, requete: str) -> None:
        with closing(sqlite3.connect(self.base)) as base, base:
            base.execute(requete)

    def lire_base(self, requete: str) -> list[tuple]:
        with closing(sqlite3.connect(self.base)) as base:
            return base.execute(requete).fetchall()


FICHE_COMPLETE = {
    "First Name": "Jean",
    "Last Name": "Martin",
    "Phone 1 - Label": "Mobile",
    "Phone 1 - Value": "+33 6 98 76 54 32",
    "Phone 2 - Label": "Work",
    "Phone 2 - Value": "+33 1 23 45 67 89",
    "E-mail 1 - Label": "Work",
    "E-mail 1 - Value": "jean@exemple.fr",
    "Organization Name": "ACME",
    "Organization Title": "Directeur",
    "Address 1 - Formatted": "1 rue de la Paix ::: 75002 Paris",
    "Notes": "Café ☕",
    "Birthday": "1980-05-12",
}


class TestSqlite(TestAvecBase):
    def test_base_absente_donne_un_carnet_vide_sans_creer_de_fichier(self):
        resultat = charger_contacts(self.base)

        self.assertEqual(resultat.contacts, {})
        self.assertFalse(self.base.exists())

    def test_aller_retour_conserve_fiches_accents_et_ordre(self):
        donnees = {
            "Zoé": {"Notes": "Café ☕", "Phone 1 - Value": "+33 6 12 34 56 78"},
            "Jean Martin": FICHE_COMPLETE,
            "Albert": {},
        }

        sauvegarder_contacts(donnees, self.base)
        relu = charger_contacts(self.base).contacts

        self.assertEqual(relu, donnees)
        self.assertEqual(list(relu), ["Zoé", "Jean Martin", "Albert"])

    def test_champs_simples_enregistres_dans_les_colonnes(self):
        sauvegarder_contacts({"Jean Martin": FICHE_COMPLETE}, self.base)

        self.assertEqual(
            self.lire_base(
                "SELECT id, nom, prenom, nom_famille, entreprise, poste, adresse, notes FROM contacts"
            ),
            [(1, "Jean Martin", "Jean", "Martin", "ACME", "Directeur",
              "1 rue de la Paix ::: 75002 Paris", "Café ☕")],
        )

    def test_telephones_et_emails_enregistres_un_par_ligne(self):
        sauvegarder_contacts({"Jean Martin": FICHE_COMPLETE}, self.base)

        self.assertEqual(
            self.lire_base("SELECT * FROM telephones ORDER BY numero"),
            [(1, 1, "Mobile", "+33 6 98 76 54 32"), (1, 2, "Work", "+33 1 23 45 67 89")],
        )
        self.assertEqual(self.lire_base("SELECT * FROM emails"), [(1, 1, "Work", "jean@exemple.fr")])

    def test_champ_non_gere_conserve_dans_autres_champs(self):
        fiche = {"Birthday": "1980-05-12", "telephone": "01 02 03 04 05", "Phone 01 - Value": "x"}

        sauvegarder_contacts({"A": fiche}, self.base)

        self.assertEqual(
            sorted(self.lire_base("SELECT cle, valeur FROM autres_champs")),
            [("Birthday", "1980-05-12"), ("Phone 01 - Value", "x"), ("telephone", "01 02 03 04 05")],
        )
        self.assertEqual(charger_contacts(self.base).contacts, {"A": fiche})

    def test_champ_absent_distinct_d_un_champ_vide(self):
        donnees = {"A": {"Notes": "", "Phone 1 - Label": "Mobile"}}

        sauvegarder_contacts(donnees, self.base)

        self.assertEqual(self.lire_base("SELECT prenom, notes FROM contacts"), [(None, "")])
        self.assertEqual(charger_contacts(self.base).contacts, donnees)

    def test_champ_none_traite_comme_absent(self):
        sauvegarder_contacts({"A": {"Notes": None, "Birthday": None}}, self.base)

        self.assertEqual(charger_contacts(self.base).contacts, {"A": {}})

    def test_suppression_retire_aussi_les_champs_du_contact(self):
        sauvegarder_contacts({"Jean Martin": FICHE_COMPLETE, "B": {}}, self.base)

        sauvegarder_contacts({"B": {}}, self.base)

        self.assertEqual(self.lire_base("SELECT COUNT(*) FROM telephones"), [(0,)])
        self.assertEqual(self.lire_base("SELECT COUNT(*) FROM autres_champs"), [(0,)])

    def test_sauvegarde_remplace_tout_le_contenu(self):
        sauvegarder_contacts({"Ancien": {}, "Gardé": {}}, self.base)

        sauvegarder_contacts({"Gardé": {}, "Nouveau": {}}, self.base)

        self.assertEqual(list(charger_contacts(self.base).contacts), ["Gardé", "Nouveau"])

    def test_caractere_isole_invalide_remplace_a_l_enregistrement(self):
        donnees = {"A\ud83d": {"Notes": "x\ud83d"}}  # demi-paire UTF-16 seule

        sauvegarder_contacts(donnees, self.base)

        self.assertEqual(charger_contacts(self.base).contacts, {"A�": {"Notes": "x�"}})

    def test_echec_d_ecriture_laisse_la_base_et_sa_version_intactes(self):
        sauvegarder_contacts({"Ancien": {"Notes": "n"}}, self.base)
        self.modifier_base("PRAGMA user_version = 0")
        noms_en_double = {"A\ud83d": {}, "A\udc00": {}}  # identiques une fois remplacés

        with self.assertRaisesRegex(OSError, "contacts.db"):
            sauvegarder_contacts(noms_en_double, self.base)

        self.assertEqual(self.lire_base("PRAGMA user_version"), [(0,)])
        self.assertEqual(self.lire_base("SELECT nom, notes FROM contacts"), [("Ancien", "n")])

    def test_fichier_qui_n_est_pas_une_base_refuse_sans_le_modifier(self):
        self.base.write_text("pas une base", encoding="utf-8")

        with self.assertRaisesRegex(ErreurChargement, "Impossible de lire la base"):
            charger_contacts(self.base)
        self.assertEqual(self.base.read_text(encoding="utf-8"), "pas une base")

    def test_ecriture_dans_un_fichier_qui_n_est_pas_une_base_leve_oserror(self):
        self.base.write_text("pas une base", encoding="utf-8")

        with self.assertRaisesRegex(OSError, "contacts.db"):
            sauvegarder_contacts({"A": {}}, self.base)
        self.assertEqual(self.base.read_text(encoding="utf-8"), "pas une base")

    def test_base_sans_table_donne_un_carnet_vide(self):
        sqlite3.connect(self.base).close()  # fichier vide : base valide sans table

        self.assertEqual(charger_contacts(self.base).contacts, {})

    def test_base_d_un_autre_format_refusee_sans_la_modifier(self):
        self.modifier_base("CREATE TABLE contacts (position INTEGER PRIMARY KEY, nom TEXT, fiche TEXT)")
        avant = self.base.read_bytes()

        with self.assertRaisesRegex(ErreurChargement, "format attendu"):
            charger_contacts(self.base)
        self.assertEqual(self.base.read_bytes(), avant)


class TestImportJson(TestAvecBase):
    def test_json_importe_dans_la_base_et_laisse_intact(self):
        contenu = '{"Hélène": {"Notes": "importée"}, "Albert": {}}'
        self.ecrire(contenu)

        resultat = charger_contacts(self.base)

        attendu = {"Hélène": {"Notes": "importée"}, "Albert": {}}
        self.assertEqual(resultat.contacts, attendu)
        self.assertTrue(self.base.exists())
        self.assertEqual(list(charger_contacts(self.base).contacts), ["Hélène", "Albert"])
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), contenu)

    def test_nombres_importes_en_texte(self):
        self.ecrire('{"A": {"Notes": 0, "Birthday": 1980, "Organization Name": null}}')

        resultat = charger_contacts(self.base)

        self.assertEqual(resultat.contacts, {"A": {"Notes": "0", "Birthday": "1980"}})

    def test_valeur_composee_refusee_sans_creer_la_base(self):
        self.ecrire('{"Dupont": {"Notes": ["a", "b"]}}')

        with self.assertRaisesRegex(ErreurChargement, "« Notes » de « Dupont »"):
            charger_contacts(self.base)
        self.assertFalse(self.base.exists())

    def test_base_vide_de_0_octet_n_empeche_pas_l_import(self):
        self.ecrire('{"Alice": {"Notes": "importée"}}')
        self.base.write_bytes(b"")

        resultat = charger_contacts(self.base)

        self.assertEqual(resultat.contacts, {"Alice": {"Notes": "importée"}})
        self.assertEqual(self.lire_base("SELECT nom FROM contacts"), [("Alice",)])

    def test_json_ignore_une_fois_la_base_creee(self):
        self.ecrire('{"Ancien": {}}')
        charger_contacts(self.base)
        sauvegarder_contacts({"Nouveau": {}}, self.base)

        self.assertEqual(charger_contacts(self.base).contacts, {"Nouveau": {}})

    def test_json_invalide_refuse_sans_creer_la_base_ni_le_deplacer(self):
        self.ecrire("{ corrompu")

        with self.assertRaisesRegex(ErreurChargement, "contacts.json"):
            charger_contacts(self.base)
        self.assertFalse(self.base.exists())
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), "{ corrompu")

    def test_echec_de_creation_de_la_base_leve_erreur_chargement(self):
        self.ecrire('{"A": {}}')
        verrou = sqlite3.OperationalError("database is locked")

        with mock.patch("carnet.stockage.sqlite3.connect", side_effect=verrou):
            with self.assertRaisesRegex(ErreurChargement, "Import de contacts.json impossible"):
                charger_contacts(self.base)


if __name__ == "__main__":
    unittest.main()

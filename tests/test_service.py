"""Tests du service : aucune saisie clavier ni affichage, comme pour une interface graphique."""

import unittest
from unittest import mock

from carnet import (
    Carnet,
    ContactExistant,
    ContactIntrouvable,
    DonneesInvalides,
    ErreurChargement,
    SaisieContact,
)
from carnet.stockage import charger_contacts
from tests.aide import TestAvecDossier

ECHEC_ECRITURE = mock.patch("carnet.service.sauvegarder_contacts", side_effect=OSError("disque plein"))


class TestCarnet(TestAvecDossier):
    def carnet(self, contenu: str | None = None) -> Carnet:
        if contenu is not None:
            self.ecrire(contenu)
        return Carnet(self.chemin)

    def disque(self) -> dict:
        return charger_contacts(self.chemin).contacts

    # -- Ajout -----------------------------------------------------------

    def test_ajout_persiste_et_retourne_le_nom(self):
        carnet = self.carnet()

        nom = carnet.ajouter(SaisieContact(nom=" Alice ", email="alice@example.com"))

        self.assertEqual(nom, "Alice")
        self.assertIn("Alice", self.disque())
        self.assertEqual(carnet.vue("alice").emails[0].valeur, "alice@example.com")

    def test_ajout_donnees_invalides_detaille_les_champs(self):
        carnet = self.carnet()

        with self.assertRaises(DonneesInvalides) as ctx:
            carnet.ajouter(SaisieContact(nom="", email="x"))

        self.assertEqual(set(ctx.exception.erreurs), {"nom", "email"})
        self.assertEqual(len(carnet), 0)
        self.assertFalse(self.chemin.exists())

    def test_ajout_doublon_insensible_a_la_casse(self):
        carnet = self.carnet('{"Dupont": {}}')

        with self.assertRaises(ContactExistant) as ctx:
            carnet.ajouter(SaisieContact(nom="dupont"))

        self.assertEqual(ctx.exception.nom, "Dupont")
        self.assertEqual(carnet.noms, ["Dupont"])

    # -- Modification ----------------------------------------------------

    def test_modification_conserve_les_champs_importes_et_la_position(self):
        carnet = self.carnet(
            '{"A": {}, "Jean": {"Phone 2 - Value": "0622", "Organization Name": "ACME"}, "Z": {}}'
        )

        carnet.modifier("jean", SaisieContact(nom="Jean", telephone="06 11 11 11 11", notes="n"))

        fiche = self.disque()["Jean"]
        self.assertEqual(fiche["Phone 1 - Value"], "+33 6 11 11 11 11")
        self.assertEqual(fiche["Phone 2 - Value"], "0622")
        self.assertEqual(fiche["Organization Name"], "ACME")
        self.assertEqual(list(self.disque()), ["A", "Jean", "Z"])

    def test_renommage(self):
        carnet = self.carnet('{"A": {}, "Jean": {"Notes": "x"}, "Z": {}}')

        nom = carnet.modifier("Jean", SaisieContact(nom="Jean Martin", notes="x"))

        self.assertEqual(nom, "Jean Martin")
        self.assertEqual(carnet.noms, ["A", "Jean Martin", "Z"])
        self.assertEqual(list(self.disque()), ["A", "Jean Martin", "Z"])

    def test_renommage_changement_de_casse_seulement(self):
        carnet = self.carnet('{"jean": {}}')

        self.assertEqual(carnet.modifier("jean", SaisieContact(nom="Jean")), "Jean")
        self.assertEqual(carnet.noms, ["Jean"])

    def test_renommage_vers_un_nom_existant_refuse(self):
        carnet = self.carnet('{"Jean": {}, "Marie": {}}')

        with self.assertRaises(ContactExistant) as ctx:
            carnet.modifier("Jean", SaisieContact(nom="MARIE"))

        self.assertEqual(ctx.exception.nom, "Marie")
        self.assertEqual(carnet.noms, ["Jean", "Marie"])

    def test_modification_contact_inconnu(self):
        with self.assertRaises(ContactIntrouvable):
            self.carnet("{}").modifier("Inconnu", SaisieContact(nom="X"))

    def test_modification_garde_une_valeur_importee_non_conforme(self):
        carnet = self.carnet('{"Bob": {"Phone 1 - Value": "06 11 ::: 06 22"}}')

        carnet.modifier("Bob", SaisieContact(nom="Bob", telephone="06 11 ::: 06 22", notes="ok"))

        self.assertEqual(self.disque()["Bob"]["Notes"], "ok")

    def test_saisie_reflete_la_fiche(self):
        carnet = self.carnet('{"Bob": {"First Name": "Robert", "telephone": "0102030405"}}')

        saisie = carnet.saisie("BOB")

        self.assertEqual((saisie.nom, saisie.prenom, saisie.telephone), ("Bob", "Robert", "+33 1 02 03 04 05"))

    # -- Suppression et recherche ----------------------------------------

    def test_suppression_insensible_a_la_casse(self):
        carnet = self.carnet('{"Dupont": {}, "Martin": {}}')

        supprime = carnet.supprimer("DUPONT")

        self.assertEqual(supprime, "Dupont")
        self.assertEqual(carnet.noms, ["Martin"])
        self.assertEqual(list(self.disque()), ["Martin"])

    def test_suppression_contact_inconnu(self):
        carnet = self.carnet('{"Martin": {}}')

        with self.assertRaises(ContactIntrouvable):
            carnet.supprimer("Inconnu")
        self.assertEqual(carnet.noms, ["Martin"])

    def test_recherche_partielle_insensible_a_la_casse(self):
        carnet = self.carnet('{"Jean Martin": {}, "Marie Dupont": {}}')

        self.assertEqual([v.nom for v in carnet.rechercher("MART")], ["Jean Martin"])

    # -- Noms importés atypiques -----------------------------------------

    def test_nom_importe_avec_espaces_autour_reste_accessible(self):
        carnet = self.carnet('{" Bob ": {"Notes": "x"}}')

        self.assertEqual(carnet.vue(" Bob ").notes, "x")
        self.assertEqual(carnet.vue("bob").nom, " Bob ")
        self.assertEqual(carnet.supprimer("Bob"), " Bob ")

    def test_noms_ne_differant_que_par_la_casse_designes_exactement(self):
        carnet = self.carnet('{"Alice": {"Notes": "MAJ"}, "alice": {"Notes": "min"}}')

        self.assertEqual(carnet.vue("alice").notes, "min")
        carnet.supprimer("alice")

        self.assertEqual(self.disque(), {"Alice": {"Notes": "MAJ"}})

    # -- Échec d'écriture : mémoire et disque restent identiques ---------

    def test_echec_ecriture_ajout_sans_effet(self):
        carnet = self.carnet('{"Dupont": {}}')

        with ECHEC_ECRITURE, self.assertRaises(OSError):
            carnet.ajouter(SaisieContact(nom="Zoé"))

        self.assertEqual(carnet.noms, ["Dupont"])
        carnet.ajouter(SaisieContact(nom="Zoé"))  # un nouvel essai fonctionne
        self.assertIn("Zoé", self.disque())

    def test_echec_ecriture_suppression_sans_effet(self):
        carnet = self.carnet('{"Dupont": {}}')

        with ECHEC_ECRITURE, self.assertRaises(OSError):
            carnet.supprimer("Dupont")

        self.assertEqual(carnet.noms, ["Dupont"])
        self.assertEqual(carnet.vue("Dupont").nom, "Dupont")

    def test_echec_ecriture_modification_sans_effet(self):
        carnet = self.carnet('{"Dupont": {"Notes": "avant"}}')

        with ECHEC_ECRITURE, self.assertRaises(OSError):
            carnet.modifier("Dupont", SaisieContact(nom="Durand", notes="après"))

        self.assertEqual(carnet.noms, ["Dupont"])
        self.assertEqual(carnet.vue("Dupont").notes, "avant")

    # -- Uniformisation des numéros existants ----------------------------

    def test_numeros_mis_au_format_des_le_chargement(self):
        carnet = self.carnet('{"B": {"Phone 1 - Value": "06 70 01 0475", "Phone 2 - Value": "0102030405"},'
                             ' "Ancien": {"telephone": "01 02 03 04 05"}}')

        self.assertEqual(
            [t.valeur for t in carnet.vue("B").telephones],
            ["+33 6 70 01 04 75", "+33 1 02 03 04 05"],
        )
        self.assertEqual(carnet.vue("Ancien").telephones[0].valeur, "+33 1 02 03 04 05")
        self.assertEqual(carnet.saisie("B").telephone, "+33 6 70 01 04 75")

    def test_chargement_ne_reecrit_pas_le_fichier(self):
        contenu = '{"B": {"Phone 1 - Value": "06 70 01 0475"}}'

        self.carnet(contenu)

        self.assertEqual(self.chemin.read_text(encoding="utf-8"), contenu)

    def test_forme_uniforme_ecrite_au_prochain_enregistrement(self):
        carnet = self.carnet('{"B": {"Phone 1 - Value": "06 70 01 0475"},'
                             ' "Bizarre": {"Phone 1 - Value": "le standard"}, "C": {}}')

        carnet.supprimer("C")  # n'importe quelle modification

        disque = self.disque()
        self.assertEqual(disque["B"]["Phone 1 - Value"], "+33 6 70 01 04 75")
        self.assertEqual(disque["Bizarre"]["Phone 1 - Value"], "le standard")  # non reconnu : intact

    def test_modification_d_un_numero_importe_non_reconnu_conservee_a_l_identique(self):
        carnet = self.carnet('{"Bob": {"Phone 1 - Value": "0611 ::: standard"}}')

        carnet.modifier("Bob", SaisieContact(nom="Bob", telephone=carnet.saisie("Bob").telephone, notes="n"))

        self.assertEqual(self.disque()["Bob"]["Phone 1 - Value"], "0611 ::: standard")

    def test_ajout_enregistre_le_numero_au_format(self):
        carnet = self.carnet()

        carnet.ajouter(SaisieContact(nom="A", telephone="06.70.01.04.75"))

        self.assertEqual(self.disque()["A"]["Phone 1 - Value"], "+33 6 70 01 04 75")

    # -- Divers ----------------------------------------------------------

    def test_contains_et_fiche(self):
        carnet = self.carnet('{"Dupont": {"Notes": "x"}}')

        self.assertIn("dupont", carnet)
        self.assertNotIn("Martin", carnet)
        fiche = carnet.fiche("DUPONT")
        fiche["Notes"] = "modifiée"
        self.assertEqual(carnet.fiche("Dupont")["Notes"], "x")  # copie indépendante

    def test_fichier_corrompu_signale(self):
        carnet = self.carnet("{ corrompu")

        self.assertEqual(len(carnet), 0)
        self.assertIsNotNone(carnet.fichier_mis_de_cote)
        self.assertTrue(carnet.fichier_mis_de_cote.exists())

    def test_fichier_mal_forme_leve_erreur_chargement(self):
        with self.assertRaises(ErreurChargement):
            self.carnet("[]")


class TestCarnetSqlite(TestAvecDossier):
    def test_operations_persistees_dans_la_base_dans_l_ordre(self):
        base = self.dossier / "contacts.db"
        carnet = Carnet(base)

        carnet.ajouter(SaisieContact(nom="Alice", telephone="06 12 34 56 78"))
        carnet.ajouter(SaisieContact(nom="Bob"))
        carnet.ajouter(SaisieContact(nom="Chloé"))
        carnet.modifier("Alice", SaisieContact(nom="Alice Martin", notes="renommée"))
        carnet.supprimer("Bob")

        rouvert = Carnet(base)
        self.assertEqual(rouvert.noms, ["Alice Martin", "Chloé"])
        self.assertEqual(rouvert.vue("Alice Martin").notes, "renommée")

    def test_premiere_ouverture_importe_le_json_et_uniformise_les_numeros(self):
        self.ecrire('{"Bob": {"Phone 1 - Value": "0612345678"}}')

        carnet = Carnet(self.dossier / "contacts.db")

        self.assertEqual(carnet.vue("Bob").telephones[0].valeur, "+33 6 12 34 56 78")


if __name__ == "__main__":
    unittest.main()

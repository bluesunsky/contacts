"""Tests du service : aucune saisie clavier ni affichage, comme pour une interface graphique."""

import unittest

from carnet import (
    Carnet,
    ContactExistant,
    ContactIntrouvable,
    DonneesInvalides,
    ErreurChargement,
    NouveauContact,
)
from carnet.stockage import charger_contacts
from tests.aide import TestAvecDossier


class TestCarnet(TestAvecDossier):
    def carnet(self, contenu: str | None = None) -> Carnet:
        if contenu is not None:
            self.ecrire(contenu)
        return Carnet(self.chemin)

    def test_ajout_persiste_et_retourne_le_nom(self):
        carnet = self.carnet()

        nom = carnet.ajouter(NouveauContact(nom=" Alice ", email="alice@example.com"))

        self.assertEqual(nom, "Alice")
        self.assertIn("Alice", charger_contacts(self.chemin).contacts)
        self.assertEqual(carnet.vue("alice").emails[0].valeur, "alice@example.com")

    def test_ajout_donnees_invalides_detaille_les_champs(self):
        carnet = self.carnet()

        with self.assertRaises(DonneesInvalides) as ctx:
            carnet.ajouter(NouveauContact(nom="", email="x"))

        self.assertEqual(set(ctx.exception.erreurs), {"nom", "email"})
        self.assertEqual(len(carnet), 0)
        self.assertFalse(self.chemin.exists())

    def test_ajout_doublon_insensible_a_la_casse(self):
        carnet = self.carnet('{"Dupont": {}}')

        with self.assertRaises(ContactExistant) as ctx:
            carnet.ajouter(NouveauContact(nom="dupont"))

        self.assertEqual(ctx.exception.nom, "Dupont")
        self.assertEqual(carnet.noms, ["Dupont"])

    def test_suppression_insensible_a_la_casse(self):
        carnet = self.carnet('{"Dupont": {}, "Martin": {}}')

        supprime = carnet.supprimer("DUPONT")

        self.assertEqual(supprime, "Dupont")
        self.assertEqual(carnet.noms, ["Martin"])
        self.assertEqual(list(charger_contacts(self.chemin).contacts), ["Martin"])

    def test_suppression_contact_inconnu(self):
        carnet = self.carnet('{"Martin": {}}')

        with self.assertRaises(ContactIntrouvable):
            carnet.supprimer("Inconnu")
        self.assertEqual(carnet.noms, ["Martin"])

    def test_recherche_partielle_insensible_a_la_casse(self):
        carnet = self.carnet('{"Jean Martin": {}, "Marie Dupont": {}}')

        self.assertEqual([v.nom for v in carnet.rechercher("MART")], ["Jean Martin"])

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


if __name__ == "__main__":
    unittest.main()

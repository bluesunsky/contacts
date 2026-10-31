import unittest

from carnet.modele import (
    MESSAGE_EMAIL,
    MESSAGE_OBLIGATOIRE,
    MESSAGE_TELEPHONE,
    Email,
    NouveauContact,
    Telephone,
    erreur_email,
    erreur_telephone,
    vue_contact,
)


class TestValidation(unittest.TestCase):
    def test_telephones_acceptes(self):
        for valeur in ["", "06 12 34 56 78", "+33 (0)6 12-34.56.78"]:
            with self.subTest(valeur=valeur):
                self.assertIsNone(erreur_telephone(valeur))

    def test_telephones_refuses(self):
        for valeur in ["abc", "12345", "06 12 34 56 78 poste 2"]:
            with self.subTest(valeur=valeur):
                self.assertEqual(erreur_telephone(valeur), MESSAGE_TELEPHONE)

    def test_emails(self):
        self.assertIsNone(erreur_email(""))
        self.assertIsNone(erreur_email("bob@example.com"))
        self.assertEqual(erreur_email("pas-un-mail"), MESSAGE_EMAIL)
        self.assertEqual(erreur_email("a@b"), MESSAGE_EMAIL)


class TestNouveauContact(unittest.TestCase):
    def test_espaces_retires(self):
        contact = NouveauContact(nom="  Alice ", email=" a@b.fr ")

        self.assertEqual(contact.nom, "Alice")
        self.assertEqual(contact.email, "a@b.fr")

    def test_erreurs_par_champ(self):
        contact = NouveauContact(nom=" ", telephone="abc", email="x")

        self.assertEqual(
            contact.erreurs(),
            {"nom": MESSAGE_OBLIGATOIRE, "telephone": MESSAGE_TELEPHONE, "email": MESSAGE_EMAIL},
        )

    def test_contact_valide_sans_erreur(self):
        self.assertEqual(NouveauContact(nom="Alice").erreurs(), {})

    def test_fiche_au_format_google_et_prenom_omis_reste_vide(self):
        fiche = NouveauContact(nom="Alice", telephone="0612345678").vers_fiche()

        self.assertEqual(fiche["First Name"], "")
        self.assertEqual(fiche["Phone 1 - Value"], "0612345678")
        self.assertEqual(fiche["Phone 1 - Label"], "Mobile")


class TestVueContact(unittest.TestCase):
    def test_champs_vides_omis(self):
        vue = vue_contact("Test", {
            "E-mail 1 - Label": "Home", "E-mail 1 - Value": "",
            "Organization Name": "", "Notes": "  ",
        })

        self.assertEqual(vue.emails, ())
        self.assertEqual(vue.entreprise, "")
        self.assertEqual(vue.notes, "")

    def test_telephones_tries_avec_label(self):
        vue = vue_contact("Test", {
            "Phone 2 - Label": "Work", "Phone 2 - Value": "222222",
            "Phone 1 - Label": "Mobile", "Phone 1 - Value": "111111",
        })

        self.assertEqual(
            vue.telephones,
            (Telephone("Mobile", "111111", 1), Telephone("Work", "222222", 2)),
        )

    def test_label_par_defaut(self):
        vue = vue_contact("Test", {"Phone 1 - Value": "111111", "E-mail 1 - Value": "a@b.fr"})

        self.assertEqual(vue.telephones[0].label, "Téléphone")
        self.assertEqual(vue.emails[0].label, "Email")

    def test_cle_ressemblante_ignoree(self):
        self.assertEqual(vue_contact("Test", {"Phone Value Notes": "x"}).telephones, ())

    def test_retrocompatibilite_ancien_format(self):
        vue = vue_contact("Test", {"telephone": "0102030405", "email": "a@b.fr"})

        self.assertEqual(vue.telephones, (Telephone("Téléphone", "0102030405"),))
        self.assertEqual(vue.emails, (Email("Email", "a@b.fr"),))

    def test_adresse_decoupee_en_lignes(self):
        vue = vue_contact("Test", {"Address 1 - Formatted": "1 rue A ::: 75000 Paris ::: France"})

        self.assertEqual(vue.adresse, ("1 rue A", "75000 Paris", "France"))


if __name__ == "__main__":
    unittest.main()

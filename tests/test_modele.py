import unittest

from carnet.modele import (
    MESSAGE_EMAIL,
    MESSAGE_OBLIGATOIRE,
    MESSAGE_TELEPHONE,
    Email,
    SaisieContact,
    Telephone,
    erreur_email,
    erreur_telephone,
    normaliser_telephone,
    traduire_libelle,
    uniformiser_telephone,
    uniformiser_telephones_fiche,
    vue_contact,
)


class TestValidation(unittest.TestCase):
    def test_telephones_acceptes(self):
        for valeur in ["", "06 12 34 56 78", "+33 (0)6 12-34.56.78"]:
            with self.subTest(valeur=valeur):
                self.assertIsNone(erreur_telephone(valeur))

    def test_telephones_refuses(self):
        for valeur in ["abc", "12345", "06 12 34 56 7A", "+33 6 12 34 56 7", "06 11 ::: 06 22"]:
            with self.subTest(valeur=valeur):
                self.assertEqual(erreur_telephone(valeur), MESSAGE_TELEPHONE)

    def test_emails(self):
        self.assertIsNone(erreur_email(""))
        self.assertIsNone(erreur_email("bob@example.com"))
        self.assertEqual(erreur_email("pas-un-mail"), MESSAGE_EMAIL)
        self.assertEqual(erreur_email("a@b"), MESSAGE_EMAIL)


class TestTelephone(unittest.TestCase):
    def test_formes_diverses_mises_au_format_international(self):
        cas = {
            "06 70 01 0475": "+33 6 70 01 04 75",
            "0670010475": "+33 6 70 01 04 75",
            "06.70.01.04.75": "+33 6 70 01 04 75",
            "+33 (0)6 70 01 04 75": "+33 6 70 01 04 75",
            "0033 6 70 01 04 75": "+33 6 70 01 04 75",
            "01 02 03 04 05": "+33 1 02 03 04 05",
            "+1 650 253 0000": "+1 650-253-0000",
            "+44 20 7946 0958": "+44 20 7946 0958",
        }
        for saisie, attendu in cas.items():
            with self.subTest(saisie=saisie):
                self.assertEqual(normaliser_telephone(saisie), attendu)

    def test_extension(self):
        for saisie in ["01 23 45 67 89 poste 12", "0123456789 ext. 12", "01 23 45 67 89 x12"]:
            with self.subTest(saisie=saisie):
                self.assertEqual(normaliser_telephone(saisie), "+33 1 23 45 67 89 ext. 12")

    def test_vide_et_invalide(self):
        self.assertEqual(normaliser_telephone("  "), "")
        self.assertIsNone(normaliser_telephone("06 12 34 56 7"))
        # Les lettres ne sont pas converties en chiffres comme sur un clavier.
        self.assertIsNone(normaliser_telephone("06 12 34 56 7A"))

    def test_valeur_multiple_et_non_reconnus_conserves(self):
        valeur = "0670010475 ::: inconnu ::: +33612345678"

        self.assertEqual(
            uniformiser_telephone(valeur),
            "+33 6 70 01 04 75 ::: inconnu ::: +33 6 12 34 56 78",
        )

    def test_saisie_mise_au_format_par_construction(self):
        self.assertEqual(SaisieContact(nom="A", telephone="06 70 01 0475").telephone, "+33 6 70 01 04 75")
        self.assertEqual(SaisieContact(nom="A", telephone="abc").telephone, "abc")  # gardé pour l'erreur

    def test_fiche_entiere_uniformisee_sans_toucher_au_reste(self):
        fiche = {"Phone 1 - Value": "0670010475", "Phone 2 - Value": "0102030405",
                 "telephone": "0611111111", "Notes": "0612345678", "Phone 3 - Value": 42}

        resultat = uniformiser_telephones_fiche(fiche)

        self.assertEqual(resultat["Phone 1 - Value"], "+33 6 70 01 04 75")
        self.assertEqual(resultat["Phone 2 - Value"], "+33 1 02 03 04 05")
        self.assertEqual(resultat["telephone"], "+33 6 11 11 11 11")
        self.assertEqual(resultat["Notes"], "0612345678")  # pas un champ téléphone
        self.assertEqual(resultat["Phone 3 - Value"], 42)  # valeur non textuelle intacte
        self.assertEqual(fiche["Phone 1 - Value"], "0670010475")  # copie

    def test_modification_uniformise_aussi_les_numeros_secondaires(self):
        fiche = {"Phone 2 - Value": "0102030405"}

        resultat = SaisieContact(nom="A").appliquer(fiche)

        self.assertEqual(resultat["Phone 2 - Value"], "+33 1 02 03 04 05")


class TestSaisieContact(unittest.TestCase):
    def test_espaces_retires(self):
        saisie = SaisieContact(nom="  Alice ", email=" a@b.fr ")

        self.assertEqual(saisie.nom, "Alice")
        self.assertEqual(saisie.email, "a@b.fr")

    def test_erreurs_par_champ(self):
        saisie = SaisieContact(nom=" ", telephone="abc", email="x")

        self.assertEqual(
            saisie.erreurs(),
            {"nom": MESSAGE_OBLIGATOIRE, "telephone": MESSAGE_TELEPHONE, "email": MESSAGE_EMAIL},
        )

    def test_saisie_valide_sans_erreur(self):
        self.assertEqual(SaisieContact(nom="Alice").erreurs(), {})

    def test_valeur_importee_inchangee_non_revalidee(self):
        reference = SaisieContact(nom="Bob", telephone="06 11 ::: 06 22", email="bob[at]ex")
        saisie = SaisieContact(nom="Bob", telephone="06 11 ::: 06 22", email="bob[at]ex", notes="x")

        self.assertEqual(saisie.erreurs(reference), {})

    def test_valeur_modifiee_revalidee(self):
        reference = SaisieContact(nom="Bob", telephone="06 11 ::: 06 22")
        saisie = SaisieContact(nom="Bob", telephone="abc")

        self.assertEqual(saisie.erreurs(reference), {"telephone": MESSAGE_TELEPHONE})

    def test_nouvelle_fiche_au_format_google_et_prenom_omis_reste_vide(self):
        fiche = SaisieContact(nom="Alice", telephone="0612345678").appliquer()

        self.assertEqual(fiche["First Name"], "")
        self.assertEqual(fiche["Phone 1 - Value"], "+33 6 12 34 56 78")
        self.assertEqual(fiche["Phone 1 - Label"], "Mobile")
        self.assertEqual(fiche["E-mail 1 - Label"], "Home")

    def test_depuis_fiche_google(self):
        fiche = {
            "First Name": "Jean", "Last Name": "Martin", "Phone 1 - Value": "0611",
            "E-mail 1 - Value": "j@ex.fr", "Notes": "n", "Organization Name": "ACME",
        }

        saisie = SaisieContact.depuis_fiche("Jean Martin", fiche)

        self.assertEqual(
            saisie,
            SaisieContact("Jean Martin", "Jean", "Martin", "0611", "j@ex.fr", "n"),
        )

    def test_depuis_fiche_ancien_format(self):
        saisie = SaisieContact.depuis_fiche("Ancien", {"telephone": "0102", "email": "a@b.fr"})

        self.assertEqual((saisie.telephone, saisie.email), ("0102", "a@b.fr"))

    def test_appliquer_conserve_les_autres_champs_et_libelles(self):
        fiche = {
            "Phone 1 - Label": "Work", "Phone 1 - Value": "0611",
            "Phone 2 - Value": "0622", "Organization Name": "ACME", "Notes": "ancienne",
        }

        resultat = SaisieContact(nom="Jean", telephone="0699", notes="nouvelle").appliquer(fiche)

        self.assertEqual(resultat["Phone 1 - Label"], "Work")
        self.assertEqual(resultat["Phone 1 - Value"], "0699")
        self.assertEqual(resultat["Phone 2 - Value"], "0622")
        self.assertEqual(resultat["Organization Name"], "ACME")
        self.assertEqual(resultat["Notes"], "nouvelle")
        self.assertEqual(fiche["Notes"], "ancienne")  # la fiche d'origine n'est pas modifiée

    def test_appliquer_migre_l_ancien_format(self):
        resultat = SaisieContact(nom="A", telephone="0102030405").appliquer({"telephone": "0102030405"})

        self.assertNotIn("telephone", resultat)
        self.assertEqual(resultat["Phone 1 - Value"], "+33 1 02 03 04 05")


class TestVueContact(unittest.TestCase):
    def test_champs_vides_omis(self):
        vue = vue_contact("Test", {
            "E-mail 1 - Label": "Home", "E-mail 1 - Value": "",
            "Organization Name": "", "Notes": "  ",
        })

        self.assertEqual(vue.emails, ())
        self.assertEqual(vue.entreprise, "")
        self.assertEqual(vue.notes, "")

    def test_valeurs_numeriques_conservees(self):
        vue = vue_contact("Test", {"Phone 1 - Value": 612345678, "Notes": 0})

        self.assertEqual(vue.telephones[0].valeur, "612345678")
        self.assertEqual(vue.notes, "0")

    def test_telephones_tries_et_libelles_traduits(self):
        vue = vue_contact("Test", {
            "Phone 2 - Label": "Work", "Phone 2 - Value": "222222",
            "Phone 1 - Label": "* Mobile", "Phone 1 - Value": "111111",
        })

        self.assertEqual(
            vue.telephones,
            (Telephone("Mobile", "111111", 1), Telephone("Travail", "222222", 2)),
        )

    def test_libelles(self):
        self.assertEqual(traduire_libelle("Home"), "Domicile")
        self.assertEqual(traduire_libelle("* Work"), "Travail")
        self.assertEqual(traduire_libelle("Perso"), "Perso")

    def test_libelle_par_defaut(self):
        vue = vue_contact("Test", {"Phone 1 - Value": "111111", "E-mail 1 - Value": "a@b.fr"})

        self.assertEqual(vue.telephones[0].label, "Téléphone")
        self.assertEqual(vue.emails[0].label, "E-mail")

    def test_cle_ressemblante_ignoree(self):
        self.assertEqual(vue_contact("Test", {"Phone Value Notes": "x"}).telephones, ())

    def test_retrocompatibilite_ancien_format(self):
        vue = vue_contact("Test", {"telephone": "0102030405", "email": "a@b.fr"})

        self.assertEqual(vue.telephones, (Telephone("Téléphone", "0102030405"),))
        self.assertEqual(vue.emails, (Email("E-mail", "a@b.fr"),))

    def test_adresse_decoupee_en_lignes(self):
        vue = vue_contact("Test", {"Address 1 - Formatted": "1 rue A ::: 75000 Paris ::: France"})

        self.assertEqual(vue.adresse, ("1 rue A", "75000 Paris", "France"))


if __name__ == "__main__":
    unittest.main()

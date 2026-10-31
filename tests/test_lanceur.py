import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from carnet import lanceur


def bloquer_pyqt6():
    """Simule l'absence de PyQt6, quels que soient les sous-modules déjà importés."""
    blocage = {nom: None for nom in list(sys.modules) if nom.startswith("PyQt6.")}
    blocage["PyQt6"] = None
    return mock.patch.dict(sys.modules, blocage)


class TestLanceur(unittest.TestCase):
    def setUp(self):
        # forcer_utf8 reconfigurerait le stderr du lanceur de tests.
        patcher = mock.patch("carnet.lanceur.forcer_utf8")
        patcher.start()
        self.addCleanup(patcher.stop)

    def lancer(self, argv):
        erreurs = io.StringIO()
        with redirect_stderr(erreurs):
            code = lanceur.main(argv)
        return code, erreurs.getvalue()

    def test_console_lance_le_terminal(self):
        with mock.patch("carnet.cli.main", return_value=0) as cli:
            self.assertEqual(lanceur.main(["--console"]), 0)
        cli.assert_called_once()

    def test_par_defaut_lance_la_fenetre(self):
        faux_gui = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch.dict(sys.modules, {"carnet.gui": faux_gui}), \
                mock.patch("carnet.cli.main") as cli:
            self.assertEqual(lanceur.main([]), 0)
        faux_gui.main.assert_called_once()
        cli.assert_not_called()

    def test_pyqt_absent_message_explicite(self):
        with bloquer_pyqt6(), mock.patch.dict(sys.modules), mock.patch("carnet.cli.main") as cli:
            sys.modules.pop("carnet.gui", None)
            code, erreurs = self.lancer([])

        self.assertEqual(code, 1)
        self.assertIn("n'est pas installé", erreurs)
        self.assertIn("--console", erreurs)
        self.assertIn("requirements.txt", erreurs)
        cli.assert_not_called()

    def test_pyqt_inutilisable_message_distinct(self):
        class GuiEnPanne:
            """Module dont l'import échoue sur une DLL Qt manquante."""
            def __getattr__(self, nom):
                raise ImportError("DLL load failed", name="PyQt6.QtWidgets")

        # PyQt6 présent (même si ce Python ne l'a pas), mais inutilisable.
        with mock.patch.dict(sys.modules, {"carnet.gui": GuiEnPanne()}), \
                mock.patch("carnet.lanceur.importlib.util.find_spec", return_value=mock.Mock()):
            code, erreurs = self.lancer([])

        self.assertEqual(code, 1)
        self.assertIn("n'a pas pu être chargé", erreurs)
        self.assertIn("DLL load failed", erreurs)

    def test_import_error_hors_pyqt6_propagee(self):
        with mock.patch.dict(sys.modules, {"carnet.gui": None}):
            with self.assertRaises(ImportError) as ctx:
                self.lancer([])

        self.assertEqual(ctx.exception.name, "carnet.gui")

    def test_option_inconnue_refusee(self):
        with self.assertRaises(SystemExit) as ctx:
            self.lancer(["--inconnue"])

        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

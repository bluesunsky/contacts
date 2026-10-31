import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from carnet import lanceur


class TestLanceur(unittest.TestCase):
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
        erreurs = io.StringIO()
        with mock.patch.dict(sys.modules, {"PyQt6": None}):
            sys.modules.pop("carnet.gui", None)
            sys.modules.pop("PyQt6.QtCore", None)
            with redirect_stderr(erreurs):
                code = lanceur.main([])

        self.assertEqual(code, 1)
        self.assertIn("--console", erreurs.getvalue())
        self.assertIn("requirements.txt", erreurs.getvalue())

    def test_option_inconnue_refusee(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            lanceur.main(["--inconnue"])


if __name__ == "__main__":
    unittest.main()

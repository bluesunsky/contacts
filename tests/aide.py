"""Outils communs aux tests."""

import tempfile
import unittest
from pathlib import Path


class TestAvecDossier(unittest.TestCase):
    """Fournit un dossier temporaire et le chemin d'un carnet à l'intérieur."""

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        self.chemin = self.dossier / "contacts.json"

    def ecrire(self, contenu: str) -> None:
        self.chemin.write_text(contenu, encoding="utf-8")

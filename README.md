# Carnet de contacts

Gestionnaire de contacts stockés dans `contacts.json`, au format d'export de
Google Contacts. Il propose une fenêtre PyQt6 et un mode terminal.

## Installation

Python 3.10 ou plus récent. Les dépendances sont listées dans
`requirements.txt` ; un environnement virtuel est recommandé :

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Le mode terminal ne nécessite aucune dépendance.

## Lancer

```
python contacts.py              # fenêtre
python contacts.py --console    # terminal
```

`python -m carnet` accepte les mêmes options. Sans PyQt6, le lancement en
fenêtre affiche un message qui indique comment l'installer ou passer en mode
terminal.

Raccourcis de la fenêtre :

| Touche | Action |
|---|---|
| Ctrl+N | Ajouter un contact |
| F2, Entrée ou double-clic dans la liste | Modifier le contact sélectionné |
| Suppr dans la liste | Supprimer le contact sélectionné, après confirmation |
| Ctrl+F | Aller à la recherche |
| Flèche bas ou Entrée dans la recherche | Aller à la liste |
| Échap dans la recherche | Effacer la recherche |
| Ctrl+Entrée dans le formulaire | Valider |

En mode terminal, la modification affiche chaque valeur actuelle : Entrée
seule la conserve, « - » efface le champ.

La modification porte sur le nom, le prénom, le nom de famille, le téléphone
et l'e-mail principaux et les notes. Les autres champs d'un contact importé de
Google Contacts (numéros secondaires, adresse, entreprise...) sont conservés.

## Organisation

| Module | Rôle | Entrées / sorties |
|---|---|---|
| `carnet/modele.py` | Structure des fiches, validation, vue d'affichage | aucune |
| `carnet/stockage.py` | Lecture et écriture atomique du JSON | fichier |
| `carnet/service.py` | Classe `Carnet` : ajouter, rechercher, supprimer | via stockage |
| `carnet/cli.py` | Interface terminal | clavier, écran |
| `carnet/gui.py` | Interface graphique PyQt6 | fenêtre |
| `carnet/lanceur.py` | Choix de l'interface selon `--console` | arguments |

Les deux interfaces passent uniquement par `Carnet` et les types de
`carnet.modele`. Les erreurs métier sont signalées par des exceptions
dérivant de `ErreurCarnet`, dont le message peut être affiché tel quel. Seul
`gui.py` importe PyQt6.

## Utiliser `Carnet` depuis une autre interface

```python
from carnet import Carnet, ContactExistant, DonneesInvalides, SaisieContact

carnet = Carnet()
for vue in carnet.vues():          # VueContact : nom, telephones, emails, adresse...
    ...

try:
    carnet.ajouter(SaisieContact(nom=..., telephone=..., email=...))
    saisie = carnet.saisie("Dupont")               # valeurs éditables actuelles
    carnet.modifier("Dupont", SaisieContact(nom="Durand", telephone=saisie.telephone))
except DonneesInvalides as e:
    e.erreurs                      # {"telephone": "Numéro invalide..."} : message par champ
except ContactExistant as e:
    str(e)                         # "Le contact « Dupont » existe déjà."
except OSError:
    ...                            # écriture impossible ; le carnet en mémoire est inchangé
```

Après la création de `Carnet`, vérifier `carnet.fichier_mis_de_cote` : s'il
est renseigné, le fichier d'origine était illisible et a été conservé sous ce
nom, ce qu'il faut signaler à l'utilisateur.

## Tests

```
python -m unittest
```

Les tests de l'interface graphique s'exécutent sans ouvrir de fenêtre et sont
ignorés si PyQt6 n'est pas installé. Les tests fonctionnent aussi avec pytest.

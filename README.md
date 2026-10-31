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

Dans la fenêtre : Ctrl+N ajoute un contact, Suppr supprime le contact
sélectionné, Ctrl+F place le curseur dans la recherche.

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
from carnet import Carnet, ContactExistant, DonneesInvalides, NouveauContact

carnet = Carnet()
for vue in carnet.vues():          # VueContact : nom, telephones, emails, adresse...
    ...

try:
    carnet.ajouter(NouveauContact(nom=..., telephone=..., email=...))
except DonneesInvalides as e:
    e.erreurs                      # {"telephone": "Numéro invalide..."} : message par champ
except ContactExistant as e:
    str(e)                         # "Le contact 'Dupont' existe déjà."
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

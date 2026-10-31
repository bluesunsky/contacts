# Carnet de contacts

Gestionnaire de contacts stockés dans `contacts.json`, au format d'export de
Google Contacts.

## Lancer

```
python contacts.py
```

ou `python -m carnet`.

## Organisation

| Module | Rôle | Entrées / sorties |
|---|---|---|
| `carnet/modele.py` | Structure des fiches, validation, vue d'affichage | aucune |
| `carnet/stockage.py` | Lecture et écriture atomique du JSON | fichier |
| `carnet/service.py` | Classe `Carnet` : ajouter, rechercher, supprimer | via stockage |
| `carnet/cli.py` | Interface terminal | clavier, écran |

Seul `cli.py` utilise `input` et `print`. Les erreurs métier sont signalées
par des exceptions dérivant de `ErreurCarnet`, dont le message peut être
affiché tel quel.

## Ajouter une interface graphique

Créer un module, par exemple `carnet/gui.py`, qui utilise uniquement `Carnet`
et les types de `carnet.modele` :

```python
from carnet import Carnet, ContactExistant, DonneesInvalides, NouveauContact

carnet = Carnet()
for vue in carnet.vues():          # VueContact : nom, telephones, emails, adresse...
    ...                            # remplir une liste

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

Les tests fonctionnent aussi avec pytest.

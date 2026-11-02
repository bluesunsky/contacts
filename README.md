# Carnet de contacts

Gestionnaire de contacts stockés dans une base SQLite, `contacts.db`, au
format d'export de Google Contacts. Il propose une fenêtre PyQt6 et un mode
terminal.

## Installation

Python 3.10 ou plus récent. Les dépendances sont listées dans
`requirements.txt` ; un environnement virtuel est recommandé :

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`phonenumbers` est nécessaire dans tous les modes ; PyQt6 seulement pour la
fenêtre.

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

## Numéros de téléphone

Tous les numéros sont enregistrés au format international lisible, quelle que
soit la façon dont ils sont tapés :

| Saisie | Enregistré |
|---|---|
| `06 70 01 0475`, `06.70.01.04.75`, `0033670010475` | `+33 6 70 01 04 75` |
| `01 23 45 67 89 poste 12` | `+33 1 23 45 67 89 ext. 12` |
| `+1 650 253 0000` | `+1 650-253-0000` |

Un numéro sans indicatif est considéré comme français ; ceux des outre-mer
composés à la française (`0692…`, `0590…`, `0596…`) reçoivent leur propre
indicatif (`+262`, `+590`, `+596`...). La validation suit les
plages attribuées par pays (bibliothèque `phonenumbers`) : un numéro d'une
plage non attribuée est refusé à la saisie.

Un carnet importé ou modifié à la main est mis au format dès son ouverture,
numéros secondaires compris : l'affichage est uniforme, et la forme uniforme
est écrite dans le fichier au prochain enregistrement. Un numéro non reconnu
est conservé tel quel.

## Stockage

Le carnet est enregistré dans `contacts.db`, à la racine du projet, dans
quatre tables :

| Table | Contenu |
|---|---|
| `contacts` | Une ligne par contact : `id` (position dans le carnet), `nom`, `prenom`, `nom_famille`, `entreprise`, `poste`, `adresse`, `notes` |
| `telephones` | Une ligne par numéro : `contact_id`, `numero` (1, 2...), `libelle`, `valeur` |
| `emails` | Une ligne par adresse e-mail, mêmes colonnes que `telephones` |
| `autres_champs` | `contact_id`, `cle`, `valeur` : les autres champs d'un export Google Contacts (anniversaire, site web...), conservés tels quels |

Une colonne vide (`NULL`) correspond à un champ absent du contact. Chaque
modification est écrite en une seule transaction. La version du schéma est
enregistrée dans `PRAGMA user_version` : une base d'un autre format est
refusée à l'ouverture, sans être modifiée.

À la première ouverture, si `contacts.db` n'existe pas encore, le contenu de
`contacts.json` y est importé. Le fichier JSON n'est pas modifié, mais il
n'est plus lu ensuite : supprimer `contacts.db` relance l'import. Si
`contacts.json` n'est pas du JSON valide, le carnet ne s'ouvre pas et indique
l'erreur, pour ne pas démarrer une base vide à la place de ces contacts.

Un chemin se terminant par `.json`, passé à `Carnet`, utilise un fichier JSON
au lieu de la base.

## Organisation

| Module | Rôle | Entrées / sorties |
|---|---|---|
| `carnet/modele.py` | Structure des fiches, validation, vue d'affichage | aucune |
| `carnet/stockage.py` | Lecture et écriture atomique de la base SQLite ou du JSON | fichier |
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

Après la création de `Carnet` sur un fichier JSON, vérifier
`carnet.fichier_mis_de_cote` : s'il est renseigné, le fichier d'origine était
illisible et a été conservé sous ce
nom, ce qu'il faut signaler à l'utilisateur.

## Tests

```
python -m unittest
```

Les tests de l'interface graphique s'exécutent sans ouvrir de fenêtre et sont
ignorés si PyQt6 n'est pas installé. Les tests fonctionnent aussi avec pytest.

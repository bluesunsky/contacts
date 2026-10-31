import json
import os

FICHIER_CONTACTS = "contacts.json"


def charger_contacts():
  if os.path.exists(FICHIER_CONTACTS):
    with open(FICHIER_CONTACTS, "r", encoding="utf-8") as f:
      try:
        return json.load(f)
      except json.JSONDecodeError:
        return {}
  return {}


def sauvegarder_contacts(contacts):
  with open(FICHIER_CONTACTS, "w", encoding="utf-8") as f:
    json.dump(contacts, f, ensure_ascii=False, indent=4)


def afficher_contacts(contacts):
  if not contacts:
    print("📭 Aucun contact enregistré.")
    return

  print(f"\n--- Liste des contacts ({len(contacts)}) ---")
  for nom, infos in contacts.items():
    print(f"\n👤 Nom : {nom}")

    # 1. Recherche dynamique des numéros de téléphone
    telephones = {
        k: v for k, v in infos.items() if "Phone" in k and "Value" in k
    }
    if telephones:
      for k, v in telephones.items():
        # Extrait le numéro de la clé (ex: Phone 1)
        num = k.split("-")[0].strip()
        # Cherche le label associé (ex: Mobile, Home) s'il existe
        label_key = k.replace("Value", "Label")
        label = infos.get(label_key, "Téléphone")
        print(f"  📞 {label} ({num}) : {v}")
    elif "telephone" in infos:  # Rétrocompatibilité anciens contacts
      print(f"  📞 Téléphone : {infos['telephone']}")

    # 2. Recherche dynamique des adresses e-mail
    emails = {k: v for k, v in infos.items() if "E-mail" in k and "Value" in k}
    if emails:
      for k, v in emails.items():
        label_key = k.replace("Value", "Label")
        label = infos.get(label_key, "Email")
        print(f"  ✉️ {label} : {v}")
    elif "email" in infos:  # Rétrocompatibilité anciens contacts
      print(f"  ✉️ Email : {infos['email']}")

    # 3. Affichage des autres informations importantes de Google Contacts
    if "Organization Name" in infos:
      print(f"  🏢 Entreprise : {infos['Organization Name']}")
    if "Organization Title" in infos:
      print(f"  💼 Poste : {infos['Organization Title']}")
    if "Address 1 - Formatted" in infos:
      # Remplacer les séparateurs de Google par des retours à la ligne propres
      adresse = infos["Address 1 - Formatted"].replace(" ::: ", "\n      ")
      print(f"  📍 Adresse : {adresse}")
    if "Notes" in infos:
      print(f"  📝 Notes : {infos['Notes']}")

    print("-" * 40)


def ajouter_contact(contacts):
  nom = input("Nom du contact : ").strip()
  if nom in contacts:
    print(f"⚠️ Le contact '{nom}' existe déjà.")
    return

  prenom = input("Prénom (optionnel) : ").strip()
  nom_famille = input("Nom de famille (optionnel) : ").strip()
  telephone = input("Numéro de téléphone : ").strip()
  email = input("Adresse email : ").strip()
  notes = input("Notes / Commentaires : ").strip()

  # On utilise les mêmes clés que Google pour garder une structure unifiée
  contacts[nom] = {
      "First Name": prenom if prenom else nom,
      "Last Name": nom_famille,
      "Phone 1 - Label": "Mobile",
      "Phone 1 - Value": telephone,
      "E-mail 1 - Label": "Home",
      "E-mail 1 - Value": email,
      "Notes": notes,
  }
  sauvegarder_contacts(contacts)
  print(f"✅ Contact '{nom}' ajouté avec succès !")


def rechercher_contact(contacts):
  recherche = input("Entrez le nom du contact recherché : ").strip().lower()
  trouves = {
      nom: infos
      for nom, infos in contacts.items()
      if recherche in nom.lower()
  }

  if not trouves:
    print("❌ Aucun contact trouvé.")
    return

  # On réutilise la logique d'affichage sur les résultats filtrés
  afficher_contacts(trouves)


def supprimer_contact(contacts):
  nom = input("Nom du contact à supprimer : ").strip()
  if nom in contacts:
    del contacts[nom]
    sauvegarder_contacts(contacts)
    print(f"🗑️ Contact '{nom}' supprimé avec succès.")
  else:
    print("❌ Contact introuvable.")


def menu():
  contacts = charger_contacts()

  while True:
    print("\n=== GESTIONNAIRE DE CONTACTS (VERSION COMPLÈTE) ===")
    print("1. Afficher tous les contacts et détails")
    print("2. Ajouter un contact")
    print("3. Rechercher un contact")
    print("4. Supprimer un contact")
    print("5. Quitter")

    choix = input("Choisissez une option (1-5) : ").strip()

    if choix == "1":
      afficher_contacts(contacts)
    elif choix == "2":
      ajouter_contact(contacts)
    elif choix == "3":
      rechercher_contact(contacts)
    elif choix == "4":
      supprimer_contact(contacts)
    elif choix == "5":
      print("👋 Au revoir !")
      break
    else:
      print("⚠️ Option invalide, veuillez réessayer.")


if __name__ == "__main__":
  menu()
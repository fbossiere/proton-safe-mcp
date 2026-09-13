# Proton Safe — Spécifications de l’assistant d’installation

Version de travail : 1.0 — 13 septembre 2026.

Document à transmettre à Claude Code pour implémentation. Il décrit des capacités à construire, sauf dans la section « État existant ». Il ne constitue ni une autorisation de publication ni l’annonce d’une compatibilité déjà testée.

## 1. Décisions proposées

Périmètre retenu par défaut : **Ubuntu 24.04 LTS, x86_64, session graphique GNOME, interface graphique native en français**, avec textes externalisés pour une traduction anglaise ultérieure. La validation doit couvrir Wayland et X11.

Le premier client cible est **ChatGPT desktop / Codex sur le même ordinateur et le même hôte Codex**. Leur disponibilité et leurs capacités doivent être vérifiées sur les versions effectivement testées. La mention « implémenter dans Claude Code » ne signifie pas que Claude Code devient automatiquement le client cible.

Le socle de configuration et de diagnostic doit rester indépendant de l’interface et du client. Le support automatique de Claude Code, de Claude Desktop, de Windows, de macOS et de LM Studio est une évolution ultérieure.

**Résultat attendu :** une personne sans connaissances de Python ou de MCP installe le logiciel, connecte Bridge, active Proton Safe dans son assistant et retrouve la connexion après redémarrage. Elle peut ensuite réparer ou retirer cette connexion sans modifier de fichiers à la main.

Le projet conserve son moteur Python et son serveur MCP. Aucune nouvelle interface de conversation, aucun modèle IA intégré et aucun nouveau service hébergé ne sont nécessaires.

## 2. État existant examiné

Dépôt : <https://github.com/fbossiere/proton-safe-mcp>.

Base examinée : commit `38c4e1d86270c2619f77145c223c47b751ee2394`, message `release: prepare v2.0.0`. Au début de l’implémentation, comparer ces observations avec le HEAD réel du dépôt et tenir compte des changements intervenus. Ne pas revenir à cette ancienne révision.

| Élément existant | Conséquence pour l’implémentation |
|---|---|
| Python >= 3.11, FastMCP, keyring, pypdf | Réutiliser le moteur ; ne pas le réécrire dans une autre langue. |
| `config.py` charge les paramètres depuis l’environnement | Ajouter une source de configuration persistante avec des règles de priorité explicites. |
| `cli.py` expose `setup`, `doctor`, `serve` | Préserver les commandes existantes ; partager leur logique avec le nouvel assistant. |
| `setup` stocke le mot de passe Bridge dans le trousseau | Réutiliser ce principe, mais tester un nouveau secret avant de remplacer un secret fonctionnel. |
| `secrets.py` utilise le service keyring `proton-safe-mcp` et l’utilisateur Bridge comme clé | Préserver la compatibilité des secrets déjà enregistrés. |
| Le mode historique accepte `PROTON_BRIDGE_PASSWORD` | Conserver sa compatibilité hors parcours géré ; le nouveau parcours ne doit jamais utiliser ce repli. |
| `doctor` contient déjà des diagnostics expurgés | Extraire des résultats structurés ; ne pas analyser ses phrases avec des expressions régulières. |
| Le diagnostic actuel appelle `status()`, qui récupère des compteurs INBOX | Ajouter une vérification d’authentification minimale pour l’installateur, sans statistiques de boîte. |
| Plugin dans `plugins/proton-safe/`, marketplace dans `.agents/plugins/marketplace.json` | Réutiliser les trois skills canoniques, sans copier manuellement leurs instructions. |
| Le plugin publié lance une version avec `uvx` et transmet des variables d’environnement | Le parcours géré doit lancer le runtime distribué à un chemin absolu et utiliser son fichier de configuration. |
| Documentation existante de dépannage GNOME / environnement | Les installations anciennes restent documentées ; le nouveau parcours doit supprimer ce problème à la source. |

Les chemins de code cités dans ce document sont relatifs au dépôt, généralement sous `src/proton_safe_mcp/`.

## 3. Périmètre de la V1

### Inclus — obligations P0

- Application graphique d’installation, de diagnostic et de réparation.
- Un compte Bridge configuré par utilisateur système ; plusieurs adresses d’envoi du même compte restent compatibles avec les limites existantes.
- Détection des prérequis et explication des blocages.
- Configuration locale persistante, indépendante des variables ajoutées à un terminal.
- Saisie privée du secret Bridge et utilisation du trousseau système.
- Réutilisation d’une installation ou d’un secret existant après vérification.
- Installation guidée du plugin OpenAI local avec les skills existants.
- Test du runtime MCP et distinction entre connexion locale et activation dans le client.
- Réexécution sans doublon, réparation, déconnexion et reprise après interruption.
- Paquet desktop comprenant son runtime et ses dépendances Python.
- Rapport de diagnostic exportable sans données personnelles.
- Documentation et tests des parcours critiques.

### Hors V1

- Connexion depuis ChatGPT web ou mobile, tunnel et serveur distant.
- Installation automatique de Proton Mail Bridge ou de ChatGPT/Codex ; leurs parcours officiels restent utilisés.
- Connexion au compte Proton dans l’assistant d’installation : mot de passe principal, 2FA et session Proton restent gérés par Bridge.
- Mac, Windows, ARM, WSL, machines sans session graphique, environnements conteneurisés ou versions sandboxées non validées des clients.
- Multicomptes, relais cloud, abonnement commercial, modèle local intégré.
- Nouveau mécanisme d’autorisation des brouillons ou nouveaux outils MCP.
- Accès limité à certains dossiers : fonctionnalité produit distincte, non simulée par une consigne au modèle.
- Mise à jour silencieuse du logiciel, télémétrie, analyse du contenu des messages.
- Publication d’une release dans le cadre de la seule implémentation de ces specs.

## 4. Parcours utilisateur

### Écran 1 — Bienvenue

Titre : **« Connecter Proton Mail à votre assistant »**.

Texte proposé :

> Retrouvez et résumez vos échanges Proton, puis préparez vos réponses depuis votre assistant. Vous relisez les brouillons et les envoyez vous-même dans Proton Mail.

Afficher trois informations courtes :

1. « Proton Mail Bridge et une offre Proton compatible sont nécessaires. »
2. « La connexion fonctionne sur cet ordinateur, lorsqu’il est allumé et que Bridge est connecté. »
3. « Les messages consultés par un assistant cloud sont transmis à son fournisseur. »

Mention secondaire visible : « Projet indépendant, non affilié à Proton. »

Bouton principal : **Commencer**. Une installation détectée ouvre plutôt le tableau d’état décrit en section 10.

### Écran 2 — Vérifier l’ordinateur

Présenter les vérifications sous forme de lignes avec une icône, un texte et une action utile :

| Contrôle | Résultat attendu | Action en cas de problème |
|---|---|---|
| Système | Ubuntu et architecture validés | Expliquer le périmètre pris en charge. |
| Session utilisateur | Session graphique, compte non root | Demander de relancer dans la session habituelle. |
| Trousseau | Secret Service disponible et accessible | Déverrouillage par le dialogue système, ou explication ciblée. |
| Bridge | Application connue détectée ou utilisateur indiquant qu’elle est installée | Ouvrir la page officielle ou l’application via un mécanisme vérifié. |
| Client | Au moins un hôte OpenAI compatible identifié | Choisir l’installation correcte ou ouvrir les instructions officielles. |

La détection d’un processus Bridge ne prouve pas qu’un compte est connecté. Un port ouvert ne prouve pas qu’il appartient à Bridge. L’authentification réussie à l’étape suivante constitue le contrôle fonctionnel.

Ne pas analyser des profils internes de Bridge pour en extraire des identifiants ou secrets. Ne pas lancer automatiquement un binaire seulement parce qu’il s’appelle `codex` dans un répertoire quelconque.

Un prérequis manquant bloque la progression correspondante, sans boucle ni installation silencieuse. Le runtime Python distribué ne doit pas apparaître comme un prérequis à installer par l’utilisateur.

### Écran 3 — Connecter Bridge

Afficher un guide court pour ouvrir les informations de connexion dans Bridge. Les captures éventuelles doivent utiliser des données fictives et indiquer la version de Bridge illustrée.

Champs :

- **Adresse affichée dans Bridge**, obligatoire.
- **Port IMAP**, valeur initiale `1143`, modifiable.
- **Mot de passe généré par Bridge**, masqué, collage autorisé, révélation temporaire explicite.

Le serveur hôte est fixé à `127.0.0.1` et n’est ni présenté comme choix ni configurable.

Texte sous le mot de passe : **« Utilisez le mot de passe IMAP affiché par Bridge, pas le mot de passe de votre compte Proton. Il sera conservé dans le trousseau de cet ordinateur. »**

Si un secret existe pour ce compte, présenter « Identifiant Bridge déjà enregistré » et **Tester la connexion**. Ne jamais révéler la valeur existante. Une action séparée **Modifier l’identifiant Bridge** permet son remplacement.

Bouton principal : **Tester et enregistrer**.

Séquence :

1. Valider localement l’adresse et le port.
2. Tester le nouveau secret en mémoire sur la connexion IMAP locale, avec STARTTLS comme dans le moteur existant.
3. Utiliser LOGIN puis NOOP et LOGOUT, ou l’équivalent minimal vérifié ; aucune lecture de message ni de compteur.
4. Après succès seulement, enregistrer le secret dans le trousseau et la configuration locale.
5. En cas d’échec, conserver l’ancienne configuration fonctionnelle et son secret.

Le secret n’est jamais fourni à Claude Code, à un modèle, à une ligne de commande ou à un sous-processus par variable d’environnement. L’utilisateur le saisit dans l’interface locale. Ne pas promettre un effacement mémoire garanti par Python ; limiter sa durée de vie et vider le widget dès qu’il n’est plus nécessaire.

### Écran 4 — Choisir l’assistant

Présenter les installations détectées avec des noms compréhensibles et, si nécessaire, un chemin dans « Détails ».

ChatGPT desktop et Codex partageant le même hôte doivent être présentés comme **une connexion partagée**, sans enregistrer deux serveurs identiques.

L’utilisateur choisit le client/hôte cible. Ne pas modifier tous les clients installés. Si plusieurs profils ou hôtes existent, sélectionner explicitement celui que le client confirme ; ne pas inventer une association depuis le nom d’une fenêtre.

Pour une version non prise en charge, expliquer le blocage et proposer une mise à jour par le canal officiel. Si l’installation du plugin doit être finalisée dans l’interface du client, accompagner cette étape au lieu de prétendre l’avoir automatisée.

### Écran 5 — Activer la connexion

Récapitulatif avant écriture dans le client :

- le client/hôte sélectionné ;
- le compte, masqué par défaut ;
- les usages : recherche, lecture, texte de certaines pièces jointes, préparation de brouillons ;
- « Aucun envoi, aucune suppression, aucun déplacement de message » ;
- en cas de migration, l’entrée Proton Safe précisément remplacée ou désactivée.

Bouton : **Activer dans [nom du client]**.

Cette action autorise les modifications annoncées. Ne pas multiplier les confirmations pour chaque fichier technique. Les dialogues imposés par le trousseau ou le client restent visibles et sont respectés.

Le client peut démarrer un serveur lorsqu’un plugin est installé : il ne faut donc enregistrer le plugin qu’après la sauvegarde réussie de la configuration et du secret.

### Écran 6 — Vérifier et démarrer

Afficher trois niveaux distincts :

1. **Bridge connecté** : authentification minimale réussie.
2. **Serveur prêt** : lancement du runtime exact configuré, négociation MCP et liste d’outils validées.
3. **Connexion active dans votre assistant** : preuve obtenue auprès du client, ou validation manuelle clairement identifiée.

Pour le niveau 2, ne pas appeler d’outil qui lit ou modifie le courrier. La présence des outils s’obtient via `initialize` et `tools/list`.

Pour le niveau 3, si aucune API fiable du client ne permet de confirmer le chargement effectif, afficher **« Configuration enregistrée — vérification dans [client] nécessaire »**. Guider l’ouverture d’une nouvelle conversation et la vérification des outils. Un bouton « J’ai vérifié dans mon assistant » enregistre une confirmation manuelle, jamais une preuve automatique.

Ne pas envoyer automatiquement de prompt dans le client. Proposer un texte copiable :

> Vérifie que les outils Proton Safe sont disponibles, sans lire mes messages ni créer de brouillon.

Puis, comme première utilisation volontaire et non comme test technique automatique :

> Retrouve les échanges concernant [mon dossier] et résume les points encore ouverts.

Ne pas créer un brouillon de test automatiquement. Ne pas fermer de force le client : proposer son redémarrage lorsque nécessaire, en laissant l’utilisateur préserver son travail.

## 5. Architecture technique proposée

### 5.1 Socle partagé

Conserver Python. Ajouter un service d’installation testable, séparé des widgets et du protocole MCP. Modules indicatifs :

```text
src/proton_safe_mcp/
  config.py                  # modèle de paramètres et compatibilité historique
  configuration_store.py     # fichier TOML et écritures privées
  secrets.py                 # accès au trousseau, politique de source des secrets
  doctor.py                  # diagnostics structurés et rendu CLI
  mail.py                    # connexion IMAP réutilisée ; probe minimal
  onboarding/
    service.py               # orchestration et transitions
    models.py                # états, résultats, codes d’erreur
    inventory.py             # découverte ciblée des installations
    ownership.py             # ressources gérées et reprise
    clients/
      base.py                # contrat d’un adaptateur
      openai_local.py        # hôte local ChatGPT/Codex
  desktop/
    app.py                   # interface PySide6
    ...
```

Ce découpage est indicatif : préférer une structure plus courte si elle conserve les séparations utiles.

Choix proposé : **PySide6 / Qt Widgets**, interfaces natives, dépendance optionnelle du paquet desktop. Le paquet MCP installé par PyPI doit continuer à fonctionner sans Qt. Importer le code graphique uniquement lorsqu’on démarre l’assistant.

L’assistant n’est pas piloté par une IA. Il n’expose ni HTTP local, ni endpoint d’installation accessible au modèle, ni nouveau serveur MCP. Ses échanges avec le runtime et les CLI passent par des appels de bibliothèque ou des processus locaux bornés.

### 5.2 Configuration persistante

Emplacement par défaut : `$XDG_CONFIG_HOME/proton-safe-mcp/config.toml`, sinon `~/.config/proton-safe-mcp/config.toml`.

Exemple de schéma proposé, avec données fictives :

```toml
schema_version = 1

[bridge]
user = "person@example.com"
imap_port = 1143
aliases = []
```

- Aucun mot de passe, token ou hôte réseau configurable dans ce fichier.
- Les limites existantes gardent leurs valeurs et bornes actuelles. Si des valeurs avancées doivent être migrées, les conserver dans une table `[limits]` explicitement typée et documentée.
- Pour `state_dir`, conserver la logique XDG existante et la possibilité historique de personnalisation. Toute valeur migrée doit être validée sans parcourir ni déplacer les pièces jointes.
- Schéma fermé pour cette version : erreur explicite sur une clé inconnue ; version de schéma future non comprise = refus sans réécriture.
- Répertoire `0700`, fichier `0600`, propriétaire attendu.
- Écriture atomique, temporaire privé dans le même répertoire, protection contre liens symboliques et vérification du fichier effectivement ouvert. Ne pas modifier récursivement les permissions du domicile.
- Une lecture ne crée pas de répertoire et ne répare pas silencieusement une configuration.

### 5.3 Règles de chargement et rétrocompatibilité

Ajouter le paramètre proposé `--config <chemin-absolu>` aux commandes concernées. Les entrées créées par le nouvel assistant passent **toujours un chemin explicite** :

```text
/opt/proton-safe-assistant/proton-safe-mcp serve --config /home/USER/.config/proton-safe-mcp/config.toml
```

Ce sont des interfaces proposées à implémenter, pas des commandes déjà présentes.

Deux modes sans ambiguïté :

| Mode | Source des paramètres | Source du secret |
|---|---|---|
| `--config` explicite, parcours géré | Fichier explicite puis valeurs par défaut ; aucune surcharge par `PROTON_*` | Trousseau uniquement |
| Commande historique sans `--config` | Comportement historique conservé, depuis l’environnement | Politique historique conservée |

**Ne pas ajouter de lecture implicite du nouveau fichier au mode historique dans cette V1.** Cela évite qu’un fichier créé pour le desktop modifie une installation existante non migrée.

Un fichier explicite absent, invalide ou trop permissif doit faire échouer le démarrage ; aucun repli silencieux vers l’environnement. Le diagnostic indique l’origine de configuration sans afficher ses valeurs privées.

Les variables de session nécessaires au trousseau, notamment D-Bus et XDG, restent utilisables : l’indépendance vis-à-vis de `PROTON_*` ne signifie pas supprimer la session utilisateur.

Les paramètres du plugin public existant peuvent être améliorés ultérieurement, mais il faut préserver le parcours historique dans le même changement et éviter les doubles enregistrements.

### 5.4 Secret et connexion de test

Introduire une abstraction légère permettant de tester un secret candidat en mémoire sans l’enregistrer. Réutiliser le même code de connexion IMAP que le serveur ; ne pas dupliquer une implémentation TLS.

Pour le parcours géré, accepter le backend Secret Service validé pour Ubuntu. Un backend absent, verrouillé ou stockant les secrets en clair ne doit jamais déclencher un repli vers un fichier, l’environnement ou le JSON du client.

Une éventuelle écriture de contrôle du trousseau utilise une valeur aléatoire non sensible sous une clé temporaire propre à l’assistant, puis la supprime. Ne pas toucher à d’autres entrées.

L’hôte reste `127.0.0.1`. Préserver le modèle STARTTLS existant ; ne pas étendre la non-vérification du certificat à d’autres hôtes. La connexion locale à Bridge ne doit pas être décrite comme une protection contre un processus malveillant sous le même compte système.

### 5.5 Contrat de l’adaptateur client

Un adaptateur doit pouvoir :

- découvrir de façon ciblée les installations connues ;
- décrire les capacités effectivement disponibles ;
- lire seulement les entrées nécessaires pour identifier un Proton Safe existant ;
- produire un plan de modification avant mutation ;
- appliquer ce plan, vérifier le résultat et rendre compte d’une activation partielle ;
- retirer ses seules ressources gérées ;
- exposer une action manuelle lorsque le client ne fournit pas d’interface automatisable stable.

Préférer les CLI documentées du client. Vérifier leurs sous-commandes et formats de sortie sur les versions prises en charge ; ne pas déduire les capacités du seul numéro de version.

Appeler les processus avec une liste d’arguments, sans shell. Borner leur durée, leur sortie et le nombre de tentatives. Les sorties brutes ne sont ni exportées ni montrées comme messages d’erreur : elles peuvent contenir des chemins, adresses ou secrets d’autres intégrations.

Les chemins de binaires doivent venir de sources connues et être corroborés par leur installation/version, ou être choisis explicitement dans l’interface. `/usr/lib/chatgpt/resources/codex` est un candidat dépendant d’un paquet, pas une constante universelle ni une garantie de compatibilité.

### 5.6 Plugin OpenAI géré

Produire un plugin local à partir des ressources canoniques embarquées dans le paquet desktop : manifeste, trois skills et configuration MCP. Aucun téléchargement de `main` pendant l’installation.

- Le nom du plugin reste cohérent avec Proton Safe ; utiliser une marketplace propre au parcours desktop pour éviter la collision avec la marketplace générique `personal`.
- Choix proposé : marketplace `proton-safe-desktop`, plugin `proton-safe` ; identifiant réel validé contre le client.
- Le serveur pointe vers le runtime desktop à un chemin absolu et passe `--config`.
- La configuration gérée ne requiert ni `uvx` ni `PROTON_BRIDGE_USER` dans la session graphique.
- La version du plugin et les mécanismes de rafraîchissement/cache du dépôt sont mis à jour avec le paquet ; le manifeste de provenance conserve la version du moteur et le digest des ressources.
- Utiliser les commandes officielles de marketplace. Automatiser l’installation du plugin seulement si la version détectée le permet ; sinon guider l’installation depuis le répertoire local déclaré.
- Ne pas écrire directement dans le cache privé du client et ne pas y appliquer de correctif.
- Ne pas remplacer les skills par une simple configuration MCP : le parcours produit doit conserver les workflows de lecture et de préparation de brouillons existants.

Le premier lot technique doit prouver cette intégration sur un client réel. Si le client n’accepte pas le mode local décrit, rendre ce blocage visible et réviser l’adaptateur avant de promettre l’installation complète. Ne pas transformer silencieusement la cible en client distant ou en autre assistant.

## 6. Diagnostic et état d’exécution

États minimaux :

```text
NEW → PREREQUISITES_READY → BRIDGE_VALIDATED → LOCAL_CONFIG_SAVED
    → CLIENT_REGISTRATION_PENDING → CLIENT_REGISTERED
    → CLIENT_VERIFICATION_PENDING → READY
```

Ajouter `REPAIR_REQUIRED`, `DISCONNECTED`, `CANCELLED` et un résultat d’échec avec code stable. Ces états décrivent des faits enregistrés ; ils ne permettent pas de sauter les contrôles lors d’une reprise.

Une relance reconstruit l’état réel à partir de la configuration, du trousseau, du runtime et du client. La présence de `READY` dans un fichier ne prouve pas que Bridge fonctionne aujourd’hui.

Ajouter `doctor --json`, rétrocompatible avec le rendu texte existant. Exemple proposé :

```json
{
  "schema_version": 1,
  "overall": "action_required",
  "checks": [
    {"id": "keyring", "status": "pass", "code": "KEYRING_AVAILABLE"},
    {"id": "bridge", "status": "pass", "code": "BRIDGE_AUTHENTICATED"},
    {"id": "client", "status": "action_required", "code": "CLIENT_RESTART_REQUIRED"}
  ]
}
```

Le schéma ne contient aucune valeur de configuration, adresse, nom de dossier, statistique de boîte, chemin personnel ni sortie brute. Les versions du logiciel, du système et du client peuvent figurer dans une section explicitement autorisée. Les messages traduits proviennent des codes internes.

Propositions de bornes : découverte CLI 5 secondes par commande, vérification IMAP 15 secondes au total, initialisation MCP 30 secondes. Prévoir une annulation effective ; une interface qui affiche « annulé » alors qu’un worker poursuit les écritures est incorrecte. Une nouvelle tentative manuelle est toujours possible. Pas de boucle de reconnexion infinie.

Les appels potentiellement lents au trousseau et au réseau n’immobilisent pas le thread graphique. Les phases de commit locales sont courtes et non interrompues au milieu d’une écriture.

## 7. Installation existante, migration et reprise

Détecter séparément :

1. installation inexistante ;
2. configuration et secret existants, client absent ;
3. installation historique fonctionnelle ;
4. installation partielle ;
5. plusieurs entrées Proton Safe ou entrées modifiées manuellement.

La migration est un plan visible : « Conserver votre compte et votre identifiant Bridge ; utiliser le runtime desktop ; remplacer cette connexion dans cet assistant. »

- Réutiliser un secret fonctionnel sans en demander la ressaisie.
- Ne pas désinstaller `uv`, Python ou la version PyPI existante.
- Ne pas supprimer les anciens fichiers `environment.d`, profils shell ou lanceurs personnalisés. La nouvelle connexion doit les ignorer ; signaler les éléments historiques éventuels dans les détails.
- Identifier une ancienne connexion par ses caractéristiques observées, pas uniquement parce que son nom contient « proton ».
- En cas de collision ou de doute sur le propriétaire d’une entrée, demander un choix ciblé dans l’assistant ; ne pas écraser.
- Ne pas créer deux serveurs actifs pour le même parcours géré. Si la désactivation de l’ancien nécessite une action du client, l’intégration reste en attente jusqu’à sa résolution.

Conserver un journal local minimal des ressources créées, versions, digests et étapes réussies, dans un répertoire privé de l’assistant. Il ne contient pas de secret. Il sert à la reprise et à la déconnexion, pas à une surveillance de l’utilisateur.

Une transaction entre trousseau, fichiers et client n’est pas atomique. Implémenter des étapes compensables :

- erreur de nouveau secret : aucune modification ;
- erreur d’écriture de fichier après changement de secret : restaurer l’ancienne valeur tant qu’elle est disponible en mémoire ;
- arrêt brutal entre étapes : détecter l’incohérence au démarrage suivant et proposer la réparation ; aucun secret ancien écrit sur disque pour faciliter le rollback ;
- échec d’enregistrement client : conserver la connexion locale valide, afficher « activation dans le client à terminer », permettre de reprendre ;
- annulation avant engagement : nettoyer seulement les temporaires de cette opération.

Ne jamais restaurer aveuglément un fichier complet du client si une autre opération l’a modifié entre-temps. Si une sauvegarde complète est exceptionnellement nécessaire, la considérer comme sensible, la garder privée et ne jamais l’inclure dans les diagnostics.

## 8. Sécurité et limites à préserver

Exigences liées à ce changement :

- Aucun nouveau pouvoir d’envoi, suppression, déplacement ou téléchargement brut de pièces jointes reçues.
- Aucun accès au mot de passe principal Proton, récupération, 2FA ou session web.
- Aucune modification des règles de confirmation des brouillons.
- Aucune lecture de message ou création de brouillon pendant les tests automatiques de l’installateur.
- Aucune exposition réseau supplémentaire du serveur ; transport STDIO conservé.
- Aucun secret dans les fichiers de configuration, arguments de processus, variables du parcours géré, journaux, rapports ou télémétrie.
- Aucun accès récursif aux configurations de tous les assistants ou à tous les secrets du trousseau.
- Ressources statiques et liens officiels embarqués ; aucun téléchargement suivi d’exécution automatique d’un script distant.
- Exécution de l’assistant sous l’utilisateur courant, jamais en root. Seul le gestionnaire de paquets du système peut demander ses privilèges habituels pour installer le paquet.
- Ne pas annoncer « tout reste sur votre ordinateur » lorsque le client utilise un modèle cloud.

Les tests doivent couvrir ces limites. Ne pas introduire une nouvelle couche de promesses de sécurité ou de confirmation que le serveur ne saurait faire respecter.

## 9. Messages d’erreur et actions

| Code | Texte utilisateur | Action |
|---|---|---|
| `BRIDGE_UNREACHABLE` | « Bridge ne répond pas sur cet ordinateur. » | Ouvrir Bridge, vérifier le port, réessayer. |
| `BRIDGE_AUTH_FAILED` | « Les informations de connexion ne sont pas acceptées. » | Vérifier l’adresse et le mot de passe généré par Bridge. |
| `BRIDGE_TLS_FAILED` | « La connexion locale à Bridge n’a pas pu être sécurisée. » | Vérifier Bridge et le port ; ne pas désactiver STARTTLS. |
| `KEYRING_LOCKED` | « Le trousseau de votre session est verrouillé. » | Déverrouiller avec le dialogue système. |
| `KEYRING_UNAVAILABLE` | « Le trousseau nécessaire n’est pas disponible. » | Afficher la procédure Ubuntu prise en charge. |
| `UNSUPPORTED_CLIENT` | « Cette version de votre assistant ne permet pas cette installation. » | Ouvrir les instructions de mise à jour. |
| `CLIENT_RESTART_REQUIRED` | « Redémarrez votre assistant pour charger Proton Safe. » | Laisser l’utilisateur terminer son travail puis revérifier. |
| `CLIENT_ACTION_REQUIRED` | « Terminez l’activation dans votre assistant. » | Montrer l’étape précise dans le client. |
| `CONFIG_CONFLICT` | « Une connexion Proton Safe existe déjà et diffère de celle proposée. » | Examiner et choisir une migration ciblée. |
| `CONFIG_INVALID` | « La configuration enregistrée ne peut pas être utilisée. » | Réparer sans l’écraser automatiquement. |
| `CONFIG_PERMISSIONS` | « La configuration n’est pas protégée correctement. » | Proposer une correction ciblée sur les fichiers du produit. |
| `RUNTIME_START_FAILED` | « Le composant de connexion n’a pas démarré. » | Retester ; proposer le diagnostic expurgé. |
| `INSTALLATION_INCOMPLETE` | « L’installation précédente s’est interrompue. » | Reprendre après vérification de l’état réel. |

Ne pas classer systématiquement une erreur réseau comme un mot de passe incorrect. Utiliser un code générique de connexion si la cause ne peut pas être déterminée de façon fiable.

## 10. Utilisation après installation

À la réouverture, afficher un tableau simple : compte masqué, version, Bridge, serveur, client, dernière vérification. Actions :

- **Vérifier la connexion** ;
- **Réparer la connexion** ;
- **Modifier les informations Bridge** ;
- **Copier un diagnostic** avec aperçu expurgé ;
- **Déconnecter Proton Safe**.

La réparation réutilise le parcours et corrige uniquement les différences détectées. Elle ne réinstalle pas tout par défaut.

La déconnexion affiche ses conséquences puis retire ou désactive les seules entrées gérées du client. Distinguer cette action de **« Effacer aussi la configuration et l’identifiant enregistrés par Proton Safe »**, désactivée par défaut. Un secret préexistant ou partagé avec une installation historique n’est pas effacé implicitement.

Un processus MCP déjà démarré peut rester actif après le retrait d’une configuration. Demander au client sa désactivation par une interface documentée ou indiquer qu’un redémarrage est nécessaire. Ne pas annoncer la révocation immédiate tant que l’arrêt du processus actif n’est pas confirmé. Ne pas tuer des processus trouvés uniquement par leur nom.

La déconnexion ne touche pas à Bridge, aux mails, aux brouillons ou aux pièces jointes de l’utilisateur. Le programme n’effectue aucun nettoyage général de `~/.codex`, `~/.config` ou du trousseau.

## 11. Distribution et ergonomie

### Paquet desktop

Choix proposé : **bundle PyInstaller en mode répertoire, distribué dans un paquet `.deb` pour Ubuntu 24.04 x86_64**. Le build contient le runtime Python, le serveur, l’interface et les dépendances nécessaires. Qt et PyInstaller sont des dépendances desktop/build, pas des dépendances imposées aux utilisateurs du serveur PyPI.

Exemple d’implantation :

```text
/opt/proton-safe-assistant/               # runtime et ressources installés par le paquet
/opt/proton-safe-assistant/proton-safe-mcp
/usr/bin/proton-safe-assistant           # entrée graphique, sans secret ni valeur utilisateur
/usr/share/applications/proton-safe-assistant.desktop
```

Les données utilisateur restent dans les répertoires XDG privés. Le paquet et ses scripts d’installation ne doivent pas rechercher une session utilisateur, créer sa configuration ou accéder à son trousseau avec des privilèges système.

Le runtime MCP et l’interface sont versionnés ensemble. Les noms/chemins ne doivent pas masquer ou écraser une installation historique du CLI dans `~/.local/bin`.

Valider les modules dynamiques de keyring, les bibliothèques de Secret Service et les plugins Qt dans le paquet final. Un build qui démarre sur le poste de développement ne prouve pas que ces dépendances sont embarquées.

Le `.deb` est une décision de départ, à éprouver tôt : tester l’ouverture et l’installation depuis le gestionnaire graphique d’une installation Ubuntu de référence. Si cela exige d’installer préalablement un outil non standard ou d’utiliser le terminal, documenter ce blocage et choisir une distribution qui satisfait le parcours avant d’annoncer la V1 comme accessible sans terminal.

Pas de mise à jour en arrière-plan dans cette V1. Les mises à jour passent par un nouveau paquet vérifié ; elles conservent configuration et secret, puis relancent le diagnostic. Une désinstallation du paquet ne supprime pas les données privées utilisateur dans ses scripts système.

### Interface

- Fenêtre redimensionnable, utilisable sur 1280 × 720 et avec facteur d’échelle 200 %.
- Navigation clavier complète, libellés accessibles et focus visible.
- Statuts accompagnés de texte, jamais distingués uniquement par la couleur.
- Boutons Retour / Continuer / Annuler cohérents ; préserver les champs non sensibles lors d’un retour.
- Détails techniques repliés par défaut ; aucune instruction demandant de modifier du TOML ou du JSON dans le parcours normal.
- Aucune formule « terminé » si une étape du client reste en attente.
- L’ouverture du navigateur se limite aux liens officiels fixes et à la demande de l’utilisateur.

## 12. Tests et critères d’acceptation

### Automatisés, avec doublures IMAP et client

| ID | Scénario | Résultat requis |
|---|---|---|
| A01 | Mode historique sans fichier explicite | Même comportement que la version actuelle. |
| A02 | Mode géré avec environnement `PROTON_*` contradictoire | Le fichier explicite et le trousseau sont seuls utilisés. |
| A03 | Secret présent uniquement dans l’environnement, mode géré | Échec clair ; aucun repli. |
| A04 | Fichier absent, schéma inconnu, lien symbolique ou permissions invalides | Refus sans écrire ni charger une autre source. |
| A05 | Mauvais nouveau secret avec ancienne installation valide | Ancien secret et ancienne configuration conservés. |
| A06 | Échec / interruption entre persistance et enregistrement client | Reprise possible, état partiel explicite, absence de secret sur disque. |
| A07 | Deux exécutions identiques | Une configuration, une connexion gérée, aucun doublon. |
| A08 | Connexion Proton Safe non gérée ou modifiée entre lecture et écriture | Conflit visible, aucune réécriture globale. |
| A09 | Client démarrant avec configuration gérée après redémarrage, sans exports | Authentification via trousseau et démarrage MCP réussis. |
| A10 | Initialisation MCP du runtime packagé | Liste d’outils conforme à la release ; aucun nouvel outil sensible. |
| A11 | Test d’installation | Aucune commande IMAP de lecture de courrier ou d’écriture ; aucun brouillon. |
| A12 | Sorties adverses de CLI et exceptions contenant secrets/adresses fictifs | Aucune fuite dans rapport, logs, messages UI ou arguments de processus. |
| A13 | Trousseau verrouillé ou backend non approuvé | Blocage ciblé ; pas de stockage de remplacement. |
| A14 | Annulation pendant test lent | Interface réactive, opération arrêtée ou phase critique explicitement achevée ; aucune écriture tardive. |
| A15 | Retrait de la connexion | Seules les ressources gérées sont touchées ; arrêt effectif ou redémarrage requis correctement annoncé. |
| A16 | Plugin historique actif | Migration ciblée, pas de double serveur, conservation des autres plugins. |
| A17 | GUI non installée | Serveur PyPI, CLI historique et tests du moteur fonctionnent sans Qt. |
| A18 | Mise à jour du paquet et ressources du plugin | Runtime et skills cohérents ; invalidation du cache documentée et vérifiée. |
| A19 | Test local réussi mais aucun retour du client | Statut « vérification client nécessaire », jamais READY automatique. |

Les tests doivent vérifier des comportements et des effets réels. Ne pas se limiter à rechercher des phrases ou des noms de fonctions dans les fichiers.

### Tests du paquet et essais humains

Le paquet est essayé sur un environnement Ubuntu de référence sans `uv`, Git, pip utilisateur ni environnement Python de développement. Les bibliothèques système explicitement nécessaires peuvent être résolues par le gestionnaire de paquets.

Avec Bridge et le client déjà installés :

1. Installer et ouvrir le logiciel par le parcours graphique documenté.
2. Réaliser la connexion avec un compte de test du mainteneur ; aucun secret communiqué à l’agent de développement.
3. Fermer puis rouvrir l’assistant depuis le menu système.
4. Redémarrer la session ou la machine, ouvrir Bridge et le client normalement, vérifier la connexion.
5. Modifier le secret dans Bridge, constater le diagnostic puis réparer.
6. Tester l’annulation, la réinstallation, la déconnexion et une mise à jour du paquet.

Objectif d’utilisabilité proposé : **au moins 3 testeurs sur 5 obtiennent le premier résultat en moins de 10 minutes, sans terminal ni aide orale**, après installation et connexion préalable de Bridge et du client. Ce seuil est un objectif de validation, pas une promesse de performance déjà acquise. Chronométrer séparément le téléchargement et l’installation des prérequis.

Recueillir uniquement, avec leur accord, le système, les versions, l’étape bloquante, le temps et l’issue. Aucun contenu de mail ni identifiant dans les retours.

Si Bridge ou un client réel n’est pas accessible à Claude Code, terminer les tests simulés et le paquet, puis fournir la procédure manuelle restante. Ne pas déclarer le parcours réel validé sur la base de mocks.

## 13. Ordre d’implémentation et livrables

### Lot 0 — Prouver le chemin de distribution

- Lire les instructions du dépôt et rapprocher ces specs du HEAD.
- Vérifier le client cible et le parcours de plugin local sur une version réelle.
- Produire un premier paquet desktop minimal qui démarre, atteint le trousseau et lance le runtime MCP embarqué.
- Consigner versions, contraintes et éventuelles modifications nécessaires au choix `.deb` / PySide6.

Ne pas construire tous les écrans avant d’avoir prouvé ces dépendances.

### Lot 1 — Configuration et diagnostic

- Source TOML explicite, mode géré et rétrocompatibilité.
- Secret candidat en mémoire, sonde Bridge minimale et persistance privée.
- Résultats de diagnostic structurés et CLI JSON.
- Tests de priorité, validation, secret et non-régression.

### Lot 2 — Service d’installation et intégration client

- Inventaire ciblé, plan de modification, plugin géré.
- Détection des doublons, migration, reprise et retrait.
- Vérification du runtime exact et états de confirmation client.
- Tests avec faux client et preuve sur client réel lorsqu’il est disponible.

### Lot 3 — Interface graphique et parcours complet

- Écrans de configuration et tableau d’état.
- Erreurs compréhensibles, opérations asynchrones et annulation.
- Réparation et export expurgé.
- Vérification graphique des écrans, clavier et facteurs d’échelle.

### Lot 4 — Paquet final et validation

- Build automatisé du paquet desktop et vérification dans un environnement propre.
- Guide utilisateur, guide de test, matrice des versions réellement prises en charge.
- Mise à jour des docs d’installation et migration, sans supprimer la voie CLI historique.
- Conservation des workflows de release existants ; ajout d’un build CI desktop sans publication automatique non demandée.
- Exécution des contrôles existants : tests, Ruff, format, mypy strict, build, audit de dépendances et documentation selon le dépôt.

Livrables à remettre : code et tests, paquet installable, scripts reproductibles de construction, documentation, rapport de validation distinguant simulé / réel / non testé, et courte liste des limites restantes. Aucune clé ni donnée personnelle dans ces livrables.

## 14. Sources techniques à revalider pendant l’implémentation

- [Proton Mail Bridge](https://proton.me/mail/bridge) : prérequis et connexion locale.
- [Systèmes pris en charge par Bridge](https://proton.me/support/operating-systems-supported-bridge) : ne pas confondre compatibilité de Bridge et compatibilité de Proton Safe.
- [MCP dans ChatGPT desktop et Codex](https://learn.chatgpt.com/docs/extend/mcp) : configuration du même hôte, commandes et serveurs apportés par les plugins.
- [Packaging des plugins OpenAI](https://developers.openai.com/plugins/build/plugins) : marketplaces locales et parcours d’installation dans le client.
- [Déploiement Qt for Python](https://doc.qt.io/qtforpython-6/deployment/index.html) : interface desktop et contraintes de distribution.
- [Fonctionnement de PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html) : runtime embarqué, mode répertoire et limites liées à la plateforme.

Les formats proposés dans ce document qui concernent Proton Safe sont des décisions de conception. Les formats appartenant aux clients doivent être vérifiés dans leurs outils/documentations actuels et dans des tests d’intégration, sans inventer de commande manquante.
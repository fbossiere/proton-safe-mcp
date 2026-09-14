---
locale: fr
---

# Proton Safe pour Windows — statut

[English](../windows-installer.md)

!!! warning "Pas encore disponible"
    **Au 14 septembre 2026, il n'existe aucun téléchargement Windows.** Des contrôles
    automatiques exercent le code et la fabrication sur Windows Server. La validation
    complète sur Windows 11, avec Bridge et un assistant réel, reste à faire : la
    [fiche de recette](../windows-acceptance.md) est entièrement au statut « non testé ».

    Tant que ce n'est pas le cas, Proton Safe ne doit pas être présenté comme compatible
    Windows, et aucun bouton de téléchargement Windows ne doit être publié. Si vous
    cherchez une version utilisable aujourd'hui, c'est
    [la version Ubuntu](telecharger.md).

## Ce qui est prévu

Un fichier unique, `ProtonSafe-Setup-<version>-x64.exe`, signé, publié dans la même
version GitHub que le paquet Ubuntu.

Une personne sans connaissances techniques télécharge ce fichier, installe Proton Safe
dans sa session Windows, connecte Proton Mail Bridge et active la connexion dans un
assistant local compatible. Ni Python, ni `uv`, ni terminal, ni mot de passe
administrateur.

| | |
|---|---|
| Système | Windows 11 Famille et Pro, 64 bits (x64) natif |
| Installation | Pour votre compte Windows uniquement, sans élévation |
| Langue | Français et anglais, selon la langue du système |
| Mot de passe Bridge | Gestionnaire d'identifiants Windows, sur cet ordinateur seulement |
| Mises à jour | Relancer un installateur plus récent ; réglages et identifiants conservés |

Windows 10, le mode S, les versions 32 bits, les processeurs ARM, WSL, Windows Server et
l'installation à distance sont hors périmètre. Ce n'est pas un oubli : Proton indique que
Bridge exclut les appareils ARM hors puces Apple, et rien de tout cela n'a été validé.

## Ce qu'il faudra avoir, sur le même ordinateur

- **Windows 11 en 64 bits (x64)**, avec votre compte Windows habituel.
- **[Proton Mail Bridge](https://proton.me/mail/bridge)** installé, ouvert et connecté à
  votre compte, avec un forfait Proton payant qui inclut Bridge.
- **Un assistant local compatible**, installé sur cet ordinateur. Un compte dans le
  navigateur ne suffit pas.

L'installateur pose le logiciel ; la connexion au compte se fait ensuite dans l'assistant
graphique. L'absence de Bridge ou d'assistant n'empêche pas d'installer le logiciel : elle
est expliquée à l'ouverture.

!!! info "Avant de confier vos messages à un assistant"
    Avec un modèle d'IA dans le cloud, le contenu des messages lus par votre assistant est
    envoyé à son fournisseur. Proton Safe ne possède aucun outil d'envoi, de suppression
    ou de déplacement : les brouillons confirmés attendent votre relecture et votre envoi
    dans Proton Mail. [Modèle de sécurité (EN)](../security-model.md).

## Où sera rangé quoi

| Élément | Emplacement |
|---|---|
| Programme | `%LOCALAPPDATA%\Programs\Proton Safe\` |
| Réglages | `%LOCALAPPDATA%\Proton Safe\config\` |
| État et pièces jointes temporaires | `%LOCALAPPDATA%\Proton Safe\state\` |
| Mot de passe Bridge | Gestionnaire d'identifiants Windows |

Ces dossiers reçoivent une liste de contrôle d'accès qui n'autorise que votre compte et
les comptes système nécessaires, sans héritage du dossier parent. Cette protection vise
les autres comptes ordinaires de l'ordinateur et le stockage accidentel en clair. Elle ne
protège pas d'un programme malveillant exécuté sous votre propre compte, d'un
administrateur, ni d'un système compromis.

Proton Safe n'ouvre aucun port, ne crée aucune règle de pare-feu et ne modifie pas le
magasin de certificats Windows. La connexion à Bridge reste sur la boucle locale.

## Mise à jour, réparation, désinstallation

Relancer un installateur plus récent met à jour l'installation existante et conserve vos
réglages, votre mot de passe enregistré, le journal de connexion et vos autres plugins.
Le même numéro de version propose de **réparer les fichiers**. Une version plus ancienne
est refusée, avec un message lisible : elle ne saurait pas relire les réglages écrits par
la plus récente.

La désinstallation passe par **Paramètres → Applications → Applications installées →
Proton Safe**. Elle retire d'abord, dans votre session, les inscriptions créées par cette
installation, puis les fichiers du programme. Vos réglages et votre mot de passe sont
conservés par défaut, pour une réinstallation ; les effacer est une case à cocher
distincte, décochée. Si l'assistant refuse le retrait, tout est conservé pour pouvoir
réessayer, et la déconnexion n'est pas annoncée à tort.

## Avertissements que nous ne contournerons pas

Signer un fichier et avoir une réputation auprès de Windows sont deux choses différentes.
Un installateur récemment publié peut déclencher un avertissement SmartScreen même
correctement signé. **Nous ne demanderons jamais de désactiver SmartScreen ou Microsoft
Defender**, et un faux positif sera traité avant de présenter le paquet au grand public.

## Suivre l'avancement

- [Fiche de recette Windows (EN)](../windows-acceptance.md) — les 21 scénarios et leur statut.
- [Documentation technique de l'installateur (EN)](../windows-installer.md) — les décisions et ce qui reste ouvert.

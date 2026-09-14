"""User-visible text, externalised so an English translation needs no code change.

Nothing here interpolates a private value. Messages are selected by stable code, never by
matching on an exception message, and never built from raw command output.
"""

from __future__ import annotations

import os
from typing import Final

from ..platform_services import services
from .models import Code

DEFAULT_LANGUAGE: Final = "fr"
SUPPORTED_LANGUAGES: Final = ("fr", "en")


def detect_language() -> str:
    """Pick a supported language from the session, defaulting to French."""
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable, "")
        tag = value.split(".")[0].split("_")[0].lower()
        if tag in SUPPORTED_LANGUAGES:
            return tag
    return DEFAULT_LANGUAGE


#: message key -> language -> text.
CATALOGUE: Final[dict[str, dict[str, str]]] = {
    "progress.dashboard": {"fr": "Votre connexion", "en": "Your connection"},
    "client.intro": {
        "fr": "Choisissez l'application dans laquelle retrouver vos outils Proton Safe.",
        "en": "Choose the application where you want to use your Proton Safe tools.",
    },
    "activate.start": {"fr": "Activer la connexion", "en": "Activate connection"},
    "verify.dashboard": {"fr": "Voir ma connexion", "en": "View my connection"},
    "dashboard.erase.short": {
        "fr": "Effacer aussi les données de connexion",
        "en": "Also erase saved connection details",
    },
    "progress.step": {"fr": "Étape {current} sur {total}", "en": "Step {current} of {total}"},
    "welcome.feature.find": {
        "fr": "Retrouvez le bon échange",
        "en": "Find the conversation you need",
    },
    "welcome.feature.summarise": {
        "fr": "Faites le point en quelques mots",
        "en": "Get a concise summary",
    },
    "welcome.feature.draft": {
        "fr": "Préparez une réponse, gardez le dernier mot",
        "en": "Prepare a reply. Keep the final say.",
    },
    "prereq.intro": {
        "fr": "Vérifions que tout est prêt pour connecter votre messagerie.",
        "en": "Let's make sure everything is ready to connect your mail.",
    },
    "prereq.bridge_help": {"fr": "Obtenir Proton Mail Bridge", "en": "Get Proton Mail Bridge"},
    "bridge.advanced": {
        "fr": "Options avancées",
        "en": "Advanced options",
    },
    # -- application ---------------------------------------------------------
    "app.start_failed": {
        "fr": (
            "Proton Safe n'a pas pu démarrer. Vérifiez que votre dossier de données est "
            "accessible et qu'aucune autre ouverture n'est en cours, puis réessayez."
        ),
        "en": (
            "Proton Safe could not start. Check that your data folder is accessible "
            "and no other launch is in progress, then try again."
        ),
    },
    "app.title": {
        "fr": "Connecter Proton Mail à votre assistant",
        "en": "Connect Proton Mail to your assistant",
    },
    "app.name": {"fr": "Proton Safe", "en": "Proton Safe"},
    "app.independent": {
        "fr": "Projet indépendant, non affilié à Proton.",
        "en": "Independent project, not affiliated with Proton.",
    },
    # -- welcome -------------------------------------------------------------
    "welcome.intro": {
        "fr": (
            "Retrouvez et résumez vos échanges Proton, puis préparez vos réponses depuis "
            "votre assistant. Vous relisez les brouillons et les envoyez vous-même dans "
            "Proton Mail."
        ),
        "en": (
            "Find and summarise your Proton conversations, then prepare replies from your "
            "assistant. You review the drafts and send them yourself in Proton Mail."
        ),
    },
    "welcome.point.bridge": {
        "fr": "Proton Mail Bridge et une offre Proton compatible sont nécessaires.",
        "en": "Proton Mail Bridge and a compatible Proton plan are required.",
    },
    "welcome.point.local": {
        "fr": (
            "La connexion fonctionne sur cet ordinateur, lorsqu'il est allumé et que "
            "Bridge est connecté."
        ),
        "en": ("The connection works on this computer, while it is on and Bridge is connected."),
    },
    "welcome.point.cloud": {
        "fr": ("Les messages consultés par un assistant cloud sont transmis à son fournisseur."),
        "en": "Messages read by a cloud assistant are sent to its provider.",
    },
    "welcome.start": {"fr": "Commencer", "en": "Get started"},
    # -- prerequisites -------------------------------------------------------
    "prereq.title": {"fr": "Vérifier l'ordinateur", "en": "Check this computer"},
    "prereq.system": {"fr": "Système", "en": "Operating system"},
    "prereq.session": {"fr": "Session utilisateur", "en": "User session"},
    "prereq.keyring": {"fr": "Trousseau", "en": "Keyring"},
    "prereq.bridge": {"fr": "Bridge", "en": "Bridge"},
    "prereq.client": {"fr": "Assistant", "en": "Assistant"},
    "prereq.recheck": {"fr": "Revérifier", "en": "Check again"},
    # -- bridge screen -------------------------------------------------------
    "bridge.title": {"fr": "Connecter Bridge", "en": "Connect Bridge"},
    "bridge.guide": {
        "fr": (
            "Ouvrez Proton Mail Bridge, sélectionnez votre compte, puis affichez ses "
            "informations de connexion IMAP."
        ),
        "en": (
            "Open Proton Mail Bridge, select your account, then show its IMAP connection details."
        ),
    },
    "bridge.user": {"fr": "Adresse affichée dans Bridge", "en": "Address shown in Bridge"},
    "bridge.port": {"fr": "Port IMAP", "en": "IMAP port"},
    "bridge.password": {
        "fr": "Mot de passe généré par Bridge",
        "en": "Password generated by Bridge",
    },
    "bridge.password.help": {
        "fr": (
            "Utilisez le mot de passe IMAP affiché par Bridge, pas le mot de passe de "
            "votre compte Proton. Il sera conservé dans le trousseau de cet ordinateur."
        ),
        "en": (
            "Use the IMAP password shown by Bridge, not your Proton account password. It "
            "will be kept in this computer's keyring."
        ),
    },
    "bridge.aliases": {
        "fr": "Autres adresses d'envoi (facultatif, séparées par des virgules)",
        "en": "Other sending addresses (optional, comma separated)",
    },
    "bridge.reveal": {"fr": "Afficher", "en": "Show"},
    "bridge.existing": {
        "fr": "Identifiant Bridge déjà enregistré",
        "en": "Bridge credential already stored",
    },
    "bridge.test": {"fr": "Tester la connexion", "en": "Test the connection"},
    "bridge.change": {"fr": "Modifier l'identifiant Bridge", "en": "Change the Bridge credential"},
    "bridge.save": {"fr": "Tester et enregistrer", "en": "Test and save"},
    "bridge.host_fixed": {
        "fr": "Le serveur est toujours 127.0.0.1 sur cet ordinateur.",
        "en": "The server is always 127.0.0.1 on this computer.",
    },
    # -- client selection ----------------------------------------------------
    "client.title": {"fr": "Choisir l'assistant", "en": "Choose your assistant"},
    "client.shared": {
        "fr": "Connexion partagée entre : {surfaces}",
        "en": "Connection shared between: {surfaces}",
    },
    "client.shared_unknown": {
        "fr": (
            "Les autres surfaces de cet assistant n'ont pas été vérifiées sur ce "
            "système : activez-les séparément si vous les utilisez."
        ),
        "en": (
            "Other surfaces of this assistant have not been verified on this system; "
            "turn them on separately if you use them."
        ),
    },
    "client.locate": {
        "fr": "Choisir un assistant…",
        "en": "Locate an assistant…",
    },
    "uninstall.nothing_to_remove": {
        "fr": "Aucune connexion Proton Safe n'était enregistrée pour ce compte.",
        "en": "No Proton Safe connection was registered for this account.",
    },
    "uninstall.erase_done": {
        "fr": (
            "Les réglages et le mot de passe enregistrés par Proton Safe ont été "
            "effacés de cet ordinateur. Proton Mail Bridge, vos messages et vos "
            "brouillons ne sont pas touchés. Si un serveur était en cours "
            "d'exécution, redémarrez votre assistant pour qu'il s'arrête."
        ),
        "en": (
            "The settings and the password saved by Proton Safe have been erased from "
            "this computer. Proton Mail Bridge, your messages and your drafts are "
            "untouched. If a server was still running, restart your assistant so it "
            "stops."
        ),
    },
    "client.locate_failed": {
        "fr": "Ce fichier n'a pas répondu comme un assistant compatible.",
        "en": "That file did not answer like a compatible assistant.",
    },
    "client.details": {"fr": "Détails", "en": "Details"},
    # -- activation ----------------------------------------------------------
    "activate.title": {"fr": "Activer la connexion", "en": "Turn the connection on"},
    "activate.button": {"fr": "Activer dans {client}", "en": "Turn on in {client}"},
    "activate.uses": {
        "fr": (
            "Usages : recherche, lecture, texte de certaines pièces jointes, préparation "
            "de brouillons."
        ),
        "en": ("What it does: search, read, text of selected attachments, and draft preparation."),
    },
    "activate.limits": {
        "fr": "Aucun envoi, aucune suppression, aucun déplacement de message.",
        "en": "No sending, no deletion, no moving of messages.",
    },
    "activate.migrate.label": {
        "fr": "Reprendre la connexion Proton Safe existante",
        "en": "Take over the existing Proton Safe connection",
    },
    "activate.migrate": {
        "fr": "Reprendre la connexion Proton Safe existante : {entries}",
        "en": "Take over the existing Proton Safe connection: {entries}",
    },
    "activate.migrate.explain": {
        "fr": (
            "Votre compte et votre identifiant Bridge sont conservés. L'ancienne entrée "
            "est retirée de votre assistant, puis la nouvelle est installée. Vos autres "
            "plugins ne sont pas touchés."
        ),
        "en": (
            "Your account and Bridge credential are kept. The old entry is removed from "
            "your assistant, then the new one is installed. Your other plugins are left "
            "alone."
        ),
    },
    "activate.replaces": {
        "fr": "Remplace l'entrée Proton Safe existante : {entries}",
        "en": "Replaces the existing Proton Safe entry: {entries}",
    },
    # -- verification --------------------------------------------------------
    "verify.title": {"fr": "Vérifier et démarrer", "en": "Check and start"},
    "verify.bridge": {"fr": "Bridge connecté", "en": "Bridge connected"},
    "verify.runtime": {"fr": "Serveur prêt", "en": "Server ready"},
    "verify.client": {
        "fr": "Connexion active dans votre assistant",
        "en": "Connection active in your assistant",
    },
    "verify.client.pending": {
        "fr": "Configuration enregistrée — vérification dans {client} nécessaire",
        "en": "Configuration saved — please check in {client}",
    },
    "verify.confirm": {
        "fr": "J'ai vérifié dans mon assistant",
        "en": "I checked in my assistant",
    },
    "verify.prompt.check": {
        "fr": (
            "Vérifie que les outils Proton Safe sont disponibles, sans lire mes messages "
            "ni créer de brouillon."
        ),
        "en": (
            "Check that the Proton Safe tools are available, without reading my messages "
            "or creating a draft."
        ),
    },
    "verify.prompt.first_use": {
        "fr": (
            "Retrouve les échanges concernant [mon dossier] et résume les points encore ouverts."
        ),
        "en": "Find the conversations about [my topic] and summarise what is still open.",
    },
    "verify.copy": {"fr": "Copier", "en": "Copy"},
    "verify.first_use": {
        "fr": (
            "Ensuite, pour une première utilisation volontaire — ce n'est pas un test "
            "technique, l'assistant lira vos messages :"
        ),
        "en": (
            "Then, for a deliberate first use — this is not a technical test, your "
            "assistant will read your messages:"
        ),
    },
    # -- dashboard -----------------------------------------------------------
    "dashboard.title": {"fr": "Proton Safe", "en": "Proton Safe"},
    "dashboard.account": {"fr": "Compte", "en": "Account"},
    "dashboard.version": {"fr": "Version", "en": "Version"},
    "dashboard.last_check": {"fr": "Dernière vérification", "en": "Last check"},
    "dashboard.never": {"fr": "jamais", "en": "never"},
    "dashboard.check": {"fr": "Vérifier la connexion", "en": "Check the connection"},
    "dashboard.repair": {"fr": "Réparer la connexion", "en": "Repair the connection"},
    "dashboard.edit": {"fr": "Modifier les informations Bridge", "en": "Change Bridge details"},
    "dashboard.copy_diagnostic": {"fr": "Copier un diagnostic", "en": "Copy a diagnostic"},
    "dashboard.disconnect": {"fr": "Déconnecter Proton Safe", "en": "Disconnect Proton Safe"},
    "dashboard.erase": {
        "fr": "Effacer aussi la configuration et l'identifiant enregistrés par Proton Safe",
        "en": "Also erase the configuration and credential saved by Proton Safe",
    },
    "dashboard.disconnect.consequences": {
        "fr": (
            "Proton Safe sera retiré de votre assistant. Vos messages, brouillons et "
            "pièces jointes ne sont pas touchés, et Bridge reste installé."
        ),
        "en": (
            "Proton Safe will be removed from your assistant. Your messages, drafts and "
            "attachments are untouched, and Bridge stays installed."
        ),
    },
    # -- common --------------------------------------------------------------
    "common.back": {"fr": "Retour", "en": "Back"},
    "common.continue": {"fr": "Continuer", "en": "Continue"},
    "common.cancel": {"fr": "Annuler", "en": "Cancel"},
    "common.close": {"fr": "Fermer", "en": "Close"},
    "common.details": {"fr": "Détails techniques", "en": "Technical details"},
    "common.working": {"fr": "Opération en cours…", "en": "Working…"},
    "common.cancelled": {"fr": "Opération annulée.", "en": "Operation cancelled."},
    "status.pass": {"fr": "OK", "en": "OK"},
    "status.warn": {"fr": "À noter", "en": "Note"},
    "status.fail": {"fr": "Bloquant", "en": "Blocking"},
    "status.action_required": {"fr": "Action requise", "en": "Action required"},
    "status.skip": {"fr": "Non vérifié", "en": "Not checked"},
}

#: code -> language -> (message, action). The action is what the user can do next.
CODE_MESSAGES: Final[dict[str, dict[str, tuple[str, str]]]] = {
    # Successful states need text too: a check line must read correctly when it passes.
    Code.SYSTEM_SUPPORTED: {
        "fr": (
            "Système compatible.",
            "Cette version a été validée sur Ubuntu 24.04 LTS x86_64.",
        ),
        "en": ("Supported system.", "This version was validated on Ubuntu 24.04 LTS x86_64."),
    },
    Code.SESSION_OK: {
        "fr": ("Session graphique utilisateur.", ""),
        "en": ("Graphical user session.", ""),
    },
    Code.KEYRING_AVAILABLE: {
        "fr": ("Le trousseau de votre session est disponible.", ""),
        "en": ("Your session keyring is available.", ""),
    },
    Code.BRIDGE_APP_DETECTED: {
        "fr": ("Proton Mail Bridge est installé sur cet ordinateur.", ""),
        "en": ("Proton Mail Bridge is installed on this computer.", ""),
    },
    Code.CLIENT_DETECTED: {
        "fr": ("Un assistant compatible a été trouvé.", ""),
        "en": ("A compatible assistant was found.", ""),
    },
    Code.BRIDGE_AUTHENTICATED: {
        "fr": ("Bridge accepte cette connexion.", ""),
        "en": ("Bridge accepts this connection.", ""),
    },
    Code.RUNTIME_READY: {
        "fr": ("Le composant de connexion démarre et expose les outils attendus.", ""),
        "en": ("The connection component starts and exposes the expected tools.", ""),
    },
    Code.CONFIG_SAVED: {
        "fr": ("Configuration et identifiant enregistrés sur cet ordinateur.", ""),
        "en": ("Configuration and credential saved on this computer.", ""),
    },
    Code.CONFIG_LOADED: {
        "fr": ("Configuration Proton Safe lue.", ""),
        "en": ("Proton Safe configuration loaded.", ""),
    },
    Code.CLIENT_REGISTERED: {
        "fr": (
            "Proton Safe est enregistré dans votre assistant.",
            "Il reste à vérifier qu'il est bien chargé dans une nouvelle conversation.",
        ),
        "en": (
            "Proton Safe is registered in your assistant.",
            "It still needs checking in a new conversation.",
        ),
    },
    Code.CLIENT_VERIFIED_MANUALLY: {
        "fr": ("Vous avez confirmé voir les outils dans votre assistant.", ""),
        "en": ("You confirmed seeing the tools in your assistant.", ""),
    },
    Code.MIGRATION_REQUIRED: {
        "fr": (
            "Une connexion Proton Safe installée autrement existe déjà.",
            "Cochez la reprise pour la remplacer, ou retirez-la vous-même dans votre assistant.",
        ),
        "en": (
            "A Proton Safe connection installed another way already exists.",
            "Tick the take-over option to replace it, or remove it yourself in your assistant.",
        ),
    },
    Code.MIGRATION_DONE: {
        "fr": (
            "L'ancienne connexion a été remplacée par la nouvelle.",
            "Il reste à vérifier qu'elle est chargée dans une nouvelle conversation.",
        ),
        "en": (
            "The previous connection was replaced by the new one.",
            "It still needs checking in a new conversation.",
        ),
    },
    Code.MIGRATION_MANUAL: {
        "fr": (
            "L'ancienne connexion doit être retirée dans votre assistant.",
            "Retirez-la depuis ses réglages de plugins, puis relancez l'activation ici. "
            "Rien n'a été modifié.",
        ),
        "en": (
            "The previous connection has to be removed in your assistant.",
            "Remove it from its plugin settings, then run the activation again here. "
            "Nothing was changed.",
        ),
    },
    Code.LOCAL_DATA_KEPT: {
        "fr": (
            "La configuration et l'identifiant ont été conservés.",
            "Ils seront effacés une fois les entrées retirées de votre assistant.",
        ),
        "en": (
            "The configuration and credential were kept.",
            "They will be erased once the entries are removed from your assistant.",
        ),
    },
    Code.CLIENT_REMOVED: {
        "fr": (
            "Les entrées créées par Proton Safe ont été retirées.",
            "Un serveur déjà démarré continue jusqu'au redémarrage de l'assistant.",
        ),
        "en": (
            "The entries created by Proton Safe were removed.",
            "A server already started keeps running until the assistant restarts.",
        ),
    },
    Code.CANCELLED: {
        "fr": ("Opération annulée avant toute modification.", ""),
        "en": ("Cancelled before anything was changed.", ""),
    },
    Code.BRIDGE_UNREACHABLE: {
        "fr": (
            "Bridge ne répond pas sur cet ordinateur.",
            "Ouvrez Proton Mail Bridge, vérifiez le port, puis réessayez.",
        ),
        "en": (
            "Bridge is not answering on this computer.",
            "Open Proton Mail Bridge, check the port, then try again.",
        ),
    },
    Code.BRIDGE_AUTH_FAILED: {
        "fr": (
            "Les informations de connexion ne sont pas acceptées.",
            "Vérifiez l'adresse et le mot de passe généré par Bridge.",
        ),
        "en": (
            "The connection details were not accepted.",
            "Check the address and the password generated by Bridge.",
        ),
    },
    Code.BRIDGE_TLS_FAILED: {
        "fr": (
            "La connexion locale à Bridge n'a pas pu être sécurisée.",
            "Vérifiez Bridge et le port ; ne désactivez pas STARTTLS.",
        ),
        "en": (
            "The local connection to Bridge could not be secured.",
            "Check Bridge and the port; do not disable STARTTLS.",
        ),
    },
    Code.BRIDGE_CONNECTION_FAILED: {
        "fr": (
            "La connexion à Bridge a échoué pour une raison indéterminée.",
            "Vérifiez que Bridge est ouvert et connecté, puis réessayez.",
        ),
        "en": (
            "The connection to Bridge failed for an undetermined reason.",
            "Check that Bridge is open and connected, then try again.",
        ),
    },
    Code.KEYRING_LOCKED: {
        "fr": (
            "Le trousseau de votre session est verrouillé.",
            "Déverrouillez-le avec le dialogue système, puis réessayez.",
        ),
        "en": (
            "Your session keyring is locked.",
            "Unlock it with the system dialog, then try again.",
        ),
    },
    Code.KEYRING_UNAVAILABLE: {
        "fr": (
            "Le trousseau nécessaire n'est pas disponible.",
            "Sur Ubuntu, ouvrez une session graphique normale et installez "
            "gnome-keyring ; Proton Safe ne stockera le mot de passe nulle part ailleurs.",
        ),
        "en": (
            "The required keyring is not available.",
            "On Ubuntu, open a normal graphical session and install gnome-keyring; "
            "Proton Safe will not store the password anywhere else.",
        ),
    },
    Code.UNSUPPORTED_CLIENT: {
        "fr": (
            "Cette version de votre assistant ne permet pas cette installation.",
            "Mettez-la à jour par son canal officiel, puis relancez la vérification.",
        ),
        "en": (
            "This version of your assistant does not support this installation.",
            "Update it through its official channel, then check again.",
        ),
    },
    Code.CLIENT_RESTART_REQUIRED: {
        "fr": (
            "Redémarrez votre assistant pour charger Proton Safe.",
            "Terminez votre travail en cours, fermez puis rouvrez l'application, et "
            "revérifiez ici.",
        ),
        "en": (
            "Restart your assistant to load Proton Safe.",
            "Finish what you are doing, close and reopen the application, then check again.",
        ),
    },
    Code.CLIENT_ACTION_REQUIRED: {
        "fr": (
            "Terminez l'activation dans votre assistant.",
            "Ouvrez ses réglages de plugins et activez Proton Safe.",
        ),
        "en": (
            "Finish turning it on in your assistant.",
            "Open its plugin settings and enable Proton Safe.",
        ),
    },
    Code.CONFIG_CONFLICT: {
        "fr": (
            "Une connexion Proton Safe existe déjà et diffère de celle proposée.",
            "Examinez l'entrée existante et choisissez une migration ciblée.",
        ),
        "en": (
            "A Proton Safe connection already exists and differs from the proposed one.",
            "Review the existing entry and choose a targeted migration.",
        ),
    },
    Code.CONFIG_INVALID: {
        "fr": (
            "La configuration enregistrée ne peut pas être utilisée.",
            "Réparez-la depuis cet assistant ; elle ne sera pas écrasée automatiquement.",
        ),
        "en": (
            "The saved configuration cannot be used.",
            "Repair it from this assistant; it will not be overwritten automatically.",
        ),
    },
    Code.CONFIG_SCHEMA_UNSUPPORTED: {
        "fr": (
            "Cette configuration a été écrite par une version plus récente.",
            "Mettez Proton Safe à jour ; le fichier ne sera pas réécrit.",
        ),
        "en": (
            "This configuration was written by a newer version.",
            "Update Proton Safe; the file will not be rewritten.",
        ),
    },
    Code.CONFIG_PERMISSIONS: {
        "fr": (
            "La configuration n'est pas protégée correctement.",
            "Appliquez la correction proposée sur les fichiers de Proton Safe.",
        ),
        "en": (
            "The configuration is not protected correctly.",
            "Apply the suggested fix to Proton Safe's own files.",
        ),
    },
    Code.CONFIG_MISSING: {
        "fr": (
            "Aucune configuration Proton Safe n'a été trouvée.",
            "Lancez la configuration depuis l'écran d'accueil.",
        ),
        "en": (
            "No Proton Safe configuration was found.",
            "Start the setup from the welcome screen.",
        ),
    },
    Code.CREDENTIAL_MISSING: {
        "fr": (
            "Aucun identifiant Bridge n'est enregistré pour ce compte.",
            "Saisissez le mot de passe généré par Bridge.",
        ),
        "en": (
            "No Bridge credential is stored for this account.",
            "Enter the password generated by Bridge.",
        ),
    },
    Code.RUNTIME_START_FAILED: {
        "fr": (
            "Le composant de connexion n'a pas démarré.",
            "Retestez ; si le problème persiste, copiez le diagnostic expurgé.",
        ),
        "en": (
            "The connection component did not start.",
            "Test again; if it persists, copy the redacted diagnostic.",
        ),
    },
    Code.RUNTIME_TOOLS_UNEXPECTED: {
        "fr": (
            "Le composant installé n'expose pas les outils attendus.",
            "Réinstallez le paquet Proton Safe depuis sa source officielle.",
        ),
        "en": (
            "The installed component does not expose the expected tools.",
            "Reinstall the Proton Safe package from its official source.",
        ),
    },
    Code.RUNTIME_NOT_FOUND: {
        "fr": (
            "Le composant de connexion est introuvable à côté de cet assistant.",
            "Réinstallez le paquet Proton Safe.",
        ),
        "en": (
            "The connection component was not found next to this assistant.",
            "Reinstall the Proton Safe package.",
        ),
    },
    Code.INSTALLATION_INCOMPLETE: {
        "fr": (
            "L'installation précédente s'est interrompue.",
            "Reprenez : l'assistant vérifiera l'état réel avant toute modification.",
        ),
        "en": (
            "The previous installation was interrupted.",
            "Resume: the assistant will check the real state before changing anything.",
        ),
    },
    Code.CLIENT_NOT_FOUND: {
        "fr": (
            "Aucun assistant compatible n'a été trouvé sur cet ordinateur.",
            "Installez ChatGPT desktop ou Codex par leur canal officiel.",
        ),
        "en": (
            "No compatible assistant was found on this computer.",
            "Install ChatGPT desktop or Codex through their official channel.",
        ),
    },
    Code.CLIENT_COMMAND_FAILED: {
        "fr": (
            "Votre assistant a refusé l'installation du plugin.",
            "Vérifiez sa version, puis réessayez ou installez le plugin depuis son "
            "répertoire local.",
        ),
        "en": (
            "Your assistant refused to install the plugin.",
            "Check its version, then retry or install the plugin from its local directory.",
        ),
    },
    Code.CLIENT_COMMAND_TIMEOUT: {
        "fr": (
            "Votre assistant n'a pas répondu dans le délai prévu.",
            "Réessayez ; aucune nouvelle tentative automatique n'est lancée.",
        ),
        "en": (
            "Your assistant did not answer in time.",
            "Try again; no automatic retry is started.",
        ),
    },
    Code.PLUGIN_ASSETS_INVALID: {
        "fr": (
            "Les ressources du plugin fournies avec ce paquet sont inutilisables.",
            "Réinstallez le paquet Proton Safe.",
        ),
        "en": (
            "The plugin resources shipped with this package are unusable.",
            "Reinstall the Proton Safe package.",
        ),
    },
    Code.SYSTEM_UNSUPPORTED: {
        "fr": (
            "Ce système n'est pas pris en charge par cette version.",
            "Cette version cible Ubuntu 24.04 LTS sur x86_64.",
        ),
        "en": (
            "This system is not supported by this version.",
            "This version targets Ubuntu 24.04 LTS on x86_64.",
        ),
    },
    Code.SESSION_ROOT: {
        "fr": (
            "Cet assistant ne doit pas être lancé en administrateur.",
            "Relancez-le depuis votre session habituelle.",
        ),
        "en": (
            "This assistant must not be run as an administrator.",
            "Start it again from your usual session.",
        ),
    },
    Code.SESSION_NO_GRAPHICAL: {
        "fr": (
            "Aucune session graphique n'a été détectée.",
            "Ouvrez une session Ubuntu normale, puis relancez l'assistant.",
        ),
        "en": (
            "No graphical session was detected.",
            "Open a normal Ubuntu session, then start the assistant again.",
        ),
    },
    Code.SESSION_ELEVATED: {
        "fr": (
            "Proton Safe ne doit pas être lancé en tant qu'administrateur.",
            "Fermez cette fenêtre et rouvrez Proton Safe depuis votre compte Windows "
            "habituel : la connexion est installée pour ce compte.",
        ),
        "en": (
            "Proton Safe must not be run as an administrator.",
            "Close this window and open Proton Safe from your usual Windows account: "
            "the connection is set up for that account.",
        ),
    },
    Code.BRIDGE_APP_UNKNOWN: {
        "fr": (
            "Proton Mail Bridge n'a pas été détecté aux emplacements connus.",
            "Installez-le depuis proton.me, ou continuez si vous savez qu'il est installé.",
        ),
        "en": (
            "Proton Mail Bridge was not found in the known locations.",
            "Install it from proton.me, or continue if you know it is installed.",
        ),
    },
}

#: Windows wording for the few texts that name something Linux-specific. Everything
#: else is shared: only the sentences that would send a Windows user to the wrong place
#: are overridden, so a translation added to the main catalogue is never forgotten here.
WINDOWS_CATALOGUE: Final[dict[str, dict[str, str]]] = {
    "prereq.keyring": {"fr": "Gestionnaire d'identifiants", "en": "Credential Manager"},
    "prereq.session": {"fr": "Compte Windows", "en": "Windows account"},
    "prereq.system": {"fr": "Windows", "en": "Windows"},
}

WINDOWS_CODE_MESSAGES: Final[dict[str, dict[str, tuple[str, str]]]] = {
    Code.SYSTEM_UNSUPPORTED: {
        "fr": (
            "Ce système n'est pas pris en charge par cette version.",
            "Cette version cible Windows 11 en 64 bits (x64). Windows 10, les "
            "processeurs ARM et les versions 32 bits ne sont pas pris en charge.",
        ),
        "en": (
            "This system is not supported by this version.",
            "This version targets Windows 11 on 64-bit (x64). Windows 10, ARM "
            "processors and 32-bit versions are not supported.",
        ),
    },
    Code.SESSION_NO_GRAPHICAL: {
        "fr": (
            "Aucune session Windows interactive n'a été détectée.",
            "Ouvrez votre session Windows habituelle, puis relancez Proton Safe.",
        ),
        "en": (
            "No interactive Windows session was detected.",
            "Sign in to your usual Windows account, then start Proton Safe again.",
        ),
    },
    Code.KEYRING_LOCKED: {
        "fr": (
            "Le Gestionnaire d'identifiants Windows n'a pas pu être ouvert.",
            "Reconnectez-vous à votre session Windows, puis réessayez.",
        ),
        "en": (
            "Windows Credential Manager could not be opened.",
            "Sign in to your Windows session again, then try once more.",
        ),
    },
    Code.KEYRING_UNAVAILABLE: {
        "fr": (
            "Le Gestionnaire d'identifiants Windows n'est pas utilisable.",
            "Ouvrez votre session Windows habituelle, sans élévation. Proton Safe "
            "n'enregistrera le mot de passe nulle part ailleurs.",
        ),
        "en": (
            "Windows Credential Manager cannot be used.",
            "Open your usual Windows session, without elevation. Proton Safe will not "
            "store the password anywhere else.",
        ),
    },
    Code.PLUGIN_ASSETS_INVALID: {
        "fr": (
            "Les ressources du plugin fournies avec cette installation sont inutilisables.",
            "Relancez l'installateur Proton Safe et choisissez « Réparer les fichiers ».",
        ),
        "en": (
            "The plugin resources shipped with this installation are unusable.",
            "Run the Proton Safe installer again and choose \u201cRepair files\u201d.",
        ),
    },
}


def _windows() -> bool:
    return services().name == "windows"


#: Fixed, official destinations. The assistant opens nothing else in a browser.
OFFICIAL_LINKS: Final[dict[str, str]] = {
    "bridge": "https://proton.me/mail/bridge",
    "bridge_systems": "https://proton.me/support/operating-systems-supported-bridge",
    "client_mcp": "https://learn.chatgpt.com/docs/extend/mcp",
    "documentation": "https://fbossiere.github.io/proton-safe-mcp/",
}


def translate(key: str, language: str | None = None, **values: str) -> str:
    """Return the text for ``key``, falling back to the key itself when unknown."""
    resolved = language or detect_language()
    entry = (WINDOWS_CATALOGUE.get(key) if _windows() else None) or CATALOGUE.get(key)
    if entry is None:
        return key
    text = entry.get(resolved) or entry.get(DEFAULT_LANGUAGE, key)
    return text.format(**values) if values else text


def explain(code: str, language: str | None = None) -> tuple[str, str]:
    """Return ``(message, action)`` for a stable code.

    An unmapped code still produces something honest rather than a raw internal string.
    """
    resolved = language or detect_language()
    entry = (WINDOWS_CODE_MESSAGES.get(str(code)) if _windows() else None) or CODE_MESSAGES.get(
        str(code)
    )
    if entry is None:
        generic = {
            "fr": ("Une étape n'a pas abouti.", "Relancez la vérification."),
            "en": ("A step did not complete.", "Run the check again."),
        }
        return generic.get(resolved, generic["fr"])
    return entry.get(resolved) or entry[DEFAULT_LANGUAGE]


def missing_translations() -> list[str]:
    """Keys whose translation is incomplete, so the gap is visible rather than silent.

    The Windows overlays are checked too: a sentence that exists in one language only
    would otherwise fall back silently to French on half the product.
    """
    gaps: list[str] = []
    for name, table in (("", CATALOGUE), ("windows:", WINDOWS_CATALOGUE)):
        for key, entry in table.items():
            gaps.extend(f"{name}{key}:{tag}" for tag in SUPPORTED_LANGUAGES if not entry.get(tag))
    for name, codes in (("", CODE_MESSAGES), ("windows:", WINDOWS_CODE_MESSAGES)):
        for code, entry_codes in codes.items():
            gaps.extend(
                f"{name}{code}:{tag}" for tag in SUPPORTED_LANGUAGES if not entry_codes.get(tag)
            )
    return sorted(gaps)

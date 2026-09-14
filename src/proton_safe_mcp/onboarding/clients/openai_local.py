"""ChatGPT desktop / Codex on this computer, sharing one local Codex host.

Capabilities are established by asking the installed client itself — each subcommand this
adapter intends to run is probed with ``--help`` — never inferred from a version number.
An installation that does not expose them is reported as unsupported instead of being
driven blind.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tomllib
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path, PurePath
from typing import Any, Final

from ...platform_services import services
from ..models import (
    ClientInstallation,
    Code,
    PlanStep,
    RegistrationOutcome,
    RegistrationPlan,
)
from ..plugin_assets import (
    MANAGED_PLUGIN,
    MANAGED_SERVER_NAME,
    ManagedPluginAssets,
)
from .base import (
    COMMAND_TIMEOUT_SECONDS,
    MUTATION_TIMEOUT_SECONDS,
    CommandRunner,
    executable_candidates,
    run_command,
)

ADAPTER_ID: Final = "openai-local"

#: Documented locations only. `/usr/lib/chatgpt/resources/codex` ships with a particular
#: Ubuntu ChatGPT desktop package; it is a packaging detail, so it is probed like any other
#: candidate and used only when it answers the subcommands this adapter needs.
LINUX_CANDIDATE_PATHS: Final = (
    "/usr/lib/chatgpt/resources/codex",
    "/snap/bin/codex",
    "/usr/bin/codex",
    "/usr/local/bin/codex",
)

#: Backwards-compatible name for the Linux list.
CANDIDATE_PATHS: Final = LINUX_CANDIDATE_PATHS

#: Per-user installation folders on Windows, relative to a known folder. These are
#: bounded probes, never a recursive search: each one is still corroborated by running
#: `--version` and every plugin subcommand this adapter would use, so a path that turns
#: out not to exist on a real installation simply finds nothing. The location a real
#: Windows client actually uses is recorded when that client is qualified; until then
#: the reliable routes are the user's `PATH` and choosing the executable explicitly.
WINDOWS_CANDIDATE_TEMPLATES: Final = (
    ("LOCALAPPDATA", "Programs/codex/codex.exe"),
    ("LOCALAPPDATA", "Programs/@openai/codex/codex.exe"),
    ("LOCALAPPDATA", "Programs/ChatGPT/resources/codex/codex.exe"),
    ("PROGRAMFILES", "ChatGPT/resources/codex/codex.exe"),
)


def default_candidate_paths() -> tuple[str, ...]:
    """The documented locations to probe on this platform."""
    if services().name != "windows":
        return LINUX_CANDIDATE_PATHS
    found: list[str] = []
    for variable, relative in WINDOWS_CANDIDATE_TEMPLATES:
        base = os.environ.get(variable, "")
        if base:
            found.append(str(Path(base).joinpath(*relative.split("/"))))
    return tuple(found)


CAP_PLUGIN: Final = "plugin"
CAP_MARKETPLACE_ADD: Final = "plugin.marketplace.add"
CAP_MARKETPLACE_REMOVE: Final = "plugin.marketplace.remove"
CAP_PLUGIN_ADD: Final = "plugin.add"
CAP_PLUGIN_REMOVE: Final = "plugin.remove"
CAP_PLUGIN_LIST: Final = "plugin.list"

#: Everything needed to install without asking the user to type commands.
REQUIRED_FOR_AUTOMATIC_INSTALL: Final = frozenset(
    {CAP_PLUGIN, CAP_MARKETPLACE_ADD, CAP_PLUGIN_ADD, CAP_PLUGIN_LIST}
)

RESOURCE_MARKETPLACE: Final = "marketplace"
RESOURCE_PLUGIN: Final = "plugin"

#: On Ubuntu these surfaces share one Codex host, so one registration covers them;
#: registering twice would create two servers for the same managed setup. That is a
#: verified fact about the tested Linux packaging, not a general one.
SHARED_SURFACES: Final = ("ChatGPT desktop", "Codex CLI", "Codex IDE extension")


def shared_surfaces() -> tuple[str, ...]:
    """Which surfaces one registration is known to cover on this platform.

    Empty on Windows on purpose. Whether ChatGPT desktop and Codex there really share
    one host and one profile has not been verified, and claiming a shared connection
    that does not exist would leave a user believing a surface is connected when it is
    not. The interface says nothing rather than something unverified.
    """
    return () if services().name == "windows" else SHARED_SURFACES


def codex_home() -> Path:
    """The client's profile directory, honouring an absolute ``CODEX_HOME``.

    The variable is read and never written: the assistant and the client must agree on
    one profile, and overwriting it would move the client's own configuration.
    """
    configured = os.environ.get("CODEX_HOME", "")
    if services().is_absolute_path(configured):
        return Path(configured)
    return Path.home() / ".codex"


def _version_of(stdout: str) -> str:
    """Take the first short line of a --version reply, bounded and single line."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:80]
    return "unknown"


class OpenAILocalAdapter:
    """Adapter for a local Codex host shared by ChatGPT desktop and Codex."""

    id = ADAPTER_ID
    display_name = "ChatGPT desktop / Codex"

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        candidate_paths: Sequence[str] | None = None,
        config_home: Path | None = None,
    ) -> None:
        self._run: CommandRunner = runner or run_command
        self._candidate_paths = (
            tuple(candidate_paths) if candidate_paths is not None else default_candidate_paths()
        )
        self._config_home = config_home

    # -- discovery ---------------------------------------------------------------

    def _candidates(self) -> list[Path]:
        paths = [Path(item) for item in self._candidate_paths]
        found = shutil.which("codex")
        if found:
            paths.insert(0, Path(found))
        # `executable_candidates` drops anything this platform will not launch directly.
        # On Windows that removes the `.cmd` and `.bat` shims a package manager creates:
        # driving one would mean building a command line out of user-controlled paths.
        return executable_candidates(paths)

    def profile_path(self) -> Path:
        return self.profile_dir().resolve()

    def _installation_id(self, executable: Path) -> str:
        identity = f"{executable.resolve()}\0{self.profile_path()}"
        return f"{ADAPTER_ID}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"

    def inspect(self, executable: Path) -> ClientInstallation | None:
        """Describe one installation the user pointed at explicitly.

        This is the supported way to reach a client installed somewhere this adapter
        does not probe. The file is not trusted for being where the user said it is: it
        still has to answer `--version` and the plugin subcommands like any other.
        """
        found = executable_candidates([executable])
        if not found:
            return None
        resolved = found[0]
        version = self._run([str(resolved), "--version"])
        if not version.ok:
            return None
        plugin = self._run([str(resolved), "plugin", "--help"])
        return ClientInstallation(
            id=self._installation_id(resolved),
            adapter=ADAPTER_ID,
            display_name=self.display_name,
            executable=resolved,
            version=_version_of(version.stdout),
            capabilities=frozenset({CAP_PLUGIN} if plugin.ok else set()),
            shared_surfaces=shared_surfaces(),
        )

    def discover(self) -> list[ClientInstallation]:
        """Find installations and confirm each one answers `--version` and `plugin`.

        Two candidate paths resolving to the same executable are reported once. Discovery
        stays cheap: the full capability probe runs only for the installation the user
        selects.
        """
        installations: list[ClientInstallation] = []
        for executable in self._candidates():
            version = self._run([str(executable), "--version"])
            if not version.ok:
                continue
            plugin = self._run([str(executable), "plugin", "--help"])
            capabilities = {CAP_PLUGIN} if plugin.ok else set()
            installations.append(
                ClientInstallation(
                    id=self._installation_id(executable),
                    adapter=ADAPTER_ID,
                    display_name=self.display_name,
                    executable=executable,
                    version=_version_of(version.stdout),
                    capabilities=frozenset(capabilities),
                    shared_surfaces=shared_surfaces(),
                )
            )
        return installations

    def describe_capabilities(self, installation: ClientInstallation) -> ClientInstallation:
        """Ask this installation about each subcommand the adapter would actually run."""
        probes = {
            CAP_PLUGIN: ["plugin", "--help"],
            CAP_MARKETPLACE_ADD: ["plugin", "marketplace", "add", "--help"],
            CAP_MARKETPLACE_REMOVE: ["plugin", "marketplace", "remove", "--help"],
            CAP_PLUGIN_ADD: ["plugin", "add", "--help"],
            CAP_PLUGIN_REMOVE: ["plugin", "remove", "--help"],
            CAP_PLUGIN_LIST: ["plugin", "list", "--help"],
        }
        capabilities = set()
        for capability, arguments in probes.items():
            result = self._run(
                [str(installation.executable), *arguments], timeout=COMMAND_TIMEOUT_SECONDS
            )
            if result.ok:
                capabilities.add(capability)
        return replace(installation, capabilities=frozenset(capabilities))

    def supports_automatic_install(self, installation: ClientInstallation) -> bool:
        return installation.capabilities >= REQUIRED_FOR_AUTOMATIC_INSTALL

    # -- existing entries --------------------------------------------------------

    def profile_dir(self) -> Path:
        """The client profile this adapter reads and writes.

        Recorded when an installation is registered, so a later disconnect can tell that
        it is removing entries from the profile they were added to rather than from
        whichever one ``CODEX_HOME`` happens to point at now.
        """
        return self._config_home or codex_home()

    def _config_path(self) -> Path:
        return self.profile_dir() / "config.toml"

    def existing_servers(self) -> dict[str, dict[str, Any]]:
        """Read only the MCP server table of the client's configuration.

        Nothing else in the file is parsed out, kept or reported, and the file is never
        rewritten by this adapter.
        """
        try:
            document = tomllib.loads(self._config_path().read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError, ValueError):
            return {}
        servers = document.get("mcp_servers")
        if not isinstance(servers, dict):
            return {}
        return {str(name): entry for name, entry in servers.items() if isinstance(entry, dict)}

    @staticmethod
    def looks_like_proton_safe(entry: dict[str, Any]) -> bool:
        """Identify a Proton Safe server by what it launches, not by its name.

        A name containing "proton" proves nothing; the command actually starting this
        project's runtime does.
        """
        parts = [str(entry.get("command", ""))]
        arguments = entry.get("args")
        if isinstance(arguments, list):
            parts.extend(str(item) for item in arguments)
        joined = " ".join(parts).lower()
        return "proton-safe-mcp" in joined or "proton_safe_mcp" in joined

    @staticmethod
    def is_managed_command(entry: dict[str, Any]) -> bool:
        """Whether this entry is one the assistant itself would write.

        A managed entry launches an absolute runtime with ``--config``; the historic
        plugin launches `uvx` and passes environment variables instead. The comparison
        is made on the executable's stem so the same entry is recognised whether it was
        written on Linux or on Windows, where it carries a ``.exe`` suffix.
        """
        arguments = entry.get("args")
        args = [str(item) for item in arguments] if isinstance(arguments, list) else []
        command = str(entry.get("command", ""))
        if not command or "--config" not in args:
            return False
        return PurePath(command.replace("\\", "/")).stem == "proton-safe-mcp"

    def installed_plugins(self, installation: ClientInstallation) -> list[str] | None:
        """Return the plugin references the client reports, or None when it cannot say.

        None and an empty list must stay distinct: "this client cannot tell us" is not
        the same fact as "this client reports no plugin", and only the second one means
        a registration disappeared.
        """
        if CAP_PLUGIN_LIST not in installation.capabilities:
            return None
        result = self._run([str(installation.executable), "plugin", "list"])
        if not result.ok:
            return None
        found: list[str] = []
        for line in result.stdout.splitlines():
            for token in line.split():
                if "@" in token and token.split("@")[0].strip():
                    found.append(token.strip().strip(",;"))
        return found

    # -- plan and apply ----------------------------------------------------------

    def plan(
        self, installation: ClientInstallation, assets: ManagedPluginAssets
    ) -> RegistrationPlan:
        """Describe the marketplace and plugin writes, and what they replace."""
        steps = [
            PlanStep("add", "plan.marketplace", assets.marketplace_name),
            PlanStep("add", "plan.plugin", assets.plugin_reference),
        ]
        replaces: list[str] = []
        conflicts: list[str] = []
        for name, entry in self.existing_servers().items():
            if not self.looks_like_proton_safe(entry):
                continue
            if name == MANAGED_SERVER_NAME and self.is_managed_command(entry):
                replaces.append(name)
            else:
                # Something else registered a Proton Safe server. It is shown for a
                # targeted decision rather than silently overwritten.
                conflicts.append(name)
        installed = self.installed_plugins(installation) or []
        migrations: list[PlanStep] = []
        for reference in installed:
            plugin, _, marketplace = reference.partition("@")
            if plugin != MANAGED_PLUGIN:
                continue
            if marketplace == assets.marketplace_name:
                replaces.append(reference)
            else:
                # This project's own plugin from another marketplace, typically the
                # published `proton-safe@personal`. The assistant can take it over, but
                # only when the user asks: it is still a change to something they set up.
                migrations.append(PlanStep("remove", RESOURCE_PLUGIN, reference))
        return RegistrationPlan(
            installation=installation,
            steps=tuple(steps),
            replaces=tuple(dict.fromkeys(replaces)),
            conflicts=tuple(dict.fromkeys(conflicts)),
            migrations=tuple(migrations),
        )

    def apply(
        self,
        plan: RegistrationPlan,
        assets: ManagedPluginAssets,
        *,
        migrate: bool = False,
    ) -> RegistrationOutcome:
        """Register the local marketplace then the plugin, reporting what was created.

        The client may start a server as soon as a plugin is installed, so this is only
        ever called after the configuration and the credential are already saved.

        ``migrate`` authorises taking over an earlier Proton Safe plugin installed from
        another marketplace. Without it, such a plan stops and asks: an installation the
        user made themselves is never replaced silently.
        """
        installation = plan.installation
        if not self.supports_automatic_install(installation):
            return RegistrationOutcome(
                ok=False,
                code=Code.UNSUPPORTED_CLIENT,
                manual_step_required=True,
                details={"marketplace_dir": str(assets.marketplace_dir)},
            )
        if plan.has_conflicts:
            return RegistrationOutcome(
                ok=False, code=Code.CONFIG_CONFLICT, details={"entries": list(plan.conflicts)}
            )
        if plan.requires_migration and not migrate:
            return RegistrationOutcome(
                ok=False,
                code=Code.MIGRATION_REQUIRED,
                details={"entries": [step.detail for step in plan.migrations]},
            )

        migrated: list[PlanStep] = []
        if plan.requires_migration:
            if CAP_PLUGIN_REMOVE not in installation.capabilities:
                # Nothing has been written yet, so the honest answer is to name the entry
                # the user must remove in their client rather than leave two servers.
                return RegistrationOutcome(
                    ok=False,
                    code=Code.MIGRATION_MANUAL,
                    manual_step_required=True,
                    details={"entries": [step.detail for step in plan.migrations]},
                )
            for step in plan.migrations:
                result = self._run(
                    [str(installation.executable), "plugin", "remove", step.detail],
                    timeout=MUTATION_TIMEOUT_SECONDS,
                )
                if not result.ok:
                    return RegistrationOutcome(
                        ok=False,
                        code=Code.MIGRATION_MANUAL,
                        migrated=tuple(migrated),
                        manual_step_required=True,
                        details={"entries": [step.detail]},
                    )
                migrated.append(step)
            # Only the plugin entry is taken over. Its marketplace is left registered,
            # because other plugins the user installed may come from it.

        created: list[PlanStep] = []
        marketplace = self._run(
            [
                str(installation.executable),
                "plugin",
                "marketplace",
                "add",
                str(assets.marketplace_dir),
            ],
            timeout=MUTATION_TIMEOUT_SECONDS,
        )
        if not marketplace.ok:
            return RegistrationOutcome(
                ok=False,
                code=Code.CLIENT_COMMAND_TIMEOUT
                if marketplace.timed_out
                else Code.CLIENT_COMMAND_FAILED,
                created=(),
                migrated=tuple(migrated),
                details={"step": "marketplace"},
            )
        created.append(PlanStep("add", RESOURCE_MARKETPLACE, assets.marketplace_name))

        plugin = self._run(
            [str(installation.executable), "plugin", "add", assets.plugin_reference],
            timeout=MUTATION_TIMEOUT_SECONDS,
        )
        if not plugin.ok:
            # The marketplace exists and is recorded, so a retry or a removal can find it.
            return RegistrationOutcome(
                ok=False,
                code=(
                    Code.CLIENT_COMMAND_TIMEOUT if plugin.timed_out else Code.CLIENT_COMMAND_FAILED
                ),
                created=tuple(created),
                details={"step": "plugin"},
            )
        created.append(PlanStep("add", RESOURCE_PLUGIN, assets.plugin_reference))

        # Verify with the client rather than trusting the exit status.
        references = self.installed_plugins(installation)
        if references is None or assets.plugin_reference not in references:
            return RegistrationOutcome(
                ok=False,
                code=Code.CLIENT_ACTION_REQUIRED,
                created=tuple(created),
                migrated=tuple(migrated),
                manual_step_required=True,
                details={"step": "verify"},
            )
        return RegistrationOutcome(
            ok=True,
            code=Code.MIGRATION_DONE if migrated else Code.CLIENT_REGISTERED,
            created=tuple(created),
            migrated=tuple(migrated),
            # Registering a plugin does not load it into a running client.
            manual_step_required=True,
        )

    def remove(
        self, installation: ClientInstallation, resources: Sequence[tuple[str, str]]
    ) -> RegistrationOutcome:
        """Remove only the listed resources, in the order that leaves nothing dangling."""
        ordered = [item for item in resources if item[0] == RESOURCE_PLUGIN]
        ordered += [item for item in resources if item[0] == RESOURCE_MARKETPLACE]
        removed: list[PlanStep] = []
        manual: list[str] = []
        for kind, name in ordered:
            if kind == RESOURCE_PLUGIN and CAP_PLUGIN_REMOVE in installation.capabilities:
                command = ["plugin", "remove", name]
            elif kind == RESOURCE_MARKETPLACE and CAP_MARKETPLACE_REMOVE in (
                installation.capabilities
            ):
                command = ["plugin", "marketplace", "remove", name]
            else:
                manual.append(name)
                continue
            result = self._run(
                [str(installation.executable), *command], timeout=MUTATION_TIMEOUT_SECONDS
            )
            if result.ok:
                removed.append(PlanStep("remove", kind, name))
            else:
                manual.append(name)
        if manual:
            return RegistrationOutcome(
                ok=False,
                code=Code.CLIENT_ACTION_REQUIRED,
                created=tuple(removed),
                manual_step_required=True,
                details={"remaining": manual},
            )
        return RegistrationOutcome(
            ok=True,
            code=Code.CLIENT_REMOVED,
            created=tuple(removed),
            # A server the client already started keeps running until it restarts.
            manual_step_required=True,
        )

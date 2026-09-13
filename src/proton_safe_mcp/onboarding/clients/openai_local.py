"""ChatGPT desktop / Codex on this computer, sharing one local Codex host.

Capabilities are established by asking the installed client itself — each subcommand this
adapter intends to run is probed with ``--help`` — never inferred from a version number.
An installation that does not expose them is reported as unsupported instead of being
driven blind.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

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
CANDIDATE_PATHS: Final = (
    "/usr/lib/chatgpt/resources/codex",
    "/snap/bin/codex",
    "/usr/bin/codex",
    "/usr/local/bin/codex",
)

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

#: Both surfaces share one Codex host, so one registration covers them; registering twice
#: would create two servers for the same managed setup.
SHARED_SURFACES: Final = ("ChatGPT desktop", "Codex CLI", "Codex IDE extension")


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "")
    if configured.startswith("/"):
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
        candidate_paths: Sequence[str] = CANDIDATE_PATHS,
        config_home: Path | None = None,
    ) -> None:
        self._run: CommandRunner = runner or run_command
        self._candidate_paths = tuple(candidate_paths)
        self._config_home = config_home

    # -- discovery ---------------------------------------------------------------

    def _candidates(self) -> list[Path]:
        paths = [Path(item) for item in self._candidate_paths]
        found = shutil.which("codex")
        if found:
            paths.insert(0, Path(found))
        return executable_candidates(paths)

    def discover(self) -> list[ClientInstallation]:
        """Find installations and confirm each one answers `--version` and `plugin`.

        Two candidate paths resolving to the same executable are reported once. Discovery
        stays cheap: the full capability probe runs only for the installation the user
        selects.
        """
        installations: list[ClientInstallation] = []
        for index, executable in enumerate(self._candidates()):
            version = self._run([str(executable), "--version"])
            if not version.ok:
                continue
            plugin = self._run([str(executable), "plugin", "--help"])
            capabilities = {CAP_PLUGIN} if plugin.ok else set()
            installations.append(
                ClientInstallation(
                    id=f"{ADAPTER_ID}:{index}",
                    adapter=ADAPTER_ID,
                    display_name=self.display_name,
                    executable=executable,
                    version=_version_of(version.stdout),
                    capabilities=frozenset(capabilities),
                    shared_surfaces=SHARED_SURFACES,
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

    def _config_path(self) -> Path:
        return (self._config_home or codex_home()) / "config.toml"

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
        plugin launches `uvx` and passes environment variables instead.
        """
        arguments = entry.get("args")
        args = [str(item) for item in arguments] if isinstance(arguments, list) else []
        command = str(entry.get("command", ""))
        return command.endswith("proton-safe-mcp") and "--config" in args

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
        for reference in installed:
            plugin, _, marketplace = reference.partition("@")
            if plugin != MANAGED_PLUGIN:
                continue
            if marketplace == assets.marketplace_name:
                replaces.append(reference)
            else:
                conflicts.append(reference)
        return RegistrationPlan(
            installation=installation,
            steps=tuple(steps),
            replaces=tuple(dict.fromkeys(replaces)),
            conflicts=tuple(dict.fromkeys(conflicts)),
        )

    def apply(self, plan: RegistrationPlan, assets: ManagedPluginAssets) -> RegistrationOutcome:
        """Register the local marketplace then the plugin, reporting what was created.

        The client may start a server as soon as a plugin is installed, so this is only
        ever called after the configuration and the credential are already saved.
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
                manual_step_required=True,
                details={"step": "verify"},
            )
        return RegistrationOutcome(
            ok=True,
            code=Code.CLIENT_REGISTERED,
            created=tuple(created),
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

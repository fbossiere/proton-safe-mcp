# Download Proton Safe for Ubuntu

[Français](fr/telecharger.md)

**A guided app to connect Proton Mail to your local ChatGPT desktop / Codex assistant.**

## Before you download

You need all of the following on the **same computer**:

- **Ubuntu 24.04 LTS, Intel / AMD 64-bit (x86_64).** This installer is not for Windows,
  macOS, ARM, WSL or a phone.
- **[Proton Mail Bridge](https://proton.me/mail/bridge)** installed, running and signed in,
  with a paid Proton plan that includes Bridge.
- **A compatible local ChatGPT desktop / Codex installation.** A ChatGPT web account alone
  is not enough. The setup app checks whether your installed client supports the required
  plugin commands before making changes.
- **A graphical user session with a session keyring** (Secret Service, such as Ubuntu's
  `gnome-keyring`). Run the application as your normal user.

Python and `uv` are included. You do not need to install them or edit a configuration file.

!!! info "Before giving an assistant access to your mail"
    With a cloud AI model, the content of messages your assistant reads is sent to that
    provider. Proton Safe has no send, delete or move tools; confirmed drafts wait in
    Proton Mail for you to review and send. [Read the security model](security-model.md).

## Get the installer

[Download for Ubuntu — v2.1.1 (.deb)](https://github.com/fbossiere/proton-safe-mcp/releases/download/v2.1.1/proton-safe-assistant_2.1.1_amd64.deb){ .md-button .md-button--primary }

Free, MIT licensed, hosted on the project's **official GitHub Release**. No GitHub account
is needed to download it. This is an independent project, not affiliated with or endorsed by Proton.

[Release notes and all files](https://github.com/fbossiere/proton-safe-mcp/releases/tag/v2.1.1)
· [Checksum file](https://github.com/fbossiere/proton-safe-mcp/releases/download/v2.1.1/proton-safe-assistant_2.1.1_amd64.deb.sha256)
· [Build provenance](https://github.com/fbossiere/proton-safe-mcp/releases/download/v2.1.1/BUILD-PROVENANCE.txt)

## Install, connect, try

1. **Open the downloaded `.deb` with your graphical package installer** and choose Install.
   Ubuntu may ask for your computer's administrator password to install the application.
2. **Launch Proton Safe** from the applications menu, as your normal user.
3. **Follow the guided checks.** Open Bridge to find its IMAP address and generated password.
   Enter those in Proton Safe. Your Proton account password belongs only in Bridge.
4. **Review the plan**, select your detected assistant and activate the connection. Reopen
   or restart your AI client if it has not loaded the new connection, then verify the tools
   there as the setup app requests.
5. **[Try your first three requests](try-it.md)** and tell us where the setup was easy or difficult.

![Proton Safe Bridge form with address and password fields and advanced options collapsed](assets/desktop/bridge-en.png)

*Actual interface render with demo data. It does not demonstrate a live mail connection.*

??? question "The file opens as an archive instead of an installer"
    Use **Open with** and select your software/package installer if one is installed.
    If your Ubuntu installation has none, the alternative is to open a terminal in your
    Downloads folder and run:

    ```bash
    sudo apt install ./proton-safe-assistant_2.1.1_amd64.deb
    ```

    Then launch **Proton Safe** normally, never with `sudo`.

??? info "Verify the download"
    Put the `.deb` and its `.sha256` file in the same folder. In a terminal in that folder:

    ```bash
    sha256sum -c proton-safe-assistant_2.1.1_amd64.deb.sha256
    ```

    The published v2.1.1 installer has SHA-256:

    ```text
    bf9612173d6dae36135ee11605f3cab44125b06a7be3a9f1179cce9334204512
    ```

    The checksum detects a damaged or mismatched download. Obtain both files from the
    official release; a checksum is not a separate guarantee of the publisher's identity.

## Updates and removal

**Updates are manual.** Check the [release notes](https://github.com/fbossiere/proton-safe-mcp/releases)
before installing a newer official `.deb` over the existing version. Reopen Proton Safe,
check the connection, and restart your assistant so it loads the updated runtime.

To stop access, use **Disconnect Proton Safe** in the app first, then restart your AI client.
The app separately offers to erase its saved local settings and credential. A failed removal
keeps the information needed for a retry. Afterwards, you can uninstall the package with
Ubuntu's software manager. See [connection removal](desktop-assistant.md#after-installation).

## Another operating system or assistant?

This desktop installer currently targets Ubuntu 24.04 and local ChatGPT desktop / Codex.
For other MCP clients, see the [command-line setup](getting-started.md) and
[client guides](clients.md). These are separate, more technical installation paths;
this download does not add support for ChatGPT web or mobile.

If installation stops, keep the message visible and follow the
[troubleshooting guide](troubleshooting.md), or [report the step that blocked you](try-it.md#send-feedback).

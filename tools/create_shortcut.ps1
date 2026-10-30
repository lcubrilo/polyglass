<#
.SYNOPSIS
    Creates a "Polyglass (dev)" shortcut that runs Polyglass from this source checkout.

.DESCRIPTION
    The shortcut starts .venv\Scripts\pythonw.exe -m polyglass in the repository folder, without a
    console window, using the Polyglass icon. It is named "Polyglass (dev)" so it never clashes with the
    shortcut of an installed release.

    Run from the repository root:
        powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1
        powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1 -StartMenu

.PARAMETER StartMenu
    Also add the shortcut to the Start Menu, so Polyglass can be found by typing its name.

.PARAMETER Folder
    Create the shortcut in this folder instead of the desktop.
#>
param(
    [switch]$StartMenu,
    [string]$Folder = [Environment]::GetFolderPath("Desktop")
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
$icon = Join-Path $repo "polyglass\resources\polyglass.ico"

if (-not (Test-Path $pythonw)) {
    throw "No virtual environment at $repo\.venv. Create it first: py -3.11 -m venv .venv; .venv\Scripts\pip install -e ."
}

$folders = @($Folder)
if ($StartMenu) { $folders += [Environment]::GetFolderPath("Programs") }

$shell = New-Object -ComObject WScript.Shell
foreach ($target in $folders) {
    $path = Join-Path $target "Polyglass (dev).lnk"
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $pythonw
    $link.Arguments = "-m polyglass"
    $link.WorkingDirectory = $repo
    $link.IconLocation = $icon
    $link.Description = "Polyglass, running from $repo"
    $link.Save()
    "Created $path"
}

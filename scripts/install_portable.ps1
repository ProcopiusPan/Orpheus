[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InstallPath,
    [string] $RemoteUrl,
    [string] $GitName = "Orpheus User",
    [string] $GitEmail = "orpheus-user@example.invalid",
    [string] $PythonCommand = "py",
    [string] $PluginName = "orpheus",
    [string] $PersonalRoot,
    [switch] $DryRun,
    [switch] $SkipDependencyInstall,
    [switch] $SkipPluginInstall
)

$ErrorActionPreference = "Stop"
$packageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedInstall = [IO.Path]::GetFullPath($InstallPath)
$resolvedPersonalRoot = if ([string]::IsNullOrWhiteSpace($PersonalRoot)) {
    [Environment]::GetFolderPath("UserProfile")
} else { [IO.Path]::GetFullPath($PersonalRoot) }

function Assert-SafeText { param([string] $Value, [string] $Name)
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Contains("`n") -or $Value.Contains("`r")) {
        throw "$Name must be non-empty and single-line"
    }
}

function Get-RequiredCommand { param([string] $Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { throw "Required command not found: $Name" }
    if ($command.Path) { return $command.Path }
    return $command.Name
}

function Invoke-External {
    param([string] $File, [string[]] $Arguments, [string] $WorkingDirectory)
    $display = $File + " " + ($Arguments -join " ")
    if ($DryRun) { Write-Output ("DRY_RUN " + $display); return }
    Push-Location $WorkingDirectory
    try {
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $display" }
    } finally { Pop-Location }
}

function Assert-SafeRemote {
    param([string] $Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    if ($Value -match "[\r\n?#@\\]") { throw "RemoteUrl must be credential-free HTTPS or SSH without query, fragment, userinfo, or backslashes" }
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) { throw "RemoteUrl must be an absolute HTTPS or SSH URL" }
    if ($uri.Scheme -notin @("https", "ssh") -or [string]::IsNullOrWhiteSpace($uri.Host) -or [string]::IsNullOrWhiteSpace($uri.AbsolutePath.Trim('/'))) {
        throw "RemoteUrl must be an absolute HTTPS or SSH URL with a repository path"
    }
    if (-not [string]::IsNullOrEmpty($uri.UserInfo) -or $uri.Query -or $uri.Fragment) {
        throw "RemoteUrl must not contain userinfo, query, or fragment"
    }
}

function Write-AtomicJson {
    param([string] $Path, [object] $Value)
    $directory = Split-Path -Parent $Path
    $temporary = Join-Path $directory ("marketplace." + [Guid]::NewGuid().ToString("N") + ".tmp")
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    try {
        [IO.File]::WriteAllText($temporary, (($Value | ConvertTo-Json -Depth 20) + "`n"), $utf8)
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        if (Test-Path $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    }
}

Assert-SafeText $GitName "GitName"
Assert-SafeText $GitEmail "GitEmail"
if ($PluginName -notmatch "^[a-z0-9]+(?:-[a-z0-9]+)*$" -or $PluginName.Length -gt 64) {
    throw "PluginName must be lowercase letters, digits, and single hyphens only"
}
Assert-SafeRemote $RemoteUrl

$installExisted = Test-Path $resolvedInstall
if ($installExisted -and -not (Test-Path $resolvedInstall -PathType Container)) { throw "InstallPath is not a directory" }
if ($installExisted -and @(Get-ChildItem -LiteralPath $resolvedInstall -Force).Count -gt 0) {
    throw "InstallPath exists and is non-empty; refusing to overwrite"
}
if (Test-Path $resolvedPersonalRoot -PathType Leaf) { throw "PersonalRoot is a file" }

# All command and destination checks happen before the first write.
$gitCommand = Get-RequiredCommand "git"
$pythonCommandPath = Get-RequiredCommand $PythonCommand
if (-not $DryRun) {
    & $pythonCommandPath --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "PythonCommand could not run" }
}

$pluginSource = Join-Path $resolvedPersonalRoot ("plugins/" + $PluginName)
$marketplaceDir = Join-Path $resolvedPersonalRoot ".agents/plugins"
$marketplacePath = Join-Path $marketplaceDir "marketplace.json"
$marketplaceExists = $false
$marketplaceOriginalBytes = $null
$marketplace = $null
$pluginSourceExisted = $false
if (-not $SkipPluginInstall) {
    $codexCommand = Get-RequiredCommand "codex"
    $codexHelp = & $codexCommand plugin add --help 2>&1
    if ($LASTEXITCODE -ne 0 -or -not ($codexHelp -match "--json")) {
        throw "Installed Codex CLI does not support 'codex plugin add ... --json'"
    }
    if ((Test-Path $pluginSource) -and -not (Test-Path $pluginSource -PathType Container)) { throw "Personal plugin source is not a directory" }
    if ((Test-Path $pluginSource) -and @(Get-ChildItem -LiteralPath $pluginSource -Force).Count -gt 0) {
        throw "Personal plugin source exists and is non-empty; refusing to overwrite"
    }
    $pluginSourceExisted = Test-Path $pluginSource
    $marketplaceExists = Test-Path $marketplacePath
    if ($marketplaceExists) {
        if (-not (Test-Path $marketplacePath -PathType Leaf)) { throw "Marketplace path is not a file" }
        $marketplaceOriginalBytes = [IO.File]::ReadAllBytes($marketplacePath)
        try { $marketplace = Get-Content $marketplacePath -Raw | ConvertFrom-Json }
        catch { throw "Existing marketplace is not valid JSON" }
        if ($marketplace.name -ne "personal") { throw "Existing marketplace is not personal; refusing to overwrite" }
        if (@($marketplace.plugins | Where-Object { $_.name -eq $PluginName }).Count -gt 0) {
            throw "personal marketplace already contains $PluginName"
        }
    } else {
        $marketplace = Get-Content (Join-Path $packageRoot "marketplace/marketplace.json") -Raw | ConvertFrom-Json
        if ($marketplace.name -ne "personal") { throw "Packaged marketplace must be personal" }
        if ($PluginName -ne "orpheus") {
            $marketplace.plugins = @($marketplace.plugins | Where-Object { $_.name -ne "orpheus" })
        }
    }
    if (Test-Path $marketplaceDir -PathType Leaf) { throw "Marketplace directory is a file" }
}

if ($RemoteUrl -and -not $DryRun) {
    $oldPrompt = $env:GIT_TERMINAL_PROMPT
    $env:GIT_TERMINAL_PROMPT = "0"
    try {
        $remoteProbe = & $gitCommand ls-remote --heads --tags $RemoteUrl 2>&1
        if ($LASTEXITCODE -ne 0) { throw "RemoteUrl could not be queried; refusing to configure it" }
        if ($remoteProbe) { throw "Remote repository is non-empty; refusing to overwrite" }
    } finally { $env:GIT_TERMINAL_PROMPT = $oldPrompt }
}

$installCreated = $false
$pluginCreated = $false
$marketplaceWritten = $false
$pushAttempted = $false
try {
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $resolvedInstall | Out-Null
        $installCreated = -not $installExisted
        Get-ChildItem -LiteralPath $packageRoot -Force |
            Where-Object { $_.Name -notin @(".git", ".runtime", "dist", "build") } |
            Copy-Item -Destination $resolvedInstall -Recurse -Force
        New-Item -ItemType Directory -Force -Path (Join-Path $resolvedInstall "facts"), (Join-Path $resolvedInstall "candidates"), (Join-Path $resolvedInstall "reviews"), (Join-Path $resolvedInstall "requests"), (Join-Path $resolvedInstall "issues"), (Join-Path $resolvedInstall "incidents") | Out-Null
        Copy-Item (Join-Path $resolvedInstall "templates/facts/MANIFEST.json") (Join-Path $resolvedInstall "facts/MANIFEST.json") -Force
        Copy-Item (Join-Path $resolvedInstall "templates/facts/README.md") (Join-Path $resolvedInstall "facts/README.md") -Force
        $projectPluginSource = Join-Path $resolvedInstall "plugins/orpheus"
        $projectPluginPath = Join-Path $resolvedInstall ("plugins/" + $PluginName)
        if ($PluginName -ne "orpheus") {
            Move-Item -LiteralPath $projectPluginSource -Destination $projectPluginPath
        }
        $pluginManifestPath = Join-Path $projectPluginPath ".codex-plugin/plugin.json"
        $pluginManifest = Get-Content $pluginManifestPath -Raw | ConvertFrom-Json
        $pluginManifest.name = $PluginName
        if ($PluginName -ne "orpheus") {
            $pluginManifest.version = "$($pluginManifest.version).$PluginName"
            $pluginManifest.interface.displayName = "Orpheus ($PluginName)"
        }
        Write-AtomicJson $pluginManifestPath $pluginManifest
    }

    $venvPython = Join-Path $resolvedInstall ".venv/Scripts/python.exe"
    Invoke-External $pythonCommandPath @("-3.13", "-m", "venv", (Join-Path $resolvedInstall ".venv")) $resolvedInstall
    if (-not $DryRun -and -not $SkipDependencyInstall) {
        Invoke-External $venvPython @("-m", "pip", "install", "--requirement", (Join-Path $resolvedInstall "requirements.lock.txt")) $resolvedInstall
        Invoke-External $venvPython @("-m", "pip", "install", "--no-deps", "-e", $resolvedInstall) $resolvedInstall
    }

    $mcp = @{ mcpServers = @{ "orpheus-fact" = @{ command = $venvPython; args = @(Join-Path $resolvedInstall "scripts/orpheus_fact_stdio.py") } } }
    if (-not $DryRun) {
        Write-AtomicJson (Join-Path $projectPluginPath ".mcp.json") $mcp
        Invoke-External $gitCommand @("init", "-b", "main") $resolvedInstall
        Invoke-External $gitCommand @("config", "user.name", $GitName) $resolvedInstall
        Invoke-External $gitCommand @("config", "user.email", $GitEmail) $resolvedInstall
        Invoke-External $gitCommand @("add", ".") $resolvedInstall
        Invoke-External $gitCommand @("commit", "-m", "initialize portable Orpheus repository") $resolvedInstall
    }

    if (-not $SkipPluginInstall) {
        if (-not $DryRun) {
            New-Item -ItemType Directory -Force -Path (Split-Path $pluginSource) | Out-Null
            if (-not (Test-Path $pluginSource)) { New-Item -ItemType Directory -Path $pluginSource | Out-Null; $pluginCreated = $true }
            Copy-Item (Join-Path $resolvedInstall ("plugins/" + $PluginName + "/*")) $pluginSource -Recurse -Force
            if (-not $marketplace.plugins) { $marketplace | Add-Member -NotePropertyName plugins -NotePropertyValue @() }
            if (@($marketplace.plugins | Where-Object { $_.name -eq $PluginName }).Count -eq 0) {
                $entry = @{ name = $PluginName; source = @{ source = "local"; path = ("./plugins/" + $PluginName) }; policy = @{ installation = "AVAILABLE"; authentication = "ON_INSTALL" }; category = "Productivity" }
                $marketplace.plugins += [PSCustomObject]$entry
            }
            New-Item -ItemType Directory -Force -Path $marketplaceDir | Out-Null
            Write-AtomicJson $marketplacePath $marketplace
            $marketplaceWritten = $true
            Invoke-External $codexCommand @("plugin", "add", ($PluginName + "@personal"), "--json") $resolvedInstall
        }
    }

    if ($RemoteUrl) {
        if (-not $DryRun) {
            Invoke-External $gitCommand @("remote", "add", "origin", $RemoteUrl) $resolvedInstall
            $pushAttempted = $true
            Invoke-External $gitCommand @("push", "--set-upstream", "origin", "main") $resolvedInstall
        } else { Write-Output "DRY_RUN empty-remote probe and git push --set-upstream origin main" }
    }
} catch {
    if (-not $DryRun -and -not $pushAttempted) {
        if ($marketplaceWritten) {
            if ($marketplaceExists) { [IO.File]::WriteAllBytes($marketplacePath, $marketplaceOriginalBytes) }
            elseif (Test-Path $marketplacePath) { Remove-Item -LiteralPath $marketplacePath -Force }
        }
        if (Test-Path $pluginSource) {
            if (-not $pluginSourceExisted) { Remove-Item -LiteralPath $pluginSource -Recurse -Force }
            else { Get-ChildItem -LiteralPath $pluginSource -Force | Remove-Item -Recurse -Force }
        }
        if ($installCreated -and (Test-Path $resolvedInstall)) { Remove-Item -LiteralPath $resolvedInstall -Recurse -Force }
        elseif ($installExisted -and (Test-Path $resolvedInstall)) {
            Get-ChildItem -LiteralPath $resolvedInstall -Force | Remove-Item -Recurse -Force
        }
    }
    throw
}

if ($DryRun) {
    Write-Output ("DRY_RUN create personal marketplace at " + $marketplacePath + " and codex plugin add " + $PluginName + "@personal --json")
}
Write-Output (ConvertTo-Json @{ status = if ($DryRun) { "DRY_RUN" } else { "INSTALLED" }; install_path = $resolvedInstall; personal_root = $resolvedPersonalRoot; remote_configured = [bool]$RemoteUrl; plugin = if ($SkipPluginInstall) { "SKIPPED" } else { $PluginName + "@personal" } } -Compress)

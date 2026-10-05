param(
    [Parameter(Mandatory = $true)][string]$Commit,
    [Parameter(Mandatory = $true)][long]$Build,
    [string]$Python = "python",
    [string]$OutputDirectory = ""
)
$ErrorActionPreference = "Stop"
$taskRepo = Split-Path -Parent $PSScriptRoot
$taskWork = Join-Path $taskRepo ".pc-release-build"
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $taskRepo "pc-releases" }
if (-not (Test-Path -LiteralPath (Join-Path $taskRepo "pc-app/ffmpeg.exe"))) {
    throw "Falta pc-app/ffmpeg.exe. Se necesita para grabar; no se publica una version incompleta."
}
function Invoke-BuildStep([string[]]$Arguments) {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Fallo de compilacion: $Arguments" }
}
Push-Location (Join-Path $taskRepo "pc-app")
try {
    # Rutas separadas: no sobrescribir los artefactos anteriores del usuario.
    Invoke-BuildStep @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "$taskWork/app", "--workpath", "$taskWork/work-app", "main.spec")
    Invoke-BuildStep @("-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--noupx", "--name", "AuditFlow", "--distpath", "$taskWork/launcher", "--workpath", "$taskWork/work-launcher", "--specpath", "$taskWork", "--paths", (Join-Path $taskRepo "pc-app"), "launcher.py")
} finally { Pop-Location }
$taskProbe = Start-Process -FilePath "$taskWork/app/main/main.exe" -ArgumentList "--self-test" -PassThru -WindowStyle Hidden
if (-not $taskProbe.WaitForExit(60000)) {
    $taskProbe.Kill()
    throw "La prueba del bundle no termino en 60 segundos; no se publica."
}
if ($taskProbe.ExitCode -ne 0) { throw "La prueba del bundle fallo; revisar self-test.json." }
$taskProbeResult = Get-Content -LiteralPath "$taskWork/app/main/self-test.json" -Raw | ConvertFrom-Json
if (-not $taskProbeResult.ok) { throw "El bundle no es valido: $($taskProbeResult.error)" }
# No incluir el resultado de diagnóstico en los archivos distribuidos.
Remove-Item -LiteralPath "$taskWork/app/main/self-test.json"
Invoke-BuildStep @((Join-Path $taskRepo "tools/package_pc_release.py"), "--app", "$taskWork/app/main", "--launcher", "$taskWork/launcher/AuditFlow.exe", "--output", $OutputDirectory, "--commit", $Commit, "--build", "$Build")

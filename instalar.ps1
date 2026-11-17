# Instalador de um comando do Harness Juridico (Windows 10/11, sem administrador).
#
# Uso, no PowerShell:
#   irm https://raw.githubusercontent.com/paulotony11/harness-juridico/main/instalar.ps1 | iex
#
# Opcional, definir antes do comando:
#   $env:HARNESS_DIR = "D:\harness-juridico"     # onde baixar o repositorio (padrao: $HOME\harness-juridico)
#   $env:CEREBRO_EM  = "C:\caminho\do\cofre"      # cofre do segundo cerebro fora do workspace (ex.: OneDrive)
#
# Pode rodar de novo a qualquer momento: atualiza o que mudou, faz backup do que substituir e nunca
# sobrescreve notas do cofre.

function Install-HarnessJuridico {
    $ErrorActionPreference = 'Continue'
    $repo = 'https://github.com/paulotony11/harness-juridico.git'
    $dir = if ($env:HARNESS_DIR) { $env:HARNESS_DIR } else { Join-Path $HOME 'harness-juridico' }

    function Update-SessionPath {
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
    }
    function Write-Step($texto) { Write-Host "`n=== $texto ===" -ForegroundColor Cyan }

    Write-Step 'Git'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements --silent
        Update-SessionPath
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host 'Git nao foi instalado. Instale com "winget install Git.Git" e rode o comando de novo.' -ForegroundColor Red
        return
    }

    Write-Step "Repositorio em $dir"
    if (Test-Path (Join-Path $dir '.git')) {
        git -C $dir pull --ff-only
    } else {
        git clone $repo $dir
    }
    if (-not (Test-Path (Join-Path $dir 'instalar.py'))) {
        Write-Host 'Nao consegui baixar o repositorio. Confira a internet e rode de novo.' -ForegroundColor Red
        return
    }

    Write-Step 'Pre-requisitos: Python, uv, Tesseract, Obsidian'
    $env:HARNESS_BOOTSTRAP = '1'
    & (Join-Path $dir 'prerequisitos-windows.ps1')
    Update-SessionPath
    $env:UV_NATIVE_TLS = '1'

    Write-Step 'Claude Code'
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Write-Host 'ja instalado'
    } else {
        Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
        Update-SessionPath
        $local = Join-Path $HOME '.local\bin'
        if ((Test-Path $local) -and ($env:Path -notlike "*$local*")) { $env:Path += ";$local" }
    }

    Write-Step 'Python'
    $py = $null
    $candidatos = @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'), 'python', 'py')
    foreach ($c in $candidatos) {
        try {
            $ok = & $c -c "import sys; print(sys.version_info >= (3, 12))" 2>$null
            if ($ok -eq 'True') { $py = $c; break }
        } catch { }
    }
    if (-not $py) {
        Write-Host 'Python 3.12+ nao encontrado. Feche e abra o PowerShell e rode o comando de novo.' -ForegroundColor Red
        return
    }
    Write-Host "usando $py"

    Write-Step 'Stack do harness'
    $opcoes = @('instalar.py')
    $cerebro = $env:CEREBRO_EM
    if (-not $cerebro -and $env:OneDrive) {
        $padrao = Join-Path $env:OneDrive 'HYASMIN - ADVOCACIA\Cerebro Juridico'
        if (Test-Path $padrao) { $cerebro = $padrao }
    }
    if ($cerebro) {
        Write-Host "cofre do segundo cerebro: $cerebro"
        $opcoes += @('--cerebro-em', $cerebro)
    }
    Push-Location $dir
    try { & $py @opcoes } finally { Pop-Location }

    Write-Host "`nPronto. Feche e abra o terminal, entre na pasta do workspace (cd ~\juridico) e rode: claude" -ForegroundColor Green
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Write-Host 'Na primeira vez, o Claude Code pede login com a sua conta.' -ForegroundColor Yellow
    }
}

Install-HarnessJuridico

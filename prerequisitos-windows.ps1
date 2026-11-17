# Pré-requisitos do harness jurídico no Windows (sem precisar de administrador).
# Uso: powershell -ExecutionPolicy Bypass -File .\prerequisitos-windows.ps1
# Depois: python instalar.py

$ErrorActionPreference = "Continue"

function Install-WingetPkg($id) {
    Write-Host "== $id"
    winget install --id $id -e --source winget --accept-source-agreements --accept-package-agreements --silent
}

Install-WingetPkg "Python.Python.3.13"
Install-WingetPkg "astral-sh.uv"
Install-WingetPkg "Git.Git"
Install-WingetPkg "GitHub.cli"
Install-WingetPkg "UB-Mannheim.TesseractOCR"

# Redes com inspeção de HTTPS (antivírus/proxy): uv passa a usar os certificados do Windows.
[Environment]::SetEnvironmentVariable("UV_NATIVE_TLS", "1", "User")

# Tesseract: PATH do usuário + idioma português numa pasta do usuário (Program Files exige admin).
$tess = "C:\Program Files\Tesseract-OCR"
if (Test-Path "$tess\tesseract.exe") {
    $p = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($p -notlike "*Tesseract-OCR*") {
        [Environment]::SetEnvironmentVariable("Path", ($p.TrimEnd(';') + ";$tess"), "User")
    }
    $td = Join-Path $env:LOCALAPPDATA "tessdata"
    New-Item -ItemType Directory -Force $td | Out-Null
    Copy-Item "$tess\tessdata\eng.traineddata", "$tess\tessdata\osd.traineddata" $td -Force
    if (-not (Test-Path "$td\por.traineddata")) {
        Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata" -OutFile "$td\por.traineddata"
    }
    [Environment]::SetEnvironmentVariable("TESSDATA_PREFIX", $td, "User")
    Write-Host "Tesseract: idiomas em $td (eng, osd, por)"
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "Claude Code nao encontrado. Instale com:"
    Write-Host "  irm https://claude.ai/install.ps1 | iex"
}

Write-Host ""
Write-Host "Feche e abra o terminal (para o PATH valer) e rode: python instalar.py"

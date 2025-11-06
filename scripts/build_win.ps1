param(
  [switch]$Console
)
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
  pip install pyinstaller
}
$mode = "--windowed"
if ($Console) { $mode = "" }
pyinstaller --noconfirm $mode --name "BallotFinder" `
  --add-data "config.json;." app.py
Write-Host "Built to dist/BallotFinder/"

<#
Dev helper for common project commands.

Usage (from the project root):
  .\run.ps1            # start the API with auto-reload (default)
  .\run.ps1 app        # same as above
  .\run.ps1 migrate    # apply DB migrations (alembic upgrade head)
  .\run.ps1 revision   # check current DB revision
  .\run.ps1 test <file># run a python script with the venv interpreter
#>
param(
    [string]$cmd = "app",
    [string]$arg = ""
)

$py     = ".\.venv\Scripts\python.exe"
$uvi    = ".\.venv\Scripts\uvicorn.exe"
$alembic = ".\.venv\Scripts\alembic.exe"

switch ($cmd) {
    "app"      { & $uvi app.main:app --reload }
    "migrate"  { & $alembic upgrade head }
    "revision" { & $alembic current }
    "test"     { & $py $arg }
    default    { Write-Host "Unknown command '$cmd'. Use: app | migrate | revision | test" }
}

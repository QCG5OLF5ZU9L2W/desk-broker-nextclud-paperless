# Minimaler Explorer-Kontextmenü-Starter für spätere Windows-Paketierung.
# Muss an den finalen Installationspfad angepasst werden.
$Exe = "$env:LOCALAPPDATA\paperless-nc-import\paperless-nc-import.exe"
$Key = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\PaperlessNcImport"
New-Item -Path $Key -Force | Out-Null
Set-ItemProperty -Path $Key -Name "MUIVerb" -Value "An Paperless senden"
Set-ItemProperty -Path $Key -Name "Icon" -Value $Exe
New-Item -Path "$Key\command" -Force | Out-Null
Set-ItemProperty -Path "$Key\command" -Name "(default)" -Value "`"$Exe`" --gui `"%1`""
Write-Host "Kontextmenü installiert."

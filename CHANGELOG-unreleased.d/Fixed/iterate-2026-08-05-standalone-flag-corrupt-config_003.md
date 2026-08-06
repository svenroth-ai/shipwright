A run config saved with a UTF-8 BOM (PowerShell `Out-File -Encoding utf8`, VS Code `utf8bom`) is read normally instead of reported as corrupt at "line 1 column 1".

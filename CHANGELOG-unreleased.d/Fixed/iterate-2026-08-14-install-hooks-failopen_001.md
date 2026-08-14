install-hooks.ps1 could silently overwrite a foreign `core.hooksPath` or report success on a failed write; both scripts now fail closed (ported from svenroth-ai/leadwright)

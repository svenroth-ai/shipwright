Config readers now uniformly tolerate a UTF-8 BOM: lib/config.read_config uses utf-8-sig like the four sibling readers, so a hand-edited BOM config no longer raises JSONDecodeError.

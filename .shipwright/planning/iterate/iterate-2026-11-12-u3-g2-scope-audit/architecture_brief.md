# Architecture Brief
Problem: (a) audit check G2 flags every scope of a project whose only split is the generic adopted one, and a source comment promises an automatic skip that does not exist; (b) a comma-joined scope such as daemon,lib is read as one unknown token.
Options: (1) do nothing and leave the false promise; (2) correct the text and point to the two explicit opt-outs (disabled_checks G2, or the project's own alias map / stoplist); (3) skip G2 automatically when only the adopted split exists; (4) for (b): split on commas and judge each part, or keep one token.
Nothing permanent is added to the data model; one small pure module for scope parsing.

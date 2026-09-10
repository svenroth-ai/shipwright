The anchor-promotion staleness guard now also catches an uncommitted or untracked edit to a bound test file (not only a committed one), since this tool is only ever run by a human operator, never CI.

decision-drop writes now resolve against the calling iterate's own worktree instead of the main repo's disk, so a drop written mid-iterate no longer lands outside the branch that produced it

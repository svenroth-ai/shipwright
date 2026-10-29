The design boundary check keeps what it recorded at session start when commits land during the same run, so changes made earlier in the session are still reported instead of being absorbed.

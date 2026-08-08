windows-tests.yml now provisions its pytest environment once (was 3x) and runs shared/tests under pytest-xdist (-n 4), cutting the job from ~24-28min to a predicted ~10-14min

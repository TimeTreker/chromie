# Pinned GPU runtime. Remove this constructor repair when an upstream pinned
# image initializes Gemma4Unified's inherited output-head contract itself.
FROM lmsysorg/sglang@sha256:59e11312666e1c5c155210ea335589b91daa0d70848521b390b93b1b1e8fb0ef

# The unified constructor skips the parent constructor, but inherits forward(),
# which reads lm_head_is_tied. Preserve the exact existing GPU branch predicate.
RUN python3 - <<'PY'
from pathlib import Path

path = Path('/sgl-workspace/sglang/python/sglang/srt/models/gemma4_unified.py')
source = path.read_text()
before = '        if self.pp_group.world_size == 1 and text_tie:\n'
after = (
    '        self.lm_head_is_tied = self.pp_group.world_size == 1 and text_tie\n'
    '        if self.lm_head_is_tied:\n'
)
if source.count(before) != 1:
    raise RuntimeError('Pinned Gemma constructor changed; review the upstream fix before building')
path.write_text(source.replace(before, after))
PY

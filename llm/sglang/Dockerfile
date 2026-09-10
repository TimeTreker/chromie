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

# XGrammar must honor the same per-schema whitespace annotation already used
# by SGLang's llguidance backend. Remove when the pinned upstream supports it.
# The complete schema string remains the cache key, including this annotation.
RUN python3 - <<'PY'
from pathlib import Path

path = Path('/sgl-workspace/sglang/python/sglang/srt/constrained/xgrammar_backend.py')
source = path.read_text()
before = '''                ctx = self.grammar_compiler.compile_json_schema(
                    schema=key_string, any_whitespace=self.any_whitespace
                )'''
after = '''                schema = json.loads(key_string)
                guidance = schema.get("x-guidance", {}) if isinstance(schema, dict) else {}
                if not isinstance(guidance, dict):
                    raise RuntimeError("x-guidance must be an object")
                any_whitespace = guidance.get("whitespace_flexible", self.any_whitespace)
                if not isinstance(any_whitespace, bool):
                    raise RuntimeError("whitespace_flexible must be a boolean")
                ctx = self.grammar_compiler.compile_json_schema(
                    schema=key_string, any_whitespace=any_whitespace
                )'''
if source.count(before) != 1:
    raise RuntimeError('Pinned XGrammar dispatch changed; review request formatting before building')
path.write_text(source.replace(before, after))
PY

# Bound JSON whitespace only when a tagged request explicitly asks for it.
# Structural JSONSchemaFormat lacks this existing XGrammar option; compile that
# node to equivalent EBNF while retaining the enclosing tagged sequence. Remove
# this bridge when the pinned structural-format API supports the option itself.
RUN python3 - <<'PY'
from pathlib import Path

path = Path('/sgl-workspace/sglang/python/sglang/srt/constrained/xgrammar_backend.py')
source = path.read_text()
marker = '\ndef _allocate_token_bitmask('
helper = '''
def _bounded_tagged_json_whitespace(node):
    if isinstance(node, dict):
        if node.get("type") == "json_schema":
            schema = node.get("json_schema")
            guidance = schema.get("x-guidance", {}) if isinstance(schema, dict) else {}
            if not isinstance(guidance, dict):
                raise RuntimeError("x-guidance must be an object")
            limit = guidance.get("max_whitespace_cnt")
            if limit is not None:
                if type(limit) is not int or limit < 1:
                    raise RuntimeError("max_whitespace_cnt must be a positive integer")
                from xgrammar import Grammar
                grammar = Grammar.from_json_schema(schema, max_whitespace_cnt=limit)
                node.clear()
                node.update(type="grammar", grammar=str(grammar))
        else:
            for value in node.values():
                _bounded_tagged_json_whitespace(value)
    elif isinstance(node, list):
        for value in node:
            _bounded_tagged_json_whitespace(value)

'''
before = '                    self._sanitize_structural_format(format_dict)\n'
after = before + '                    _bounded_tagged_json_whitespace(format_dict)\n'
if source.count(marker) != 1 or source.count(before) != 1:
    raise RuntimeError('Pinned structural dispatch changed; review bounded whitespace before building')
source = source.replace(marker, '\n' + helper + marker).replace(before, after)
path.write_text(source)
PY

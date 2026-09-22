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

# Dynamic turn/Goal schemas must not accumulate for the lifetime of the server.
# The compiler owns bounded reusable grammars; a second strong-reference cache
# would retain evicted grammars indefinitely. Active requests keep their own refs.
# Remove when the pinned upstream exposes and enforces this two-layer bound.
RUN python3 - <<'PY'
from pathlib import Path

path = Path('/sgl-workspace/sglang/python/sglang/srt/constrained/xgrammar_backend.py')
source = path.read_text()
before = '        self.grammar_compiler = GrammarCompiler(tokenizer_info=tokenizer_info)\n'
after = '''        self.grammar_compiler = GrammarCompiler(
            tokenizer_info=tokenizer_info, cache_limit_bytes=512 * 1024 * 1024
        )
'''
marker = '    def dispatch_json(self, key_string: str) -> BaseGrammarObject:\n'
method = '''    def set_cache(self, key, value):
        # GrammarCompiler reuses compiled grammars within its byte budget.
        # BaseGrammarBackend.cache must not keep a second unbounded owner.
        return None

'''
if source.count(before) != 1 or source.count(marker) != 1:
    raise RuntimeError('Pinned grammar cache ownership changed; review memory bounds before building')
path.write_text(source.replace(before, after).replace(marker, method + marker))

# Exercise the actual patched backend, not a duplicate cache implementation.
import json
from xgrammar import TokenizerInfo
from sglang.srt.constrained.xgrammar_backend import XGrammarGrammarBackend

class Tokenizer:
    def init_xgrammar(self):
        return TokenizerInfo([bytes([i]) for i in range(256)], stop_token_ids=[255]), None

backend = XGrammarGrammarBackend(Tokenizer(), 256)
if backend.grammar_compiler.cache_limit_bytes != 512 * 1024 * 1024:
    raise RuntimeError('Compiler cache budget was not applied')
for i in range(64):
    key = json.dumps({'type': 'string', 'enum': [f'value-{i}']})
    grammar = backend.dispatch_json(key)
    if not grammar.matcher.accept_string(json.dumps(f'value-{i}')):
        raise RuntimeError('Bounded grammar rejected its declared value')
    if backend.dispatch_json(key).matcher.accept_string(json.dumps('unlisted')):
        raise RuntimeError('Bounded grammar accepted an undeclared value')
    backend.set_cache(('json', key), grammar)
if backend.cache:
    raise RuntimeError('Backend retained a second unbounded grammar cache')
backend.executor.shutdown(wait=True)
PY

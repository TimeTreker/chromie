// Executed against the actual native compiler during the image build.
// Large valid grammars must not collide with parser control-state markers.
#include <iostream>
#include <stdexcept>

#include "earley_parser.h"
#include "grammar_builder.h"
#include "grammar_functor.h"

int main() {
  using namespace xgrammar;
  for (int32_t target : {127999, 128000, 128001}) {
    GrammarBuilder builder;
    const auto literal = builder.AddByteString("b");
    for (int32_t i = 1; i < target; ++i) builder.AddEmptyStr();
    const auto sequence = builder.AddSequence({literal});
    if (sequence != target) throw std::runtime_error("Wrong fixture index");
    builder.AddRule("root", builder.AddChoices({sequence}));
    auto grammar = builder.Get();
    GrammarFSMBuilder::Apply(&grammar);
    grammar->optimized = true;
    std::cout << "Checking expression " << target << std::endl;

    EarleyParser lookahead(grammar, ParserState(-1, sequence, 0, -1, 0));
    if (lookahead.IsCompleted() || lookahead.Advance('x') ||
        !lookahead.Advance('b') || !lookahead.IsCompleted()) {
      throw std::runtime_error("Lookahead acceptance changed");
    }
    EarleyParser root(grammar, ParserState::GetInvalidState());
    if (!root.Advance('b') || !root.IsCompleted()) {
      throw std::runtime_error("Root rejected a valid string");
    }
    root.Reset();
    if (root.Advance('x') || !root.Advance('b') || !root.IsCompleted()) {
      throw std::runtime_error("Reset changed acceptance");
    }
  }
  // A per-rule view must retain its actual terminal states, not a bitmap over
  // every state in the fused grammar. Check both a small and a pressure case,
  // while keeping the same accepted/rejected language.
  for (int32_t count : {256, 4096}) {
    GrammarBuilder builder;
    const auto literal = builder.AddByteString("b");
    const auto sequence = builder.AddSequence({literal});
    std::vector<int32_t> alternatives;
    for (int32_t i = 0; i < count; ++i) {
      auto rule = builder.AddRule("leaf_" + std::to_string(i), builder.AddChoices({sequence}));
      alternatives.push_back(builder.AddSequence({builder.AddRuleRef(rule)}));
    }
    builder.AddRule("root", builder.AddChoices(alternatives));
    auto grammar = builder.Get();
    GrammarFSMBuilder::Apply(&grammar);
    grammar->optimized = true;
    size_t views = 0, retained_ends = 0;
    for (const auto& view : grammar->per_rule_fsms) {
      if (!view) continue;
      ++views;
      const auto& fsm = view->GetFsm();
      retained_ends += fsm.GetEnds().size();
      for (auto end : fsm.GetEnds()) {
        if (!fsm.IsEndState(end)) throw std::runtime_error("Lost terminal state");
      }
    }
    if (views < static_cast<size_t>(count) || retained_ends > views * 3) {
      throw std::runtime_error("Per-rule terminal storage grew with the complete FSM");
    }
    EarleyParser parser(grammar, ParserState::GetInvalidState());
    if (parser.Advance('x') || !parser.Advance('b') || !parser.IsCompleted()) {
      throw std::runtime_error("Sparse terminal storage changed acceptance");
    }
    std::cout << "Sparse views=" << views << " terminal ids=" << retained_ends << std::endl;
  }
  for (int32_t count : {128, 2048}) {
    GrammarBuilder builder;
    auto unit = builder.AddRule("unit", builder.AddChoices({
        builder.AddSequence({builder.AddByteString("b")})}));
    std::vector<int32_t> alternatives;
    for (int32_t i = 0; i < count; ++i) {
      auto body = builder.AddSequence({builder.AddRepeat(unit, 1, 4)});
      auto leaf = builder.AddRule("bounded_" + std::to_string(i), builder.AddChoices({body}));
      alternatives.push_back(builder.AddSequence({builder.AddRuleRef(leaf)}));
    }
    builder.AddRule("root", builder.AddChoices(alternatives));
    auto source = builder.Get();
    auto grammar = RepetitionRangeExpander::Apply(source);
    if (grammar->NumRules() > source->NumRules() + 16) {
      throw std::runtime_error("Identical repetition gained a chain per occurrence");
    }
    GrammarFSMBuilder::Apply(&grammar);
    grammar->optimized = true;
    for (int length : {0, 1, 2, 4, 5}) {
      EarleyParser parser(grammar, ParserState::GetInvalidState());
      bool accepted = true;
      for (int i = 0; i < length && accepted; ++i) accepted = parser.Advance('b');
      accepted = accepted && parser.IsCompleted();
      if (accepted != (length >= 1 && length <= 4)) {
        throw std::runtime_error("Shared repetition changed its bounds");
      }
    }
    std::cout << "Repeated bounds=" << count << " added rules="
              << grammar->NumRules() - source->NumRules() << std::endl;
  }
}

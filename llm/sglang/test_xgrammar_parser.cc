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
}

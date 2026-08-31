"""Static function-word inventory used to suppress non-entity query windows.

The canonical source is the unversioned Snowball English stop list, vendored as
the 2026-08-31 snapshot from https://snowballstem.org/algorithms/english/stop.txt.
The upstream page documents one word per non-comment line; its compound forms
are retained here and tokenized with the linker's Unicode token rule.  This
module deliberately has no runtime dependency or download.

Some Snowball-commented homonym/modals are a thesis query policy, not canonical
Snowball entries. Exact aliases resolve before this inventory is consulted, and
the inventory is only used to discard semantic uncovered windows, so legitimate
aliases with function-word spellings remain available to exact matching.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Snowball English stop list, canonical unversioned source snapshot (2026-08-31).
SNOWBALL_ENGLISH_STOPWORDS = frozenset(
    """
    i me my myself we our ours ourselves you your yours yourself yourselves
    he him his himself she her hers herself it its itself they them their theirs themselves
    what which who whom this that these those
    am is are was were be been being have has had having do does did doing
    would should could ought
    i'm you're he's she's it's we're they're i've you've we've they've
    i'd you'd he'd she'd we'd they'd i'll you'll he'll she'll we'll they'll
    isn't aren't wasn't weren't hasn't haven't hadn't doesn't don't didn't
    won't wouldn't shan't shouldn't can't cannot couldn't mustn't
    let's that's who's what's here's there's when's where's why's how's
    a an the
    and but if or because as until while
    of at by for with about against between into through during before after above below
    to from up down in out on off over under again further then once
    here there when where why how
    all any both each few more most other some such
    no nor not only own same so than too very
    """.split()
)

# Thesis-query request verbs are project policy, not additions to Snowball.
PROJECT_REQUEST_SCAFFOLDING = frozenset(
    {"please", "show", "list", "tell", "give", "get", "find", "provide", "display", "need"}
)

# Snowball documents these six as commented homonym/modal forms. The thesis
# suppresses them in semantic query scaffolding while preserving exact aliases.
THESIS_QUERY_AUXILIARIES = frozenset({"can", "may", "might", "must", "shall", "will"})

# The linker operates on Unicode word tokens, while Snowball records several
# apostrophe compounds.  Deriving tokens from the vendored finite source keeps
# the policy faithful to the source without treating contractions as content.
ENTITY_LINKER_FUNCTION_WORDS = (
    frozenset(token for phrase in SNOWBALL_ENGLISH_STOPWORDS for token in _TOKEN_RE.findall(phrase))
    | THESIS_QUERY_AUXILIARIES
    | PROJECT_REQUEST_SCAFFOLDING
)

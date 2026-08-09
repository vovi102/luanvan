# Entity Dictionary v0 Sources

Retrieved date: 2026-06-28

Manual verification: failed on 2026-08-09. A seed-42 sample found 7 provenance
errors in 50 rows (14%); see
`docs/research/entity-dictionary-manual-sample-2026-08-09.md`. This snapshot must
not be treated as Ethereum-only until its DefiLlama rows are rebuilt
chain-aware.

## Snapshot inputs

- CoinGecko Uniswap token list: `https://tokens.coingecko.com/uniswap/all.json`
  - Used for Ethereum token contract labels and addresses.
  - Committed rows: 3,200.
- DefiLlama protocols API: `https://api.llama.fi/protocols`
  - Used for protocol metadata, Ethereum addresses, category mapping, and top DeFi coverage selection.
  - Committed rows: 441.
- DefiLlama Adapters repository: `https://github.com/DefiLlama/DefiLlama-Adapters`
  - Used for exchange reserve addresses and centralized exchange coverage.
  - Committed rows: 879.

## Automated acceptance criteria

- `entities.json` contains at least 3,000 externally sourced Ethereum address entries.
- `aliases.json` contains at least 1,000 normalized aliases.
- `concepts.json` contains 8-12 concept categories.
- The committed coverage list includes top-30 exchange owners and top-50 DeFi protocol owners.
- Artifacts are structurally validated offline; live scraping is not required
  for CI. Chain provenance still requires pinned upstream evidence.

## Boundaries

- No fake, synthetic, or generated Ethereum addresses are accepted in committed artifacts.
- Ambiguous aliases that normalize to multiple owners are excluded from the global alias map while the underlying real-source entity rows remain in `entities.json`.
- Etherscan HTML label pages were not used as an automated source because the environment received a Cloudflare challenge during acquisition.
- Current DefiLlama rows were extracted without preserving adapter chain
  context. They may contain non-Ethereum addresses and must be remediated before
  downstream use.

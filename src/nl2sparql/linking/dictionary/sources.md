# Entity Dictionary v0 Sources

Retrieved date: 2026-08-09

Manual verification: passed on 2026-08-09. The independent seed-20260809 sample
passed 50/50 with zero critical and zero minor errors; see
`docs/research/entity-dictionary-manual-sample-remediated-2026-08-09.md`. The
failed seed-42 audit remains at
`docs/research/entity-dictionary-manual-sample-2026-08-09.md` as root-cause
evidence for this rebuild.

## Snapshot inputs

- CoinGecko Uniswap token list: `https://tokens.coingecko.com/uniswap/all.json`
  - Committed snapshot SHA-256:
    `ebe4a02621fb0774db2b96d84f5439498b365e97db83ca352493e3576d654eca`.
  - Only exact records with integer `chainId=1` are compiled.
  - Committed output rows: 5,064 after reviewed-address precedence.
- DefiLlama protocols API: `https://api.llama.fi/protocols`
  - Committed snapshot SHA-256:
    `be9cbab88c9cb9a68f26d6f8460186fe90939f71d75665b93df27c71885c5e0f`.
  - A row is accepted only when its exact address is unprefixed and its `chains`
    list contains `Ethereum`.
  - Committed output rows: 21.
- DefiLlama Adapters repository: `https://github.com/DefiLlama/DefiLlama-Adapters`
  - Pinned commit: `bbd74a89801e9729ea1a5076d80bc7d636520f4b`.
  - Every accepted row has a file-and-line locator with explicit Ethereum
    context; arbitrary adapter JavaScript is never executed.
  - Committed output rows: 49 (30 treasury, 13 operational, 6 token).
- Concrete vault API: `https://apy.api.concrete.xyz/v1/vault:tvl/all`
  - Committed snapshot SHA-256:
    `1747ebf245016afb85acbfa97cb24dabdb3873493b7039cd516181a20b5f5a45`.
  - One exact vault under JSON chain key `1` supplies Concrete coverage.

## Automated acceptance criteria

- `entities.json` contains at least 3,000 externally sourced Ethereum address entries.
- `aliases.json` contains at least 1,000 normalized aliases.
- `concepts.json` contains 8-12 concept categories.
- The committed coverage list includes top-30 exchange owners and top-50 DeFi protocol owners.
- All 5,135 entities have `chain_id=1`, a valid `address_role`, an immutable
  source revision, and a row-level locator.
- Artifacts are validated offline; live scraping is not required for CI.

## Boundaries

- No fake, synthetic, or generated Ethereum addresses are accepted in committed artifacts.
- Ambiguous aliases that normalize to multiple owners are excluded from the global alias map while the underlying real-source entity rows remain in `entities.json`.
- Etherscan HTML label pages were not used as an automated source because the environment received a Cloudflare challenge during acquisition.
- Address roles are semantic boundaries: `operational` is eligible for flow
  analysis, `token` is a token contract, and `treasury` is an exchange reserve or
  custody account. Token and treasury rows must not be sampled as operational
  protocol endpoints.

# T2.2 — Independent audit of the remediated entity dictionary

**Audit date:** 2026-08-09

**Conclusion:** Pass. All 50 sampled rows match immutable source evidence. The
sample has zero critical chain/address errors and zero minor metadata errors.

## Method

- Population: 5,135 records in the remediated `entities.json` at parent commit
  `23e8def`.
- Sampling: `random.Random(20260809).sample(range(5135), 50)`, without
  replacement. The seed differs from the failed seed-42 audit.
- Distribution: 49 `coingecko_token_list` rows and one
  `defillama_cex_adapter` row.
- CoinGecko pass condition: the pinned JSON locator contains the exact address
  and owner name and declares integer `chainId = 1`.
- DefiLlama adapter pass condition: the address occurs exactly at the pinned Git
  commit and row locator, and that evidence explicitly assigns it to Ethereum.
- The generated dictionary was not accepted as evidence for itself.

## Results

| # | Index | Address | Owner | Role | Source evidence | Verdict |
|---:|---:|---|---|---|---|---|
| 1 | 736 | `0xe86df1970055e9caee93dae9b7d5fd71595d0e18` | Bitcoin20 | token | CoinGecko `/tokens/1504`: exact name/address; `chainId=1` | Pass |
| 2 | 3115 | `0xf1b99e3e573a1a9c5e6b2ce818b617f0e664e86b` | Opyn Squeeth | token | CoinGecko `/tokens/544`: exact name/address; `chainId=1` | Pass |
| 3 | 232 | `0xa700b4eb416be35b2911fd5dee80678ff64ff6c9` | Aave v3 AAVE | token | CoinGecko `/tokens/1438`: exact name/address; `chainId=1` | Pass |
| 4 | 804 | `0xaf3a37e800991501b88dc4745a96cc8fc3d5cb52` | Bobina | token | CoinGecko `/tokens/2259`: exact name/address; `chainId=1` | Pass |
| 5 | 4049 | `0xa6422e3e219ee6d4c1b18895275fe43556fd50ed` | Stobox Token | token | CoinGecko `/tokens/1472`: exact name/address; `chainId=1` | Pass |
| 6 | 4057 | `0x011e55d2b28306458e37ca7e997c879bb25a455d` | Strata Junior USDat | token | CoinGecko `/tokens/4528`: exact name/address; `chainId=1` | Pass |
| 7 | 4262 | `0x60808f2a0d035e16f57e9043842bd1bfbda24fa2` | Thermo Fisher Scientific (Ondo Tokenized Stock) | token | CoinGecko `/tokens/2021`: exact name/address; `chainId=1` | Pass |
| 8 | 987 | `0xad5cdc3340904285b8159089974a99a1a09eb4c0` | Chevron xStock | token | CoinGecko `/tokens/4639`: exact name/address; `chainId=1` | Pass |
| 9 | 1683 | `0x410e7d6b6303e531753d4fbe3e50e35efbcff53c` | Forgent Power Solutions (Ondo Tokenized) | token | CoinGecko `/tokens/4406`: exact name/address; `chainId=1` | Pass |
| 10 | 2858 | `0xac51066d7bec65dc4589368da368b212745d63e8` | My Neighbor Alice | token | CoinGecko `/tokens/1835`: exact name/address; `chainId=1` | Pass |
| 11 | 2916 | `0xd2a08ff5f31d2f2d70c91960323c2ed31268ae25` | Neos.ai | token | CoinGecko `/tokens/442`: exact name/address; `chainId=1` | Pass |
| 12 | 1578 | `0x6d44ddba07a9373d665ce636f639e1c46565a349` | FOMO | token | CoinGecko `/tokens/2204`: exact name/address; `chainId=1` | Pass |
| 13 | 3178 | `0x7ad16874759348f04b6b6119463d66c07ae54899` | PIRB | token | CoinGecko `/tokens/1075`: exact name/address; `chainId=1` | Pass |
| 14 | 852 | `0x086f405146ce90135750bbec9a063a8b20a8bffb` | Brevis | token | CoinGecko `/tokens/2730`: exact name/address; `chainId=1` | Pass |
| 15 | 2897 | `0x6967b9a8c0b14849cfe8f9e5732b401433fd2898` | Naka Go | token | CoinGecko `/tokens/2118`: exact name/address; `chainId=1` | Pass |
| 16 | 1272 | `0x420658a1d8b8f5c36ddaf1bb828f347ba9011969` | Degen Arena | token | CoinGecko `/tokens/200`: exact name/address; `chainId=1` | Pass |
| 17 | 2577 | `0x33a4bcb4e941dd13439a8f4f723580927c6d9800` | MOTHER VEGETABLE Token | token | CoinGecko `/tokens/1393`: exact name/address; `chainId=1` | Pass |
| 18 | 4283 | `0xf19308f923582a6f7c465e5ce7a9dc1bec6665b1` | TitanX | token | CoinGecko `/tokens/1960`: exact name/address; `chainId=1` | Pass |
| 19 | 334 | `0x5aa7b9be58d4001a7065718641ce7b121b41ef9b` | AlphPad | token | CoinGecko `/tokens/4686`: exact name/address; `chainId=1` | Pass |
| 20 | 1438 | `0xbca703c64f616a17b4f2763f34f93400dbe20f17` | Eaton Corporation plc xStock | token | CoinGecko `/tokens/3173`: exact name/address; `chainId=1` | Pass |
| 21 | 4186 | `0x5483dc6abda5f094865120b2d251b5744fc2ecb5` | TaoPad | token | CoinGecko `/tokens/1727`: exact name/address; `chainId=1` | Pass |
| 22 | 2287 | `0x471d113059324321749e097705197a2b44a070fc` | Kanga Exchange | token | CoinGecko `/tokens/101`: exact name/address; `chainId=1` | Pass |
| 23 | 2158 | `0xcefa48c12a7a41076771f367cbab4b5fcba82e35` | Interactive Brokers Group (Dinari Tokenized Stock) | token | CoinGecko `/tokens/3935`: exact name/address; `chainId=1` | Pass |
| 24 | 3432 | `0xc07e1300dc138601fa6b0b59f8d0fa477e690589` | Quack AI | token | CoinGecko `/tokens/3072`: exact name/address; `chainId=1` | Pass |
| 25 | 1713 | `0x23fa3aa82858e7ad1f0f04352f4bb7f5e1bbfb68` | Frictionless | token | CoinGecko `/tokens/1900`: exact name/address; `chainId=1` | Pass |
| 26 | 4970 | `0x7743e50f534a7f9f1791dde7dcd89f7783eefc39` | f(x) USD Saving | token | CoinGecko `/tokens/2428`: exact name/address; `chainId=1` | Pass |
| 27 | 571 | `0x1c95b093d6c236d3ef7c796fe33f9cc6b8606714` | BOMB | token | CoinGecko `/tokens/240`: exact name/address; `chainId=1` | Pass |
| 28 | 1734 | `0x5ce215d9c37a195df88e294a06b8396c296b4e15` | Futu Holdings (Ondo Tokenized Stock) | token | CoinGecko `/tokens/2487`: exact name/address; `chainId=1` | Pass |
| 29 | 1742 | `0xcf67815cce72e682eb4429eca46843bed81ca739` | GAM3S.GG | token | CoinGecko `/tokens/4843`: exact name/address; `chainId=1` | Pass |
| 30 | 2678 | `0x1f38d22f4ec3479c8268c85476b9418716bdb115` | Meh | token | CoinGecko `/tokens/4084`: exact name/address; `chainId=1` | Pass |
| 31 | 1991 | `0x292fcdd1b104de5a00250febba9bc6a5092a0076` | HashAI | token | CoinGecko `/tokens/4174`: exact name/address; `chainId=1` | Pass |
| 32 | 4018 | `0x8e6cd950ad6ba651f6dd608dc70e5886b1aa6b24` | StarLink | token | CoinGecko `/tokens/3153`: exact name/address; `chainId=1` | Pass |
| 33 | 4293 | `0x27f6c8289550fce67f6b50bed1f519966afe5287` | Tokenised GBP | token | CoinGecko `/tokens/2023`: exact name/address; `chainId=1` | Pass |
| 34 | 2925 | `0x8e95a7d99812190bf9691c1df0eef3405165e0fe` | Nest Bybit Vault 1 | token | CoinGecko `/tokens/4969`: exact name/address; `chainId=1` | Pass |
| 35 | 2966 | `0xe831f96a7a1dce1aa2eb760b1e296c6a74caa9d5` | Nexum | token | CoinGecko `/tokens/1308`: exact name/address; `chainId=1` | Pass |
| 36 | 1959 | `0xf5581dfefd8fb0e4aec526be659cfab1f8c781da` | HOPR | token | CoinGecko `/tokens/303`: exact name/address; `chainId=1` | Pass |
| 37 | 4336 | `0xaf75d880b3128981d1fed3292fc02e3fb37acd53` | TruthGPT | token | CoinGecko `/tokens/1476`: exact name/address; `chainId=1` | Pass |
| 38 | 1764 | `0x79d464248516bc6977ca2069ba15d8d1044479d8` | GPUnet | token | CoinGecko `/tokens/92`: exact name/address; `chainId=1` | Pass |
| 39 | 589 | `0xbabe3ce7835665464228df00b03246115c30730a` | Baby Neiro Token | token | CoinGecko `/tokens/1330`: exact name/address; `chainId=1` | Pass |
| 40 | 268 | `0x03183ce31b1656b72a55fa6056e287f50c35bbeb` | Accenture xStock | token | CoinGecko `/tokens/4983`: exact name/address; `chainId=1` | Pass |
| 41 | 683 | `0xf17e65822b568b3903685a7c9f496cf7656cc6c2` | Biconomy | token | CoinGecko `/tokens/3319`: exact name/address; `chainId=1` | Pass |
| 42 | 21 | `0x187e3534f461d7c59a7d6899a983a5305b48f93f` | CoinEx | treasury | DefiLlama commit `bbd74a8`, `projects/coinex/index.js:L6-L8`: exact address in `ethereum` owners | Pass |
| 43 | 1795 | `0xd567b5f02b9073ad3a982a099a23bf019ff11d1c` | Gamestarter | token | CoinGecko `/tokens/2196`: exact name/address; `chainId=1` | Pass |
| 44 | 574 | `0x2a7f6a311cf835ebb16b7e954b8aacbb61ea149e` | BORNE | token | CoinGecko `/tokens/4922`: exact name/address; `chainId=1` | Pass |
| 45 | 3686 | `0x6d7497751656618fc38cfb5478994a20f7e235df` | SPYRO | token | CoinGecko `/tokens/1309`: exact name/address; `chainId=1` | Pass |
| 46 | 1526 | `0x4c93b9fbf7fd1777ccbcbc538b1d0a8b58fb1ad6` | Ethereum STRATO | token | CoinGecko `/tokens/4487`: exact name/address; `chainId=1` | Pass |
| 47 | 1358 | `0x4955f6641bf9c8c163604c321f4b36e988698f75` | Dogecast | token | CoinGecko `/tokens/77`: exact name/address; `chainId=1` | Pass |
| 48 | 2032 | `0x74b1af114274335598da72f5c6ed7b954a016eed` | HitBTC | token | CoinGecko `/tokens/658`: exact name/address; `chainId=1` | Pass |
| 49 | 4356 | `0x5aa158404fed6b4730c13f49d3a7f820e14a636f` | ULTRON | token | CoinGecko `/tokens/1126`: exact name/address; `chainId=1` | Pass |
| 50 | 5094 | `0x08efcc2f3e61185d0ea7f8830b3fec9bfa2ee313` | sNUSD | token | CoinGecko `/tokens/159`: exact name/address; `chainId=1` | Pass |

## Acceptance evaluation

- Critical chain/address errors: 0/50.
- Minor metadata errors: 0/50.
- Result: pass under the approved threshold of zero critical errors and at most
  one minor metadata error.

## Limitations

- The random sample is dominated by CoinGecko because token rows are 99.1% of
  the population. The separate reviewed-manifest verification checked all 71
  CEX/protocol rows against their pinned locators before artifact generation.
- Source attribution establishes the published source claim, not legal ownership
  or private-key control.
- Only 14 protocol rows are currently marked `operational`; downstream flow
  queries must not treat the larger `token` population as protocol endpoints.


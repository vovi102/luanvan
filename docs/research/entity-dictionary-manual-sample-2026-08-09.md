# T2.2 — Manual source audit cho 50 dictionary entries

**Ngày kiểm tra:** 2026-08-09

**Kết luận:** Fail acceptance. Sample có 43 pass và 7 fail; error rate 14%.
Các lỗi đều liên quan tới chain provenance, không phải typo label nhỏ.

## Phương pháp

- Population: 4.520 records trong
  `src/nl2sparql/linking/dictionary/entities.json` tại commit parent `b78fda8`.
- Sampling: `random.Random(42).sample(range(4520), 50)`, không thay thế.
- Phân bố sample: 30 `coingecko_token_list`, 15 `defillama_adapters`, 5
  `defillama_protocols`.
- CoinGecko: chỉ pass khi current token list chứa exact address, exact token name
  và `chainId = 1`.
- DefiLlama: chỉ pass khi exact address nằm trong chain section `ethereum` của
  owner/protocol tương ứng. Việc address xuất hiện ở chain khác không đủ.
- Source snapshot nội bộ không được dùng để tự chứng minh chính nó; mọi verdict
  dựa trên payload/link primary source.

## Kết quả tổng hợp

| Source | Pass | Fail | Error rate |
|---|---:|---:|---:|
| CoinGecko Uniswap token list | 30 | 0 | 0% |
| DefiLlama CEX adapters | 13 | 2 | 13,33% |
| DefiLlama protocol adapters | 0 | 5 | 100% |
| **Tổng** | **43** | **7** | **14%** |

## Audit từng entry

| # | Index | Address | Expected label / owner / category | Primary source | Observed evidence | Verdict |
|---:|---:|---|---|---|---|---|
| 1 | 912 | `0x5509be53b2dd0cd6fb8473b0eda94e0a3059b73a` | `SwissBorg: reserve wallet 0038` / `SwissBorg` / `exchange` | [SwissBorg adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/swissborg.js) | Address chỉ nằm trong section `arbitrum`. | **Fail** |
| 2 | 204 | `0xbcf6011192399df75a96b0a4ce47c4820853e9e5` | `Bitget: reserve wallet 0018` / `Bitget` / `exchange` | [Bitget adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/bitget/index.js) | Address nằm trong section `bsc`, không phải `ethereum`. | **Fail** |
| 3 | 2253 | `0xc53d2e7321ab83b28af2360559aa303676a23f98` | `Franklin US Large Cap Multifactor Index ETF (Ondo Tokenized) (FLQLON) token contract` / `Franklin US Large Cap Multifactor Index ETF (Ondo Tokenized)` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 4 | 2006 | `0x246908bff0b1ba6ecadcf57fb94f6ae2fcd43a77` | `Divi (DIVI) token contract` / `Divi` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 5 | 1828 | `0x1db1afd9552eeb28e2e36597082440598b7f1320` | `Constellation Staked RPL (XRPL) token contract` / `Constellation Staked RPL` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 6 | 1143 | `0x6be2425c381eb034045b527780d2bf4e21ab7236` | `Kelp: protocol address 0006` / `Kelp` / `staking` | [Kelp official repository](https://github.com/Kelp-DAO/LRT-rsETH#bridged-rseth) | Official table identifies this as zkSync rsETH. | **Fail** |
| 7 | 839 | `0x8a2bd0e455d24d8c7a9f15ffd902dc74b961bac6` | `OSL HK: reserve wallet 0045` / `OSL HK` / `exchange` | [OSL HK adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/osl-hk.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 8 | 4467 | `0x847deb9c78fb00319bc7a006dff729c11428e537` | `lululemon xStock (LULUX) token contract` / `lululemon xStock` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 9 | 712 | `0x7ab6c736baf1dac266aab43884d82974a9adcccf` | `Nexo: reserve wallet 0010` / `Nexo` / `exchange` | [Nexo adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/nexo-cex.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 10 | 3456 | `0xbe40491f3261fd42724f1aeb465796eb11c06ddf` | `Re7 FRAX (RE7FRAX) token contract` / `Re7 FRAX` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 11 | 260 | `0x81e091afff917fc1aaad86a47c0c5b508927d186` | `Bitkub: reserve wallet 0041` / `Bitkub` / `exchange` | [Bitkub adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/bitkub-cex.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 12 | 244 | `0x3fefacc8aa963b20524d8cf9719931723de8dcfe` | `Bitkub: reserve wallet 0013` / `Bitkub` / `exchange` | [Bitkub adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/bitkub-cex.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 13 | 767 | `0xa2684f75740cfff46c29bae79a4ecc43043c003d` | `OKX: reserve wallet 0076` / `OKX` / `exchange` | [OKX adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/okex/index.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 14 | 1791 | `0xa95837130bcbc0ad99e188e22f674e4ec6925be2` | `Cleveland-Cliffs (Ondo Tokenized) (CLFON) token contract` / `Cleveland-Cliffs (Ondo Tokenized)` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 15 | 1905 | `0xb40865a6ed718f57468cd3f4f60825a130b89a51` | `DESU (DESU) token contract` / `DESU` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 16 | 4139 | `0x8f3470a7388c05ee4e7af3d01d8c722b0ff52374` | `Veritaseum (VERI) token contract` / `Veritaseum` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 17 | 217 | `0xec96bbbe895301710a89a06546264ebb4f0cc546` | `Bitget: reserve wallet 0065` / `Bitget` / `exchange` | [Bitget adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/bitget/index.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 18 | 1628 | `0x50038be55be5b964cfa32cf128b5cf05f123959f` | `BlackRock BUIDL: protocol address 0008` / `BlackRock BUIDL` / `token_contract` | [Securitize adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/securitize/index.js) | Đây là 40 ký tự đầu của Aptos resource address dài hơn, không phải Ethereum address trong source. | **Fail** |
| 19 | 4464 | `0x2b47c128b35dddcb66ce2fa5b33c95314a7de245` | `kpk USDC RWA Euler Vault (Ethereum) (KPK_RWA_USDC) token contract` / `kpk USDC RWA Euler Vault (Ethereum)` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 20 | 3436 | `0xa1d6df714f91debf4e0802a542e13067f31b8262` | `RFOX (RFOX) token contract` / `RFOX` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 21 | 1805 | `0x081f67afa0ccf8c7b17540767bbe95df2ba8d97f` | `CoinEx (CET) token contract` / `CoinEx` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 22 | 3679 | `0x61dbbbb552dc893ab3aad09f289f811e67cef285` | `Skate (SKATE) token contract` / `Skate` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 23 | 2278 | `0xa043fdc5a6e2e381e3532d5a97404b82fb7a0af8` | `GE Vernova (Ondo Tokenized) (GEVON) token contract` / `GE Vernova (Ondo Tokenized)` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 24 | 53 | `0xdbfefd2e8460a6ee4955a68582f85708baea60a3` | `Curve DEX: protocol address 0006` / `Curve DEX` / `dex` | [Curve adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/curve/index.js) | Address được khai báo dưới `base`, không phải `ethereum`. | **Fail** |
| 25 | 1307 | `0x8a458a9dc9048e005d22849f470891b840296619` | `Aave v3 MKR (AMKR) token contract` / `Aave v3 MKR` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 26 | 3462 | `0xa02f5e93f783baf150aa1f8b341ae90fe0a772f7` | `Re7 cbBTC (RE7CBBTC) token contract` / `Re7 cbBTC` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 27 | 2787 | `0x8e7bd91f7d51d58145365341fdb37e0edfc8397f` | `MAGA PEPE (ETH) (MAGAPEPE) token contract` / `MAGA PEPE (ETH)` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 28 | 2276 | `0xc3d2b3e23855001508e460a6dbe9f9e3116201af` | `GATEWAY TO MARS (MARS) token contract` / `GATEWAY TO MARS` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 29 | 1273 | `0xc713e5e149d5d0715dcd1c156a020976e7e56b88` | `Aave MKR (AMKR) token contract` / `Aave MKR` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 30 | 1763 | `0xe737f948bdfe3beae9423292853ec0579173cebb` | `Charles Schwab (Ondo Tokenized Stock) (SCHWON) token contract` / `Charles Schwab (Ondo Tokenized Stock)` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 31 | 2757 | `0xc64500dd7b0f1794807e67802f8abbf5f8ffb054` | `Locus Chain (LOCUS) token contract` / `Locus Chain` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 32 | 837 | `0x8627890ccbadba4800753ba130e110c86522f2a8` | `OSL HK: reserve wallet 0073` / `OSL HK` / `exchange` | [OSL HK adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/osl-hk.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 33 | 759 | `0x868dab0b8e21ec0a48b726a1ccf25826c78c6d7f` | `OKX: reserve wallet 0031` / `OKX` / `exchange` | [OKX adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/okex/index.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 34 | 3112 | `0x1f57da732a77636d913c9a75d685b26cc85dcc3a` | `OPENLOOT (OL) token contract` / `OPENLOOT` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 35 | 792 | `0xde01974fb4a98bafd7cbf8a06ecf6dcc94d7283f` | `OKX: reserve wallet 0069` / `OKX` / `exchange` | [OKX adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/okex/index.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 36 | 2940 | `0x6b4c7a5e3f0b99fcd83e9c089bddd6c7fce5c611` | `Million (MM) token contract` / `Million` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 37 | 2817 | `0x33a4bcb4e941dd13439a8f4f723580927c6d9800` | `MOTHER VEGETABLE Token (MVT) token contract` / `MOTHER VEGETABLE Token` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 38 | 2166 | `0x26827f7f51769ea21f94ba98ba64f5d0dc8988f9` | `FAME- Rumble Kong League ($FAME) token contract` / `FAME- Rumble Kong League` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 39 | 355 | `0x6f4565c9d673dbdd379aba0b13f8088d1af3bb0c` | `Bybit: reserve wallet 0011` / `Bybit` / `exchange` | [Bybit adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/bybit.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 40 | 3763 | `0x99f70a0e1786402a6796c6b0aa997ef340a5c6da` | `Spiko: protocol address 0004` / `Spiko` / `token_contract` | [Spiko adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/spiko/index.js) | Address chỉ nằm trong `polygon`/`arbitrum` arrays. | **Fail** |
| 41 | 4392 | `0xf587f2e8aff7d76618d3b6b4626621860fbd54e3` | `cbBTC Core Morpho Vault (GTCBBTCC) token contract` / `cbBTC Core Morpho Vault` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 42 | 1022 | `0x2bdc204b6d192921605c66b7260cfef7be34eb2e` | `Avalon USDa: protocol address 0008` / `Avalon USDa` / `lending` | [Avalon adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/avalon-finance-usda/index.js) | Address nằm trong config `mantle`, không phải `ethereum`. | **Fail** |
| 43 | 3100 | `0x744030ad4e6c10faf5483b62473d88a254d62261` | `NuLink (NLK) token contract` / `NuLink` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 44 | 645 | `0xa152f8bb749c55e9943a3a0a3111d18ee2b3f94e` | `KuCoin: reserve wallet 0015` / `KuCoin` / `exchange` | [KuCoin adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/kucoin/index.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 45 | 2401 | `0x6942806d1b2d5886d95ce2f04314ece8eb825833` | `Groyper (GROYPER) token contract` / `Groyper` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 46 | 2962 | `0x468eabcb5c914ac59e72691f8fc970880a94f4b3` | `Modulr (EMDR) token contract` / `Modulr` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 47 | 1575 | `0x2791bfd60d232150bff86b39b7146c0eaaa2ba81` | `BiFi (BIFI) token contract` / `BiFi` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |
| 48 | 569 | `0x3c02290922a3618a4646e3bbca65853ea45fe7c6` | `Indodax: reserve wallet 0006` / `Indodax` / `exchange` | [Indodax adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/indodax.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 49 | 375 | `0xa4b9569bf942c3aad23c0c2d322fe4aff8e1bf30` | `Bybit: reserve wallet 0080` / `Bybit` / `exchange` | [Bybit adapter](https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/cex/bybit.js) | Address nằm trong `ethereum` owners. | **Pass** |
| 50 | 1866 | `0xad5fdc8c3c18d50315331fca7f66efe5033f6c4c` | `Crazy Frog Coin (CRAZY) token contract` / `Crazy Frog Coin` / `token_contract` | [CoinGecko list](https://tokens.coingecko.com/uniswap/all.json) | Exact address/name; `chainId=1`. | **Pass** |

## Root cause và remediation

Các `defillama_protocols`/`defillama_adapters` rows đã được tạo bằng cách nhận
diện chuỗi giống EVM address mà không giữ chain context của adapter. Cách này có
thể lấy address từ Base, BSC, Arbitrum, Polygon, Mantle, zkSync hoặc cắt 40 hex
characters đầu của Aptos resource address. Source URL CEX cũ
`.registries/cex/index.js` cũng đã stale và không trỏ tới evidence row-level.

T2.2 không được mark done trước khi:

1. Rebuild DefiLlama records bằng parser chain-aware, chỉ nhận explicit
   `ethereum` sections và reject non-EVM identifiers/truncated matches.
2. Ghi source URL trực tiếp tới owner/protocol adapter và pin commit SHA hoặc
   retrieval snapshot.
3. Regenerate dictionary/aliases/concepts, chạy lại automated tests và lấy một
   sample 50 mới độc lập để manual audit.

## Limitations

- Audit kiểm tra provenance/address/owner/category, không chứng minh private-key
  control hoặc accuracy của mọi exchange attribution ngoài claim của source.
- URL `main` có thể thay đổi sau ngày audit; remediation phải pin commit SHA.
- Kết luận chỉ áp dụng cho sample seed 42, nhưng lỗi hệ thống đủ để bác bỏ
  acceptance hiện tại dù chưa ước lượng chính xác toàn-population error rate.

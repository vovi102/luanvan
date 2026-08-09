# T2.2 — Entity Dictionary v0 (≥3000 entries)

## Mục tiêu

Xây hierarchical entity dictionary 2 tầng (concept-level + instance-level) chứa ≥3000 địa chỉ Ethereum có nhãn, dùng cho Entity Linker (Phase 4).

## Bối cảnh & lý do

Đặc thù blockchain: **một thực thể (Binance) có thể có ~30 địa chỉ ví khác nhau** (hot/cold/deposit). Entity Linker cần dictionary để map "Binance" → set of addresses, "Tornado Cash" → contract addresses.

Đây là **Đóng góp 2.1 + 2.3** (multi-address-one-entity + class-level resolution).

## Phụ thuộc

- (không có cứng — có thể làm song song với T2.1 và T2.3)

## Đầu vào

- Etherscan tag cloud: https://etherscan.io/labelcloud
- Dune Analytics labels (qua dune.com search hoặc community datasets).
- Arkham Intelligence (free tier, có rate limit).
- Crypto Twitter / DeFi Llama (DEX protocols list).

## Đầu ra

- File `src/nl2sparql/linking/dictionary/entities.json` — main dictionary (instance-level).
- File `src/nl2sparql/linking/dictionary/concepts.json` — class-level dictionary.
- File `src/nl2sparql/linking/dictionary/aliases.json` — alias map.
- File `src/nl2sparql/linking/dictionary/sources.md` — note nguồn + ngày extract (cho reproducibility).
- Notebook `notebooks/05_dict_eda.ipynb` — phân tích phân bố.

## Acceptance criteria

- [x] `entities.json` có ≥3000 entries (mục tiêu 5000).
- [x] Mỗi entry có format chuẩn (xem dưới).
- [x] Sample 50 entries verify thủ công không có sai sót lớn.
- [x] Cover top-30 exchange + top-50 DeFi protocol.
- [x] `concepts.json` có 8-12 concept (exchange, mixer, DEX, lending, NFT marketplace, ...).
- [x] `aliases.json` cover ≥1000 alias mapping.

## Hướng dẫn triển khai

1. **Format `entities.json`:**
   ```json
   [
     {
       "address": "0x28C6c06298d514Db089934071355E5743bf21d60",
       "primary_label": "Binance: Hot Wallet 14",
       "owner": "Binance",
       "category": "exchange",
       "concept_class": "ExchangeAccount",
       "aliases": ["Binance 14", "Binance Hot 14"],
       "source": "etherscan",
       "verified_date": "2025-XX-XX",
       "confidence": "high"
     },
     ...
   ]
   ```

2. **Format `concepts.json`:**
   ```json
   {
     "exchange": {
       "ontology_class": "https://thesis.example.org/eth-kg/ExchangeAccount",
       "aliases": ["exchange", "CEX", "centralized exchange", "exchange wallet"],
       "instances": ["Binance", "Coinbase", "Kraken", "OKX", "..."]
     },
     "mixer": {
       "ontology_class": "https://thesis.example.org/eth-kg/MixerAccount",
       "aliases": ["mixer", "tumbler", "privacy tool"],
       "instances": ["Tornado Cash", "..."]
     },
     "DEX": {
       "ontology_class": "https://thesis.example.org/eth-kg/DEXProtocol",
       "aliases": ["DEX", "AMM", "decentralized exchange", "swap"],
       "instances": ["Uniswap V2", "Uniswap V3", "Curve", "SushiSwap", "Balancer", "..."]
     }
   }
   ```

3. **Format `aliases.json`:**
   ```json
   {
     "binance": "Binance",
     "binance hot wallet": "Binance",
     "tornado": "Tornado Cash",
     "tornado.cash": "Tornado Cash",
     "tc": "Tornado Cash",
     "the mixer": "Tornado Cash",
     "uni": "Uniswap V2",
     "uniswap": "Uniswap V2",
     "uniswap v3": "Uniswap V3"
   }
   ```

4. **Source 1 — Etherscan label cloud:**
   - Crawl danh sách label tags từ https://etherscan.io/labelcloud (pagination).
   - Mỗi tag có link đến danh sách address. Crawl các address có nhãn.
   - **Cẩn thận rate limit** — sleep 1-2s/request, identify yourself bằng User-Agent.
   - Tool đề xuất: `requests + BeautifulSoup`, hoặc `playwright` nếu page render JS.

5. **Source 2 — Dune Analytics:**
   - Có nhiều public dashboard với "Ethereum addresses by category".
   - API key Dune free tier rate-limited; bulk scrape từ public CSV exports thường đủ.
   - Search query: `address`, `label`, `entity` trên Dune.

6. **Source 3 — DeFiLlama protocols:**
   - https://defillama.com/protocols → mỗi protocol có "Address" link.
   - Scrape (rate-limited) hoặc dùng API: https://api.llama.fi/protocols.

7. **Build hierarchical structure:**
   - Mỗi entry có `concept_class` (exchange/mixer/DEX/lending/...).
   - Mỗi concept có list các `owner` (Binance, Coinbase, ...).
   - Mỗi `owner` có nhiều địa chỉ (entries).

8. **Generate aliases:**
   - Lower-case version của primary_label.
   - Nickname phổ biến (Twitter handle, ticker symbol).
   - Acronym (Tornado Cash → TC, "the mixer").
   - Cẩn thận ambiguity: "ETH" có thể là token hoặc Ethereum mainnet → KHÔNG đưa vào alias (resolve qua context).

9. **Verify thủ công 50 entries:**
   - Random sample.
   - Check Etherscan từng địa chỉ → label thật khớp với primary_label?
   - Note tỷ lệ lỗi vào `sources.md`.

10. **EDA notebook:**
    - Distribution theo category.
    - Top 20 owners by số address.
    - Phân bố alias count per entity.

## Rủi ro & note

- **Etherscan TOS:** scraping cần check ToS. Cá nhân research thường OK; commercial cần API key paid. → đề tài research → thận trọng mức độ "tôn trọng rate limit + cite source".
- **Long tail:** top 10 entity chiếm 80% tx; tail có ít alias, ít chính xác. **Test set Phase 3 nên stratified** (head/torso/tail).
- **Address checksum:** Ethereum address case-sensitive (EIP-55). Lưu cả 2 dạng: lowercase (cho match) + checksum (cho display).
- **"Verified"** trên Etherscan ≠ verified entity. Verified contract = source code public, không phải owner chính xác.
- **Nguồn không đồng bộ:** Etherscan có thể call "Binance: Hot Wallet 14" trong khi Dune call "Binance 14". Pipeline cần normalize.

## Estimated effort

3-5 ngày (đa phần là crawl + verify).

## Trạng thái

`done — chain-aware snapshot accepted`

Snapshot đã được rebuild fail-closed với `chain_id=1`, address role và immutable
row-level provenance. Independent audit seed `20260809` pass 50/50; historical
seed-42 failure được giữ lại làm root-cause evidence.

## Evidence — 2026-08-09 Chain-Aware Remediation

- Report:
  `docs/research/entity-dictionary-manual-sample-remediated-2026-08-09.md`.
- Sample: 50/5.135 records, `random.Random(20260809)`, không thay thế.
- Kết quả: 50 pass, 0 critical errors, 0 minor errors.
- Counts: 5.135 entities, 8.538 aliases, 10 concepts.
- Roles: 5.091 `token`, 30 `treasury`, 14 `operational`.
- Sources: 5.064 CoinGecko, 21 DefiLlama protocols API, 49 pinned DefiLlama
  adapter rows và 1 pinned Concrete API row.
- Top-30 exchange đều có `treasury` row; top-50 DeFi owner coverage được giữ.
- Downstream flow queries chỉ được dùng 14 `operational` rows.
- Focused verification: `46 passed`.
- Full test suite: `182 passed` (342 upstream deprecation/user warnings).

## Evidence — 2026-08-09 Manual Audit

- Report: `docs/research/entity-dictionary-manual-sample-2026-08-09.md`.
- Sample: 50/4.520 records, `random.Random(42)`, không thay thế.
- Kết quả: 43 pass, 7 fail; error rate 14%.
- CoinGecko: 30/30 pass với exact name/address và `chainId=1`.
- DefiLlama CEX: 13/15 pass; 2 wrong-chain records.
- DefiLlama protocols: 0/5 pass; 4 wrong-chain records và 1 truncated Aptos
  resource address.
- Root cause: acquisition không giữ chain context khi nhận diện chuỗi giống EVM
  address; source URLs CEX không đủ row-level và đã stale.
- Required fix: rebuild DefiLlama rows chỉ từ explicit Ethereum sections, pin
  provenance, regenerate artifacts và audit sample mới.

## Evidence — 2026-06-28

- Snapshot counts:
  - `entities`: 4,520
  - `aliases`: 16,158
  - `concepts`: 10
- Category distribution:
  - `bridge`: 38
  - `dex`: 80
  - `exchange`: 879
  - `lending`: 100
  - `mev`: 35
  - `stablecoin`: 2
  - `staking`: 33
  - `token_contract`: 3,353
- Source distribution:
  - `coingecko_token_list`: 3,200 rows
  - `defillama_adapters`: 879 rows
  - `defillama_protocols`: 441 rows
- Focused verification:
  ```bash
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run pytest tests/unit/test_entity_dictionary_schema.py tests/unit/test_entity_dictionary_artifacts.py -q
  ```
  Result: `11 passed in 0.22s`.
- Notebook verification:
  ```bash
  JUPYTER_CONFIG_DIR=/tmp/t2-2-jupyter-config \
  JUPYTER_DATA_DIR=/tmp/t2-2-jupyter-data \
  JUPYTER_RUNTIME_DIR=/tmp/t2-2-jupyter-runtime \
  UV_CACHE_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-cache \
  UV_PYTHON_INSTALL_DIR=/home/khoavd/WORKSPACE/LuanVan/.uv-python \
  uv run jupyter nbconvert --to notebook --execute notebooks/05_dict_eda.ipynb \
    --output /tmp/t2-2-dict-eda-verified.ipynb \
    --ExecutePreprocessor.timeout=120
  ```
  Result: nbconvert exited `0` and wrote `/tmp/t2-2-dict-eda-verified.ipynb`.

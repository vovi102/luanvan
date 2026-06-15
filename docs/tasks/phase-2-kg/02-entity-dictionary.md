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

- [ ] `entities.json` có ≥3000 entries (mục tiêu 5000).
- [ ] Mỗi entry có format chuẩn (xem dưới).
- [ ] Sample 50 entries verify thủ công không có sai sót lớn.
- [ ] Cover top-30 exchange + top-50 DeFi protocol.
- [ ] `concepts.json` có 8-12 concept (exchange, mixer, DEX, lending, NFT marketplace, ...).
- [ ] `aliases.json` cover ≥1000 alias mapping.

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

`todo`

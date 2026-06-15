# T2.1 — Ontology Extension (EthOn + DeFi)

## Mục tiêu

Thiết kế ontology extension trên EthOn để cover các khái niệm cần cho thesis: ExchangeAccount, MixerAccount, DEXProtocol, LendingProtocol, TokenTransfer event. Tổng 15-20 class, ~30 property với documentation phong phú cho schema linker.

## Bối cảnh & lý do

EthOn cover transaction/block cơ bản, nhưng **không có** khái niệm DeFi và **không có** label semantic cho địa chỉ. Đây là gap thesis cần lấp.

**Property documentation phong phú là quan trọng** — schema linker (Phase 4) sẽ embed các trường `rdfs:comment` + `:synonyms` + `:exampleUsage` để match với câu hỏi.

## Phụ thuộc

- T1.1 — Đã hiểu EthOn cấu trúc.

## Đầu vào

- File `src/nl2sparql/kg/ontology/ethon-classes.md` và `ethon-properties.md` (từ T1.1).
- Tham khảo `docs/memory/03-ONTOLOGY_REFERENCE.md` cho định hướng.

## Đầu ra

- File `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl` chứa ontology extension.
- File `src/nl2sparql/kg/ontology/changelog.md` track version.
- File `src/nl2sparql/kg/ontology/competency-questions.md` chứa 30+ câu hỏi mẫu mà ontology phải support được.
- Update `docs/memory/03-ONTOLOGY_REFERENCE.md` với version cuối.

## Acceptance criteria

- [ ] File `.ttl` parse được bằng `rdflib`, không lỗi.
- [ ] Load vào Protégé không có inconsistency (chạy reasoner FaCT++ hoặc HermiT).
- [ ] Có ≥15 class, ≥25 property.
- [ ] **MỌI property có:** `rdfs:label`, `rdfs:comment` (≥2 câu), `:synonyms` (≥3 từ đồng nghĩa), `:exampleUsage`, `rdfs:domain`, `rdfs:range`.
- [ ] 30+ competency questions, mỗi câu có ghi class/property cần dùng.
- [ ] Cover được ≥80% trong 30 competency questions (~24 câu).

## Hướng dẫn triển khai

1. **Liệt kê competency questions trước** (`competency-questions.md`):
   - 10 câu trivial: count, list, filter (e.g. "transactions in January").
   - 10 câu medium: join 2 entity, group-by (e.g. "top 10 senders to Binance").
   - 10 câu hard: multi-hop, alias, class-level (e.g. "any major DEX that received ≥1000 ETH from a known mixer").
   - Mỗi câu liệt kê ontology element nó cần.

2. **Class hierarchy:**

   ```turtle
   # ---------- Account hierarchy ----------
   :Account a owl:Class ;
       rdfs:subClassOf ethon:Account ;
       rdfs:label "Ethereum Account (extended)" ;
       rdfs:comment "Any Ethereum account, with extended labels and category info." .

   :ExternallyOwnedAccount a owl:Class ;
       rdfs:subClassOf :Account ;
       rdfs:label "Externally Owned Account (EOA)" ;
       rdfs:comment "An account controlled by a private key (no code)." ;
       :synonyms "EOA, wallet, user account, externally owned address" .

   :ContractAccount a owl:Class ;
       rdfs:subClassOf :Account ;
       rdfs:label "Smart Contract Account" ;
       rdfs:comment "An account with deployed bytecode that executes on calls." ;
       :synonyms "contract, smart contract, deployed contract" .

   :ExchangeAccount a owl:Class ;
       rdfs:subClassOf :ExternallyOwnedAccount ;
       rdfs:label "Centralized Exchange Account" ;
       rdfs:comment "An account belonging to a centralized cryptocurrency exchange (CEX) such as Binance, Coinbase, or Kraken. Includes hot wallets, cold wallets, and deposit addresses." ;
       :synonyms "exchange, CEX, centralized exchange, exchange wallet, hot wallet" .

   :MixerAccount a owl:Class ;
       rdfs:subClassOf :ContractAccount ;
       rdfs:label "Mixer / Privacy Tool Contract" ;
       rdfs:comment "A smart contract that obfuscates transaction provenance, such as Tornado Cash. Often associated with privacy tools or money laundering." ;
       :synonyms "mixer, tumbler, privacy tool, anonymizer, Tornado Cash" .

   :DEXProtocol a owl:Class ;
       rdfs:subClassOf :ContractAccount ;
       rdfs:label "Decentralized Exchange Protocol" ;
       rdfs:comment "A smart contract enabling token swaps without a central intermediary. Examples: Uniswap V2/V3, Curve, SushiSwap, Balancer." ;
       :synonyms "DEX, AMM, decentralized exchange, swap protocol, liquidity pool" .

   :LendingProtocol a owl:Class ;
       rdfs:subClassOf :ContractAccount ;
       rdfs:label "Lending Protocol Contract" ;
       rdfs:comment "A smart contract for collateralized lending/borrowing. Examples: Aave, Compound, MakerDAO." ;
       :synonyms "lending, borrowing protocol, money market, DeFi lending" .

   :TokenContract a owl:Class ;
       rdfs:subClassOf :ContractAccount ;
       rdfs:label "Token Contract" ;
       rdfs:comment "An ERC-20, ERC-721, or ERC-1155 token contract." ;
       :synonyms "token, ERC20, ERC721, NFT contract" .

   # ---------- Transaction-related ----------
   :Transaction a owl:Class ;
       rdfs:subClassOf ethon:Transaction ;
       rdfs:label "Ethereum Transaction (extended)" ;
       rdfs:comment "A transaction on Ethereum with extended attributes for analytics." .

   :TokenTransfer a owl:Class ;
       rdfs:label "ERC-20/721 Token Transfer Event" ;
       rdfs:comment "A token transfer emitted as an ERC-20 Transfer event log within a transaction. Distinct from native ETH transfer." ;
       :synonyms "token transfer, ERC20 transfer, NFT transfer" .
   ```

3. **Properties:** ~25-30 properties. Mỗi property như mẫu:

   ```turtle
   :hasFrom a owl:ObjectProperty ;
       rdfs:label "has from address" ;
       rdfs:comment "The sender (from) address of an Ethereum transaction. This is the address that signed and sent the transaction. For meta-transactions, this is the relayer; the original signer is captured by :initiatedBy." ;
       :synonyms "sender, from, source, origin, sent by, originator" ;
       :exampleUsage "?tx :hasFrom :addr_x . # x sent the transaction" ;
       rdfs:domain :Transaction ;
       rdfs:range :Account .

   :initiatedBy a owl:ObjectProperty ;
       rdfs:label "initiated by" ;
       rdfs:comment "The original signer of a meta-transaction or account-abstraction operation. In standard transactions, this equals :hasFrom; in EIP-4337 user operations, this differs from the relayer." ;
       :synonyms "original signer, true sender, EIP-4337 user, meta-tx signer" ;
       :exampleUsage "?tx :initiatedBy :addr_x . # x is the true originator" ;
       rdfs:domain :Transaction ;
       rdfs:range :Account .
   ```

4. **Property categories cần có:**
   - **Identity:** `:hasLabel`, `:hasOwner`, `:hasCategory`, `:hasAlias`.
   - **Transaction:** `:hasFrom`, `:hasTo`, `:hasValue`, `:hasGasUsed`, `:hasGasPrice`, `:hasNonce`, `:hasInputData`, `:hasReceiptStatus`.
   - **Time:** `:hasTimestamp`, `:hasBlockNumber`.
   - **Token:** `:hasTokenSymbol`, `:hasTokenName`, `:hasDecimals`, `:transferredAmount`, `:transferredToken`.
   - **Block:** `:hasMiner`, `:hasGasLimit`, `:hasTxCount`.
   - **Meta-tx:** `:initiatedBy`, `:executedBy`.

5. **Annotation property tự định nghĩa:**
   ```turtle
   :synonyms a owl:AnnotationProperty ;
       rdfs:label "synonyms" ;
       rdfs:comment "Comma-separated list of synonym phrases used for schema linking from natural language questions." .

   :exampleUsage a owl:AnnotationProperty ;
       rdfs:label "example usage in SPARQL" ;
       rdfs:comment "Example SPARQL fragment showing canonical usage of this term." .
   ```

6. **Verify trong Protégé:**
   - Open file → Reasoner → Synchronize Reasoner (FaCT++ hoặc HermiT).
   - Không có "Inconsistent ontology" error.
   - Class hierarchy hiển thị đẹp.

7. **Verify ≥80% competency questions cover:** với mỗi câu, viết SPARQL bằng tay (ít nhất là sketch) chỉ dùng class/property đã định nghĩa. Nếu không viết được → thêm property/class vào ontology.

## Rủi ro & note

- **Cám dỗ "thêm hết cho chắc"** — đừng. 30 property đủ; quá nhiều sẽ làm schema linker noisy.
- **Domain/range chặt vs lỏng:** ưu tiên chặt cho schema check. Có thể lỏng ở annotation (e.g. `rdfs:domain :Account` thay vì `:Transaction` cho `:hasLabel`).
- **EthOn dùng `ethon:Transaction`** — extension dùng `:Transaction` sub-class. Quyết định trước khi RML mapping (Phase 2.4) dùng URI nào.
- **Đừng OWL DL quá** — full OWL2 reasoning chậm. RDFS + restrictions cơ bản đủ.

## Estimated effort

2-3 ngày.

## Trạng thái

`todo`

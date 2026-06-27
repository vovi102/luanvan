# 03 — Ontology Reference

> **Trạng thái:** `v0.1.0` finalized in T2.1.
> **Artifact chính:** `src/nl2sparql/kg/ontology/eth-kg-extension-v0.1.0.ttl`.
> **Quy tắc:** Mọi thay đổi class/property phải cập nhật file này, `src/nl2sparql/kg/ontology/changelog.md`, và decision log nếu đổi semantics.

## Naming convention

- **Namespace mặc định:** `https://thesis.example.org/eth-kg/`.
- **Prefix sử dụng:**
  - `:` — namespace mặc định của ontology extension.
  - `ethon:` — `http://ethon.consensys.net/` (ontology nền).
  - `xsd:` — XML Schema datatypes.
  - `rdfs:` — RDFS.
  - `owl:` — OWL.
  - `sh:` — SHACL cho Phase 2.5.

- **Class:** `PascalCase` (ví dụ `:ExchangeAccount`, `:DEXProtocol`).
- **Property:** `camelCase` mở đầu bằng động từ/giới từ (ví dụ `:hasFrom`, `:executedBy`, `:transferredAmount`).

## Class hierarchy v0.1.0

```
ethon:Account
└── :Account
    ├── :ExternallyOwnedAccount
    │   ├── :IndividualAccount
    │   ├── :ExchangeAccount
    │   ├── :ValidatorAccount
    │   └── :MEVActorAccount
    └── :ContractAccount
        ├── :MixerAccount
        ├── :DEXProtocol
        ├── :LendingProtocol
        ├── :BridgeProtocol
        ├── :NFTMarketplace
        └── :TokenContract

ethon:Tx
└── :Transaction

ethon:Block
└── :Block

ethon:LogEntry
├── :TokenTransfer
└── :ProtocolInteraction
```

## Property catalogue v0.1.0

### Identity and attribution

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:hasLabel` | `:Account` | `xsd:string` | Human-readable account label. |
| `:hasAlias` | `:Account` | `xsd:string` | Alternative names for entity linking. |
| `:hasOwner` | `:Account` | `xsd:string` | Organization/person/protocol believed to control account. |
| `:hasCategory` | `:Account` | `xsd:string` | Text category mirroring class membership. |
| `:hasConfidenceScore` | `:Account` | `xsd:decimal` | Attribution confidence. |
| `:hasSource` | `:Account` | `xsd:string` | Provenance/source of attribution. |

### Transaction

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:hasFrom` | `:Transaction` | `:Account` | Sender/source account. |
| `:hasTo` | `:Transaction` | `:Account` | Recipient/destination account; omitted for contract creation if unknown. |
| `:hasValue` | `:Transaction` | `xsd:decimal` | Native ETH value in wei. |
| `:hasGasUsed` | `:Transaction` | `xsd:integer` | Gas consumed by transaction. |
| `:hasGasPrice` | `:Transaction` | `xsd:decimal` | Gas price/effective gas price in wei per gas. |
| `:hasNonce` | `:Transaction` | `xsd:integer` | Sender transaction nonce. |
| `:hasInputData` | `:Transaction` | `xsd:string` | Raw calldata/input payload. |
| `:hasReceiptStatus` | `:Transaction` | `xsd:boolean` | Success/failure status. |
| `:includedInBlock` | `:Transaction` | `:Block` | Block containing transaction. |
| `:hasTimestamp` | `:Transaction` | `xsd:dateTime` | UTC block timestamp copied to transaction for query convenience. |
| `:hasBlockNumber` | `:Transaction` | `xsd:integer` | Containing block number. |

### Token transfer

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:emittedInTransaction` | `:TokenTransfer` | `:Transaction` | Transaction that emitted transfer event. |
| `:tokenTransferFrom` | `:TokenTransfer` | `:Account` | Token event sender/source holder. |
| `:tokenTransferTo` | `:TokenTransfer` | `:Account` | Token event recipient/destination holder. |
| `:transferredToken` | `:TokenTransfer` | `:TokenContract` | Token contract whose asset moved. |
| `:transferredAmount` | `:TokenTransfer` | `xsd:decimal` | Raw token amount in smallest unit. |
| `:hasTokenSymbol` | `:TokenContract` | `xsd:string` | Token ticker/symbol. |
| `:hasTokenName` | `:TokenContract` | `xsd:string` | Human-readable token name. |
| `:hasDecimals` | `:TokenContract` | `xsd:integer` | Token decimal precision. |

### Block

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:hasMiner` | `:Block` | `:Account` | Miner/validator/proposer/beneficiary account. |
| `:hasGasLimit` | `:Block` | `xsd:integer` | Block gas limit. |
| `:hasTxCount` | `:Block` | `xsd:integer` | Number of transactions in block. |

### Meta-transaction

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:initiatedBy` | `:Transaction` | `:Account` | Original signer/user for meta-transaction or account abstraction. |
| `:executedBy` | `:Transaction` | `:Account` | Relayer/executor/bundler that submitted execution. |

## Property documentation contract

Mọi property local phải có đủ:

- `rdfs:label`
- `rdfs:comment` ít nhất 2 câu
- `:synonyms` ít nhất 3 cụm, phân tách bằng dấu phẩy
- `:exampleUsage` chứa SPARQL fragment canonical
- `rdfs:domain`
- `rdfs:range`

`rdfs:comment`, `:synonyms`, và `:exampleUsage` là input chính cho schema linker ở Phase 4.

## Decision: ETH vs Wei

- **Lưu trong KG:** Wei (`xsd:decimal`, integer-valued).
- **Display ở UI/result:** ETH (chia 1e18).
- **Trong câu hỏi:** user dùng "ETH" → linker convert sang wei khi sinh SPARQL filter.

Lý do: tránh floating-point loss; SPARQL filter trên integer chính xác hơn.

## Decision: Time representation

- `:hasTimestamp` dùng `xsd:dateTime` (ISO 8601 UTC).
- Các filter "last month", "yesterday" được resolve thành range cụ thể bởi linker tier, không để LLM tự tính.

## Mở rộng vs giữ nguyên EthOn

- **Giữ nguyên:** không sửa, không override class/property EthOn.
- **Mở rộng:** local classes subclass `ethon:Account`, `ethon:Tx`, `ethon:Block`, và `ethon:LogEntry`.
- **Property mới:** thêm ở namespace local để mapping và schema linker kiểm soát semantics thống nhất.

## Competency-question coverage

- File: `src/nl2sparql/kg/ontology/competency-questions.md`.
- Tổng: 30 câu.
- Coverage: 30/30 câu có thể sketch bằng class/property trong v0.1.0.
- Nhóm: 10 trivial, 10 medium, 10 hard.

## Versioning ontology

- File: `src/nl2sparql/kg/ontology/eth-kg-extension-vX.Y.Z.ttl`.
- Bump minor khi thêm property/class tương thích ngược.
- Bump major khi đổi semantics, rename, hoặc đổi domain/range có thể phá mapping/query cũ.
- Mỗi bump → cập nhật `src/nl2sparql/kg/ontology/changelog.md`, file này, và decision log nếu có quyết định mới.

## Changelog

| Version | Date | Note |
|---|---|---|
| 0.1.0 | 2026-06-27 | Chốt ontology extension đầu tiên: 17 classes, 30 properties, 30 competency questions, rdflib validation. |
| 0.0.1-placeholder | 2025-XX | File khởi tạo, chưa chốt nội dung. |

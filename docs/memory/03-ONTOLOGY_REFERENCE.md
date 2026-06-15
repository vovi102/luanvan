# 03 — Ontology Reference

> **Trạng thái:** PLACEHOLDER — sẽ được hoàn thiện trong Phase 2 (task `phase-2-kg/01-ontology-extension.md`).
> **Quy tắc:** Mọi thay đổi class/property phải cập nhật file này + bumb version trong `decisions log`.

## Naming convention

- **Namespace mặc định:** `https://thesis.example.org/eth-kg/` (tạm; sẽ chốt ở Phase 2).
- **Prefix sử dụng:**
  - `:` — namespace mặc định (custom extension).
  - `ethon:` — `http://ethon.consensys.net/` (kế thừa).
  - `xsd:` — XML Schema datatypes.
  - `rdfs:` — RDFS.
  - `owl:` — OWL.
  - `sh:` — SHACL.

- **Class:** `PascalCase` (ví dụ `:ExchangeAccount`, `:DEXProtocol`).
- **Property:** `camelCase` mở đầu bằng động từ/giới từ (ví dụ `:hasFrom`, `:executedBy`, `:transferredAmount`).

## Class hierarchy (DỰ KIẾN — sẽ chốt ở Phase 2)

```
ethon:Account (kế thừa)
├── :ExternallyOwnedAccount
│   ├── :ExchangeAccount (sàn: Binance, Coinbase, ...)
│   ├── :MixerAccount (Tornado Cash, ...)
│   └── :IndividualAccount
└── :ContractAccount
    ├── :DEXProtocol (Uniswap, Curve, ...)
    ├── :LendingProtocol (Aave, Compound, ...)
    ├── :TokenContract (ERC20/ERC721)
    └── :OtherContract

ethon:Transaction (kế thừa)
└── :Transaction (extension nếu cần)

ethon:Block (kế thừa, dùng nguyên)

:TokenTransfer (mới, không có sẵn trong EthOn)
:LiquidityEvent (mới, cho DEX)
```

## Property dự kiến (sẽ chốt ở Phase 2)

### Quan hệ giao dịch

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:hasFrom` | `:Transaction` | `:Account` | Sender. Khác với `:initiatedBy` (signer trong meta-tx). |
| `:hasTo` | `:Transaction` | `:Account` | Recipient. Có thể là contract hoặc EOA. |
| `:initiatedBy` | `:Transaction` | `:Account` | Người ký gốc (cho meta-tx, account abstraction). |
| `:executedBy` | `:Transaction` | `:Account` | Người thực thi (relayer trong meta-tx). |
| `:hasValue` | `:Transaction` | `xsd:decimal` | Amount in wei (hoặc ETH — quyết định Phase 2). |
| `:hasGasUsed` | `:Transaction` | `xsd:integer` | |
| `:includedInBlock` | `:Transaction` | `:Block` | |
| `:hasTimestamp` | `:Transaction` | `xsd:dateTime` | Lấy từ `:Block`, replicate cho query nhanh. |

### Nhãn entity

| Property | Domain | Range | Ghi chú |
|---|---|---|---|
| `:hasLabel` | `:Account` | `xsd:string` | Tên đã biết (e.g. "Binance: Hot Wallet 14"). |
| `:hasOwner` | `:Account` | `xsd:string` | Tên tổ chức sở hữu (e.g. "Binance"). |
| `:hasCategory` | `:Account` | `xsd:string` | Free-text category (mirror cho dễ query). |

### Token

| Property | Domain | Range |
|---|---|---|
| `:hasTokenSymbol` | `:TokenContract` | `xsd:string` |
| `:hasTokenName` | `:TokenContract` | `xsd:string` |
| `:hasDecimals` | `:TokenContract` | `xsd:integer` |

## Property documentation (RICH — quan trọng cho schema linker!)

Mỗi property phải có `rdfs:label`, `rdfs:comment`, `:exampleUsage`, `rdfs:domain`, `rdfs:range`. Ví dụ:

```turtle
:hasFrom a owl:ObjectProperty ;
  rdfs:label "has from address" ;
  rdfs:comment "The sender (from) address of an Ethereum transaction. \
                This is the address that signed the transaction. \
                Differs from :initiatedBy which represents the original \
                signer in meta-transactions or account-abstraction patterns." ;
  :exampleUsage "?tx :hasFrom :addr_x . # x sent the transaction" ;
  :synonyms "sender, from, source, origin" ;
  rdfs:domain :Transaction ;
  rdfs:range :Account .
```

`:synonyms` field là QUAN TRỌNG cho schema linker — sẽ được embed cùng với `rdfs:comment`.

## Decision: ETH vs Wei

- **Lưu trong KG:** Wei (`xsd:decimal`, integer-valued).
- **Display ở UI/result:** ETH (chia 1e18).
- **Trong câu hỏi:** user dùng "ETH" → linker convert sang wei khi sinh SPARQL filter.

Lý do: tránh floating-point loss; SPARQL filter trên integer chính xác hơn.

## Decision: Time representation

- `:hasTimestamp` dùng `xsd:dateTime` (ISO 8601 UTC).
- Các filter "last month", "yesterday" được resolve thành range cụ thể bởi linker tier (KHÔNG để LLM tự tính).

## Mở rộng vs giữ nguyên EthOn

- **Giữ nguyên:** `ethon:Account`, `ethon:Transaction`, `ethon:Block`, `ethon:Contract`.
- **Mở rộng (subclass):** thêm `:ExchangeAccount`, `:MixerAccount`, `:DEXProtocol`, `:LendingProtocol` ở namespace local.
- **Property mới:** thêm ở namespace local. KHÔNG override property của EthOn.

## Versioning ontology

- File: `src/nl2sparql/kg/ontology/eth-kg-extension-vX.Y.ttl`.
- Bump minor `Y` khi thêm property/class.
- Bump major `X` khi đổi semantics (rename, đổi domain/range).
- Mỗi bump → 1 dòng trong `05-DECISION_LOG.md` + 1 dòng trong file này.

## Changelog

| Version | Date | Note |
|---|---|---|
| 0.0.1-placeholder | 2025-XX | File khởi tạo, chưa chốt nội dung. Chốt sau Phase 2. |

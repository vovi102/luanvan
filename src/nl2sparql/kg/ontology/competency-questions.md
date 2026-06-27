# Ethereum KG Ontology Competency Questions v0.1.0

These questions define the query coverage expected from
`eth-kg-extension-v0.1.0.ttl`. Every item below is covered by the local classes
and properties in the ontology extension.

## Trivial questions

- [x] CQ01: Count all transactions in a time range.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`
  - Properties: `:hasTimestamp`
  - SPARQL sketch:
    ```sparql
    SELECT (COUNT(?tx) AS ?count) WHERE { ?tx a :Transaction ; :hasTimestamp ?ts . FILTER(?ts >= "2024-01-01T00:00:00Z"^^xsd:dateTime) }
    ```

- [x] CQ02: List transactions above 1 ETH.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`
  - Properties: `:hasValue`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx ?value WHERE { ?tx a :Transaction ; :hasValue ?value . FILTER(?value >= 1000000000000000000) }
    ```

- [x] CQ03: List failed transactions.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`
  - Properties: `:hasReceiptStatus`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx WHERE { ?tx a :Transaction ; :hasReceiptStatus false . }
    ```

- [x] CQ04: Find transactions sent by a given account.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`, `:Account`
  - Properties: `:hasFrom`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx WHERE { ?tx a :Transaction ; :hasFrom ?account . }
    ```

- [x] CQ05: Find transactions received by a given account.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`, `:Account`
  - Properties: `:hasTo`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx WHERE { ?tx a :Transaction ; :hasTo ?account . }
    ```

- [x] CQ06: Show the block number for a transaction.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Transaction`
  - Properties: `:hasBlockNumber`
  - SPARQL sketch:
    ```sparql
    SELECT ?blockNumber WHERE { ?tx a :Transaction ; :hasBlockNumber ?blockNumber . }
    ```

- [x] CQ07: List known exchange accounts.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:ExchangeAccount`
  - Properties: `:hasLabel`, `:hasOwner`
  - SPARQL sketch:
    ```sparql
    SELECT ?account ?label ?owner WHERE { ?account a :ExchangeAccount ; :hasLabel ?label ; :hasOwner ?owner . }
    ```

- [x] CQ08: Find token contracts by symbol.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:TokenContract`
  - Properties: `:hasTokenSymbol`, `:hasTokenName`
  - SPARQL sketch:
    ```sparql
    SELECT ?token ?name WHERE { ?token a :TokenContract ; :hasTokenSymbol "USDC" ; :hasTokenName ?name . }
    ```

- [x] CQ09: List blocks with their transaction counts.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Block`
  - Properties: `:hasBlockNumber`, `:hasTxCount`
  - SPARQL sketch:
    ```sparql
    SELECT ?block ?n ?txCount WHERE { ?block a :Block ; :hasBlockNumber ?n ; :hasTxCount ?txCount . }
    ```

- [x] CQ10: Find accounts with low attribution confidence.
  - Difficulty: trivial
  - Coverage: covered
  - Classes: `:Account`
  - Properties: `:hasConfidenceScore`, `:hasSource`
  - SPARQL sketch:
    ```sparql
    SELECT ?account ?score WHERE { ?account a :Account ; :hasConfidenceScore ?score . FILTER(?score < 0.7) }
    ```

## Medium questions

- [x] CQ11: Top senders by total native ETH value.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Transaction`, `:Account`
  - Properties: `:hasFrom`, `:hasValue`
  - SPARQL sketch:
    ```sparql
    SELECT ?sender (SUM(?value) AS ?totalWei) WHERE { ?tx a :Transaction ; :hasFrom ?sender ; :hasValue ?value . } GROUP BY ?sender ORDER BY DESC(?totalWei) LIMIT 10
    ```

- [x] CQ12: Top recipients by transaction count.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Transaction`, `:Account`
  - Properties: `:hasTo`
  - SPARQL sketch:
    ```sparql
    SELECT ?recipient (COUNT(?tx) AS ?count) WHERE { ?tx a :Transaction ; :hasTo ?recipient . } GROUP BY ?recipient ORDER BY DESC(?count) LIMIT 10
    ```

- [x] CQ13: Transactions from exchanges to DEX protocols.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Transaction`, `:ExchangeAccount`, `:DEXProtocol`
  - Properties: `:hasFrom`, `:hasTo`, `:hasValue`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx ?value WHERE { ?tx a :Transaction ; :hasFrom ?ex ; :hasTo ?dex ; :hasValue ?value . ?ex a :ExchangeAccount . ?dex a :DEXProtocol . }
    ```

- [x] CQ14: Token transfers involving a given exchange.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:TokenTransfer`, `:ExchangeAccount`
  - Properties: `:tokenTransferFrom`, `:tokenTransferTo`, `:transferredAmount`
  - SPARQL sketch:
    ```sparql
    SELECT ?transfer ?amount WHERE { ?transfer a :TokenTransfer ; :transferredAmount ?amount . { ?transfer :tokenTransferFrom ?exchange } UNION { ?transfer :tokenTransferTo ?exchange } ?exchange a :ExchangeAccount . }
    ```

- [x] CQ15: Token transfer volume by token symbol.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:TokenTransfer`, `:TokenContract`
  - Properties: `:transferredToken`, `:transferredAmount`, `:hasTokenSymbol`
  - SPARQL sketch:
    ```sparql
    SELECT ?symbol (SUM(?amount) AS ?volume) WHERE { ?transfer a :TokenTransfer ; :transferredToken ?token ; :transferredAmount ?amount . ?token :hasTokenSymbol ?symbol . } GROUP BY ?symbol
    ```

- [x] CQ16: Failed high-gas transactions.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Transaction`
  - Properties: `:hasReceiptStatus`, `:hasGasUsed`, `:hasGasPrice`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx ?gasUsed ?gasPrice WHERE { ?tx a :Transaction ; :hasReceiptStatus false ; :hasGasUsed ?gasUsed ; :hasGasPrice ?gasPrice . FILTER(?gasUsed > 500000) }
    ```

- [x] CQ17: Blocks proposed by a known validator account.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Block`, `:ValidatorAccount`
  - Properties: `:hasMiner`, `:hasBlockNumber`, `:hasTimestamp`
  - SPARQL sketch:
    ```sparql
    SELECT ?block ?number ?ts WHERE { ?block a :Block ; :hasMiner ?validator ; :hasBlockNumber ?number ; :hasTimestamp ?ts . ?validator a :ValidatorAccount . }
    ```

- [x] CQ18: Transactions that call contracts with input data.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Transaction`, `:ContractAccount`
  - Properties: `:hasTo`, `:hasInputData`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx ?input WHERE { ?tx a :Transaction ; :hasTo ?contract ; :hasInputData ?input . ?contract a :ContractAccount . FILTER(STRLEN(?input) > 10) }
    ```

- [x] CQ19: Token transfers emitted by high-value transactions.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:TokenTransfer`, `:Transaction`
  - Properties: `:emittedInTransaction`, `:hasValue`, `:transferredAmount`
  - SPARQL sketch:
    ```sparql
    SELECT ?transfer ?tx ?amount WHERE { ?transfer a :TokenTransfer ; :emittedInTransaction ?tx ; :transferredAmount ?amount . ?tx :hasValue ?value . FILTER(?value > 1000000000000000000) }
    ```

- [x] CQ20: Accounts grouped by owner and category.
  - Difficulty: medium
  - Coverage: covered
  - Classes: `:Account`
  - Properties: `:hasOwner`, `:hasCategory`
  - SPARQL sketch:
    ```sparql
    SELECT ?owner ?category (COUNT(?account) AS ?count) WHERE { ?account a :Account ; :hasOwner ?owner ; :hasCategory ?category . } GROUP BY ?owner ?category
    ```

## Hard questions

- [x] CQ21: Did any major DEX receive ETH from a known mixer?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:MixerAccount`, `:DEXProtocol`
  - Properties: `:hasFrom`, `:hasTo`, `:hasValue`
  - SPARQL sketch:
    ```sparql
    ASK { ?tx a :Transaction ; :hasFrom ?mixer ; :hasTo ?dex ; :hasValue ?value . ?mixer a :MixerAccount . ?dex a :DEXProtocol . FILTER(?value >= 1000000000000000000000) }
    ```

- [x] CQ22: Which exchange sent the most value to lending protocols?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:ExchangeAccount`, `:LendingProtocol`
  - Properties: `:hasFrom`, `:hasTo`, `:hasValue`, `:hasOwner`
  - SPARQL sketch:
    ```sparql
    SELECT ?owner (SUM(?value) AS ?totalWei) WHERE { ?tx a :Transaction ; :hasFrom ?exchange ; :hasTo ?lending ; :hasValue ?value . ?exchange a :ExchangeAccount ; :hasOwner ?owner . ?lending a :LendingProtocol . } GROUP BY ?owner ORDER BY DESC(?totalWei) LIMIT 1
    ```

- [x] CQ23: Which mixer-funded accounts later sent tokens to exchanges?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:TokenTransfer`, `:MixerAccount`, `:ExchangeAccount`
  - Properties: `:hasFrom`, `:hasTo`, `:tokenTransferFrom`, `:tokenTransferTo`, `:hasTimestamp`
  - SPARQL sketch:
    ```sparql
    SELECT ?account ?exchange WHERE { ?funding a :Transaction ; :hasFrom ?mixer ; :hasTo ?account ; :hasTimestamp ?t1 . ?mixer a :MixerAccount . ?transfer a :TokenTransfer ; :tokenTransferFrom ?account ; :tokenTransferTo ?exchange . ?exchange a :ExchangeAccount . }
    ```

- [x] CQ24: Find relayed transactions where the initiator differs from the executor.
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:Account`
  - Properties: `:initiatedBy`, `:executedBy`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx ?initiator ?executor WHERE { ?tx a :Transaction ; :initiatedBy ?initiator ; :executedBy ?executor . FILTER(?initiator != ?executor) }
    ```

- [x] CQ25: Which token had the largest transfer volume through DEX protocols?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:TokenTransfer`, `:TokenContract`, `:DEXProtocol`
  - Properties: `:tokenTransferTo`, `:transferredToken`, `:transferredAmount`, `:hasTokenSymbol`
  - SPARQL sketch:
    ```sparql
    SELECT ?symbol (SUM(?amount) AS ?volume) WHERE { ?transfer a :TokenTransfer ; :tokenTransferTo ?dex ; :transferredToken ?token ; :transferredAmount ?amount . ?dex a :DEXProtocol . ?token :hasTokenSymbol ?symbol . } GROUP BY ?symbol ORDER BY DESC(?volume) LIMIT 1
    ```

- [x] CQ26: Which bridge contracts received funds from exchanges before token transfers out?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:TokenTransfer`, `:ExchangeAccount`, `:BridgeProtocol`
  - Properties: `:hasFrom`, `:hasTo`, `:tokenTransferFrom`, `:hasTimestamp`
  - SPARQL sketch:
    ```sparql
    SELECT ?bridge ?tx ?transfer WHERE { ?tx a :Transaction ; :hasFrom ?exchange ; :hasTo ?bridge ; :hasTimestamp ?t1 . ?exchange a :ExchangeAccount . ?bridge a :BridgeProtocol . ?transfer a :TokenTransfer ; :tokenTransferFrom ?bridge . }
    ```

- [x] CQ27: Find NFT marketplace interactions with high native ETH value.
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:NFTMarketplace`
  - Properties: `:hasTo`, `:hasValue`, `:hasInputData`
  - SPARQL sketch:
    ```sparql
    SELECT ?tx ?value WHERE { ?tx a :Transaction ; :hasTo ?market ; :hasValue ?value ; :hasInputData ?input . ?market a :NFTMarketplace . FILTER(?value > 10000000000000000000) }
    ```

- [x] CQ28: Which MEV actors interacted with DEX protocols most often?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Transaction`, `:MEVActorAccount`, `:DEXProtocol`
  - Properties: `:hasFrom`, `:hasTo`
  - SPARQL sketch:
    ```sparql
    SELECT ?actor (COUNT(?tx) AS ?count) WHERE { ?tx a :Transaction ; :hasFrom ?actor ; :hasTo ?dex . ?actor a :MEVActorAccount . ?dex a :DEXProtocol . } GROUP BY ?actor ORDER BY DESC(?count)
    ```

- [x] CQ29: Which accounts received tokens and then sent native ETH to an exchange?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:TokenTransfer`, `:Transaction`, `:ExchangeAccount`
  - Properties: `:tokenTransferTo`, `:hasFrom`, `:hasTo`, `:hasTimestamp`
  - SPARQL sketch:
    ```sparql
    SELECT ?account ?exchange WHERE { ?transfer a :TokenTransfer ; :tokenTransferTo ?account . ?tx a :Transaction ; :hasFrom ?account ; :hasTo ?exchange . ?exchange a :ExchangeAccount . }
    ```

- [x] CQ30: Which labeled owners operate accounts across multiple DeFi categories?
  - Difficulty: hard
  - Coverage: covered
  - Classes: `:Account`
  - Properties: `:hasOwner`, `:hasCategory`, `:hasAlias`
  - SPARQL sketch:
    ```sparql
    SELECT ?owner (COUNT(DISTINCT ?category) AS ?categoryCount) WHERE { ?account a :Account ; :hasOwner ?owner ; :hasCategory ?category . OPTIONAL { ?account :hasAlias ?alias . } } GROUP BY ?owner HAVING(?categoryCount > 1)
    ```

# Receipt verification

To verify a receipt follow https://microsoft.github.io/CCF/main/use_apps/verify_tx.html#receipt-verification

To obtain the custom claims digest:

1. Clear the header field in the response
2. Build a [`ReceiptClaims`](../proto/lskvserver.proto) protobuf type from the request sent and response received.
3. Serialize the `ReceiptClaims` and compute the sha256 hex digest
4. Compare this hex digest with the `claims_digest` in the receipt

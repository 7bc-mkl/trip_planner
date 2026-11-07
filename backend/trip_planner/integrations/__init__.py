"""Outbound integrations — the model providers, and nothing else.

One rule holds this package together: **a provider's wire format stops here.**
`model.py` owns the contract, the prompt, the timeout, the retry, the budget and
the validation; each adapter owns exactly one thing, which is how its provider
spells an HTTP request and a response. Nothing under `domain/`, `inbound/` or
`api/` imports an adapter or knows one exists.

That is what makes D24's promise — *changing the selected provider is a
configuration change, not a code change* — true rather than aspirational.
"""

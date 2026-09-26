"""AWS SES/SNS/S3 inbound mail — the one external integration this app has.

Two modules, and the split is the boundary that matters: `ses.py` is the **only**
place that knows what an SNS envelope or an SES event looks like, and everything
downstream consumes the plain `DeliveryNotice` and `ReceivedMessage` values
`transport.py` defines. No routing, storage or approval code reads an AWS field,
which is what keeps D25's choice of transport a choice rather than a shape the
whole feature has taken on.
"""

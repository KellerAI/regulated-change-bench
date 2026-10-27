# Payments API

| Method | Path | Action | MFA |
|---|---|---|---|
| POST | /payments | create_payment | no |
| POST | /payments/{id}/approve | approve_payment | yes |
| POST | /payments/{id}/release | release_payment | yes |
| GET | /payments/{id}/status | view_account | no |

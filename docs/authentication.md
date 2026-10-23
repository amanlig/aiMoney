# Authentication architecture

Authorized accounts are created manually in PostgreSQL. There is no public signup.
The operator manages users through `auth_admin.py` or SQL; see the
[administration guide](../deploy/README.md). Everyone authorized currently shares
one portfolio, including its settings and application controls.

```mermaid
sequenceDiagram
    actor User
    participant UI as React sign-in
    participant Proxy as Caddy HTTPS
    participant API as FastAPI authentication
    participant DB as PostgreSQL
    participant SES as Amazon SES
    User->>UI: Enter authorized email
    UI->>Proxy: POST request-code, same origin
    Proxy->>API: Overwrite trusted client-IP header
    API->>DB: Check limits and active app_users record
    alt Active, manually provisioned user
        API->>DB: Save code HMAC and expiry
        API-->>UI: Generic response, challenge ID
        API->>SES: Deliver short-lived code using EC2 role
        SES-->>User: Email code
    else Unknown or disabled email
        API-->>UI: Same generic response, no email
    end
    User->>UI: Enter code
    UI->>API: POST verify with challenge ID
    API->>DB: Atomically validate expiry/attempts and consume code
    API->>DB: Save hash of random session token
    API-->>UI: Secure HttpOnly host-only cookie
    UI->>API: Portfolio request with cookie
    API->>DB: Validate session and active user
    API-->>UI: Authorized shared-portfolio data
```

```mermaid
erDiagram
    app_users ||--o{ auth_challenges : receives
    app_users ||--o{ auth_sessions : owns
    app_users {
        bigint id PK
        text email UK
        integer active
        bigint created_at
    }
    auth_challenges {
        text id PK
        bigint user_id FK
        text code_hash
        bigint created_at
        bigint expires_at
        integer attempts
        bigint used_at
    }
    auth_sessions {
        text token_hash PK
        bigint user_id FK
        bigint created_at
        bigint expires_at
    }
    auth_rate_limits {
        text bucket PK
        bigint window_start
        integer hits
    }
```

Codes expire after 10 minutes and 5 attempts. Every accepted request replaces
that user's previous code. Rate limits cover email, client IP and global sending;
verification attempts are limited per challenge and IP. PostgreSQL transaction
locks prevent concurrent code reuse. Database failures fail closed.

The browser session lasts 12 hours, or 30 days with the personal-device option.
Sign-out revokes it server-side. Each protected request checks the user's active
status, so disabling a user blocks existing sessions immediately. The minimal
health endpoint and sign-in assets contain no portfolio records and remain public.

The HMAC secret, broker credentials and provider configuration stay in `.secrets/`
on encrypted EBS, outside Git and image layers. AWS credentials are temporary
instance-role credentials with permission only for the app's SES sender.

Future work: scheduled backups and recovery drills, audit events and explicit
roles. Per-user portfolios require ownership and access checks throughout the
data model and API, plus separated broker credentials; adding email accounts
alone does not create that isolation. See [future direction](../ARCHITECTURE.md#future-direction).

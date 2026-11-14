# System Map

How the [DrChrono PDF Compiler](README.md) fits together: what the user does, which parts run, and what comes out. Per-app details are in each folder's `DOC.md`.

## User journey

| # | Page | User does | App does | User sees |
|---|---|---|---|---|
| 1 | `/`, `/authorize/` (`verify`) | Opens the site, clicks **Sign in with DrChrono** | Shows the sign-in page (or goes to search if already signed in); saves a random `state` and redirects | DrChrono sign-in |
| 2 | `/oauth/callback` (`verify`) | Signs in to DrChrono, allows access | Checks `state`, exchanges code for tokens, saves them to a passwordless local user | "Successfully connected as …", search page |
| 3 | `/search/` (`search`) | Enters first name, last name and/or DOB, clicks **Search Patients** | Calls `/api/patients_summary`, stores results in session | "Found N matching patient(s)." |
| 4 | `/search/results/` (`search`) | Clicks **Select & View Appointments** | Loads every past, attended visit scheduled in the last 3 years with a clinical note PDF | Patient cards (name, DOB, chart ID) |
| 5 | `/appts/patient/<id>/` (`appts`) | Unticks unwanted visits, clicks **Generate PDF Report for Selected** | — | Visits newest first, all ticked |
| 6 | `POST /pdf/patient/<id>/generate-selected/` (`pdf`) | Waits | Fetches data, draws forms, merges | Download `Patient_<First>_<Last>_REPORT.pdf`, or back to step 5 with errors |
| 7 | `POST /logout/` (`verify`) | Clicks **Log out** in the navbar | Revokes the app's DrChrono access, deletes stored tokens, ends the session (DrChrono itself stays signed in) | Sign-in page: "You're signed out." |

## Components

```mermaid
flowchart LR
    U([User browser])

    subgraph Django["Django app (Render, gunicorn)"]
        V[verify<br/>sign-in, tokens, require_auth]
        S[search<br/>patient search]
        A[appts<br/>visit list]
        P[pdf<br/>build + merge PDF]
        C[core<br/>DrChrono API client]
    end

    subgraph DC["DrChrono"]
        O[OAuth2<br/>/o/authorize, /o/token]
        API[REST API<br/>/api/...]
        N[Clinical note PDFs]
    end

    DB[(PostgreSQL<br/>users, tokens, sessions)]
    CFG[Config<br/>PROVIDER_* env vars<br/>pdf/forms/HCFA.pdf]

    U -- sign in --> V
    U -- search --> S
    U -- pick visits --> A
    U -- generate --> P
    P -- PDF download --> U

    V --> O
    V --> API
    V --> DB
    S --> C
    S --> DB
    A --> C
    P --> C
    C --> API
    P --> N
    P --> CFG
```

Every page after sign-in passes through `verify.require_auth`: it refreshes the token when less than 5 minutes are left, or sends the user back to the sign-in page.

## PDF generation (step 6)

```mermaid
sequenceDiagram
    actor User
    participant PDF as pdf app
    participant DC as DrChrono

    User->>PDF: POST ticked appointment IDs
    PDF->>DC: Refresh token if under 5 minutes left
    Note over PDF,DC: Fetch once (one reused connection)
    PDF->>DC: GET /api/patients/{id}
    PDF->>DC: GET /api/appointments (every page)
    PDF->>DC: GET /api/line_items?patient={id}
    PDF->>PDF: Check ticked visits belong to the patient, and claim details are complete
    PDF->>PDF: Balance report (all eligible visits)
    loop Each ticked visit, oldest first
        PDF->>DC: Download clinical note PDF
        PDF->>PDF: Claim form(s), 6 charges per form
        PDF->>PDF: Skip and list anything that fails
    end
    PDF->>PDF: Merge ('Not included' page first if anything was skipped)
    PDF-->>User: PDF download (Patient_First_Last_REPORT.pdf)
```

## Output

```
Patient_<First>_<Last>_REPORT.pdf
├── Not included          only if something was skipped: what, and why
├── Balance report        provider, patient, total balance, unpaid line items
├── Visit A (oldest)
│   ├── Clinical note     DrChrono's PDF, as is
│   └── HCFA-1500         one page per 6 charges
├── Visit B
│   ├── Clinical note
│   └── HCFA-1500
└── … per ticked visit, oldest first
```

HCFA-1500 box sources:

| Boxes | Source |
|---|---|
| 2, 3, 4, 5, 7, 11 | DrChrono patient: name, DOB, sex, address, cell phone |
| 21 | DrChrono appointment: ICD-10 codes |
| 12, 31 dates | Clinical note's `updated_at` |
| 24A, 24D, 24F, 28 | DrChrono line items: dates, CPT codes, charges, total |
| 24J, 25, 26, 31, 32, 33 | Env vars (see [README](README.md#environment-variables)) |
| 1, 6, 10, 11d, 12, 13, 24B, 24E, 24G, 27 | Hardcoded (see [`pdf/DOC.md`](drchrono_compiler/pdf/DOC.md#hardcoded-hcfa-values)) |

## Data kept

| Where | What |
|---|---|
| Database | Django user (no password), DrChrono access/refresh tokens |
| Session | OAuth state, last search results and filters |
| Env vars | DrChrono app credentials, practice details |
| Not stored | Appointments, line items, generated PDFs |

## Errors the user sees

| Situation | Message / result |
|---|---|
| Token expiring | Refreshed silently |
| Not signed in | Sign-in page |
| Token can't be refreshed | Sign-in page: "Your DrChrono session expired, please sign in again." |
| Cancel on DrChrono's screen | Sign-in page: "Sign-in was cancelled." |
| Stale or forged sign-in return | Sign-in page: "Sign-in expired, please try again." |
| DrChrono error during sign-in | Sign-in page: "Couldn't sign in to DrChrono, please try again." |
| CSRF failure (stale session) | Sign-in page: "Your session has expired, please sign in again." |
| Empty search form | "Please provide at least one of: First Name, Last Name, or Date Of Birth" |
| No matches | "No patients found matching your criteria." |
| DrChrono error on search or the appointment list | A plain message, e.g. "DrChrono isn't responding. Try again in a moment." or "DrChrono's hourly request limit was reached…" |
| DrChrono rejects the token mid-session (401) | Sign-in page: "Your DrChrono session expired, please sign in again." |
| More than 50 search matches | "DrChrono found more than 50 matches. Add details to narrow the search." |
| Visits can't load | "Failed to load appointments: …", empty list |
| Patient or practice details every claim needs are missing | Back on the visit list: "Can't build claim forms: missing patient zip code." |
| One visit's note or claim can't be built | PDF still downloads; a first "Not included" page lists what was skipped and why |

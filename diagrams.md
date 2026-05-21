# System Diagrams in Mermaid Syntax

These diagrams are based on the Django web application for student document requests. Each section contains Mermaid code that can be pasted directly into the [Mermaid Live Editor](https://mermaid.live).

## Use Case Diagram

```mermaid
graph TD
    A[Student] --> B[Login with Student ID and OTP]
    A --> C[Submit Document Request]
    A --> D[View Own Requests]
    A --> E[Delete Own Request]

    F[Registrar] --> G[Login with Credentials]
    F --> H[View All Requests]
    F --> I[Approve/Reject Request]
    F --> J[Start Processing Document]
    F --> K[Mark Document Ready]
    F --> L[Mark Document Completed]
    F --> M[Delete Request]

    N[Cashier] --> O[Login with Credentials]
    N --> P[View Payment Pending Requests]
    N --> Q[Confirm Payment]

    B --> R[Access Student Dashboard]
    C --> R
    D --> R
    E --> R

    G --> S[Access Registrar Dashboard]
    H --> S
    I --> S
    J --> S
    K --> S
    L --> S
    M --> S

    O --> T[Access Cashier Dashboard]
    P --> T
    Q --> T
```

## Class Diagram

```mermaid
classDiagram
    class User {
        +username: CharField
        +email: EmailField
        +groups: ManyToMany
    }

    class StudentMasterList {
        +student_id: CharField
        +full_name: CharField
        +course: CharField
        +major: CharField
        +email: EmailField
        +phone_number: CharField
    }

    class OTPToken {
        +user: ForeignKey
        +otp_code: CharField
        +created_at: DateTimeField
        +is_verified: BooleanField
        +generate_code()
    }

    class DocumentType {
        +name: CharField
        +price: DecimalField
    }

    class DocumentRequest {
        +student: ForeignKey
        +document_type: ForeignKey
        +reason: TextField
        +status: CharField
        +created_at: DateTimeField
    }

    class Profile {
        +user: OneToOneField
        +must_change_password: BooleanField
    }

    User ||--o{ OTPToken : has
    User ||--o{ DocumentRequest : submits
    User ||--|| Profile : has
    DocumentRequest --> DocumentType : requests
```

## Sequence Diagram (Student Login Flow)

```mermaid
sequenceDiagram
    participant Student
    participant LoginView
    participant StudentMasterList
    participant User
    participant OTPToken
    participant EmailService
    participant VerifyOTPView

    Student->>LoginView: Enter Student ID
    LoginView->>StudentMasterList: Check if ID exists
    StudentMasterList-->>LoginView: Student data or None
    alt ID exists
        LoginView->>User: Get or create User
        User-->>LoginView: User object
        LoginView->>OTPToken: Create OTP
        OTPToken-->>LoginView: OTP object
        LoginView->>EmailService: Send OTP email
        EmailService-->>LoginView: Email sent
        LoginView-->>Student: Redirect to OTP verification
        Student->>VerifyOTPView: Enter OTP
        VerifyOTPView->>OTPToken: Verify OTP
        OTPToken-->>VerifyOTPView: Verification result
        alt Valid OTP
            VerifyOTPView->>Student: Login successful, redirect to dashboard
        else
            VerifyOTPView-->>Student: Invalid OTP
        end
    else
        LoginView-->>Student: ID not found
    end
```

## Package Diagram

```mermaid
graph TD
    A[thesis] --> B[requests_app]
    A --> C[static]
    A --> D[db.sqlite3]

    B --> E[models.py]
    B --> F[views.py]
    B --> G[forms.py]
    B --> H[urls.py]
    B --> I[admin.py]
    B --> J[templates/]
    B --> K[migrations/]

    J --> L[base.html]
    J --> M[dashboard.html]
    J --> N[login_id.html]
    J --> O[login_otp.html]
    J --> P[registrar_dashboard.html]
    J --> Q[cashier_dashboard.html]
    J --> R[staff_login.html]

    C --> S[css/style.css]
```

## Deployment Diagram

```mermaid
graph TD
    A[Client Browser] --> B[Web Server]
    B --> C[Django Application]
    C --> D[SQLite Database]

    B --> E[Email Service]
    C --> F[Static Files]

    subgraph "Server Environment"
        B
        C
        D
        E
        F
    end

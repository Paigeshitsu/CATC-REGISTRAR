# Systems Architecture

## Architectural Pattern and Style Used

The web-based document request system for the Computer Arts and Technological College (CATC) employs the **Model-View-Controller (MVC)** architectural pattern, adapted through the Django web framework. This pattern separates the application into three interconnected components: the Model, which handles data and business logic; the View, which manages user interface presentation; and the Controller, which processes user input and coordinates interactions between the Model and View.

### Model Layer
- **Django Models**: Represented by classes in `models.py` such as `DocumentRequest`, `StudentMasterList`, `OTPToken`, and `DocumentType`. These define the data structure, relationships, and business rules.
- **Database**: Uses SQLite for data persistence, providing a lightweight, file-based relational database suitable for development and small-scale deployment.
- **ORM**: Django's Object-Relational Mapping allows seamless interaction between Python objects and database tables, abstracting SQL operations.

### View Layer
- **Django Templates**: HTML templates in the `templates/` directory (e.g., `dashboard.html`, `registrar_dashboard.html`) render dynamic content using Django's template language.
- **Forms**: Custom forms in `forms.py` handle user input validation and rendering, integrating with templates for a consistent user experience.
- **Static Files**: CSS and JavaScript files in the `static/` directory enhance the visual presentation and interactivity.

### Controller Layer
- **Django Views**: Functions in `views.py` act as controllers, processing HTTP requests, interacting with models, and returning appropriate responses.
- **URL Routing**: Defined in `urls.py`, mapping URLs to view functions for request handling.
- **Middleware**: Django's built-in middleware manages sessions, authentication, and cross-site request forgery (CSRF) protection.

The system also incorporates **Layered Architecture** style, organizing components into distinct layers:
1. **Presentation Layer**: User interfaces and templates
2. **Application Layer**: Views and business logic
3. **Domain Layer**: Models and data entities
4. **Infrastructure Layer**: Database and external services (e.g., email)

This layered approach ensures separation of concerns, making the system maintainable, testable, and scalable. The **RESTful** style is partially implemented through Django's URL patterns and HTTP method handling, though not fully stateless due to session management.

### Controller Layer
- **Django Views**: Functions in `views.py` act as controllers, processing HTTP requests, interacting with models, and returning appropriate responses.
- **URL Routing**: Defined in `urls.py`, mapping URLs to view functions for request handling.
- **Middleware**: Django's built-in middleware manages sessions, authentication, and cross-site request forgery (CSRF) protection.

The system also incorporates **Layered Architecture** style, organizing components into distinct layers:
1. **Presentation Layer**: User interfaces and templates
2. **Application Layer**: Views and business logic
3. **Domain Layer**: Models and data entities
4. **Infrastructure Layer**: Database and external services (e.g., email)

This layered approach ensures separation of concerns, making the system maintainable, testable, and scalable. The **RESTful** style is partially implemented through Django's URL patterns and HTTP method handling, though not fully stateless due to session management.

**Package Structure:**
```
thesis/
├── requests_app/
│   ├── models.py          # Data models
│   ├── views.py           # Business logic and controllers
│   ├── forms.py           # Form definitions
│   ├── urls.py            # URL routing
│   ├── admin.py           # Admin interface configuration
│   ├── decorators.py      # Custom decorators for role-based access
│   ├── templates/         # HTML templates
│   ├── migrations/        # Database schema migrations
│   └── __init__.py
├── thesis/
│   ├── settings.py        # Django configuration
│   ├── urls.py            # Main URL configuration
│   └── wsgi.py            # WSGI application
├── static/                # Static assets
└── manage.py              # Django management script
```

**Key Development Principles:**
- **Modularity**: Each Django app (requests_app) encapsulates related functionality
- **Reusability**: Models and forms are designed for reuse across views
- **Separation of Concerns**: Templates handle presentation, views handle logic, models handle data
- **Configuration Management**: Settings are centralized in `settings.py`

### Physical View
The physical view describes the system's deployment and hardware/software infrastructure.

**Deployment Architecture:**
- **Web Server**: Runs Django application via WSGI (e.g., Gunicorn in production)
- **Database Server**: SQLite database file stored on the same server
- **Email Service**: Integrated SMTP service for OTP delivery
- **Client**: Web browsers accessing the application

**Hardware Requirements:**
- **Server**: Minimum 2GB RAM, 20GB storage, capable of running Python 3.8+
- **Client**: Standard web browser with JavaScript enabled
- **Network**: Internet connection for email services

**Software Stack:**
- **Operating System**: Cross-platform (Windows/Linux/macOS)
- **Web Framework**: Django 4.x
- **Database**: SQLite 3.x
- **Programming Language**: Python 3.8+
- **Frontend**: HTML5, CSS3, Bootstrap (via templates)
- **Email**: Django's email backend with SMTP

The system is designed for single-server deployment with potential for scaling through database migration to PostgreSQL and addition of load balancers for high-traffic scenarios.

### Scenarios View (Use Case Realizations)
This view illustrates how architectural components collaborate to realize key use cases.

**Use Case: Student Submits Document Request**
1. Student accesses login page (View)
2. Enters ID, system validates (Controller/Model)
3. OTP generated and emailed (Model/Service)
4. Student verifies OTP (Controller)
5. Redirected to dashboard (View)
6. Submits request form (View/Controller)
7. Request saved to database (Model)

**Use Case: Registrar Approves Request**
1. Registrar logs in (Controller)
2. Views pending requests (View/Model)
3. Updates request status (Controller/Model)
4. System sends notifications if configured (Service)

These views collectively provide a comprehensive understanding of the system's architecture, supporting design decisions, implementation, and maintenance activities.
